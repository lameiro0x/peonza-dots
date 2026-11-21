"""Keep the screen awake while a Claude Code session works.

hypridle locks at 10 min and turns the screens off at 15; a session that works
for an hour would hide behind the lock screen. While any session works, agentd
holds one logind idle inhibitor, which hypridle 0.1.8 honours (block mode only:
it reads BlockInhibited, never BlockWeakInhibited). When the work stops, the
inhibitor goes after a grace period and hypridle starts its timers again from
that moment (it recreates its idle notifications on release if one fired).

Only idle: a deliberate hibernate (Super+Shift+Esc, the power key, the lock
screen's button) still works while Claude works.

The inhibitor is a child `systemd-inhibit … bash` that reads a pipe from agentd,
one byte per cycle. Release is closing the pipe. If agentd dies, even by
SIGKILL, the kernel closes the pipe and the lock goes; if agentd hangs alive,
the lease runs out after LEASE_S without a byte. No state to clean up, here or
in `--reset`.

What counts as working (`working`), for a session shown in a terminal window:
  * its own turn runs (status busy) and it wrote in the last STALE_S;
  * or the turn ended but a background subagent of it is still writing.
Never: a session with no window (nothing to look at), one that waits for you (an
unanswered prompt would keep an unlocked desktop on all night), the `!` shell
mode, and background shells or Monitors, which cannot be told apart from a dev
server or a `tail -f` that runs for ever. A live but hung session stops counting
STALE_S after its last write; a timestamp from the future counts as no write.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Callable, Sequence

from .model import Session

STALE_S = 20 * 60      # a turn that wrote nothing for this long is hung, not working
FUTURE_S = 60.0        # clock skew tolerated before a timestamp reads as bogus
GRACE_S = 60.0         # keep the lock this long after the work stops: no flapping
                       # across a permission prompt, a minute to read the result
RETRY_S = 30.0         # a lock that could not be taken is tried again this often
LEASE_S = 120          # the lock lapses if agentd sends nothing for this long
LOCKER = "hyprlock"    # a locked screen keeps no lock: see App.cycle

# bash, not sh: `read -t` is not POSIX. Ends on EOF (agentd let go or died) and
# on a silent pipe (agentd hung).
LEASE = ("/usr/bin/bash", "-c", f"while read -r -t {LEASE_S} _; do :; done")
COMMAND = ("systemd-inhibit", "--what=idle", "--mode=block", "--no-ask-password",
           "--who=agentd", "--why=Claude está trabajando", *LEASE)


def working(s: Session, now: float) -> bool:
    """Whether this session is doing work that should keep the screen on."""
    if s.state != "busy" or not s.window:
        return False

    def fresh(t: float | None) -> bool:
        return t is not None and now - STALE_S < t <= now + FUTURE_S

    if s.waiting_on is None:                 # its own turn: Claude Code says busy
        return fresh(s.moved) or fresh(s.agents_moved)
    return fresh(s.agents_moved)             # only a background subagent that writes


class Awake:
    """One idle inhibitor, held while asked for and GRACE_S beyond.

    `update(want)` is called once per agentd cycle: it feeds the lease and
    checks the child. An inhibitor that dies after holding well is taken again
    at once (logind restarted); one that keeps dying (polkit said no) is
    reported once and tried again every RETRY_S, never in a tight loop.
    """

    def __init__(self, spawn: Callable[[], subprocess.Popen] | None = None,
                 log: Callable[[str], None] = print, clock: Callable[[], float] = time.monotonic,
                 grace_s: float = GRACE_S, retry_s: float = RETRY_S, command: Sequence[str] = COMMAND):
        self.spawn = spawn or self._spawn
        self.command = tuple(command)
        self.log, self.clock = log, clock
        self.grace_s, self.retry_s = grace_s, retry_s
        self.child: subprocess.Popen | None = None
        self.taken_at = float("-inf")
        self.confirmed = False           # the child outlived one cycle: logind said yes
        self.wanted_at = float("-inf")
        self.retry_at = float("-inf")
        self._said: set[str] = set()     # failures already logged, until the next release

    def _spawn(self) -> subprocess.Popen:
        # stdout: nothing to say. stderr: the journal, where a refused lock
        # says why ("Failed to inhibit: …"); it carries nothing of a session.
        p = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
        if p.stdin is not None:
            os.set_blocking(p.stdin.fileno(), False)     # a stuck reader never stalls agentd
        return p

    def _once(self, msg: str) -> None:
        if msg not in self._said:
            self._said.add(msg)
            self.log(msg)

    @property
    def held(self) -> bool:
        return self.child is not None

    def update(self, want: bool) -> None:
        now = self.clock()
        child = self.child
        if child is not None and child.poll() is not None:
            healthy = now - self.taken_at >= self.retry_s
            self._once(f"the idle inhibitor exited ({child.returncode}); trying again "
                       + ("now" if healthy else f"every {self.retry_s:.0f} s"))
            self._drop()
            self.retry_at = now if healthy else now + self.retry_s
        if want:
            self.wanted_at = now
            if self.child is None and now >= self.retry_at:
                self._take(now)
        elif self.child is not None and now - self.wanted_at >= self.grace_s:
            self.release()
            self.log("Claude stopped working: the screen may lock and sleep again")
            return
        if self.child is not None:
            self._feed()
            if not self.confirmed and now > self.taken_at:
                self.confirmed = True
                self._once("Claude is working: the screen stays on (idle inhibitor held)")

    def _take(self, now: float) -> None:
        try:
            self.child = self.spawn()
        except OSError as e:
            self._once(f"cannot start the idle inhibitor: {type(e).__name__}; trying again every "
                       f"{self.retry_s:.0f} s")
            self.retry_at = now + self.retry_s
            return
        self.taken_at, self.confirmed = now, False

    def _feed(self) -> None:
        """One byte renews the lease. A full pipe or a gone reader is not an
        error here: the next poll() tells whether the child is still there."""
        stdin = self.child.stdin if self.child is not None else None
        if stdin is None:
            return
        try:
            os.write(stdin.fileno(), b"\n")
        except (BlockingIOError, BrokenPipeError):
            pass

    def release(self) -> None:
        """Close the pipe: the reader ends, systemd-inhibit ends, the lock goes."""
        child = self.child
        if child is None:
            return
        self._drop()
        self._said.clear()
        try:
            child.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            child.kill()            # systemd-inhibit forks its child with PDEATHSIG
            try:
                child.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.log("the idle inhibitor did not exit after SIGKILL")

    def _drop(self) -> None:
        child, self.child = self.child, None
        self.confirmed = False
        if child is not None and child.stdin is not None:
            try:
                child.stdin.close()
            except OSError:
                pass        # the reader already gone: the pipe is broken, which is the point
