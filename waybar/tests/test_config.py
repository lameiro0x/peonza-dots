"""waybar/config.jsonc against contracts/constants.json and the bar's hard rules."""

from __future__ import annotations

import json
import re
import unittest

from gtkcss import CONSTANTS, ROOT, THEMES, WAYBAR, load_config

C = CONSTANTS
SLOT_DIR = f"$XDG_RUNTIME_DIR/{C['runtime']}/{C['waybar_dir']}"
DISPATCH = "hyprctl dispatch"  # a constant, so tools/lint.py never reads a pattern as a call
LUA_DISPATCH = re.compile(rf"^{DISPATCH} 'hl\.[^']*'$")
# Anything that makes /bin/sh more than an exec: Waybar kills exec children by
# process group, so a pipeline or redirect leaves an orphan behind on every reload.
SHELL_CONSTRUCT = re.compile(r"[|><;&`]|\$\(")
PUA = re.compile("[%s-%s%s-%s]" % (chr(0xE000), chr(0xF8FF), chr(0xF0000), chr(0x10FFFF)))


PEONZA = chr(int(C["glyph"]["codepoint"].removeprefix("U+"), 16))


def is_material_design(ch: str) -> bool:
    return 0xF0001 <= ord(ch) <= 0xF1AF0


class ConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = load_config()
        cls.mods = {k: v for k, v in cls.cfg.items() if isinstance(v, dict)}

    def test_one_strip_as_tall_as_the_frames_top_edge(self) -> None:
        tops = [json.loads((ROOT / "themes" / t / "theme.json").read_text(encoding="utf-8"))
                ["geometry"]["frame_top"] for t in THEMES]
        self.assertEqual((self.cfg["layer"], self.cfg["position"]), ("top", "top"))
        self.assertTrue(min(tops) <= self.cfg["height"] <= max(tops), (self.cfg["height"], tops))
        self.assertIs(self.cfg["reload_style_on_change"], True)

    def test_peonza_where_the_distro_logo_was(self) -> None:
        self.assertEqual(self.mods["custom/peonza"]["format"], PEONZA)
        self.assertNotIn("custom/distro", self.mods)

    def test_layout(self) -> None:
        self.assertEqual(self.cfg["modules-left"], ["custom/peonza", "custom/window"])
        self.assertEqual(self.cfg["modules-center"], ["group/workspaces"])
        self.assertEqual(self.cfg["modules-right"],
                         ["custom/agents", "wireplumber", "network", "clock"])

    def test_every_listed_module_is_configured(self) -> None:
        listed = self.cfg["modules-left"] + self.cfg["modules-center"] + self.cfg["modules-right"]
        listed += self.mods["group/workspaces"]["modules"]
        for m in listed:
            self.assertIn(m, self.mods, f"{m} is listed but has no config block")

    def test_desktop_has_no_laptop_modules(self) -> None:
        for m in self.mods:
            self.assertNotRegex(m, r"battery|backlight|brightness", m)

    def test_eleven_slots_in_order(self) -> None:
        want = [f"custom/ws{n}" for n in range(1, C["max_ws"] + 1)]
        self.assertEqual(self.mods["group/workspaces"]["modules"], want)
        self.assertEqual(len(want), 11)

    def test_slot_reads_its_output_file_and_wakes_on_the_signal(self) -> None:
        for n in range(1, C["max_ws"] + 1):
            with self.subTest(slot=n):
                m = self.mods[f"custom/ws{n}"]
                self.assertEqual(m["exec"], f"cat {SLOT_DIR}/$WAYBAR_OUTPUT_NAME-{n}.json")
                self.assertEqual(m["signal"], C["signal"])
                self.assertEqual(m["return-type"], "json")

    def test_slot_click_and_scroll_are_lua(self) -> None:
        for n in range(1, C["max_ws"] + 1):
            with self.subTest(slot=n):
                m = self.mods[f"custom/ws{n}"]
                self.assertEqual(m["on-click"], f"{DISPATCH} '{C['dispatch_focus_ws'] % n}'")
                self.assertEqual(m["on-scroll-up"], "hyprctl dispatch 'hl.dsp.focus({ workspace = \"e+1\" })'")
                self.assertEqual(m["on-scroll-down"], "hyprctl dispatch 'hl.dsp.focus({ workspace = \"e-1\" })'")

    def test_every_hyprctl_dispatch_anywhere_is_lua(self) -> None:
        for name, m in self.mods.items():
            for key, val in m.items():
                if isinstance(val, str) and "hyprctl" in val:
                    with self.subTest(module=name, key=key):
                        self.assertRegex(val, LUA_DISPATCH)

    def test_window_and_agents_read_agentd(self) -> None:
        w, a = self.mods["custom/window"], self.mods["custom/agents"]
        self.assertEqual(w["exec"], f"cat {SLOT_DIR}/$WAYBAR_OUTPUT_NAME-window.json")
        self.assertEqual(a["exec"], f"cat {SLOT_DIR}/{C['agents_file']}")
        for m in (w, a):
            self.assertEqual(m["signal"], C["signal"])
            self.assertEqual(m["return-type"], "json")
        self.assertEqual(a["on-click"], f"qs -c {C['qs_config']} ipc call {C['sidebar_ipc']} toggle")

    def test_no_exec_has_shell_constructs(self) -> None:
        for name, m in self.mods.items():
            if "exec" in m:
                with self.subTest(module=name):
                    self.assertNotRegex(m["exec"], SHELL_CONSTRUCT)

    def test_glyphs_are_escapes_of_material_design(self) -> None:
        raw = (WAYBAR / "config.jsonc").read_text(encoding="utf-8")
        self.assertIsNone(PUA.search(raw), "type glyphs as \\u escapes, never raw PUA characters")
        decoded = "".join(str(v) for m in self.mods.values() for v in m.values())
        glyphs = PUA.findall(decoded)
        self.assertTrue(glyphs, "expected Nerd Font glyphs in the config")
        for ch in glyphs:
            self.assertTrue(is_material_design(ch) or ch == PEONZA,
                            f"U+{ord(ch):X} is neither a Material Design (nf-md) glyph nor the peonza")


if __name__ == "__main__":
    unittest.main()
