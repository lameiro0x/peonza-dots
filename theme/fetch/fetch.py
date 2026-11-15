#!/usr/bin/env python3
"""The peonza of the system fetches, per theme, from the brand's own model.

    python3 theme/fetch/fetch.py            write the files below for every theme
    python3 theme/fetch/fetch.py --check    exit 1 if any is stale or missing

    themes/<id>/fastfetch/peonza.webp   the brand's `think` state over one period, a
                                        looping lossless WebP: fastfetch's logo in kitty
    themes/<id>/fastfetch/peonza.txt    the still peonza in half blocks, `$1` ink: the logo
                                        in the TTY, over ssh and in tmux
    themes/<id>/neofetch/peonza.png     the still peonza at the size neofetch shows it in
                                        kitty, 1:1: NEO_ROWS x CELL px high, as many whole
                                        cells wide as hold its ink (theme/templates/neofetch/)
    themes/<id>/neofetch/peonza.txt     the still peonza in sextants (U+1FB00, 2 x 3 pixels
                                        a cell, which kitty draws itself), `${c1}` ink:
                                        neofetch's outside kitty
    themes/<id>/dripfetch/config.yaml   theme/fetch/dripfetch.yaml with theme/render.py's
                                        placeholders resolved and a larger half-block
                                        peonza, widened for kitty's cells, in place of its
                                        `@@peonza@@` line

Why WebP and not APNG: fastfetch decodes an animated logo with ImageMagick 7 on Linux,
and ImageMagick reads an APNG through its PNG coder, as one frame (measured with
7.1.2-35: `magick identify` lists 1 image for a 24-frame APNG, 24 for the same frames as
WebP). Lossless WebP keeps the full alpha (GIF would cut the antialiased edge to one bit)
and decodes back to exactly the pixels drawn.

The spin reads because the brand's `think` pose is not symmetric about the axis: two
engraved seams turn with the body while the axis precesses (6.5 deg) and the disc opens
and closes. One spin per precession turn, so `FRAMES` evenly spaced instants loop. 72 of
them, one per refresh of a 60 Hz screen: at the bar's 24 (50 ms) the turn stepped visibly
in kitty. fastfetch decodes the WebP once per logo size and caches it (measured: 72 frames
at 480 px, 0.6 s with `magick ... -coalesce -resize 310x310`; 1.0 s at 672 px).

Ink is the theme's fg0 with the grooves in bg0, transparent around, like every other
peonza asset; the signal never appears. The text peonzas are the brand's still pose drawn
with a 32 (36) px mark's optics; a pixel is ink where the drawing is opaque and not a groove,
so the seams and the disc rim show as gaps in the ground colour, the way the mark is
engraved. Each text row is two pixel rows (▀ ▄ █), the only shapes the Linux console's
default font has; neofetch's, which runs in kitty, is three (sextants).

--check compares decoded pixels with theme/peonza/gen.py's tolerance and the text
exactly. Without the brand repo (or PEONZA_BRAND), node or rsvg-convert it skips with
a message and exits 0, as gen.py does.
"""

from __future__ import annotations

import io
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence
from PIL.PngImagePlugin import PngInfo

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "theme" / "peonza"))
sys.path.insert(0, str(ROOT / "theme"))
sys.path.insert(0, str(ROOT / "tools"))

import gen  # noqa: E402
import render  # noqa: E402
import tokens  # noqa: E402

FRAMES = 72          # over think's 1.2 s period: one per 60 Hz refresh
GAP = 16             # ms a frame; kitty times the next frame from when it showed this one,
                     # so its own wake-up (~0.5 ms) brings the loop back to ~1.2 s
PX = 480             # 1.5x the largest logo box (31 x 12 kitty cells of 10 x 26 px = 310 px)
TEXT_PX = 32         # the half-block peonza for the console (8 x 16 cells: square halves)
DRIP_PX = 36         # dripfetch's, in kitty, whose half cell is 10 x 13 px:
DRIP_STRETCH = 1.23  # 1.23 columns per pixel row keep it round
NEO_PX = 36          # neofetch's, in sextants (2 x 3 a cell): 12 lines of kitty's 10 x 26 px
NEO_STRETCH = 1.73   # cells, so a sextant pixel is 5 x 8.7 px: 1.73 columns per pixel row
NEO_ROWS = 13        # neofetch's picture in kitty: 13 lines beside its 21 of text (centred, 4 above)
NEO_SCALE = 1.1      # the still pose's square at 1.1 x the picture's height: its ink (80 %) fills
                     # 88 % of it and 30 cells, which with the gap and the text fit 88 columns
CELL = (10, 26)      # kitty's cell in px at 13 pt with cell_height 112 % (CSI 16t, measured)
GROOVE = 0.25        # below this share of the way from bg0 to fg0, an opaque pixel is a groove
WEBP = "fastfetch/peonza.webp"
TXT = "fastfetch/peonza.txt"
NEO = "neofetch/peonza.txt"
NEO_PNG = "neofetch/peonza.png"
DRIP = "dripfetch/config.yaml"
DRIP_TEMPLATE = HERE / "dripfetch.yaml"
MARK = "@@peonza@@"
GENERATED = "GENERATED by theme/fetch/fetch.py"
# The brand's rights notice (gen.TEXT) as XMP: WebP has no text chunks.
XMP = ('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
       '<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>{0}</dc:creator>'
       '<dc:rights>{1}</dc:rights></rdf:Description></rdf:RDF></x:xmpmeta>').format(*(v for _, v in gen.TEXT)).encode()

PNG_INFO = PngInfo()
for _k, _v in gen.TEXT:
    PNG_INFO.add_itxt(_k, _v)


def spin(t: dict) -> list[Image.Image]:
    c = t["colors"]
    job = {"key": "fetch", "motion": "think", "frames": FRAMES, "opsz": PX, "ink": {"fg": c["fg0"], "bg": c["bg0"]}}
    return [gen.raster(svg, PX) for svg in gen.svgs([job])["fetch"]]


def webp(frames: list[Image.Image]) -> bytes:
    buf = io.BytesIO()
    # exact: keep the colour under transparent pixels, so --check can compare raw RGBA.
    frames[0].save(buf, "WEBP", save_all=True, append_images=frames[1:], duration=GAP,
                   loop=0, lossless=True, quality=100, method=4, exact=True, xmp=XMP)
    return buf.getvalue()


def ink(size: int, stretch: float, cell: tuple[int, int]) -> np.ndarray:
    """The still peonza as a boolean pixel grid, trimmed to its ink and padded to whole
    cells of `cell` (columns, rows) pixels: `size` pixel rows, `stretch` times as many columns."""
    job = {"key": "text", "motion": "still", "frames": 1, "opsz": size, "ink": {"fg": "#ffffff", "bg": "#000000"}}
    big = gen.raster(gen.svgs([job])["text"][0], 4 * size)    # area-averaged down: no rsvg hinting at 32 px
    px = np.asarray(big.resize((round(size * stretch), size), Image.Resampling.BOX), dtype=np.int16)
    on = (px[..., 3] >= 128) & (px[..., :3].mean(axis=2) >= GROOVE * 255)
    on = on[np.ix_(on.any(axis=1), on.any(axis=0))]
    w, h = cell
    return np.pad(on, ((0, -len(on) % h), (0, -on.shape[1] % w)))


def blocks(size: int = TEXT_PX, stretch: float = 1.0) -> list[str]:
    """Half-block rows (▀ ▄ █), for cells whose half is not square at `stretch` != 1."""
    on = ink(size, stretch, (1, 2))
    glyph = {(1, 1): "█", (1, 0): "▀", (0, 1): "▄", (0, 0): " "}
    return ["".join(glyph[int(a), int(b)] for a, b in zip(top, bottom)).rstrip() for top, bottom in zip(on[::2], on[1::2])]


def sextant(bits: int) -> str:
    """The cell whose 2 x 3 pixels are `bits` (bit 0 top left, 1 top right, ... 5 bottom
    right). Unicode's sextant block skips the four that exist already: blank, the two
    half blocks and the full block."""
    special = {0: " ", 21: "▌", 42: "▐", 63: "█"}
    return special.get(bits) or chr(0x1FB00 + bits - 1 - (bits > 21) - (bits > 42))


def sextants(size: int = NEO_PX, stretch: float = NEO_STRETCH) -> list[str]:
    """Sextant rows: three times the vertical detail of a line, twice the horizontal."""
    on = ink(size, stretch, (2, 3)).astype(int)
    weight = np.array([[1, 2], [4, 8], [16, 32]])
    rows = []
    for y in range(0, len(on), 3):
        rows.append("".join(sextant(int((on[y:y + 3, x:x + 2] * weight).sum())) for x in range(0, on.shape[1], 2)).rstrip())
    return rows


def picture(t: dict, rows: int = NEO_ROWS, cell: tuple[int, int] = CELL) -> Image.Image:
    """The still peonza for kitty's graphics protocol, drawn at the size it is shown: its
    ink trimmed and centred on whole cells, `rows` high and as few columns as hold it.
    Never resampled: kitty shows it 1:1 (theme/templates/neofetch/config.conf)."""
    c = t["colors"]
    w, h = cell
    size = round(rows * h * NEO_SCALE)
    job = {"key": "neo", "motion": "still", "frames": 1, "opsz": size, "ink": {"fg": c["fg0"], "bg": c["bg0"]}}
    img = gen.raster(gen.svgs([job])["neo"][0], size)
    img = img.crop(img.getbbox())
    canvas = Image.new("RGBA", (-(-img.width // w) * w, rows * h))
    canvas.paste(img, ((canvas.width - img.width) // 2, (canvas.height - img.height) // 2))
    return canvas


def dripfetch(t: dict, rows: list[str]) -> str:
    out = []
    for line in render.render_text(DRIP_TEMPLATE.read_text(encoding="utf-8"), t, DRIP).split("\n"):
        if line.strip() == MARK:
            pad = line[:len(line) - len(line.lstrip())]
            out += [f'{pad}- "{row}"' for row in rows]
        else:
            out.append(line)
    head = f"# {GENERATED} — theme «{t['name']}». Edit theme/fetch/dripfetch.yaml or contracts/themes/{t['id']}.json and re-run it.\n"
    return head + "\n".join(out)


def outputs(tid: str, console: list[str], kitty: list[str], neo: list[str]) -> dict[Path, list[Image.Image] | Image.Image | str]:
    t = tokens.load(tid)
    base = gen.THEMES_OUT / tid
    return {base / WEBP: spin(t), base / TXT: "$1" + "\n".join(console) + "\n",
            base / NEO: "${c1}" + "\n".join(neo) + "\n", base / NEO_PNG: picture(t), base / DRIP: dripfetch(t, kitty)}


def decoded(path: Path) -> tuple[list[np.ndarray], list[int], int] | None:
    try:
        with Image.open(path) as im:
            frames, durations = [], []
            for f in ImageSequence.Iterator(im):
                frames.append(np.asarray(f.convert("RGBA"), dtype=np.int16))
                durations.append(f.info.get("duration", 0))   # set by the decode, not the seek
            return frames, durations, im.info.get("loop", 1)
    except (OSError, ValueError):
        return None


def differs(path: Path, want: object) -> str | None:
    if not path.exists():
        return "missing"
    if isinstance(want, str):
        return None if path.read_text(encoding="utf-8") == want else "text differs"
    got = decoded(path)
    if got is None:
        return "not a readable image"
    frames, durations, loop = got
    still = isinstance(want, Image.Image)
    if still:
        want = [want]
    if len(frames) != len(want):
        return f"{len(frames)} frames, expected {len(want)}"
    if not still and (loop != 0 or any(d != GAP for d in durations)):
        return f"timing: loop {loop}, durations {sorted(set(durations))} ms, expected loop 0 at {GAP} ms"
    for i, (cur, img) in enumerate(zip(frames, want)):
        new = np.asarray(img, dtype=np.int16)
        if cur.shape != new.shape:
            return f"frame {i}: size {cur.shape[1]}x{cur.shape[0]}, expected {new.shape[1]}x{new.shape[0]}"
        worst = int(np.abs(cur - new).max())
        if worst > gen.TOLERANCE:
            return f"frame {i}: pixels differ by up to {worst}"
    return None


def main(argv: list[str]) -> int:
    check = "--check" in argv
    missing = [what for what, ok in ((f"{gen.REPO}/src/pose.mjs", (gen.REPO / "src" / "pose.mjs").exists()),
                                     ("node", shutil.which("node")),
                                     ("rsvg-convert", shutil.which("rsvg-convert"))) if not ok]
    if missing:
        print(f"fetch: skip (no {', '.join(missing)}; set PEONZA_BRAND to logo-peonza's brand/mark/)")
        return 0
    try:
        console, kitty, neo = blocks(), blocks(DRIP_PX, DRIP_STRETCH), sextants()
        todo = {tid: outputs(tid, console, kitty, neo) for tid in tokens.theme_ids()}
    except (render.RenderError, tokens.ThemeError) as e:
        print(f"fetch: {e}", file=sys.stderr)
        return 2
    stale = []
    for tid, files in todo.items():
        for path, want in files.items():
            if check:
                why = differs(path, want)
                if why:
                    stale.append(f"{path.relative_to(ROOT)}: {why}")
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(want, str):
                path.write_text(want, encoding="utf-8")
            elif isinstance(want, Image.Image):
                want.save(path, optimize=True, pnginfo=PNG_INFO)
            else:
                path.write_bytes(webp(want))
        if not check:
            print(f"wrote themes/{tid}/{{{WEBP},{TXT},{NEO},{NEO_PNG},{DRIP}}}")
    for line in stale:
        print(f"stale: {line} (run python3 theme/fetch/fetch.py)")
    if check and not stale:
        print("fetch: ok")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
