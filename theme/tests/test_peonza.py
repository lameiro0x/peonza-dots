"""The peonza: the glyph font's charset and family, and the raster assets per theme —
sizes and frame counts from contracts/constants.json, ink in fg0 with bg0 lines, the
signal in the wobble sheet and nowhere else, and deterministic generators.

    python3 -m unittest discover -s theme/tests -p 'test_peonza.py' -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "theme" / "peonza"))
sys.path.insert(0, str(ROOT / "tools"))

import colormath  # noqa: E402
import gen  # noqa: E402
import glyph  # noqa: E402
import tokens  # noqa: E402

THEMES = tokens.load_all()
C = tokens.constants()
SPEC = C["peonza_assets"]
HAS_BRAND = (gen.REPO / "src" / "pose.mjs").exists()


def rgba(tid: str, rel: str) -> np.ndarray:
    with Image.open(ROOT / "themes" / tid / rel) as im:
        return np.asarray(im.convert("RGBA"), dtype=np.int16)


def dims(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size


def rgb255(h: str) -> np.ndarray:
    return np.array([round(v * 255) for v in colormath.rgb(h)])


def plymouth(tid: str) -> list[str]:
    return [SPEC["plymouth"] % i for i in range(SPEC["plymouth_frames"])]


def assets(tid: str) -> list[str]:
    return [SPEC["still"], SPEC["spin"], SPEC["wobble"], SPEC["logo"], *plymouth(tid)]


class Font(unittest.TestCase):
    def setUp(self):
        from fontTools.ttLib import TTFont
        self.font = TTFont(glyph.OUT)

    def bounds(self, cp: int) -> tuple[float, float, float, float]:
        from fontTools.pens.boundsPen import BoundsPen
        gs = self.font.getGlyphSet()
        pen = BoundsPen(gs)
        gs[self.font.getBestCmap()[cp]].draw(pen)
        return pen.bounds

    def test_charset_is_the_built_glyphs(self):
        cmap = set(self.font.getBestCmap())
        self.assertEqual(cmap, {cp for cp, *_ in glyph.GLYPHS})
        registered = {int(v[2:], 16) for v in C["glyph"]["codepoints"].values()}
        self.assertLessEqual(registered, cmap, "constants.json names a code point the font lacks")
        self.assertIn(int(C["glyph"]["codepoint"][2:], 16), cmap)

    def test_prompt_cut_fits_three_cells(self):
        # kitty 0.49 drops every pixel column left of the pen and cuts the bottom
        # of ink taller than the cell; it gives a PUA symbol followed by spaces as
        # many cells as its ink is wide. So the prompt's cut keeps its ink inside a
        # three-cell advance (JetBrainsMono cells are 600 units), wider than two
        # cells at any size so kitty grants the third, and inside the cell's height
        # with modify_font cell_height 112% (about -379..1099), clear of both rows.
        bar = self.bounds(0x100000)
        x0, y0, x1, y1 = self.bounds(glyph.PROMPT)
        self.assertEqual(self.font["hmtx"][self.font.getBestCmap()[glyph.PROMPT]], (1800, round(x0)))
        self.assertGreater(x0, 0, "ink left of the pen: kitty cuts it")
        self.assertLess(x1, 1800, "ink past the advance")
        self.assertAlmostEqual(x0 + x1, 1800, delta=2, msg="off the advance's centre")
        self.assertGreater(x1 - x0, 1250, "two cells' worth or less: kitty would not grant the third")
        self.assertGreaterEqual(y0, -330)
        self.assertLessEqual(y1, 1060)
        self.assertGreater(y1 - y0, 1.4 * (bar[3] - bar[1]), "the prompt cut is the bar's, larger")

    @unittest.skipUnless((glyph.BRAND / "peonza-20.svg").exists(), "no logo-peonza brand")
    def test_build_is_deterministic_and_committed(self):
        a = glyph.build()
        self.assertEqual(a, glyph.build())
        self.assertEqual(a, glyph.OUT.read_bytes())


class Sheets(unittest.TestCase):
    def test_sizes_and_frame_counts(self):
        px, ply = SPEC["sprite_px"], SPEC["plymouth_px"]
        want = {SPEC["still"]: (px, px), SPEC["spin"]: (px * SPEC["spin_frames"], px),
                SPEC["wobble"]: (px * SPEC["wobble_frames"], px), SPEC["logo"]: (gen.LOGO_PX, gen.LOGO_PX)}
        for tid in THEMES:
            for rel, size in want.items():
                with self.subTest(theme=tid, file=rel):
                    self.assertEqual(dims(ROOT / "themes" / tid / rel), size)
            for rel in plymouth(tid):
                self.assertEqual(dims(ROOT / "themes" / tid / rel), (ply, ply), rel)
            self.assertFalse((ROOT / "themes" / tid / (SPEC["plymouth"] % SPEC["plymouth_frames"])).exists())

    def test_every_frame_is_drawn_and_moves(self):
        px = SPEC["sprite_px"]
        for tid in THEMES:
            for rel, n in ((SPEC["spin"], SPEC["spin_frames"]), (SPEC["wobble"], SPEC["wobble_frames"])):
                a = rgba(tid, rel)[..., 3]
                frames = [a[:, i * px:(i + 1) * px] for i in range(n)]
                with self.subTest(theme=tid, file=rel):
                    self.assertTrue(all((f > 128).sum() > 0.15 * px * px for f in frames))
                    self.assertTrue(all(not np.array_equal(f, g) for f, g in zip(frames, frames[1:])))

    def test_transparent_around_the_mark(self):
        for tid in THEMES:
            for rel in (SPEC["still"], SPEC["logo"]):
                a = rgba(tid, rel)[..., 3]
                self.assertEqual(int(a[0].max()) + int(a[:, 0].max()) + int(a[:, -1].max()), 0, f"{tid} {rel}")


class Inks(unittest.TestCase):
    def check_ink(self, px: np.ndarray, fg: str, bg: str, what: str) -> None:
        """Opaque pixels are mostly `fg`, and every one lies between `fg` and `bg`."""
        solid = px[px[..., 3] == 255][:, :3]
        f, b = rgb255(fg), rgb255(bg)
        near_fg = (np.abs(solid - f).max(axis=1) <= 2).mean()
        self.assertGreater(near_fg, 0.6, f"{what}: only {near_fg:.0%} of opaque pixels are {fg}")
        seg = f - b
        t = np.clip(((solid - b) @ seg) / (seg @ seg), 0, 1)
        off = np.sqrt(((solid - (b + t[:, None] * seg)) ** 2).sum(axis=1)).max()
        self.assertLessEqual(off, 6, f"{what}: a pixel is {off:.1f} off the {fg}..{bg} line")

    def test_ink_is_fg0_with_bg0_lines(self):
        for tid, t in THEMES.items():
            for rel in assets(tid):
                if rel == SPEC["wobble"]:
                    continue
                with self.subTest(theme=tid, file=rel):
                    self.check_ink(rgba(tid, rel), t["colors"]["fg0"], t["colors"]["bg0"], f"{tid} {rel}")

    def test_wobble_is_the_signal(self):
        for tid, t in THEMES.items():
            with self.subTest(theme=tid):
                self.check_ink(rgba(tid, SPEC["wobble"]), t["colors"]["signal"], t["colors"]["bg0"], f"{tid} wobble")

    def test_signal_nowhere_else(self):
        for tid, t in THEMES.items():
            sig = rgb255(t["colors"]["signal"])
            for rel in assets(tid):
                if rel == SPEC["wobble"]:
                    continue
                px = rgba(tid, rel)
                seen = px[px[..., 3] > 128][:, :3]
                d = np.sqrt(((seen - sig) ** 2).sum(axis=1)).min()
                self.assertGreater(d, 40, f"{tid} {rel}: a pixel is {d:.0f} from the signal")


@unittest.skipUnless(HAS_BRAND, "no logo-peonza repo")
class Generator(unittest.TestCase):
    def test_deterministic(self):
        a, b = gen.outputs("grafito"), gen.outputs("grafito")
        self.assertEqual([p for p, _ in a], [p for p, _ in b])
        for (p, x), (_, y) in zip(a, b):
            self.assertTrue(np.array_equal(np.asarray(x), np.asarray(y)), p.name)

    def test_unknown_motion_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            gen.svgs([{"key": "x", "motion": "dance", "frames": 1, "opsz": 32, "ink": {"fg": "#ffffff", "bg": "#000000"}}])
        self.assertIn("unknown motion", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
