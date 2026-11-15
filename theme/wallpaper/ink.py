#!/usr/bin/env python3
"""Tinta's drawing sheets (its alternates) and its lock picture, graphite on charcoal.

    python3 theme/wallpaper/ink.py            write the masters in assets/wallpapers/:
                                              tinta-plano, tinta-despiece, tinta-estela
                                              (2560x1440) and tinta-lock (1920x1080)
    python3 theme/wallpaper/ink.py --check    exit 1 if a master is stale, the brand's
                                              profile moved, a deployed copy breaks the
                                              light budget, its frame misses the tiled
                                              window, or the lock's text would sink
    python3 theme/wallpaper/ink.py --only tinta-estela --out DIR   one, elsewhere

Three sheets of one set, nothing lit, all from the peonza's real profile (the curve
the brand fitted to the film prop, ~/Repos/logo-peonza/src/geometry.mjs), dimensioned
in the brand's units (tip to grip = 1):
  plano     RY-PZ-001: half-section elevation (cut half hatched at 45°), a plan view in
            a degree ring, a stroboscope of the top still spinning (four wireframe
            exposures through the brand's camera, 20° over the table).
  despiece  RY-PZ-002: the top as three turned parts (grip, body, steel tip) lifted
            apart along its axis through the same camera, balloons, a parts list and
            the tip in half-section at 4:1.
  estela    RY-PZ-003: the axis's trace seen from above as the spin decays (precession
            speeding up, nutation cusps widening into loops), with spin and lean
            against time and the initial conditions.
Hierarchy by line weight and grey: outlines fg1, dimensions and secondary views fg2,
hatching and construction `line`, fg0 only for section letters and the ring's index.
Tinta's amber means "an AI waits" and never appears here (scenes.py grades alternates
to grey anyway).

Layout is in px of the 1920x1080 screen ("units"). The sheet's frame is the outer edge
of one tiled window alone on that screen, derived from tinta's geometry (frame_top,
gaps_out, border, rounding): a terminal opened there lands exactly on it. The grid runs
on above it under the floating bar to the screen's top; the side and bottom margins
stay bare charcoal. The desk (clock top left, binary clock bottom left, the sound's
lines on the left edge between them, Hito top right, the HUD under it, the peonza's
card bottom centre: DESK) sits on empty sheet; the title block keeps a drawing sheet's
own corner, bottom right inside the frame, under the HUD.

The masters are 2560x1440 and scenes.py derives each alternate from one: a LANCZOS
resize to 1920, a mono S-curve, JPEG again. So a unit is 4/3 master px, every straight
line is a whole number of units wide and lies on unit edges (it lands on exact screen
px at 1920; --check finds the frame there). Line work is SVG rasterised by
rsvg-convert; labels are Pillow text in the vendored Martian Mono with the BASIC
layout, so FreeType alone places them.

Deterministic: a seeded grain, no wall-clock input. --check compares decoded pixels
with scenes.py's tolerance, then measures the deployed copies against BUDGET (what
the screen shows, not the master: the S-curve brightens the lines).
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenes import BRAND, ROOT, differs, finish, grain, save  # noqa: E402

import colormath  # noqa: E402  (tools/, on the path scenes.py set up)
import tokens  # noqa: E402

FONT = ROOT / "assets" / "fonts" / "MartianMono-Regular.ttf"
GEOMETRY = BRAND.parents[1] / "src" / "geometry.mjs"   # the brand repo's profile, when present
W, H = 2560, 1440
UNIT = W / 1920                                      # master px per screen px at 1920x1080

# The brand's fitted profile (geometry.mjs PROFILE): the right half of a solid of
# revolution in (r, h), tip at (0, 0), top of the grip at h = 1. --check fails if the
# brand's copy moves.
PROFILE = {
    "rim": 0.488, "rimTop": 0.356, "rimBot": 0.332, "cap": 0.036,
    "horn": [0.040, 0.70, 0.17, 0.378], "under": [0.36, 0.305, 0.26, 0.24],
    "waist": [0.205, 0.192], "cone": [0.135, 0.112, 0.040, 0.0],
}

GEOMETRY_T = tokens.load("tinta")["geometry"]
SCREEN = (1920, 1080)                                # the main monitor (DP-1), where the frame must fit


def window(g: dict = GEOMETRY_T, screen: tuple[int, int] = SCREEN) -> tuple[int, int, int, int]:
    """x, y, w, h of one tiled window's outer edge (its border included) alone on the
    screen: Hyprland keeps geometry.frame_top for the bar and gaps_out round the tiled
    area (measured on the stage, 2026-11-14: with gaps_out 12 and border 1 a lone kitty
    sits at 13,59 1894x1008, its border's outer px at 12..1907 x 58..1067)."""
    go = g["gaps_out"]
    return go, g["frame_top"] + go, screen[0] - 2 * go, screen[1] - g["frame_top"] - 2 * go


if GEOMETRY_T["rounding_power"] != 2:
    raise SystemExit("ink: the frame's corners are circular; tinta's geometry.rounding_power must stay 2")
# Sheet, in units. The frame is that window's outermost px ring, its corners rounded as
# the border's (rounding + border); the grid runs on above it to the top of the screen.
_WX, _WY, _WW, _WH = window()
LEFT, TOP, RIGHT, BOTTOM = _WX, _WY, _WX + _WW - 1, _WY + _WH - 1
CORNER = GEOMETRY_T["rounding"] + GEOMETRY_T["border"]
MARGIN = GEOMETRY_T["gaps_out"]                      # what the side and bottom margins hold scales with it
ZONES_X, ZONES_Y = 8, 4
GRID = 24                                            # minor grid pitch; a major line every 5
# Tinta's desk on the 1920x1080 screen, as layer boxes (shadow margin included):
# x0, y0, x1, y1, measured with `hyprctl layers` on the stage (2026-11-14). The sheets
# keep their drawing DESK_CLEAR units away from them (--check renders the drawing
# alone and looks). Hito's box is its worst case («hoy», five tasks, the filter line and
# a three-line project picker); the HUD sits under it, 24 above the title block; both
# end at the title block's right edge (2026-11-15). The peonza's card sits at the bottom
# centre. The sound's lines (desk/EdgeViz.qml) grow from the left edge, vertically
# centred: 72 lines 7 apart, up to 72 dots of 4 px, in a layer padded 12 all round. So
# the left column, clock to binary clock, is the desk's while music plays.
DESK = {"clock": (52, 86, 371, 301), "hito": (1380, 86, 1908, 460),
        "binary": (52, 781, 364, 1036), "hud": (1287, 580, 1908, 918),
        "peonza": (890, 896, 1030, 1036), "edgeviz": (0, 276, 312, 804)}
DESK_CLEAR = 20
# Zones a sheet may draw under by the user's choice, so crowded() lets them be (none
# today: the Despiece's parts list stands beside the desk clock, not under it).
SHARED: dict[str, set[str]] = {}
PAD = 12                                             # a desk card's layer pad round its visible card
# The elevation: the axis, the tip and 1 brand unit, in units. 0.488 * 500 is whole,
# so the rim's 2-unit outline lands on screen px. Its dimensions clear the clock above
# and the binary clock below.
AX, TY, S = 760, 800, 500
# Plan view: centre, half the elevation's scale. Its dial's labels clear Hito's card.
PC, SP = (1110, 270), 250
# The strobe view: the orbit's centre and radius on screen, the scale, the camera. The
# left column belongs to the sound's lines and the right one to Hito and the HUD, so it
# sits under the plan, on its axis, between the elevation's rim and the HUD.
OC, ORBIT, SW = (1118, 700), 80, SP / 4               # the plan is 1:1
CAMERA, LEAN = 20, 8                                  # degrees, as the brand draws it
FRAMES, DT, RPM = 4, 0.05, 2400                       # 2400 rpm * 0.05 s = 2 whole turns
SPAN = 0.9                                            # the tip's arc: x within ±SPAN of the orbit
PRECESSION = 34                                       # the axis turns this much more per exposure
# Title block, 508 x 114, where a drawing sheet keeps it: the bottom right corner,
# TB_INSET units inside the frame (the HUD's card ends above it).
TB_INSET = 12
TB = (RIGHT - TB_INSET - 507, BOTTOM - TB_INSET - 113)

# What a deployed copy may show (Rec.709 luma, 0-255), measured at 1920x1080 and
# scaled with the size. Bright area and hard edges are what read as glare, not the
# mean: the comic version had 10.6 % of px over 200 and 4.6 % hard edges.
BUDGET = {
    "mean": (22, 45), "p50": 30, "p99": 150, "over200": 0.10,   # %
    "block16": 90, "edges": 1.5, "bar_mean": 28, "bar_p99": 70,  # block mean; % px; top band
}
BAR = GEOMETRY_T["frame_top"]


# ── geometry ──────────────────────────────────────────────────────────────────
def segments(p: dict = PROFILE) -> list[list[float]]:
    """Cubic segments [r0,h0, r1,h1, r2,h2, r3,h3] from the top of the grip to the tip
    (geometry.mjs segments())."""
    k = 0.5523 * p["cap"]
    top = 1 - p["cap"]
    return [
        [0, 1, k, 1, p["cap"], top + k, p["cap"], top],
        [p["cap"], top, *p["horn"], p["rim"], p["rimTop"]],
        [p["rim"], p["rimTop"], p["rim"], p["rimTop"] - 0.008, p["rim"], p["rimBot"] + 0.008, p["rim"], p["rimBot"]],
        [p["rim"], p["rimBot"], *p["under"], *p["waist"]],
        [*p["waist"], *p["cone"], 0, 0],
    ]


def curve(m, reverse: bool = False) -> str:
    """The profile as SVG path data under the affine map m(r, h) -> (x, y); being
    affine, mapping the control points maps the curve exactly."""
    segs = segments()
    if reverse:
        segs = [[*g[6:8], *g[4:6], *g[2:4], *g[0:2]] for g in reversed(segs)]
    d = "M%s" % xy(*m(*segs[0][:2]))
    for g in segs:
        d += "C" + " ".join(xy(*m(g[i], g[i + 1])) for i in (2, 4, 6))
    return d


def xy(x: float, y: float) -> str:
    return f"{x:.2f} {y:.2f}"


def elev(side: int):
    """Elevation map of one half (side +1 right, -1 left)."""
    return lambda r, h: (AX + side * r * S, TY - h * S)


def snap(v: float, w: float) -> float:
    """Centre of a w-unit line nearest v that covers whole screen px."""
    return np.floor(v - w / 2 + 0.5) + w / 2


# ── drawing ───────────────────────────────────────────────────────────────────
class Sheet:
    """SVG line work in screen units plus Pillow labels, composited over the ground."""

    def __init__(self, colors: dict) -> None:
        self.c = colors
        self.svg: list[str] = []
        self.defs: list[str] = []
        self.labels: list[tuple] = []

    def add(self, el: str) -> None:
        self.svg.append(el)

    def path(self, d: str, ink: str, w: float = 1, dash: str = "", extra: str = "") -> None:
        dash = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<path d="{d}" fill="none" stroke="{self.c[ink]}" stroke-width="{w}"{dash}{extra}/>')

    def line(self, p: tuple, q: tuple, ink: str, w: float = 1, dash: str = "") -> None:
        """A segment; axis-aligned ones snapped to whole screen px."""
        (x0, y0), (x1, y1) = p, q
        if y0 == y1:
            y0 = y1 = snap(y0, w)
        if x0 == x1:
            x0 = x1 = snap(x0, w)
        self.path(f"M{xy(x0, y0)}L{xy(x1, y1)}", ink, w, dash)

    def circle(self, c: tuple, r: float, ink: str, w: float = 1, dash: str = "") -> None:
        dash = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<circle cx="{c[0]}" cy="{c[1]}" r="{r:.2f}" fill="none" stroke="{self.c[ink]}" stroke-width="{w}"{dash}/>')

    def fill(self, d: str, ink: str) -> None:
        self.add(f'<path d="{d}" fill="{self.c[ink]}"/>')

    def arrow(self, tip: tuple, toward: tuple, ink: str = "fg2", length: float = 9, half: float = 2.4) -> None:
        """A filled arrowhead with its point on `tip`, pointing away from `toward`."""
        t = np.array(tip, float)
        u = t - np.array(toward, float)
        u /= np.hypot(*u)
        n = np.array([-u[1], u[0]])
        a, b = t - u * length + n * half, t - u * length - n * half
        self.fill(f"M{xy(*t)}L{xy(*a)}L{xy(*b)}Z", ink)

    def label(self, x: float, y: float, text: str, size: float, ink: str = "fg2",
              anchor: str = "ls", rotate: bool = False) -> None:
        self.labels.append((x, y, text, size, ink, anchor, rotate))

    # Dimensions: thin fg2 line between arrowheads, extension lines from the part.
    def dim_v(self, x: float, y0: float, y1: float, text: str) -> None:
        """A vertical dimension at x between heights y0 < y1, text rotated on its left
        (the caller draws the extension lines: they share one datum)."""
        x = snap(x, 1)
        self.line((x, y0), (x, y1), "fg2")
        self.arrow((x, y0), (x, y0 + 1))
        self.arrow((x, y1), (x, y1 - 1))
        self.label(x - 5, (y0 + y1) / 2, text, 12, anchor="ms", rotate=True)

    def dim_h(self, y: float, x0: float, x1: float, text: str, ext_from: tuple[float, float] | None = None) -> None:
        """A horizontal dimension at y between x0 < x1, text centred above; extension
        lines start at ext_from (y of the part at x0 and at x1)."""
        y = snap(y, 1)
        if ext_from:
            for xe, ye in zip((x0, x1), ext_from):
                self.line((xe, ye + 4), (xe, y + 5), "fg2")
        self.line((x0, y), (x1, y), "fg2")
        self.arrow((x0, y), (x0 + 1, y))
        self.arrow((x1, y), (x1 - 1, y))
        self.label((x0 + x1) / 2, y - 5, text, 12, anchor="ms")

    def document(self) -> str:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 1920 1080">'
                f'<defs>{"".join(self.defs)}</defs>{"".join(self.svg)}</svg>')


def frame(s: Sheet) -> None:
    """Border with zone ticks and labels, crop marks, registration targets, grid."""
    # The grid first, under everything: minor every GRID, major every 5 from the frame.
    # It runs on over the bar's band to the screen's top; the margins stay bare.
    def ink(n: int) -> str:
        return "line" if n % 5 == 0 else "bg3"
    for x in range(LEFT + GRID, RIGHT, GRID):
        s.line((x + 0.5, 0), (x + 0.5, BOTTOM), ink((x - LEFT) // GRID))
    for y in range(TOP + GRID, BOTTOM, GRID):
        s.line((LEFT, y + 0.5), (RIGHT, y + 0.5), ink((y - TOP) // GRID))
    for y in range(TOP - GRID, -1, -GRID):
        s.line((LEFT, y + 0.5), (RIGHT + 1, y + 0.5), ink((TOP - y) // GRID))
    s.add(f'<rect x="{LEFT}" y="{TOP}" width="{RIGHT - LEFT}" height="{BOTTOM - TOP}" rx="{CORNER - 0.5}" '
          f'fill="none" stroke="{s.c["line"]}" stroke-width="1" transform="translate(0.5 0.5)"/>')

    zx, zy = (RIGHT - LEFT) / ZONES_X, (BOTTOM - TOP) / ZONES_Y
    for i in range(1, ZONES_X):
        x = round(LEFT + i * zx)
        s.line((x, TOP), (x, TOP + 8), "line")
        s.line((x, BOTTOM - 8), (x, BOTTOM), "line")
    # What lives in the margins (24 units wide when it was drawn) shrinks with them.
    k = min(1.0, MARGIN / 24)
    foot, side_r = (BOTTOM + 1 + 1080) / 2, (RIGHT + 1 + 1920) / 2
    for i in range(ZONES_X):
        s.label(LEFT + (i + 0.5) * zx, foot + 3.5, str(i + 1), 10, "line", "ms")
    for i in range(1, ZONES_Y):
        y = round(TOP + i * zy)
        s.line((LEFT, y), (LEFT + 8, y), "line")
        s.line((RIGHT - 8, y), (RIGHT, y), "line")
    for i in range(ZONES_Y):
        for x in (LEFT / 2, side_r):
            s.label(x, TOP + (i + 0.5) * zy + 4, "ABCD"[i], 10, "line", "ms")

    # Crop marks: the frame's sides carried past its corners.
    near, far, up = round(5 * k), round(18 * k), round(12 * k)
    for cx, cy, dx, dy in [(LEFT, TOP, -1, -1), (RIGHT, TOP, 1, -1), (LEFT, BOTTOM, -1, 1), (RIGHT, BOTTOM, 1, 1)]:
        s.line((cx + near * dx, cy), (cx + far * dx, cy), "fg2")
        s.line((cx, cy + near * dy), (cx, cy + (up if dy < 0 else far) * dy), "fg2")

    # Registration targets in the margins, on the zone boundaries.
    r, arm = min(6, MARGIN / 2 - 2), min(10, MARGIN / 2)
    for c in [(960.5, foot), (LEFT / 2, TOP + 2 * zy), (side_r, TOP + 2 * zy)]:
        s.circle(c, r, "fg2")
        s.line((c[0] - arm, c[1]), (c[0] + arm, c[1]), "fg2")
        s.line((c[0], c[1] - arm), (c[0], c[1] + arm), "fg2")


def elevation(s: Sheet) -> None:
    """Half-section elevation: section on the left, outline on the right."""
    right, left = elev(1), elev(-1)
    p = PROFILE
    top, tip = TY - S, TY

    # The cut face, hatched at 45° inside the left half.
    section = curve(left) + f"L{xy(AX, TY)}L{xy(AX, top)}Z"
    s.defs.append(f'<clipPath id="cut"><path d="{section}"/></clipPath>')
    lo, hi = AX - p["rim"] * S, AX
    hatch = "".join(f"M{xy(x, TY + 4)}L{xy(x + (S + 8), TY + 4 - (S + 8))}"
                    for x in np.arange(lo - S - 8, hi + 8, 8 * np.sqrt(2)))
    s.add(f'<path d="{hatch}" fill="none" stroke="{s.c["line"]}" stroke-width="1" clip-path="url(#cut)"/>')

    # Visible edges of the outside half: the rim's two creases and the waist's.
    for r, h in [(p["rim"], p["rimTop"]), (p["rim"], p["rimBot"]), (p["waist"][0], p["waist"][1])]:
        s.line((AX, TY - h * S), (AX + r * S, TY - h * S), "fg2")
    # The outline: both halves, and the cut face's edge on the axis.
    s.path(curve(right), "fg1", 2, extra=' stroke-linejoin="round"')
    s.path(curve(left), "fg1", 2, extra=' stroke-linejoin="round"')
    s.line((AX, top + 1), (AX, tip - 1), "fg1", 2)
    # The axis: a centre line (long dash, dot) past both ends.
    s.line((AX + 0.5, top - 30), (AX + 0.5, tip + 26), "fg2", 1, dash="24 4 2 4")

    # Heights on the section side, from the tip: rim underside, rim top, the whole.
    x_rim = AX - p["rim"] * S
    s.line((AX - 4, tip), (x_rim - 104, tip), "fg2")            # the datum all three measure from
    s.dim_v(x_rim - 34, TY - p["rimBot"] * S, tip, f'{p["rimBot"]:.3f}')
    s.dim_v(x_rim - 64, TY - p["rimTop"] * S, tip, f'{p["rimTop"]:.3f}')
    s.dim_v(x_rim - 94, top, tip, "1.000")
    s.line((x_rim - 4, TY - p["rimBot"] * S), (x_rim - 39, TY - p["rimBot"] * S), "fg2")
    s.line((x_rim - 4, TY - p["rimTop"] * S), (x_rim - 69, TY - p["rimTop"] * S), "fg2")
    s.line((AX - 6, top), (x_rim - 99, top), "fg2")

    # Diameters under the tip: the waist, then the rim.
    yw, xw = TY - p["waist"][1] * S, p["waist"][0] * S
    s.dim_h(tip + 34, AX - xw, AX + xw, f'Ø{2 * p["waist"][0]:.3f}', ext_from=(yw, yw))
    s.dim_h(tip + 64, x_rim, AX + p["rim"] * S, f'Ø{2 * p["rim"]:.3f}',
            ext_from=(TY - p["rimBot"] * S, TY - p["rimBot"] * S))

    # The grip's round end: a leader from the cap at 45° to a shoulder.
    c = np.array([AX + p["cap"] * S * 0.7071, top + p["cap"] * S * (1 - 0.7071)])
    k = c + [70, -70]
    s.line(tuple(k), tuple(c + [3, -3]), "fg2")
    s.arrow(tuple(c), tuple(c + [1, -1]))
    s.line((k[0], k[1]), (k[0] + 60, k[1]), "fg2")
    s.label(k[0] + 4, k[1] - 5, f'R{p["cap"]:.3f}', 12)

    s.label(AX, tip + 112, "SEMICORTE A–A", 13, "fg1", "ms")
    s.label(AX, tip + 130, "ESC 2:1", 10, "fg2", "ms")


def plan(s: Sheet) -> None:
    """Plan view inside a degree ring, with the cutting plane of the elevation."""
    p = PROFILE
    cx, cy = PC
    rim = p["rim"] * SP
    s.circle(PC, rim, "fg2", 2)
    s.circle(PC, p["waist"][0] * SP, "fg2", 1, dash="6 3")          # hidden under the disc
    s.circle(PC, p["cap"] * SP, "fg2", 1)
    s.line((cx - rim - 18, cy + 0.5), (cx + rim + 18, cy + 0.5), "fg2", 1, dash="24 4 2 4")
    s.line((cx + 0.5, cy - rim - 18), (cx + 0.5, cy + rim + 18), "fg2", 1, dash="24 4 2 4")

    # Cutting plane A-A: the horizontal diameter, thick ends, arrows looking back.
    end = rim + 26
    for d in (-1, 1):
        x = cx + d * end
        s.line((x - d * 14, cy), (x, cy), "fg1", 2)
        s.line((x - d * 7, cy), (x - d * 7, cy - 20), "fg2")
        s.arrow((x - d * 7, cy - 22), (x - d * 7, cy - 21))
        s.label(x - d * 7, cy - 30, "A", 12, "fg0", "ms")

    r0 = rim + 44
    degree_ring(s, PC, r0)

    s.label(cx, cy + r0 + 52, "PLANTA", 13, "fg1", "ms")
    s.label(cx, cy + r0 + 70, "ESC 1:1", 10, "fg2", "ms")


def degree_ring(s: Sheet, c: tuple, r0: float) -> None:
    """A tick every 2°, longer every 10°, labelled every 30°; the north index in fg0."""
    s.circle(c, r0, "line")
    ticks = {2: ("line", 5), 10: ("fg2", 9)}
    d = {ink: "" for ink, _ in ticks.values()}
    for deg in range(0, 360, 2):
        ink, n = ticks[10] if deg % 10 == 0 else ticks[2]
        a = np.deg2rad(deg)
        u = np.array([np.sin(a), -np.cos(a)])
        d[ink] += f"M{xy(*(np.array(c) + u * r0))}L{xy(*(np.array(c) + u * (r0 + n)))}"
        if deg % 30 == 0:
            q = np.array(c) + u * (r0 + 22)
            s.label(q[0], q[1] + 4, f"{deg:03d}", 10, "fg2", "ms")
    for ink, path in d.items():
        s.path(path, ink)
    s.fill(f"M{xy(c[0], c[1] - r0 + 2)}L{xy(c[0] - 4, c[1] - r0 - 6)}L{xy(c[0] + 4, c[1] - r0 - 6)}Z", "fg0")


def tilt(lean: float, azimuth: float) -> np.ndarray:
    """Rotation taking the body's axis (0, 1, 0) to one leaning `lean` rad towards
    `azimuth` (x right, y up, z towards the camera), about the tip."""
    ax = np.array([np.sin(lean) * np.cos(azimuth), np.cos(lean), np.sin(lean) * np.sin(azimuth)])
    k = np.array([ax[2], 0.0, -ax[0]])
    k = k / (np.linalg.norm(k) or 1)
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(lean) * kx + (1 - np.cos(lean)) * kx @ kx


def strobe(s: Sheet) -> None:
    """A chronophotograph of the top still spinning: FRAMES exposures DT apart, through
    the brand's camera (CAMERA° over the table, orthographic). The tip wanders along an
    orbit on the table while the axis, leaning LEAN°, precesses; the spin (RPM) is a
    whole number of turns per exposure, so the strobe freezes it, as a strobe does.
    Older exposures are fainter; the newest carries its axis."""
    p = PROFILE
    a = np.deg2rad(CAMERA)

    def screen(q: np.ndarray, tip: np.ndarray) -> tuple[float, float]:
        return tip[0] + q[0] * SW, tip[1] + (q[2] * np.sin(a) - q[1] * np.cos(a)) * SW

    def on_table(psi: float) -> np.ndarray:
        return np.array([OC[0] + ORBIT * np.cos(psi), OC[1] + ORBIT * np.sin(psi) * np.sin(a)])

    # The tip's orbit, the whole loop, as a hairline.
    s.add(f'<ellipse cx="{OC[0]}" cy="{OC[1]}" rx="{ORBIT}" ry="{ORBIT * np.sin(a):.2f}" fill="none" '
          f'stroke="{s.c["line"]}" stroke-width="1"/>')

    caps = []
    view = np.array([0.0, np.sin(a), np.cos(a)])                    # towards the camera
    for k in range(FRAMES):
        f = k / (FRAMES - 1)
        g = round(70 + (150 - 70) * f)
        ink = f"strobe{k}"
        s.c[ink] = "#%02x%02x%02x" % (g, g, g)
        t = round(96 + (150 - 96) * f)                              # tags stay legible
        s.c[ink + "t"] = "#%02x%02x%02x" % (t, t, t)
        psi = np.arccos(SPAN * (2 * f - 1))                         # the near arc, evenly spaced across
        tip = on_table(psi)
        rot = tilt(np.deg2rad(LEAN), psi + np.deg2rad(PRECESSION) * k)

        # Near meridians only (every 60°): the far ones are behind the body.
        d = ""
        for m in range(6):
            th = np.deg2rad(30 + 60 * m)
            radial = rot @ np.array([np.sin(th), 0.0, np.cos(th)])
            if radial @ view < 0.05:
                continue
            d += curve(lambda r, h: screen(rot @ np.array([r * np.sin(th), h, r * np.cos(th)]), tip))
        # Parallels: the rim's two edges, as sampled 3D circles.
        for r, h in [(p["rim"], p["rimTop"]), (p["rim"], p["rimBot"])]:
            ring = [screen(rot @ np.array([r * np.sin(u), h, r * np.cos(u)]), tip)
                    for u in np.linspace(0, 2 * np.pi, 97)]
            d += "M" + "L".join(xy(*q) for q in ring) + "Z"
        s.path(d, ink, extra=' stroke-linejoin="round"')

        top = screen(rot @ np.array([0.0, 1.0, 0.0]), tip)
        caps.append(top)
        tag_y = OC[1] - SW * np.cos(a) - 34
        s.line((top[0], top[1] - 6), (top[0], tag_y + 4), "line")
        s.label(top[0], tag_y, f"t+{k * DT:.2f}", 9, ink + "t", "ms")
        if k == FRAMES - 1:
            end = screen(rot @ np.array([0.0, 1.18, 0.0]), tip)
            s.line(tuple(tip + (tip - end) * 0.06), end, "fg2", 1, dash="24 4 2 4")

    # The precession: the grip's path through the exposures, dotted.
    s.path("M" + "L".join(xy(*q) for q in caps), "fg2", dash="1 3")

    y = OC[1] + ORBIT * np.sin(a) + 40
    s.label(OC[0], y, "VISTA AUXILIAR", 13, "fg1", "ms")
    s.label(OC[0], y + 18, "ESTROBOSCOPIA", 13, "fg1", "ms")
    s.label(OC[0], y + 36, f"{FRAMES} TOMAS · {DT:.2f} s · {RPM} RPM", 10, "fg2", "ms")
    s.label(OC[0], y + 52, f"PREC {LEAN}° · ESC 1:{SP / SW:.0f}", 10, "fg2", "ms")


def outline(n: int = 96) -> np.ndarray:
    """The profile as (r, h) samples from the grip's top to the tip; h never rises."""
    t = np.linspace(0, 1, n)[:, None]
    out = []
    for g in segments():
        p0, p1, p2, p3 = (np.array(g[i:i + 2]) for i in (0, 2, 4, 6))
        out.append((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)
    return np.vstack(out)


def radius(h: float | np.ndarray) -> float | np.ndarray:
    o = outline()[::-1]
    return np.interp(h, o[:, 1], o[:, 0])


def table(s: Sheet, x0: float, y0: float, widths: list[int], rows: list[list[str]], caption: str) -> None:
    """A ruled table under a caption: the header row in fg2 captions, the rest in fg2."""
    x1, step = x0 + sum(widths), 24
    y1 = y0 + step * len(rows)
    s.label(x0, y0 - 10, caption, 13, "fg1", "ls")
    s.add(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="{s.c["bg0"]}"/>')
    for k in range(len(rows) + 1):
        s.line((x0, y0 + k * step), (x1, y0 + k * step), "fg2" if k in (0, len(rows)) else "line")
    xs = np.cumsum([x0, *widths])
    for x in xs:
        s.line((x, y0), (x, y1), "fg2" if x in (xs[0], xs[-1]) else "line")
    for k, row in enumerate(rows):
        for text, xa in zip(row, xs):
            s.label(xa + 6, y0 + k * step + 16, text, 8 if k == 0 else 11, "fg2", "ls")


# ── the exploded view (despiece) ──────────────────────────────────────────────
# The top as three turned parts, cut from the profile at these heights and lifted
# apart along its axis, through the strobe's camera: (balloon, name, h0, h1, lift,
# pin (r, h from, h to) or None, material).
EX, EY, SE = 700, 940, 525
BALLOONS = 410                                        # the balloons' column (their centres)
PARTS = [
    (1, "MANGO", 0.70, 1.0, 0.36, (0.022, 0.58, 0.70), "HAYA"),
    (2, "CUERPO", 0.06, 0.70, 0.16, None, "HAYA TORNEADA"),
    (3, "PÚA", 0.0, 0.06, 0.0, (0.018, 0.06, 0.16), "ACERO C45"),
]
# Detail B: the tip at 4:1 (half-section), its own tip on screen.
DX, DY, SD = 1080, 485, 4 * SE


def axo(r: float, th: float, h: float) -> tuple[float, float]:
    """A point at radius r, angle th (0 faces the camera) and height h, on screen."""
    a = np.deg2rad(CAMERA)
    return EX + r * np.sin(th) * SE, EY - (h * np.cos(a) - r * np.cos(th) * np.sin(a)) * SE


def ring(r: float, h: float, start: float, stop: float, n: int = 72) -> str:
    """Path data of a horizontal circle's arc, angles in degrees (0 faces the camera)."""
    pts = [axo(r, np.deg2rad(u), h) for u in np.linspace(start, stop, n)]
    return "M" + "L".join(xy(*p) for p in pts)


def exploded(s: Sheet) -> None:
    for num, name, h0, h1, lift, pin, _ in PARTS:
        hs = np.linspace(h0, h1, 80)
        rs = radius(hs)
        # Sides (the meridians at ±90°), the front half of the lower face, the whole
        # upper face (seen from 20° above); the lower face's back half is hidden.
        for side in (-1, 1):
            s.path("M" + "L".join(xy(*axo(r, side * np.pi / 2, h + lift)) for r, h in zip(rs, hs)),
                   "fg1", 1.5, extra=' stroke-linejoin="round"')
        if rs[0] > 0.004:
            s.path(ring(rs[0], h0 + lift, -90, 90), "fg1", 1.5)
            s.path(ring(rs[0], h0 + lift, 90, 270), "line", dash="4 3")
        if rs[-1] > 0.004:
            s.path(ring(rs[-1], h1 + lift, 0, 360), "fg1", 1.5)
        # Wireframe: three front meridians, and the rim's creases on the body.
        for th in (-40, 0, 40):
            s.path("M" + "L".join(xy(*axo(r, np.deg2rad(th), h + lift)) for r, h in zip(rs, hs)), "line")
        if name == "CUERPO":
            for h in (PROFILE["rimTop"], PROFILE["rimBot"]):
                s.path(ring(PROFILE["rim"], h + lift, -90, 90), "fg2")
            s.path(ring(0.022, h1 + lift, 0, 360), "fg2")          # the grip's socket
        if pin:
            pr, p0, p1 = pin
            for side in (-1, 1):
                s.path(f"M{xy(*axo(pr, side * np.pi / 2, p0 + lift))}L{xy(*axo(pr, side * np.pi / 2, p1 + lift))}", "fg2")
            end = p1 if p0 >= h0 else p0                          # the free end of the pin
            s.path(ring(pr, end + lift, 0, 360) if end == p1 else ring(pr, end + lift, -90, 90), "fg2")
        # The balloon on the left, its leader ending in a dot on the part.
        hm = (h0 + h1) / 2 if name != "CUERPO" else PROFILE["rimTop"] + 0.08
        px, py = axo(radius(hm), -np.pi / 2, hm + lift)
        bx, by = BALLOONS, py
        s.line((bx + 14, by), (px - 4, py), "fg2")
        s.add(f'<circle cx="{px - 2:.2f}" cy="{py:.2f}" r="2" fill="{s.c["fg2"]}"/>')
        s.circle((bx, by), 13, "fg2")
        s.label(bx, by + 4.5, str(num), 12, "fg1", "ms")

    # The axis through every part, and detail B round the tip.
    top, foot = axo(0, 0, 1.0 + PARTS[0][4] + 0.06), axo(0, 0, -0.07)
    s.line((EX + 0.5, top[1]), (EX + 0.5, foot[1]), "fg2", 1, dash="24 4 2 4")
    bc = axo(0, 0, 0.08)
    s.circle(bc, 62, "fg2", dash="6 3")
    k = np.array(bc) + [44, 44]
    s.line(tuple(k), (k[0] + 30, k[1]), "fg2")
    s.label(k[0] + 36, k[1] + 4.5, "B", 12, "fg0", "ls")

    s.label(EX, EY + 60, "DESPIECE · VISTA AXONOMÉTRICA", 13, "fg1", "ms")
    s.label(EX, EY + 78, f"CÁMARA {CAMERA}° · ESC 1:1", 10, "fg2", "ms")

    detail(s)
    rows = [["Nº", "DENOMINACIÓN", "MATERIAL", "CANT."]] + [[str(p[0]), p[1], p[6], "1"] for p in PARTS]
    # Beside the desk clock, where the user put it (2026-11-15): one card gap right of its
    # layer, the caption's top (21 units over the table) level with its visible card,
    # and all of it above the sound's lines.
    x0, y0 = DESK["clock"][2] + DESK_CLEAR, DESK["clock"][1] + PAD + 21
    table(s, x0, y0, [30, 82, 116, 44], rows, "LISTA DE PIEZAS")
    y1 = y0 + 24 * len(rows)
    s.label(x0, y1 + 20, "AJUSTE H7/p6 EN 1–2 Y 2–3", 10, "fg2", "ls")
    s.label(x0, y1 + 36, "ARISTAS MATADAS 0.005", 10, "fg2", "ls")


def detail(s: Sheet) -> None:
    """Detail B: the tip and its shank in half-section at 5:1."""
    pr, p0, p1 = PARTS[2][5]
    h0, h1 = PARTS[2][2], PARTS[2][3]
    hs = np.linspace(h0, h1, 60)
    cone = [(r, h) for r, h in zip(radius(hs), hs)]

    def pt(r: float, h: float, side: int) -> tuple[float, float]:
        return DX + side * r * SD, DY - h * SD

    def body(side: int) -> str:
        pts = [pt(r, h, side) for r, h in cone] + [pt(pr, h1, side), pt(pr, p1, side), pt(0, p1, side)]
        return "M" + "L".join(xy(*q) for q in pts)

    # Left half cut and hatched (steel: 45°, close), right half in outline.
    section = body(-1) + f"L{xy(DX, DY)}Z"
    s.defs.append(f'<clipPath id="tip"><path d="{section}"/></clipPath>')
    span = (p1 - h0) * SD + 12
    hatch = "".join(f"M{xy(x, DY + 6)}L{xy(x + span, DY + 6 - span)}"
                    for x in np.arange(DX - span - pr * SD, DX + 6, 5 * np.sqrt(2)))
    s.add(f'<path d="{hatch}" fill="none" stroke="{s.c["line"]}" stroke-width="1" clip-path="url(#tip)"/>')
    for side in (-1, 1):
        s.path(body(side), "fg1", 2, extra=' stroke-linejoin="round"')
    s.line(pt(radius(h1), h1, 1), pt(pr, h1, 1), "fg2")               # the shoulder's edge
    s.line((DX, DY - p1 * SD + 1), (DX, DY - 1), "fg1", 2)
    s.line((DX + 0.5, DY - p1 * SD - 24), (DX + 0.5, DY + 22), "fg2", 1, dash="24 4 2 4")

    # Heights from the tip on the left; the two diameters on the right.
    xl = DX - radius(h1) * SD
    s.line((DX - 4, DY), (xl - 74, DY), "fg2")
    s.line((DX - pr * SD - 4, DY - p1 * SD), (xl - 74, DY - p1 * SD), "fg2")
    s.line((xl - 4, DY - h1 * SD), (xl - 44, DY - h1 * SD), "fg2")
    s.dim_v(xl - 34, DY - h1 * SD, DY, f"{h1:.3f}")
    s.dim_v(xl - 64, DY - p1 * SD, DY, f"{p1:.3f}")
    rc = radius(h1) * SD
    s.dim_h(DY - p1 * SD - 34, DX - pr * SD, DX + pr * SD, f"Ø{2 * pr:.3f}",
            ext_from=(DY - p1 * SD, DY - p1 * SD))
    s.dim_h(DY + 30, DX - rc, DX + rc, f"Ø{2 * radius(h1):.3f}", ext_from=(DY - h1 * SD, DY - h1 * SD))

    s.label(DX, DY + 78, "DETALLE B · PÚA", 13, "fg1", "ms")
    s.label(DX, DY + 96, "SEMICORTE · ESC 4:1", 10, "fg2", "ms")


# ── the axis's trace (estela) ─────────────────────────────────────────────────
# A heavy top released leaning a little: its axis precesses ever faster as the spin
# decays and nods (nutation) in cusps that widen into loops. The model is a sketch, not
# a solution: spin w = W0 e^(-t/TAU); precession rate and lean grow as it slows;
# cusps per turn fall with the square of the spin.
PX, PY, PR = 680, 556, 290                    # the polar view: centre and 10° radius
T_END, TAU = 8.0, 8.0
THETA0, CUSPS0, PERIOD0 = 1.5, 12, 5.5        # degrees; cusps per turn; s per turn at W0


def trace(n: int = 8000) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """t (s), spin (rpm), lean (°) and azimuth (rad) of the axis."""
    t = np.linspace(0, T_END, n)
    k = np.exp(t / TAU)                         # W0 / w
    omega = 2 * np.pi / PERIOD0 * k
    psi = np.concatenate([[0], np.cumsum((CUSPS0 / k ** 2 * omega)[:-1] * np.diff(t))])
    lean0 = THETA0 + 5 * (1 - np.exp(-t / TAU))
    lean = lean0 + 0.6 * k ** 2 * (1 - np.cos(psi)) / 2
    phi = np.concatenate([[0], np.cumsum((omega * (1 - np.cos(psi)))[:-1] * np.diff(t))])
    return t, RPM / k, lean, phi


def estela(s: Sheet) -> None:
    t, spin, lean, phi = trace()

    def polar(theta: float, az: float) -> tuple[float, float]:
        return PX + theta / 10 * PR * np.sin(az), PY - theta / 10 * PR * np.cos(az)

    # Rings every 2° of lean, spokes every 30°, the degree ring outside.
    for deg in (2, 4, 6, 8):
        s.circle((PX, PY), deg / 10 * PR, "line", dash="6 3")
        q = polar(deg, np.deg2rad(15))
        s.label(q[0] + 3, q[1] - 3, f"{deg}°", 9, "fg2", "ls")
    s.circle((PX, PY), PR, "line")
    for az in range(0, 360, 30):
        s.line(polar(0.25, np.deg2rad(az)), polar(10, np.deg2rad(az)), "bg3")
    degree_ring(s, (PX, PY), PR + 18)
    s.line((PX - 8, PY + 0.5), (PX + 8, PY + 0.5), "fg2")
    s.line((PX + 0.5, PY - 8), (PX + 0.5, PY + 8), "fg2")

    # The trace, older stretches fainter, as the strobe's exposures are.
    pts = np.array([polar(th, az) for th, az in zip(lean, phi)])
    parts = 8
    for k, chunk in enumerate(np.array_split(np.arange(len(t)), parts)):
        g = round(70 + (160 - 70) * k / (parts - 1))
        ink = f"trace{k}"
        s.c[ink] = "#%02x%02x%02x" % (g, g, g)
        idx = np.append(chunk, min(chunk[-1] + 1, len(t) - 1))
        s.path("M" + "L".join(xy(*q) for q in pts[idx]), ink, extra=' stroke-linejoin="round"')
    for sec in range(1, int(T_END) + 1):
        i = np.searchsorted(t, sec)
        q = pts[min(i, len(t) - 1)]
        s.add(f'<circle cx="{q[0]:.2f}" cy="{q[1]:.2f}" r="2.5" fill="{s.c["fg1"]}"/>')
        u = (q - [PX, PY]) / (np.hypot(*(q - [PX, PY])) or 1)
        s.label(q[0] + u[0] * 16, q[1] + u[1] * 16 + 4, f"{sec} s", 9, "fg2", "ms")
    s.circle(tuple(pts[0]), 4, "fg1")

    s.label(PX, PY + PR + 82, "VISTA SUPERIOR · TRAZA DEL EJE", 13, "fg1", "ms")
    s.label(PX, PY + PR + 100, f"RADIO: INCLINACIÓN · ÁNGULO: ACIMUT · {T_END:.0f} s DE GIRO", 10, "fg2", "ms")

    # The middle column, Hito's card and the HUD to its right: the conditions over the
    # two charts.
    rows = [["CONDICIÓN", "VALOR"], ["GIRO INICIAL", f"{RPM} rpm"], ["INCLINACIÓN INICIAL", f"{THETA0}°"],
            ["AMORTIGUAMIENTO", f"{TAU:.0f} s"], ["PRECESIÓN INICIAL", f"{PERIOD0} s/VUELTA"]]
    table(s, 1004, 104, [164, 108], rows, "CONDICIONES INICIALES")
    plot(s, 1050, 270, t, spin, (0, RPM), [0, 1200, 2400], "GIRO · rpm")
    plot(s, 1050, 410, t, lean, (0, 10), [0, 5, 10], "INCLINACIÓN · °")


def plot(s: Sheet, x0: float, y0: float, t: np.ndarray, v: np.ndarray, lim: tuple[float, float],
         ticks: list[float], title: str) -> None:
    """A small chart, 230 x 90: axes and ticks in fg2, gridlines bg3, the curve in fg1."""
    w, h = 230, 90
    sx = lambda tt: x0 + tt / T_END * w                     # noqa: E731
    sy = lambda vv: y0 + h - (vv - lim[0]) / (lim[1] - lim[0]) * h   # noqa: E731
    s.label(x0 - 46, y0 - 18, title, 12, "fg1", "ls")
    for tick in ticks:
        s.line((x0, sy(tick)), (x0 + w, sy(tick)), "bg3")
        s.label(x0 - 8, sy(tick) + 4, f"{tick:g}", 9, "fg2", "rs")
    for sec in range(0, int(T_END) + 1, 2):
        s.line((sx(sec), y0 + h), (sx(sec), y0 + h + 5), "fg2")
        s.label(sx(sec), y0 + h + 18, f"{sec}", 9, "fg2", "ms")
    s.label(x0 + w + 6, y0 + h + 18, "s", 9, "fg2", "ls")
    s.line((x0, y0), (x0, y0 + h), "fg2")
    s.line((x0, y0 + h), (x0 + w, y0 + h), "fg2")
    s.path("M" + "L".join(xy(sx(a), sy(b)) for a, b in zip(t[::4], v[::4])), "fg1",
           extra=' stroke-linejoin="round"')


def title_block(s: Sheet, cells: list[list[tuple[str, str]]]) -> None:
    """The cajetín: captions in `line`, values in fg2, the title in fg1. `cells` fills
    its three rows (2, 4 and 3 cells; the projection symbol sits in the last row)."""
    x0, y0 = TB
    x1, y1 = TB[0] + 508, TB[1] + 114
    s.add(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="{s.c["bg0"]}"/>')
    rows = [y0, y0 + 46, y0 + 80, y1]
    cols = {0: [x0, x0 + 330, x1], 1: [x0, x0 + 150, x0 + 260, x0 + 380, x1], 2: [x0, x0 + 260, x0 + 380, x1]}
    for r in range(3):
        s.line((x0, rows[r]), (x1, rows[r]), "fg2" if r == 0 else "line")
        for x in cols[r][1:-1]:
            s.line((x, rows[r]), (x, rows[r + 1]), "line")
    s.line((x0, y0), (x0, y1), "fg2")
    for r, row in enumerate(cells):
        for (cap, val), xa in zip(row, cols[r]):
            s.label(xa + 6, rows[r] + 10, cap, 8, "fg2", "lm")
            big = r == 0 and cap == "TÍTULO"
            s.label(xa + 6, rows[r + 1] - 6, val, 22 if big else 12, "fg1" if big else "fg2", "ls")

    # First-angle projection symbol: a truncated cone, its end view beside the wide end.
    mx, my = cols[2][1] + 86, (rows[2] + rows[3]) / 2 + 3
    s.add(f'<g fill="none" stroke="{s.c["fg2"]}" stroke-width="1">'
          f'<path d="M{xy(mx - 30, my - 4)}L{xy(mx - 10, my - 7)}L{xy(mx - 10, my + 7)}L{xy(mx - 30, my + 4)}Z"/>'
          f'<circle cx="{mx + 14}" cy="{my}" r="7"/><circle cx="{mx + 14}" cy="{my}" r="4"/></g>')


def ground(colors: dict) -> np.ndarray:
    """Charcoal: bg0 in the side and bottom margins; the sheet (up to the screen's top)
    a slow falloff from the drawing's middle through Tinta's bg1..bg3, with a whisper of
    grain against banding. Its bottom corners round like the frame's."""
    levels = np.array([colors[k] for k in ("bg0", "bg1", "bg2", "bg3")])[:, 0]
    y, x = (np.mgrid[0:H, 0:W] + 0.5) / UNIT
    inside = (x >= LEFT) & (x <= RIGHT + 1) & (y <= BOTTOM + 1)
    cy = BOTTOM + 1 - CORNER
    for cx, beyond in ((LEFT + CORNER, x < LEFT + CORNER), (RIGHT + 1 - CORNER, x > RIGHT + 1 - CORNER)):
        inside &= ~(beyond & (y > cy) & (np.hypot(x - cx, y - cy) > CORNER))
    fall = np.exp(-(((x - 900) / 820) ** 2 + ((y - 560) / 520) ** 2))
    v = np.where(inside, np.interp(1.3 + 1.3 * fall, np.arange(4), levels), levels[0])
    return v + grain(W, H, seed=7, amount=0.9 / 255)[..., 0]


def rasterise(svg: str) -> np.ndarray:
    png = subprocess.run(["rsvg-convert", "-w", str(W), "-h", str(H)], input=svg.encode(),
                         check=True, capture_output=True, timeout=120).stdout
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"), dtype=np.float64) / 255.0


def letter(labels: list[tuple], colors: dict) -> list[tuple[np.ndarray, np.ndarray]]:
    """(coverage, grey) of every label ink, set at the master's size."""
    fonts: dict[float, ImageFont.FreeTypeFont] = {}
    inks: dict[str, Image.Image] = {}
    for x, y, text, size, ink, anchor, rotate in labels:
        font = fonts.setdefault(size, ImageFont.truetype(str(FONT), size * UNIT, layout_engine=ImageFont.Layout.BASIC))
        layer = inks.setdefault(ink, Image.new("L", (W, H), 0))
        if not rotate:
            ImageDraw.Draw(layer).text((x * UNIT, y * UNIT), text, font=font, fill=255, anchor=anchor)
            continue
        # Read from below: turned a quarter left, its baseline on `x`, centred on `y`.
        box = font.getbbox(text, anchor="ls")
        tile = Image.new("L", (box[2] - box[0] + 4, box[3] - box[1] + 4), 0)
        ImageDraw.Draw(tile).text((2 - box[0], 2 - box[1]), text, font=font, fill=255, anchor="ls")
        tile = tile.transpose(Image.Transpose.ROTATE_90)        # the baseline's row becomes column 2 - box[1]
        layer.paste(255, (round(x * UNIT) - (2 - box[1]), round(y * UNIT - tile.height / 2)), tile)
    return [(np.asarray(img, dtype=np.float64) / 255.0, colors[ink][0]) for ink, img in inks.items()]


def render(source: str) -> Image.Image:
    sheet = Sheet(dict(tokens.load("tinta")["colors"]))
    frame(sheet)
    for draw in SHEETS[source]:
        draw(sheet)

    grey = {k: np.array(colormath.rgb(v), dtype=np.float64) for k, v in sheet.c.items()}
    v = ground(grey)
    art = rasterise(sheet.document())
    v = v * (1 - art[..., 3]) + art[..., :3].mean(-1) * art[..., 3]
    for cov, ink in letter(sheet.labels, grey):
        v = v + (ink - v) * cov
    return finish(np.repeat(np.clip(v, 0, 1)[..., None], 3, axis=2))


def crowded(source: str) -> list[str]:
    """Which desk cards the sheet's drawing (frame and grid left out) comes within
    DESK_CLEAR units of: its line work and labels alone, at the 1920 screen."""
    sheet = Sheet(dict(tokens.load("tinta")["colors"]))
    for draw in SHEETS[source]:
        draw(sheet)
    cov = rasterise(sheet.document())[..., 3]
    for c, _ in letter(sheet.labels, {k: np.zeros(1) for k in sheet.c}):
        cov = np.maximum(cov, c)
    cov = np.asarray(Image.fromarray((cov * 255).astype(np.uint8)).resize(SCREEN, Image.BOX), dtype=np.float64) / 255
    out = []
    for name, (x0, y0, x1, y1) in DESK.items():
        if name in SHARED.get(source, ()):
            continue
        box = cov[max(0, y0 - DESK_CLEAR):y1 + DESK_CLEAR, max(0, x0 - DESK_CLEAR):x1 + DESK_CLEAR]
        if box.max() > 0.05:
            ys, xs = np.nonzero(box > 0.05)
            out.append(f"{name}: ink at x {xs.min() + max(0, x0 - DESK_CLEAR)}..{xs.max() + max(0, x0 - DESK_CLEAR)}, "
                       f"y {ys.min() + max(0, y0 - DESK_CLEAR)}..{ys.max() + max(0, y0 - DESK_CLEAR)}")
    return out


# ── the lock's picture ────────────────────────────────────────────────────────
# hyprlock blurs it hard (3 passes of 7) and sinks it to 0.48 (theme/templates/@tinta/
# hypr/hyprlock.conf): only big shapes survive. The half-section from the sheet, so close
# that the grip runs off the top and the rim off both sides: the time, the portrait and
# the field sit on its black body, a pale paper with the sheet's grid and the degree
# ring round it. 1920x1080, as lock masters are.
LOCK = "assets/wallpapers/tinta-lock.jpg"
LS, LRIM = 2300, 700                                   # px per brand unit; the rim's screen row


def lock_plate() -> Image.Image:
    w, h = SCREEN
    hm = (PROFILE["rimTop"] + PROFILE["rimBot"]) / 2

    def m(side: int):
        return lambda r, hh: (w / 2 + side * r * LS, LRIM - (hh - hm) * LS)

    body = curve(m(-1)) + "L" + curve(m(1), reverse=True)[1:] + "Z"
    section = curve(m(-1)) + f"L{xy(w / 2, LRIM + hm * LS)}L{xy(w / 2, LRIM - (1 - hm) * LS)}Z"
    hatch = "".join(f"M{xy(x, h + 40)}L{xy(x + h + 80, -40)}" for x in np.arange(-h - 80, w / 2 + 40, 34))
    c = (w / 2, LRIM)
    ticks = "".join(
        f"M{xy(c[0] + np.sin(a) * 1060, c[1] - np.cos(a) * 1060)}"
        f"L{xy(c[0] + np.sin(a) * (1060 + (60 if k % 5 == 0 else 28)), c[1] - np.cos(a) * (1060 + (60 if k % 5 == 0 else 28)))}"
        for k, a in enumerate(np.deg2rad(np.arange(0, 360, 2))))
    grid = "".join(f"M{x + 0.5} 0V{h}" for x in range(0, w, 48)) + "".join(f"M0 {y + 0.5}H{w}" for y in range(12, h, 48))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
           f'<defs><radialGradient id="p" cx="0.5" cy="0.42" r="0.75">'
           f'<stop offset="0" stop-color="#cfcfcf"/><stop offset="1" stop-color="#6e6e6e"/></radialGradient>'
           f'<clipPath id="cut"><path d="{section}"/></clipPath></defs>'
           f'<rect width="{w}" height="{h}" fill="url(#p)"/>'
           f'<path d="{grid}" stroke="#000" stroke-opacity="0.16" stroke-width="2"/>'
           f'<circle cx="{c[0]}" cy="{c[1]}" r="1060" fill="none" stroke="#1a1a1a" stroke-width="10"/>'
           f'<path d="{ticks}" stroke="#1a1a1a" stroke-width="7"/>'
           f'<path d="{body}" fill="#0b0b0b" stroke="#e6e6e6" stroke-width="5"/>'
           f'<path d="{hatch}" stroke="#4a4a4a" stroke-width="7" clip-path="url(#cut)"/>'
           f'<path d="M{w / 2} 0V{h}" stroke="#8c8c8c" stroke-width="5" stroke-dasharray="90 18 10 18"/>'
           f'</svg>')
    png = subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h)], input=svg.encode(),
                         check=True, capture_output=True, timeout=120).stdout
    with Image.open(io.BytesIO(png)) as im:
        v = np.asarray(im.convert("L"), dtype=np.float64) / 255.0
    # The old picture's scanlines, and grain against banding.
    v = v * (1 - 0.06 * (np.arange(w) % 4 == 0))[None, :] + grain(w, h, seed=9, amount=1.2 / 255)[..., 0]
    return finish(np.repeat(np.clip(v, 0, 1)[..., None], 3, axis=2))


def cells(title: str, number: str, scale: str, rev: str, units: str) -> list[list[tuple[str, str]]]:
    return [[("TÍTULO", title), ("Nº PLANO", number)],
            [("PROYECTO", "RYCE"), ("ESCALA", scale), ("REV", rev), ("HOJA", "1/1")],
            [("COTAS", units), ("MÉTODO", "ISO-E"), ("FECHA", "2026.11")]]


# Each master (as tinta's wallpaper.alternates lists it) and what is drawn on its sheet.
SHEETS = {
    "assets/wallpapers/tinta-plano.jpg": [
        elevation, plan, strobe,
        lambda s: title_block(s, cells("PEONZA", "RY-PZ-001", "2:1", "D", "h PUNTA-MANGO = 1"))],
    "assets/wallpapers/tinta-despiece.jpg": [
        exploded, lambda s: title_block(s, cells("DESPIECE", "RY-PZ-002", "1:1", "A", "h PUNTA-MANGO = 1"))],
    "assets/wallpapers/tinta-estela.jpg": [
        estela, lambda s: title_block(s, cells("ESTELA", "RY-PZ-003", f"10° = {PR}", "A", "GRADOS Y SEGUNDOS"))],
}


# ── checks ────────────────────────────────────────────────────────────────────
def brand_drift() -> str | None:
    """How the brand's PROFILE differs from ours, if the brand repo is here."""
    if not GEOMETRY.exists():
        return None
    block = re.search(r"PROFILE = \{(.*?)\n\};", GEOMETRY.read_text(encoding="utf-8"), re.S)
    if not block:
        return f"{GEOMETRY}: no PROFILE block"
    theirs = {k: [float(n) for n in re.findall(r"[\d.]+", v)]
              for k, v in re.findall(r"^\s*(\w+):\s*(\[[^\]]*\]|[\d.]+)", block.group(1), re.M)}
    ours = {k: v if isinstance(v, list) else [v] for k, v in PROFILE.items()}
    return None if theirs == ours else f"PROFILE differs from {GEOMETRY}: {theirs}"


def luma(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float64) @ np.array([0.2126, 0.7152, 0.0722])


def measure(path: Path) -> dict:
    """The BUDGET's quantities on one decoded picture."""
    y = luma(path)
    h, w = y.shape
    k = h / 1080
    b = round(16 * k)
    blocks = y[:h // b * b, :w // b * b].reshape(h // b, b, w // b, b).mean((1, 3))
    gx, gy = np.abs(np.diff(y, axis=1))[:-1, :], np.abs(np.diff(y, axis=0))[:, :-1]
    bar = y[:round(BAR * k)]
    return {"mean": y.mean(), "p50": np.percentile(y, 50), "p99": np.percentile(y, 99),
            "over200": 100 * (y > 200).mean(), "block16": blocks.max(),
            "edges": 100 * (np.hypot(gx, gy) > 96).mean(),
            "bar_mean": bar.mean(), "bar_p99": np.percentile(bar, 99)}


def over_budget(m: dict) -> list[str]:
    lo, hi = BUDGET["mean"]
    bad = [] if lo <= m["mean"] <= hi else [f"mean {m['mean']:.1f} outside {lo}-{hi}"]
    return bad + [f"{k} {m[k]:.2f} > {BUDGET[k]}" for k in BUDGET if k != "mean" and m[k] > BUDGET[k]]


# Where the frame is looked for in a deployed 1920 copy: rows (for the sides) and
# columns (for the top and bottom) clear of zone ticks, labels, grid lines and drawings.
PROBE_ROWS, PROBE_COLS = (TOP + 100, TOP + 642, TOP + 900), (LEFT + 252, LEFT + 732, LEFT + 1212)


def frame_found(y: np.ndarray) -> tuple[list[int], list[str]]:
    """[left, top, right, bottom] px of the frame in a 1920x1080 luma picture: on each
    side, the brightest line within 10 px of where it should be, at every probe; it must
    stand 12 levels over both neighbours and agree across the probes."""
    found, why = [], []
    sides = [("left", LEFT, lambda i, p: y[p, i]), ("top", TOP, lambda i, p: y[i, p]),
             ("right", RIGHT, lambda i, p: y[p, i]), ("bottom", BOTTOM, lambda i, p: y[i, p])]
    for name, want, at in sides:
        probes = PROBE_ROWS if name in ("left", "right") else PROBE_COLS
        hits = set()
        for p in probes:
            span = np.arange(want - 10, want + 11)
            vals = np.array([at(i, p) for i in span])
            i = int(span[np.argmax(vals)])
            if not at(i, p) - max(at(i - 1, p), at(i + 1, p)) >= 12:
                why.append(f"{name} edge at {i} (probe {p}) does not stand out")
            hits.add(i)
        if len(hits) != 1:
            why.append(f"{name} edge wanders: {sorted(hits)}")
        found.append(min(hits))
    return found, why


def deployed(source: str) -> list[Path]:
    """The copies scenes.py writes for one of tinta's sheets: alt-<n>/ for an alternate,
    wallpaper/ itself when the sheet is the main picture (the public export's despiece)."""
    wp = tokens.load("tinta")["wallpaper"]
    d = ROOT / "themes" / "tinta" / "wallpaper"
    if source != wp["source"]:
        d = d / f"alt-{wp['alternates'].index(source) + 1}"
    return [d / f"{w}x{h}.jpg" for w, h in ((1920, 1080), (2560, 1440))]


# The lock's text (fg0) over the brightest 16 px block of the centre column, once
# hyprlock has sunk the picture to this brightness (blur only lowers the peak).
LOCK_COLUMN, LOCK_BRIGHTNESS = (760, 1160), 0.48


def lock_contrast(path: Path) -> float:
    y = luma(path)[:, slice(*LOCK_COLUMN)]
    b = 16
    peak = y[:y.shape[0] // b * b, :y.shape[1] // b * b].reshape(y.shape[0] // b, b, -1, b).mean((1, 3)).max()
    grey = "#%02x%02x%02x" % ((round(peak * LOCK_BRIGHTNESS),) * 3)
    return colormath.contrast(tokens.load("tinta")["colors"]["fg0"], grey)


def check(sources: list[str]) -> int:
    fails = []
    why = differs(ROOT / LOCK, lock_plate())
    if why:
        fails.append(f"stale: {LOCK}: {why} (run python3 theme/wallpaper/ink.py)")
    shipped = ROOT / "themes" / "tinta" / "wallpaper" / "lock.jpg"
    if shipped.exists():
        ratio = lock_contrast(shipped)
        print(f"ink: {shipped.relative_to(ROOT)}: the time over the lock's brightest centre {ratio:.2f}:1")
        if ratio < 4.5:
            fails.append(f"lock: {shipped.relative_to(ROOT)}: fg0 at {ratio:.2f}:1 over its centre column, under 4.5")
    drift = brand_drift()
    if drift:
        fails.append(f"brand: {drift} (copy it into ink.py's PROFILE and re-render)")
    x, y, w, h = window()
    want = [x, y, x + w - 1, y + h - 1]
    for source in sources:
        why = differs(ROOT / source, render(source))
        if why:
            fails.append(f"stale: {source}: {why} (run python3 theme/wallpaper/ink.py)")
        fails += [f"desk: {source}: {b} (keep {DESK_CLEAR} units clear of the card)" for b in crowded(source)]
        for path in deployed(source):
            rel = path.relative_to(ROOT)
            if not path.exists():
                fails.append(f"missing: {rel} (run python3 theme/wallpaper/scenes.py)")
                continue
            m = measure(path)
            print(f"ink: {rel}: " + " ".join(f"{k} {v:.2f}" for k, v in m.items()))
            fails += [f"over budget: {rel}: {b}" for b in over_budget(m)]
            if path.stem == "1920x1080":
                got, why = frame_found(luma(path))
                print(f"ink: {rel}: frame {got}, tiled window's outer px {want}")
                fails += [f"frame: {rel}: {b}" for b in why]
                if got != want:
                    fails.append(f"frame: {rel}: at {got}, the tiled window's edge is {want}")
    for f in fails:
        print(f)
    if not fails:
        print("ink: ok")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if a master is stale, a copy is over budget or its frame misses the window")
    ap.add_argument("--only", choices=[Path(s).stem for s in [*SHEETS, LOCK]], help="one picture")
    ap.add_argument("--out", type=Path, help="write the sheet(s) into this folder instead of assets/wallpapers/")
    a = ap.parse_args(argv)
    if a.check:
        if a.only or a.out:
            ap.error("--check takes no --only/--out: it checks everything")
        return check(list(SHEETS))
    for source in [*SHEETS, LOCK]:
        if a.only and Path(source).stem != a.only:
            continue
        out = (a.out / Path(source).name) if a.out else ROOT / source
        save(out, lock_plate() if source == LOCK else render(source))
        print(f"wrote {out}")
    if not a.out:
        print("now run python3 theme/wallpaper/scenes.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
