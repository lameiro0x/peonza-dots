"""waybar/style.css static rules: what GTK3 accepts, the signal budget, no reflow,
no glow, nothing that moves on its own.

The real parser gate is gtk3_css_gate.py (needs python-gobject, Linux). This file is
its offline twin: an allowlist of the properties GTK 3.24 knows, so a typo or a
web-only property fails on the Mac before Waybar would exit 1 on it.
"""

from __future__ import annotations

import re
import unittest

from gtkcss import THEMES, css_text, defines, palette_css, rules

# GTK 3.24 style properties (gtk/gtkcssstylepropertyimpl.c + shorthands), the ones a
# bar could plausibly want. Anything else is either unknown to GTK3 (Waybar exits 1)
# or something this sheet should not need.
GTK3_PROPS = {
    "color", "opacity", "font", "font-family", "font-size", "font-style", "font-weight",
    "font-variant", "font-stretch", "font-feature-settings", "letter-spacing",
    "text-decoration", "text-decoration-line", "text-decoration-color", "text-shadow",
    "background", "background-color", "background-image", "background-clip",
    "background-origin", "background-position", "background-repeat", "background-size",
    "border", "border-width", "border-style", "border-color", "border-radius",
    "border-top", "border-right", "border-bottom", "border-left",
    "border-top-left-radius", "border-top-right-radius",
    "border-bottom-left-radius", "border-bottom-right-radius",
    "outline", "outline-width", "outline-style", "outline-color", "outline-offset",
    "box-shadow", "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "min-width", "min-height",
    "transition", "transition-property", "transition-duration",
    "transition-timing-function", "transition-delay",
    "animation", "animation-name", "animation-duration", "animation-timing-function",
    "animation-iteration-count", "animation-direction", "animation-play-state",
    "animation-delay", "animation-fill-mode",
    "-gtk-icon-shadow", "-gtk-icon-effect", "-gtk-icon-source", "-gtk-icon-transform",
}
# A slot changes state constantly (focus, waiting, busy, hover). If any of these
# rules touched geometry, every focus change would reflow the row and no easing
# curve could hide it. Only `.empty` / `.off` may size a slot: they follow content.
STATEFUL = re.compile(r"\.(active|waiting|working)\b|:hover")
GEOMETRY = re.compile(r"^(padding|margin|min-width|min-height|font|font-size|font-weight|letter-spacing|border(-width)?)")
SIGNAL = re.compile(r"@signal\w*")


class StyleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = css_text("style.css")
        cls.rules = rules(cls.css)

    def test_palette_is_imported_first(self) -> None:
        self.assertTrue(self.css.lstrip().startswith('@import "palette.css";'))

    def test_style_does_not_redefine_tokens(self) -> None:
        self.assertEqual(defines(self.css), {}, "colours live in contracts/themes/*.json")

    def test_every_colour_reference_is_defined_in_every_theme(self) -> None:
        used = set(re.findall(r"@([\w-]+)", re.sub(r"@(import|keyframes)\b", "", self.css)))
        for theme in THEMES:
            known = set(defines(css_text(palette_css(theme))))
            for name in used:
                with self.subTest(theme=theme):
                    self.assertIn(name, known, f"@{name} is not a palette token")

    def test_only_gtk3_properties(self) -> None:
        for sel, decls in self.rules:
            for prop in decls:
                with self.subTest(selector=sel, prop=prop):
                    self.assertIn(prop, GTK3_PROPS)

    def test_no_hex_literals(self) -> None:
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b", self.css), "use palette tokens")

    def test_signal_only_means_waiting(self) -> None:
        for sel, decls in self.rules:
            if any(SIGNAL.search(v) for v in decls.values()):
                with self.subTest(selector=sel):
                    self.assertIn(".waiting", sel, f"signal outside a waiting state: {sel}")

    def test_waiting_rings_on_the_bar_on_the_pill_and_on_the_counter(self) -> None:
        sels = dict(self.rules)
        self.assertEqual(sels["#workspaces .waiting"]["box-shadow"], "inset 0 0 0 2px @signal")
        self.assertEqual(sels["#workspaces .waiting.active"]["box-shadow"], "inset 0 0 0 2px @signal_on_pill")
        self.assertEqual(sels["#custom-agents.waiting"]["box-shadow"], "inset 0 0 0 2px @signal")

    def test_active_slot_is_the_flat_pill(self) -> None:
        sels = dict(self.rules)
        active = sels["#workspaces .active, #workspaces .active:hover"]
        self.assertEqual((active["background-color"], active["color"]), ("@pill", "@ink_on_pill"))

    def test_the_bar_floats_on_plates(self) -> None:
        # No strip: a transparent window, and the three module groups are the plates
        # (their colour is what test_contrast composites every ink over).
        sels = dict(self.rules)
        self.assertEqual(sels["window#waybar"]["background-color"], "transparent")
        plates = sels[".modules-left, .modules-center, .modules-right"]
        self.assertEqual(plates["background-color"], "@bar_bg")
        self.assertNotEqual(plates.get("margin", "0"), "0", "plates float off the edge")

    def test_no_glow(self) -> None:
        # Shadows are contours (inset, no blur) or nothing; a halo is the old look.
        for sel, decls in self.rules:
            for part in decls.get("box-shadow", "none").split(","):
                with self.subTest(selector=sel):
                    self.assertRegex(part.strip(), r"^(none|inset 0 0 0 \d+px @[\w]+)$")

    def test_nothing_animates_on_its_own(self) -> None:
        # GTK3 repaints the whole bar every frame while an animation runs; state
        # changes ease through transitions, which stop when they arrive.
        self.assertNotIn("@keyframes", self.css)
        for sel, decls in self.rules:
            for prop in decls:
                self.assertFalse(prop.startswith("animation"), f"{sel} {prop}")

    def test_peonza_glyph_font_comes_first(self) -> None:
        sels = dict(self.rules)
        fam = sels["#custom-peonza"]["font-family"]
        self.assertTrue(fam.startswith('"Ryce Peonza", "JetBrainsMono Nerd Font"'), fam)

    def test_state_changes_never_touch_geometry(self) -> None:
        for sel, decls in self.rules:
            if sel.startswith("#workspaces") and STATEFUL.search(sel):
                for prop in decls:
                    with self.subTest(selector=sel, prop=prop):
                        self.assertNotRegex(prop, GEOMETRY)


if __name__ == "__main__":
    unittest.main()
