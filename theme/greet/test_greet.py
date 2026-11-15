"""The terminal greeting (theme/greet/greet.py, apps/fish/functions/fish_greeting.fish):
each theme's stream is one kitty plays and then forgets — a placement that keeps the
cursor and never answers, frames that only patch what moved, played once in 1 to 1.5 s
and held on the still — small enough to print in every new shell, in the theme's inks
and never its signal; and fish prints it only in a local kitty wide and tall enough,
with the hello the hour calls for.

    python3 -m unittest discover -s theme/greet -v

The fish tests need fish; the up-to-date check needs the brand repo, node and rsvg-convert.
"""

from __future__ import annotations

import fcntl
import os
import pty
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))

import colormath  # noqa: E402
import greet  # noqa: E402
import tokens  # noqa: E402

THEMES = tokens.load_all()
HAS_BRAND = (greet.gen.REPO / "src" / "pose.mjs").exists() and bool(shutil.which("node")) and bool(shutil.which("rsvg-convert"))
FUNCTION = ROOT / "apps/fish/functions/fish_greeting.fish"
BUDGET = 128 * 1024   # bytes a new shell prints


def blob(tid: str) -> bytes:
    return (ROOT / "themes" / tid / greet.OUT).read_bytes()


def rgb255(h: str) -> np.ndarray:
    return np.array([round(v * 255) for v in colormath.rgb(h)], dtype=np.int16)


class Stream(unittest.TestCase):
    def test_placement_keeps_the_cursor_and_never_answers(self):
        for tid in THEMES:
            with self.subTest(tid):
                raw = greet.APC.findall(blob(tid))
                firsts = [greet.keys(k.decode()) for k, _ in raw if set(greet.keys(k.decode())) != {"m"}]
                # q=2 on every command: a reply would arrive in the shell's input as typing
                self.assertTrue(all(k.get("q") == "2" for k in firsts))
                self.assertTrue(all(len(data or b"") <= greet.CHUNK for _, data in raw))
                head = firsts[0]
                self.assertEqual((head["a"], head["c"], head["r"], head["C"]), ("T", str(greet.COLS), str(greet.ROWS), "1"))
                self.assertNotIn("i", head, "an image id would replace an earlier greeting in the same window")

    def test_plays_once_in_about_a_second_and_holds_the_still(self):
        for tid in THEMES:
            with self.subTest(tid):
                _, frames, tail = greet.replay(blob(tid))
                self.assertEqual(tail[-1], f"a=a,I={greet.NUMBER},s=3,v=2,q=2")   # once, then stop on the last frame
                gaps = [g for _, g in frames]
                self.assertTrue(1000 <= sum(gaps[:-1]) <= 1500, sum(gaps[:-1]))
                self.assertGreaterEqual(min(gaps), 16)
                self.assertGreater(len(frames), 40)
                first, last = frames[0][0], frames[-1][0]
                self.assertEqual(last.shape, (greet.H, greet.W, 4))
                self.assertFalse(np.array_equal(first, last))

    def test_small_enough_for_every_shell(self):
        for tid in THEMES:
            with self.subTest(tid):
                self.assertLessEqual(len(blob(tid)), BUDGET)

    def test_patches_only(self):
        """After the first, a frame is sent as the part that moved, not the whole picture."""
        for tid in THEMES:
            with self.subTest(tid):
                cmds = greet.parse(blob(tid))
                sizes = [len(data) for keys, data in cmds[1:] if data and "z=" in keys]
                self.assertLess(np.median(sizes), len(cmds[0][1]) / 2)

    def test_check_tells_stale_from_current(self):
        good = blob("origen")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "peonza.kitty"
            for content, stale in ((good, False), (good[:-300], True), (blob("papel"), True)):
                path.write_bytes(content)
                self.assertEqual(greet.differs(path, good) is not None, stale)

    def test_inks_are_the_themes_and_never_the_signal(self):
        for tid, t in THEMES.items():
            c = t["colors"]
            inks = np.stack([rgb255(c[k]) for k in ("fg0", "fg1", "fg2", "bg0", "line")])
            signal = rgb255(c["signal"])
            with self.subTest(tid):
                for pic, _ in greet.replay(blob(tid))[1]:
                    solid = pic[pic[..., 3] >= 250][:, :3].astype(np.int16)
                    near_ink = np.abs(solid[:, None, :] - inks[None]).max(axis=2).min(axis=1)
                    near_signal = np.abs(solid - signal).max(axis=1)
                    # every solid pixel is an ink or a blend between two (an edge): never
                    # nearer the signal than the inks are
                    self.assertTrue(np.all((near_signal > 24) | (near_ink <= near_signal)))


def run_greeting(env: dict[str, str], cols: int = 100, lines: int = 30, tty: bool = True) -> bytes:
    """fish_greeting's output in a pty of cols x lines (or a pipe), with only `env` set."""
    base = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"), "LANG": "C.UTF-8"}
    script = f"source {FUNCTION}; fish_greeting"
    if not tty:
        r = subprocess.run(["fish", "--no-config", "-c", script], env=base | env, capture_output=True, timeout=30)
        return r.stdout
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", lines, cols, 0, 0))
    p = subprocess.Popen(["fish", "--no-config", "-c", script], env=base | env, stdin=slave, stdout=slave,
                         stderr=slave, close_fds=True)
    os.close(slave)
    out = b""
    try:
        while True:
            ready, _, _ = select.select([master], [], [], 30)
            if not ready:
                break
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
    finally:
        os.close(master)
        p.wait(timeout=30)
    return out


@unittest.skipUnless(shutil.which("fish"), "no fish")
class Fish(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.state.mkdir()
        (self.state / "current").symlink_to(ROOT / "themes" / "origen")
        # A clock fixed at 15:xx on a Sunday, 15 November.
        self.bin = Path(tmp.name) / "bin"
        self.bin.mkdir()
        (self.bin / "date").write_text("#!/bin/sh\necho '15 7 15 11'\n")
        (self.bin / "date").chmod(0o755)
        self.kitty = {"TERM": "xterm-kitty", "KITTY_WINDOW_ID": "1", "RYCE_THEME_STATE": str(self.state),
                      "PATH": f"{self.bin}:{os.environ['PATH']}"}

    def test_parses(self):
        r = subprocess.run(["fish", "--no-execute", str(FUNCTION)], capture_output=True, text=True, timeout=30)
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_greets_in_a_local_kitty(self):
        out = run_greeting(self.kitty)
        self.assertIn(blob("origen"), out)
        text = out.decode("utf-8", "replace")
        self.assertIn("buenas tardes", text)
        self.assertIn("domingo 15 de noviembre", text)
        self.assertTrue(text.startswith("\r\n" * 4 + "\x1b[4A"), "room is made before the picture")

    def test_at_forty_columns_the_longest_date_fits(self):
        (self.bin / "date").write_text("#!/bin/sh\necho '9 3 30 9'\n")
        out = run_greeting(self.kitty, cols=40).decode("utf-8", "replace")
        self.assertIn("buenos días", out)
        self.assertIn("miércoles 30 de septiembre", out)
        self.assertLessEqual(13 + len("miércoles 30 de septiembre"), 40)

    def test_silent_everywhere_else(self):
        cases = {
            "another terminal": ({**self.kitty, "TERM": "xterm-256color"}, {}),
            "kitty's TERM without kitty": ({k: v for k, v in self.kitty.items() if k != "KITTY_WINDOW_ID"}, {}),
            "ssh": ({**self.kitty, "SSH_TTY": "/dev/pts/9"}, {}),
            "ssh without a tty": ({**self.kitty, "SSH_CONNECTION": "10.0.0.1 1 10.0.0.2 22"}, {}),
            "tmux": ({**self.kitty, "TMUX": "/tmp/tmux-1000/default,1,0"}, {}),
            "switched off": ({**self.kitty, "ryce_greet": "off"}, {}),
            "the console": ({**self.kitty, "TERM": "linux"}, {}),
            "narrow": (self.kitty, {"cols": 39}),
            "short": (self.kitty, {"lines": 11}),
            "not a terminal": (self.kitty, {"tty": False}),
            "no theme state": ({**self.kitty, "RYCE_THEME_STATE": str(self.state / "missing")}, {}),
        }
        for name, (env, size) in cases.items():
            with self.subTest(name):
                self.assertEqual(run_greeting(env, **size), b"")


@unittest.skipUnless(HAS_BRAND, "no logo-peonza repo, node or rsvg-convert")
class Committed(unittest.TestCase):
    def test_outputs_are_current(self):
        r = subprocess.run([sys.executable, str(HERE / "greet.py"), "--check"], capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
