#!/usr/bin/env python3
"""Build theme/boot/greeter/background.jpg: the login page's ground, the same whatever the
desktop theme (sibling of the GRUB art in theme/boot/grub.py).

A neutral black sheet, #0a0a0a on the left lifting to #111111 on the right. There the peonza
stands as a line drawing of Tinta's «Plano» family (theme/wallpaper/ink.py, whose profile and
pen this reuses): a half-section elevation, the cut half faintly hatched, the outline in the
sheet's `line` grey, a dash-dot axis, one height dimension, the spin's orbits on the floor
round its tip, over a faint 4 px dot grid. The left share of the width stays plain:
quickshell/greeter draws its column there. No glow; everything that reads is live QML (and
regreet shows the same picture).

    python3 theme/boot/greeter.py            write theme/boot/greeter/background.jpg
    python3 theme/boot/greeter.py --check    exit 1 if it is stale, missing, stray or too bright

Build-time only (python-pillow, python-numpy, rsvg-convert); the installer copies the file
next to the page in /usr/local/share/ryce/greeter. Deterministic: fixed seed, no clock.
--check re-renders in memory and compares decoded pixels with a tolerance, so another
libjpeg's rounding does not count as stale.
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "wallpaper"))
import ink  # noqa: E402  the peonza's profile and the drawing pen of Tinta's «Plano»
from grub import SS  # noqa: E402  supersampling, as GRUB's art

ROOT = HERE.parents[1]
OUT = ROOT / "theme" / "boot" / "greeter"
NAME = "background.jpg"
W, H = 1920, 1080
QUALITY = 92

LEFT_GROUND, RIGHT_GROUND = 10, 17     # #0a0a0a -> #111111
INK = 240                              # the page's fg0, #f0f0f0: the orbits fade towards it
PLAIN = 0.40                           # the left share of the width kept free for the column
GRID, GRID_LIFT = 4, 5.0               # dot pitch in pixels; a dot's lift in levels (~2 %)
# The elevation: the axis, the tip and one brand unit (tip to grip), in pixels.
AX, TY, S = 1436, 852, 620
STROKE = 1.5
PENS = {
    "outline": "#3a3a3a",              # the page's `line`
    "crease": "#242424",               # visible edges inside the outline
    "hatch": "#171717",                # the cut face
    "axis": "#2e2e2e",
    "dim": "#2a2a2a",
}

# The luminance budget: a dark page that never glows (asserted on every render). The
# brightest pixels are the outline's #3a3a3a: nothing may pass it by more than the grain.
MAX_MEAN, MAX_P999, MAX_PLAIN_MEAN = 20.0, 60.0, 12.5
# --check tolerance on decoded pixels, in levels.
TOL_MEAN, TOL_MAX = 0.25, 6


def smooth(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def rasterise(body: str, defs: str = "") -> np.ndarray:
    """SVG elements at 1920x1080 as RGBA floats in 0..1."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
           f"<defs>{defs}</defs>{body}</svg>")
    png = subprocess.run(["rsvg-convert", "-w", str(W), "-h", str(H)], input=svg.encode(),
                         check=True, capture_output=True, timeout=120).stdout
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"), np.float32) / 255


def elevation() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The half-section's line work (grey levels, alpha) and the solid's silhouette (alpha)."""
    p, xy = ink.PROFILE, ink.xy
    right = lambda r, h: (AX + r * S, TY - h * S)  # noqa: E731
    left = lambda r, h: (AX - r * S, TY - h * S)   # noqa: E731
    top, rim = TY - S, p["rim"] * S
    s = ink.Sheet(PENS)

    # The cut face, hatched at 45° inside the left half.
    cut = ink.curve(left) + f"L{xy(AX, TY)}L{xy(AX, top)}Z"
    s.defs.append(f'<clipPath id="cut"><path d="{cut}"/></clipPath>')
    hatch = "".join(f"M{xy(x, TY + 4)}L{xy(x + S + 8, TY + 4 - (S + 8))}"
                    for x in np.arange(AX - rim - S - 8, AX + 8, 10 * np.sqrt(2)))
    s.add(f'<path d="{hatch}" fill="none" stroke="{PENS["hatch"]}" stroke-width="1" clip-path="url(#cut)"/>')
    # The outside half's visible edges: the rim's two creases and the waist's.
    for r, h in [(p["rim"], p["rimTop"]), (p["rim"], p["rimBot"]), tuple(p["waist"])]:
        s.line((AX, TY - h * S), (AX + r * S, TY - h * S), "crease")
    # The outline, both halves, and the cut face's edge on the axis.
    for half in (right, left):
        s.path(ink.curve(half), "outline", STROKE, extra=' stroke-linejoin="round"')
    s.line((AX, top + 1), (AX, TY - 1), "outline", STROKE)
    # The axis: a centre line (long dash, dot) past both ends.
    s.line((AX + 0.5, top - 34), (AX + 0.5, TY + 30), "axis", 1, dash="24 4 2 4")
    # One dimension: the whole height, on the outline's side, from the floor it stands on.
    xd = ink.snap(AX + rim + 64, 1)
    s.line((AX + p["cap"] * S + 6, top), (xd + 8, top), "dim")
    s.line((AX + 6, TY), (xd + 8, TY), "dim")
    s.line((xd, top), (xd, TY), "dim")
    s.arrow((xd, top), (xd, top + 1), "dim")
    s.arrow((xd, TY), (xd, TY - 1), "dim")

    art = rasterise("".join(s.svg), "".join(s.defs))
    solid = ink.curve(right) + f"L{xy(AX, TY)}Z" + ink.curve(left) + f"L{xy(AX, TY)}Z"
    body = rasterise(f'<path d="{solid}" fill="#fff"/>')[..., 3]
    return art[..., :3].mean(-1) * 255, art[..., 3], body


def background() -> Image.Image:
    rng = np.random.default_rng(2611)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # The ground: flat on the column, lifting towards the right where the peonza stands.
    g = LEFT_GROUND + (RIGHT_GROUND - LEFT_GROUND) * smooth(PLAIN * W, W, xx)
    # The dot grid: one pixel every GRID, fading in past the column.
    dots = ((xx % GRID == 0) & (yy % GRID == 0)).astype(np.float32)
    g += dots * GRID_LIFT * smooth(PLAIN * W, (PLAIN + 0.18) * W, xx)

    # The floor: flat orbits round the tip, the spin's trace, fading outwards.
    floor = Image.new("L", (W * SS, H * SS), 0)
    draw = ImageDraw.Draw(floor)
    cx, cy = AX * SS, TY * SS
    for i, rx in enumerate((132, 214, 318, 446, 598)):
        ry = rx * 0.12
        a = round(255 * 0.07 * (1 - i / 6))
        draw.ellipse((cx - rx * SS, cy - ry * SS, cx + rx * SS, cy + ry * SS), outline=a, width=SS)
    floor = np.asarray(floor.resize((W, H), Image.Resampling.BOX), np.float32) / 255

    grey, alpha, body = elevation()
    floor *= 1 - body          # a hidden line: the solid stands in front of the floor's back half
    g = g + (INK - g) * floor
    g = g * (1 - alpha) + grey * alpha
    # Grain, about half a level: dithers the ramp so it never bands.
    g += rng.normal(0, 0.55, (H, W))
    img = Image.fromarray(np.clip(np.rint(g), 0, 255).astype(np.uint8), "L")
    lum = np.asarray(img)
    budget(lum)
    return img.convert("RGB")


def budget(lum: np.ndarray) -> None:
    """The page is dark and the column's ground is plain: fail the build otherwise."""
    mean, p999 = float(lum.mean()), float(np.percentile(lum, 99.9))
    plain = float(lum[:, : round(PLAIN * W)].mean())
    assert mean <= MAX_MEAN, f"greeter.py: mean luma {mean:.1f} > {MAX_MEAN}"
    assert p999 <= MAX_P999, f"greeter.py: 99.9th percentile luma {p999:.0f} > {MAX_P999}"
    assert plain <= MAX_PLAIN_MEAN, f"greeter.py: the column's ground averages {plain:.1f} > {MAX_PLAIN_MEAN}"


def encode(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=QUALITY, optimize=True, progressive=False)
    return buf.getvalue()


def decoded(data: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(data)) as im:
        return np.asarray(im.convert("L"), np.int16)


def main(argv: list[str]) -> int:
    check = "--check" in argv
    want = encode(background())
    path = OUT / NAME
    if check:
        bad = [f"stray: {p.relative_to(ROOT)} (not generated: delete it)"
               for p in sorted(OUT.iterdir()) if p.name != NAME] if OUT.is_dir() else []
        if not path.is_file():
            bad.append(f"missing: {path.relative_to(ROOT)} (run python3 theme/boot/greeter.py)")
        else:
            have = decoded(path.read_bytes())
            if have.shape != (H, W):
                bad.append(f"stale: {path.relative_to(ROOT)} is {have.shape[1]}x{have.shape[0]}, not {W}x{H}")
            else:
                diff = np.abs(have - decoded(want))
                if diff.mean() > TOL_MEAN or diff.max() > TOL_MAX:
                    bad.append(f"stale: {path.relative_to(ROOT)} (mean diff {diff.mean():.2f}, "
                               f"max {diff.max()}; run python3 theme/boot/greeter.py)")
        for b in bad:
            print(b)
        if not bad:
            print(f"greeter.py: ok ({NAME}, {len(want) // 1024} KiB)")
        return 1 if bad else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for p in OUT.iterdir():
        if p.name != NAME:
            p.unlink()
    path.write_bytes(want)
    print(f"greeter.py: wrote {path.relative_to(ROOT)} ({len(want) // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
