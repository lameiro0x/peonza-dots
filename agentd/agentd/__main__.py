"""agentd entry point: the event loop and the CLI.

    python3 -m agentd                       run (systemd --user service)
    python3 -m agentd --once [--wait 45]    one collect + publish, then exit

SIGHUP (systemctl --user reload agentd, sent by ryce-theme after a theme
switch) re-reads the palette and rewrites every file.

Runs as its own systemd --user service, never as a Waybar `exec` child: Waybar
kills those with killpg and waitpid()s without a timeout, so a child slow to
die freezes the bar.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import selectors
import signal
import threading
import sys
import time
import traceback
from pathlib import Path
from typing import Callable, Mapping, TextIO

from . import render
from .claude import ClaudeHome
from .const import MAX_WS, RUNTIME
from .hypr import FakeHypr, Hypr, RealHypr
from .model import Snapshot, collect
from .procfs import Proc
from . import publish
from .publish import Publisher, reconcile, signal_waybar

# socket2 v2 events only: the v1 twins double the rate and v1 `windowtitle`
# does not even carry the title.
WATCHED = {
    "workspacev2", "focusedmonv2", "activewindowv2", "openwindow", "closewindow",
    "movewindowv2", "windowtitlev2", "createworkspacev2", "destroyworkspacev2",
    "monitoraddedv2", "monitorremovedv2", "monitorremoved", "urgent", "activespecialv2",
    "moveworkspacev2", "renameworkspacev2", "configreloaded",
}
TITLE_EVENT = "windowtitlev2"
LINE_MAX = 4096         # an event name never needs more; the rest of a long line is dropped


def parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agentd", description=__doc__.split("\n\n")[0])
    p.add_argument("--once", action="store_true", help="collect and publish once, then exit")
    p.add_argument("--reset", action="store_true",
                   help="put the bar back to bare numerals, drop the roster, untag windows, exit "
                        "(ExecStopPost: also runs after a crash)")
    p.add_argument("--wait", type=float, default=0, metavar="N",
                   help="with --once: wait up to N s for Hyprland first")
    p.add_argument("--no-dispatch", action="store_true",
                   help="touch nothing outside --outdir: no window tags, no Waybar signal")
    p.add_argument("--outdir", type=Path, help="default: $XDG_RUNTIME_DIR/agentd")
    p.add_argument("--fixtures", type=Path, metavar="DIR",
                   help="read hypr/ proc/ claude/ fs/ under DIR instead of the machine (implies --once)")
    p.add_argument("--palette", type=Path,
                   help="a theme.json (ryce.theme/2); default: ~/.config/ryce/palette.json, "
                        "the link to the current theme")
    return p.parse_args(argv)


class App:
    """One collect → publish → reconcile cycle over injected seams."""

    def __init__(self, hypr: Hypr, proc: Proc, home: ClaudeHome, fsroot: str, publisher: Publisher,
                 palette_path: Path, dispatch: bool, clock: Callable[[], float] = time.time,
                 err: TextIO | None = None, args: argparse.Namespace | None = None):
        self.args = args
        self.hypr, self.proc, self.home, self.fsroot = hypr, proc, home, fsroot
        self.publisher, self.palette_path, self.dispatch = publisher, palette_path, dispatch
        self.palette = render.load_palette(palette_path)
        self.clock = clock
        self.err = err
        self.active = False          # a session is busy or waiting: transcripts move
        self.session_windows: set[str] = set()   # their title events are spinner noise
        self._last_error = ""
        self._tag_errors: set[str] = set()

    def log(self, msg: str) -> None:
        print(f"agentd: {msg}", file=self.err or sys.stderr, flush=True)

    def cycle(self) -> Snapshot:
        snap = collect(self.hypr, self.proc, self.home, self.fsroot)
        self.publisher.publish(snap, self.palette, self.clock())
        if self.dispatch and snap.connected:
            self._report(reconcile(self.hypr, snap.desired_tags, snap.current_tags))
        self.active = any(s.state in ("busy", "waiting") for s in snap.sessions)
        self.session_windows = {s.window for s in snap.sessions if s.window}
        return snap

    def _report(self, errors: list[str]) -> None:
        """Log a rejected tag once, not on every 2 s cycle while it persists."""
        for e in errors:
            if e not in self._tag_errors:
                self.log(e)
        self._tag_errors = set(errors)

    def reload(self) -> None:
        """The theme changed: re-read the palette and republish everything. Slot
        markup embeds colours, so every slot must be rewritten, and a Waybar
        started since the last cycle must not keep an older theme's ink."""
        self.palette = render.load_palette(self.palette_path)
        self.publisher.forget()

    def reset(self) -> None:
        self._report(publish.reset(self.publisher.outdir, self.hypr if self.dispatch else None,
                                   self.publisher.signal))

    def safe_cycle(self) -> Snapshot | None:
        """A cycle that cannot kill the daemon. The log line names the failure
        and where it happened — never its message, which could quote a session."""
        try:
            snap = self.cycle()
        except Exception as e:  # the daemon's outer boundary: report, keep serving
            frame = traceback.extract_tb(e.__traceback__)[-1]
            line = f"cycle failed: {type(e).__name__} at {Path(frame.filename).name}:{frame.lineno}"
            if line != self._last_error:
                self.log(line)
                self._last_error = line
            return None
        self._last_error = ""
        return snap


def make_app(argv: list[str], env: Mapping[str, str], clock: Callable[[], float] = time.time,
             err: TextIO | None = None) -> App:
    a = parse(argv)
    home = Path(env.get("HOME") or Path.home())
    outdir = a.outdir or Path(env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}") / RUNTIME
    palette = a.palette or home / ".config" / "ryce" / "palette.json"
    if a.fixtures:
        fx = a.fixtures
        hypr, proc = FakeHypr(fx / "hypr"), Proc(fx / "proc")
        claude, fsroot = ClaudeHome(fx / "claude", clock=clock), str(fx / "fs")
    else:
        hypr = RealHypr(env, log=lambda msg: print(f"agentd: {msg}", file=err or sys.stderr, flush=True))
        proc = Proc()
        claude, fsroot = ClaudeHome(home / ".claude", clock=clock), "/"
    quiet = a.no_dispatch or a.fixtures is not None
    return App(hypr, proc, claude, fsroot, Publisher(outdir, signal=None if quiet else lambda: signal_waybar(proc)),
               palette, dispatch=not a.no_dispatch, clock=clock, err=err, args=a)


class Loop:
    """socket2 events, shaped; the sessions dir polled at 1 Hz; a heartbeat.

    Event shaping, because a cycle costs four compositor requests and a /proc
    walk: title events of windows that host a session are dropped (Claude
    Code's spinner retitles them every second; their state comes from the
    session file), other title-only changes publish at most once per
    title_gap_s (a page can retitle itself every 10 ms), and every other event
    waits at least event_gap_s after the previous cycle. The compositor's
    socket is looked up again after every disconnect.
    """

    def __init__(self, app, debounce_s: float = 0.06, event_gap_s: float = 0.5,
                 title_gap_s: float = 1.0, poll_s: float = 1.0, heartbeat_s: float = 30.0,
                 busy_s: float = 2.0):
        self.app = app
        self.debounce_s, self.event_gap_s, self.title_gap_s = debounce_s, event_gap_s, title_gap_s
        self.poll_s, self.heartbeat_s, self.busy_s = poll_s, heartbeat_s, busy_s
        self.wake_r, self.wake_w = os.pipe()
        os.set_blocking(self.wake_r, False)
        os.set_blocking(self.wake_w, False)
        self._stopping = False
        self._reload = False

    def _wake(self) -> None:
        try:
            os.write(self.wake_w, b"x")
        except OSError:
            pass

    def stop(self, *_):
        self._stopping = True
        self._wake()

    def hup(self, *_):
        self._reload = True
        self._wake()

    def _gap(self, line: bytes) -> float | None:
        """How long after the last cycle this event may trigger one; None: ignore it."""
        name, _, data = line.partition(b">>")
        name = name.decode("ascii", "replace")
        if name == TITLE_EVENT:
            addr = data.split(b",", 1)[0].decode("ascii", "replace")
            addr = addr if addr.startswith("0x") else f"0x{addr}"
            return None if addr in self.app.session_windows else self.title_gap_s
        return self.event_gap_s if name in WATCHED else None

    def run(self) -> None:
        sel = selectors.DefaultSelector()
        sel.register(self.wake_r, selectors.EVENT_READ, "wake")
        mono = time.monotonic
        conn, buf, skipping, sig = None, b"", False, None
        pending, deadline = True, 0.0
        last_cycle, next_poll, next_connect = float("-inf"), 0.0, 0.0

        def want(at: float) -> None:
            nonlocal pending, deadline
            deadline = min(deadline, at) if pending else at
            pending = True

        while not self._stopping:
            now = mono()
            if conn is None and now >= next_connect:
                conn = self.app.hypr.events()
                if conn is not None:
                    sel.register(conn, selectors.EVENT_READ, "hypr")
                    want(now)
                else:
                    next_connect = now + 1.0
            wake_at = min(next_poll, last_cycle + self.heartbeat_s)
            if pending:
                wake_at = min(wake_at, deadline)
            if conn is None:
                wake_at = min(wake_at, next_connect)
            for key, _ in sel.select(max(0.0, wake_at - mono())):
                if key.data == "wake":
                    try:
                        os.read(self.wake_r, 4096)
                    except BlockingIOError:
                        pass
                    continue
                try:
                    chunk = conn.recv(65536)
                except BlockingIOError:
                    continue
                except OSError:
                    chunk = b""
                if not chunk:
                    # Hyprland went away or dropped us for being slow: reconnect.
                    sel.unregister(conn)
                    conn.close()
                    conn, buf, skipping, next_connect = None, b"", False, 0.0
                    want(mono())
                    break
                if skipping:
                    # Inside the tail of an over-long line: drop up to its end,
                    # keeping the "\n" so the head we held is terminated.
                    cut = chunk.find(b"\n")
                    if cut < 0:
                        continue
                    chunk, skipping = chunk[cut:], False
                *lines, buf = (buf + chunk).split(b"\n")
                if len(buf) > LINE_MAX:
                    buf, skipping = buf[:LINE_MAX], True     # the head holds the event name
                for line in lines:
                    gap = self._gap(line)
                    if gap is not None:
                        now = mono()
                        want(max(now + self.debounce_s, last_cycle + gap))
            if self._stopping:
                break
            if self._reload:
                self._reload = False
                self.app.reload()
                want(mono())
            now = mono()
            if now >= next_poll:
                next_poll = now + self.poll_s
                s = self.app.home.signature()
                if s != sig:
                    sig = s
                    want(now)
                elif self.app.active and now - last_cycle >= self.busy_s:
                    want(now)
            if (pending and now >= deadline) or now >= last_cycle + self.heartbeat_s:
                self.app.safe_cycle()
                pending, last_cycle = False, now
        if conn is not None:
            conn.close()
        sel.close()


_TAG = re.compile(r"<[^>]*>")


def summary(snap: Snapshot, app: App) -> list[str]:
    files = render.waybar(snap, app.palette)
    rows = []
    for out in snap.outputs:
        for n in range(1, MAX_WS + 1):
            text = files[f"{out}-{n}.json"]["text"]
            if text:
                plain = html.unescape(_TAG.sub("", text)).replace("\u2068", "").replace("\u2069", "")
                rows.append(f"{out}-{n}: {plain}")
    agents = files["agents.json"]
    rows.append(f"agents: {agents['text']} ({agents['tooltip']})")
    rows.append(f"-> {app.publisher.outdir}")
    return rows


def wait_for_hyprland(hypr: Hypr, seconds: float) -> None:
    end = time.monotonic() + seconds
    while hypr.query("monitors") is None and time.monotonic() < end:
        time.sleep(0.5)


def handle_signals(loop: Loop) -> None:
    """TERM/INT stop the loop, HUP reloads the palette. The handlers only set a
    flag and poke the loop's wake pipe; the work happens in the loop."""
    signal.set_wakeup_fd(loop.wake_w)
    signal.signal(signal.SIGTERM, loop.stop)
    signal.signal(signal.SIGINT, loop.stop)
    signal.signal(signal.SIGHUP, loop.hup)


def main(argv: list[str] | None = None, stdout: TextIO | None = None, stderr: TextIO | None = None,
         env: Mapping[str, str] = os.environ) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # A theme switch sends SIGHUP and its default action kills: ignore it until
    # handle_signals() installs the real handler (startup takes a moment).
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    stdout = stdout or sys.stdout
    app = make_app(argv, env, err=stderr)
    a = app.args
    if a.reset:
        app.reset()
        return 0
    if a.once or a.fixtures:
        if a.wait and not a.fixtures:
            wait_for_hyprland(app.hypr, a.wait)
        snap = app.safe_cycle()
        if snap is None:
            return 1
        # Only to a terminal. Under systemd this is ExecStartPre and stdout is
        # the journal, persistent on this machine: repo names and page titles
        # would land on disk at every boot for a line nobody reads.
        if stdout.isatty():
            print("\n".join(summary(snap, app)), file=stdout)
        return 0 if snap.connected else 1

    loop = Loop(app)
    handle_signals(loop)
    loop.run()
    # A stopped agentd must not leave a ringing bar and a bordered window behind.
    app.reset()
    return 0


if __name__ == "__main__":
    sys.exit(main())
