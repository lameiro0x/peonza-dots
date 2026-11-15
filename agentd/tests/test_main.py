import io
import json
import os
import shutil
import signal
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from agentd.__main__ import App, Loop, handle_signals, main, make_app
from agentd.claude import ClaudeHome
from agentd.hypr import RealHypr
from agentd.procfs import Proc
from agentd.publish import Publisher
from world import MARKER, main_world

THEMES = Path(__file__).resolve().parents[2] / "themes"


class Tty(io.StringIO):
    def isatty(self):
        return True


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.fx = main_world(root / "fx").root
        self.out = root / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *extra, stdout=None):
        stdout = stdout if stdout is not None else io.StringIO()
        rc = main(["--once", "--fixtures", str(self.fx), "--outdir", str(self.out),
                   "--palette", str(self.fx / "missing.json"), *extra], stdout=stdout)
        return rc, stdout.getvalue()

    def test_once_with_fixtures_writes_every_consumer_file(self):
        rc, _ = self.run_cli("--no-dispatch")
        self.assertEqual(rc, 0)
        names = sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file())
        self.assertIn("roster.json", names)
        self.assertIn("lock.txt", names)
        self.assertIn("waybar/agents.json", names)
        self.assertEqual(len([n for n in names if n.startswith("waybar/DP-1-")]), 12)
        self.assertEqual(len([n for n in names if n.startswith("waybar/HDMI-A-1-")]), 12)

    def test_nothing_reaches_stdout_off_a_tty(self):
        _, printed = self.run_cli("--no-dispatch")
        self.assertEqual(printed, "")

    def test_a_tty_gets_a_plain_summary(self):
        _, printed = self.run_cli("--no-dispatch", stdout=Tty())
        self.assertIn("DP-1-3: 3 \U000f1719 brujula · Arreglar…", printed)
        self.assertNotIn("<span", printed)

    def test_the_users_prompt_text_reaches_no_output(self):
        _, printed = self.run_cli("--no-dispatch", stdout=Tty())
        self.assertNotIn(MARKER, printed)
        for f in self.out.rglob("*"):
            if f.is_file():
                self.assertNotIn(MARKER, f.read_text(encoding="utf-8"), f)

    def test_tag_dispatch_goes_to_hypr_unless_disabled(self):
        app = make_app(["--once", "--fixtures", str(self.fx), "--outdir", str(self.out)], os.environ)
        app.cycle()
        self.assertEqual(app.hypr.dispatched, [
            'hl.dsp.window.tag({ tag = "+agentwait", window = "address:0x5500000003" })',
            'hl.dsp.window.tag({ tag = "-agentwait", window = "address:0x5500000004" })'])
        app = make_app(["--once", "--no-dispatch", "--fixtures", str(self.fx), "--outdir", str(self.out)],
                       os.environ)
        app.cycle()
        self.assertEqual(app.hypr.dispatched, [])
        self.assertIsNone(app.publisher.signal)

    def test_agentd_never_writes_a_focus_click(self):
        # Clicks are Waybar's config (Lua `hl.dsp.focus`); agentd only writes data.
        self.run_cli()
        for f in (self.out / "waybar").iterdir():
            payload = json.loads(f.read_text())
            self.assertEqual(set(payload), {"text", "tooltip", "class"})
            self.assertNotIn("hl.dsp", f.read_text())

    def test_default_outdir_and_palette(self):
        app = make_app(["--once"], {"XDG_RUNTIME_DIR": "/run/user/1000", "HOME": "/home/u"})
        self.assertEqual(app.publisher.outdir, Path("/run/user/1000/agentd"))
        self.assertEqual(app.palette_path, Path("/home/u/.config/ryce/palette.json"))

    def test_wait_gives_a_missing_compositor_n_seconds_then_publishes_anyway(self):
        rt = Path(self.tmp.name) / "rt"
        rt.mkdir()
        t0 = time.monotonic()
        rc = main(["--once", "--wait", "1", "--no-dispatch", "--outdir", str(self.out)],
                  stdout=io.StringIO(), stderr=io.StringIO(),
                  env={"XDG_RUNTIME_DIR": str(rt), "HOME": self.tmp.name})
        self.assertGreaterEqual(time.monotonic() - t0, 1.0)
        self.assertEqual(rc, 1)
        self.assertTrue((self.out / "roster.json").exists())

    def test_reset_mode_turns_the_bar_back_into_numerals(self):
        self.run_cli("--no-dispatch")
        rc = main(["--reset", "--fixtures", str(self.fx), "--outdir", str(self.out)],
                  stdout=io.StringIO(), stderr=io.StringIO())
        self.assertEqual(rc, 0)
        self.assertFalse((self.out / "roster.json").exists())
        self.assertEqual(json.loads((self.out / "waybar" / "DP-1-3.json").read_text())["class"], ["empty"])

    def test_a_rejected_tag_is_logged_once_while_it_keeps_failing(self):
        err = io.StringIO()
        app = make_app(["--once", "--fixtures", str(self.fx), "--outdir", str(self.out)], os.environ, err=err)
        app.hypr.dispatch = lambda lua: "error: bad window"
        for _ in range(3):
            app.cycle()
        self.assertEqual(err.getvalue().count("tag +agentwait 0x5500000003: error: bad window"), 1)

    def test_reload_rewrites_every_slot_in_the_new_themes_ink(self):
        theme = Path(self.tmp.name) / "palette.json"
        shutil.copy(THEMES / "origen" / "theme.json", theme)
        app = make_app(["--once", "--no-dispatch", "--fixtures", str(self.fx), "--outdir", str(self.out),
                        "--palette", str(theme)], os.environ)
        woken = []
        app.publisher.signal = lambda: woken.append(1)
        app.cycle()
        slots = sorted((self.out / "waybar").iterdir())
        inodes = {f.name: f.stat().st_ino for f in slots}
        app.cycle()
        self.assertEqual({f.name: f.stat().st_ino for f in slots}, inodes, "nothing changed, nothing rewritten")

        shutil.copy(THEMES / "grafito" / "theme.json", theme)
        app.reload()
        app.cycle()
        # Every file, the empty slots and the counter included, is a fresh file now.
        for f in slots:
            self.assertNotEqual(f.stat().st_ino, inodes[f.name], f.name)
        self.assertEqual(len(woken), 2)
        fg1 = json.loads((THEMES / "grafito" / "theme.json").read_text())["colors"]["fg1"]
        text = json.loads((self.out / "waybar" / "DP-1-3.json").read_text())["text"]
        self.assertIn(f'<span foreground="{fg1}">3</span>', text)

    def test_unwritable_outdir_fails_once_without_a_traceback(self):
        blocker = Path(self.tmp.name) / "file"
        blocker.write_text("")
        err = io.StringIO()
        rc = main(["--once", "--no-dispatch", "--fixtures", str(self.fx), "--outdir", str(blocker / "x")],
                  stdout=io.StringIO(), stderr=err)
        self.assertEqual(rc, 1)
        self.assertIn("agentd: cycle failed:", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


class FakeApp:
    def __init__(self, conns, session_windows=()):
        self.conns = list(conns)
        self.connects = 0
        self.cycles = []
        self.reloads = 0
        self.active = False
        self.session_windows = set(session_windows)
        app = self

        class H:
            def events(self):
                app.connects += 1
                return app.conns.pop(0) if app.conns else None

        class C:
            def signature(self):
                return ()

        self.hypr, self.home = H(), C()

    def safe_cycle(self):
        self.cycles.append(time.monotonic())

    def reload(self):
        self.reloads += 1


class LoopTest(unittest.TestCase):
    def start(self, session_windows=(), **gaps):
        self.a, b = socket.socketpair()
        self.a.setblocking(False)
        self.app = FakeApp([self.a], session_windows)
        self.loop = Loop(self.app, debounce_s=0.02, poll_s=0.05, heartbeat_s=60, **gaps)
        self.t = threading.Thread(target=self.loop.run, daemon=True)
        self.t.start()
        time.sleep(0.2)
        self.assertEqual(len(self.app.cycles), 1)              # the start-up collect
        return b

    def tearDown(self):
        self.loop.stop()
        self.t.join(2)
        self.assertFalse(self.t.is_alive())

    def test_title_events_of_session_windows_are_ignored(self):
        b = self.start({"0x5500000002"}, event_gap_s=0.05, title_gap_s=0.05)
        for i in range(30):
            b.sendall(f"windowtitlev2>>5500000002,⠂ frame {i}\n".encode())
        time.sleep(0.3)
        self.assertEqual(len(self.app.cycles), 1)

    def test_a_burst_coalesces_and_noise_is_ignored(self):
        b = self.start(event_gap_s=0.05, title_gap_s=0.05)
        for i in range(20):
            b.sendall(f"openwindow>>{i:x},2,kitty,x\n".encode())
        time.sleep(0.3)
        self.assertEqual(len(self.app.cycles), 2)
        b.sendall(b"bell>>0x1\nscreencast>>0,0\n")
        time.sleep(0.3)
        self.assertEqual(len(self.app.cycles), 2)
        for ev in (b"moveworkspacev2>>3,3,DP-1\n", b"renameworkspacev2>>3,web\n"):
            b.sendall(ev)
            time.sleep(0.2)
        self.assertEqual(len(self.app.cycles), 4)

    def test_structural_events_wait_the_minimum_gap(self):
        b = self.start(event_gap_s=0.4, title_gap_s=1.0)
        b.sendall(b"openwindow>>1,2,kitty,x\n")
        time.sleep(0.7)
        self.assertEqual(len(self.app.cycles), 2)
        self.assertGreaterEqual(self.app.cycles[1] - self.app.cycles[0], 0.39)

    def test_a_title_flood_from_a_page_publishes_at_most_once_per_gap(self):
        b = self.start(event_gap_s=0.05, title_gap_s=0.3)
        end = time.monotonic() + 1.2
        while time.monotonic() < end:
            b.sendall(b"windowtitlev2>>99,(1) inbox\n")
            time.sleep(0.01)
        time.sleep(0.35)
        self.assertLessEqual(len(self.app.cycles), 1 + 5)
        self.assertGreaterEqual(len(self.app.cycles), 3)

    def test_a_long_event_line_keeps_its_name(self):
        b = self.start(event_gap_s=0.05, title_gap_s=0.05)
        b.sendall(b"openwindow>>1,2,kitty," + b"x" * 6000)
        time.sleep(0.05)
        b.sendall(b"y" * 6000 + b"\n")
        time.sleep(0.3)
        self.assertEqual(len(self.app.cycles), 2)

    def test_hup_reloads_then_publishes_at_once(self):
        self.start(event_gap_s=5, title_gap_s=5)
        self.loop.hup()
        time.sleep(0.2)
        self.assertEqual(self.app.reloads, 1)
        self.assertEqual(len(self.app.cycles), 2)

    def test_eof_goes_looking_for_a_new_socket(self):
        b = self.start()
        b.close()
        time.sleep(0.3)
        self.assertGreaterEqual(self.app.connects, 2)


class SignalTest(unittest.TestCase):
    def test_sighup_asks_the_loop_to_reload_and_wakes_it(self):
        loop = Loop(FakeApp([]))
        saved = {n: signal.getsignal(n) for n in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
        prev_fd = signal.set_wakeup_fd(-1)
        try:
            handle_signals(loop)
            os.kill(os.getpid(), signal.SIGHUP)
            time.sleep(0.05)        # the handler runs between bytecodes of this thread
            self.assertTrue(loop._reload)
            self.assertFalse(loop._stopping)
            self.assertTrue(os.read(loop.wake_r, 64))
        finally:
            signal.set_wakeup_fd(prev_fd)
            for n, h in saved.items():
                signal.signal(n, h)
            os.close(loop.wake_r)
            os.close(loop.wake_w)


class FakeCompositor:
    """Hyprland's two sockets, served from a world's hypr/*.json."""

    def __init__(self, rt: Path, hypr_dir: Path):
        d = rt / "hypr" / "sig"
        d.mkdir(parents=True)
        self.hypr_dir, self.dispatched, self.streams = hypr_dir, [], []
        self.ctl = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.ev = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.ctl.bind(str(d / ".socket.sock"))
            self.ev.bind(str(d / ".socket2.sock"))
        except OSError:
            self.close()
            raise
        for s, fn in ((self.ctl, self._control), (self.ev, self._events)):
            s.listen(8)
            threading.Thread(target=fn, daemon=True).start()

    def _control(self):
        while True:
            try:
                c, _ = self.ctl.accept()
            except OSError:
                return
            with c:
                req = c.recv(65536).decode()
                if req.startswith("j/"):
                    f = self.hypr_dir / f"{req[2:]}.json"
                    c.sendall(f.read_bytes() if f.exists() else b"[]")
                elif req.startswith("dispatch "):
                    self.dispatched.append(req[len("dispatch "):])
                    c.sendall(b"ok")

    def _events(self):
        while True:
            try:
                c, _ = self.ev.accept()
            except OSError:
                return
            self.streams.append(c)

    def close(self):
        for s in [self.ctl, self.ev, *self.streams]:
            s.close()


class LiveLoopTest(unittest.TestCase):
    """The real loop and RealHypr against stand-in sockets: a session that
    starts waiting must ring and be tagged within the plan's 1.5 s."""

    def setUp(self):
        base = "/tmp" if os.access("/tmp", os.W_OK) else None
        self.tmp = tempfile.TemporaryDirectory(dir=base, prefix="ag")
        root = Path(self.tmp.name)
        if len(str(root / "hypr" / "sig" / ".socket2.sock")) > 100:
            self.skipTest("socket path too long here")
        self.w = main_world(root / "w")
        try:
            self.hypr = FakeCompositor(root / "rt", self.w.root / "hypr")
        except OSError as e:
            self.skipTest(f"cannot bind a unix socket here: {e}")
        self.out = root / "out"
        r = self.w.root
        self.app = App(RealHypr({"XDG_RUNTIME_DIR": str(root / "rt")}, log=lambda msg: None), Proc(r / "proc"),
                       ClaudeHome(r / "claude"), str(r / "fs"), Publisher(self.out, signal=None),
                       r / "none.json", dispatch=True)
        self.loop = Loop(self.app)
        self.thread = threading.Thread(target=self.loop.run, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.loop.stop()
        self.thread.join(3)
        self.hypr.close()
        self.tmp.cleanup()

    def slot(self, name):
        try:
            return json.loads((self.out / "waybar" / name).read_text())
        except (OSError, ValueError):
            return None

    def test_waiting_reaches_ring_and_tag_within_one_and_a_half_seconds(self):
        deadline = time.monotonic() + 3
        while self.slot("DP-1-2.json") is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertIn("working", self.slot("DP-1-2.json")["class"])
        f = self.w.root / "claude" / "sessions" / "1003.json"
        d = json.loads(f.read_text())
        d.update(status="waiting", waitingFor="permission prompt")
        f.write_text(json.dumps(d))
        t0 = time.monotonic()
        plus = 'hl.dsp.window.tag({ tag = "+agentwait", window = "address:0x5500000002" })'
        while time.monotonic() - t0 < 1.5:
            if plus in self.hypr.dispatched and "waiting" in (self.slot("DP-1-2.json") or {}).get("class", []):
                break
            time.sleep(0.02)
        self.assertIn(plus, self.hypr.dispatched)
        self.assertIn("waiting", self.slot("DP-1-2.json")["class"])
        self.assertEqual((self.out / "lock.txt").read_text(), "2 agentes te esperan")


if __name__ == "__main__":
    unittest.main()
