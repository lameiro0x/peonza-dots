"""Contrast floor of the fallback bar, in every theme (vault decision 2026-09-27).

Every colour the bar puts on screen, composited over what is really under it:
@bar_bg over the theme's OWN top band (the lighter of its two sizes: since the
four themes have their own pictures, a theme's bar never sits on another's), the
pill over that, the hover tint over that. Text needs 4.5:1, marks (glyph-only modules, the empty slot's
numeral, the key column, rings) need 3:1. Each theme resolves the sheet through
its own themes/<id>/waybar/palette.css.

    python3 waybar/tests/test_contrast.py --table    print every pair and its ratio

The bands come from theme/wallpaper/bands.json (written by the wallpaper generator);
#1a1a22 is the stand-in only if that file is missing.
"""

from __future__ import annotations

import json
import re
import sys
import unittest

from gtkcss import RGBA, ROOT, THEMES, Palette, css_text, hexof, over, ratio, rules

sys.path.insert(0, str(ROOT / "agentd"))
from agentd import render  # noqa: E402
from agentd.claude import ClaudeHome  # noqa: E402
from agentd.hypr import FakeHypr  # noqa: E402
from agentd.model import collect  # noqa: E402
from agentd.procfs import Proc  # noqa: E402

BANDS = ROOT / "theme" / "wallpaper" / "bands.json"
_BANDS = json.loads(BANDS.read_text(encoding="utf-8")) if BANDS.exists() else {"themes": {}}


def top_band(theme: str) -> str:
    """The lighter top band of the theme's two wallpaper sizes: what its bar covers."""
    tops = [b["top"] for b in _BANDS["themes"].get(theme, {}).values()]
    return max(tops, key=lambda b: b["luminance"])["average"] if tops else "#1a1a22"
TEXT, MARK = 4.5, 3.0
# Selectors whose `color` paints a glyph or a placeholder, never words.
MARK_SELECTORS = {
    "#custom-peonza",
    "#custom-ws1, #custom-ws2, #custom-ws3, #custom-ws4, #custom-ws5, #custom-ws6, "
    "#custom-ws7, #custom-ws8, #custom-ws9, #custom-ws10, #custom-ws11",
    "#wireplumber.muted, #network.disconnected, #network.linked",
}
SPAN = re.compile(r'<span foreground="(#[0-9a-fA-F]{6})">')
SLOT_FILE = re.compile(r".+-\d+\.json")
# agentd's own stage worlds: four sessions in every state, and eight slots full.
FIXTURES = [ROOT / "agentd" / "tests" / "fixtures" / d for d in ("stage", "stage8")]


class Surfaces:
    def __init__(self, pal: Palette, sheet: list[tuple[str, dict[str, str]]]) -> None:
        wall = pal.resolve(top_band(pal.theme))
        self.bar = over(pal.resolve("@bar_bg"), wall)
        hover = next(d["background-color"] for s, d in sheet if ":hover" in s and ".active" not in s)
        self.hover = over(pal.resolve(hover), self.bar)
        self.pill = over(pal.resolve("@pill"), self.bar)
        self.tooltip = over(pal.resolve("@tooltip_bg"), wall)

    def under(self, selector: str) -> dict[str, RGBA]:
        """Every surface a selector list can paint on (union over its parts)."""
        found: dict[str, RGBA] = {}
        for part in (p.strip() for p in selector.split(",")):
            if part.startswith("tooltip"):
                found["tooltip"] = self.tooltip
            elif ".active" in part:
                found["pill"] = self.pill
            elif part.startswith(("#custom-ws", "#workspaces")):
                found |= {"bar": self.bar, "hover": self.hover}
            else:
                found["bar"] = self.bar
        return found


def slots(theme: str) -> list[tuple[str, dict]]:
    """What agentd writes for the stage worlds in this theme's greys."""
    pal = render.load_palette(ROOT / "themes" / theme / "theme.json")
    out = []
    for fx in FIXTURES:
        snap = collect(FakeHypr(fx / "hypr"), Proc(fx / "proc"), ClaudeHome(fx / "claude"), str(fx / "fs"))
        out += [(f"{fx.name}/{name}", p) for name, p in render.waybar(snap, pal).items()
                if SLOT_FILE.fullmatch(name)]
    return out


def pairs(theme: str) -> list[tuple[str, str, str, float, float]]:
    """(what, colour, surface, ratio, floor) for everything the bar draws in `theme`."""
    pal = Palette(theme)
    sheet = rules(css_text("style.css"))
    surf = Surfaces(pal, sheet)
    out = []
    for sel, decls in sheet:
        if sel.startswith("@keyframes"):
            continue
        under = surf.under(sel)
        if "color" in decls:
            floor = MARK if sel in MARK_SELECTORS else TEXT
            for name, bg in under.items():
                fg = over(pal.resolve(decls["color"]), bg)
                out.append((f"{sel} color", decls["color"], name, ratio(fg, bg), floor))
        ring = re.match(r"inset 0 0 0 \d+px ([^,]+)", decls.get("box-shadow", ""))
        if ring:
            for name, bg in under.items():
                fg = over(pal.resolve(ring.group(1)), bg)
                out.append((f"{sel} ring", ring.group(1), name, ratio(fg, bg), MARK))
    # Slot ink comes from agentd's Pango markup and beats CSS: check agentd's real
    # output on the surface its classes put it on. Spans: key numeral, icon,
    # project, title — the first two are the key column (marks), the rest is text.
    for what, slot in slots(theme):
        under = surf.under("#workspaces .active" if "active" in slot["class"] else "#workspaces")
        for i, col in enumerate(SPAN.findall(slot["text"])):
            for name, bg in under.items():
                out.append((f"{what} span {i + 1}", col, name,
                            ratio(pal.resolve(col), bg), MARK if i < 2 else TEXT))
    return out


class ContrastTest(unittest.TestCase):
    def test_floor_in_every_theme(self) -> None:
        for theme in THEMES:
            rows = pairs(theme)
            self.assertGreater(len(rows), 40)
            self.assertTrue(any(" span " in r[0] for r in rows), "agentd's slots were not checked")
            for what, col, name, r, floor in rows:
                with self.subTest(theme=theme, what=what, surface=name):
                    self.assertGreaterEqual(r, floor, f"{col} on {name}: {r:.2f}:1 < {floor}:1")

    def test_waiting_ring_reads_on_every_surface(self) -> None:
        for theme in THEMES:
            rows = [r for r in pairs(theme) if ".waiting" in r[0] and r[0].endswith("ring")]
            self.assertEqual({r[2] for r in rows}, {"bar", "hover", "pill"}, theme)


if __name__ == "__main__":
    if "--table" in sys.argv:
        for theme in THEMES:
            pal = Palette(theme)
            print(f"\n{theme}: bar = @bar_bg over {top_band(theme)} = "
                  f"{hexof(Surfaces(pal, rules(css_text('style.css'))).bar)}")
            for what, col, name, r, floor in pairs(theme):
                print(f"{'ok ' if r >= floor else 'LOW'} {r:5.2f}:1 (>= {floor}) {col:<22} on {name:<7} {what}")
        sys.exit(0)
    unittest.main()
