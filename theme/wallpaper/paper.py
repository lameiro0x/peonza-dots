#!/usr/bin/env python3
"""Papel's pictures: the Tractatus as dots on cream paper, after the Ludwig Wittgenstein
Project's book covers (Frederic Kettelhoit's generator, markdown_to_book_covers.py).

    python3 theme/wallpaper/paper.py            write assets/wallpapers/papel.jpg (2560x1440)
                                                and papel-lock.jpg (1920x1080)
    python3 theme/wallpaper/paper.py --check    exit 1 if a committed master is stale or
                                                breaks the paper budget below
    python3 theme/wallpaper/paper.py --out DIR  render both into DIR (for looking)

The recipe is the cover's: a grid of cells, one circle per paragraph in reading order,
its radius from the paragraph's length (ln(len+1)^2), filled or hollow by a rule, a pale
halo behind the questions, and small hollow «axis» rings on every cell that carries no
text. The text is the Tractatus (German, 1921; public domain): tractatus.json holds only
each proposition's number, length and question marks, measured once from
wittgensteinproject.org. Filled = a proposition numbered to at most three decimals
(1, 1.1, 2.012, ...); hollow = the remarks on remarks (4.0031, 6.3631, ...): about three
in four filled, the cover's balance.

  desktop  the 526 propositions in reading order inside the peonza's silhouette
           (peonza-silhouette.svg), its engraving (peonza.svg) left as paper, the edge
           cells a little heavier, so the mark emerges from density alone; the left
           third carries only the axis rings, the bar's rows are bare paper, and the
           title sits in a window cut out of the rings at the bottom right. The desk's
           widgets stand on the rings like the rest of the page (solid cards since
           2026-11-15): a window cut for them read as a missing patch when they hid.
  lock     the cover itself: the book as a block of dots with a window carved out of
           it on the left, where hyprlock (@papel/hypr/hyprlock.conf) sets the time, the
           date and the field. WINDOW is that window in px; the template's positions are
           measured against it.

Ink only (fg0, a warm grey for the rings, the selection's pale yellow for halos): the
signal colour never appears. Discs and rings are drawn analytically (signed distance,
1 px anti-aliasing) at each master's own size, never resized from a bigger render.
Deterministic: no randomness, no wall-clock input; --check compares decoded pixels with
scenes.py's tolerance. Reads ~/Repos/logo-peonza (or $PEONZA_BRAND) for the desktop's
silhouette; without it, it skips with a message.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenes import BRAND, ROOT, colormath, differs, finish, hexrgb, mark, save, tokens  # noqa: E402

HERE = Path(__file__).resolve().parent
TEXT = HERE / "tractatus.json"
OUT = ROOT / "assets" / "wallpapers" / "papel.jpg"
LOCK = ROOT / "assets" / "wallpapers" / "papel-lock.jpg"
FONT = ROOT / "assets" / "fonts" / "SpaceMono-Bold.ttf"
FONT_REGULAR = ROOT / "assets" / "fonts" / "SpaceMono-Regular.ttf"

CELL = 30                       # px at 1920 wide: a 64 x 36 grid (40 px at 2560, the cover's own cell)
COLS, ROWS = 64, 36
R_MIN, R_MAX = 0.17, 0.42       # a proposition's radius, in cells, shortest to longest
RING = 0.12                     # a hollow proposition's stroke, in cells
AXIS_R, AXIS_W = 0.10, 0.05     # the empty cells' rings (the cover: r 4, stroke 2 at cell 40)
EDGE = 0.19                     # how much heavier a silhouette's outermost cells are (R_MAX stays in its cell)

# Desktop: the peonza's 100-unit box in cells, and where its top-left corner sits.
BOX, AT = 37, (22, 1)        # the stem stays left of Hito's layer (x >= 1360, «hoy» + 5 tasks)
TITLE = ("Tractatus logico-philosophicus", "526 proposiciones · un punto cada una")
# Lock: the book's block and the window carved out of it, in cells (col0, row0, col1, row1).
BLOCK = (16, 6, 50, 30)
WINDOW = (17, 10, 33, 25)
# Cells left as bare paper under text that sits on the lock picture, the cover's own way
# of setting a title: (col0, row0, col1, row1): the lockup and the two ends of the foot
# line in @papel/hypr/hyprlock.conf.
LOCK_QUIET = ((1, 1, 7, 3), (1, 34, 10, 35), (52, 34, 63, 35))

# What a paper picture may cost, measured on the 1920 render (scenes.py's own sizes):
# mostly paper (a mean luminance at least this fraction of bg0's, so a darker paper keeps
# the same budget), the bar's rows and the desk's left third free of text dots.
BUDGET = {"paper_fraction_min": 0.90, "ink_fraction_max": 0.10, "quiet_rows": 2, "quiet_cols": 24}


def propositions() -> list[tuple[str, int, int]]:
    return [tuple(p) for p in json.loads(TEXT.read_text(encoding="utf-8"))["propositions"]]


def spine(num: str) -> bool:
    """The cover's filled/hollow rule for a text that is all numbered: up to three decimals."""
    return len(num.partition(".")[2]) <= 3


def radii(props: list[tuple[str, int, int]]) -> np.ndarray:
    """Each proposition's radius in cells: the cover's ln(len+1)^2, stretched to R_MIN..R_MAX."""
    v = np.log(np.array([p[1] for p in props], dtype=np.float64) + 1) ** 2
    return R_MIN + (R_MAX - R_MIN) * (v - v.min()) / (v.max() - v.min())


def palette(t: dict) -> dict[str, np.ndarray]:
    c = t["colors"]
    return {"paper": hexrgb(c["bg0"]), "ink": hexrgb(c["fg0"]), "axis": hexrgb(c["line"]),
            "halo": hexrgb(t["term"]["selection_bg"]), "grey": hexrgb(c["fg1"])}


# ── the grid ──────────────────────────────────────────────────────────────────
class Sheet:
    """Per-cell drawing orders: radius (cells), kind (0 nothing, 1 disc, 2 ring), and a
    halo radius (cells, 0 for none). The screen's grid unless told otherwise (the
    launcher's panel, panels.py, has its own)."""

    def __init__(self, rows: int = ROWS, cols: int = COLS) -> None:
        self.r = np.full((rows, cols), AXIS_R)
        self.kind = np.full((rows, cols), 2, dtype=np.int8)
        self.width = np.full((rows, cols), AXIS_W)
        self.text = np.zeros((rows, cols), dtype=bool)
        self.halo = np.zeros((rows, cols))

    def write(self, cells: list[tuple[int, int]], weight: np.ndarray | None = None) -> None:
        """The whole book in `cells` (row-major order): proposition k*N//len(cells) in cell k."""
        props = propositions()
        rad = radii(props)
        n = len(props)
        for k, (y, x) in enumerate(cells):
            i = k * n // len(cells)
            num, _, q = props[i]
            self.r[y, x] = rad[i] * (1 + EDGE * (weight[y, x] if weight is not None else 0))
            self.kind[y, x] = 1 if spine(num) else 2
            self.width[y, x] = RING
            self.text[y, x] = True
            self.halo[y, x] = min(rad[i] * 2 + 0.1, 0.62) if q else 0.0

    def clear(self, mask: np.ndarray) -> None:
        self.kind[mask] = 0
        self.text[mask] = False
        self.halo[mask] = 0.0


def raster(sheet: Sheet, w: int, h: int, pal: dict[str, np.ndarray]) -> np.ndarray:
    """The sheet at w x h: halos first, then each cell's disc or ring, analytically."""
    rows, cols = sheet.r.shape
    cell = w / cols
    px = (np.arange(w) + 0.5) / cell
    py = (np.arange(h) + 0.5) / cell
    ix = np.minimum(px.astype(int), cols - 1)
    iy = np.minimum(py.astype(int), rows - 1)
    dx = (px - ix - 0.5) * cell
    dy = (py - iy - 0.5) * cell
    d = np.sqrt(dx[None, :] ** 2 + dy[:, None] ** 2)
    rgb = np.broadcast_to(pal["paper"], (h, w, 3)).copy()

    # Halos reach past their cell: each one is painted over its own square.
    for y, x in zip(*np.nonzero(sheet.halo)):
        rr = sheet.halo[y, x] * cell
        cx, cy = (x + 0.5) * cell, (y + 0.5) * cell
        x0, x1 = max(0, int(cx - rr - 2)), min(w, int(cx + rr + 3))
        y0, y1 = max(0, int(cy - rr - 2)), min(h, int(cy + rr + 3))
        xx = np.arange(x0, x1) + 0.5 - cx
        yy = np.arange(y0, y1) + 0.5 - cy
        cov = np.clip(rr - np.sqrt(xx[None, :] ** 2 + yy[:, None] ** 2) + 0.5, 0, 1)
        rgb[y0:y1, x0:x1] += (pal["halo"] - rgb[y0:y1, x0:x1]) * cov[..., None]

    r = sheet.r[iy][:, ix] * cell
    sw = np.maximum(sheet.width[iy][:, ix] * cell, 1.0)
    kind = sheet.kind[iy][:, ix]
    disc = np.clip(r - d + 0.5, 0, 1)
    ring = np.clip(sw / 2 - np.abs(d - (r - sw / 2)) + 0.5, 0, 1)
    cov = np.where(kind == 1, disc, np.where(kind == 2, ring, 0.0))
    ink = np.where((sheet.text[iy][:, ix])[..., None], pal["ink"], pal["axis"])
    return rgb + (ink - rgb) * cov[..., None]


def type_on(rgb: np.ndarray, lines: list[tuple[str, Path, float, np.ndarray, float, float]]) -> np.ndarray:
    """Space Mono lines: (text, font file, size px, colour, left px, baseline px)."""
    h, w = rgb.shape[:2]
    for text, font, size, col, x, base in lines:
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).text((x, base), text, fill=255, anchor="ls",
                               font=ImageFont.truetype(str(font), round(size)))
        a = np.asarray(m, dtype=np.float64)[..., None] / 255.0
        rgb = rgb + (col - rgb) * a
    return rgb


# ── desktop ───────────────────────────────────────────────────────────────────
def coverage(file: str, box: int = BOX, sub: int = 8) -> np.ndarray:
    """A brand mark's RGBA averaged per cell over the box x box cells it is drawn into."""
    a = mark(file, box=box * sub)
    return a.reshape(box, sub, box, sub, 4).mean(axis=(1, 3))


def peonza_cells() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(inside, engraving, edge weight) on the screen's grid: the mark's box at AT."""
    sil = coverage("peonza-silhouette.svg")[..., 3]
    full = coverage("peonza.svg")
    dark = full[..., 3] * (1 - full[..., :3].mean(axis=-1))          # the black engraving
    inside = np.zeros((ROWS, COLS), dtype=bool)
    cut = np.zeros((ROWS, COLS), dtype=bool)
    x0, y0 = AT
    win = (slice(max(0, y0), min(ROWS, y0 + BOX)), slice(max(0, x0), min(COLS, x0 + BOX)))
    src = (slice(win[0].start - y0, win[0].stop - y0), slice(win[1].start - x0, win[1].stop - x0))
    inside[win] = sil[src] >= 0.5
    cut[win] = dark[src] >= 0.3
    # Outermost cells: inside, with a 4-neighbour outside.
    pad = np.pad(inside, 1)
    edge = inside & ~(pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:])
    # The engraving runs inside the outline only; on the outline it would eat the silhouette.
    return inside, cut & inside & ~edge, edge.astype(np.float64)


def desktop(w: int, h: int, t: dict) -> Image.Image:
    pal = palette(t)
    sheet = Sheet()
    inside, cut, edge = peonza_cells()
    if inside[:BUDGET["quiet_rows"]].any() or inside[:, :BUDGET["quiet_cols"]].any():
        raise SystemExit("paper: the peonza reaches the bar's rows or the desk's left third")
    data = inside & ~cut
    sheet.write([tuple(c) for c in np.argwhere(data)], edge)
    # The engraving keeps its axis rings: a faint line drawn through the dark field.
    # The title's window: two lines set right on the grid's last columns, rings cleared
    # one cell around them.
    u = w / 1920
    size, small = 22 * u, 14 * u
    right = (COLS - 2) * CELL * u
    f1, f2 = ImageFont.truetype(str(FONT), round(size)), ImageFont.truetype(str(FONT_REGULAR), round(small))
    w1, w2 = f1.getlength(TITLE[0]), f2.getlength(TITLE[1])
    base1, base2 = (ROWS - 3.35) * CELL * u, (ROWS - 2.4) * CELL * u
    c0 = int((right - max(w1, w2)) / (CELL * u)) - 1
    hole = cells([(0, 0, COLS, BUDGET["quiet_rows"]),     # the bar floats on bare paper
                  (c0, ROWS - 5, COLS - 1, ROWS - 1)])       # the title's window
    if (hole & sheet.text).any():
        raise SystemExit("paper: the title's window cuts into the peonza")
    sheet.clear(hole)
    rgb = raster(sheet, w, h, pal)
    rgb = type_on(rgb, [(TITLE[0], FONT, size, pal["ink"], right - w1, base1),
                        (TITLE[1], FONT_REGULAR, small, pal["grey"], right - w2, base2)])
    return finish(rgb)


# ── lock ──────────────────────────────────────────────────────────────────────
def lock(w: int, h: int, t: dict) -> Image.Image:
    pal = palette(t)
    sheet = Sheet()
    block, hole = cells([BLOCK]), cells([WINDOW])
    sheet.write([tuple(c) for c in np.argwhere(block & ~hole)])
    sheet.clear(hole | cells(LOCK_QUIET))
    return finish(raster(sheet, w, h, pal))


def cells(rects) -> np.ndarray:
    """A grid mask of (col0, row0, col1, row1) rectangles, ends exclusive."""
    m = np.zeros((ROWS, COLS), dtype=bool)
    for c0, r0, c1, r1 in rects:
        m[r0:r1, c0:c1] = True
    return m


def window_px(w: int = 1920) -> tuple[int, int, int, int]:
    """The lock's window in px at width w: left, top, right, bottom."""
    s = w / COLS
    return tuple(round(v * s) for v in WINDOW)  # type: ignore[return-value]


# ── budget and outputs ────────────────────────────────────────────────────────
def over_budget(img: Image.Image, t: dict, quiet: bool) -> list[str]:
    a = np.asarray(img.convert("RGB"), dtype=np.float64) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    lum = lin @ np.array([0.2126, 0.7152, 0.0722])
    out = []
    floor = BUDGET["paper_fraction_min"] * colormath.luminance(t["colors"]["bg0"])
    if lum.mean() < floor:
        out.append(f"mean luminance {lum.mean():.3f} < {floor:.3f}, "
                   f"{BUDGET['paper_fraction_min']:.0%} of the paper's (paper first)")
    ink = (lum < colormath.luminance(t["colors"]["fg1"])).mean()
    if ink > BUDGET["ink_fraction_max"]:
        out.append(f"ink covers {ink:.1%} > {BUDGET['ink_fraction_max']:.0%}")
    if quiet:
        cell = img.width / COLS
        axis = colormath.luminance(t["colors"]["line"])
        rows = lum[: round(BUDGET["quiet_rows"] * cell)]
        cols = lum[:, : round(BUDGET["quiet_cols"] * cell)]
        for name, part in (("the bar's rows", rows), ("the desk's left third", cols)):
            if part.min() < axis - 0.02:
                out.append(f"{name} hold ink darker than the axis rings ({part.min():.3f})")
    return out


def outputs(t: dict) -> list[tuple[Path, Image.Image, bool]]:
    return [(OUT, desktop(2560, 1440, t), True), (LOCK, lock(1920, 1080, t), False)]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a master is stale or over budget")
    ap.add_argument("--out", type=Path, help="write both pictures into this folder instead")
    a = ap.parse_args(argv)
    if not (BRAND / "peonza-silhouette.svg").exists():
        print(f"paper: skip (no {BRAND / 'peonza-silhouette.svg'}; set PEONZA_BRAND to the brand's mark/ folder)")
        return 0
    # Raw, not tokens.load(): the contract names these masters, so it validates only once they exist.
    t = json.loads((tokens.THEMES_SRC / "papel.json").read_text(encoding="utf-8"))
    bad = []
    for path, img, quiet in outputs(t):
        bad += [f"{path.name}: {b}" for b in over_budget(img, t, quiet)]
        if a.check:
            why = differs(path, img)
            if why:
                bad.append(f"stale: {path.relative_to(ROOT)}: {why} (run python3 theme/wallpaper/paper.py)")
        else:
            dst = a.out / path.name if a.out else path
            dst.parent.mkdir(parents=True, exist_ok=True)
            save(dst, img)
            print(f"wrote {dst}")
    for b in bad:
        print(f"paper: {b}")
    if a.check and not bad:
        print("paper: ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
