import io
import signal
import json
import os
import stat
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from agentd import render
from agentd.claude import ClaudeHome
from agentd.hypr import FakeHypr
from agentd.model import collect
from agentd.procfs import Proc
from agentd.publish import Publisher, reconcile, reset, signal_waybar, tag_commands
from world import NOW, World, main_world

PLUS3 = 'hl.dsp.window.tag({ tag = "+agentwait", window = "address:0x3" })'
MINUS4 = 'hl.dsp.window.tag({ tag = "-agentwait", window = "address:0x4" })'


class TagTest(unittest.TestCase):
    def test_add_missing_and_remove_stale_with_exact_lua(self):
        self.assertEqual(tag_commands({"0x3", "0x5"}, {"0x4", "0x5"}), [PLUS3, MINUS4])

    def test_in_sync_sends_nothing(self):
        self.assertEqual(tag_commands({"0x3"}, {"0x3"}), [])

    def test_addresses_that_are_not_bare_lowercase_hex_never_reach_lua(self):
        evil = {'0x3" }) hl.dsp.exec_cmd("rm -rf ~") --', "0x3\n", "0X3", "3", "", "0x"}
        self.assertEqual(tag_commands(evil, set()), [])
        self.assertEqual(tag_commands(set(), evil), [])

    def test_reconcile_sends_through_hypr_and_returns_failures(self):
        with tempfile.TemporaryDirectory() as t:
            h = FakeHypr(t)
            self.assertEqual(reconcile(h, {"0x3"}, {"0x4"}), [])
            self.assertEqual(h.dispatched, [PLUS3, MINUS4])
            h.dispatch = lambda lua: "error: no such window"
            self.assertEqual(reconcile(h, {"0x3"}, set()), ["tag +agentwait 0x3: error: no such window"])


class SignalTest(unittest.TestCase):
    @unittest.skipUnless(hasattr(signal, "SIGRTMIN"), "real-time signals are Linux-only")
    def test_only_waybar_processes_older_than_a_second_are_woken(self):
        with tempfile.TemporaryDirectory() as t:
            w = World(Path(t))
            (w.root / "proc" / "uptime").write_text("100000.00 5.00\n")
            hz = os.sysconf("SC_CLK_TCK")
            w.proc(300, "waybar")                                     # running for hours
            w.proc(301, "waybar", start=int((100000 - 0.4) * hz))     # still starting up
            w.proc(302, "waybar-helper")
            w.proc(303, "waybar")
            sent = []

            def kill(pid, sig):
                if pid == 303:
                    raise ProcessLookupError(pid)                      # exited meanwhile
                sent.append((pid, sig))

            signal_waybar(Proc(w.root / "proc"), kill=kill)
            self.assertEqual(sent, [(300, signal.SIGRTMIN + 9)])


class PublisherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.world = main_world(root / "world")
        self.out = root / "out" / "agentd"
        self.signals = 0
        self.pub = Publisher(self.out, signal=self.bump)

    def tearDown(self):
        self.tmp.cleanup()

    def bump(self):
        self.signals += 1

    def snap(self):
        r = self.world.root
        return collect(FakeHypr(r / "hypr"), Proc(r / "proc"),
                       ClaudeHome(r / "claude", clock=lambda: NOW), str(r / "fs"))

    def test_first_publish_writes_everything_and_signals_once(self):
        written = self.pub.publish(self.snap(), render.GREYS, NOW)
        self.assertEqual(self.signals, 1)
        self.assertIn("waybar/DP-1-3.json", written)
        self.assertIn("waybar/HDMI-A-1-window.json", written)
        self.assertIn("waybar/agents.json", written)
        self.assertEqual((self.out / "lock.txt").read_text(), "1 agente te espera")
        payload = json.loads((self.out / "waybar" / "DP-1-3.json").read_text())
        self.assertIn("waiting", payload["class"])
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.out / "roster.json").stat().st_mode), 0o600)
        self.assertEqual([p.name for p in self.out.rglob(".*")], [])     # no temp files left

    def test_spinner_frames_cause_zero_rewrites(self):
        self.pub.publish(self.snap(), render.GREYS, NOW)
        clients = self.world.root / "hypr" / "clients.json"
        for frame in "⠐⠠⢀⡀✳✻":
            data = json.loads(clients.read_text())
            data[1]["title"] = f"{frame} Montar el rice"
            clients.write_text(json.dumps(data))
            self.assertEqual(self.pub.publish(self.snap(), render.GREYS, NOW + 1), [])
        self.assertEqual(self.signals, 1)

    def test_roster_is_not_rewritten_for_a_new_timestamp_alone(self):
        self.pub.publish(self.snap(), render.GREYS, NOW)
        self.assertEqual(self.pub.publish(self.snap(), render.GREYS, NOW + 60), [])
        self.assertEqual(json.loads((self.out / "roster.json").read_text())["generatedAt"], NOW)

    def test_a_state_change_rewrites_only_what_changed(self):
        self.pub.publish(self.snap(), render.GREYS, NOW)
        s = self.world.root / "claude" / "sessions" / "1103.json"
        d = json.loads(s.read_text())
        d["status"] = "busy"
        del d["waitingFor"]
        s.write_text(json.dumps(d))
        written = self.pub.publish(self.snap(), render.GREYS, NOW + 1)
        self.assertEqual(sorted(written), ["lock.txt", "roster.json", "waybar/DP-1-3.json",
                                           "waybar/agents.json"])
        self.assertEqual((self.out / "lock.txt").read_text(), "")
        self.assertEqual(self.signals, 2)

    def test_no_signal_when_disabled(self):
        Publisher(self.out, signal=None).publish(self.snap(), render.GREYS, NOW)
        self.assertEqual(self.signals, 0)

    def test_compositor_down_keeps_slots_and_still_updates_counters(self):
        self.pub.publish(self.snap(), render.GREYS, NOW)
        for f in (self.world.root / "hypr").iterdir():
            f.unlink()
        written = self.pub.publish(self.snap(), render.GREYS, NOW + 1)
        self.assertNotIn("waybar/DP-1-3.json", written)
        self.assertTrue((self.out / "waybar" / "DP-1-3.json").exists())
        self.assertFalse(json.loads((self.out / "roster.json").read_text())["hypr"]["connected"])


class ResetTest(unittest.TestCase):
    """agentd stopping must not leave a ringing bar or a glowing window behind."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.w = main_world(root / "world")
        self.out = root / "agentd"
        r = self.w.root
        snap = collect(FakeHypr(r / "hypr"), Proc(r / "proc"),
                       ClaudeHome(r / "claude", clock=lambda: NOW), str(r / "fs"))
        Publisher(self.out).publish(snap, render.GREYS, NOW)
        self.signals = 0

    def tearDown(self):
        self.tmp.cleanup()

    def bump(self):
        self.signals += 1

    def slot(self, name):
        return json.loads((self.out / "waybar" / name).read_text())

    def test_reset_leaves_numerals_and_nothing_else(self):
        h = FakeHypr(self.w.root / "hypr")
        reset(self.out, h, self.bump)
        self.assertEqual(self.slot("DP-1-3.json"), {"text": "三", "tooltip": "", "class": ["empty"]})
        self.assertEqual(self.slot("HDMI-A-1-9.json"), {"text": "", "tooltip": "", "class": ["off"]})
        self.assertEqual(self.slot("DP-1-window.json"), {"text": "", "tooltip": "", "class": ["empty"]})
        self.assertEqual(self.slot("agents.json"), {"text": "", "tooltip": "", "class": ["calm"]})
        self.assertFalse((self.out / "roster.json").exists())
        self.assertEqual((self.out / "lock.txt").read_text(), "")
        self.assertEqual(self.signals, 1)
        self.assertEqual(h.dispatched, [MINUS4.replace("0x4", "0x5500000004")])

    def test_reset_without_compositor_or_outdir_does_not_fail(self):
        empty = Path(self.tmp.name) / "no-hypr"
        empty.mkdir()
        reset(self.out, FakeHypr(empty), None)
        reset(Path(self.tmp.name) / "never-created", None, None)
        self.assertFalse((Path(self.tmp.name) / "never-created").exists())


if __name__ == "__main__":
    unittest.main()
