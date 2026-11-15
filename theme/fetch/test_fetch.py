"""The fetch peonza (theme/fetch/fetch.py) and the configs that show it: fastfetch's
animated WebP spins readably in fg0 and bg0 and never in the signal, at one frame per
60 Hz refresh, the half-block peonza keeps to the Linux console's glyphs and neofetch's
to sextants, fastfetch runs its rendered config with it and every line fits 88 columns
beside the logo, each theme's neofetch config parses as bash, and each dripfetch
config is one dripfetch accepts.

    python3 -m unittest discover -s theme/fetch -v

The dripfetch test needs dripfetch installed (AUR), neofetch's run needs neofetch
(AUR), the wrappers' need fish.
"""

from __future__ import annotations

import base64
import fcntl
import importlib.util
import json
import os
import re
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unicodedata
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))

import colormath  # noqa: E402
import fetch  # noqa: E402
import tokens  # noqa: E402

THEMES = tokens.load_all()
HAS_BRAND = (fetch.gen.REPO / "src" / "pose.mjs").exists() and bool(shutil.which("node")) and bool(shutil.which("rsvg-convert"))
INFO_ROWS = 21   # the lines print_info writes (theme/templates/neofetch/config.conf)
COLOUR = re.compile(r'"(#[0-9a-f]{6}(?:[0-9a-f]{2})?)"')


def out(tid: str, rel: str) -> Path:
    return ROOT / "themes" / tid / rel


def rgb255(h: str) -> np.ndarray:
    return np.array([round(v * 255) for v in colormath.rgb(h)])


def rows(tid: str) -> list[str]:
    text = out(tid, fetch.TXT).read_text(encoding="utf-8")
    return text.removeprefix("$1").rstrip("\n").split("\n")


def neo_conf(tid: str, name: str) -> int:
    """A number the theme's neofetch config sets (`gap=5`)."""
    text = out(tid, "neofetch/config.conf").read_text(encoding="utf-8")
    return int(re.search(rf"(?m)^{name}=(\d+)", text).group(1))


def run_neofetch(tid: str, cols: int, term: str = "xterm-kitty") -> str:
    """Everything neofetch writes with a theme's config on a pty `cols` wide whose terminal
    answers kitty's cell-size query (CSI 16t) with fetch.CELL."""
    with tempfile.TemporaryDirectory() as state:
        os.symlink(ROOT / "themes" / tid, Path(state) / "current")
        master, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, cols, 0, 0))
        env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "SSH_TTY")} | {"TERM": term, "RYCE_THEME_STATE": state}
        p = subprocess.Popen(["neofetch", "--config", str(out(tid, "neofetch/config.conf"))],
                             stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
        os.close(slave)
        buf, asked, deadline = b"", False, time.monotonic() + 60
        try:
            while time.monotonic() < deadline:
                if not select.select([master], [], [], 0.5)[0]:
                    continue
                try:
                    chunk = os.read(master, 1 << 16)
                except OSError:   # EIO: neofetch exited and the pty closed
                    break
                if not chunk:
                    break
                buf += chunk
                if not asked and b"\x1b[16t" in buf:
                    os.write(master, b"\x1b[6;%d;%dt" % (fetch.CELL[1], fetch.CELL[0]))
                    asked = True
        finally:
            os.close(master)
            p.kill() if p.poll() is None else None
            p.wait(timeout=10)
    return buf.decode("utf-8", "replace")


def drip_rows(tid: str) -> list[str]:
    """The peonza's rows in a dripfetch config: the quoted list items of half blocks."""
    return re.findall(r'(?m)^ +- "([ ▀▄█]+)"$', out(tid, fetch.DRIP).read_text(encoding="utf-8"))


class Spin(unittest.TestCase):
    def setUp(self):
        self.webp = {tid: fetch.decoded(out(tid, fetch.WEBP)) for tid in THEMES}

    def test_one_period_looping_a_frame_per_refresh(self):
        # think's 1.2 s over the frames, one per 60 Hz refresh: kitty times each frame
        # from when it showed the last, so the gap is at most a refresh (16.7 ms).
        self.assertLessEqual(fetch.GAP, 1000 / 60)
        self.assertAlmostEqual(fetch.FRAMES * 1000 / 60, 1200, delta=1)
        for tid, got in self.webp.items():
            self.assertIsNotNone(got, tid)
            frames, durations, loop = got
            self.assertEqual(len(frames), fetch.FRAMES, tid)
            self.assertEqual({f.shape for f in frames}, {(fetch.PX, fetch.PX, 4)}, tid)
            self.assertEqual((loop, set(durations)), (0, {fetch.GAP}), tid)

    def test_the_spin_reads(self):
        # An axisymmetric top turning about its axis would give the same picture every
        # frame. The seams have to move across the body (ink changes where both frames
        # are opaque), and the precession moves the outline.
        for tid, (frames, _, _) in self.webp.items():
            for i, (a, b) in enumerate(zip(frames, frames[1:] + frames[:1])):
                both = (a[..., 3] == 255) & (b[..., 3] == 255)
                seam = (np.abs(a[..., :3] - b[..., :3]).max(axis=2) > 64) & both
                outline = (a[..., 3] > 128) != (b[..., 3] > 128)
                with self.subTest(theme=tid, frame=i):
                    self.assertGreater(seam.sum(), 200, "no groove moved across the body")
                    self.assertGreater(outline.sum(), 200, "the outline stood still")

    def test_ink_is_fg0_with_bg0_grooves_and_never_the_signal(self):
        for tid, (frames, _, _) in self.webp.items():
            c = THEMES[tid]["colors"]
            fg, bg, sig = rgb255(c["fg0"]), rgb255(c["bg0"]), rgb255(c["signal"])
            px = np.concatenate([f.reshape(-1, 4) for f in frames])
            solid = px[px[:, 3] == 255][:, :3]
            self.assertGreater((np.abs(solid - fg).max(axis=1) <= 2).mean(), 0.6, tid)
            seg = fg - bg
            t = np.clip(((solid - bg) @ seg) / (seg @ seg), 0, 1)
            self.assertLessEqual(np.sqrt(((solid - (bg + t[:, None] * seg)) ** 2).sum(axis=1)).max(), 6, tid)
            seen = px[px[:, 3] > 128][:, :3]
            self.assertGreater(np.sqrt(((seen - sig) ** 2).sum(axis=1)).min(), 40, f"{tid}: a pixel near the signal")

    def test_transparent_around(self):
        for tid, (frames, _, _) in self.webp.items():
            for f in frames:
                a = f[..., 3]
                self.assertEqual(int(a[0].max()) + int(a[-1].max()) + int(a[:, 0].max()) + int(a[:, -1].max()), 0, tid)


class Blocks(unittest.TestCase):
    def test_console_glyphs_one_ink_and_one_shape_for_every_theme(self):
        first = rows(next(iter(THEMES)))
        for tid in THEMES:
            text = out(tid, fetch.TXT).read_text(encoding="utf-8")
            self.assertTrue(text.startswith("$1") and "$" not in text[2:], tid)
            self.assertEqual(rows(tid), first, tid)
        self.assertLessEqual(set("".join(first)), set(" ▀▄█"), "a glyph the console font lacks")
        self.assertLessEqual(max(map(len, first)), fetch.TEXT_PX)
        self.assertLessEqual(len(first), fetch.TEXT_PX // 2)
        self.assertGreater(sum(r.count("█") for r in first), 100, "too little ink to read as the top")
        self.assertTrue(first[0].strip() and first[-1].strip(), "blank rows left untrimmed")

    @unittest.skipUnless(HAS_BRAND, "no logo-peonza repo, node or rsvg-convert")
    def test_deterministic(self):
        self.assertEqual(fetch.blocks(), fetch.blocks())
        frames = fetch.spin(THEMES["grafito"])[:3]
        self.assertEqual(fetch.webp(frames), fetch.webp(frames))


class Fastfetch(unittest.TestCase):
    def config(self, tid: str) -> dict:
        return json.loads(re.sub(r"(?m)^\s*//.*$", "", out(tid, "fastfetch/config.jsonc").read_text(encoding="utf-8")))

    def test_logo_is_the_spinning_peonza(self):
        for tid in THEMES:
            logo = self.config(tid)["logo"]
            self.assertEqual((logo["type"], logo["animationFrame"]), ("kitty", 0), tid)
            self.assertEqual(logo["source"], f"~/.local/state/ryce/theme/current/{fetch.WEBP}")
            # A square at kitty's 10 x 26 px cell, never scaled up.
            w, h = logo["width"] * 10, logo["height"] * 26
            self.assertLess(abs(w - h) / h, 0.02, tid)
            self.assertGreaterEqual(fetch.PX / w, 1.5)
            self.assertEqual(logo["color"]["1"], THEMES[tid]["colors"]["fg0"])
            self.assertTrue(self.config(tid)["display"]["disableLinewrap"], tid)

    @unittest.skipUnless(shutil.which("fastfetch"), "no fastfetch")
    def test_runs_with_the_text_peonza(self):
        for tid in THEMES:
            r = subprocess.run(["fastfetch", "-c", str(out(tid, "fastfetch/config.jsonc")), "--pipe",
                                "--logo-type", "file", "--logo", str(out(tid, fetch.TXT))],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual((r.returncode, r.stderr.strip()), (0, ""), f"{tid}: {r.stderr}")
            for word in ("sistema", "escritorio", "máquina", THEMES[tid]["name"]):
                self.assertIn(word, r.stdout, tid)
            self.assertIn(rows(tid)[6].rstrip(), r.stdout, f"{tid}: the peonza is not drawn")

    @unittest.skipUnless(shutil.which("fastfetch"), "no fastfetch")
    def test_fits_88_columns_beside_the_logo(self):
        # Half a 1920 px kitty: printed there, or printed wider and then split, no line
        # reaches past the edge for kitty to wrap under the peonza. This machine's values,
        # and the widest the config allows for: two screens with their refresh rates.
        logo = self.config("origen")["logo"]
        beside = logo["width"] + logo["padding"]["left"] + logo["padding"]["right"]
        r = subprocess.run(["fastfetch", "-c", str(out("origen", "fastfetch/config.jsonc")), "--pipe", "--logo-type", "none"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        key = self.config("origen")["display"]["key"]["width"]
        values = [line.split("\x1b[", 1)[1].split("G", 1)[1] for line in r.stdout.splitlines() if "\x1b[" in line]
        values.append("1920x1080 @ 144 Hz, 1920x1080 @ 72 Hz")
        for v in values:
            self.assertLessEqual(beside + key + len(v), 88, repr(v))


class Neofetch(unittest.TestCase):
    def test_sextant_code_points(self):
        # Bit i is sextant cell i + 1 (1 2 / 3 4 / 5 6), as Unicode names them.
        for bits in range(1, 63):
            if bits in (21, 42):
                continue
            cells = "".join(str(i + 1) for i in range(6) if bits >> i & 1)
            self.assertEqual(unicodedata.name(fetch.sextant(bits)), f"BLOCK SEXTANT-{cells}")
        self.assertEqual([fetch.sextant(b) for b in (0, 21, 42, 63)], [" ", "▌", "▐", "█"])

    def test_one_peonza_in_sextants_and_fg0(self):
        glyphs = set(" ▌▐█") | {chr(c) for c in range(0x1FB00, 0x1FB3C)}
        first = out("origen", fetch.NEO).read_text(encoding="utf-8")
        for tid in THEMES:
            text = out(tid, fetch.NEO).read_text(encoding="utf-8")
            self.assertEqual(text, first, f"{tid}: another shape")
            self.assertTrue(text.startswith("${c1}") and text.count("$") == 1, tid)
            art = text.removeprefix("${c1}").rstrip("\n").split("\n")
            self.assertLessEqual(set("".join(art)), glyphs)
            self.assertLessEqual(len(art), fetch.NEO_PX // 3)
            # Outside kitty the art, the gap and the text fit 82 columns, as they always did.
            self.assertLessEqual(max(map(len, art)) + neo_conf(tid, "gap") + neo_conf(tid, "ryce_text_cols"), 82)
            conf = out(tid, "neofetch/config.conf").read_text(encoding="utf-8")
            self.assertNotIn("{{", conf, tid)
            self.assertIn(f"ascii_colors=('{THEMES[tid]['colors']['fg0']}')", conf, tid)
            signal = {THEMES[tid]["colors"][k] for k in ("signal", "signal_dim", "signal_on_pill")}
            self.assertFalse(signal & set(re.findall(r"#[0-9a-f]{6}", conf)), f"{tid}: the signal in neofetch")

    def test_picture_is_whole_cells_of_fg0_and_fits_half_a_kitty(self):
        w, h = fetch.CELL
        first = None
        for tid in THEMES:
            with Image.open(out(tid, fetch.NEO_PNG)) as im:
                self.assertEqual(im.mode, "RGBA", tid)
                px = np.asarray(im, dtype=np.int16)
            self.assertEqual((px.shape[0], px.shape[1] % w), (fetch.NEO_ROWS * h, 0), f"{tid}: not whole cells")
            a = px[..., 3]
            self.assertEqual(int(a[0].max()) + int(a[-1].max()) + int(a[:, 0].max()) + int(a[:, -1].max()), 0, tid)
            ys, xs = np.nonzero(a)
            # Centred on its box, to the pixel, and filling most of its height.
            self.assertLessEqual(abs(ys.min() - (px.shape[0] - 1 - ys.max())), 1, tid)
            self.assertLessEqual(abs(xs.min() - (px.shape[1] - 1 - xs.max())), 1, tid)
            self.assertGreater((ys.max() - ys.min()) / px.shape[0], 0.85, tid)
            c = THEMES[tid]["colors"]
            solid = px[a == 255][:, :3]
            self.assertGreater((np.abs(solid - rgb255(c["fg0"])).max(axis=1) <= 2).mean(), 0.6, tid)
            self.assertGreater((np.abs(solid - rgb255(c["bg0"])).max(axis=1) <= 2).sum(), 500, f"{tid}: no grooves")
            seen = px[a > 128][:, :3]
            self.assertGreater(np.sqrt(((seen - rgb255(c["signal"])) ** 2).sum(axis=1)).min(), 40, f"{tid}: the signal")
            first = a if first is None else first
            self.assertTrue(np.array_equal(a, first), f"{tid}: another shape")
            # Half a 1920 px kitty, 88 columns, as for fastfetch: the picture, the gap and the text fit.
            self.assertLessEqual(px.shape[1] // w + neo_conf(tid, "gap") + neo_conf(tid, "ryce_text_cols"), 88, tid)

    def test_centring_is_whole_cells_beside_the_text(self):
        # print_info writes 21 lines; a picture with as many odd lines centres on them with
        # no pixel offset, so the PNG is drawn exactly 1:1 at kitty's cell.
        self.assertEqual((INFO_ROWS - fetch.NEO_ROWS) % 2, 0)
        h = fetch.NEO_ROWS * fetch.CELL[1]
        script = f'source "$1"; ryce_ch={fetch.CELL[1]} ryce_ph={h}; ryce_place {INFO_ROWS}; echo $top $dy $total'
        r = subprocess.run(["bash", "-c", script, "-", str(out("origen", "neofetch/config.conf"))],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.stdout.split(), [str((INFO_ROWS - fetch.NEO_ROWS) // 2), "0", str(INFO_ROWS)], r.stderr)

    @unittest.skipUnless(shutil.which("neofetch"), "neofetch not installed (AUR)")
    def test_kitty_gets_the_picture_centred_and_1_to_1(self):
        cw, ch = fetch.CELL
        for tid in THEMES:
            got = run_neofetch(tid, 140)
            with Image.open(out(tid, fetch.NEO_PNG)) as im:
                pw, ph = im.size
            gap, art = neo_conf(tid, "gap"), -(-pw // cw)
            # Sent whole, unscaled (no c, r, w or h keys), dy pixels into its first line.
            m = re.search(r"\x1b_Ga=T,f=100,q=2,C=1,Y=(\d+),m=1;", got)
            self.assertIsNotNone(m, f"{tid}: no picture")
            payload = "".join(re.findall(r"\x1b_G(?:a=T[^;]*|m=[01]);([A-Za-z0-9+/=]*)\x1b\\", got))
            self.assertEqual(base64.b64decode(payload), out(tid, fetch.NEO_PNG).read_bytes(), tid)
            # The text beside it, a rule beside each of its lines, and the picture centred on them.
            self.assertIn(f"\x1b[{art + gap}C", got, tid)
            lines = got.count(f"\x1b[{art + gap - 2}G")
            self.assertGreater(lines, 15, tid)
            px = (lines * ch - ph) // 2
            self.assertEqual(int(m.group(1)), px % ch, tid)
            self.assertIn(f"\x1b[{lines - px // ch}A\x1b_G", got, f"{tid}: not centred on {lines} lines")

    @unittest.skipUnless(shutil.which("neofetch"), "neofetch not installed (AUR)")
    def test_falls_back_to_sextants_then_to_no_art(self):
        sext = out("origen", fetch.NEO).read_text(encoding="utf-8").removeprefix("${c1}").split("\n")[3]
        half = rows("origen")[4]
        # One column short of the picture beside the text, then of the sextants.
        with Image.open(out("origen", fetch.NEO_PNG)) as im:
            beside = -(-im.width // fetch.CELL[0]) + neo_conf("origen", "gap") + neo_conf("origen", "ryce_text_cols")
        for cols, term, want in ((beside - 1, "xterm-kitty", sext), (140, "xterm-256color", sext), (140, "linux", half),
                                 (81, "xterm-kitty", None)):
            with self.subTest(cols=cols, term=term):
                got = run_neofetch("origen", cols, term)
                self.assertNotIn("\x1b_G", got)
                self.assertIn("equipo", got)
                if want:
                    self.assertIn(want, got)
                else:
                    self.assertNotIn("│", got)
                    self.assertNotIn(sext, got)

    def test_config_is_bash(self):
        for tid in THEMES:
            r = subprocess.run(["bash", "-n", str(out(tid, "neofetch/config.conf"))], capture_output=True, text=True, timeout=30)
            self.assertEqual((r.returncode, r.stderr), (0, ""), tid)

    @unittest.skipUnless(shutil.which("neofetch"), "neofetch not installed (AUR)")
    def test_neofetch_runs_every_theme(self):
        for tid in THEMES:
            r = subprocess.run(["neofetch", "--config", str(out(tid, "neofetch/config.conf")), "--stdout"],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            for word in ("equipo", "escritorio", "máquina", THEMES[tid]["name"]):
                self.assertIn(word, r.stdout, tid)


class Dripfetch(unittest.TestCase):
    def text(self, tid: str) -> str:
        return out(tid, fetch.DRIP).read_text(encoding="utf-8")

    def test_theme_colours_peonza_and_no_signal(self):
        for tid, t in THEMES.items():
            text = self.text(tid)
            self.assertNotIn("{{", text, tid)
            self.assertNotIn(fetch.MARK, [line.strip() for line in text.splitlines()], tid)
            self.assertIn(f'background: "{t["colors"]["bg0"]}00"', text, "kitty's translucency")
            peonza = drip_rows(tid)
            self.assertEqual(peonza, drip_rows("origen"), f"{tid}: another shape")
            self.assertLessEqual(len(peonza), fetch.DRIP_PX // 2, tid)
            self.assertLessEqual(max(map(len, peonza)), round(fetch.DRIP_PX * fetch.DRIP_STRETCH), tid)
            self.assertGreater(sum(r.count("█") for r in peonza), 150, tid)
            colours = set(COLOUR.findall(text))
            self.assertIn(t["colors"]["fg0"], colours)
            signal = {t["colors"][k] for k in ("signal", "signal_dim", "signal_on_pill")}
            self.assertFalse({c[:7] for c in colours} & signal, f"{tid}: the signal in dripfetch")
            weights = [float(w) for w in re.findall(r"- \[([0-9.]+), \"#", text)]
            self.assertAlmostEqual(sum(weights), 1.0, places=3)

    @unittest.skipUnless(importlib.util.find_spec("dripfetch"), "dripfetch not installed (AUR)")
    def test_dripfetch_accepts_every_theme(self):
        from dripfetch.app.config import load_config
        for tid in THEMES:
            cfg = load_config(out(tid, fetch.DRIP))
            peonza = cfg["boxes"]["items"][0]
            self.assertEqual(list(peonza["text"]), drip_rows(tid), tid)

    @unittest.skipUnless(shutil.which("fish"), "no fish")
    def test_wrappers_parse(self):
        for name in ("dripfetch", "fastfetch", "neofetch", "fish_greeting"):
            r = subprocess.run(["fish", "--no-execute", str(ROOT / f"apps/fish/functions/{name}.fish")],
                               capture_output=True, text=True, timeout=30)
            self.assertEqual((r.returncode, r.stderr), (0, ""), name)


@unittest.skipUnless(HAS_BRAND, "no logo-peonza repo, node or rsvg-convert")
class Committed(unittest.TestCase):
    def test_outputs_are_current(self):
        self.assertEqual(subprocess.run([sys.executable, str(HERE / "fetch.py"), "--check"], capture_output=True,
                                        text=True, timeout=300).returncode, 0, "run python3 theme/fetch/fetch.py")


if __name__ == "__main__":
    unittest.main()
