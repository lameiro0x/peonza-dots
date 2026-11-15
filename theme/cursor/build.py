#!/usr/bin/env python3
"""Build assets/cursors/ryce-peonza: the mouse cursor, drawn from the peonza.

The pointer IS the spinning top, the `wait` cursor's own figure turned over 35 degrees off
vertical: its sharp tip leads up and to the left and is the hotspot, the disc and the grip,
shortened to a round knob, trail down and to the right.
Every other shape (hand, I-beam, arrows, badges) speaks the same language, so the cursor
holds up on any ground (white, the cream paper, Ola's sage, grey, black): a film-black
fill, a bone outline 1/16 of the size wide (2 px at 32), a soft shadow under it, and bone
cuts inside the fill (the brand's crescent under the disc's face, the fingers). `wait` is
the top upright as the brand draws it, spinning on its tip: studs run round its rim and
the axis precesses, so the spin reads although the solid is round; `progress` is the
pointer, smaller, with that spinning top beside its grip.

The shape is the brand's measured profile (~/Repos/logo-peonza/src/geometry.mjs,
PROFILE; theme/cursor/tests checks the copy below against it when the brand is there)
seen from CAMERA degrees above its rim: the union of the circles of the solid of
revolution, each an ellipse on screen.

One theme folder, two formats, one name (Hyprland draws hyprcursor; GTK, Qt, XWayland
and the greeter's cage read XCursor):

    index.theme         [Icon Theme], Inherits=Adwaita for the few names not drawn here
    cursors/            XCursor files at 24, 32, 48 and 64 px; every alias is a byte copy
                        of its drawn file, never a link: install/boot/stage.py, root's
                        only reader of the repo, refuses symbolic and hard links (git
                        stores the copies as one blob)
    manifest.hl         hyprcursor manifest
    hyprcursors/*.hlc   hyprcursor shapes (meta.hl + PNGs, hotspots as fractions, the
                        aliases as define_override), compiled by `hyprcursor-util --create`
                        and re-zipped with fixed timestamps so a rebuild is byte-identical

    python3 theme/cursor/build.py                write the theme
    python3 theme/cursor/build.py --check        exit 1 if a committed file is stale,
                                                 missing or stray (pixels compared with a
                                                 tolerance of 2; no hyprcursor-util needed)
    python3 theme/cursor/build.py --sheet PNG    contact sheet: every shape at 24/32/48 on
                                                 six grounds, the animations frame by frame

Build-time only (python-pillow, python-numpy, hyprcursor for hyprcursor-util); the
committed theme is what deploys (install/links.tsv, install/boot-setup.sh). Every
hotspot is a multiple of 1/8, so it lands on a whole pixel at every size.
"""

from __future__ import annotations

import io
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
NAME = "ryce-peonza"
OUT = ROOT / "assets" / "cursors" / NAME
SIZES = (24, 32, 48, 64)
SS = 4                      # supersampling of the vector drawing
TOLERANCE = 2               # --check: max channel difference that is not "stale"

INK = (236, 231, 222)       # the brand's bone, --peonza-ink
FILL = (12, 10, 8)          # the brand's film black, --peonza-ground
OUTLINE = 1 / 16            # bone outline, as a fraction of the size
CUT = 1 / 28                # bone lines inside the fill
SHADOW = (1 / 40, 1 / 20, 1 / 24, 0.42)   # dx, dy, blur radius (fractions), opacity

# The measured profile, copied from logo-peonza src/geometry.mjs PROFILE: (r, h), tip at the
# origin, top of the grip at h = 1.
PROFILE = {
    "rim": 0.488, "rimTop": 0.356, "rimBot": 0.332, "cap": 0.036,
    "horn": (0.040, 0.70, 0.17, 0.378),
    "under": (0.36, 0.305, 0.26, 0.24),
    "waist": (0.205, 0.192),
    "cone": (0.135, 0.112, 0.040, 0.0),
}
CAMERA = 10                 # degrees above the rim plane, as the brand (src/pose.mjs CAMERA)

FRAMES = 18                 # one loop of progress and wait
DELAY = 55                  # ms a frame: one precession and 2/3 of a turn a second


# --- the peonza ----------------------------------------------------------------------------

def _segments(p: dict = PROFILE) -> list[tuple[float, ...]]:
    k = 0.5523 * p["cap"]
    cap_y = 1 - p["cap"]
    rim, top, bot = p["rim"], p["rimTop"], p["rimBot"]
    return [
        (0, 1, k, 1, p["cap"], cap_y + k, p["cap"], cap_y),
        (p["cap"], cap_y, *p["horn"], rim, top),
        (rim, top, rim, top - 0.008, rim, bot + 0.008, rim, bot),
        (rim, bot, *p["under"], *p["waist"]),
        (*p["waist"], *p["cone"], 0, 0),
    ]


def profile(n: int = 40) -> list[tuple[float, float]]:
    """(r, h) samples from the top of the grip down to the tip."""
    out = []
    for g in _segments():
        for i in range(n):
            t = i / n
            u = 1 - t
            w = (u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t)
            out.append((sum(c * g[2 * j] for j, c in enumerate(w)), sum(c * g[2 * j + 1] for j, c in enumerate(w))))
    out.append((0.0, 0.0))
    return out


PROFILE_PTS = profile()


class Top:
    """The peonza on screen: tip at `tip`, `length` from tip to grip, its axis `angle`
    degrees clockwise from straight up (180 = tip up), seen `camera` degrees above the rim.
    `wall` deepens the disc's edge below its rim (a share of the height), as the brand does
    at small sizes (src/opsz.mjs `wall`) so the disc reads as a solid one. `point`, `grip`
    and `knob` bend the drawing for the pointer (see lift() and body())."""

    def __init__(self, tip, length, angle, camera=CAMERA, wall=0.0, point=1.0, grip=1.0, knob=0.0):
        self.tip, self.k, self.wall, self.point, self.grip, self.knob = tip, length, wall, point, grip, knob
        a, c = math.radians(angle), math.radians(camera)
        self.cos, self.sin, self.sa, self.ca = math.cos(a), math.sin(a), math.sin(c), math.cos(c)

    def at(self, x: float, y: float) -> tuple[float, float]:
        """Peonza-local (x right, y down, tip at 0) to the canvas."""
        x, y = x * self.k, y * self.k
        return (self.tip[0] + x * self.cos - y * self.sin, self.tip[1] + x * self.sin + y * self.cos)

    def lift(self, h: float) -> float:
        """Height with the lower cone stretched by `point` and the grip above the disc's
        face shrunk by `grip` (1, 1: as measured)."""
        waist, face = PROFILE["waist"][1], PROFILE["rimTop"]
        if h < waist:
            return h * self.point
        return h + waist * (self.point - 1) - max(h - face, 0) * (1 - self.grip)

    def on(self, r: float, h: float, theta: float) -> tuple[float, float]:
        """The point of the solid at radius r, height h, azimuth theta (0 faces the camera)."""
        return self.at(r * math.sin(theta), -self.lift(h) * self.ca + r * math.cos(theta) * self.sa)

    def circle(self, r: float, h: float, n: int = 40) -> list[tuple[float, float]]:
        return [self.on(r, h, 2 * math.pi * i / n) for i in range(n)]

    def body(self) -> list:
        """The silhouette: the profile seen side on (both limbs), the circles of the solid
        for the disc's depth (the tip's are tiny), the wall under the rim, and a round knob
        of radius `knob` on the grip's end."""
        limb = [(r, -self.lift(h) * self.ca) for r, h in PROFILE_PTS]
        side = [self.at(x, y) for x, y in limb] + [self.at(-x, y) for x, y in reversed(limb)]
        rim, bot = PROFILE["rim"], PROFILE["rimBot"]
        wall = [("add", self.circle(rim, bot - self.wall * i / 4)) for i in range(1, 5)] if self.wall else []
        knob = [("add", ring(*self.at(0, -self.lift(1) * self.ca), self.knob * self.k, 24))] if self.knob else []
        return [("add", side)] + [("add", self.circle(max(r, 0.004), h)) for r, h in PROFILE_PTS[::4]] + wall + knob

    def crescent(self, depth: float = 0.07, ends: float = 0.86) -> list[tuple[float, float]]:
        """The brand's cut under the front edge of the disc's face: bone between the rim and
        an arc `depth` lower at the middle, tapering to nothing at `ends` of the half-width."""
        top, t0 = PROFILE["rimTop"], math.asin(ends)
        ts = [-t0 + 2 * t0 * i / 24 for i in range(25)]
        upper = [self.on(PROFILE["rim"], top, t) for t in ts]
        lower = [self.on(PROFILE["rim"], top - depth * (math.cos(t) - math.cos(t0)) / (1 - math.cos(t0)), t)
                 for t in reversed(ts)]
        return upper + lower

    def studs(self, theta: float, n: int = 3, r: float = 0.05) -> list:
        """`n` bone studs round the rim, the first at azimuth `theta`; only the near ones show."""
        out = []
        for i in range(n):
            t = theta + 2 * math.pi * i / n
            if math.cos(t) > 0.2:
                x, y = self.on(PROFILE["rim"] * 0.93, PROFILE["rimBot"] - self.wall / 2, t)
                out.append(("mark", ring(x, y, r * self.k * (0.55 + 0.45 * math.cos(t)), 12)))
        return out


# --- drawing -------------------------------------------------------------------------------
# A shape is a list of ops on the unit square: ("add", polygon) / ("cut", polygon) build the
# fill; ("line", points, width) and ("mark", polygon) are bone cuts inside it. The outline is the fill grown by
# OUTLINE (each polygon stroked with round joins), the shadow is the whole cursor, blurred.

def ring(cx, cy, r, n=48, start=0.0):
    return [(cx + r * math.cos(start + 2 * math.pi * i / n), cy + r * math.sin(start + 2 * math.pi * i / n))
            for i in range(n)]


def capsule(p0, p1, r, n=12):
    (x0, y0), (x1, y1) = p0, p1
    a = math.atan2(y1 - y0, x1 - x0)
    out = [(x1 + r * math.cos(a - math.pi / 2 + math.pi * i / n), y1 + r * math.sin(a - math.pi / 2 + math.pi * i / n))
           for i in range(n + 1)]
    out += [(x0 + r * math.cos(a + math.pi / 2 + math.pi * i / n), y0 + r * math.sin(a + math.pi / 2 + math.pi * i / n))
            for i in range(n + 1)]
    return out


def rrect(x0, y0, x1, y1, r, n=6):
    out = []
    for cx, cy, a in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        out += [(cx + r * math.cos(math.radians(a + 90 * i / n)), cy + r * math.sin(math.radians(a + 90 * i / n)))
                for i in range(n + 1)]
    return out


def turn(pts, deg, cx=0.5, cy=0.5):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def turn_ops(ops, deg, cx=0.5, cy=0.5):
    return [(o[0], turn(o[1], deg, cx, cy), *o[2:]) for o in ops]


def render(ops: list, size: int) -> Image.Image:
    """The ops at `size` px: RGBA, straight alpha."""
    px = size * SS
    sc = lambda pts: [(x * px, y * px) for x, y in pts]  # noqa: E731
    grow = OUTLINE * px
    fill = Image.new("L", (px, px), 0)
    edge = Image.new("L", (px, px), 0)
    cuts = Image.new("L", (px, px), 0)
    df, de, dc = ImageDraw.Draw(fill), ImageDraw.Draw(edge), ImageDraw.Draw(cuts)
    for op in ops:
        kind, pts = op[0], sc(op[1])
        if kind == "mark":   # a bone patch inside the fill
            dc.polygon(pts, fill=255)
            continue
        if kind == "line":
            w = op[2] * px
            dc.line(pts, fill=255, width=max(1, round(w)), joint="curve")
            for x, y in (pts[0], pts[-1]):
                dc.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=255)
            continue
        loop = pts + pts[:2]
        if kind == "add":
            df.polygon(pts, fill=255)
            de.polygon(pts, fill=255)
            de.line(loop, fill=255, width=round(2 * grow), joint="curve")
        else:  # cut: a hole, its edge drawn as outline
            df.polygon(pts, fill=0)
            de.polygon(pts, fill=0)
            de.line(loop, fill=255, width=round(2 * grow), joint="curve")
    a_fill = np.asarray(fill, np.float32) / 255
    a_edge = np.maximum(np.asarray(edge, np.float32) / 255, a_fill)
    a_cut = np.asarray(cuts, np.float32) / 255 * a_fill
    # Premultiplied: bone where the outline shows, film black over the fill, bone cuts in it.
    t = a_fill * (1 - a_cut)
    rgb = np.array(INK, np.float32) * (a_edge - t)[..., None] + np.array(FILL, np.float32) * t[..., None]
    hi = np.dstack([rgb, a_edge * 255])
    lo = hi.reshape(size, SS, size, SS, 4).mean(axis=(1, 3))   # box filter down to the size
    alpha = lo[..., 3:4]
    straight = np.where(alpha > 0, lo[..., :3] / np.maximum(alpha / 255, 1e-6), 0)
    img = Image.fromarray(np.dstack([np.clip(straight, 0, 255), alpha]).round().astype(np.uint8), "RGBA")
    return _shadow(img, size)


def _shadow(img: Image.Image, size: int) -> Image.Image:
    dx, dy, blur, opacity = SHADOW
    a = img.getchannel("A")
    sh = Image.new("L", a.size, 0)
    sh.paste(a, (round(dx * size), round(dy * size)))
    sh = sh.filter(ImageFilter.GaussianBlur(blur * size)).point(lambda v: round(v * opacity))
    base = Image.merge("RGBA", (*(Image.new("L", a.size, 0),) * 3, sh))
    return Image.alpha_composite(base, img)


# --- the shapes ----------------------------------------------------------------------------

HOT = (1 / 4, 1 / 4)        # the pointer's tip, clear of the corner for the disc's wings
TILT = 145                  # the pointer's axis, degrees clockwise from up (180: tip straight up)
REACH = 0.70                # the measured height, as a fraction of the size
LOOK = 16                   # seen from above its rim: the disc an ellipse 0.28 as tall as wide
POINT = 3.0                 # the lower cone drawn this much longer: the one sharp end, leading
GRIP = 0.4                  # the grip above the disc's face drawn this much shorter...
KNOB = 0.09                 # ...and ended in a round knob of this radius (a share of the height)
WALL = 0.06                 # the disc's edge, deepened as the brand does at small sizes
CRESCENT = 0.065            # the brand's cut under the disc face's near edge


def peonza_pointer(reach: float = REACH, tilt: float = TILT, look: float = LOOK, tip=HOT) -> list:
    """The `wait` top turned over, 35 degrees off vertical, its tip up and to the left as the
    hotspot, the disc and the grip trailing down and to the right. Turned over, the brand's
    tall tapering grip read as the point and the short tip as the tail (the cursor looked
    upside down), so the drawing bends as the brand's does at small sizes (src/opsz.mjs):
    the lower cone POINT times longer, the grip GRIP as tall ending in a round knob. The tip
    is the figure's furthest point up-left and the only sharp end of its axis."""
    top = Top(tip, reach, tilt, look, wall=WALL, point=POINT, grip=GRIP, knob=KNOB)
    return top.body() + [("mark", top.crescent(CRESCENT))]


def badge(cx, cy, r) -> list:
    return [("add", ring(cx, cy, r))]


B = (0.72, 0.72, 0.17)      # where a pointer's badge sits


def plus(cx, cy, r, w):
    return [("line", [(cx - r, cy), (cx + r, cy)], w), ("line", [(cx, cy - r), (cx, cy + r)], w)]


def help_mark(cx, cy, s):
    arc = [(cx + s * 0.55 * math.cos(math.radians(a)), cy - s * 0.45 + s * 0.5 * math.sin(math.radians(a)))
           for a in range(190, 400, 15)]
    return [("line", arc + [(cx, cy + s * 0.12)], s * 0.32), ("line", [(cx, cy + s * 0.62), (cx, cy + s * 0.63)], s * 0.36)]


def hand(fingers: str) -> list:
    """`point`: index up (hotspot at its tip); `open`: all four up; `fist`: knuckles."""
    ops = [("add", rrect(0.27, 0.46, 0.75, 0.88, 0.14))]
    if fingers == "point":
        ops += [("add", capsule((0.375, 0.20), (0.375, 0.56), 0.075))]
        for x, top in ((0.505, 0.47), (0.62, 0.50)):
            ops += [("add", capsule((x, top), (x, 0.60), 0.068))]
        ops += [("add", capsule((0.30, 0.66), (0.17, 0.53), 0.066))]
        ops += [("line", [(0.44, 0.50), (0.44, 0.63)], CUT), ("line", [(0.565, 0.53), (0.565, 0.64)], CUT)]
    elif fingers == "open":
        for x, top in ((0.33, 0.20), (0.445, 0.15), (0.56, 0.17), (0.675, 0.25)):
            ops += [("add", capsule((x, top), (x, 0.58), 0.06))]
        ops += [("add", capsule((0.30, 0.70), (0.17, 0.52), 0.062))]
        ops += [("line", [(x, 0.36), (x, 0.56)], CUT * 0.9) for x in (0.39, 0.5, 0.615)]
    else:  # fist
        for x in (0.33, 0.445, 0.56, 0.675):
            ops += [("add", capsule((x, 0.40), (x, 0.52), 0.062))]
        ops += [("add", capsule((0.30, 0.68), (0.20, 0.58), 0.06))]
        ops += [("line", [(x, 0.40), (x, 0.52)], CUT * 0.9) for x in (0.39, 0.5, 0.615)]
    return ops


def arrow2(length=0.74, shaft=0.10, head=0.34, head_len=0.2) -> list:
    """A double arrow along x, centred."""
    x0, x1 = 0.5 - length / 2, 0.5 + length / 2
    h, s = head / 2, shaft / 2
    return [("add", [(x0, 0.5), (x0 + head_len, 0.5 - h), (x0 + head_len, 0.5 - s), (x1 - head_len, 0.5 - s),
                     (x1 - head_len, 0.5 - h), (x1, 0.5), (x1 - head_len, 0.5 + h), (x1 - head_len, 0.5 + s),
                     (x0 + head_len, 0.5 + s), (x0 + head_len, 0.5 + h)])]


def split() -> list:
    """col-resize: a double arrow cut by two bars."""
    ops = [o for o in arrow2(0.82)]
    ops += [("add", rrect(0.43, 0.2, 0.47, 0.8, 0.02)), ("add", rrect(0.53, 0.2, 0.57, 0.8, 0.02))]
    return ops


def fleur(dot: bool) -> list:
    ops = arrow2(0.8, head=0.26, head_len=0.15) + turn_ops(arrow2(0.8, head=0.26, head_len=0.15), 90)
    if dot:
        ops += [("cut", ring(0.5, 0.5, 0.06))]
    return ops


def ibeam() -> list:
    w, top, bot = 0.045, 0.16, 0.84
    return [("add", rrect(0.5 - w, top + 0.02, 0.5 + w, bot - 0.02, 0.02)),
            ("add", capsule((0.36, top), (0.64, top), 0.04)),
            ("add", capsule((0.36, bot), (0.64, bot), 0.04))]


def crosshair() -> list:
    w, g = 0.03, 0.09
    ops = []
    for (x0, y0, x1, y1) in ((0.5, 0.14, 0.5, 0.5 - g), (0.5, 0.5 + g, 0.5, 0.86),
                             (0.14, 0.5, 0.5 - g, 0.5), (0.5 + g, 0.5, 0.86, 0.5)):
        ops.append(("add", capsule((x0, y0), (x1, y1), w)))
    return ops + [("add", ring(0.5, 0.5, 0.035, 16))]


def not_allowed(cx=0.5, cy=0.5, r=0.32) -> list:
    w = r * 0.28
    slash = turn(rrect(cx - r + w * 0.5, cy - w / 2, cx + r - w * 0.5, cy + w / 2, w / 2), 45, cx, cy)
    return [("add", ring(cx, cy, r)), ("cut", ring(cx, cy, r - w)), ("add", slash)]


def magnifier(sign: str) -> list:
    c, r = 0.375, 0.24
    ops = [("add", capsule((c + 0.18, c + 0.18), (0.82, 0.82), 0.075)), ("add", ring(c, c, r))]
    ops += [("line", [(c - 0.11, c), (c + 0.11, c)], 0.06)]
    if sign == "+":
        ops += [("line", [(c, c - 0.11), (c, c + 0.11)], 0.06)]
    return ops


def menu(cx, cy) -> list:
    ops = [("add", rrect(cx - 0.17, cy - 0.15, cx + 0.17, cy + 0.15, 0.04))]
    return ops + [("line", [(cx - 0.09, cy + d), (cx + 0.09, cy + d)], CUT * 1.2) for d in (-0.07, 0, 0.07)]


def alias_mark(cx, cy, s):
    arc = [(cx - s * 0.1 + s * 0.42 * math.cos(math.radians(a)), cy + s * 0.25 + s * 0.42 * math.sin(math.radians(a)))
           for a in range(180, 271, 15)]
    tip = (cx + s * 0.45, cy - s * 0.17)
    return [("line", arc + [tip], s * 0.24), ("line", [(tip[0] - s * 0.25, tip[1] - s * 0.22), tip,
                                                         (tip[0] - s * 0.25, tip[1] + s * 0.22)], s * 0.24)]


LEAN = 9                    # wait/progress: how far the spinning top leans as it precesses
STUDS = 3                   # bone studs round its rim; they turn 2/3 of a turn a loop


def spinner(i: int, n: int = FRAMES, tip=(0.5, 0.88), length: float = 0.74) -> list:
    """The top upright as the brand draws it, spinning on its tip: the studs run round the
    near side of the rim, and the axis precesses once a loop (it sways side to side as the
    disc opens and shuts), so the spin reads although the solid is round."""
    phase = 2 * math.pi * i / n
    top = Top(tip, length, LEAN * math.sin(phase), CAMERA + 4 + LEAN * math.cos(phase), wall=WALL)
    return top.body() + [("mark", top.crescent(CRESCENT))] + top.studs(-4 * math.pi / 3 * i / n, STUDS)


def busy(i: int, n: int = FRAMES) -> list:
    """`progress`: the pointer, smaller, with the spinning top beside its grip."""
    return peonza_pointer(0.46) + spinner(i, n, tip=(0.68, 0.88), length=0.36)


Shape = tuple  # (frames: list[ops], hotspot)
CENTRE = (0.5, 0.5)
SHAPES: dict[str, Shape] = {
    "default": ([peonza_pointer()], HOT),
    "context-menu": ([peonza_pointer() + menu(0.70, 0.74)], HOT),
    "help": ([peonza_pointer() + badge(*B) + help_mark(B[0], B[1], B[2])], HOT),
    "alias": ([peonza_pointer() + badge(*B) + alias_mark(B[0], B[1], B[2])], HOT),
    "copy": ([peonza_pointer() + badge(*B) + plus(B[0], B[1], B[2] * 0.5, B[2] * 0.3)], HOT),
    "no-drop": ([peonza_pointer() + not_allowed(*B)], HOT),
    "progress": ([busy(i) for i in range(FRAMES)], HOT),
    "wait": ([spinner(i) for i in range(FRAMES)], CENTRE),
    "pointer": ([hand("point")], (3 / 8, 1 / 8)),
    "grab": ([hand("open")], CENTRE),
    "grabbing": ([hand("fist")], CENTRE),
    "text": ([ibeam()], CENTRE),
    "vertical-text": ([turn_ops(ibeam(), 90)], CENTRE),
    "crosshair": ([crosshair()], CENTRE),
    "cell": ([[("add", capsule((0.5, 0.2), (0.5, 0.8), 0.075)), ("add", capsule((0.2, 0.5), (0.8, 0.5), 0.075))]], CENTRE),
    "move": ([fleur(False)], CENTRE),
    "all-scroll": ([fleur(True)], CENTRE),
    "not-allowed": ([not_allowed()], CENTRE),
    "ew-resize": ([arrow2()], CENTRE),
    "ns-resize": ([turn_ops(arrow2(), 90)], CENTRE),
    "nwse-resize": ([turn_ops(arrow2(0.84), 45)], CENTRE),
    "nesw-resize": ([turn_ops(arrow2(0.84), -45)], CENTRE),
    "col-resize": ([split()], CENTRE),
    "row-resize": ([turn_ops(split(), 90)], CENTRE),
    "zoom-in": ([magnifier("+")], (3 / 8, 3 / 8)),
    "zoom-out": ([magnifier("-")], (3 / 8, 3 / 8)),
    "right_ptr": ([peonza_pointer(0.62, 360 - TILT, tip=(3 / 4, 1 / 4))], (3 / 4, 1 / 4)),
    "center_ptr": ([peonza_pointer(0.60, 180, LOOK, (0.5, 1 / 8))], (0.5, 1 / 8)),
}

# Every other name a client may ask for -> the drawn shape. The cursor-shape-v1 names
# (Wayland), the legacy X11 names and the hashes Qt/GTK2 ask for, as in capitaine-cursors.
ALIASES: dict[str, tuple[str, ...]] = {
    "default": ("left_ptr", "arrow", "top_left_arrow", "x-cursor", "X_cursor", "wayland-cursor"),
    "context-menu": ("dnd-ask",),
    "help": ("left_ptr_help", "question_arrow", "whats_this",
             "5c6cd98b3f3ebcb1f9c7f1c204630408", "d9ce0ab605698f320427677b458ad60b"),
    "pointer": ("hand", "hand1", "hand2", "pointing_hand",
                "9d800788f1b08800ae810202380a0822", "e29285e634086352946a0e7090d73106"),
    "progress": ("left_ptr_watch", "half-busy", "00000000000000020006000e7e9ffc3f",
                 "08e8e1c95fe2fc01f976f1e063a24ccd", "3ecb610c1bf2410f44200f48c40d3599"),
    "wait": ("watch",),
    "cell": ("plus",),
    "crosshair": ("cross", "tcross", "cross_reverse", "diamond_cross"),
    "text": ("xterm", "ibeam"),
    "alias": ("link", "dnd-link", "3085a0e285430894940527032f8b26df",
              "640fb0e74195791501fd1ed57b41487f", "a2a266d0498c3104214a47bd64ab0fc8"),
    "copy": ("dnd-copy", "1081e37283d90000800003c07f3ef6bf", "6407b0e94181790501fd1e167b474872",
             "b66166c04f8c3109214a4fbd64a50fc8"),
    "move": ("fleur", "size_all", "all-resize", "4498f0e0c1937ffe01fd06f973665830",
             "9081237383d90e509aa00f00170e968f"),
    "grab": ("openhand",),
    "grabbing": ("closedhand", "dnd-move", "dnd-none", "fcf21c00b30f7e3f83fe0dfd12e71cff"),
    "no-drop": ("dnd-no-drop", "forbidden"),
    "not-allowed": ("circle", "crossed_circle", "03b6e0fcb3499374a867c041f52298f0"),
    "ew-resize": ("e-resize", "w-resize", "size_hor", "h_double_arrow", "sb_h_double_arrow",
                  "left_side", "right_side", "028006030e0e7ebffc7f7070c0600140"),
    "ns-resize": ("n-resize", "s-resize", "size_ver", "v_double_arrow", "sb_v_double_arrow",
                  "top_side", "bottom_side", "00008160000006810000408080010102"),
    "nwse-resize": ("nw-resize", "se-resize", "size_fdiag", "top_left_corner", "bottom_right_corner",
                    "ul_angle", "lr_angle", "fd_double_arrow", "c7088f0f3e6c8088236ef8e1e3e70000"),
    "nesw-resize": ("ne-resize", "sw-resize", "size_bdiag", "top_right_corner", "bottom_left_corner",
                    "ur_angle", "ll_angle", "bd_double_arrow", "fcf1c3c7cd4491d801f1e1c78f100000"),
    "col-resize": ("split_h", "14fef782d02440884392942c11205230"),
    "row-resize": ("split_v", "2870a09082c103050810ffdffffe0204"),
}


# --- XCursor -------------------------------------------------------------------------------
# libXcursor's file format: a header, a table of contents, then one image chunk per size and
# frame (ARGB, premultiplied, little-endian), frames of one size in order with their delay.
XC_IMAGE = 0xFFFD0002


def premultiplied_bgra(img: Image.Image) -> bytes:
    a = np.asarray(img, np.uint16)
    rgb = (a[..., :3] * a[..., 3:4] + 127) // 255
    return np.dstack([rgb[..., 2], rgb[..., 1], rgb[..., 0], a[..., 3]]).astype(np.uint8).tobytes()


def xcursor(images: list[tuple[int, Image.Image, int, int, int]]) -> bytes:
    """images: (nominal size, RGBA, xhot, yhot, delay ms), grouped by size."""
    head = struct.pack("<4sIII", b"Xcur", 16, 0x10000, len(images))
    pos = len(head) + 12 * len(images)
    toc, chunks = [], []
    for nominal, img, xhot, yhot, delay in images:
        chunk = struct.pack("<9I", 36, XC_IMAGE, nominal, 1, img.width, img.height, xhot, yhot, delay)
        chunk += premultiplied_bgra(img)
        toc.append(struct.pack("<III", XC_IMAGE, nominal, pos))
        chunks.append(chunk)
        pos += len(chunk)
    return head + b"".join(toc) + b"".join(chunks)


def read_xcursor(data: bytes) -> list[tuple[int, np.ndarray, int, int, int]]:
    """The inverse of xcursor(): (nominal, premultiplied RGBA array, xhot, yhot, delay)."""
    magic, hsize, _, ntoc = struct.unpack_from("<4sIII", data)
    if magic != b"Xcur":
        raise ValueError("not an XCursor file")
    out = []
    for i in range(ntoc):
        kind, _, pos = struct.unpack_from("<III", data, hsize + 12 * i)
        if kind != XC_IMAGE:
            continue
        _, _, nominal, _, w, h, xhot, yhot, delay = struct.unpack_from("<9I", data, pos)
        px = np.frombuffer(data, np.uint8, w * h * 4, pos + 36).reshape(h, w, 4)
        out.append((nominal, px[..., [2, 1, 0, 3]], xhot, yhot, delay))
    return out


# --- the theme -----------------------------------------------------------------------------

def frames_of(name: str) -> dict[int, list[Image.Image]]:
    ops_list, _ = SHAPES[name]
    return {s: [render(ops, s) for ops in ops_list] for s in SIZES}


def hotspot(name: str, size: int) -> tuple[int, int]:
    hx, hy = SHAPES[name][1]
    return round(hx * size), round(hy * size)


INDEX = f"""[Icon Theme]
Name={NAME}
Comment=ryce-pc: the peonza as the mouse pointer (theme/cursor/build.py)
Inherits=Adwaita
"""
MANIFEST = f"""name = {NAME}
description = ryce-pc: the peonza as the mouse pointer (theme/cursor/build.py)
version = 1
cursors_directory = hyprcursors
"""


def meta(name: str, n_frames: int) -> str:
    hx, hy = SHAPES[name][1]
    lines = ["resize_algorithm = bilinear", f"hotspot_x = {hx:g}", f"hotspot_y = {hy:g}"]
    lines += [f"define_override = {a}" for a in ALIASES.get(name, ())]
    for s in SIZES:
        if n_frames == 1:
            lines.append(f"define_size = {s}, {s}.png")
        else:
            lines += [f"define_size = {s}, {s}-{i:02d}.png, {DELAY}" for i in range(n_frames)]
    return "\n".join(lines) + "\n"


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def hlc_entries(name: str, frames: dict[int, list[Image.Image]]) -> dict[str, bytes]:
    n = len(frames[SIZES[0]])
    out = {"meta.hl": meta(name, n).encode()}
    for s, imgs in frames.items():
        for i, img in enumerate(imgs):
            out[f"{s}.png" if n == 1 else f"{s}-{i:02d}.png"] = png_bytes(img)
    return out


def compile_hyprcursors(shapes: dict[str, dict[str, bytes]], dest: Path) -> None:
    """hyprcursor-util --create on a working-state tree, then each .hlc re-zipped with fixed
    timestamps (the tool stamps the clock, which would make every build differ)."""
    tool = shutil.which("hyprcursor-util")
    if not tool:
        raise SystemExit("build.py: falta hyprcursor-util (pacman -S hyprcursor)")
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "src", Path(tmp) / "out"
        for name, entries in shapes.items():
            d = src / "hyprcursors" / name
            d.mkdir(parents=True)
            for fn, data in entries.items():
                (d / fn).write_bytes(data)
        (src / "manifest.hl").write_text(MANIFEST, encoding="utf-8")
        out.mkdir()
        r = subprocess.run([tool, "--create", str(src), "--output", str(out)], capture_output=True, text=True, timeout=120)
        built = out / f"theme_{NAME}" / "hyprcursors"
        if r.returncode != 0 or not built.is_dir():
            raise SystemExit(f"build.py: hyprcursor-util --create falló:\n{r.stdout}{r.stderr}")
        dest.mkdir(parents=True, exist_ok=True)
        for name in shapes:
            with zipfile.ZipFile(built / f"{name}.hlc") as z:
                items = [(i.filename, z.read(i)) for i in z.infolist()]
            (dest / f"{name}.hlc").write_bytes(stable_zip(items))


def stable_zip(items: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for fn, data in items:
            info = zipfile.ZipInfo(fn, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            z.writestr(info, data)
    return buf.getvalue()


def build_all() -> dict[str, dict[int, list[Image.Image]]]:
    return {name: frames_of(name) for name in SHAPES}


def xcursor_of(name: str, frames: dict[int, list[Image.Image]]) -> bytes:
    delay = DELAY if len(frames[SIZES[0]]) > 1 else 0
    return xcursor([(s, img, *hotspot(name, s), delay) for s in SIZES for img in frames[s]])


def write(drawn: dict) -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "cursors").mkdir(parents=True)
    (OUT / "index.theme").write_text(INDEX, encoding="utf-8")
    (OUT / "manifest.hl").write_text(MANIFEST, encoding="utf-8")
    for name, frames in drawn.items():
        (OUT / "cursors" / name).write_bytes(xcursor_of(name, frames))
    for base, names in ALIASES.items():
        for a in names:
            shutil.copyfile(OUT / "cursors" / base, OUT / "cursors" / a)
    compile_hyprcursors({n: hlc_entries(n, f) for n, f in drawn.items()}, OUT / "hyprcursors")


# --- --check -------------------------------------------------------------------------------

def _diff(a: Image.Image, b: Image.Image) -> int:
    if a.size != b.size:
        return 255
    return int(np.abs(np.asarray(a, np.int16) - np.asarray(b, np.int16)).max())


def check(drawn: dict) -> list[str]:
    bad: list[str] = []
    rel = lambda p: p.relative_to(ROOT)  # noqa: E731
    want_files = {"index.theme": INDEX, "manifest.hl": MANIFEST}
    for fn, text in want_files.items():
        p = OUT / fn
        if not p.is_file() or p.read_text(encoding="utf-8") != text:
            bad.append(f"stale: {rel(p)}")
    expect_cursors = set(drawn) | {a for names in ALIASES.values() for a in names}
    have = {p.name for p in (OUT / "cursors").iterdir()} if (OUT / "cursors").is_dir() else set()
    bad += [f"missing: {rel(OUT / 'cursors' / n)}" for n in sorted(expect_cursors - have)]
    bad += [f"stray: {rel(OUT / 'cursors' / n)}" for n in sorted(have - expect_cursors)]
    links = sorted(n for n in have if (OUT / "cursors" / n).is_symlink())
    bad += [f"stale: {rel(OUT / 'cursors' / n)} is a link, should be a file" for n in links]
    for base, names in ALIASES.items():
        for a in names:
            p = OUT / "cursors" / a
            if a in have and a not in links and base in have and p.read_bytes() != (OUT / "cursors" / base).read_bytes():
                bad.append(f"stale: {rel(p)} (should be a copy of {base})")
    for name, frames in drawn.items():
        p = OUT / "cursors" / name
        if name not in have or name in links:
            continue
        try:
            want = read_xcursor(xcursor_of(name, frames))
            got = read_xcursor(p.read_bytes())
        except (ValueError, struct.error) as e:
            bad.append(f"stale: {rel(p)} ({e})")
            continue
        if len(got) != len(want) or any(
                g[0] != w[0] or g[2:] != w[2:] or g[1].shape != w[1].shape
                or np.abs(g[1].astype(np.int16) - w[1]).max() > TOLERANCE for g, w in zip(got, want)):
            bad.append(f"stale: {rel(p)}")
    hdir = OUT / "hyprcursors"
    have_h = {p.name for p in hdir.iterdir()} if hdir.is_dir() else set()
    want_h = {f"{n}.hlc" for n in drawn}
    bad += [f"missing: {rel(hdir / n)}" for n in sorted(want_h - have_h)]
    bad += [f"stray: {rel(hdir / n)}" for n in sorted(have_h - want_h)]
    for name, frames in drawn.items():
        p = hdir / f"{name}.hlc"
        if p.name not in have_h:
            continue
        want = hlc_entries(name, frames)
        try:
            with zipfile.ZipFile(p) as z:
                got = {i.filename: z.read(i) for i in z.infolist()}
        except zipfile.BadZipFile:
            bad.append(f"stale: {rel(p)} (not a zip)")
            continue
        if set(got) != set(want) or got["meta.hl"] != want["meta.hl"] or any(
                _diff(Image.open(io.BytesIO(got[k])).convert("RGBA"), Image.open(io.BytesIO(v))) > TOLERANCE
                for k, v in want.items() if k != "meta.hl"):
            bad.append(f"stale: {rel(p)}")
    top = {p.name for p in OUT.iterdir()} if OUT.is_dir() else set()
    bad += [f"stray: {rel(OUT / n)}" for n in sorted(top - {"index.theme", "manifest.hl", "cursors", "hyprcursors"})]
    return bad


# --- contact sheet -------------------------------------------------------------------------
GROUNDS = (("blanco", (255, 255, 255)), ("papel", (247, 243, 235)), ("Ola", (140, 158, 147)),
           ("azul", (58, 95, 138)), ("gris", (128, 128, 128)), ("negro", (0, 0, 0)))


def sheet(drawn: dict, path: Path) -> None:
    names = list(drawn)
    cell, sizes = 60, (24, 32, 48)
    band = cell * len(sizes)
    w = cell * len(names)
    anim = [n for n in names if len(drawn[n][32]) > 1]
    h = band * len(GROUNDS) + len(anim) * 2 * cell + 4 * 64 * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    y = 0
    for _, g in GROUNDS:
        im.paste(Image.new("RGBA", (w, band), (*g, 255)), (0, y))
        for c, n in enumerate(names):
            for r, s in enumerate(sizes):
                f = drawn[n][s][0]
                im.alpha_composite(f, (c * cell + (cell - s) // 2, y + r * cell + (cell - s) // 2))
        y += band
    for n in anim:
        for g in ((247, 243, 235), (0, 0, 0)):
            im.paste(Image.new("RGBA", (w, cell), (*g, 255)), (0, y))
            for i, f in enumerate(drawn[n][48]):
                im.alpha_composite(f, (i * cell + 6, y + 6))
            y += cell
    # The pointer, 4x, on cream and black: the pixels as they land.
    for g in ((247, 243, 235), (0, 0, 0), (140, 158, 147), (255, 255, 255)):
        im.paste(Image.new("RGBA", (w, 64 * 2), (*g, 255)), (0, y))
        x = 0
        for n in ("default", "pointer", "text", "progress", "help", "nwse-resize", "not-allowed", "wait"):
            big = drawn[n][32][0].resize((128, 128), Image.NEAREST)
            im.alpha_composite(big, (x, y))
            x += 136
        y += 128
    path.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(path)


def main(argv: list[str]) -> int:
    drawn = build_all()
    if "--sheet" in argv:
        i = argv.index("--sheet")
        if i + 1 >= len(argv):
            print("build.py: --sheet necesita la ruta del PNG", file=sys.stderr)
            return 2
        sheet(drawn, Path(argv[i + 1]))
        print(f"build.py: sheet {argv[i + 1]}")
        return 0
    if "--check" in argv:
        bad = check(drawn)
        for b in bad:
            print(f"{b} (run python3 theme/cursor/build.py)")
        if not bad:
            print(f"cursor: ok ({len(drawn)} shapes, {sum(map(len, ALIASES.values()))} aliases)")
        return 1 if bad else 0
    write(drawn)
    print(f"build.py: wrote {OUT.relative_to(ROOT)} ({len(drawn)} shapes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
