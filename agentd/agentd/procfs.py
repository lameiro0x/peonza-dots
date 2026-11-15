"""/proc, read through a root so tests can hand it a synthetic tree.

Every read tolerates the process vanishing between two calls: a gone process is
an empty answer, never an exception.
"""

from __future__ import annotations

import os
from pathlib import Path

SHELLS = {"fish", "bash", "zsh", "sh", "dash", "nu"}


class Proc:
    def __init__(self, root: str | Path = "/proc"):
        self.root = Path(root)

    def _read(self, *parts: str) -> str | None:
        try:
            return self.root.joinpath(*parts).read_text()
        except (OSError, UnicodeDecodeError):
            return None

    def children(self, pid: int) -> list[int]:
        raw = self._read(str(pid), "task", str(pid), "children") or ""
        return [int(x) for x in raw.split() if x.isdigit()]

    def comm(self, pid: int) -> str:
        return (self._read(str(pid), "comm") or "").strip()

    def cmdline(self, pid: int) -> list[str]:
        """argv; empty for a kernel thread, a zombie or a gone process."""
        raw = self._read(str(pid), "cmdline") or ""
        return raw.removesuffix("\0").split("\0") if raw else []

    def stat(self, pid: int) -> list[str] | None:
        """/proc/<pid>/stat with stat[n - 1] == field n of proc(5).

        Split after the LAST ')' so a comm holding spaces or parens is safe.
        """
        raw = self._read(str(pid), "stat")
        if raw is None:
            return None
        close = raw.rfind(")")
        if close == -1:
            return None
        return ["", ""] + raw[close + 2:].split()

    def start_time(self, pid: int) -> str | None:
        """Field 22, what Claude Code stores as procStart on Linux."""
        f = self.stat(pid)
        return f[21] if f and len(f) > 21 else None

    def pids(self) -> list[int]:
        try:
            return [int(e.name) for e in os.scandir(self.root) if e.name.isdigit()]
        except OSError:
            return []

    def age(self, pid: int) -> float | None:
        """Seconds since the process started (uptime − starttime / CLK_TCK)."""
        start, up = self.start_time(pid), (self._read("uptime") or "").split()
        try:
            return float(up[0]) - int(start) / os.sysconf("SC_CLK_TCK")
        except (TypeError, ValueError, IndexError):
            return None

    def cwd(self, pid: int) -> str | None:
        try:
            return os.readlink(self.root / str(pid) / "cwd")
        except OSError:
            return None

    def foreground(self, shell_pid: int) -> int | None:
        """The process group holding the shell's terminal, if it is not the shell.

        Field 5 is pgrp and field 8 tpgid; when they differ a job runs in the
        foreground and tpgid names it.
        """
        f = self.stat(shell_pid)
        if not f or len(f) < 8:
            return None
        try:
            pgrp, tpgid = int(f[4]), int(f[7])
        except ValueError:
            return None
        return None if tpgid <= 0 or tpgid == pgrp else tpgid

    def shell_under(self, pid: int) -> int | None:
        """The first shell below a terminal, breadth first.

        The first child of a kitty window is a `kitten` helper whose cwd is
        $HOME; taking it would label every terminal with the home directory.
        """
        for p in self.descendants(pid)[1:]:
            if self.comm(p) in SHELLS:
                return p
        return None

    def descendants(self, pid: int, depth: int = 6, limit: int = 200) -> list[int]:
        """pid and its descendants, breadth first, at most `depth` levels below
        it and `limit` pids in all (a browser can own hundreds)."""
        out, seen, level = [], {pid}, [pid]
        for d in range(depth + 1):
            nxt = []
            for p in level:
                if len(out) >= limit:
                    return out
                out.append(p)
                if d < depth:
                    for c in self.children(p):
                        if c not in seen:
                            seen.add(c)
                            nxt.append(c)
            level = nxt
        return out
