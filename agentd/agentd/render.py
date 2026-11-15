"""Snapshot → what consumers read. Pure.

Waybar payloads follow contracts/waybar.sample/README.md; the roster follows
contracts/roster.v1.schema.json. Markup carries greys only: the waiting state
is a class, and waybar/style.css draws it as the theme's signal ring. Every Spanish
word about a state comes from const.WORDS, the vocabulary the sidebar shares.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .const import AGENTS_FILE, ALWAYS_SHOWN, MAX_WS, WORDS
from .model import Session, Snapshot, Window, Workspace
from .strings import clip, clip_middle, isolate, pango, printable, width

# Built-in greys: Origen's, the default theme (contracts/themes/origen.json).
# Used whole when the deployed theme (~/.config/ryce/palette.json, a link to the
# current theme.json) is missing or unreadable, per key when one value is
# malformed: a bad theme file must never take the bar down at boot.
GREYS = {
    "fg0": "#ebdbb2", "fg1": "#bdae93", "fg2": "#ae9f90", "busy": "#bdae93",
    "ink_on_pill": "#1d2021", "dim_on_pill": "#665c54",
}
_HEX = re.compile(r"#[0-9a-fA-F]{6}")
ADDR = re.compile(r"0x[0-9a-f]+")

# Material Design glyphs (nf-md-*), by code point: never typed by hand. At 13 px
# in JetBrainsMono Nerd Font each advances 11 px — a uniform set.
ICONS = {
    "claude": "\U000F1719",    # md-robot-outline
    "term": "\U000F018D",      # md-console (md-memory means RAM in the sidebar)
    "nvim": "\U000F0577",
    "code": "\U000F0A1E",
    "files": "\U000F024B",
    "browser": "\U000F059F",   # md-web
    "window": "\U000F0379",    # md-monitor
}
CJK = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六",
       7: "七", 8: "八", 9: "九", 10: "十", 11: "十一"}

# Cells per occupied slot for label + " · " + title, by how many slots on the
# output are occupied — never by focus or content, so a slot's width changes
# only when a workspace gains or loses its last window. Measured on the 1920 px
# stage (Waybar 0.16, 13 px JetBrains Mono): 7.7 px a cell, 24 px of pill per
# slot plus 4.4 cells of numeral and icon, ~37 px per empty numeral, and a
# centre that must stay under ~1090 px or GTK ellipsizes the 42-cell window
# line on the left. budget(n) = ((1078 − 37·empties) / n − 24) / 7.7 − 4.4.
SLOT_BY_LOAD = {0: 44, 1: 44, 2: 44, 3: 35, 4: 26, 5: 20, 6: 15, 7: 12, 8: 10, 9: 8, 10: 6}
SLOT_MIN = 5
# A Claude slot's project name gets at most this much, so the title keeps room.
LABEL_BY_LOAD = {0: 16, 1: 16, 2: 16, 3: 16, 4: 16, 5: 12}
LABEL_MIN = 9
TITLE_MIN = 6           # a shorter title is noise: drop it
# The left island holds about 42 cells at 1920 px (measured by the bar slice);
# GTK must never have to ellipsize it.
WINDOW_WIDTH = 42
PROJECT_IN_WINDOW = 20
NAMES = {"claude", "term", "nvim"}     # labels that are directory basenames
SEP = " › "


def load_palette(path: str | Path) -> dict[str, str]:
    try:
        colors = json.loads(Path(path).read_text(encoding="utf-8")).get("colors")
    except (OSError, ValueError, AttributeError):
        return dict(GREYS)
    if not isinstance(colors, dict):
        return dict(GREYS)
    return {k: (colors[k] if isinstance(colors.get(k), str) and _HEX.fullmatch(colors[k]) else v)
            for k, v in GREYS.items()}


# ── text pieces ─────────────────────────────────────────────────────────────

def _headline(s: Session) -> str | None:
    return s.title or s.name


def _state_line(s: Session) -> str | None:
    if s.state == "waiting":
        return WORDS["waiting_for"].get(s.waiting_for or "", WORDS["waiting_fallback"])
    if s.state == "busy":
        n = sum(a.live for a in s.subagents)
        return WORDS["state"]["busy"] + (f" · {n} subagente{'s' if n != 1 else ''}" if n else "")
    if s.state == "shell":
        return WORDS["state"]["shell"]
    return None


def _claude_block(w: Window) -> list[str]:
    s = w.lead
    rows = [s.project + (f" — {_headline(s)}" if _headline(s) else "")]
    if s.source == "hecho" and s.lines:
        rows.append(f"hecho: {s.lines[0]}")
    else:
        rows += [f"• {x}" for x in s.lines]
    if (st := _state_line(s)):
        rows.append(st)
    for o in w.sessions:
        if o is not s:
            rows.append(f"+ {o.project} — {WORDS['state'].get(o.state, WORDS['state']['unknown'])}")
    return rows


def _tooltip(ws: Workspace) -> str:
    rows = []
    for w in ws.windows:
        if w.lead:
            rows += _claude_block(w)
        elif w.kind in ("browser", "code", "files", "window") and w.title:
            rows.append(w.title)
        else:
            rows.append(w.label)
    return pango("\n".join(rows))


def _fit(kind: str, label: str, n: int) -> str:
    """Directory names keep both ends; page and window titles are prose."""
    return clip_middle(label, n) if kind in NAMES else clip(label, n)


def idle_slot(n: int) -> dict:
    """What a slot shows with nothing known about it (agentd stopped)."""
    if n <= ALWAYS_SHOWN:
        return {"text": CJK.get(n, str(n)), "tooltip": "", "class": ["empty"]}
    return {"text": "", "tooltip": "", "class": ["off"]}


def _slot(ws: Workspace, load: int, pal: dict[str, str]) -> dict:
    if not ws.occupied:
        return {"text": CJK.get(ws.id, str(ws.id)), "tooltip": "",
                "class": ["empty"] + (["active"] if ws.active else [])}
    state = ws.state
    if ws.active:
        key = icon = title_c = pal["dim_on_pill"]
        ink = pal["ink_on_pill"]
    else:
        # The key numeral is read (text floor 4.5:1, fg1); the icon is a mark (fg2).
        key, ink, title_c = pal["fg1"], pal["fg0"], pal["fg1"]
        # A working session warms its icon one step. It has to be in the markup:
        # CSS cannot win against a span that already names a colour.
        icon = pal["busy"] if state == "busy" else pal["fg2"]
    budget = SLOT_BY_LOAD.get(load, SLOT_MIN)
    title = _headline(ws.lead) if ws.lead else None
    label, room = _fit(ws.kind, ws.label, budget), 0
    if title:
        # The title takes whatever a capped label leaves, so a short project
        # name buys a longer title; when no title fits, the label keeps it all.
        short = _fit(ws.kind, ws.label, min(budget, LABEL_BY_LOAD.get(load, LABEL_MIN)))
        if budget - width(short) - 3 >= TITLE_MIN:
            label, room = short, budget - width(short) - 3
    # The key column: the workspace number, which is the key you press.
    text = (f'<span foreground="{key}">{ws.id}</span> '
            f'<span foreground="{icon}">{ICONS.get(ws.kind, ICONS["window"])}</span> '
            f'<span foreground="{ink}">{isolate(pango(label))}</span>')
    if room:
        text += f'<span foreground="{title_c}"> · {isolate(pango(clip(title, room)))}</span>'
    classes = ["occupied"] + (["active"] if ws.active else [])
    if state == "waiting":
        classes.append("waiting")      # drawn by waybar/style.css as the ring
    elif state == "busy":
        classes.append("working")
    return {"text": text, "tooltip": _tooltip(ws), "class": classes}


def _window_line(w: Window | None) -> dict:
    if w is None:
        return {"text": "", "tooltip": "", "class": ["empty"]}
    if w.lead:
        # «proyecto › lo que hace»; the title stands in when nothing is being
        # done, and lives in the slot and this tooltip anyway.
        s = w.lead
        project = clip_middle(s.project, PROJECT_IN_WINDOW)
        rest = s.lines[0] if s.lines else _headline(s)
        text = isolate(pango(project))
        if rest:
            room = WINDOW_WIDTH - width(project) - width(SEP)
            text += SEP + isolate(pango(clip(rest, room)))
        tip = [s.project + (f" — {_headline(s)}" if _headline(s) else "")] + [f"• {x}" for x in s.lines]
        return {"text": text, "tooltip": pango("\n".join(tip)), "class": ["window", "claude"]}
    title = w.title or w.label
    return {"text": isolate(pango(clip(title, WINDOW_WIDTH))), "tooltip": pango(title),
            "class": ["window"]}


# ── files ───────────────────────────────────────────────────────────────────

def _waiting_words(n: int) -> str:
    return WORDS["lock_one"] if n == 1 else WORDS["lock_many"] % n


def agents(snap: Snapshot) -> dict:
    c = snap.counts
    parts = []
    if c["waiting"]:
        parts.append(_waiting_words(c["waiting"]))
    if c["busy"]:
        parts.append(f"{c['busy']} {WORDS['state']['busy']}")
    if c["idle"]:
        parts.append(f"{c['idle']} {WORDS['state']['idle']}")
    if c["waiting"]:
        n, cls = c["waiting"], "waiting"
    elif c["busy"]:
        n, cls = c["busy"], "busy"
    else:
        n, cls = 0, "calm"
    return {"text": f"{ICONS['claude']} {n}", "tooltip": " · ".join(parts) or "sin agentes",
            "class": [cls]}


def lock_text(snap: Snapshot) -> str:
    n = snap.counts["waiting"]
    return _waiting_words(n) if n else ""


def waybar(snap: Snapshot, pal: dict[str, str]) -> dict[str, dict]:
    """File name (inside the waybar dir) → payload, for every output."""
    files = {}
    for out in snap.outputs:
        mine = {w.id: w for w in snap.workspaces if w.output == out}
        load = sum(w.occupied for w in mine.values())
        for n in range(1, MAX_WS + 1):
            files[f"{out}-{n}.json"] = (_slot(mine[n], load, pal) if n in mine
                                        else {"text": "", "tooltip": "", "class": ["off"]})
        files[f"{out}-window.json"] = _window_line(snap.focused.get(out))
    files[AGENTS_FILE] = agents(snap)
    return files


def _session(s: Session) -> dict:
    window = s.window if s.window and ADDR.fullmatch(s.window) else None
    return {
        "sessionId": s.sid, "pid": s.pid, "kind": s.kind, "project": s.project, "cwd": s.cwd,
        "title": s.title, "name": s.name, "state": s.state, "waitingFor": s.waiting_for,
        "since": s.since, "doing": s.doing, "asked": s.asked, "did": s.did, "waiting_on": s.waiting_on,
        "subagents": [{"id": a.id, "type": a.type, "description": a.description, "live": a.live}
                      for a in s.subagents],
        "workspace": s.workspace, "window": window,
        "tagged": bool(window and s.tagged and s.state == "waiting"),
    }


def roster(snap: Snapshot, generated_at: float) -> dict:
    return {
        "schema": "agentd.roster/1",
        "generatedAt": generated_at,
        "hypr": {"connected": snap.connected, "focusedWorkspace": snap.focused_ws,
                 "outputs": list(snap.outputs)},
        "counts": snap.counts,
        "sessions": [_session(s) for s in snap.sessions],
        "workspaces": [{"id": w.id, "output": w.output, "active": w.active, "occupied": w.occupied,
                        "label": printable(w.label), "icon": w.kind, "state": w.state,
                        "lead": w.lead.sid if w.lead else None}
                       for w in snap.workspaces],
    }
