#!/usr/bin/env python3
"""Build theme/boot/grub/: the GRUB menu's own art, the same whatever the desktop theme.

The brand's warm black and bone ink (~/Repos/logo-peonza/brand/mark/peonza-128.svg, its
--peonza-ground and --peonza-ink): the peonza large and faint on the right, standing on the
floor it spins on (a few flat orbits around its tip), fine grain over the ground; on the left
a short list in Martian Mono, the selected entry on a quiet bar with a bone edge, the
countdown under it and the keys at the foot. Text that never changes is drawn here into the
background (anti-aliased); what GRUB must write itself (entries, countdown, the editor) uses
the "Ryce Regular N" fonts install/boot-setup.sh makes with grub-mkfont.

    python3 theme/boot/grub.py            write theme.txt, background.png, select_*.png, terminal_*.png
    python3 theme/boot/grub.py --check    exit 1 if a committed file is stale, missing or stray

Build-time only (python-pillow, python-numpy, rsvg-convert); the committed files are what
install/boot-setup.sh copies to /boot/grub/themes/ryce. Deterministic: fixed seed, no clock.
--check compares decoded pixels, not PNG bytes. Without the brand (set PEONZA_BRAND to its
brand/mark/ folder) it skips with a message.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
BRAND = Path(os.environ.get("PEONZA_BRAND", Path.home() / "Repos" / "logo-peonza" / "brand" / "mark"))
OUT = ROOT / "theme" / "boot" / "grub"
FONT = ROOT / "assets" / "fonts" / "MartianMono-Regular.ttf"
W, H = 1920, 1080   # GRUB_GFXMODE; GRUB stretches the picture to any other mode
SS = 4              # supersampling for the drawn lines

GROUND = (12, 10, 8)        # the brand's --peonza-ground
INK = (236, 231, 222)       # the brand's --peonza-ink


def mix(a: float) -> tuple[int, int, int]:
    """INK at opacity a over GROUND."""
    return tuple(round(g + (i - g) * a) for g, i in zip(GROUND, INK))


def hexc(c: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % c


ITEM = mix(0.50)
SELECTED = INK
BAR = mix(0.075)
DIM = mix(0.34)
FAINT = mix(0.22)

# Layout, in 1920x1080 pixels. Columns sit on whole percentages of the width so the
# theme.txt percentages land on the same pixels the background was drawn for.
LEFT = 192                  # 10 %
MENU_TOP = 432              # 40 %
MENU_W = 576                # 30 %
ITEM_H, ITEM_GAP, ITEM_PAD = 52, 6, 24
# The selection's 9-slice borders. GRUB moves the selected entry's text right by the left
# border and down by the top one: a wide left border puts the bar's bone edge (SEL_EDGE)
# out in front of the text, and a thin top keeps the list evenly spaced.
SEL_L, SEL_T, SEL_EDGE = 18, 2, 2
ITEMS = 4
# GRUB insets the list by item_padding on every side, then the text by the selection's left
# slice: the box starts that far left of LEFT, so the entries' text sits on the column.
MENU_INSET = ITEM_PAD + SEL_L
MENU_H = ITEMS * (ITEM_H + ITEM_GAP) + 2 * ITEM_PAD + 24   # room to spare: never a scrollbar
TIMEOUT_TOP = MENU_TOP + ITEMS * (ITEM_H + ITEM_GAP) + 36
ITEM_PX, SMALL_PX = 20, 16  # the GRUB font sizes (grub-mkfont -s)
TIP = (1404, 890)           # where the peonza's tip touches the floor
MARK = 940                  # the drawing's box, in pixels


def _font(px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), px)


def mark(size: int) -> Image.Image:
    """The brand drawing's coverage (L), size x size; its tip at (0.4613, 0.90) of the box."""
    svg = BRAND / "peonza-128.svg"
    png = subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), str(svg)],
                         check=True, capture_output=True, timeout=60).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA").getchannel("A")


def text(img: Image.Image, xy: tuple[int, int], s: str, px: int, color, tracking: float = 0) -> None:
    """S at XY (left, baseline), letter-spaced by TRACKING em."""
    draw, font = ImageDraw.Draw(img), _font(px)
    x, y = xy
    if not tracking:
        draw.text((x, y), s, font=font, fill=color, anchor="ls")
        return
    for ch in s:
        draw.text((x, y), ch, font=font, fill=color, anchor="ls")
        x += font.getlength(ch) + tracking * px


def background() -> Image.Image:
    rng = np.random.default_rng(1414)
    # The ground: flat warm black, a touch lighter where the peonza stands, darker at the edges.
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.hypot((xx - TIP[0]) / W, (yy - TIP[1] * 0.75) / H)
    light = np.clip(1.0 - d * 1.35, 0, 1) ** 2 * 0.035
    edge = np.clip(np.hypot((xx - W / 2) / W, (yy - H / 2) / H) * 1.6 - 0.45, 0, 1) * 0.02
    base = np.array(GROUND, np.float32)
    ink = np.array(INK, np.float32)
    rgb = base + (ink - base) * light[..., None] - base * edge[..., None] * 8

    # The floor: flat orbits around the tip, the spin's trace, fading outwards.
    floor = Image.new("L", (W * SS, H * SS), 0)
    draw = ImageDraw.Draw(floor)
    for i, rx in enumerate((150, 236, 344, 476, 632, 812)):
        ry = rx * 0.13
        a = round(255 * 0.13 * (1 - i / 7))
        cx, cy = TIP[0] * SS, TIP[1] * SS
        draw.ellipse((cx - rx * SS, cy - ry * SS, cx + rx * SS, cy + ry * SS), outline=a, width=SS)
    floor = np.asarray(floor.resize((W, H), Image.Resampling.BOX), np.float32) / 255

    # The peonza: bone ink at low opacity, so it reads as a shape in the dark, not a logo.
    cov = mark(MARK)
    sheet = Image.new("L", (W, H), 0)
    sheet.paste(cov, (round(TIP[0] - 0.4613 * MARK), round(TIP[1] - 0.90 * MARK)))
    # Lit from above: a little brighter at the head than at the tip.
    ramp = np.clip((TIP[1] - yy) / (0.9 * MARK), 0, 1)
    peonza = np.asarray(sheet, np.float32) / 255 * (0.03 + 0.045 * ramp)

    # The mark hides the floor's back half, as if it stood on it.
    floor *= 1 - np.asarray(sheet, np.float32) / 255
    rgb = rgb + (ink - rgb) * np.maximum(floor, peonza)[..., None]
    # Grain: fine, monochrome, about one level either way.
    rgb += rng.normal(0, 0.9, (H, W))[..., None]
    img = Image.fromarray(np.clip(np.rint(rgb), 0, 255).astype(np.uint8), "RGB")

    # The words that never change.
    text(img, (LEFT, MENU_TOP - 26), "ARRANQUE", 13, DIM, tracking=0.32)
    keys = [("↑ ↓", "elegir"), ("Intro", "arrancar"), ("e", "editar"), ("c", "consola")]
    x, y, f = LEFT, H - 72, _font(SMALL_PX - 2)
    for key, what in keys:
        text(img, (x, y), key, SMALL_PX - 2, ITEM)
        x += f.getlength(key) + 10
        text(img, (x, y), what, SMALL_PX - 2, FAINT)
        x += f.getlength(what) + 36
    return img


def nine(box: Image.Image, left: int, top: int) -> dict[str, Image.Image]:
    """The 9-slice cuts of BOX, whose centre is its single pixel at (left, top): the right
    and bottom borders are whatever is past it."""
    w, h = box.size
    x0, x1, y0, y1 = left, left + 1, top, top + 1
    cols = {"w": (0, x0), "": (x0, x1), "e": (x1, w)}
    rows = {"n": (0, y0), "": (y0, y1), "s": (y1, h)}
    return {(r + c) or "c": box.crop((cx[0], ry[0], cx[1], ry[1]))
            for r, ry in rows.items() for c, cx in cols.items()}


def selection() -> dict[str, Image.Image]:
    """The selected entry: a quiet bar, its corners rounded by SEL_T, a bone edge in front."""
    w, h, r = SEL_L + 1 + SEL_T, 2 * SEL_T + 1, SEL_T
    shape = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), r * SS, fill=255)
    edge = Image.new("L", shape.size, 0)
    ImageDraw.Draw(edge).rectangle((0, 0, SEL_EDGE * SS - 1, h * SS), fill=255)
    color = Image.new("RGB", shape.size, BAR)
    color.paste(INK, mask=ImageChops.multiply(shape, edge))
    color.putalpha(shape)
    box = color.resize((w, h), Image.Resampling.BOX)
    return {f"select_{k}.png": v for k, v in nine(box, SEL_L, SEL_T).items()}


def terminal() -> dict[str, Image.Image]:
    """The editor and console box (e, c): the ground, opaque, inside a hairline."""
    r = 6
    box = Image.new("RGBA", (2 * r + 1, 2 * r + 1), GROUND + (255,))
    ImageDraw.Draw(box).rectangle((0, 0, 2 * r, 2 * r), outline=FAINT + (255,))
    return {f"terminal_{k}.png": v for k, v in nine(box, r, r).items()}


def theme_txt() -> str:
    pct = lambda v, whole: f"{round(v / whole * 100)}%"
    assert all(v / 1920 * 100 == round(v / 1920 * 100) for v in (LEFT, MENU_W))
    assert MENU_TOP / H * 100 == round(MENU_TOP / H * 100)
    return f"""\
# Generated by theme/boot/grub.py: edit it there and re-run. The GRUB menu, the same whatever
# the desktop theme. install/boot-setup.sh copies this folder to /boot/grub/themes/ryce and adds
# the fonts: Martian Mono as "Ryce Regular {ITEM_PX}" and "Ryce Regular {SMALL_PX}". The editor
# and the console use GRUB's own unicode.pf2 (Unifont), which grub.cfg always loads: Martian
# Mono has no box drawing and loses its descenders in GRUB's terminal cells.
title-text: ""
desktop-image: "background.png"
desktop-image-scale-method: "stretch"
desktop-color: "{hexc(GROUND)}"
message-font: "Ryce Regular {SMALL_PX}"
message-color: "{hexc(ITEM)}"
message-bg-color: "{hexc(GROUND)}"
terminal-font: "Unifont Regular 16"
terminal-box: "terminal_*.png"
terminal-left: "9%"
terminal-top: "10%"
terminal-width: "82%"
terminal-height: "80%"
terminal-border: "0"

+ boot_menu {{
  left = {pct(LEFT, W)}-{MENU_INSET}
  top = {pct(MENU_TOP, H)}-{ITEM_PAD}
  width = {pct(MENU_W, W)}
  height = {MENU_H}
  item_font = "Ryce Regular {ITEM_PX}"
  selected_item_font = "Ryce Regular {ITEM_PX}"
  item_color = "{hexc(ITEM)}"
  selected_item_color = "{hexc(SELECTED)}"
  selected_item_pixmap_style = "select_*.png"
  icon_width = 0
  icon_height = 0
  item_icon_space = 0
  item_height = {ITEM_H}
  item_padding = {ITEM_PAD}
  item_spacing = {ITEM_GAP}
  scrollbar = false
}}

+ label {{
  id = "__timeout__"
  left = {pct(LEFT, W)}
  top = {pct(MENU_TOP, H)}+{TIMEOUT_TOP - MENU_TOP}
  width = 600
  height = 24
  align = "left"
  font = "Ryce Regular {SMALL_PX}"
  color = "{hexc(DIM)}"
  text = "Arranca en %d s"
}}
"""


def outputs() -> dict[str, Image.Image | str]:
    out: dict[str, Image.Image | str] = {"theme.txt": theme_txt(), "background.png": background()}
    out.update(selection())
    out.update(terminal())
    return out


def same(path: Path, want: Image.Image | str) -> bool:
    if not path.exists():
        return False
    if isinstance(want, str):
        return path.read_text(encoding="utf-8") == want
    with Image.open(path) as have:
        return have.mode == want.mode and have.size == want.size and have.tobytes() == want.tobytes()


def main(argv: list[str]) -> int:
    check = "--check" in argv
    if not (BRAND / "peonza-128.svg").exists():
        print(f"grub.py: no está la marca en {BRAND} (PEONZA_BRAND): no se genera nada")
        return 0
    want = outputs()
    if check:
        bad = [f"stale: {(OUT / n).relative_to(ROOT)} (run python3 theme/boot/grub.py)"
               for n, v in want.items() if not same(OUT / n, v)]
        bad += [f"stray: {p.relative_to(ROOT)} (not generated: delete it)"
                for p in sorted(OUT.iterdir()) if p.name not in want] if OUT.is_dir() else []
        for b in bad:
            print(b)
        if not bad:
            print(f"grub.py: ok ({len(want)} files)")
        return 1 if bad else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for p in OUT.iterdir():
        if p.name not in want:
            p.unlink()
    for name, v in want.items():
        if isinstance(v, str):
            (OUT / name).write_text(v, encoding="utf-8")
        else:
            v.save(OUT / name, optimize=True)
    print(f"grub.py: wrote {len(want)} files in {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
