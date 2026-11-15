"""From Hyprland + /proc + ~/.claude to one Snapshot.

`gather` does the reading (compositor, process tree, session files) and `build`
is pure: the same Inputs always give the same Snapshot. `collect` is both.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import NamedTuple

from .claude import SESSION_ID, SUBAGENT_KEEP_S, SUBAGENT_MAX, ClaudeHome, Subagent, doing, doing_line, project_of
from .const import ALWAYS_SHOWN, MAX_WS, TAG
from .hypr import Hypr
from .procfs import Proc
from .strings import printable

STATES = {"busy", "shell", "idle", "waiting"}
RANK = {"waiting": 0, "busy": 1}           # every other state ranks 2
GHOST_ENTRYPOINTS = {"sdk-cli", "sdk-py", "sdk-ts"}
# A turn that ended with its own background work still out is not over: the
# session goes on by itself when the work reports back. Most telling kind first.
WAITING_ON = ("agent", "shell", "monitor")
# A background session (kind bg) runs under Claude Code's daemon; the terminal
# that shows it holds only a `claude attach <job>` client, where <job> is the
# session file's jobId, the head of its sessionId (measured 2.1.325).
JOB_ID = re.compile(r"^[0-9a-f-]{8,36}$")

# What Claude Code animates at the head of a window title: braille spinner
# frames, asterisks, the middle dot. Absent from JetBrainsMono Nerd Font, they
# drag in a fallback (colour emoji included) that renders as specks. Only the
# leading run goes: "Pull request #12 · repo" keeps its dot.
SPINNER = re.compile(r"^[\s⠀-⣿✳✲✻✶✢✽·•]+")

BROWSERS = {
    "firefox": re.compile(r"\s+[—-]\s+Mozilla Firefox$"),
    "zen": re.compile(r"\s+[—-]\s+Zen( Browser)?$"),
    "chromium": re.compile(r"\s+-\s+Chromium$"),
    "google-chrome": re.compile(r"\s+-\s+Google Chrome$"),
    "brave-browser": re.compile(r"\s+-\s+Brave$"),
}
TERMINALS = {"kitty", "alacritty", "foot", "wezterm", "com.mitchellh.ghostty"}
EDITORS = {"nvim", "vim", "hx", "emacs"}
CODE = {"code": " - Visual Studio Code", "code-oss": " - Code - OSS", "vscodium": " - VSCodium"}
FILES = {"thunar", "nautilus", "org.gnome.nautilus", "pcmanfm"}


@dataclass
class Session:
    pid: int
    sid: str
    kind: str
    cwd: str
    project: str
    title: str | None
    name: str | None
    state: str                       # waiting | busy | shell | idle | unknown
    waiting_for: str | None
    since: float | None              # seconds, from statusUpdatedAt
    source: str                      # ahora | tool | away | hecho | none
    lines: list[str]
    subagents: list[Subagent]        # live first, at most SUBAGENT_MAX
    workspace: int | None = None
    window: str | None = None
    tagged: bool = False
    doing: str = ""                  # one line, claude.doing_line
    asked: str = ""                  # first sentence of the user's last prompt
    waiting_on: str | None = None    # busy only because of background work: WAITING_ON
    did: str = ""                    # first line of the latest Hecho
    job: str = ""                    # what `claude attach <job>` names (jobId), bg sessions


@dataclass
class Window:
    address: str
    ws: int
    focus: int
    kind: str                        # claude | term | nvim | code | files | browser | window
    label: str
    title: str                       # the window title, spinner stripped
    sessions: list[Session] = field(default_factory=list)
    lead: Session | None = None      # the session that names the window


@dataclass
class Workspace:
    id: int
    output: str
    active: bool
    windows: list[Window]            # most recently focused first

    @property
    def occupied(self) -> bool:
        return bool(self.windows)

    @property
    def head(self) -> Window | None:
        return self.windows[0] if self.windows else None

    @property
    def kind(self) -> str:
        """claude while any session lives here, whichever window was focused
        last; else the most recently focused window's kind."""
        if self.lead:
            return "claude"
        return self.head.kind if self.head else "window"

    @property
    def label(self) -> str:
        """The lead session's project; else the most recently focused window's label."""
        lead = self.lead
        if lead:
            return lead.project
        return self.head.label if self.head else ""

    @property
    def state(self) -> str | None:
        """waiting if anything in it waits, else busy, else idle; None without sessions."""
        states = {s.state for w in self.windows for s in w.sessions}
        for st in ("waiting", "busy"):
            if st in states:
                return st
        return "idle" if states else None

    @property
    def lead(self) -> Session | None:
        """The session a bar shows for this workspace: waiting, else busy, else
        any. Ties go to the most recently focused window (the focused one while
        the workspace is active) and inside it to the session naming the window,
        so the slot's label and its lead agree; then to the oldest `since`."""
        def key(c: tuple[int, Window, Session]):
            i, w, s = c
            return (RANK.get(s.state, 2), i, s is not w.lead,
                    s.since if s.since is not None else float("inf"), s.sid)

        found = [(i, w, s) for i, w in enumerate(self.windows) for s in w.sessions]
        return min(found, key=key)[2] if found else None


@dataclass
class Snapshot:
    connected: bool
    outputs: list[str]
    focused_ws: int | None
    workspaces: list[Workspace]      # the slots each output shows, output order then id
    focused: dict[str, Window | None]
    sessions: list[Session]          # roster order
    desired_tags: set[str]
    current_tags: set[str]

    @property
    def counts(self) -> dict[str, int]:
        c = {"waiting": 0, "busy": 0, "idle": 0}
        for s in self.sessions:
            c[s.state if s.state in c else "idle"] += 1
        return c


class Inputs(NamedTuple):
    connected: bool
    clients: list[dict]
    monitors: list[dict]
    workspaces: list[dict]
    rules: list[dict]
    sessions: dict[int, Session]
    hosted: dict[str, list[int]]          # address → session pids under it
    views: dict[str, tuple[str, str]]     # address → (kind, label) when no session
    foreground: dict[str, int]            # address → foreground pid


# ── reading ─────────────────────────────────────────────────────────────────

def _ws_id(c: dict) -> int | None:
    v = (c.get("workspace") or {}).get("id")
    return v if isinstance(v, int) else None


def _number(v: object) -> float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def read_sessions(proc: Proc, home: ClaudeHome, fsroot: str = "/") -> dict[int, Session]:
    out = {}
    for pid, d in home.sessions().items():
        status = d.get("status")
        if status is None and str(d.get("entrypoint", "")) in GHOST_ENTRYPOINTS:
            continue        # plugin SDK sessions register with status null: not agents
        # Liveness: procStart must equal the kernel's start time. Fail closed —
        # files are left behind by SIGKILL/OOM and pids get reused.
        want = str(d.get("procStart") or "").strip()
        if not want or proc.start_time(pid) != want:
            continue
        sid = d.get("sessionId")
        if not isinstance(sid, str) or not SESSION_ID.match(sid):
            continue        # a UUID: it becomes a path and a glob
        cwd = d.get("cwd") if isinstance(d.get("cwd"), str) else ""
        state = status if status in STATES else "unknown"
        dig = home.transcript(sid, cwd, stamp=(status, d.get("statusUpdatedAt")))
        started = _number(d.get("startedAt"))
        started = started / 1000 if started is not None else None
        # Background work dies with the process: a launch from an earlier run of
        # a resumed session is not pending, nor is an agent whose meta finished.
        pending = tuple(p for p in dig.pending if started is None or p.at is None or p.at >= started)
        subs = home.subagents(sid, cwd, started) if pending or state in ("busy", "waiting", "shell") else []
        done = {s.tool_use for s in subs if not s.live and s.tool_use}
        pending = tuple(p for p in pending if p.id not in done)
        waiting_on = None
        if state in ("idle", "shell") and pending:
            state = "busy"
            waiting_on = next(k for k in WAITING_ON if any(p.kind == k for p in pending))
        source, lines = doing(dig, state)
        horizon = home.clock() - SUBAGENT_KEEP_S
        subs = [s for s in subs if s.live or s.mtime >= horizon][:SUBAGENT_MAX]
        upd = d.get("statusUpdatedAt")
        name = d.get("name")
        out[pid] = Session(
            pid=pid, sid=sid, kind=str(d.get("kind") or "unknown"), cwd=cwd,
            project=printable(project_of(cwd, fsroot)), title=dig.title,
            name=printable(name) if isinstance(name, str) and name.strip()
            and d.get("nameSource") != "derived" else None,
            state=state,
            waiting_for=printable(d["waitingFor"]) if state == "waiting"
            and isinstance(d.get("waitingFor"), str) else None,
            since=upd / 1000 if _number(upd) is not None else None,
            source=source, lines=lines, subagents=subs,
            doing=doing_line(dig, pending), asked=dig.asked, waiting_on=waiting_on, did=dig.did,
            job=d["jobId"] if isinstance(d.get("jobId"), str) and JOB_ID.match(d["jobId"]) else "",
        )
    home.forget({s.sid for s in out.values()})
    return out


def _basename(path: str | None) -> str:
    return os.path.basename(path.rstrip("/")) if path else ""


def window_title(c: dict) -> str:
    """The client title as one printable line, spinner frames gone.

    Sliced to 512 first: a page can set a 16k-character title, and the
    browser-suffix regexes are not linear on that.
    """
    return printable(SPINNER.sub("", str(c.get("title") or "")[:512]))


def describe(c: dict, proc: Proc) -> tuple[str, str]:
    """(kind, label) of a window that hosts no session."""
    cls = str(c.get("class") or "").lower()
    title = window_title(c)
    pid = c.get("pid") if isinstance(c.get("pid"), int) else 0
    if cls in BROWSERS:
        return "browser", BROWSERS[cls].sub("", title) or "browser"
    if cls in TERMINALS:
        shell = proc.shell_under(pid) if pid > 0 else None
        if shell is None:
            return "term", "shell"
        fg = proc.foreground(shell)
        if fg:
            comm = proc.comm(fg)
            here = proc.cwd(fg) or proc.cwd(shell)
            return ("nvim" if comm in EDITORS else "term"), _basename(here) or comm
        return "term", _basename(proc.cwd(shell)) or "shell"
    if cls in CODE:
        return "code", title.removesuffix(CODE[cls]) or cls
    if cls in FILES:
        return "files", title or cls
    return "window", title or cls or "window"


def attached(argv: list[str], loose: dict[int, Session]) -> int | None:
    """The session a `claude attach <job>` argv shows, among the sessions no
    window runs; None for any other argv, or when the job names none or two."""
    if len(argv) < 3 or os.path.basename(argv[0]) != "claude" or argv[1] != "attach":
        return None
    job = argv[2]
    if not JOB_ID.match(job):
        return None
    hits = [p for p, s in loose.items() if job == s.job or s.sid.startswith(job)]
    return hits[0] if len(hits) == 1 else None


def gather(hypr: Hypr, proc: Proc, home: ClaudeHome, fsroot: str = "/") -> Inputs:
    clients, monitors, workspaces = (hypr.query(q) for q in ("clients", "monitors", "workspaces"))
    connected = all(isinstance(x, list) for x in (clients, monitors, workspaces))
    if not connected:
        clients, monitors, workspaces = [], [], []
    rules = hypr.query("workspacerules") if connected else None
    clients = [c for c in clients if isinstance(c, dict) and isinstance(c.get("address"), str)]
    sessions = read_sessions(proc, home, fsroot)

    # One process behind several windows (kitty's new_os_window): /proc cannot
    # tell which window a session lives in, so none of them claims it — no
    # ring, no tag on the wrong window. Fail closed.
    pids = [c.get("pid") for c in clients]
    shared = {p for p in pids if isinstance(p, int) and pids.count(p) > 1}
    trees = {c["address"]: proc.descendants(c["pid"]) for c in clients
             if sessions and isinstance(c.get("pid"), int) and c["pid"] > 0 and c["pid"] not in shared}
    shows = {p: p for p in sessions}             # process → the session it shows
    under = {p for t in trees.values() for p in t}
    loose = {p: s for p, s in sessions.items() if p not in under}
    if loose:                                    # argv is read only while a session has no window
        for p in under - shows.keys():
            if (s := attached(proc.cmdline(p), loose)) is not None:
                shows[p] = s
    hosted, views, fg = {}, {}, {}
    for c in clients:
        addr, pid = c["address"], c.get("pid")
        here = list(dict.fromkeys(shows[p] for p in trees.get(addr, ()) if p in shows))
        if here:
            hosted[addr] = here
            shell = proc.shell_under(pid)
            front = shows.get(proc.foreground(shell)) if shell else None
            if front in here:
                fg[addr] = front
            continue
        ws = _ws_id(c)
        if ws and ws > 0 and c.get("mapped", True) and not c.get("hidden"):
            views[addr] = describe(c, proc)
    return Inputs(connected, clients, [m for m in monitors if isinstance(m, dict)],
                  [w for w in workspaces if isinstance(w, dict)],
                  [r for r in (rules if isinstance(rules, list) else []) if isinstance(r, dict)],
                  sessions, hosted, views, fg)


# ── building ────────────────────────────────────────────────────────────────

def _roster_key(s: Session):
    since = s.since if s.since is not None else float("inf")
    if s.state == "waiting":
        return (0, since, s.sid)                  # oldest wait first
    newest = -s.since if s.since is not None else float("inf")
    return (1 if s.state == "busy" else 2, newest, s.sid)


def build(i: Inputs) -> Snapshot:
    sessions = {pid: Session(**vars(s)) for pid, s in i.sessions.items()}   # build never mutates Inputs
    monitors = sorted((m for m in i.monitors if isinstance(m.get("name"), str)),
                      key=lambda m: m.get("id", 0))
    outputs = [m["name"] for m in monitors]
    active = {m["name"]: (m.get("activeWorkspace") or {}).get("id") for m in monitors}
    focused_ws = next((active[m["name"]] for m in monitors if m.get("focused")), None)

    def output_of(selector: str) -> str:
        # Hyprland's `desc:<prefix>` names a monitor by the head of its
        # description; one that matches no plugged monitor stays a selector.
        want = selector.removeprefix("desc:").strip()
        if selector.startswith("desc:") and want:
            return next((m["name"] for m in monitors
                         if str(m.get("description") or "").startswith(want)), selector)
        return selector

    rules: dict[int, str] = {}
    for r in i.rules:
        ws = str(r.get("workspaceString", "")).strip()
        if ws.isdigit() and isinstance(r.get("monitor"), str) and r["monitor"]:
            rules[int(ws)] = output_of(r["monitor"])
    live = {w["id"]: w.get("monitor") for w in i.workspaces if isinstance(w.get("id"), int)}

    def owner(ws: int) -> str:
        # A rule naming a plugged monitor is authoritative. A rule naming an
        # unplugged one is not a claim: the workspace shows where it lives, or
        # nowhere. With no rule at all, an empty slot belongs to the first
        # output, so one monitor without rules still shows all eleven.
        r = rules.get(ws)
        if r in outputs:
            return r
        if live.get(ws) in outputs:
            return live[ws]
        return outputs[0] if r is None and outputs else ""

    by_ws: dict[int, list[Window]] = {}
    for c in i.clients:
        addr, ws = c["address"], _ws_id(c)
        here = [sessions[p] for p in i.hosted.get(addr, [])]
        for s in here:
            if s.window is None:
                s.window, s.workspace = addr, ws if ws and ws > 0 else None
        visible = ws is not None and ws > 0 and c.get("mapped", True) and not c.get("hidden")
        if not visible:
            continue
        if here:
            lead = sessions.get(i.foreground.get(addr)) or max(here, key=lambda s: s.since or 0)
            kind, label = "claude", lead.project
        else:
            lead, (kind, label) = None, i.views.get(addr, ("window", "window"))
        title = window_title(c)
        focus = c.get("focusHistoryID") if isinstance(c.get("focusHistoryID"), int) else 1 << 30
        by_ws.setdefault(ws, []).append(Window(addr, ws, focus, kind, label, title, here, lead))
    for wins in by_ws.values():
        wins.sort(key=lambda w: w.focus)

    slots = []
    for out in outputs:
        for ws in range(1, MAX_WS + 1):
            # The first ALWAYS_SHOWN slots always show (an empty one is a dim
            # numeral); the rest only while in use, so empty numerals do not
            # eat the room the labels need.
            here = Workspace(ws, out, active.get(out) == ws, by_ws.get(ws, []))
            if owner(ws) == out and (ws <= ALWAYS_SHOWN or here.occupied or here.active):
                slots.append(here)

    focused = {out: (by_ws.get(active.get(out)) or [None])[0] for out in outputs}
    desired = {s.window for s in sessions.values() if s.state == "waiting" and s.window}
    for s in sessions.values():
        s.tagged = s.window in desired
    current = {c["address"] for c in i.clients
               if isinstance(c.get("tags"), list) and TAG in c["tags"]}
    return Snapshot(i.connected, outputs, focused_ws, slots, focused,
                    sorted(sessions.values(), key=_roster_key), desired, current)


def collect(hypr: Hypr, proc: Proc, home: ClaudeHome, fsroot: str = "/") -> Snapshot:
    return build(gather(hypr, proc, home, fsroot))
