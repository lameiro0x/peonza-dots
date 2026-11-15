"""Chromium's new tab pictures: every theme ships both sizes, drawn on the side its column
leaves free, readable under the column, light, deterministic, and none of them is one of
the theme's desk pictures.

    python3 -m unittest discover -s theme/tests -p 'test_newtab.py' -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "theme" / "wallpaper"))
sys.path.insert(0, str(ROOT / "tools"))

import newtab  # noqa: E402
import tokens  # noqa: E402

THEMES = tokens.load_all()
SIZES = {"1920x1080.jpg": (1920, 1080), "2560x1440.jpg": (2560, 1440)}


def shipped(tid: str, name: str = "1920x1080.jpg") -> Path:
    return ROOT / "themes" / tid / "chromium" / "newtab" / name


def small(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB").resize((480, 270), Image.BOX), dtype=np.float64)


class NewTab(unittest.TestCase):
    def test_every_theme_ships_both_sizes(self) -> None:
        self.assertEqual(set(newtab.PICTURES), set(THEMES))
        for tid in THEMES:
            for name, size in SIZES.items():
                with self.subTest(tid=tid, file=name), Image.open(shipped(tid, name)) as im:
                    self.assertEqual(im.size, size)
                    self.assertLessEqual(shipped(tid, name).stat().st_size, newtab.MAX_BYTES)

    def test_the_drawing_sits_on_the_side_the_column_leaves_free(self) -> None:
        for tid, t in THEMES.items():
            with self.subTest(tid=tid):
                a = small(shipped(tid))
                ink = np.abs(a - newtab.hexrgb(t["colors"]["bg0"]) * 255).mean(-1)
                cw = int(newtab.COLUMN * a.shape[1])
                column, far = (ink[:, :cw], ink[:, -cw:]) if newtab.column_left(tid) else (ink[:, -cw:], ink[:, :cw])
                self.assertGreater(far.mean(), 2 * column.mean() + 1)

    def test_fg1_reads_under_the_column_without_the_scrim(self) -> None:
        for tid in THEMES:
            for name in SIZES:
                with self.subTest(tid=tid, file=name), Image.open(shipped(tid, name)) as im:
                    self.assertGreaterEqual(newtab.column_contrast(im, tid), newtab.MIN_CONTRAST)

    def test_no_new_tab_is_a_desk_picture(self) -> None:
        for tid, t in THEMES.items():
            desks = [ROOT / "themes" / tid / "wallpaper" / "1920x1080.jpg"]
            desks += [ROOT / "themes" / tid / "wallpaper" / f"alt-{n}" / "1920x1080.jpg"
                      for n in range(1, len(t["wallpaper"]["alternates"]) + 1)]
            mine = small(shipped(tid))
            for desk in desks:
                with self.subTest(tid=tid, desk=desk.parent.name):
                    # The same picture re-encoded differs by about 1; mostly-bare ones by 7+.
                    self.assertGreater(np.abs(mine - small(desk)).mean(), 4)

    def test_deterministic(self) -> None:
        for tid in ("grafito", "papel"):
            with self.subTest(tid=tid):
                a = np.asarray(newtab.PICTURES[tid](480, 270, True))
                b = np.asarray(newtab.PICTURES[tid](480, 270, True))
                self.assertTrue(np.array_equal(a, b))


if __name__ == "__main__":
    unittest.main()
