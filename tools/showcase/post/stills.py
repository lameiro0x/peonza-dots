#!/usr/bin/env python3
"""The README's stills from the raw shots of tools/showcase/scenes/record.sh.

    python3 -I tools/showcase/post/stills.py RAW_DIR MEDIA_DIR

Writes, each under its size limit: theme-<t>.jpg and desk-<t>.jpg (1920x1080), the
close-ups (sidebar, hito, aria, cheatsheet, selector, osd), bars.png (the five bars
stacked), newtab.jpg (the five Chromium new-tab drawings), boot.webp (the five Plymouth
peonzas spinning, 17 ms a frame: WebP counts whole milliseconds), social.png (1280x640) and contact.jpg (every still).
The crops are the stage's fixed 1920x1080 geometry, read off the shots by eye.
"""
from __future__ import annotations

import functools
import io
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
THEMES = ["origen", "grafito", "ola", "tinta", "papel"]   # the picker's order
KB = 1024

# Close-ups from Tinta's bare desk (the OSD from Papel's): (left, top, right, bottom), the
# panels' own outlines where they have one.
CROPS = {
    "sidebar": ("part-sidebar", (1522, 56, 1920, 1066)),
    "hito": ("part-hito", (0, 52, 400, 680)),
    "aria": ("part-aria", (1488, 58, 1908, 672)),
    "cheatsheet": ("part-keys", (247, 164, 1673, 915)),
    "selector": ("part-selector", (285, 694, 1635, 1080)),
    "osd": ("part-osd", (1660, 420, 1920, 660)),
}
BAR_H = 58          # the floating bar and its shadow, from the top edge
BAR_W = 1080        # up to the last workspace slot


@functools.cache
def font_path() -> str:
    return subprocess.run(["fc-match", "-f", "%{file}", "JetBrains Mono:style=Regular"],
                          capture_output=True, text=True, check=True, timeout=10).stdout


def font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    """JetBrains Mono (the terminals' face, neutral to every theme), at WEIGHT."""
    f = ImageFont.truetype(font_path(), size)
    try:
        f.set_variation_by_axes([weight])
    except OSError:
        pass                       # a static face: its own weight
    return f


def save_jpeg(im: Image.Image, out: Path, limit: int) -> None:
    """The best JPEG quality that fits LIMIT bytes (4:4:4 chroma: thin UI lines)."""
    for q in (95, 92, 90, 88, 85, 82, 80, 76, 72):
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=q, subsampling=0 if q >= 85 else 2,
                               optimize=True, progressive=True)
        if buf.tell() <= limit:
            out.write_bytes(buf.getvalue())
            return
    raise SystemExit(f"stills.py: {out.name} does not fit {limit // KB} KB even at q72")


def save_png(im: Image.Image, out: Path, limit: int) -> None:
    im.save(out, optimize=True)
    if out.stat().st_size > limit:
        # A 256-colour palette keeps flat UI crisp and small.
        im.convert("RGB").quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(out, optimize=True)
    if out.stat().st_size > limit:
        raise SystemExit(f"stills.py: {out.name} is {out.stat().st_size // KB} KB, over {limit // KB} KB")


def shot(raw: Path, name: str) -> Image.Image:
    p = raw / f"{name}.png"
    if not p.is_file():
        raise SystemExit(f"stills.py: missing {p} (run tools/showcase/scenes/record.sh)")
    im = Image.open(p).convert("RGB")
    if im.size != (1920, 1080):
        raise SystemExit(f"stills.py: {p} is {im.size}, the stage shoots 1920x1080")
    return im


def themes(raw: Path, media: Path) -> None:
    for t in THEMES:
        for kind in ("theme", "desk"):
            save_jpeg(shot(raw, f"{kind}-{t}"), media / f"{kind}-{t}.jpg", 600 * KB)


def closeups(raw: Path, media: Path) -> None:
    for name, (src, box) in CROPS.items():
        save_png(shot(raw, src).crop(box), media / f"{name}.png", 1536 * KB)


def bars(raw: Path, media: Path) -> None:
    gap = 6
    # The left half: the top, the gauges and the named workspaces, at 1:1 in the README.
    strips = [shot(raw, f"desk-{t}").crop((0, 0, BAR_W, BAR_H)) for t in THEMES]
    out = Image.new("RGB", (BAR_W, len(strips) * BAR_H + (len(strips) - 1) * gap), "#0a0a0a")
    for i, s in enumerate(strips):
        out.paste(s, (0, i * (BAR_H + gap)))
    save_png(out, media / "bars.png", 1536 * KB)


def newtab(media: Path) -> None:
    """One strip in the boot strip's order, each tile in a hairline so Tinta's black has an edge."""
    w, h, gap = 400, 225, 10
    out = Image.new("RGB", (5 * w + 6 * gap, h + 2 * gap), "#0a0a0a")
    draw = ImageDraw.Draw(out)
    for i, t in enumerate(THEMES):
        im = Image.open(ROOT / "themes" / t / "chromium" / "newtab" / "1920x1080.jpg").convert("RGB")
        x = gap + i * (w + gap)
        out.paste(im.resize((w, h), Image.Resampling.LANCZOS), (x, gap))
        draw.rectangle((x - 1, gap - 1, x + w, gap + h), outline="#3a3833")
    save_jpeg(out, media / "newtab.jpg", 1536 * KB)


def boot(media: Path) -> None:
    """The five Plymouth peonzas side by side, each on its theme's ground (Papel's dark
    peonza vanishes on black), 72 frames at 60 fps, looping."""
    size, pad, gap = 160, 36, 8
    cell = size + 2 * pad
    grounds = [json.loads((ROOT / "themes" / t / "theme.json").read_text(encoding="utf-8"))["colors"]["bg0"]
               for t in THEMES]
    frames = []
    for n in range(72):
        f = Image.new("RGB", (5 * cell + 4 * gap, cell), "#000000")
        for i, t in enumerate(THEMES):
            p = Image.open(ROOT / "themes" / t / "peonza" / f"plymouth-{n:02d}.png").convert("RGBA")
            x = i * (cell + gap)
            f.paste(grounds[i], (x, 0, x + cell, cell))
            f.paste(p, (x + pad, pad), p)
        frames.append(f)
    out = media / "boot.webp"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=17, loop=0,
                   lossless=False, quality=88, method=6)
    if out.stat().st_size > 1536 * KB:
        raise SystemExit(f"stills.py: boot.webp is {out.stat().st_size // KB} KB")


def social(raw: Path, media: Path) -> None:
    """1280x640 on Tinta's black: the name and a one-line parts list on the left, the five
    bare desks fanned out on the right like a stack of finishes, Tinta on top."""
    w, h = 1280, 640
    out = Image.new("RGB", (w, h), "#0a0a0a")
    d = ImageDraw.Draw(out)
    cw, ch, step = 600, 338, (62, 56)
    for i, t in enumerate(["papel", "ola", "grafito", "origen", "tinta"]):
        x, y = 620 + (i - 2) * step[0], 48 + i * step[1]
        card = shot(raw, f"desk-{t}").resize((cw, ch), Image.Resampling.LANCZOS)
        d.rectangle([x - 6, y - 6, x + cw + 5, y + ch + 5], fill="#0a0a0a")
        out.paste(card, (x, y))
        d.rectangle([x - 1, y - 1, x + cw, y + ch], outline="#3a3a3a", width=1)
    d.text((64, 214), "peonza-dots", font=font(68, 600), fill="#f0f0f0")
    d.text((66, 310), "five themes, one desktop", font=font(24, 400), fill="#b4b4b4")
    d.text((66, 346), "Hyprland · Quickshell · kitty · fish", font=font(18, 400), fill="#9a9a9a")
    d.line([(66, 296), (430, 296)], fill="#3a3a3a", width=1)
    save_png(out, media / "social.png", 1023 * KB)


def contact(media: Path) -> None:
    """Every still of MEDIA, labelled, five to a row."""
    names = sorted(p for p in media.iterdir()
                   if p.suffix in (".jpg", ".png", ".webp") and p.stem not in ("contact",))
    cell, label = (384, 216), 26
    cols = 5
    rows = (len(names) + cols - 1) // cols
    out = Image.new("RGB", (cols * (cell[0] + 8) + 8, rows * (cell[1] + label + 8) + 8), "#161616")
    d, f = ImageDraw.Draw(out), font(14)
    for i, p in enumerate(names):
        im = Image.open(p).convert("RGB")
        im.thumbnail(cell, Image.Resampling.LANCZOS)
        r, c = divmod(i, cols)
        x, y = 8 + c * (cell[0] + 8), 8 + r * (cell[1] + label + 8)
        out.paste(im, (x + (cell[0] - im.width) // 2, y + (cell[1] - im.height) // 2))
        d.text((x, y + cell[1] + 5), f"{p.name}  {p.stat().st_size // KB} KB", font=f, fill="#b4b4b4")
    save_jpeg(out, media / "contact.jpg", 4096 * KB)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__.strip().splitlines()[2].strip())
    raw, media = Path(sys.argv[1]), Path(sys.argv[2])
    media.mkdir(parents=True, exist_ok=True)
    themes(raw, media)
    closeups(raw, media)
    bars(raw, media)
    newtab(media)
    boot(media)
    social(raw, media)


if __name__ == "__main__":
    if sys.argv[1:2] == ["contact"]:
        contact(Path(sys.argv[2]))
    else:
        main()
