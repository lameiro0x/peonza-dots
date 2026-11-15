#!/usr/bin/env python3
"""Validate agentd roster files against contract v1 (stdlib only).

Usage: python3 contracts/check_roster.py FILE [FILE ...]
Exit 0 when every file validates; 1 and one line per problem otherwise.

This is the executable form of contracts/roster.v1.schema.json (revised in
place on 2026-11-14: `doing` became one line, `subagents` a list, `asked`
and `waiting_on` joined; agentd and every reader ship together). It is a small
hand-written checker on purpose: the PC has no jsonschema package, and the
contract has to be checkable on the Mac, the laptop and the new PC alike.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STATES = {"waiting", "busy", "shell", "idle", "unknown"}
WAITING_ON = {"shell", "agent", "monitor", None}
ICONS = {"claude", "term", "nvim", "code", "files", "browser", "window"}
WS_STATES = {"busy", "waiting", "idle", None}
ADDR = re.compile(r"^0x[0-9a-f]+$")
ORDER = {"waiting": 0, "busy": 1}
LINE = 60           # doing, asked, did, a subagent's description
SUBAGENTS = 8

SESSION_KEYS = {
    "sessionId", "pid", "kind", "project", "cwd", "title", "name", "state",
    "waitingFor", "since", "doing", "asked", "waiting_on", "subagents", "workspace",
    "window", "tagged",
}
SESSION_OPTIONAL = {"did"}    # additive (2026-11-14): a reader that ignores it loses nothing
SUBAGENT_KEYS = {"id", "type", "description", "live"}


def _line(v, n: int) -> str | None:
    """Why v is not one raw line of at most n characters, or None."""
    if not isinstance(v, str) or len(v) > n:
        return f"must be a string of <= {n} chars"
    if "<" in v or "**" in v or "`" in v or "\n" in v:
        return "carries markup or a newline; roster is one raw line"
    return None
WS_KEYS = {"id", "output", "active", "occupied", "label", "icon", "state"}
WS_OPTIONAL = {"lead"}     # additive: a v1 reader that ignores it loses nothing
TOP_KEYS = {"schema", "generatedAt", "hypr", "counts", "sessions", "workspaces"}


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def check(doc) -> list[str]:
    errs: list[str] = []
    if not isinstance(doc, dict):
        return ["top level is not an object"]
    if set(doc) != TOP_KEYS:
        errs.append(f"top-level keys {sorted(set(doc) ^ TOP_KEYS)} differ from contract")
    if doc.get("schema") != "agentd.roster/1":
        errs.append("schema must be 'agentd.roster/1'")
    if not _num(doc.get("generatedAt")):
        errs.append("generatedAt must be a number")

    h = doc.get("hypr")
    if not isinstance(h, dict) or set(h) != {"connected", "focusedWorkspace", "outputs"}:
        errs.append("hypr must have exactly connected, focusedWorkspace, outputs")
    else:
        if not isinstance(h["connected"], bool):
            errs.append("hypr.connected must be bool")
        if h["focusedWorkspace"] is not None and not _int(h["focusedWorkspace"]):
            errs.append("hypr.focusedWorkspace must be int or null")
        if not isinstance(h["outputs"], list) or not all(isinstance(o, str) for o in h["outputs"]):
            errs.append("hypr.outputs must be a list of strings")

    c = doc.get("counts")
    if not isinstance(c, dict) or set(c) != {"waiting", "busy", "idle"}:
        errs.append("counts must have exactly waiting, busy, idle")
    else:
        for k, v in c.items():
            if not _int(v) or v < 0:
                errs.append(f"counts.{k} must be a non-negative int")

    sessions = doc.get("sessions")
    if not isinstance(sessions, list):
        errs.append("sessions must be a list")
        sessions = []
    for i, s in enumerate(sessions):
        p = f"sessions[{i}]"
        if not isinstance(s, dict):
            errs.append(f"{p} is not an object")
            continue
        if set(s) - SESSION_OPTIONAL != SESSION_KEYS:
            errs.append(f"{p} keys differ: {sorted((set(s) - SESSION_OPTIONAL) ^ SESSION_KEYS)}")
            continue
        for k in ("sessionId", "kind", "project", "cwd"):
            if not isinstance(s[k], str):
                errs.append(f"{p}.{k} must be a string")
        for k in ("title", "name", "waitingFor"):
            if s[k] is not None and not isinstance(s[k], str):
                errs.append(f"{p}.{k} must be string or null")
        if not _int(s["pid"]):
            errs.append(f"{p}.pid must be int")
        if s["state"] not in STATES:
            errs.append(f"{p}.state {s['state']!r} not in {sorted(STATES)}")
        if s["since"] is not None and not _num(s["since"]):
            errs.append(f"{p}.since must be number or null")
        for k in ("doing", "asked", "did"):
            if k in s and (why := _line(s[k], LINE)):
                errs.append(f"{p}.{k} {why}")
        if s["waiting_on"] not in WAITING_ON:
            errs.append(f"{p}.waiting_on {s['waiting_on']!r} not in {sorted(WAITING_ON - {None})} or null")
        elif s["waiting_on"] is not None and s["state"] != "busy":
            errs.append(f"{p}.waiting_on is set but the session is not busy")
        subs = s["subagents"]
        if not isinstance(subs, list) or len(subs) > SUBAGENTS:
            errs.append(f"{p}.subagents must be a list of at most {SUBAGENTS}")
            subs = []
        for j, a in enumerate(subs):
            q = f"{p}.subagents[{j}]"
            if not isinstance(a, dict) or set(a) != SUBAGENT_KEYS:
                errs.append(f"{q} must have exactly {sorted(SUBAGENT_KEYS)}")
                continue
            for k, n in (("id", 64), ("type", 40), ("description", LINE)):
                if (why := _line(a[k], n)):
                    errs.append(f"{q}.{k} {why}")
            if not isinstance(a["live"], bool):
                errs.append(f"{q}.live must be bool")
        if s["workspace"] is not None and not _int(s["workspace"]):
            errs.append(f"{p}.workspace must be int or null")
        if s["window"] is not None and not (isinstance(s["window"], str) and ADDR.match(s["window"])):
            errs.append(f"{p}.window must match ^0x[0-9a-f]+$ or be null")
        if not isinstance(s["tagged"], bool):
            errs.append(f"{p}.tagged must be bool")
        if s["tagged"] and s["state"] != "waiting":
            errs.append(f"{p} is tagged but not waiting")

    # Ordering: waiting first, then busy, then the rest.
    ranks = [ORDER.get(str(s.get("state")), 2) for s in sessions if isinstance(s, dict)]
    if ranks != sorted(ranks):
        errs.append("sessions are not sorted waiting → busy → rest")

    if isinstance(c, dict) and set(c) == {"waiting", "busy", "idle"} and sessions:
        got = {
            "waiting": sum(1 for s in sessions if s.get("state") == "waiting"),
            "busy": sum(1 for s in sessions if s.get("state") == "busy"),
            "idle": sum(1 for s in sessions if s.get("state") in ("idle", "shell", "unknown")),
        }
        if got != c:
            errs.append(f"counts {c} disagree with sessions {got}")

    by_sid = {s["sessionId"]: s for s in sessions
              if isinstance(s, dict) and isinstance(s.get("sessionId"), str)}
    wss = doc.get("workspaces")
    if not isinstance(wss, list):
        errs.append("workspaces must be a list")
        wss = []
    for i, w in enumerate(wss):
        p = f"workspaces[{i}]"
        if not isinstance(w, dict) or set(w) - WS_OPTIONAL != WS_KEYS:
            errs.append(f"{p} keys differ from contract")
            continue
        if "lead" in w:
            lead = w["lead"]
            if lead is not None and lead not in by_sid:
                errs.append(f"{p}.lead must be the sessionId of a listed session, or null")
            elif (lead is None) != (w["state"] is None):
                errs.append(f"{p}.lead is null exactly when state is null")
            elif lead is not None and w["state"] in ORDER and by_sid[lead].get("state") != w["state"]:
                errs.append(f"{p}.lead is not the most urgent session: state {w['state']!r}, "
                            f"lead {by_sid[lead].get('state')!r}")
        if not _int(w["id"]) or w["id"] < 1:
            errs.append(f"{p}.id must be int >= 1")
        if not isinstance(w["output"], str) or not isinstance(w["label"], str):
            errs.append(f"{p}.output/label must be strings")
        if not isinstance(w["active"], bool) or not isinstance(w["occupied"], bool):
            errs.append(f"{p}.active/occupied must be bool")
        if w["icon"] not in ICONS:
            errs.append(f"{p}.icon {w['icon']!r} invalid")
        if w["state"] not in WS_STATES:
            errs.append(f"{p}.state {w['state']!r} invalid")
        elif (w["icon"] == "claude") != (w["state"] is not None):
            errs.append(f"{p}.icon is 'claude' exactly when a session lives here (state not null)")
    return errs


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python3 contracts/check_roster.py FILE [FILE ...]", file=sys.stderr)
        return 2
    bad = 0
    for name in argv:
        try:
            doc = json.loads(Path(name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"{name}: unreadable: {e}")
            bad += 1
            continue
        errs = check(doc)
        for e in errs:
            print(f"{name}: {e}")
        bad += bool(errs)
        if not errs:
            print(f"{name}: ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
