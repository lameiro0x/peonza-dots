import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from agentd.hypr import FakeHypr, RealHypr


class FakeHyprTest(unittest.TestCase):
    def test_reads_queries_from_files_and_records_dispatches(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "clients.json").write_text('[{"address": "0x1"}]')
            Path(t, "monitors.json").write_text("{not json")
            h = FakeHypr(t)
            self.assertEqual(h.query("clients"), [{"address": "0x1"}])
            self.assertIsNone(h.query("monitors"))
            self.assertIsNone(h.query("workspaces"))
            self.assertEqual(h.dispatch("hl.x()"), "ok")
            self.assertEqual(h.dispatched, ["hl.x()"])
            self.assertIsNone(h.events())


class SignatureTest(unittest.TestCase):
    """Liveness is a successful connect(), injected here as `probe`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rt = Path(self.tmp.name)
        self.alive = set()
        self.logs = []

    def hypr(self, **env):
        env.setdefault("XDG_RUNTIME_DIR", str(self.rt))
        return RealHypr(env, probe=lambda path: Path(path).parent.name in self.alive,
                        log=self.logs.append)

    def tearDown(self):
        self.tmp.cleanup()

    def instance(self, name, live=True, mtime=None):
        d = self.rt / "hypr" / name
        d.mkdir(parents=True)
        (d / ".socket.sock").touch()      # a killed compositor leaves this behind
        if live:
            self.alive.add(name)
        if mtime:
            os.utime(d, (mtime, mtime))

    def test_env_signature_wins_while_it_answers(self):
        self.instance("old", mtime=1)
        self.instance("env", mtime=2)
        self.instance("new", mtime=3)
        self.assertEqual(self.hypr(HYPRLAND_INSTANCE_SIGNATURE="env").signature(), "env")

    def test_a_dead_env_instance_with_its_socket_file_left_is_skipped(self):
        self.instance("dead", live=False, mtime=9)
        self.instance("stale", live=False, mtime=8)
        self.instance("a", mtime=1)
        self.instance("b", mtime=2)
        self.assertEqual(self.hypr(HYPRLAND_INSTANCE_SIGNATURE="dead").signature(), "b")

    def test_a_compositor_restart_is_followed_and_logged_once_each_way(self):
        self.instance("first")
        h = self.hypr(HYPRLAND_INSTANCE_SIGNATURE="first")
        self.assertEqual(h.signature(), "first")
        self.alive.clear()                         # compositor dies
        self.assertIsNone(h.signature(fresh=True))
        self.assertIsNone(h.signature(fresh=True))
        self.instance("second")                    # and comes back under a new signature
        self.assertEqual(h.signature(fresh=True), "second")
        self.assertEqual(self.logs, ["Hyprland connected (first)", "Hyprland not reachable",
                                     "Hyprland connected (second)"])

    def test_no_compositor_is_none_and_queries_fail_soft(self):
        h = self.hypr()
        self.assertIsNone(h.signature())
        self.assertIsNone(h.query("clients"))
        self.assertIsNone(h.dispatch("hl.x()"))
        self.assertIsNone(h.events())


class SocketTest(unittest.TestCase):
    """One-shot requests against a stand-in control socket."""

    def setUp(self):
        # AF_UNIX paths are capped at ~104 bytes; macOS TMPDIR is long.
        base = "/tmp" if os.access("/tmp", os.W_OK) else None
        self.tmp = tempfile.TemporaryDirectory(dir=base, prefix="ag")
        d = Path(self.tmp.name) / "hypr" / "s"
        d.mkdir(parents=True)
        self.path = str(d / ".socket.sock")
        if len(self.path) > 100:
            self.skipTest("socket path too long here")
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.srv.bind(self.path)
        except OSError as e:
            self.skipTest(f"cannot bind a unix socket here: {e}")
        self.srv.listen(4)
        self.got = []
        self.reply = b'[{"id": 1}]'
        threading.Thread(target=self.serve, daemon=True).start()
        self.h = RealHypr({"XDG_RUNTIME_DIR": self.tmp.name}, log=lambda msg: None)

    def tearDown(self):
        self.srv.close()
        self.tmp.cleanup()

    def serve(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            with c:
                req = c.recv(65536).decode()
                if not req:
                    continue                  # the liveness probe: connect, then close
                self.got.append(req)
                c.sendall(self.reply if req.startswith("j/") else b"ok")

    def test_a_title_that_is_not_utf8_does_not_read_as_a_dead_compositor(self):
        self.reply = b'[{"title": "caf\xe9"}]'
        self.assertEqual(self.h.query("clients"), [{"title": "caf\ufffd"}])

    def test_query_is_a_json_request_and_dispatch_is_raw(self):
        self.assertEqual(self.h.query("monitors"), [{"id": 1}])
        self.assertEqual(self.h.dispatch('hl.dsp.focus({ workspace = 3 })'), "ok")
        self.assertEqual(self.got, ["j/monitors", "dispatch hl.dsp.focus({ workspace = 3 })"])


if __name__ == "__main__":
    unittest.main()
