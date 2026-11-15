#!/usr/bin/env python3
"""Raster peonza assets per theme, from the brand's own model.

    python3 theme/peonza/gen.py            write themes/<id>/peonza/*.png
    python3 theme/peonza/gen.py --check    exit 1 if any PNG is stale (pixel compare)

What and where come from contracts/constants.json `peonza_assets`:

    still.png          the still logo, one sprite square
    spin.png           the brand's `think` state over one period (1.2 s), a horizontal
                       sheet of `spin_frames`: plays while AI sessions are busy
    wobble.png         the same precession, wider, so the top nods (`wobble_frames`):
                       plays while a session waits for you. The ONE asset in the
                       theme's `signal`; every other asset is in `fg0`
    logo.png           512 px, lock screen and fastfetch
    plymouth-NN.png    `plymouth_frames` spin frames of `plymouth_px`, the boot splash: one
                       per 60 Hz refresh over the 1.2 s period, like desk.png
    desk.png           the `think` state again, 72 frames of 96 px (one per 60 Hz refresh
                       over the 1.2 s period): the desk's spinning peonza
                       (quickshell/ryce/peonza/), drawn for its own size like the logo

Ink is the theme's fg0 (wobble: signal), the engraved lines are filled with bg0, and
around the mark is transparent. Every sheet covers one period at evenly spaced
instants, so it loops: spin at 50 ms a frame, plymouth and desk at one per 60 Hz
refresh play in real time; wobble's 16 frames are 75 ms each.

The sprites are drawn with the optics of a 32 px mark (the brand's loader: disc more
open, lines a full device pixel) and rendered at 64 px, so they stay legible scaled
down to the bar's ~24 px; plymouth and the logo are drawn for their own size.

Pipeline: theme/peonza/frames.mjs imports ~/Repos/logo-peonza/src/{pose,mark}.mjs and
prints the SVGs; each one goes through its own rsvg-convert process (no resvg in Node:
see the logo-peonza fiche on its memory trap); Pillow composes the sheets. --check
compares decoded pixels with a tolerance (max abs channel difference <= 2), so an rsvg
or zlib rebuild cannot flap. Without the brand repo (set PEONZA_BRAND to its
brand/mark/ folder) or without node it skips with a message and exits 0.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import tokens  # noqa: E402

HERE = Path(__file__).resolve().parent
BRAND = Path(os.environ.get("PEONZA_BRAND", Path.home() / "Repos" / "logo-peonza" / "brand" / "mark"))
REPO = BRAND.parents[1]
THEMES_OUT = ROOT / "themes"
SPRITE_OPSZ = 32
LOGO_PX = 512   # fastfetch draws it ~310 px wide; the lock screen at 128 (a clean quarter)
DESK_PX = 96    # quickshell/ryce/peonza/DeskPeonza.qml shows it 1:1
DESK_FRAMES = 72
DESK = "peonza/desk.png"
TOLERANCE = 2
# The brand's rights notice (logo-peonza brand/README.md, «Derechos»): every file carries it.
TEXT = [("Author", "lameiro0x"),
        ("Copyright", "© 2026 lameiro0x. All rights reserved. The peonza mark; for this desktop only.")]


def jobs(t: dict, spec: dict) -> list[dict]:
    """What frames.mjs draws for one theme: (key, motion, frames, opsz, ink)."""
    c = t["colors"]
    ink, alarm = {"fg": c["fg0"], "bg": c["bg0"]}, {"fg": c["signal"], "bg": c["bg0"]}
    return [
        {"key": "still", "motion": "still", "frames": 1, "opsz": SPRITE_OPSZ, "ink": ink},
        {"key": "spin", "motion": "think", "frames": spec["spin_frames"], "opsz": SPRITE_OPSZ, "ink": ink},
        {"key": "wobble", "motion": "wobble", "frames": spec["wobble_frames"], "opsz": SPRITE_OPSZ, "ink": alarm},
        {"key": "logo", "motion": "still", "frames": 1, "opsz": LOGO_PX, "ink": ink},
        {"key": "plymouth", "motion": "think", "frames": spec["plymouth_frames"], "opsz": spec["plymouth_px"], "ink": ink},
        {"key": "desk", "motion": "think", "frames": DESK_FRAMES, "opsz": DESK_PX, "ink": ink},
    ]


def svgs(job_list: list[dict]) -> dict[str, list[str]]:
    r = subprocess.run(["node", str(HERE / "frames.mjs"), str(REPO)], input=json.dumps(job_list),
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise SystemExit(f"gen.py: theme/peonza/frames.mjs failed:\n{r.stderr.strip()}")
    return json.loads(r.stdout)


def raster(svg: str, px: int) -> Image.Image:
    png = subprocess.run(["rsvg-convert", "-w", str(px), "-h", str(px)], input=svg.encode(),
                         check=True, capture_output=True, timeout=60).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")


def sheet(frames: list[Image.Image]) -> Image.Image:
    px = frames[0].width
    out = Image.new("RGBA", (px * len(frames), px), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        out.paste(f, (i * px, 0))
    return out


def outputs(tid: str) -> list[tuple[Path, Image.Image]]:
    spec = tokens.constants()["peonza_assets"]
    drawn = svgs(jobs(tokens.load(tid), spec))
    px = spec["sprite_px"]
    base = THEMES_OUT / tid
    out = [
        (base / spec["still"], raster(drawn["still"][0], px)),
        (base / spec["spin"], sheet([raster(s, px) for s in drawn["spin"]])),
        (base / spec["wobble"], sheet([raster(s, px) for s in drawn["wobble"]])),
        (base / spec["logo"], raster(drawn["logo"][0], LOGO_PX)),
        (base / DESK, sheet([raster(s, DESK_PX) for s in drawn["desk"]])),
    ]
    out += [(base / (spec["plymouth"] % i), raster(s, spec["plymouth_px"])) for i, s in enumerate(drawn["plymouth"])]
    return out


def differs(path: Path, img: Image.Image) -> str | None:
    if not path.exists():
        return "missing"
    with Image.open(path) as im:
        cur = np.asarray(im.convert("RGBA"), dtype=np.int16)
    new = np.asarray(img, dtype=np.int16)
    if cur.shape != new.shape:
        return f"size {cur.shape[1]}x{cur.shape[0]}, expected {new.shape[1]}x{new.shape[0]}"
    worst = int(np.abs(cur - new).max())
    return f"pixels differ by up to {worst}" if worst > TOLERANCE else None


def main(argv: list[str]) -> int:
    check = "--check" in argv
    missing = [what for what, ok in ((f"{REPO}/src/pose.mjs", (REPO / "src" / "pose.mjs").exists()),
                                     ("node", shutil.which("node")),
                                     ("rsvg-convert", shutil.which("rsvg-convert"))) if not ok]
    if missing:
        print(f"peonza: skip (no {', '.join(missing)}; set PEONZA_BRAND to logo-peonza's brand/mark/)")
        return 0
    info = PngInfo()
    for k, v in TEXT:
        info.add_itxt(k, v)
    stale = []
    for tid in tokens.theme_ids():
        for path, img in outputs(tid):
            if check:
                why = differs(path, img)
                if why:
                    stale.append(f"{path.relative_to(ROOT)}: {why}")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                img.save(path, optimize=True, pnginfo=info)
        if not check:
            print(f"wrote themes/{tid}/peonza/")
    if check:
        for line in stale:
            print(f"stale: {line} (run python3 theme/peonza/gen.py)")
        if not stale:
            print("peonza: ok")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
