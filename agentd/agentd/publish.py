"""Writing what changed, waking Waybar once, and keeping the window tag true.

Files are replaced atomically (tmp + os.replace) so a reader never sees half
of one. Nothing is rewritten unless its content changed: Claude Code's spinner
retitles windows about once a second forever, and that must cost zero writes
and zero Waybar refreshes.
"""

from __future__ import annotations

import json
import os
import re
import signal
from pathlib import Path
from typing import Callable

from . import render
from .const import AGENTS_FILE, DISPATCH_TAG, LOCK_FILE, ROSTER_FILE, SIGNAL, TAG, WAYBAR_DIR
from .hypr import Hypr
from .model import Snapshot
from .procfs import Proc

_SLOT_FILE = re.compile(r".+-(\d+)\.json")


def tag_commands(desired: set[str], current: set[str]) -> list[str]:
    """The Lua that makes `agentwait` sit on exactly the desired windows.

    The address is the only variable part interpolated into Lua, so it must be
    a bare lowercase hex address — nothing from a session or a transcript ever
    gets near this string.
    """
    ok = lambda a: bool(render.ADDR.fullmatch(a))
    return ([DISPATCH_TAG % (f"+{TAG}", a) for a in sorted(desired - current) if ok(a)]
            + [DISPATCH_TAG % (f"-{TAG}", a) for a in sorted(current - desired) if ok(a)])


def reconcile(hypr: Hypr, desired: set[str], current: set[str]) -> list[str]:
    """Send the tag commands; returns one line per command Hyprland rejected.

    No tag state lives here: `current` is read back from Hyprland every time,
    so a restart of either side heals itself on the next collect.
    """
    errors = []
    for lua in tag_commands(desired, current):
        reply = hypr.dispatch(lua)
        if reply is not None and reply != "ok":
            sign = "+" if f'"+{TAG}"' in lua else "-"
            addr = lua.rsplit("address:", 1)[1].split('"', 1)[0]
            errors.append(f"tag {sign}{TAG} {addr}: {reply[:120]}")
    return errors


def signal_waybar(proc: Proc, kill: Callable[[int, int], None] = os.kill, min_age: float = 1.0) -> None:
    """SIGRTMIN+9 to every running Waybar, so each bar re-reads its slots.

    Only to processes older than a second: a Waybar still starting has not
    installed its handler yet, and the default action of a real-time signal
    is to terminate.
    """
    rtmin = getattr(signal, "SIGRTMIN", None)     # Linux only; Waybar is too
    if rtmin is None:
        return
    for pid in proc.pids():
        if proc.comm(pid) != "waybar" or (proc.age(pid) or 0.0) < min_age:
            continue
        try:
            kill(pid, rtmin + SIGNAL)
        except OSError:
            pass    # gone meanwhile, or another user's bar: neither is ours to wake


def _write(path: Path, data: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)


def reset(outdir: str | Path, hypr: Hypr | None, wake: Callable[[], None] | None) -> list[str]:
    """Put everything agentd publishes back to "nothing known".

    Runs when agentd stops (and as ExecStopPost, so after a crash too): without
    it the bar keeps the last labels and the waiting ring forever, the lock
    screen keeps saying someone waits, and the waiting window keeps its border.
    Slots fall back to their bare numerals; nothing is created if agentd never
    ran. Returns the tag commands Hyprland rejected.
    """
    out = Path(outdir)
    bar = out / WAYBAR_DIR
    if bar.is_dir():
        for f in bar.glob("*.json"):
            if f.name == AGENTS_FILE:
                payload = {"text": "", "tooltip": "", "class": ["calm"]}
            elif f.name.endswith("-window.json"):
                payload = {"text": "", "tooltip": "", "class": ["empty"]}
            elif (m := _SLOT_FILE.fullmatch(f.name)):
                payload = render.idle_slot(int(m.group(1)))
            else:
                continue
            _write(f, json.dumps(payload, ensure_ascii=False))
    if out.is_dir():
        (out / ROSTER_FILE).unlink(missing_ok=True)
        _write(out / LOCK_FILE, "")
    if wake:
        wake()
    clients = hypr.query("clients") if hypr else None
    if not isinstance(clients, list):
        return []
    tagged = {c["address"] for c in clients if isinstance(c, dict) and isinstance(c.get("address"), str)
              and isinstance(c.get("tags"), list) and TAG in c["tags"]}
    return reconcile(hypr, set(), tagged)


class Publisher:
    def __init__(self, outdir: str | Path, signal: Callable[[], None] | None = None):
        self.outdir = Path(outdir)
        self.signal = signal
        self._last: dict[str, object] = {}

    def _put(self, rel: str, key: object, data: str, written: list[str]) -> None:
        if self._last.get(rel) == key:
            return
        _write(self.outdir / rel, data)
        self._last[rel] = key
        written.append(rel)

    def forget(self) -> None:
        """Make the next publish rewrite every file, changed or not."""
        self._last.clear()

    def publish(self, snap: Snapshot, pal: dict[str, str], now: float) -> list[str]:
        """Write every file whose content changed; returns their relative paths."""
        (self.outdir / WAYBAR_DIR).mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.outdir, 0o700)
        written: list[str] = []
        for name, payload in render.waybar(snap, pal).items():
            self._put(f"{WAYBAR_DIR}/{name}", payload, json.dumps(payload, ensure_ascii=False), written)
        if written and self.signal:
            self.signal()
        doc = render.roster(snap, now)
        key = {k: v for k, v in doc.items() if k != "generatedAt"}
        self._put(ROSTER_FILE, key, json.dumps(doc, ensure_ascii=False, indent=1), written)
        lock = render.lock_text(snap)
        self._put(LOCK_FILE, lock, lock, written)
        return written
