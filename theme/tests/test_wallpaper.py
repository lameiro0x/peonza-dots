"""Wallpapers: every theme ships its five files at their sizes, a translucent bar stays
legible over its band, the signal colour stays rare, Grafito is greys only, bands.json
matches the pixels, and the scenes are deterministic.

    python3 -m unittest discover -s theme/tests -p 'test_wallpaper.py' -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "theme" / "wallpaper"))
sys.path.insert(0, str(ROOT / "tools"))

import colormath  # noqa: E402
import scenes  # noqa: E402
import tokens  # noqa: E402

THEMES = tokens.load_all()
FILES = {"1920x1080.jpg": (1920, 1080), "2560x1440.jpg": (2560, 1440), "thumb.png": (480, 270),
         "lock.jpg": (1920, 1080), "panel.png": scenes.PANEL}
BANDS = json.loads(scenes.BANDS.read_text(encoding="utf-8"))


def desks(tid: str) -> list[str]:
    """Every desktop picture of a theme: the main one and its alternates, both sizes."""
    alts = [f"alt-{n}/" for n in range(1, len(THEMES[tid]["wallpaper"]["alternates"]) + 1)]
    return [f"{a}{s}.jpg" for a in ["", *alts] for s in ("1920x1080", "2560x1440")]


def pixels(tid: str, name: str) -> np.ndarray:
    with Image.open(ROOT / "themes" / tid / "wallpaper" / name) as im:
        return np.asarray(im.convert("RGB"), dtype=np.int16)


def dims(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size


class Outputs(unittest.TestCase):
    def test_every_theme_has_its_files_at_their_sizes(self):
        for tid in THEMES:
            for name, size in FILES.items():
                with self.subTest(theme=tid, file=name):
                    self.assertEqual(dims(ROOT / "themes" / tid / "wallpaper" / name), size)

    def test_every_alternate_has_both_sizes_and_nothing_is_left_over(self):
        for tid in THEMES:
            with self.subTest(theme=tid):
                for name in desks(tid):
                    w, h = name.rsplit("/", 1)[-1].removesuffix(".jpg").split("x")
                    self.assertEqual(dims(ROOT / "themes" / tid / "wallpaper" / name), (int(w), int(h)))
                self.assertEqual(scenes.orphans(tid), [])

    def test_alternates_are_greys_only(self):
        # Tinta's alternate is ink on charcoal: the amber signal is never in it.
        for tid, t in THEMES.items():
            if t["wallpaper"]["grade"] != "mono":
                continue
            for name in desks(tid)[2:]:
                with self.subTest(theme=tid, file=name):
                    px = pixels(tid, name)
                    self.assertLessEqual(int((px.max(axis=-1) - px.min(axis=-1)).max()), 2)

    def test_old_wallpapers_are_gone(self):
        self.assertFalse(list((ROOT / "assets" / "wallpapers").glob("*.png")))

    def test_a_translucent_bar_stays_legible(self):
        # The floating bar's plates paint bg0 at alpha.bar over the top band: fg1 keeps the text floor on them,
        # over the band's lightest pixel (dark themes) and its darkest (paper: the ink dots).
        for tid, t in THEMES.items():
            a = t["alpha"]["bar"]
            for name in desks(tid):
                with self.subTest(theme=tid, file=name):
                    px = pixels(tid, name)
                    band = px[: round(t["geometry"]["frame_top"] / 1080 * px.shape[0])].reshape(-1, 3)
                    for top in (colormath.to_hex(tuple(band.max(axis=0) / 255)),
                                colormath.to_hex(tuple(band.min(axis=0) / 255))):
                        under = colormath.over(t["colors"]["bg0"], a, top)
                        self.assertGreaterEqual(colormath.contrast(t["colors"]["fg1"], under), 4.5, (top, under))

    def test_signal_stays_rare(self):
        # A photo may hold the signal's hue somewhere; it must never become a field of it.
        for tid, t in THEMES.items():
            sig = np.array([round(v * 255) for v in colormath.rgb(t["colors"]["signal"])])
            for name in ["thumb.png", *desks(tid)]:
                with self.subTest(theme=tid, file=name):
                    d = np.sqrt(((pixels(tid, name) - sig) ** 2).sum(axis=-1))
                    self.assertLess(float((d < 40).mean()), 0.005, "over 0.5 % of the picture is signal-coloured")

    def test_grafito_is_greys_only(self):
        for name in FILES:
            px = pixels("grafito", name)
            self.assertLessEqual(int((px.max(axis=-1) - px.min(axis=-1)).max()), 2, name)  # JPEG rounding

    def test_grafito_desks_stay_under_the_desk_ui_ceiling(self):
        # Grafito's DeskUi sets its light text straight on the plate and assumes no
        # wallpaper of the theme ever gets lighter than #999999 (2026-11-14: they peak at
        # #7c7c7c).
        for name in desks("grafito"):
            with self.subTest(file=name):
                self.assertLess(int(pixels("grafito", name).max()), 0x99, "a Grafito wallpaper peaks at #999999 or over")


class Panel(unittest.TestCase):
    """The launcher's panel: a pale peonza of its own (the user asked for "more white"),
    never the signal. That it is panels.py's drawing and not a crop of the wallpaper is
    scenes.py --check's job."""

    def test_panel_is_pale_and_signal_free(self):
        for tid, t in THEMES.items():
            with self.subTest(theme=tid):
                px = pixels(tid, "panel.png")
                lum = (px / 255.0) @ np.array([0.2126, 0.7152, 0.0722])
                self.assertGreater(float(np.median(lum)), 0.75, "the panel's paper is not pale")
                sig = np.array([round(v * 255) for v in colormath.rgb(t["colors"]["signal"])])
                self.assertEqual(int((np.sqrt(((px - sig) ** 2).sum(axis=-1)) < 40).sum()), 0, "signal in the panel")

    @unittest.skipUnless(all((scenes.BRAND / f).exists() for f in ("peonza.svg", "peonza-silhouette.svg",
                                                                   "peonza-64.svg")), "no logo-peonza brand")
    def test_panels_are_deterministic(self):
        import panels
        for tid in THEMES:
            a, b = (np.asarray(panels.panel(THEMES[tid])) for _ in range(2))
            self.assertTrue(np.array_equal(a, b), tid)


class Bands(unittest.TestCase):
    def test_bands_match_the_pixels(self):
        for tid in THEMES:
            for size in ("1920x1080", "2560x1440"):
                with self.subTest(theme=tid, size=size):
                    with Image.open(ROOT / "themes" / tid / "wallpaper" / f"{size}.jpg") as im:
                        got = scenes.bands(im.convert("RGB"))
                    for k in ("top", "lightest"):
                        self.assertEqual(got[k]["average"], BANDS["themes"][tid][size][k]["average"])

    def test_floor_is_the_lightest_band_of_all(self):
        every = [b["lightest"] for sz in BANDS["themes"].values() for b in sz.values()]
        self.assertEqual(BANDS["floor"]["luminance"], max(b["luminance"] for b in every))
        self.assertEqual(BANDS["band_px"], 60)


class Generator(unittest.TestCase):
    def test_photo_scenes_are_deterministic_and_cover_the_frame(self):
        for tid, t in THEMES.items():
            if t["wallpaper"]["scene"] != "photo":
                continue
            a, b = scenes.photo(480, 270, t), scenes.photo(480, 270, t)
            self.assertEqual(a.size, (480, 270), tid)
            self.assertTrue(np.array_equal(np.asarray(a), np.asarray(b)), tid)

    def test_mono_grade_is_grey(self):
        img = Image.fromarray(np.dstack([np.linspace(0, 255, 64 * 64).reshape(64, 64).astype(np.uint8),
                                         np.zeros((64, 64), np.uint8), np.full((64, 64), 200, np.uint8)]))
        px = np.asarray(scenes.grade(img, "mono"), dtype=np.int16)
        self.assertEqual(int((px.max(axis=-1) - px.min(axis=-1)).max()), 0)
        self.assertIs(scenes.grade(img, "none"), img)

    def test_cover_crops_around_the_focus(self):
        img = Image.fromarray(np.dstack([np.tile(np.arange(400, dtype=np.uint8)[:100], (100, 1))] * 3))  # 100x100 ramp
        left = np.asarray(scenes.cover(img, 160, 90, [0.0, 0.5]))
        right = np.asarray(scenes.cover(img, 160, 90, [1.0, 0.5]))
        self.assertLess(left.mean(), right.mean() + 1)

    @unittest.skipUnless((scenes.BRAND / "peonza-64.svg").exists(), "no logo-peonza brand")
    def test_brand_scenes_are_deterministic(self):
        for scene in scenes.NEEDS_BRAND:
            a, b = (scenes.SCENES[scene](640, 360, THEMES["grafito"]) for _ in range(2))
            self.assertTrue(np.array_equal(np.asarray(a), np.asarray(b)), scene)

    def test_check_tolerates_two_and_flags_three(self):
        base = np.full((4, 4, 3), 100, dtype=np.uint8)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "w.png"
            Image.fromarray(base).save(p)
            self.assertIsNone(scenes.differs(p, Image.fromarray(base + 2)))
            self.assertIn("up to 3", scenes.differs(p, Image.fromarray(base + 3)))
            self.assertIn("size", scenes.differs(p, Image.fromarray(np.zeros((2, 2, 3), dtype=np.uint8))))
            self.assertEqual(scenes.differs(Path(tmp) / "none.png", Image.fromarray(base)), "missing")

    def test_bands_check_flags_a_drift(self):
        drifted = json.loads(json.dumps(BANDS))
        drifted["themes"]["ola"]["1920x1080"]["top"]["average"] = "#ffffff"
        self.assertIsNone(scenes.bands_differ(BANDS, BANDS))
        self.assertIn("ola 1920x1080 top", scenes.bands_differ(drifted, BANDS))


class Paper(unittest.TestCase):
    """Papel's reading room (theme/wallpaper/paper.py): the text, where the spread lies, the
    lock's rows against its hyprlock template, and a budget that can fail."""

    @classmethod
    def setUpClass(cls):
        import paper
        cls.paper = paper

    def test_the_text_opens_the_quijote_in_modern_accents(self):
        text = " ".join(self.paper.QUIJOTE)
        self.assertTrue(text.startswith("En un lugar de la Mancha, de cuyo nombre no quiero acordarme"))
        for old in (" á ", " ó ", "fué", "vió"):                # the 1905 source's accents, modernised
            self.assertNotIn(old, text)

    def test_the_spread_clears_the_bar_and_every_card(self):
        s, m = self.paper.SPREAD, self.paper.CARD_MARGIN
        top = s["head"] - 20                                    # the running heads' capitals
        bottom = s["first"] + (s["lines"] - 1) * s["lead"] + 8  # the last line's descenders
        self.assertGreater(top, self.paper.BAR)
        for page in ("verso", "recto"):
            x0, x1 = s[page]
            for name, (c0, r0, c1, r1) in self.paper.CARDS.items():
                with self.subTest(page=page, card=name):
                    apart = x1 <= c0 - m or x0 >= c1 + m or bottom <= r0 - m or top >= r1 + m
                    self.assertTrue(apart, f"the {page} reaches the {name} card")

    def test_the_lock_template_sits_on_the_pictures_rows(self):
        conf = (ROOT / "theme" / "templates" / "@papel" / "hypr" / "hyprlock.conf").read_text(encoding="utf-8")
        blocks = [b for b in conf.split("\n}") if "position" in b]

        def at(block: str) -> tuple[int, int]:
            x, y = (int(v) for v in block.split("position = ", 1)[1].split("\n", 1)[0].split(","))
            return x, y

        field = next(b for b in blocks if "input-field {" in b)
        w, h = (int(v) for v in field.split("size = ", 1)[1].split("\n", 1)[0].split(","))
        cx, cy = at(field)
        rows = self.paper.LOCK_ROWS
        self.assertEqual((cx, w), (0, rows["field_width"]), "the field is the hairline's width, centred")
        self.assertAlmostEqual(540 - cy + h / 2, rows["field_rule"], delta=2, msg="the field stands on its hairline")
        # The hour and its second line are centred labels inside the picture's quiet band.
        x0, y0, x1, y1 = self.paper.LOCK_QUIET
        for key in ("ryce-hora\"; {", "--parte"):
            block = next(b for b in blocks if key in b)
            with self.subTest(label=key):
                self.assertEqual(at(block)[0], 0)
                self.assertTrue(y0 < 540 - at(block)[1] < y1)

    def test_banding_measure_sees_an_undithered_gradient(self):
        light = np.linspace(30.0, 40.0, 600)
        self.assertGreater(self.paper.band_step(np.round(light), light), 0.95)
        dithered = np.round(light + np.random.default_rng(1).normal(0, 1.1, light.size))
        self.assertLess(self.paper.band_step(dithered, light), self.paper.BUDGET["band_step_max"])

    def test_budget_refuses_ghosts_that_read_and_a_lit_room(self):
        t = THEMES["papel"]
        lamp = self.paper.LAMP["desk"]
        ground = self.paper.baize(192, 108, t, lamp, felt=False)
        mask = Image.new("L", (192, 108), 0)
        mask.paste(255, (80, 60, 120, 70))
        loud = (ground, [(self.paper.palette(t)["vellum"], 0.6, mask)], lamp)
        img = scenes.finish(self.paper.lay(*loud[:2]))
        self.assertTrue(any("ghost letters" in b for b in self.paper.over_budget(img, t, loud)))
        lit = Image.new("RGB", (192, 108), t["colors"]["fg0"])
        self.assertTrue(any("dim room" in b for b in self.paper.over_budget(lit, t)))

    @unittest.skipUnless((scenes.BRAND / "peonza-silhouette.svg").exists(), "no logo-peonza brand")
    def test_masters_are_fresh_and_within_the_budget(self):
        import subprocess
        r = subprocess.run([sys.executable, str(ROOT / "theme" / "wallpaper" / "paper.py"), "--check"],
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
