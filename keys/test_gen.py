#!/usr/bin/env python3
"""Hold hypr/binds.lua to dotsArch's hyprland.conf, plus an explicit allowlist.

    python3 -m unittest discover -s keys -v

Every bind in dotsArch must exist in binds.lua with the equivalent Lua
dispatcher, unless RYCE_DEVIATIONS says why it differs; the only binds allowed
beyond dotsArch are the ones in RYCE_EXTRAS; no hotkey may appear twice. Expected translations are written out by hand,
independently of gen.py, so a wrong mapping in the generator fails here instead
of being copied.

dotsArch is read from ~/Repos/dotsArch, or from $DOTSARCH_HYPRLAND_CONF.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

KEYS = Path(__file__).resolve().parent
sys.path.insert(0, str(KEYS))
import gen  # noqa: E402

DOTSARCH = Path(os.environ.get("DOTSARCH_HYPRLAND_CONF",
                               Path.home() / "Repos/dotsArch/.config/hypr/hyprland.conf"))

SHOT = "~/.config/hypr/scripts/screenshot.sh"

# dotsArch exec command -> ryce-pc's command. Identical unless ryce routes it
# through something better: the terminal through the capped agents slice, the
# screenshots through one script that saves to ~/Pictures/Screenshots.
EXEC = {
    "kitty": "test -x ~/.local/bin/ryce-term && exec ~/.local/bin/ryce-term || exec kitty",
    # Same launcher through bin/ryce-launcher (the panel filled); apps start as scopes
    # in app.slice so systemd-oomd sees them (rofi 2.x drun launches through
    # -run-command / -run-shell-command), in the fallback and in the wrapper alike.
    "rofi -show drun -theme ~/.config/rofi/style.rasi":
        "test -x ~/.local/bin/ryce-launcher && exec ~/.local/bin/ryce-launcher"
        " || exec rofi -show drun -theme ~/.config/rofi/style.rasi"
        ' -run-command "systemd-run --user --scope --slice=app.slice --collect {cmd}"'
        ' -run-shell-command "systemd-run --user --scope --slice=app.slice --collect kitty -e {cmd}"',
    "grim ~/Pictures/screenshot_$(date +%Y%m%d_%H%M%S).png": f"{SHOT} full",
    'grim -g "$(slurp)" ~/Pictures/screenshot_$(date +%Y%m%d_%H%M%S).png': f"{SHOT} area",
    "~/.config/hypr/scripts/screenshot-area.sh": f"{SHOT} area-copy",
    "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+",
    "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-",
    "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle": "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
}
DIRECTION = {"l": "left", "r": "right", "u": "up", "d": "down"}
MOUSE = {"movewindow": "hl.dsp.window.drag()", "resizewindow": "hl.dsp.window.resize()"}

Combo = tuple[frozenset[str], str]


def combo(mods: str | list[str], key: str) -> Combo:
    parts = mods.split() if isinstance(mods, str) else mods
    return frozenset(m.upper() for m in parts), key.lower()


def show(c: Combo) -> str:
    return " + ".join([*sorted(c[0]), c[1]])


# dotsArch binds that ryce-pc keeps on the same keys but with a different
# dispatcher: combo -> (dispatcher, why).
STEP = "function() local s = ryce.ws_step({}) if s then hl.dispatch(s) end end"
RYCE_DEVIATIONS: dict[Combo, tuple[str, str]] = {
    # dotsArch's `workspace e-1/e+1` skips EMPTY workspaces, so CTRL+arrows could
    # never reach a new one (the user's complaint, 2026-11-09). ryce.ws_step walks
    # by number, empty ones included, stops at 1 and 10 and crosses screens on the
    # way (5 -> 6), as the user asked on 2026-11-15.
    combo("CTRL", "Left"): (STEP.format(-1), "e-1 skips empty workspaces"),
    combo("CTRL", "Right"): (STEP.format(1), "e+1 skips empty workspaces"),
}

# dotsArch binds ryce-pc leaves unbound on purpose: combo -> why.
RYCE_DROPPED: dict[Combo, str] = {
    # Ten workspaces, five per screen (the user, 2026-11-15): there is no 11.
    combo("CTRL", "apostrophe"): "no workspace 11",
    combo("CTRL SHIFT", "apostrophe"): "no workspace 11",
}

# A screen by side: nothing at the edge instead of Hyprland's «Invalid monitor» banner.
SIDE = 'function() if hl.get_monitor("{0}") then hl.dispatch({1}({{ monitor = "{0}" }})) end end'

# Everything ryce-pc binds that dotsArch does not: (dispatcher, bind options).
# Adding a bind to keymap.tsv without adding it here fails the parity test.
RYCE_EXTRAS: dict[Combo, tuple[str, str]] = {
    # The agents sidebar (Quickshell config `ryce`, IpcHandler target `sidebar`).
    combo("SUPER", "a"): ('hl.dsp.exec_cmd("qs -c ryce ipc call sidebar toggle")', ""),
    # Theme selector drawer (IpcHandler `selector`), and a blind step to the next
    # theme through the switcher itself.
    combo("SUPER", "t"): ('hl.dsp.exec_cmd("qs -c ryce ipc call selector toggle")', ""),
    combo("SUPER SHIFT", "t"): ('hl.dsp.exec_cmd("~/.local/bin/ryce-theme next")', ""),
    # Desktop widgets (IpcHandler `desk`, toggle(name)): the clock, the PC stats.
    combo("SUPER", "d"): ('hl.dsp.exec_cmd("qs -c ryce ipc call desk toggle clock")', ""),
    combo("SUPER SHIFT", "d"): ('hl.dsp.exec_cmd("qs -c ryce ipc call desk toggle stats")', ""),
    # Lock now; same command as hypridle's lock_cmd, so never two hyprlocks.
    combo("SUPER", "Escape"): ('hl.dsp.exec_cmd("pidof hyprlock || hyprlock")', ""),
    # Hibernate (install/power-setup.sh; S3 suspend kills this board's chipset on wake):
    # hypridle's before_sleep_cmd locks first; the whole session, Claude Code sessions
    # included, is written to disk and comes back at the next power-on.
    combo("SUPER SHIFT", "Escape"): ('hl.dsp.exec_cmd("systemctl hibernate")', ""),
    # Clipboard history picker (cliphist + rofi); cancelling keeps the clipboard.
    combo("SUPER", "c"): ('hl.dsp.exec_cmd("~/.config/hypr/scripts/clipboard.sh")', ""),
    # Widgets: the Aria music drawer, Hito's tasks drawer, the keybinding cheat sheet
    # and the wallpaper picker (IpcHandler `aria`, `hito`, `keys`, `wallpick`).
    combo("SUPER", "m"): ('hl.dsp.exec_cmd("qs -c ryce ipc call aria toggle")', ""),
    combo("SUPER", "h"): ('hl.dsp.exec_cmd("qs -c ryce ipc call hito toggle")', ""),
    combo("SUPER", "F1"): ('hl.dsp.exec_cmd("qs -c ryce ipc call keys toggle")', ""),
    combo("SUPER SHIFT", "w"): ('hl.dsp.exec_cmd("qs -c ryce ipc call wallpick toggle")', ""),
    # Clear the desk and bring it back (hypr/despejar.lua; «escritorio»).
    combo("SUPER", "e"): ("function() ryce.despejar() end", ""),
    # English <-> Spanish on EVERY keyboard: grp:alt_shift_toggle switches only the
    # device it is typed on, and the PC has ~10 keyboard devices. switchxkblayout is
    # a hyprctl command, not a Lua dispatcher in 0.57.
    combo("SUPER", "space"): ('hl.dsp.exec_cmd("hyprctl switchxkblayout all next")', ""),
    # Annotate a selection in swappy (the CTRL+SHIFT+s area shot, editable).
    combo("SUPER SHIFT", "s"): (f'hl.dsp.exec_cmd("{SHOT} edit")', ""),
    # Screens by side (the AOC left, the Samsung right): focus one, carry the window
    # there (focus follows). Never a whole workspace: each screen keeps its own.
    combo("CTRL ALT", "Left"): (SIDE.format("l", "hl.dsp.focus"), ""),
    combo("CTRL ALT", "Right"): (SIDE.format("r", "hl.dsp.focus"), ""),
    combo("CTRL SUPER", "Left"): (SIDE.format("l", "hl.dsp.window.move"), ""),
    combo("CTRL SUPER", "Right"): (SIDE.format("r", "hl.dsp.window.move"), ""),
    # Songs without media keys (the user's keyboard has none): SUPER+ALT + arrows.
    combo("SUPER ALT", "Right"): ('hl.dsp.exec_cmd("playerctl next")', "{ locked = true }"),
    combo("SUPER ALT", "Left"): ('hl.dsp.exec_cmd("playerctl previous")', "{ locked = true }"),
    combo("SUPER ALT", "space"): ('hl.dsp.exec_cmd("playerctl play-pause")', "{ locked = true }"),
    # Media keys; locked so they work over hyprlock too.
    combo("", "XF86AudioPlay"): ('hl.dsp.exec_cmd("playerctl play-pause")', "{ locked = true }"),
    combo("", "XF86AudioPause"): ('hl.dsp.exec_cmd("playerctl play-pause")', "{ locked = true }"),
    combo("", "XF86AudioNext"): ('hl.dsp.exec_cmd("playerctl next")', "{ locked = true }"),
    combo("", "XF86AudioPrev"): ('hl.dsp.exec_cmd("playerctl previous")', "{ locked = true }"),
}


def lua_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def expected(disp: str, arg: str) -> str:
    """The Lua dispatcher call equivalent to one dotsArch keyboard bind."""
    if disp == "exec":
        if arg not in EXEC:
            raise AssertionError(f"dotsArch exec {arg!r} has no ryce equivalent: add it to keymap.tsv and EXEC")
        return f"hl.dsp.exec_cmd({lua_quote(EXEC[arg])})"
    if disp == "killactive":
        return "hl.dsp.window.close()"
    if disp == "movefocus":
        return f'hl.dsp.focus({{ direction = "{DIRECTION[arg]}" }})'
    if disp == "movewindow" and arg == "mon:+1":
        return 'hl.dsp.window.move({ monitor = "+1" })'
    if disp == "movewindow":
        return f'hl.dsp.window.move({{ direction = "{DIRECTION[arg]}" }})'
    if disp == "resizeactive":
        dx, dy = (int(v) for v in arg.split())
        return f"hl.dsp.window.resize({{ x = {dx}, y = {dy}, relative = true }})"
    if disp == "workspace":
        return f"hl.dsp.focus({{ workspace = {arg} }})"
    if disp == "movetoworkspace":
        return f"hl.dsp.window.move({{ workspace = {arg} }})"
    if disp == "focusmonitor" and arg == "+1":
        return 'hl.dsp.focus({ monitor = "+1" })'
    if disp == "fullscreen":
        return "hl.dsp.window.fullscreen()"
    if disp == "togglefloating":
        return 'hl.dsp.window.float({ action = "toggle" })'
    if disp == "pseudo":
        return "hl.dsp.window.pseudo()"
    if disp == "layoutmsg" and arg == "togglesplit":
        return 'hl.dsp.layout("togglesplit")'
    if disp == "exit":
        return "hl.dsp.exit()"
    raise AssertionError(f"dotsArch dispatcher {disp!r} {arg!r} has no known ryce equivalent")


def dotsarch_binds() -> dict[Combo, tuple[str, str, str]]:
    """(mods, key) -> (bind flags, dispatcher, argument), with $variables expanded."""
    text = DOTSARCH.read_text(encoding="utf-8")
    variables = dict(re.findall(r"^\s*\$(\w+)\s*=\s*(.+?)\s*$", text, re.M))
    binds: dict[Combo, tuple[str, str, str]] = {}
    for line in text.splitlines():
        m = re.match(r"\s*bind([a-z]*)\s*=\s*(.*)", line)
        if not m:
            continue
        flags, rest = m.groups()
        parts = [p.strip() for p in rest.split(",", 3)]
        mods = re.sub(r"\$(\w+)", lambda v: variables[v.group(1)], parts[0])
        binds[combo(mods, parts[1])] = (flags, parts[2], parts[3] if len(parts) > 3 else "")
    return binds


LUA_BIND = re.compile(r'^hl\.bind\("([^"]+)", (.+?)(?:, (\{[^}]*\}))?\)$')


def lua_binds() -> list[tuple[Combo, str, str]]:
    """(combo, dispatcher, opts) for every hl.bind line of binds.lua, in order."""
    out = []
    for line in gen.LUA_OUT.read_text(encoding="utf-8").splitlines():
        if not line.startswith("hl.bind("):
            continue
        m = LUA_BIND.match(line)
        if not m:
            raise AssertionError(f"unparseable bind in {gen.LUA_OUT.name}: {line}")
        *mods, key = m.group(1).split(" + ")
        out.append((combo(mods, key), m.group(2), m.group(3) or ""))
    return out


class Keybindings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DOTSARCH.is_file():
            raise unittest.SkipTest(f"{DOTSARCH} not found; set DOTSARCH_HYPRLAND_CONF")
        cls.dots = dotsarch_binds()
        cls.lua = lua_binds()
        print(f"\ndotsArch: {len(cls.dots)} binds | binds.lua: {len(cls.lua)} | "
              f"extras: {len(RYCE_EXTRAS)}", file=sys.stderr)

    def test_generated_file_matches_keymap(self):
        rendered = gen.render_lua(gen.parse(gen.KEYMAP.read_text(encoding="utf-8")))
        self.assertEqual(gen.LUA_OUT.read_text(encoding="utf-8"), rendered,
                         "hypr/binds.lua is stale: run python3 keys/gen.py")

    def test_every_dotsarch_bind_is_in_hyprland(self):
        lua = {c: (d, o) for c, d, o in self.lua}
        for c, (flags, disp, arg) in self.dots.items():
            with self.subTest(bind=show(c)):
                if c in RYCE_DROPPED:
                    self.assertNotIn(c, lua, f"dropped ({RYCE_DROPPED[c]}) but still bound")
                    continue
                self.assertIn(c, lua, "missing from binds.lua")
                dispatch, opts = lua[c]
                if c in RYCE_DEVIATIONS:
                    self.assertEqual(dispatch, RYCE_DEVIATIONS[c][0])
                    continue
                self.assertEqual(dispatch, MOUSE[disp] if "m" in flags else expected(disp, arg))
                if "m" in flags:
                    self.assertEqual(opts, "{ mouse = true }")
                if "e" in flags and "l" in flags:  # bindel
                    self.assertEqual(opts, "{ locked = true, repeating = true }")

    def test_extras_are_exactly_the_allowlist(self):
        lua = {c: (d, o) for c, d, o in self.lua}
        extra = set(lua) - set(self.dots)
        self.assertEqual(sorted(map(show, extra)), sorted(map(show, RYCE_EXTRAS)),
                         "a bind beyond dotsArch must be listed in RYCE_EXTRAS (and vice versa)")
        for c, want in RYCE_EXTRAS.items():
            with self.subTest(bind=show(c)):
                self.assertEqual(lua[c], want)

    def test_extras_do_not_shadow_dotsarch(self):
        self.assertEqual(set(RYCE_EXTRAS) & set(self.dots), set())

    def test_deviations_are_dotsarch_binds(self):
        self.assertLessEqual(set(RYCE_DEVIATIONS), set(self.dots), "a deviation must name a dotsArch bind")
        self.assertLessEqual(set(RYCE_DROPPED), set(self.dots), "a dropped bind must name a dotsArch bind")

    def test_no_hotkey_bound_twice(self):
        combos = [c for c, _, _ in self.lua]
        dupes = sorted(show(c) for c in set(combos) if combos.count(c) > 1)
        self.assertEqual(dupes, [], "bound twice in binds.lua")

    def test_workspace_keys_match_contract(self):
        import json
        consts = json.loads((gen.ROOT / "contracts" / "constants.json").read_text(encoding="utf-8"))
        lua = {c: d for c, d, _ in self.lua}
        for n, key in enumerate(consts["workspace_keys"], 1):
            with self.subTest(workspace=n):
                self.assertEqual(lua[combo("CTRL", key)], f"hl.dsp.focus({{ workspace = {n} }})")
                self.assertEqual(lua[combo("CTRL SHIFT", key)], f"hl.dsp.window.move({{ workspace = {n} }})")
        self.assertEqual(len(consts["workspace_keys"]), len(gen.WORKSPACES))
        bound = {int(m) for d in lua.values() for m in re.findall(r"workspace = (\d+) \}", d)}
        self.assertEqual(bound, set(gen.WORKSPACES), "a key bound to a workspace no slot shows")
        # agentd keeps a slot for every workspace a key reaches.
        self.assertGreaterEqual(consts["max_ws"], len(consts["workspace_keys"]))


class Parser(unittest.TestCase):
    def parse_one(self, row: str):
        return gen.parse(row + "\n")

    def test_rejects_bad_rows(self):
        bad = {
            "CTRL\tx\tbogus\t-": "unknown action",
            "HYPER\tx\tclose\t-": "unknown modifier",
            "CTRL\tx\tclose\t-\tsticky": "unknown flag",
            "CTRL\tx\tclose\tnow": "no argument",
            "CTRL\tx\texec\t-": "an argument",
            "CTRL\tx\tworkspace\t11": "1-10",
            "CTRL\tx\tworkspace\t0": "1-10",
            "CTRL\tx\tworkspace\te+1": "1-10",
            "CTRL\tx\twstomonitor\tl": "unknown action",
            "CTRL\tx\twsstep\t2": "wsstep must be",
            "CTRL\tx\twsstep\t-": "an argument",
            "CTRL\tx\tcall\tos.exit": "function name",
            "CTRL\tx\tcall\tryce.x()": "function name",
            "CTRL\tx\tcall\t-": "an argument",
            "CTRL\tx\tresize\t10 10": "exactly one axis",
            "CTRL\tx\tfocusmonitor\tleft": "monitor must be",
            "CTRL\tx\tmovetomonitor\t-": "an argument",
            "CTRL ALT SHIFT\tx\tclose\t-": "keyboard layout",
            "ALT SHIFT\tx\tclose\t-": "keyboard layout",
            "SUPER\tmouse:272\tclose\t-": "mouse:",
            "SUPER\tmouse:272\tdrag\t-\tlocked": "no flag",
        }
        for row, msg in bad.items():
            with self.subTest(row=row):
                with self.assertRaisesRegex(gen.KeymapError, msg):
                    self.parse_one(row)

    def test_rejects_duplicate_combo_regardless_of_modifier_order(self):
        with self.assertRaisesRegex(gen.KeymapError, "already bound"):
            gen.parse("CTRL SHIFT\tx\tclose\t-\nSHIFT CTRL\tX\tfullscreen\t-\n")

    def test_lua_string_escaping(self):
        (b,) = self.parse_one('-\tF1\texec\techo "a\\b"')
        self.assertEqual(gen.lua_dispatch(b), r'hl.dsp.exec_cmd("echo \"a\\b\"")')

    def test_ws_step_helper_is_emitted_once_before_the_binds(self):
        out = gen.render_lua(gen.parse("CTRL\tLeft\twsstep\t-1\nCTRL\tRight\twsstep\t+1\n"))
        self.assertEqual(out.count("function ryce.ws_step(d)"), 1)
        self.assertLess(out.index("function ryce.ws_step(d)"), out.index("hl.bind("))
        self.assertIn(f'hl.bind("CTRL + Left", {STEP.format(-1)})', out)
        self.assertIn(f'hl.bind("CTRL + Right", {STEP.format(1)})', out)

    def test_monitor_actions_by_side(self):
        out = gen.render_lua(gen.parse("CTRL ALT\tLeft\tfocusmonitor\tl\n"
                                       "SUPER CTRL\tRight\tmovetomonitor\tr\n"))
        self.assertIn('hl.bind("CTRL + ALT + Left", function() if hl.get_monitor("l") then '
                      'hl.dispatch(hl.dsp.focus({ monitor = "l" })) end end)', out)
        self.assertIn('hl.bind("CTRL + SUPER + Right", function() if hl.get_monitor("r") then '
                      'hl.dispatch(hl.dsp.window.move({ monitor = "r" })) end end)', out)
        (cycle,) = gen.parse("CTRL\tTab\tfocusmonitor\t+1\n")
        self.assertEqual(gen.lua_dispatch(cycle), 'hl.dsp.focus({ monitor = "+1" })')

    def test_call_runs_the_function_on_each_press(self):
        (b,) = self.parse_one("SUPER\te\tcall\tryce.despejar")
        self.assertEqual(gen.lua_dispatch(b), "function() ryce.despejar() end")

    def test_flags_render_as_bind_options(self):
        out = gen.render_lua(gen.parse("-\tF1\texec\tx\tlocked\n-\tF2\texec\ty\trepeat\n"))
        self.assertIn('hl.bind("F1", hl.dsp.exec_cmd("x"), { locked = true })', out)
        self.assertIn('hl.bind("F2", hl.dsp.exec_cmd("y"), { locked = true, repeating = true })', out)



class ExecRuleSyntax(unittest.TestCase):
    """Hyprland parses a leading `[...]` in an exec command as WINDOW RULES
    (`[workspace 2 silent] kitty`). A shell test written as `[ -x … ] && …` is eaten
    as rules and the rest never runs: CTRL+Return did nothing on the real PC
    (2026-11-09). Use `test -x` instead."""

    def test_exec_never_starts_with_bracket(self):
        text = (Path(__file__).resolve().parent / "keymap.tsv").read_text(encoding="utf-8")
        for b in gen.parse(text):
            if b.action == "exec":
                self.assertFalse(b.arg.lstrip().startswith("["),
                                 f"{b.combo}: exec starts with '[' (Hyprland exec-rules syntax): {b.arg}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
