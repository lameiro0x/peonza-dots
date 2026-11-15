"""Hyprland IPC: one-shot control-socket requests and the socket2 event stream.

Hyprland 0.57 is Lua-only: a `dispatch` request evaluates its argument as Lua,
so every dispatch agentd sends is an `hl.…` call built from constants and a
validated window address (see publish.tag_commands).
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


class Hypr(Protocol):
    def query(self, what: str) -> Any | None:
        """`j/<what>` decoded (clients, monitors, workspaces, workspacerules), or None."""

    def dispatch(self, lua: str) -> str | None:
        """Send `dispatch <lua>`; Hyprland's reply text, or None when unreachable."""

    def events(self) -> socket.socket | None:
        """A connected socket2 stream, or None when there is no compositor."""


def _connects(path: str) -> bool:
    """A compositor is alive when its control socket accepts a connection.

    The socket FILE proves nothing: a killed compositor leaves its directory
    and both sockets behind, and a user manager that outlives a compositor
    restart still exports the dead signature.
    """
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(path)
        return True
    except OSError:
        return False


class RealHypr:
    def __init__(self, env: Mapping[str, str] = os.environ,
                 probe: Callable[[str], bool] = _connects,
                 log: Callable[[str], None] | None = None):
        self.env = env
        self.runtime = Path(env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}") / "hypr"
        self.probe = probe
        self.log = log or (lambda msg: print(f"agentd: {msg}", file=sys.stderr, flush=True))
        self._sig: str | None = None
        self._reported: str | None = ""      # "" = nothing reported yet

    def signature(self, fresh: bool = False) -> str | None:
        """The live instance: the environment's one if it answers, else the
        most recently started one that answers.

        Kept until a request fails (`fresh` re-resolves), so a healthy session
        costs no extra connects.
        """
        if self._sig and not fresh:
            return self._sig
        try:
            dirs = [p for p in self.runtime.iterdir() if (p / ".socket.sock").exists()]
        except OSError:
            dirs = []

        def mtime(p: Path) -> float:
            try:
                return p.stat().st_mtime
            except OSError:
                return 0.0

        env = self.env.get("HYPRLAND_INSTANCE_SIGNATURE")
        cands = sorted(dirs, key=lambda p: (p.name != env, -mtime(p)))
        self._sig = next((p.name for p in cands if self.probe(str(p / ".socket.sock"))), None)
        if self._sig != self._reported:
            self.log(f"Hyprland connected ({self._sig})" if self._sig else "Hyprland not reachable")
            self._reported = self._sig
        return self._sig

    def _path(self, name: str, fresh: bool = False) -> str | None:
        sig = self.signature(fresh)
        return str(self.runtime / sig / name) if sig else None

    def _request(self, command: str) -> bytes | None:
        """One request, socket opened and closed each time.

        Holding the control socket open stalls the compositor: its accept loop
        is synchronous. A failure re-resolves the instance once and retries.
        """
        for fresh in (False, True):
            path = self._path(".socket.sock", fresh)
            if path is None:
                return None
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.settimeout(2.0)
                    s.connect(path)
                    s.sendall(command.encode())
                    chunks = []
                    while chunk := s.recv(65536):
                        chunks.append(chunk)
                return b"".join(chunks)
            except OSError:
                continue
        return None

    def query(self, what: str) -> Any | None:
        raw = self._request(f"j/{what}")
        try:
            # An XWayland title need not be UTF-8; one bad byte must not read
            # as a dead compositor.
            return json.loads(raw.decode("utf-8", "replace")) if raw else None
        except ValueError:
            return None

    def dispatch(self, lua: str) -> str | None:
        raw = self._request(f"dispatch {lua}")
        return None if raw is None else raw.decode("utf-8", "replace").strip()

    def events(self) -> socket.socket | None:
        path = self._path(".socket2.sock", fresh=True)
        if path is None:
            return None
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.settimeout(2.0)
            s.connect(path)
            s.setblocking(False)
            return s
        except OSError:
            s.close()
            return None


class FakeHypr:
    """Hyprland as a directory of `<what>.json` files; dispatches are recorded."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.dispatched: list[str] = []

    def query(self, what: str) -> Any | None:
        try:
            return json.loads((self.root / f"{what}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def dispatch(self, lua: str) -> str | None:
        self.dispatched.append(lua)
        return "ok"

    def events(self) -> socket.socket | None:
        return None
