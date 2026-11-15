#!/usr/bin/env python3
"""despiece.png: Tinta's bare desk drawn up as an exploded view, for the README.

    python3 -I tools/showcase/post/despiece.py RAW_DIR MEDIA_DIR

The shot sits on a sheet in Tinta's ink; numbered balloons in the margin point at each
part with a thin leader, and a title block closes the corner, like the parts-list sheet
on Tinta's wallpaper. The balloons are filled, the wallpaper's own 1-3 are hollow, so the
two numberings never read as one. PARTS is the legend the README's parts table follows.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stills import KB, font, save_png, shot  # noqa: E402

BG, LINE, FG0, FG1, FG2 = "#0a0a0a", "#3a3a3a", "#f0f0f0", "#b4b4b4", "#9a9a9a"
SCALE, X0, Y0 = 0.75, 180, 170           # the shot on the sheet
SHEET = (1800, 1220)

# number, part, its point on the 1920x1080 shot, and where its balloon sits on the sheet.
# The points sit on a part's edge, never on its text, so no leader crosses a label.
PARTS = [
    (1, "peonza logo: still, spinning while agents work, nodding when one waits", (25, 14), (199, 92)),
    (2, "meters: cpu, memory, network", (300, 14), (400, 92)),
    (3, "workspaces, named after the AI session in each", (880, 14), (840, 92)),
    (4, "now playing (Aria, the music drawer)", (1370, 14), (1210, 92)),
    (5, "«te espera»: sessions waiting for you", (1632, 14), (1410, 92)),
    (6, "desk clock", (66, 190), (95, 312)),
    (7, "edge visualiser (cava, in dots)", (40, 560), (95, 590)),
    (8, "binary clock", (66, 905), (95, 850)),
    (9, "the wallpaper: «Despiece», a parts-list sheet", (447, 693), (515, 1060)),
    (10, "desk peonza", (962, 958), (904, 1060)),
    (11, "Hito: today's tasks", (1894, 220), (1705, 335)),
    (12, "agent HUD: sessions, load, temperatures", (1894, 700), (1705, 700)),
]


def on_sheet(p: tuple[int, int]) -> tuple[float, float]:
    return X0 + p[0] * SCALE, Y0 + p[1] * SCALE


def draw(raw: Path, media: Path) -> None:
    sheet = Image.new("RGB", SHEET, BG)
    desk = shot(raw, "part-despiece").resize((int(1920 * SCALE), int(1080 * SCALE)), Image.Resampling.LANCZOS)
    sheet.paste(desk, (X0, Y0))
    d = ImageDraw.Draw(sheet)
    w, h = SHEET

    # The sheet's border and the shot's frame.
    d.rectangle([24, 24, w - 25, h - 25], outline=LINE, width=2)
    d.rectangle([X0 - 1, Y0 - 1, X0 + desk.width, Y0 + desk.height], outline=FG2, width=1)

    num = font(22, 700)
    r = 21
    for n, _, point, balloon in PARTS:
        px, py = on_sheet(point)
        bx, by = balloon
        # The leader stops at the balloon's rim; a dark underlay keeps it legible on the shot.
        dx, dy = px - bx, py - by
        dist = max((dx * dx + dy * dy) ** 0.5, 1)
        sx, sy = bx + dx / dist * r, by + dy / dist * r
        d.line([(sx, sy), (px, py)], fill=BG, width=5)
        d.line([(sx, sy), (px, py)], fill=FG1, width=2)
        d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=FG0, outline=BG, width=2)
        d.ellipse([bx - r, by - r, bx + r, by + r], fill=FG0, outline=BG, width=2)
        d.text((bx, by + 1), str(n), font=num, fill=BG, anchor="mm")

    # The title block, bottom right: Tinta's wallpaper's own grid of labelled cells.
    small, big, mid = font(13, 400), font(34, 500), font(18, 400)
    x0, y0, x1, y1 = 1120, h - 25 - 150, w - 25, h - 25
    d.rectangle([x0, y0, x1, y1], outline=FG2, width=2)
    rows = [y0, y0 + 74, y1]
    d.line([(x0, rows[1]), (x1, rows[1])], fill=FG2, width=1)
    cols = [x0, x0 + 170, x0 + 300, x0 + 420, x1]
    for c in cols[1:-1]:
        d.line([(c, rows[1]), (c, y1)], fill=FG2, width=1)
    d.line([(x1 - 170, y0), (x1 - 170, rows[1])], fill=FG2, width=1)

    def cell(x: int, y: int, label: str, value: str, f=mid) -> None:
        d.text((x + 12, y + 9), label, font=small, fill=FG2)
        d.text((x + 12, y + 30), value, font=f, fill=FG0)

    cell(x0, y0, "TITLE", "DESPIECE", big)
    d.text((x0 + 210, y0 + 48), "exploded view of the desktop", font=small, fill=FG1)
    cell(x1 - 170, y0, "SHEET No.", "PD-001")
    cell(cols[0], rows[1], "PROJECT", "peonza-dots")
    cell(cols[1], rows[1], "FINISH", "tinta")
    cell(cols[2], rows[1], "SCALE", "1:1")
    cell(cols[3], rows[1], "SHEET", "1/1 · 2026.11")

    save_png(sheet, media / "despiece.png", 1536 * KB)


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "legend":
        for n, part, _, _ in PARTS:
            print(f"{n}\t{part}")
        return
    if len(sys.argv) != 3:
        raise SystemExit(__doc__.strip().splitlines()[2].strip())
    draw(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    main()
