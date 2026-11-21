#!/usr/bin/env python3
"""Chromium's new tab backgrounds: one picture per theme, in its palette and its language,
drawn for the new tab's layout and never a desktop picture or a crop of one.

    python3 theme/wallpaper/newtab.py            write themes/<id>/chromium/newtab/{1920x1080,2560x1440}.jpg
    python3 theme/wallpaper/newtab.py --check    exit 1 if one is stale, too heavy, or its
                                                 column side is not calm enough to read on
    python3 theme/wallpaper/newtab.py --only ola --out DIR   one theme, elsewhere (for looking)

The new tab (apps/chromium/newtab) sets its clock, search and bookmarks in one column on
the side the theme's layout.css names (--col-justify: start = left, end = right); the
picture keeps that side calm and puts its drawing on the other one:

  origen   the peonza as a peak at dusk: its fitted profile above the rim stands on a
           lake's horizon, lit along its crest by a sun just set behind it; under the
           water line its cone, broken by the afterglow's ripples like a reflection.
  grafito  the peonza as a solid, upright and lit from the upper left, printed through a
           45° halftone screen: Grafito's grey dots on black, their size the light, and
           its shadow on the table in the smallest ones.
  ola      the peonza spinning on still water at night: rings of four lines (seigaiha's
           own count) spreading from its tip, seen from the sheets' 20°; the top cut from
           the same block, indigo carved with seigaiha in washi.
  tinta    a study in revolution: the peonza's fitted profile turned about its axis as a
           wireframe through the sheets' camera (20° over the table), hidden lines
           dashed, on a degree ring laid on the table.
  papel    the title page of the 1605 Quijote on green baize under the lamp, set in
           Literata in its own spelling, in a gilt double rule, with Juan de la Cuesta's
           device redrawn round the peonza (paper.py's baize, inks and type).

COLUMN is the column's width at 1920 plus a margin; --check measures fg1 (the dimmest
text there) against the worst 16 px block under it in each picture, with no scrim (the
page darkens it further), and refuses under 4.5:1. Each size is drawn at its own
resolution, not resized. Deterministic: seeded noise only; --check compares decoded
pixels with scenes.py's tolerance. Needs rsvg-convert (Tinta) and, for Papel, the brand's mark/ folder (paper.py).
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ink  # noqa: E402  (the brand's fitted profile and the sheets' camera)
from scenes import ROOT, SIZES, TOLERANCE, blur, colormath, finish, grain, hexrgb, mix, smoothstep, tokens  # noqa: E402

THEMES_OUT = ROOT / "themes"
COLUMN = 0.47                   # 864 px (54rem) of 1920, and a little more
MIN_CONTRAST = 4.5
MAX_BYTES = 450_000             # per picture: the new tab reads it on every open
JPEG = {"quality": 88, "subsampling": 0, "optimize": True, "progressive": True}


def column_left(tid: str, root: Path = THEMES_OUT) -> bool:
    """True when the theme's new tab column stands on the left (its layout.css)."""
    css = (root / tid / "chromium" / "newtab" / "layout.css").read_text(encoding="utf-8")
    m = re.search(r"--col-justify:\s*(start|end)", css)
    if not m:
        raise SystemExit(f"newtab: no --col-justify in themes/{tid}/chromium/newtab/layout.css")
    return m.group(1) == "start"


def away(w: int, h: int, left: bool) -> tuple[np.ndarray, np.ndarray]:
    """Per pixel: u, 0 on the column's edge of the screen and 1 on the far one, and y in
    0..1, both (h, w)."""
    x = (np.arange(w) + 0.5) / w
    y = (np.arange(h) + 0.5) / h
    u = x if left else 1 - x
    return np.broadcast_to(u[None, :], (h, w)), np.broadcast_to(y[:, None], (h, w))


def colours(tid: str) -> tuple[dict, dict[str, np.ndarray], list[np.ndarray]]:
    t = tokens.load(tid)
    return t, {k: hexrgb(v) for k, v in t["colors"].items()}, [hexrgb(a) for a in t["ansi"]]


def lerp(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    return a + (b - a) * k


def svg_raster(body: str, w: int, h: int) -> Image.Image:
    """SVG drawn in 1920x1080 units, rasterised at w x h."""
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 1920 1080">{body}</svg>'
    png = subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h)], input=svg.encode(),
                         check=True, capture_output=True, timeout=120).stdout
    with Image.open(io.BytesIO(png)) as im:
        return im.convert("RGB")


def hx(c: np.ndarray) -> str:
    return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in np.clip(c, 0, 1))


# ── the peonza, shared by Origen, Grafito and Ola ─────────────────────────────
SS = 3                                               # supersampling of filled outlines


def fill(shapes: list[list[tuple[float, float]]], w: int, h: int) -> np.ndarray:
    """Anti-aliased coverage (h, w) of filled polygons given in px."""
    im = Image.new("L", (w * SS, h * SS), 0)
    draw = ImageDraw.Draw(im)
    for pts in shapes:
        draw.polygon([(x * SS, y * SS) for x, y in pts], fill=255)
    return np.asarray(im.resize((w, h), Image.BOX), dtype=np.float64) / 255


def side_view(cx: float, base: float, s: float, h0: float = 0.0, h1: float = 1.0) -> list[tuple[float, float]]:
    """The fitted profile (ink.PROFILE) between heights h0 and h1 as one closed outline in
    px, both halves: 1 brand unit is s px and height h0 sits on row `base`."""
    o = ink.outline(96)
    o = o[(o[:, 1] >= h0 - 1e-9) & (o[:, 1] <= h1 + 1e-9)]
    right = [(cx + r * s, base - (hh - h0) * s) for r, hh in o]
    return right + [(cx - r * s, y) for (_, y), (r, _) in zip(right[::-1], o[::-1])]


# ── origen ────────────────────────────────────────────────────────────────────
def origen(w: int, h: int, left: bool) -> Image.Image:
    t, c, a = colours("origen")
    u, y = away(w, h, left)
    p = ink.PROFILE
    ember = lerp(a[3], a[1], 0.45)                   # gold into rose: the afterglow
    far = smoothstep(COLUMN - 0.05, 0.95, u)         # 0 on the column's side
    hor, at = 0.60, 0.73                             # the lake's horizon; the peak's u
    cx, s = (at if left else 1 - at) * w, 0.62 * h
    # The sky warms towards the horizon on the far side, brightest behind the peak.
    glow = np.exp(-(((u - at) * w / h / 0.55) ** 2 + ((y - hor) / 0.22) ** 2))
    rgb = mix(np.broadcast_to(c["bg0"], (h, w, 3)), lerp(c["bg2"], ember, 0.25), smoothstep(0.1, hor, y) * (0.3 + 0.7 * far))
    rgb = mix(rgb, lerp(ember, a[11], 0.35), 0.9 * glow * far)
    # The lake: dark, the afterglow laid on it in broken streaks under the peak.
    rows = (np.arange(h) + 0.5) / h
    cols = (np.arange(w) + 0.5) / h * 540
    ripple = np.sin(rows * 702)[:, None] > -0.2 + 0.7 * np.sin(cols[None, :] * 0.045 + rows[:, None] * 377) ** 2
    streak = 0.85 * np.exp(-(((u - at) * w / h / 0.42) ** 2)) * far * ripple * np.exp(-(y - hor) / 0.14)
    water = mix(np.broadcast_to(lerp(c["bg0"], c["bg1"], 0.5), (h, w, 3)), lerp(ember, c["bg0"], 0.45), streak)
    rgb = np.where((y > hor)[..., None], water, rgb)
    # The peak is the peonza above its rim's underside, standing on the horizon and lit
    # along its crest by the sun just behind it; under the water line, its cone, broken
    # by the ripples like a reflection.
    peak = fill([side_view(cx, hor * h, s, p["rimBot"], 1.0)], w, h)
    rgb = mix(rgb, c["bg0"], peak)
    crest = np.clip((blur(peak, max(1, round(h / 540)), 1) - peak) * 3, 0, 1)
    rgb = mix(rgb, lerp(a[11], a[3], 0.4), crest * smoothstep(0.0, 0.5, hor - y) * 0.9)
    cone = fill([side_view(cx, hor * h + p["rimBot"] * s, s, 0.0, p["rimBot"])], w, h)
    rgb = mix(rgb, lerp(c["bg0"], c["bg1"], 0.3), cone * ripple)
    return finish(rgb + grain(w, h, seed=3, amount=1.2 / 255))


# ── grafito ───────────────────────────────────────────────────────────────────
def grafito(w: int, h: int, left: bool) -> Image.Image:
    """The peonza as a solid, upright and lit from the upper left, printed through a 45°
    halftone screen: grey dots on black, their size the light."""
    t, c, a = colours("grafito")
    at, cam = 0.73, np.deg2rad(ink.CAMERA)
    s, tipx, tipy = 0.60 * h, (at if left else 1 - at) * w, 0.86 * h
    # Shade on a half-size raster: a dense point cloud of the surface, nearest point wins.
    lw, lh = w // 2, h // 2
    hs = np.linspace(0, 1, 1400)
    o = ink.outline(400)[::-1]
    r = np.interp(hs, o[:, 1], o[:, 0])
    dr = np.gradient(r, hs)
    th = np.linspace(0, 2 * np.pi, 2400, endpoint=False)
    H_, T = np.meshgrid(hs, th, indexing="ij")
    R, D = np.meshgrid(r, th, indexing="ij")[0], np.meshgrid(dr, th, indexing="ij")[0]
    pos = np.stack([R * np.sin(T), H_, R * np.cos(T)], -1).reshape(-1, 3)
    nrm = np.stack([np.sin(T), -D, np.cos(T)], -1).reshape(-1, 3)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    view = np.array([0.0, np.sin(cam), np.cos(cam)])
    light = np.array([-0.75, 0.45, 0.35])
    light /= np.linalg.norm(light)
    # Key light from the upper left, an ambient floor so the far side still prints, and
    # a rim where the surface turns away from the camera, so the outline holds on black.
    rim = (1 - np.abs(nrm @ view)) ** 3
    lit = np.clip(0.20 + 0.75 * np.clip(nrm @ light, 0, 1) + 0.35 * rim, 0, 1)
    px = ((tipx + pos[:, 0] * s) / 2).astype(int)
    py = ((tipy - (pos[:, 1] * np.cos(cam) - pos[:, 2] * np.sin(cam)) * s) / 2).astype(int)
    depth = pos @ view
    ok = (px >= 0) & (px < lw) & (py >= 0) & (py < lh)
    order = np.argsort(depth[ok])                       # far first, near last: near wins
    shade = np.zeros((lh, lw))
    inside = np.zeros((lh, lw))
    shade[py[ok][order], px[ok][order]] = lit[ok][order]
    inside[py[ok][order], px[ok][order]] = 1
    # Its shadow on the table, thrown to the right: a flat, dim ellipse.
    yy, xx = np.mgrid[0:lh, 0:lw] + 0.5
    sh = ((xx - (tipx + 0.22 * s) / 2) / (0.34 * s / 2)) ** 2 + ((yy - tipy / 2) / (0.07 * s / 2)) ** 2 < 1
    shade = np.where((inside == 0) & sh, 0.06, shade)
    # The screen: cells `pitch` apart on axes turned 45°, one dot per cell centre.
    pitch = h / 132
    X, Y = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    ua, va = (X + Y) / np.sqrt(2), (Y - X) / np.sqrt(2)
    ca, cb = (np.floor(ua / pitch) + 0.5) * pitch, (np.floor(va / pitch) + 0.5) * pitch
    cx, cy = (ca - cb) / np.sqrt(2), (ca + cb) / np.sqrt(2)
    v = shade[np.clip((cy / 2).astype(int), 0, lh - 1), np.clip((cx / 2).astype(int), 0, lw - 1)]
    rad = pitch * 0.52 * np.sqrt(v)
    cov = np.clip(rad - np.hypot(X - cx, Y - cy) + 0.5, 0, 1) * (v > 0)
    ink_ = mix(np.broadcast_to(c["line"], (h, w, 3)), c["fg1"] * 0.92, smoothstep(0.1, 1.0, v))
    return finish(mix(np.broadcast_to(c["bg0"], (h, w, 3)), ink_, cov))


# ── ola ───────────────────────────────────────────────────────────────────────
def seigaiha(w: int, h: int, r: int, rings: int, stroke: float) -> np.ndarray:
    """Coverage of seigaiha (scales of `rings` concentric arcs, radius r px) over w x h.
    The pattern repeats every 2r across and r down (rows r/2 apart, every other one
    shifted r), so one tile is drawn and repeated; a scale lies over the row below it."""
    X, Y = np.meshgrid(np.arange(2 * r) + 0.5, np.arange(r) + 0.5)
    tile = np.zeros((r, 2 * r))
    for j in range(4, -3, -1):                       # bottom rows first
        cy, off = j * r / 2, (r if j % 2 else 0)
        cx = np.round((X - off) / (2 * r)) * 2 * r + off
        d = np.hypot(X - cx, Y - cy)
        ring = np.zeros_like(d)
        for k in range(rings):
            rr = r * (1 - k / rings) - stroke
            ring = np.maximum(ring, np.clip(stroke / 2 + 0.5 - np.abs(d - rr), 0, 1))
        tile = np.where(d < r, ring, tile)
    return np.tile(tile, (h // r + 1, w // (2 * r) + 1))[:h, :w]


def ola(w: int, h: int, left: bool) -> Image.Image:
    """The peonza spinning on still water at night: rings of four lines, seigaiha's own
    count, spread from its tip across the water, seen from the sheets' 20°."""
    t, c, a = colours("ola")
    u, y = away(w, h, left)
    indigo = lerp(c["tint"], c["bg0"], 0.45)
    washi = lerp(c["fg0"], c["bg0"], 0.35)
    at = 0.70
    tipx, tipy, s = (at if left else 1 - at) * w, 0.66 * h, 0.42 * h
    k = np.sin(np.deg2rad(ink.CAMERA))
    X, Y = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    rho = np.hypot(X - tipx, (Y - tipy) / k)          # distance on the water, px
    rgb = mix(np.broadcast_to(c["bg0"], (h, w, 3)), c["bg1"], smoothstep(0.0, 1.0, y))
    rings = np.zeros((h, w))
    lw = h / 540                                      # a line's width in px
    for g, r0 in enumerate([0.16, 0.34, 0.56, 0.82, 1.12]):
        for j in range(4):
            rr = (r0 + 0.035 * j) * h
            rings = np.maximum(rings, np.clip(lw - np.abs(rho - rr) * k * 0.9 + 0.5 - 0.5 * lw, 0, 1) * (1 - 0.15 * g))
    rgb = mix(rgb, indigo, rings * smoothstep(0.42, 0.80, u) * smoothstep(0.42, 0.48, y))
    # The top over its rings, cut from the same block: indigo, carved with seigaiha in
    # washi, the half away from the light a step darker, its edge in washi.
    outline = side_view(tipx, tipy, s)
    body = fill([outline], w, h)
    half = fill([outline[: len(outline) // 2] + [(tipx, tipy - s), (tipx, tipy)]], w, h)
    scales = seigaiha(w, h, round(0.032 * h), 4, max(1.0, 1.2 * h / 1080))
    rgb = mix(rgb, lerp(c["tint"], c["bg0"], 0.40), body)
    rgb = mix(rgb, washi, scales * body * (0.85 - 0.45 * half))
    rgb = mix(rgb, washi, np.clip((blur(body, max(1, round(h / 720)), 1) - body) * 4, 0, 1))
    return finish(rgb + grain(w, h, seed=5, amount=1.0 / 255))


# ── tinta ─────────────────────────────────────────────────────────────────────
def tinta(w: int, h: int, left: bool) -> Image.Image:
    t, c, a = colours("tinta")
    g = {k: hx(v) for k, v in c.items()}
    # 1 brand unit and the tip's row, in units: the table's ring stays inside a window
    # wider than 16:9 (the page crops it top and bottom).
    S, base = 640, 850
    cx = (0.735 if left else 0.265) * 1920
    cam = np.deg2rad(ink.CAMERA)
    o = ink.outline(64)

    def at(r: float, th: float, hh: float) -> tuple[float, float]:
        return cx + r * np.sin(th) * S, base - (hh * np.cos(cam) - r * np.cos(th) * np.sin(cam)) * S

    def path(pts) -> str:
        return "M" + "L".join(f"{x:.2f} {yy:.2f}" for x, yy in pts)

    parts = [f'<rect width="1920" height="1080" fill="{g["bg0"]}"/>']
    # The sheet's grid, minor every 24, major every 120.
    for x in range(0, 1920, 24):
        parts.append(f'<path d="M{x + .5} 0V1080" stroke="{g["bg3"] if x % 120 == 0 else g["bg1"]}"/>')
    for yy in range(0, 1080, 24):
        parts.append(f'<path d="M0 {yy + .5}H1920" stroke="{g["bg3"] if yy % 120 == 0 else g["bg1"]}"/>')
    # The table's degree ring round the tip, a tick every 5°, longer every 30°.
    rr = 0.62
    ring = [at(rr, th, 0) for th in np.linspace(0, 2 * np.pi, 181)]
    ticks = "".join(path([at(rr, th, 0), at(rr + (0.05 if k % 6 == 0 else 0.025), th, 0)])
                    for k, th in enumerate(np.deg2rad(np.arange(0, 360, 5))))
    parts += [f'<path d="{path(ring)}Z" fill="none" stroke="{g["line"]}"/>',
              f'<path d="{ticks}" fill="none" stroke="{g["fg2"]}"/>']
    # Meridians every 15°: the near ones solid (lighter as they face the camera), the far
    # ones dashed under them; the outline (±90°) in fg1.
    for deg in range(0, 360, 15):
        th = np.deg2rad(deg)
        line = path(at(r, th, hh) for r, hh in o)
        facing = np.cos(th)
        if deg in (90, 270):
            continue
        if facing < 0:
            parts.append(f'<path d="{line}" fill="none" stroke="{g["line"]}" stroke-dasharray="5 4"/>')
        else:
            parts.append(f'<path d="{line}" fill="none" stroke="{hx(lerp(c["line"], c["fg2"], facing))}"/>')
    # Parallels: near half solid, far half dashed.
    for hh in np.linspace(0.04, 0.96, 24):
        r = float(ink.radius(hh))
        near = [at(r, th, hh) for th in np.linspace(-np.pi / 2, np.pi / 2, 61)]
        back = [at(r, th, hh) for th in np.linspace(np.pi / 2, 3 * np.pi / 2, 61)]
        parts += [f'<path d="{path(back)}" fill="none" stroke="{g["bg3"]}" stroke-dasharray="5 4"/>',
                  f'<path d="{path(near)}" fill="none" stroke="{g["line"]}"/>']
    for side in (np.pi / 2, -np.pi / 2):
        parts.append(f'<path d="{path(at(r, side, hh) for r, hh in o)}" fill="none" stroke="{g["fg1"]}" '
                     f'stroke-width="1.5" stroke-linejoin="round"/>')
    top, foot = at(0, 0, 1.12), at(0, 0, -0.10)
    parts.append(f'<path d="M{cx + .5} {top[1]:.1f}V{foot[1]:.1f}" stroke="{g["fg2"]}" stroke-dasharray="24 4 2 4"/>')
    return svg_raster("".join(parts), w, h)


# ── papel ─────────────────────────────────────────────────────────────────────
# The 1605 title page, in its own spelling, centred on the far side (1920x1080 units):
# (text, face, px, tracking, baseline). Faces: caps (spaced capitals) or italic.
TITLE_PAGE = [("EL INGENIOSO", "caps", 26, 6.0, 236),
              ("HIDALGO DON QVI-", "caps", 44, 3.0, 306),
              ("XOTE DE LA MANCHA,", "caps", 44, 3.0, 362),
              ("Compuesto por Miguel de Ceruantes", "italic", 24, 0, 420),
              ("Saauedra.", "italic", 24, 0, 452),
              ("EN MADRID,", "caps", 18, 4.0, 846),
              ("Por Iuan de la Cuesta.", "italic", 22, 0, 878),
              ("Año 1605.", "italic", 22, 0, 914)]
DEVICE = {"cy": 650, "ring": 128, "motto": 104, "peonza": 128}   # Cuesta's device, the peonza in it
MOTTO = "POST TENEBRAS SPERO LVCEM"
TITLE_INK = 0.44                # vellum: a page lit by the lamp, calm beside the column


def papel(w: int, h: int, left: bool) -> Image.Image:
    """The title page of the 1605 Quijote on the baize under the lamp: its lines in vellum,
    a gilt double rule round it, and Juan de la Cuesta's device redrawn with the peonza
    inside its ring and the device's own motto, «post tenebras spero lucem», round it."""
    import paper
    t = tokens.load("papel")
    pal = paper.palette(t)
    u = w / 1920
    cx = (0.735 if left else 0.265) * w
    words, wd = paper.blank(w, h)
    gilt, gd = paper.blank(w, h)
    faces = {"caps": paper.LITERATA, "italic": paper.LITERATA_ITALIC}
    for text, kind, px, track, base in TITLE_PAGE:
        f = paper.face(faces[kind], px * u)
        if kind == "caps":
            paper.spaced(wd, text, f, cx, base * u, track * u, [])
        else:
            wd.text((cx, base * u), text, font=f, fill=255, anchor="ms", features=["onum"])
    # The frame: thick and thin rules; a short rule under the author.
    for inset, width in ((0, 2), (8, 1)):
        x0, y0, x1, y1 = cx - (330 - inset) * u, (150 + inset) * u, cx + (330 - inset) * u, (960 - inset) * u
        gd.rectangle((x0, y0, x1, y1), outline=255, width=max(1, round(width * u)))
    gd.line((cx - 40 * u, 490 * u, cx + 40 * u, 490 * u), fill=255, width=max(1, round(u)))
    # The device: a double ring, the motto along its upper arc, the peonza in the middle.
    d = DEVICE
    cy = d["cy"] * u
    for r, width in ((d["ring"], 2), (d["ring"] - 7, 1)):
        gd.ellipse((cx - r * u, cy - r * u, cx + r * u, cy + r * u), outline=255, width=max(1, round(width * u)))
    arc(gilt, MOTTO, paper.face(paper.LITERATA, 13 * u), cx, cy, d["motto"] * u, 2.2 * u)
    paper.stamp(gilt, paper.peonza(round(d["peonza"] * u)), cx, cy - d["peonza"] * u / 2)
    ground = paper.baize(w, h, t, ((0.735 if left else 0.265), 0.55, 0.30, 0.62), seed=13)
    return finish(paper.lay(ground, [(pal["vellum"], TITLE_INK, words), (pal["gilt"], paper.GILT, gilt)]))


def arc(mask: Image.Image, text: str, font, cx: float, cy: float, r: float, track: float) -> None:
    """Capitals set clockwise along the top of a circle of radius r (their baseline on it),
    centred on the top, each glyph turned to the circle's tangent."""
    widths = [font.getlength(ch) for ch in text]
    total = (sum(widths) + track * (len(text) - 1)) / r          # the arc's angle
    phi = -total / 2
    box = int(font.size * 3)
    for ch, wd in zip(text, widths):
        mid = phi + wd / 2 / r
        g = Image.new("L", (box, box), 0)
        ImageDraw.Draw(g).text((box / 2, box / 2), ch, font=font, fill=255, anchor="ms")
        g = g.rotate(-np.degrees(mid), resample=Image.BICUBIC, center=(box / 2, box / 2))
        x, y = round(cx + r * np.sin(mid) - box / 2), round(cy - r * np.cos(mid) - box / 2)
        under = mask.crop((x, y, x + box, y + box))
        mask.paste(Image.fromarray(np.maximum(np.asarray(under), np.asarray(g))), (x, y))
        phi += (wd + track) / r


PICTURES = {"origen": origen, "grafito": grafito, "ola": ola, "tinta": tinta, "papel": papel}


# ── outputs and checks ────────────────────────────────────────────────────────
def outputs(tid: str, root: Path = THEMES_OUT) -> list[tuple[Path, Image.Image]]:
    left = column_left(tid)
    return [(root / tid / "chromium" / "newtab" / f"{w}x{h}.jpg", PICTURES[tid](w, h, left)) for w, h in SIZES]


def encode(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", **JPEG)
    return buf.getvalue()


def differs(path: Path, img: Image.Image) -> str | None:
    """scenes.differs for this file's JPEG settings: decoded pixels, tolerance included."""
    if not path.exists():
        return "missing"
    with Image.open(path) as im:
        cur = np.asarray(im.convert("RGB"), dtype=np.int16)
    with Image.open(io.BytesIO(encode(img))) as im:
        new = np.asarray(im.convert("RGB"), dtype=np.int16)
    if cur.shape != new.shape:
        return f"size {cur.shape[1]}x{cur.shape[0]}, expected {new.shape[1]}x{new.shape[0]}"
    worst = int(np.abs(cur - new).max())
    return f"pixels differ by up to {worst}" if worst > TOLERANCE else None


def column_contrast(img: Image.Image, tid: str) -> float:
    """fg1 against the worst 16 px block (at 1080) under the column, no scrim."""
    t = tokens.load(tid)
    rgb = np.asarray(img.convert("RGB"), dtype=np.float64)
    h, w = rgb.shape[:2]
    cw = int(COLUMN * w)
    col = rgb[:, :cw] if column_left(tid) else rgb[:, w - cw:]
    b = max(1, round(16 * h / 1080))
    hh, ww = col.shape[0] // b * b, col.shape[1] // b * b
    blocks = col[:hh, :ww].reshape(hh // b, b, ww // b, b, 3).mean((1, 3)).reshape(-1, 3)
    lum = blocks @ np.array([0.2126, 0.7152, 0.0722])
    pick = blocks[np.argmax(lum) if colormath.luminance(t["colors"]["bg0"]) < 0.5 else np.argmin(lum)]
    return colormath.contrast(t["colors"]["fg1"], "#%02x%02x%02x" % tuple(int(round(v)) for v in pick))


def check(tid: str, path: Path, img: Image.Image) -> list[str]:
    rel = path.relative_to(ROOT)
    bad = []
    if why := differs(path, img):
        bad.append(f"stale: {rel}: {why} (run python3 theme/wallpaper/newtab.py)")
        return bad
    size = path.stat().st_size
    ratio = column_contrast(img, tid)
    print(f"newtab: {rel}: {size // 1000} kB, fg1 over the column's worst block {ratio:.2f}:1")
    if size > MAX_BYTES:
        bad.append(f"heavy: {rel}: {size} bytes > {MAX_BYTES}")
    if ratio < MIN_CONTRAST:
        bad.append(f"contrast: {rel}: fg1 at {ratio:.2f}:1 under the column, under {MIN_CONTRAST}")
    return bad


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a picture is stale, heavy or loud under the column")
    ap.add_argument("--only", choices=list(PICTURES), help="one theme")
    ap.add_argument("--out", type=Path, help="write <out>/<theme>/chromium/newtab/ instead of themes/")
    a = ap.parse_args(argv)
    if a.check and (a.only or a.out):
        ap.error("--check takes no --only/--out: it checks everything")
    if set(PICTURES) != set(tokens.theme_ids()):
        raise SystemExit(f"newtab: PICTURES covers {sorted(PICTURES)}, the themes are {tokens.theme_ids()}")
    bad = []
    for tid in PICTURES:
        if a.only and tid != a.only:
            continue
        for path, img in outputs(tid):
            if a.check:
                bad += check(tid, path, img)
                continue
            out = a.out / path.relative_to(THEMES_OUT) if a.out else path
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(encode(img))
            print(f"wrote {out}")
    if a.check:
        print("\n".join(bad) if bad else "newtab: ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
