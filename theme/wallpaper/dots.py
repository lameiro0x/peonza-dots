#!/usr/bin/env python3
"""Grafito's other two plates: the main one's dot matrix, carrying something else.

    python3 theme/wallpaper/dots.py            write assets/wallpapers/grafito-{ondas,relieve}.jpg
    python3 theme/wallpaper/dots.py --check    exit 1 if a master is stale
    python3 theme/wallpaper/dots.py --only grafito-ondas --out DIR   one, elsewhere

The same plate as scenes.py's grafito scene (72 rows of round dots on black, a dot's
size is its value, greys only, the rows under the bar at the floor), so the three read
as one set:
  ondas    two point sources of ripples a little apart, their interference drawn in
           dot sizes: rings that cross into a moiré, fading out from the middle right.
  relieve  a contour map of a seeded relief: dots grow on the contour lines, every fifth
           (the index contour) inked lighter, the rest of the ground at the floor.

Masters at 2560x1440 (Grafito's wallpaper.alternates); scenes.py derives the sizes, the
thumbs and the picker's previews. Deterministic: seeded noise, no wall-clock input;
--check compares decoded pixels with scenes.py's tolerance.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenes import ROOT, ROWS, differs, dots, fbm, hexrgb, mix, save, smoothstep  # noqa: E402

import tokens  # noqa: E402  (tools/, on the path scenes.py set up)

W, H = 2560, 1440
COLS = round(W / (H / ROWS))
FLOOR = 0.10                                           # the main plate's floor and bar rows
QUIET = round(0.08 * ROWS)                             # rows under the bar, as on the main plate


def cells() -> tuple[np.ndarray, np.ndarray]:
    """Cell centres, x and y in 0..1 of the plate's height (square cells)."""
    jx = (np.arange(COLS) + 0.5) / ROWS
    jy = (np.arange(ROWS) + 0.5) / ROWS
    return np.broadcast_to(jx[None, :], (ROWS, COLS)), np.broadcast_to(jy[:, None], (ROWS, COLS))


def envelope(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The main plate's slow falloff, centred where its peonza sits."""
    aspect = COLS / ROWS
    return np.exp(-(((x / aspect - 0.64) / 0.62) ** 2 + ((y - 0.56) / 0.62) ** 2))


def ondas() -> tuple[np.ndarray, np.ndarray]:
    x, y = cells()
    a, b = np.array([1.12, 0.50]), np.array([1.30, 0.66])   # the two sources, in heights
    r1, r2 = np.hypot(x - a[0], y - a[1]), np.hypot(x - b[0], y - b[1])
    k = 2 * np.pi / 0.085                                  # ripple wavelength: ~6 rows
    wave = (np.cos(k * r1) + np.cos(k * r2 + 0.8)) / 2      # -1..1, the interference
    damp = np.exp(-np.minimum(r1, r2) / 0.9)
    v = FLOOR + 0.8 * smoothstep(0.05, 0.95, (wave + 1) / 2) * (0.35 + 0.65 * damp) * envelope(x, y) ** 0.45
    # Lit dots in about #5a, the crests a step lighter.
    return v, 0.8 * smoothstep(0.12, 0.45, v) + 0.2 * smoothstep(0.45, 0.85, v)


def relieve() -> tuple[np.ndarray, np.ndarray]:
    x, y = cells()
    terrain = fbm(COLS, ROWS, 48, 48, 3, seed=17)
    terrain = terrain + 0.55 * envelope(x, y)              # one massif where the eye rests
    levels = terrain * 18
    # Distance to the nearest contour in cells (the level's offset over its slope), so
    # a line stays one dot wide on steep and gentle ground alike.
    gy, gx = np.gradient(levels)
    near = np.abs(levels - np.round(levels)) / np.maximum(np.hypot(gx, gy), 1e-3)
    index = (np.round(levels) % 5 == 0)
    line = 1 - smoothstep(0.35, 0.7, near)
    v = FLOOR + line * (0.48 + 0.3 * index) * (0.4 + 0.6 * envelope(x, y) ** 1.4)
    return v, line * (0.8 + 0.2 * index)              # contours about #5a, index ones lighter


PLATES = {"assets/wallpapers/grafito-ondas.jpg": ondas, "assets/wallpapers/grafito-relieve.jpg": relieve}


def render(source: str):
    c = {k: hexrgb(v) for k, v in tokens.load("grafito")["colors"].items()}
    v, light = PLATES[source]()
    v = v.copy()
    v[:QUIET] = FLOOR
    light = light.copy()
    light[:QUIET] = 0
    ink = mix(np.broadcast_to(c["line"], (ROWS, COLS, 3)), c["fg1"] * 0.62, light)
    return dots(W, H, np.clip(v, 0, 1), ink, c["bg0"])


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a master is stale")
    ap.add_argument("--only", choices=[Path(s).stem for s in PLATES], help="one plate")
    ap.add_argument("--out", type=Path, help="write into this folder instead of assets/wallpapers/")
    a = ap.parse_args(argv)
    if a.check and (a.only or a.out):
        ap.error("--check takes no --only/--out: it checks everything")
    stale = []
    for source in PLATES:
        if a.only and Path(source).stem != a.only:
            continue
        img = render(source)
        if a.check:
            if why := differs(ROOT / source, img):
                stale.append(f"stale: {source}: {why} (run python3 theme/wallpaper/dots.py)")
            continue
        out = (a.out / Path(source).name) if a.out else ROOT / source
        save(out, img)
        print(f"wrote {out}")
    if a.check:
        print("\n".join(stale) if stale else "dots: ok")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
