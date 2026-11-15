"""The launcher's left panel (panel.png, 360x600): a pale peonza for every theme, drawn
in the theme's own language rather than cut from its wallpaper. The user asked for "one
of the peonza, a nice one, with a little more white" instead of the old crop.

  origen   the brand mark in ochre, lit from the left, on a hazy evening sky with a sun
           behind it and its shadow on the ground (the Hudson River School's light).
  grafito  the dot plate inverted: dark dots on pale paper, the mark at one dot per
           pixel over a floor of small grey dots.
  ola      the mark in Prussian blue on washi, spinning on seigaiha waves.
  tinta    a pale technical plate: the half-section elevation of ink.py's Plano (the
           brand's fitted profile, cut half hatched) inside a degree ring, on a grid.
  papel    the Tractatus cover's dots on cream: the peonza's silhouette as propositions
           (paper.py's Sheet on a 15 px grid), axis rings around it.

rofi's face covers the top ~135 px and the readout and signature the bottom ~140, so
every mark sits in the band between (TOP..FOOT). The signal colour never appears.
Deterministic: no randomness but seeded noise, no wall-clock input. Needs the brand's
mark/ folder (~/Repos/logo-peonza or $PEONZA_BRAND); scenes.py skips the panel without it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenes import PANEL, blur, finish, grid, hexrgb, mark, mix, smoothstep, value_noise, ROWS, dots  # noqa: E402

W, H = PANEL
TOP, FOOT = 150, 460            # the band rofi leaves bare, in px of the 600 tall panel
NEEDS = ("peonza.svg", "peonza-silhouette.svg", "peonza-64.svg")


def lighten(c: np.ndarray, k: float) -> np.ndarray:
    return c + (1 - c) * k


def tone(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    """a..b by a fixed k (scenes.mix takes a per-pixel t)."""
    return a + (b - a) * k


def place(layer: np.ndarray, size: int, x: int, y: int) -> np.ndarray:
    """A size x size layer (h, w[, c]) pasted on an empty W x H canvas at x, y."""
    out = np.zeros((H, W) + layer.shape[2:])
    out[y:y + size, x:x + size] = layer
    return out


def brand(size: int, x: int, y: int) -> tuple[np.ndarray, np.ndarray]:
    """(silhouette, engraving) coverage of the brand mark, size px square at x, y."""
    full = mark("peonza.svg", box=size)
    sil = mark("peonza-silhouette.svg", box=size)[..., 3]
    eng = full[..., 3] * (1 - full[..., :3].mean(axis=-1))
    return place(sil, size, x, y), place(eng, size, x, y)


# ── origen ────────────────────────────────────────────────────────────────────
def origen(t: dict) -> Image.Image:
    c = {k: hexrgb(v) for k, v in t["colors"].items()}
    ochre = hexrgb(t["ansi"][3])
    x, y = grid(W, H)
    sky = mix(lighten(c["fg0"], 0.55), lighten(c["fg0"], 0.12), smoothstep(0.05, 0.95, y))
    glow = np.exp(-(((x - 0.62) / 0.34) ** 2 + ((y - 0.36) / 0.20) ** 2))
    rgb = mix(sky, lighten(c["fg0"], 0.85), 0.8 * glow)
    # A low ground line and mist over it.
    ground = smoothstep(0.735, 0.745, y)
    rgb = mix(rgb, mix(lighten(c["fg1"], 0.35), lighten(c["fg0"], 0.2), smoothstep(0.74, 1.0, y)), 0.7 * ground)
    size, px, py = 300, 30, TOP - 6
    sil, eng = brand(size, px, py)
    # Its shadow on the ground, long to the right as at sunset.
    sh = np.exp(-(((x - 0.62) / 0.30) ** 2 + ((y - 0.75) / 0.018) ** 2))
    rgb = mix(rgb, c["bg3"], 0.35 * sh)
    light = np.clip(0.55 + 0.9 * (0.62 - x) + 0.4 * (0.45 - y), 0, 1)
    body = mix(np.broadcast_to(tone(ochre, c["bg0"], 0.45), (H, W, 3)), lighten(ochre, 0.25), light)
    rgb = mix(rgb, body, sil)
    rgb = mix(rgb, c["bg0"], eng)
    return finish(rgb + value_noise(W, H, 2, 2, np.random.default_rng(3))[..., None] * 0.012)


# ── grafito ───────────────────────────────────────────────────────────────────
def grafito(t: dict) -> Image.Image:
    c = {k: hexrgb(v) for k, v in t["colors"].items()}
    pitch = H / ROWS
    cols = int(np.ceil(W / pitch))
    box = 38
    m = mark("peonza-64.svg", box=box)[..., 3]
    shut = np.asarray(Image.fromarray(np.round(m * 255).astype(np.uint8))
                      .filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3)), dtype=np.float64) / 255
    field, cut = np.zeros((ROWS, cols)), np.zeros((ROWS, cols))
    bx, by = (cols - box) // 2, round((TOP + FOOT) / 2 / pitch) - box // 2
    field[by:by + box, bx:bx + box] = shut
    cut[by:by + box, bx:bx + box] = np.clip(shut - m, 0, 1)
    v = np.maximum(field * (1 - 0.5 * cut), 0.10)
    paper = lighten(c["fg0"], 0.4)
    ink = mix(np.broadcast_to(tone(paper, c["fg2"], 0.35), (ROWS, cols, 3)), c["bg3"], smoothstep(0.3, 0.9, field) * (1 - 0.8 * cut))
    return dots(W, H, v, ink, paper)


# ── ola ───────────────────────────────────────────────────────────────────────
def seigaiha(r: float, rings: int, y0: float) -> np.ndarray:
    """Coverage of a seigaiha pattern (scales of concentric arcs, radius r px) below y0."""
    xs, ys = np.arange(W) + 0.5, np.arange(H) + 0.5
    out = np.zeros((H, W))
    taken = np.zeros((H, W), dtype=bool)
    row = 0
    cy = H + r
    while cy > y0 - r:           # bottom rows first: an upper scale lies over the lower
        off = r if row % 2 else 0
        for cx in np.arange(-r + off, W + 2 * r, 2 * r):
            d = np.hypot(xs[None, :] - cx, ys[:, None] - cy)
            inside = (d < r) & (ys[:, None] < cy + 0.01) | (d < r) & (ys[:, None] >= cy)
            ring = np.zeros((H, W))
            for k in range(rings):
                rr = r * (1 - k / rings) - 1.5
                ring = np.maximum(ring, np.clip(1.2 - np.abs(d - rr), 0, 1))
            out = np.where(inside, ring, out)
            taken |= inside
        cy -= r / 2
        row += 1
    return out * (ys[:, None] > y0 - r)


def ola(t: dict) -> Image.Image:
    c = {k: hexrgb(v) for k, v in t["colors"].items()}
    washi = lighten(c["fg0"], 0.5)
    indigo = tone(hexrgb(t["colors"]["tint"]), c["bg0"], 0.62)
    fibre = blur(value_noise(W, H, 3, 40, np.random.default_rng(11)), 1)
    rgb = np.broadcast_to(washi, (H, W, 3)) - (fibre[..., None] - 0.5) * 0.03
    waves = seigaiha(30, 4, 392)
    rgb = mix(rgb, tone(washi, indigo, 0.35), waves)
    size = 270
    sil, eng = brand(size, (W - size) // 2 + 6, TOP - 12)
    rgb = mix(rgb, washi, np.clip(blur(sil, 4) * 1.6, 0, 1))      # a halo of paper round it
    rgb = mix(rgb, indigo, sil)
    rgb = mix(rgb, washi, eng)
    return finish(rgb)


# ── tinta ─────────────────────────────────────────────────────────────────────
def tinta(t: dict) -> Image.Image:
    import ink                                     # loads tinta's tokens; only this panel needs it
    c = t["colors"]
    g = {k: hexrgb(v) for k, v in c.items()}
    paper = tone(g["fg0"], g["fg1"], 0.18)
    col = {"paper": paper, "minor": tone(paper, g["fg2"], 0.14), "major": tone(paper, g["fg2"], 0.32),
           "hatch": tone(paper, g["fg2"], 0.75), "thin": g["line"], "bold": g["bg2"]}
    hx = {k: "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in a) for k, a in col.items()}
    p = ink.PROFILE
    ax, s = W / 2, 280
    ty = FOOT - 6
    top, rim_y = ty - s, ty - (p["rimTop"] + p["rimBot"]) / 2 * s

    def side(k: int):
        return lambda r, h: (ax + k * r * s, ty - h * s)

    lines = [f'<path d="M{x + 0.5} 0V{H}" stroke="{hx["major" if x % 60 == 0 else "minor"]}"/>' for x in range(0, W, 12)]
    lines += [f'<path d="M0 {y + 0.5}H{W}" stroke="{hx["major" if y % 60 == 0 else "minor"]}"/>' for y in range(0, H, 12)]
    r0 = 168
    ticks = "".join(
        f"M{ax + np.sin(a) * r0:.2f} {rim_y - np.cos(a) * r0:.2f}"
        f"L{ax + np.sin(a) * (r0 + (10 if k % 6 == 0 else 5)):.2f} {rim_y - np.cos(a) * (r0 + (10 if k % 6 == 0 else 5)):.2f}"
        for k, a in enumerate(np.deg2rad(np.arange(0, 360, 5))))
    body = ink.curve(side(-1)) + "L" + ink.curve(side(1), reverse=True)[1:] + "Z"
    section = ink.curve(side(-1)) + f"L{ax} {ty}L{ax} {top}Z"
    hatch = "".join(f"M{x:.1f} {ty + 4}L{x + s + 8:.1f} {ty - s - 4}" for x in np.arange(ax - 2 * s, ax + 8, 7))
    creases = "".join(f"M{ax} {ty - h * s:.2f}H{ax + r * s:.2f}"
                      for r, h in [(p["rim"], p["rimTop"]), (p["rim"], p["rimBot"]), tuple(p["waist"])])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">'
           f'<defs><clipPath id="cut"><path d="{section}"/></clipPath></defs>'
           f'<rect width="{W}" height="{H}" fill="{hx["paper"]}"/>'
           f'<g stroke-width="1" fill="none">{"".join(lines)}</g>'
           f'<rect x="10.5" y="10.5" width="{W - 21}" height="{H - 21}" fill="none" stroke="{hx["thin"]}"/>'
           f'<circle cx="{ax}" cy="{rim_y:.2f}" r="{r0}" fill="none" stroke="{hx["hatch"]}"/>'
           f'<path d="{ticks}" stroke="{hx["hatch"]}"/>'
           f'<path d="{body}" fill="{hx["paper"]}"/>'
           f'<path d="{hatch}" stroke="{hx["hatch"]}" clip-path="url(#cut)"/>'
           f'<path d="{creases}" stroke="{hx["thin"]}"/>'
           f'<path d="{body}" fill="none" stroke="{hx["bold"]}" stroke-width="2" stroke-linejoin="round"/>'
           f'<path d="M{ax} {top}V{ty}" stroke="{hx["bold"]}" stroke-width="2"/>'
           f'<path d="M{ax + 0.5} {top - 26}V{ty + 22}" stroke="{hx["thin"]}" stroke-dasharray="20 4 2 4"/>'
           f'<path d="M{ax - r0 - 14} {rim_y + 0.5:.1f}H{ax + r0 + 14}" stroke="{hx["thin"]}" stroke-dasharray="20 4 2 4"/>'
           f'</svg>')
    png = subprocess.run(["rsvg-convert"], input=svg.encode(), check=True, capture_output=True, timeout=60).stdout
    import io
    with Image.open(io.BytesIO(png)) as im:
        return im.convert("RGB")


# ── papel ─────────────────────────────────────────────────────────────────────
def papel(t: dict) -> Image.Image:
    import paper
    cell = 15
    rows, cols = H // cell, W // cell
    box, x0, y0 = 21, 1, TOP // cell + 1
    sil = paper.coverage("peonza-silhouette.svg", box=box)[..., 3]
    full = paper.coverage("peonza.svg", box=box)
    dark = full[..., 3] * (1 - full[..., :3].mean(axis=-1))
    inside = np.zeros((rows, cols), dtype=bool)
    cut = np.zeros((rows, cols), dtype=bool)
    inside[y0:y0 + box, x0:x0 + box] = sil >= 0.5
    cut[y0:y0 + box, x0:x0 + box] = dark >= 0.3
    pad = np.pad(inside, 1)
    edge = inside & ~(pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:])
    sheet = paper.Sheet(rows, cols)
    sheet.write([tuple(q) for q in np.argwhere(inside & ~(cut & ~edge))], edge.astype(np.float64))
    return finish(paper.raster(sheet, W, H, paper.palette(t)))


PANELS = {"origen": origen, "grafito": grafito, "ola": ola, "tinta": tinta, "papel": papel}


def panel(t: dict) -> Image.Image:
    return PANELS[t["id"]](t)
