#!/usr/bin/env python3
"""Every theme's wallpapers, from the theme contracts (contracts/themes/<id>.json).

    python3 theme/wallpaper/scenes.py            write themes/<id>/wallpaper/* + bands.json
    python3 theme/wallpaper/scenes.py --check    exit 1 if any output is stale
    python3 theme/wallpaper/scenes.py --only ola --size 1920x1080 --out /tmp/x
                                                 one theme, one size, elsewhere (for looking)

`wallpaper.scene` picks how a theme's picture is made:

  photo    real art chosen by hand (the user asked for pictures from the internet,
           not generated ones): `wallpaper.source`, a 2560x1440 master in
           assets/wallpapers/ (sources and licences in its README.md), cover-cropped
           around `wallpaper.focus` and graded (`mono` = luminance with a gentle S-curve).
  grafito  a dot-matrix plate: a regular grid of round dots on black whose size
           encodes the peonza (the brand's 64 px drawing, one pixel per dot) over a
           slow radial falloff. The one generated picture the user kept.

Per theme: 1920x1080.jpg and 2560x1440.jpg (awww), thumb.png (480x270, the theme
selector), lock.jpg (hyprlock and the login page: `wallpaper.lock_source`, else the
desktop picture) and panel.png (the launcher's left panel: a pale peonza drawn in the
theme's language by panels.py, never a crop of the wallpaper). Each of
`wallpaper.alternates` (more 2560x1440 masters: photos, or drawn by ink.py and dots.py)
gets the two desktop sizes and a thumb.png (the wallpaper picker) in alt-<n>/, n from 1, cover-cropped around the centre and graded like the theme;
`ryce-theme wall` switches between them, only when asked. The bar floats (2026-11-12): no band is darkened under it any more; its
plates paint bg0 at alpha.bar themselves.

bands.json records, per theme and size, the mean colour of the top 60 px (`top`) and
of the lightest 60 px horizontal band (`lightest`); `floor` is the lightest of all.
Contrast tests composite translucent surfaces over those.

Deterministic: fixed seeds, no wall-clock input. --check compares decoded pixels with
a tolerance (max abs channel difference <= 2), not file bytes, so a zlib or rsvg
rebuild cannot flap. Build-time only (python-numpy, python-pillow, rsvg-convert); the
PNGs are committed and deployed. The peonza scenes and panels read ~/Repos/logo-peonza
(or $PEONZA_BRAND); without it they are skipped with a message, never failed.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import colormath  # noqa: E402
import tokens  # noqa: E402

THEMES_OUT = ROOT / "themes"
BANDS = Path(__file__).resolve().parent / "bands.json"
BRAND = Path(os.environ.get("PEONZA_BRAND", Path.home() / "Repos" / "logo-peonza" / "brand" / "mark"))
SIZES = [(1920, 1080), (2560, 1440)]
THUMB = (480, 270)
BAND_PX = 60
TOLERANCE = 2
# Scenes that draw the brand mark, and the file each one reads.
NEEDS_BRAND = {"grafito": "peonza-64.svg"}
PANEL = (360, 600)
JPEG = {"quality": 92, "subsampling": 0, "optimize": True, "progressive": True}


# ── shared ────────────────────────────────────────────────────────────────────
def hexrgb(h: str) -> np.ndarray:
    return np.array(colormath.rgb(h), dtype=np.float64)


def grid(w: int, h: int) -> tuple[np.ndarray, np.ndarray]:
    """Pixel-centre coordinates, x and y in 0..1 (each over its own axis)."""
    x = (np.arange(w) + 0.5) / w
    y = (np.arange(h) + 0.5) / h
    return np.broadcast_to(x[None, :], (h, w)), np.broadcast_to(y[:, None], (h, w))


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mix(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
    """a..b by t, where a and b are colours or (h, w, 3) images and t is (h, w)."""
    return a + (b - a) * t[..., None]


def value_noise(w: int, h: int, cx: float, cy: float, rng: np.random.Generator) -> np.ndarray:
    """Smooth value noise in 0..1: a random lattice of cx by cy px cells, bicubic."""
    gw, gh = int(w / cx) + 3, int(h / cy) + 3
    lattice = Image.fromarray(rng.random((gh, gw)).astype(np.float32), mode="F")
    a = np.asarray(lattice.resize((int(gw * cx), int(gh * cy)), Image.BICUBIC), dtype=np.float64)
    return np.clip(a[:h, :w], 0.0, 1.0)


def fbm(w: int, h: int, cx: float, cy: float, octaves: int, seed: int, gain: float = 0.5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    total, amp, norm = np.zeros((h, w)), 1.0, 0.0
    for _ in range(octaves):
        total += amp * value_noise(w, h, max(cx, 2.0), max(cy, 2.0), rng)
        norm += amp
        amp *= gain
        cx, cy = cx / 2, cy / 2
    return total / norm


def blur(a: np.ndarray, r: int, passes: int = 2) -> np.ndarray:
    """Near-Gaussian blur of a float array (any trailing channels): repeated box
    filters of radius `r` along both axes, edges clamped."""
    for _ in range(passes):
        for axis in (0, 1):
            pad = [(r + 1, r) if k == axis else (0, 0) for k in range(a.ndim)]
            c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis)
            n = a.shape[axis]
            a = (np.take(c, range(2 * r + 1, 2 * r + 1 + n), axis=axis)
                 - np.take(c, range(0, n), axis=axis)) / (2 * r + 1)
    return a


def grain(w: int, h: int, seed: int, amount: float) -> np.ndarray:
    """Luminance grain; at ~1.5 LSB it also dithers the dark gradients against banding."""
    return np.random.default_rng(seed).normal(0.0, amount, (h, w))[..., None]


def vignette(rgb: np.ndarray, cx: float, cy: float, rx: float, ry: float, depth: float) -> np.ndarray:
    x, y = grid(rgb.shape[1], rgb.shape[0])
    v = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
    return rgb * (1 - depth * smoothstep(0.25, 1.3, v))[..., None]


def mark(file: str, *, height: int | None = None, box: int | None = None) -> np.ndarray:
    """A brand mark as straight RGBA in 0..1, rendered `height` px tall or into a `box` px square."""
    size = ["-h", str(height)] if height else ["-w", str(box), "-h", str(box)]
    png = subprocess.run(["rsvg-convert", *size, str(BRAND / file)],
                         check=True, capture_output=True, timeout=60).stdout
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"), dtype=np.float64) / 255.0


def finish(rgb: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8), mode="RGB")



# ── grafito ───────────────────────────────────────────────────────────────────
ROWS = 72                                    # dots down the screen: 15 px pitch at 1080, 20 at 1440


def grafito(w: int, h: int, t: dict) -> Image.Image:
    c = {k: hexrgb(v) for k, v in t["colors"].items()}
    pitch = h / ROWS
    cols = round(w / pitch)

    # The value each dot carries: the peonza drawn at one pixel per dot, over a slow
    # radial falloff centred on it. Rows under the bar stay at the floor.
    box = 70
    # The drawing's lines are cut through (one ink); a 3 px closing fills them back to
    # the solid silhouette, and the difference is the engraving.
    m = mark(NEEDS_BRAND["grafito"], box=box)[..., 3]
    shut = Image.fromarray(np.round(m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    m = np.dstack([np.asarray(shut, dtype=np.float64) / 255.0, m])
    pad = np.zeros((ROWS + 2 * box, cols + 2 * box, 2))   # the box's empty margin may overhang
    bx, by = round(cols * 0.665) - box // 2, ROWS // 2 + 3 - box // 2
    pad[box + by:box + by + box, box + bx:box + bx + box] = m
    if pad[:box].any() or pad[box + ROWS:].any() or pad[:, :box].any() or pad[:, box + cols:].any():
        raise SystemExit(f"grafito {w}x{h}: the peonza falls off the dot grid")
    field = pad[box:box + ROWS, box:box + cols, 0]
    cut = np.clip(field - pad[box:box + ROWS, box:box + cols, 1], 0, 1)
    jx = (np.arange(cols) + 0.5) / cols
    jy = (np.arange(ROWS) + 0.5) / ROWS
    radial = np.exp(-(((jx[None, :] - 0.64) / 0.62) ** 2 + ((jy[:, None] - 0.56) / 0.62) ** 2))
    floor = 0.10 + 0.20 * radial * smoothstep(0.06, 0.20, jy)[:, None]
    v = np.maximum(field * (1 - 0.5 * cut), floor)
    v[: round(0.08 * ROWS)] = 0.10
    # Ink per dot: the mark in greys lit a little from the upper left, the plate in `line`.
    light = np.clip(1.0 - 0.9 * (jx[None, :] - 0.55) - 0.6 * (jy[:, None] - 0.35), 0.6, 1.0)
    ink_mark = c["fg1"] * 0.55 + (c["fg2"] * 0.85 - c["fg1"] * 0.55) * (1 - light)[..., None]
    ink = mix(np.broadcast_to(c["line"], (ROWS, cols, 3)), ink_mark, smoothstep(0.3, 0.9, field) * (1 - 0.75 * cut))
    return dots(w, h, v, ink, c["bg0"])


def dots(w: int, h: int, v: np.ndarray, ink: np.ndarray, ground: np.ndarray) -> Image.Image:
    """A dot plate: ROWS rows of round dots on `ground`, one per value of `v` (ROWS x
    cols, 0..1: the dot's size) in its colour from `ink` (ROWS x cols x 3)."""
    pitch = h / ROWS
    cols = v.shape[1]
    # Every pixel belongs to one cell; a dot is a disc of radius r(v) at the cell's
    # centre, anti-aliased by its signed distance.
    px = (np.arange(w) + 0.5) / pitch
    py = (np.arange(h) + 0.5) / pitch
    ix = np.minimum(px.astype(int), cols - 1)
    iy = np.minimum(py.astype(int), ROWS - 1)
    dx = (px - ix - 0.5) * pitch
    dy = (py - iy - 0.5) * pitch
    d = np.sqrt(dx[None, :] ** 2 + dy[:, None] ** 2)
    r = pitch * 0.40 * (0.18 + 0.82 * v ** 1.3)
    cov = np.clip(r[iy][:, ix] - d + 0.5, 0.0, 1.0)
    rgb = ground + (ink[iy][:, ix] - ground) * cov[..., None]
    return finish(rgb)


# ── photo ─────────────────────────────────────────────────────────────────────
def cover(img: Image.Image, w: int, h: int, focus: list[float]) -> Image.Image:
    """Crop `img` to w:h around focus (fractions of the free margin), then resize."""
    iw, ih = img.size
    if iw / ih > w / h:
        cw, ch = round(ih * w / h), ih
    else:
        cw, ch = iw, round(iw * h / w)
    x, y = round((iw - cw) * focus[0]), round((ih - ch) * focus[1])
    return img.crop((x, y, x + cw, y + ch)).resize((w, h), Image.LANCZOS)


def grade(img: Image.Image, kind: str) -> Image.Image:
    if kind != "mono":
        return img
    a = np.asarray(img.convert("L"), dtype=np.float64) / 255.0
    a = a + 0.18 * (smoothstep(0.0, 1.0, a) - a)          # a gentle S-curve: inkier blacks
    a = np.clip(a, 0, 1)
    return finish(np.repeat(a[..., None], 3, axis=2))


def photo(w: int, h: int, t: dict) -> Image.Image:
    wp = t["wallpaper"]
    with Image.open(ROOT / wp["source"]) as src:
        img = grade(cover(src.convert("RGB"), w, h, wp["focus"]), wp["grade"])
    return img


def lock(t: dict, desk: Image.Image) -> Image.Image:
    wp = t["wallpaper"]
    if not wp["lock_source"]:
        return desk.resize(SIZES[0], Image.LANCZOS) if desk.size != SIZES[0] else desk
    with Image.open(ROOT / wp["lock_source"]) as src:
        return grade(cover(src.convert("RGB"), *SIZES[0], [0.5, 0.5]), wp["grade"])


SCENES = {"photo": photo, "grafito": grafito}


# ── outputs ───────────────────────────────────────────────────────────────────
def bands(img: Image.Image) -> dict:
    """Mean colour of the top BAND_PX rows and of the lightest BAND_PX-row band."""
    rows = np.asarray(img, dtype=np.float64).mean(axis=1)            # (h, 3)
    csum = np.vstack([np.zeros(3), np.cumsum(rows, axis=0)])
    means = (csum[BAND_PX:] - csum[:-BAND_PX]) / BAND_PX              # one per top row y

    def band(yy: int) -> dict:
        hx = "#%02x%02x%02x" % tuple(int(round(v)) for v in means[yy])
        return {"y": int(yy), "average": hx, "luminance": round(colormath.luminance(hx), 5)}

    lum = means @ np.array([0.2126, 0.7152, 0.0722])                  # ranking only
    return {"top": band(0), "lightest": band(int(np.argmax(lum)))}


def outputs(tid: str, sizes: list[tuple[int, int]], root: Path) -> list[tuple[Path, Image.Image]]:
    import panels  # here, not at the top: panels.py imports this module
    t = tokens.load(tid)
    scene = SCENES[t["wallpaper"]["scene"]]
    d = root / tid / "wallpaper"
    out = []
    for w, h in sizes:
        img = scene(w, h, t)
        out.append((d / f"{w}x{h}.jpg", img))
        if (w, h) == SIZES[0]:
            out.append((d / "thumb.png", img.resize(THUMB, Image.LANCZOS)))
            out.append((d / "lock.jpg", lock(t, img)))
            if all((BRAND / f).exists() for f in panels.NEEDS):
                out.append((d / "panel.png", panels.panel(t)))
    for n, src in enumerate(t["wallpaper"]["alternates"], 1):
        alt = {**t, "wallpaper": {**t["wallpaper"], "source": src, "focus": [0.5, 0.5]}}
        for w, h in sizes:
            img = photo(w, h, alt)
            out.append((d / f"alt-{n}" / f"{w}x{h}.jpg", img))
            if (w, h) == SIZES[0]:
                out.append((d / f"alt-{n}" / "thumb.png", img.resize(THUMB, Image.LANCZOS)))
    return out


def orphans(tid: str) -> list[Path]:
    """alt-<n>/ folders left behind by an alternate the contract no longer lists."""
    keep = {f"alt-{n}" for n in range(1, len(tokens.load(tid)["wallpaper"]["alternates"]) + 1)}
    return sorted(p for p in (THEMES_OUT / tid / "wallpaper").glob("alt-*") if p.name not in keep)


def encoded(path: Path, img: Image.Image) -> np.ndarray:
    """What `img` looks like once saved as `path` (JPEG is lossy: compare like with like)."""
    if path.suffix != ".jpg":
        return np.asarray(img.convert("RGB"), dtype=np.int16)
    buf = io.BytesIO()
    img.save(buf, "JPEG", **JPEG)
    buf.seek(0)
    with Image.open(buf) as im:
        return np.asarray(im.convert("RGB"), dtype=np.int16)


def differs(path: Path, img: Image.Image) -> str | None:
    if not path.exists():
        return "missing"
    with Image.open(path) as im:
        cur = np.asarray(im.convert("RGB"), dtype=np.int16)
    new = encoded(path, img)
    if cur.shape != new.shape:
        return f"size {cur.shape[1]}x{cur.shape[0]}, expected {new.shape[1]}x{new.shape[0]}"
    worst = int(np.abs(cur - new).max())
    return f"pixels differ by up to {worst}" if worst > TOLERANCE else None


def save(path: Path, img: Image.Image) -> None:
    if path.suffix == ".jpg":
        img.save(path, "JPEG", **JPEG)
    else:
        img.save(path, optimize=True)


def bands_differ(old: dict, new: dict) -> str | None:
    for tid, sizes in new["themes"].items():
        for size, b in sizes.items():
            for k in ("top", "lightest"):
                was = old.get("themes", {}).get(tid, {}).get(size, {}).get(k, {}).get("average")
                if was is None:
                    return f"{tid} {size} {k} missing"
                if max(abs(p - q) for p, q in zip(colormath.rgb(was), colormath.rgb(b[k]["average"]))) * 255 > TOLERANCE + 0.5:
                    return f"{tid} {size} {k}: {was} -> {b[k]['average']}"
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if an output is stale")
    ap.add_argument("--only", choices=tokens.theme_ids(), help="one theme")
    ap.add_argument("--size", help="WxH, e.g. 1920x1080 (with --out: only that size)")
    ap.add_argument("--out", type=Path, help="write <out>/<theme>/wallpaper/ instead of themes/ (no bands.json)")
    a = ap.parse_args(argv)
    sizes = [tuple(int(v) for v in a.size.split("x"))] if a.size else SIZES
    partial = bool(a.only or a.size or a.out)
    if partial and a.check:
        ap.error("--check takes no --only/--size/--out: it checks everything")
    root = a.out or THEMES_OUT

    import panels
    stale, skipped = [], []
    if not all((BRAND / f).exists() for f in panels.NEEDS):
        print(f"scenes: skip every panel.png (no {BRAND}; set PEONZA_BRAND to the brand's mark/ folder)")
    doc = {"generated_by": "theme/wallpaper/scenes.py (do not edit)", "band_px": BAND_PX, "themes": {}}
    for tid in tokens.theme_ids():
        if a.only and tid != a.only:
            continue
        scene = tokens.load(tid)["wallpaper"]["scene"]
        if scene in NEEDS_BRAND and not (BRAND / NEEDS_BRAND[scene]).exists():
            skipped.append(tid)
            print(f"scenes: skip {tid} (no {BRAND / NEEDS_BRAND[scene]}; set PEONZA_BRAND to the brand's mark/ folder)")
            continue
        if not partial:
            for gone in orphans(tid):
                if a.check:
                    stale.append(f"{gone.relative_to(ROOT)}: no alternate left for it")
                else:
                    shutil.rmtree(gone)
                    print(f"removed {gone}")
        for path, img in outputs(tid, sizes, root):
            if path.parent.name == "wallpaper" and path.stem in {f"{w}x{h}" for w, h in SIZES}:
                # Bands of what ships (the decoded JPEG), so the tests can read them back.
                shipped = Image.fromarray(encoded(path, img).astype(np.uint8), mode="RGB")
                doc["themes"].setdefault(tid, {})[path.stem] = bands(shipped)
            if a.check:
                why = differs(path, img)
                if why:
                    stale.append(f"{path.relative_to(ROOT)}: {why}")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                save(path, img)
                print(f"wrote {path}")

    if not partial and not skipped:
        best = max(((tid, size, b["lightest"]) for tid, sz in doc["themes"].items() for size, b in sz.items()),
                   key=lambda r: r[2]["luminance"])
        doc["floor"] = {"theme": best[0], "size": best[1], **best[2]}
        text = json.dumps(doc, indent=2) + "\n"
        if a.check:
            old = json.loads(BANDS.read_text(encoding="utf-8")) if BANDS.exists() else {}
            why = bands_differ(old, doc)
            if why:
                stale.append(f"{BANDS.relative_to(ROOT)}: {why}")
        else:
            BANDS.write_text(text, encoding="utf-8")
            print(f"wrote {BANDS.relative_to(ROOT)}")

    if a.check:
        for line in stale:
            print(f"stale: {line} (run python3 theme/wallpaper/scenes.py)")
        if not stale:
            print("scenes: ok" + (f" (skipped {', '.join(skipped)})" if skipped else ""))
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
