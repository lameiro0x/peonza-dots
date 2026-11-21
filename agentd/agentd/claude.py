"""Claude Code's on-disk state: session files and transcript tails.

Measured on 2.1.319 (vault Meta/claude-code-state-surface.md); undocumented, so
every field is optional. Two opposite write disciplines live side by side:

  * sessions/<pid>.json is rewritten IN PLACE (O_TRUNC, no rename), so a read
    can land on half a file. That is a torn read, never a dead session: keep
    the last good parse and try again on the next poll.
  * projects/<slug>/<sessionId>.jsonl is append-only, and one line can pass
    1 MB (a screenshot); a turn can pass several. The first read takes the
    last TAIL_BYTES, starting mid-line; after that only the appended bytes are
    read and folded into a running digest, so a turn's Ahora is never lost to
    a sliding window.

Privacy: `last-prompt`, `queue-operation`, `user` records and history.jsonl
carry the user's own words. Only three kinds of `user` record pass, each
reduced at parse time to the few values agentd needs, so no other prose ever
leaves `parse_tail`:

  * a prompt the user typed (`origin.kind == "human"`) → its first sentence,
    clipped to ASK_MAX: the `asked` line the user asked to see;
  * a task notification → its tool-use id, task id and status (never the
    summary or the result). The same reduction applies to the notifications
    queued as an `attachment` (queued_command, commandMode task-notification);
  * a tool result acknowledging a background launch → the two ids.

`last-prompt`, `queue-operation` and history.jsonl are never read. Every line
that reaches a consumer goes through `clean`, which redacts credentials first.
Files are opened only if regular (`open_regular`): a FIFO planted under
~/.claude must not freeze the daemon.
"""

from __future__ import annotations

import json
import os
import re
import stat
import textwrap
import time
from pathlib import Path
from datetime import datetime
from typing import Callable, Iterable, NamedTuple

from .strings import clip, printable, width

TAIL_BYTES = 4 * 1024 * 1024      # first read (and restart): reaches back into a long turn
CATCHUP_BYTES = 32 * 1024 * 1024  # more appended than this between reads: restart from a tail
REREAD_S = 2.0
LINE_MAX = 90
ASK_MAX = 60            # the roster's `asked`, `doing` and subagent descriptions
SUBAGENT_KEEP_S = 600   # a finished subagent stays listed this long
SUBAGENT_MAX = 8
PENDING_MAX = 32        # launches whose notification never came: the oldest go
_KEEP = {"ai-title", "assistant", "system"}
_NEEDLES = (b'"ai-title"', b'"assistant"', b'"system"', b'"human"', b'task-notification',
            b'"backgroundTaskId"', b'"async_launched"', b'"taskId"')
# What a background launch waits on, by tool. Agent sends run_in_background as
# the string "true" (measured 2.1.325); Monitor always runs in the background.
_BACKGROUND = {"Bash": "shell", "Agent": "agent", "Task": "agent", "Monitor": "monitor"}
_TAG = {k: re.compile(rf"<{k}>([^<]{{1,128}})</{k}>") for k in ("tool-use-id", "task-id", "status")}
_FENCE = re.compile(r"^\s*(```|~~~)")
_SENTENCE = re.compile(r"(?<=[.!?…])\s")
_META = re.compile(r"^agent-([A-Za-z0-9_-]{1,64})\.meta\.json$")
_AGENT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")     # fullmatch: the id _META captures, joined into a path
SESSION_ID = re.compile(r"^[0-9a-f-]{36}$")
# Credentials (redact): every pattern is bounded or linear, the input is ≤ CLEAN_MAX.
_TOKEN = re.compile(r"\b(?:sk-|gh[pousr]_|github_pat_|glpat-|xox[abposr]-|AKIA|eyJ)[A-Za-z0-9_\-./+=]{6,}")
_USERINFO = re.compile(r"(?<=://)[^/\s@]{1,256}@")
_ASSIGN = re.compile(r"\b([A-Z][A-Z0-9_]{0,63}(?:KEY|TOKEN|SECRET|PASSWORD|PASS|PWD))\s*=\s*\S+")
_AFTER = re.compile(r"(?i)\b(contraseña|password|passwd|clave|token|secret|secreto)"
                    r"(\s*[:=]\s*|\s+(?:es|era|sea|is|was|de|del|=)\s+|\s+)(\S+)")
_LONG = re.compile(r"[A-Za-z0-9_\-+=]{16,}")
_SESSION = re.compile(r"^(\d+)\.json$")
# Bounded on purpose: `[^\]]*` went quadratic on a run of '[' (80k → 20 s).
_LINK = re.compile(r"\[([^\[\]]{0,200})\]\([^()\s]{0,500}\)")
CLEAN_MAX = 4096
_BULLET = re.compile(r"^(?:[-*•+]|\d+[.)])\s+(.*)$")
_RECAP = " (disable recaps in /config)"


class Pending(NamedTuple):
    """Background work the session launched and has not heard back from."""
    id: str                  # the launching tool_use id
    kind: str                # shell | agent | monitor
    description: str
    at: float | None         # launch time, epoch seconds


class Digest(NamedTuple):
    """What a transcript tail says, before the session state picks from it."""
    title: str | None
    ahora: tuple[str, ...]
    tool: tuple[str, ...]
    away: tuple[str, ...]
    hecho: tuple[str, ...]
    asked: str = ""
    pending: tuple[Pending, ...] = ()
    did: str = ""            # first line of the latest Hecho, whatever turn it was in


Digest.EMPTY = Digest(None, (), (), (), ())


class Subagent(NamedTuple):
    id: str
    type: str
    description: str
    live: bool
    tool_use: str            # the parent's tool_use id that spawned it
    mtime: float


# ── pure parsing ────────────────────────────────────────────────────────────

def parse_tail(data: bytes, partial: bool) -> list[dict]:
    """Records of the kinds agentd reads, in file order.

    `partial`: the bytes start mid-file, so the first line is a fragment.
    The last line may be unfinished (being appended); it fails to parse and
    is skipped like any other bad line.
    """
    chunks = data.split(b"\n")
    if partial:
        chunks = chunks[1:]
    out = []
    for raw in chunks:
        # Cheap prefilter: most of a tail is api-request blobs and tool output.
        if not any(n in raw for n in _NEEDLES):
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        if rec.get("type") in _KEEP:
            out.append(rec)
        elif rec.get("type") == "user" and _main(rec) and (slim := _user(rec)):
            out.append(slim)
        elif rec.get("type") == "attachment" and _main(rec) and isinstance(rec.get("attachment"), dict):
            # 2.1.316+: about half the notifications arrive queued, as an attachment.
            a = rec["attachment"]
            if (a.get("type") == "queued_command" and a.get("commandMode") == "task-notification"
                    and isinstance(a.get("prompt"), str) and (note := _note(a["prompt"]))):
                out.append(note)
    return out


def _note(text: str) -> dict | None:
    """A task notification's ids and status; without a status it is an event
    (a Monitor line), not the end, and None."""
    tags = {k: m.group(1).strip() if (m := rx.search(text[:CLEAN_MAX])) else "" for k, rx in _TAG.items()}
    return {"type": "user", "note": tags} if tags["status"] else None


def _user(rec: dict) -> dict | None:
    """A user record reduced to what agentd may keep (module docstring), or None."""
    origin = rec["origin"] if isinstance(rec.get("origin"), dict) else {}
    content = (rec.get("message") or {}).get("content")
    if origin.get("kind") == "human":
        if isinstance(content, list):
            content = "\n".join(b["text"] for b in content if isinstance(b, dict)
                                and b.get("type") == "text" and isinstance(b.get("text"), str))
        line = ask_line(content) if isinstance(content, str) else ""
        return {"type": "user", "asked": line} if line else None
    if origin.get("kind") == "task-notification" and isinstance(content, str):
        return _note(content)
    result = rec.get("toolUseResult")
    if isinstance(result, dict) and isinstance(content, list):
        task = result.get("backgroundTaskId") or result.get("taskId") or (
            result.get("agentId") if result.get("isAsync") else None)
        ids = [b.get("tool_use_id") for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
        if isinstance(task, str) and task and len(ids) == 1 and isinstance(ids[0], str):
            return {"type": "user", "ack": {"tool-use-id": ids[0], "task-id": task}}
    return None


def _prose(s: str) -> bool:
    """Mostly letters: a sentence, not a log line, a path or a hash."""
    seen = [c for c in s if not c.isspace()]
    return bool(seen) and sum(c.isalpha() for c in seen) >= 0.6 * len(seen)


def ask_line(body: str) -> str:
    """The first sentence of a prompt as one line of at most ASK_MAX cells.

    Skips what is not the user talking: code (fenced or indented), pasted
    blocks, quotes, tags (system reminders, command wrappers) and lines that
    are mostly symbols."""
    fenced = False
    for row in body[:CLEAN_MAX].split("\n"):
        if _FENCE.match(row):
            fenced = not fenced
            continue
        s = row.strip()
        if (fenced or not s or row.startswith(("    ", "\t"))
                or s.startswith(("<", ">", "[Pasted", "$ ", "#!")) or not _prose(s)):
            continue
        return clean(_SENTENCE.split(s, 1)[0], ASK_MAX)
    return ""


def open_regular(path: str | os.PathLike):
    """A binary reader for a regular file, never a FIFO or a device (a blocking
    open would freeze the daemon) nor a symlink. OSError otherwise."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(f"{path}: not a regular file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _epoch(ts: object) -> float | None:
    try:
        return datetime.fromisoformat(ts).timestamp() if isinstance(ts, str) else None
    except ValueError:
        return None


def _opaque(m: re.Match) -> str:
    w = m.group(0)
    return "…" if any(c.isdigit() for c in w) and any(c.isalpha() for c in w) else w


def _after(m: re.Match) -> str:
    """The value after «contraseña», «token»…: hidden when it follows ':' or '=',
    or looks like one (a digit or a symbol in it); «la palabra clave del índice»
    stays prose."""
    key, sep, value = m.groups()
    secret = sep.strip() in (":", "=") or any(not c.isalpha() for c in value.rstrip(".,;)"))
    return f"{key}{sep}…" if secret else m.group(0)


def redact(s: str) -> str:
    """Credentials out of a line before it reaches the screen: known token
    prefixes, long letter-and-digit words, a URL's user:password, NAME_KEY=
    values and the word after «contraseña», «password», «token»…"""
    s = _TOKEN.sub("…", s)
    s = _USERINFO.sub("…@", s)
    s = _ASSIGN.sub(r"\1=…", s)
    s = _AFTER.sub(_after, s)
    return _LONG.sub(_opaque, s)


def clean(s: str, width: int = LINE_MAX) -> str:
    """Markdown → one raw line for consumers that render plain text, credentials
    redacted before the clip so no part of one survives."""
    s = _LINK.sub(r"\1", s[:CLEAN_MAX])
    for mark in ("**", "__", "~~", "`", "*"):
        s = s.replace(mark, "")
    s = printable(redact(s.lstrip("#")).replace("<", "‹"))
    return clip(s, width)


def _section(body: str, head: str) -> tuple[str, ...]:
    """The bullets under the last `**Head:**` of a message, at most three."""
    m = None
    for m in re.finditer(r"\*\*" + head + r":\*\*", body):
        pass
    if m is None:
        return ()
    rows = body[m.end():].split("\n")
    out = [rows[0].strip()] if rows[0].strip() else []
    for row in rows[1:]:
        row = row.strip()
        if not row:
            if out:
                break
            continue
        b = _BULLET.match(row)
        if not b:
            break
        out.append(b.group(1))
    return tuple(x for x in (clean(o) for o in out) if x)[:3]


def _main(rec: dict) -> bool:
    return not rec.get("isSidechain")


def _blocks(rec: dict) -> list[dict]:
    content = (rec.get("message") or {}).get("content") if rec.get("type") == "assistant" else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _tool_line(b: dict) -> str:
    inp = b.get("input")
    desc = inp.get("description") if isinstance(inp, dict) else None
    return clean(desc if isinstance(desc, str) and desc.strip() else str(b.get("name") or ""))


def _launch(b: dict, at: float | None) -> Pending | None:
    """A tool_use that starts background work, as Pending; else None."""
    name, inp, tid = b.get("name"), b.get("input"), b.get("id")
    if not isinstance(inp, dict) or not isinstance(tid, str):
        return None
    if name == "Monitor" or inp.get("run_in_background") in (True, "true"):
        return Pending(tid, _BACKGROUND.get(name, "shell"), _tool_line(b), at)
    return None


class Fold:
    """A running digest of a transcript: feed it records in file order.

    Title, recap, asked and did: the latest anywhere. Ahora and tool: the latest
    of the open turn. Hecho: the latest of the last closed turn. A turn closes with
    `system/turn_duration` (not `end_turn`, which is followed by more
    assistant records 35 % of the time). Sidechain (subagent) records never
    count.

    Pending: background launches (run_in_background, Monitor) until the task
    notification that carries their status, or a TaskStop, matched by tool-use
    id or by the task id their launch acknowledged. They outlive the turn: the
    session goes on by itself when they report back.
    """
    __slots__ = ("title", "away", "ahora", "tool", "open_hecho", "hecho", "did", "asked", "pending", "tasks")

    def __init__(self) -> None:
        self.title: str | None = None
        self.away: tuple[str, ...] = ()
        self.ahora: tuple[str, ...] = ()
        self.tool: tuple[str, ...] = ()
        self.open_hecho: tuple[str, ...] = ()
        self.hecho: tuple[str, ...] = ()
        self.did = ""
        self.asked = ""
        self.pending: dict[str, Pending] = {}    # launch order
        self.tasks: dict[str, str] = {}          # task id → launching tool_use id

    def _settle(self, tool_use: str, task: str) -> None:
        tool_use = self.tasks.pop(task, None) or tool_use
        self.pending.pop(tool_use, None)
        for t in [t for t, u in self.tasks.items() if u == tool_use]:
            del self.tasks[t]

    def feed(self, records: list[dict]) -> Fold:
        for r in records:
            kind = r.get("type")
            if kind == "ai-title":
                t = r.get("aiTitle")
                if isinstance(t, str) and t.strip():
                    self.title = printable(t)
            elif kind == "system" and _main(r):
                sub = r.get("subtype")
                if sub == "turn_duration":
                    self.hecho, self.open_hecho = self.open_hecho, ()
                    self.ahora = self.tool = ()
                elif sub == "away_summary" and isinstance(r.get("content"), str):
                    body = r["content"].strip()
                    if body.endswith(_RECAP.strip()):
                        body = body[: -len(_RECAP.strip())]
                    wrapped = textwrap.wrap(clean(body, 10_000), LINE_MAX, max_lines=3, placeholder="…")
                    self.away = tuple(wrapped) or self.away
            elif kind == "assistant" and _main(r):
                for b in _blocks(r):
                    if b.get("type") == "text" and isinstance(b.get("text"), str):
                        self.ahora = _section(b["text"], "Ahora") or self.ahora
                        if (hecho := _section(b["text"], "Hecho")):
                            self.open_hecho, self.did = hecho, clip(hecho[0], ASK_MAX)
                    elif b.get("type") == "tool_use":
                        line = _tool_line(b)
                        if line:
                            self.tool = (line,)
                        inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                        if (p := _launch(b, _epoch(r.get("timestamp")))):
                            self.pending[p.id] = p
                            while len(self.pending) > PENDING_MAX:
                                self._settle(next(iter(self.pending)), "")
                        elif b.get("name") == "TaskStop" and isinstance(inp.get("task_id"), str):
                            self._settle("", inp["task_id"])
            elif kind == "user":                 # already reduced by parse_tail
                if r.get("asked"):
                    self.asked = r["asked"]
                elif r.get("note"):
                    self._settle(r["note"]["tool-use-id"], r["note"]["task-id"])
                elif r.get("ack") and r["ack"]["tool-use-id"] in self.pending:
                    self.tasks[r["ack"]["task-id"]] = r["ack"]["tool-use-id"]
        return self

    def snapshot(self) -> Digest:
        return Digest(self.title, self.ahora, self.tool, self.away, self.hecho,
                      self.asked, tuple(self.pending.values()), self.did)


def digest(records: list[dict]) -> Digest:
    """Title, Ahora/tool of the open turn, Hecho of the last closed turn, recap."""
    return Fold().feed(records).snapshot()


def doing(d: Digest, state: str) -> tuple[str, list[str]]:
    """(source, lines) — the chain of the roster contract."""
    chain = [("ahora", d.ahora), ("tool", d.tool), ("away", d.away)]
    if state not in ("busy", "waiting"):
        chain.insert(0, ("hecho", d.hecho))
    for source, rows in chain:
        if rows:
            return source, list(rows)
    return "none", []


def doing_line(d: Digest, pending: tuple[Pending, ...] = ()) -> str:
    """What the session is doing, one high-level line: the open turn's Ahora
    bullets (as many whole ones as fit), else its current tool, else the newest
    background work it waits on. Empty when nothing is known (an idle session
    does nothing)."""
    if d.ahora:
        line = d.ahora[0]
        for more in d.ahora[1:]:
            if width(f"{line} · {more}") > ASK_MAX:
                break
            line = f"{line} · {more}"
        return clip(line, ASK_MAX)
    if d.tool:
        return clip(d.tool[0], ASK_MAX)
    return clip(pending[-1].description, ASK_MAX) if pending else ""


_PROJECTS: dict[tuple[str, str], tuple[float, str]] = {}
PROJECT_TTL = 60.0


def project_of(cwd: str, root: str = "/", now: float | None = None) -> str:
    """Basename of the git root above cwd (≤ 8 levels up), else of cwd.

    Cached for PROJECT_TTL so a `git init` above a running session is seen
    within a minute. `root` prefixes every lookup so tests can hand a
    synthetic filesystem.
    """
    now = time.monotonic() if now is None else now
    hit = _PROJECTS.get((cwd, root))
    if hit and 0 <= now - hit[0] < PROJECT_TTL:
        return hit[1]
    name = ""
    if cwd:
        p = Path(cwd)
        name = p.name or str(p)
        for d in [p, *p.parents][:9]:
            if os.path.exists(os.path.join(root, str(d).lstrip("/"), ".git")):
                name = d.name or str(d)
                break
    if len(_PROJECTS) > 512:
        _PROJECTS.clear()
    _PROJECTS[(cwd, root)] = (now, name)
    return name


# ── the home directory ──────────────────────────────────────────────────────

class _Tail:
    __slots__ = ("path", "checked", "stamp", "seen", "offset", "midline", "fold", "digest")

    def __init__(self):
        self.stamp: object = None
        self.path: Path | None = None
        self.checked = float("-inf")
        self.seen: tuple[int, int] | None = None   # (inode, size) at the last read
        self.offset = 0          # bytes consumed: just past a newline, unless midline
        self.midline = False     # offset sits inside a line whose start was never read
        self.fold = Fold()
        self.digest = Digest.EMPTY


class ClaudeHome:
    def __init__(self, root: str | Path = Path.home() / ".claude", clock: Callable[[], float] = time.time):
        self.root = Path(root)
        self.clock = clock
        self._sessions: dict[str, tuple[tuple[int, int], dict]] = {}
        self._tails: dict[str, _Tail] = {}
        self._metas: dict[str, dict[str, tuple[tuple[int, int], Subagent]]] = {}

    def _session_files(self) -> list[os.DirEntry]:
        try:
            with os.scandir(self.root / "sessions") as it:
                return [e for e in it if _SESSION.match(e.name)]
        except OSError:
            return []

    def signature(self) -> tuple:
        """Cheap change detector for the 1 Hz poll: (name, mtime_ns, size)."""
        out = []
        for e in self._session_files():
            try:
                st = e.stat()
            except OSError:
                continue
            out.append((e.name, st.st_mtime_ns, st.st_size))
        return tuple(sorted(out))

    def sessions(self) -> dict[int, dict]:
        """pid → session dict for every readable session file.

        A torn read keeps the last good parse (and is retried next time, since
        its key is not stored); a file never read whole is simply absent.
        """
        seen = {}
        for e in self._session_files():
            try:
                st = e.stat()
            except OSError:
                continue
            key = (st.st_mtime_ns, st.st_size)
            old = self._sessions.get(e.name)
            if old and old[0] == key:
                seen[e.name] = old
                continue
            try:
                with open_regular(e.path) as fh:
                    data = json.loads(fh.read(1 << 20))
            except (OSError, ValueError):
                data = None
            if isinstance(data, dict):
                seen[e.name] = (key, data)
            elif old:
                seen[e.name] = ((-1, -1), old[1])
        self._sessions = seen
        return {int(_SESSION.match(n).group(1)): v[1] for n, v in seen.items()}

    def _locate(self, sid: str, cwd: str) -> Path | None:
        if not SESSION_ID.match(sid):      # it is globbed and joined into paths
            return None
        projects = self.root / "projects"
        guess = projects / re.sub(r"[^A-Za-z0-9]", "-", cwd) / f"{sid}.jsonl"
        if guess.is_file():
            return guess
        # The slug is lossy and long ones are truncated: look it up by id.
        return next(projects.glob(f"*/{sid}.jsonl"), None)

    def transcript(self, sid: str, cwd: str, stamp: object = None) -> Digest:
        """The digest of the session's transcript, checked only when the file
        changed and at most once per REREAD_S — unless `stamp` (the session's
        status and statusUpdatedAt) moved: a turn that just ended must show
        its own Hecho, not the previous one.

        The first read folds the last TAIL_BYTES; later reads fold only the
        complete lines appended since. A replaced or truncated file, or one
        that grew by more than CATCHUP_BYTES, starts over from a tail."""
        t = self._tails.setdefault(sid, _Tail())
        now = self.clock()
        if stamp == t.stamp and 0 <= now - t.checked < REREAD_S:
            return t.digest
        t.stamp = stamp
        t.checked = now
        if t.path is None or not t.path.is_file():
            t.path = self._locate(sid, cwd)
        if t.path is None:
            return t.digest
        try:
            with open_regular(t.path) as fh:
                st = os.fstat(fh.fileno())
                seen = (st.st_ino, st.st_size)
                if seen == t.seen:
                    return t.digest
                if (t.seen is None or st.st_ino != t.seen[0] or st.st_size < t.offset
                        or st.st_size - t.offset > CATCHUP_BYTES):
                    t.fold = Fold()
                    t.offset = max(0, st.st_size - TAIL_BYTES)
                    t.midline = t.offset > 0
                fh.seek(t.offset)
                data = fh.read(st.st_size - t.offset)
        except OSError:
            return t.digest
        t.seen = seen
        end = data.rfind(b"\n") + 1
        if end == 0:
            if t.midline:       # still inside the line whose start we never saw: skip it
                t.offset += len(data)
            return t.digest     # else an unfinished line: read it whole once it ends
        records = parse_tail(data[:end], partial=t.midline)
        t.offset += end
        t.midline = False
        if records:
            new = t.fold.feed(records).snapshot()
            # A restart from a tail can miss the ai-title and the last Hecho; neither
            # goes back to nothing once seen.
            t.digest = new._replace(title=new.title or t.digest.title, did=new.did or t.digest.did)
        return t.digest

    def subagents(self, sid: str, cwd: str, started: float | None = None) -> list[Subagent]:
        """Every subagent of the session, from `<sid>/subagents/agent-<id>.meta.json`:
        live first, then finished, newest first.

        Live = the meta has no `finished` (measured 2.1.325: Claude Code adds
        `finished: true` when the subagent ends) and was written after the
        session's process started (`started`, epoch seconds): an orphan of a
        crashed earlier run of the same session never finishes. A meta is
        re-read only when it changes; a torn one is skipped until it parses.
        """
        t = self._tails.get(sid)
        path = t.path if t and t.path else self._locate(sid, cwd)
        if path is None:
            return []
        old, seen = self._metas.get(sid, {}), {}
        try:
            with os.scandir(path.parent / sid / "subagents") as it:
                for e in it:
                    m = _META.match(e.name)
                    if not m:
                        continue
                    try:
                        st = e.stat()
                        key = (st.st_mtime_ns, st.st_size)
                        if e.name in old and old[e.name][0] == key:
                            seen[e.name] = old[e.name]
                            continue
                        with open_regular(e.path) as fh:
                            meta = json.loads(fh.read(1 << 16))
                    except (OSError, ValueError):
                        continue
                    if isinstance(meta, dict):
                        seen[e.name] = (key, _subagent(m.group(1), meta, st.st_mtime))
        except OSError:
            return []
        self._metas[sid] = seen
        subs = [s._replace(live=s.live and (started is None or s.mtime >= started))
                for _, s in seen.values()]
        return sorted(subs, key=lambda s: (not s.live, -s.mtime, s.id))

    def activity(self, sid: str, cwd: str, agents: Iterable[str] = ()) -> tuple[float | None, float | None]:
        """When the session last wrote: (its transcript, the newest transcript of
        the subagents named in `agents`), epoch seconds, None when unknown.

        A working turn appends to its transcript and a working subagent to its
        own `agent-<id>.jsonl`; the subagent's meta is written only when it
        starts and when it finishes, so it says nothing about now. Only lstat:
        nothing here is opened.
        """
        t = self._tails.get(sid)
        path = t.path if t and t.path else self._locate(sid, cwd)
        if path is None:
            return None, None

        def mtime(p: Path) -> float | None:
            try:
                st = os.lstat(p)
            except OSError:
                return None
            return st.st_mtime if stat.S_ISREG(st.st_mode) else None

        sub = path.parent / sid / "subagents"
        seen = [m for a in agents if _AGENT_ID.fullmatch(a) and (m := mtime(sub / f"agent-{a}.jsonl")) is not None]
        return mtime(path), max(seen, default=None)

    def forget(self, live: set[str]) -> None:
        """Drop the caches of sessions that ended."""
        for sid in set(self._tails) - live:
            del self._tails[sid]
        for sid in set(self._metas) - live:
            del self._metas[sid]


def _subagent(aid: str, meta: dict, mtime: float) -> Subagent:
    def text(key: str, n: int) -> str:
        return clean(meta[key], n) if isinstance(meta.get(key), str) else ""
    tool_use = meta.get("toolUseId")
    return Subagent(aid, text("agentType", 40) or "agente", text("description", ASK_MAX),
                    not meta.get("finished"), tool_use if isinstance(tool_use, str) else "", mtime)
