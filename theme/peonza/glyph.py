#!/usr/bin/env python3
"""Build assets/fonts/RycePeonza.otf: the lameiro0x spinning top as font glyphs.

The terminal prompt, fish, fastfetch's text and Waybar can only show the logo as a
character, so the brand's small-size drawings (~/Repos/logo-peonza/brand/mark/
peonza-{20,32,64}.svg — one ink, cut lines see-through) become outlines:

    rsvg-convert (1024 px) -> alpha threshold -> potrace -> fontTools CFF glyph

Codepoints live in Supplementary Private Use Area-B, far from every Nerd Font range,
so fontconfig falls back to this font for them and nothing else:

    U+100000  peonza-20 drawing   (12-31 px: prompt, bar text)
    U+100001  peonza-32 drawing   (32-63 px)
    U+100002  peonza-64 drawing   (64 px and up)
    U+100003  prompt              (the shell prompt's character, three cells wide)

The bar's cuts have a 1 em advance. The prompt's cut is the 20 px drawing again, fitted
to PROMPT_BOX: ink -290..1010 units tall, centred in an advance of three JetBrainsMono
cells (1800 units), every edge inside it. kitty 0.49 sizes a symbol by its ink, not
its advance, and draws it over that many cells (at most one per following space, and
`narrow_symbols` pins three in kitty.conf); it drops every pixel column left of the
pen and cuts what hangs below the cell. So the ink starts right of the pen, is wider
than two cells at every size (kitty grants the third) and narrower than three (it is
never shrunk), and sits centred in the 112 % cell, clear of the rows above and below.
Write it as "<mark>  " (two spaces) in a prompt; the state is its colour, never its
pose.

    python3 theme/peonza/glyph.py            write the font
    python3 theme/peonza/glyph.py --check    exit 1 if the committed font is stale

Build-time only (python-fonttools, python-pillow, potrace, rsvg-convert); the
committed .otf is what deploys. Deterministic: fixed head/name timestamps. Without
the brand (set PEONZA_BRAND to its brand/mark/ folder) it skips with a message.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAND = Path(os.environ.get("PEONZA_BRAND", Path.home() / "Repos" / "logo-peonza" / "brand" / "mark"))
OUT = ROOT / "assets" / "fonts" / "RycePeonza.otf"
FAMILY = "Ryce Peonza"
UPM = 1000
RASTER = 1024
PROMPT = 0x100003
# The prompt cut's advance and ink height in font units (see the docstring).
PROMPT_ADVANCE, PROMPT_BOX = 1800, (-290, 1010)
# (code point, glyph name, brand drawing, fitted to the prompt's box)
GLYPHS = [(0x100000, "peonza20", "peonza-20.svg", False),
          (0x100001, "peonza32", "peonza-32.svg", False),
          (0x100002, "peonza64", "peonza-64.svg", False),
          (PROMPT, "prompt", "peonza-20.svg", True)]
# 2026-11-09 00:00:00 UTC in seconds since 1904-01-01 (OpenType epoch): fixed so the
# file is byte-identical on every rebuild.
FIXED_TIME = 3845577600


def outline(svg: Path) -> str:
    """potrace SVG path data for one mark, in the 1024 px raster's coordinates."""
    from PIL import Image

    png = subprocess.run(["rsvg-convert", "-w", str(RASTER), "-h", str(RASTER), str(svg)],
                         check=True, capture_output=True, timeout=60).stdout
    alpha = Image.open(io.BytesIO(png)).convert("RGBA").getchannel("A")
    ink = alpha.point(lambda a: 0 if a >= 128 else 255, mode="1")   # potrace traces black
    with tempfile.TemporaryDirectory() as tmp:
        pbm = Path(tmp) / "mark.pbm"
        ink.save(pbm)
        res = subprocess.run(["potrace", "-s", "--flat", "-u", "1", "-t", "4", "-a", "1.0",
                              "-O", "0.2", "-o", "-", str(pbm)],
                             check=True, capture_output=True, text=True, timeout=60).stdout
    # potrace -u 1: path coordinates in pixels, origin bottom-left (it emits a
    # transform="translate(0,H) scale(1,-1)" on the group, which we do not apply).
    paths = re.findall(r'<path d="([^"]+)"', res)
    if not paths:
        raise SystemExit(f"potrace produced no outline for {svg.name}")
    return " ".join(paths)


def bounds(rec, t=None) -> tuple[float, float, float, float]:
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.transformPen import TransformPen

    pen = BoundsPen(None)
    rec.replay(TransformPen(pen, t) if t else pen)
    return pen.bounds


def fit(rec):
    """The affine that scales a drawing to PROMPT_BOX's height, rests it on the box's
    floor and centres it on PROMPT_ADVANCE."""
    from fontTools.misc.transform import Transform

    x0, y0, x1, y1 = bounds(rec)
    lo, hi = PROMPT_BOX
    k = (hi - lo) / (y1 - y0)
    return Transform().translate(PROMPT_ADVANCE / 2, lo).scale(k).translate(-(x0 + x1) / 2, -y0)


def build() -> bytes:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.svgLib.path import parse_path

    names = [".notdef"] + [g[1] for g in GLYPHS]
    fb = FontBuilder(UPM, isTTF=False)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({cp: name for cp, name, *_ in GLYPHS})

    # Raster px (origin bottom-left, y up) -> font units: the 1024 px square maps onto
    # the em box from the descender (-200) to the ascender (800).
    scale = UPM / RASTER
    drawn: dict[str, RecordingPen] = {}
    for file in dict.fromkeys(g[2] for g in GLYPHS):
        rec = RecordingPen()
        parse_path(outline(BRAND / file), TransformPen(rec, (scale, 0, 0, scale, 0, -200)))
        drawn[file] = rec
    charstrings = {".notdef": T2CharStringPen(UPM, None).getCharString()}
    # hmtx's left side bearing is the outline's xMin, as OpenType asks.
    metrics = {".notdef": (UPM, 0)}
    for _, name, file, prompt in GLYPHS:
        advance = PROMPT_ADVANCE if prompt else UPM
        rec = RecordingPen()
        drawn[file].replay(TransformPen(rec, fit(drawn[file])) if prompt else rec)
        pen = T2CharStringPen(advance, None)
        rec.replay(pen)
        charstrings[name] = pen.getCharString()
        metrics[name] = (advance, round(bounds(rec)[0]))

    fb.setupCFF(FAMILY.replace(" ", ""), {"FullName": FAMILY}, charstrings, {})
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": FAMILY, "styleName": "Regular",
                       "uniqueFontIdentifier": "ryce-peonza-1.0",
                       "version": "Version 1.000",
                       "copyright": "© 2026 lameiro0x. The peonza mark; for this desktop only."})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200,
                achVendID="RYCE")
    fb.setupPost()
    fb.font["head"].created = FIXED_TIME
    fb.font["head"].modified = FIXED_TIME
    buf = io.BytesIO()
    fb.font.save(buf)
    return buf.getvalue()


def main(argv: list[str]) -> int:
    if not all((BRAND / file).exists() for _, _, file, *_ in GLYPHS):
        print(f"glyph: skip (no {BRAND}; set PEONZA_BRAND to logo-peonza's brand/mark/)")
        return 0
    data = build()
    if "--check" in argv:
        cur = OUT.read_bytes() if OUT.exists() else b""
        if cur != data:
            print(f"stale: {OUT.relative_to(ROOT)} (run python3 theme/peonza/glyph.py)")
            return 1
        print("glyph: ok")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(data)} bytes, {len(GLYPHS)} glyphs)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
