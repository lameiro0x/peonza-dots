#!/usr/bin/env python3
"""Structure of the Hyprland config: load order, rule order, the signal budget.

    python3 -m unittest discover -s hypr/tests -v

The executable proof that Hyprland 0.57 accepts the config is
`Hyprland --verify-config` (tools/stage/verify-config.sh), once per theme. These
tests hold what that gate cannot see: binds load first, every module is
isolated, the `agentwait` rule wins, colours, blur and motion come from the
theme's palette, look.lua survives a missing palette. The load tests run
hyprland.lua for real in a stock Lua with a recording `hl` stub, once per theme
(skipped when no `lua` is on PATH). The lock screen is the rendered
themes/<id>/hypr/hyprlock.conf (template: theme/templates/hypr/hyprlock.conf).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HYPR = Path(__file__).resolve().parent.parent
ROOT = HYPR.parent
THEMES = {p.stem: json.loads(p.read_text(encoding="utf-8"))
          for p in sorted((ROOT / "contracts" / "themes").glob("*.json"))}


def light(theme: str) -> bool:
    """tools/tokens.py scheme(): paper ground, dark ink (relative luminance of bg0 > 0.5)."""
    rgb = [int(THEMES[theme]["colors"]["bg0"][i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2] > 0.5
LOCK_TEMPLATE = ROOT / "theme" / "templates" / "hypr" / "hyprlock.conf"
MODULES = ["binds", "env", "monitors", "look", "rules", "despejar", "autostart"]
LUA = shutil.which("lua") or shutil.which("lua5.4") or shutil.which("luajit")

# A recording stand-in for Hyprland's `hl` table: every call is logged as
# "<path>\t<json args>", every hl.dsp.* constructor returns a marker string.
STUB = r"""
local out = {}
local function enc(v)
    local t = type(v)
    if t == "table" then
        local parts, n = {}, #v
        if n > 0 then
            for i = 1, n do parts[#parts + 1] = enc(v[i]) end
            return "[" .. table.concat(parts, ",") .. "]"
        end
        local keys = {}
        for k in pairs(v) do keys[#keys + 1] = tostring(k) end
        table.sort(keys)
        for _, k in ipairs(keys) do parts[#parts + 1] = string.format("%q:%s", k, enc(v[k])) end
        return "{" .. table.concat(parts, ",") .. "}"
    elseif t == "string" then return string.format("%q", v)
    elseif t == "function" then return '"<fn>"'
    elseif v == nil then return "null"
    else return tostring(v) end
end
local function recorder(path)
    return setmetatable({}, {
        __index = function(_, k) return recorder(path .. "." .. k) end,
        __call = function(_, ...)
            local args = { ... }
            if path:find("^hl%.dsp%.") then return path end
            if path == "hl.on" then
                out[#out + 1] = "hl.on\t" .. enc({ args[1] })
                if args[1] == "hyprland.start" then args[2]() end
                return
            end
            out[#out + 1] = path .. "\t" .. enc(args)
        end,
    })
end
hl = recorder("hl")
package.path = arg[1] .. "/?.lua;" .. package.path
local ok, err = pcall(dofile, arg[1] .. "/hyprland.lua")
for _, line in ipairs(out) do print(line) end
if not ok then print("ERROR\t" .. (tostring(err):gsub("\n", " | "))) end
"""


def run_config(hypr_dir: Path, home: Path | None = None) -> tuple[list[tuple[str, object]], str | None]:
    """Run hyprland.lua under the stub. HOME (and so look.lua's fallback palette
    path) is an empty directory unless `home` is given."""
    with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as f:
        f.write(STUB)
    try:
        with tempfile.TemporaryDirectory() as empty:
            env = {k: v for k, v in os.environ.items() if k != "RYCE_THEME_STATE"}
            env["HOME"] = str(home or empty)
            proc = subprocess.run([LUA, f.name, str(hypr_dir)], capture_output=True, text=True,
                                  timeout=20, env=env)
    finally:
        Path(f.name).unlink()
    if proc.returncode != 0:
        raise AssertionError(f"stub run failed: {proc.stderr}")
    calls, error = [], None
    for line in proc.stdout.splitlines():
        path, _, payload = line.partition("\t")
        if path == "ERROR":
            error = payload
        else:
            calls.append((path, json.loads(payload)))
    return calls, error


def copy_hypr(dst: Path, skip: set[str] = frozenset(), theme: str | None = "origen") -> Path:
    """hypr/*.lua plus, like the live ~/.config/hypr link, one theme's palette.lua."""
    for p in HYPR.glob("*.lua"):
        if p.stem not in skip and p.stem != "local":
            shutil.copy(p, dst / p.name)
    if theme:
        shutil.copy(ROOT / "themes" / theme / "hypr" / "palette.lua", dst / "palette.lua")
    return dst


def rgb(theme: str, role: str) -> str:
    return "rgb(" + THEMES[theme]["colors"][role][1:] + ")"


def lock_conf(theme: str) -> str:
    return (ROOT / "themes" / theme / "hypr" / "hyprlock.conf").read_text(encoding="utf-8")


def blocks(text: str) -> list[str]:
    return re.findall(r"^\w[\w-]* \{.*?^\}", text, re.M | re.S)


@unittest.skipUnless(LUA, "no lua interpreter on PATH")
class LoadOrder(unittest.TestCase):
    """The whole config under the stub, once per theme."""

    @classmethod
    def setUpClass(cls):
        cls.runs = {}
        for theme in THEMES:
            with tempfile.TemporaryDirectory() as d:
                cls.runs[theme] = run_config(copy_hypr(Path(d), theme=theme))

    def each(self):
        for theme, (calls, error) in self.runs.items():
            with self.subTest(theme=theme):
                yield theme, calls, error

    @staticmethod
    def of(calls, path):
        return [a[0] for p, a in calls if p == path]

    @staticmethod
    def config(calls, key):
        (cfg,) = [a[0] for p, a in calls if p == "hl.config" and key in a[0]]
        return cfg[key]

    def test_loads_without_error(self):
        for _, _, error in self.each():
            self.assertIsNone(error)

    def test_binds_register_before_anything_else(self):
        for _, calls, _ in self.each():
            first_other = next(i for i, (p, _) in enumerate(calls) if p != "hl.bind")
            self.assertGreater(first_other, 50, "binds.lua must be the first module loaded")
            self.assertNotIn("hl.bind", [p for p, _ in calls[first_other:]])

    def test_agentwait_rule_is_last_with_a_solid_signal_border(self):
        for theme, calls, _ in self.each():
            last = self.of(calls, "hl.window_rule")[-1]
            self.assertEqual(last["match"], {"tag": "agentwait"})
            self.assertEqual(last["border_color"], rgb(theme, "signal"), "solid, no gradient")

    def test_no_glow_anywhere(self):
        for _, calls, _ in self.each():
            self.assertNotIn("glow", self.config(calls, "decoration"))
            for r in self.of(calls, "hl.window_rule"):
                self.assertNotIn("no_glow", r, r["name"])

    def test_file_dialogs_tile_beside_their_parent(self):
        for _, calls, _ in self.each():
            rules = self.of(calls, "hl.window_rule")
            tiled = [r for r in rules if r.get("tile") is True]
            self.assertIn({"class": "^xdg-desktop-portal-gtk$"}, [r["match"] for r in tiled])
            self.assertIn({"modal": True}, [r["match"] for r in tiled])
            (title,) = [r["match"]["title"] for r in tiled if "title" in r["match"]]
            for name in ("Abrir", "Abrir archivo", "Abrir archivos", "Abrir carpeta", "Guardar",
                         "Guardar como", "Seleccionar un archivo", "Elegir archivos", "Subir archivo",
                         "Open", "Open File", "Open Files", "Open Folder", "Save", "Save As",
                         "Select a File", "Choose Files", "File Upload", "Save As — Firefox"):
                self.assertRegex(name, title)
            for name in ("Picture-in-Picture", "kitty", "Reopen", "Saved"):
                self.assertNotRegex(name, title)
            self.assertFalse([r["name"] for r in tiled if r.get("float")])
            self.assertNotIn("file-dialogs", [r["name"] for r in rules if r.get("float")])
            floats = [i for i, r in enumerate(rules) if r.get("float")]
            self.assertLess(max(rules.index(r) for r in tiled), min(floats),
                            "tile rules go before the floating ones, which must still win")

    def test_borders_and_background_come_from_the_theme(self):
        for theme, calls, _ in self.each():
            general = self.config(calls, "general")
            g = THEMES[theme]["geometry"]
            self.assertEqual((general["gaps_in"], general["gaps_out"], general["border_size"]),
                             (g["gaps_in"], g["gaps_out"], g["border"]))
            # The inactive border is the theme line at low alpha: there, but barely.
            self.assertTrue(general["col"]["inactive_border"].startswith(
                "rgba(" + THEMES[theme]["colors"]["line"][1:]))
            self.assertTrue(general["col"]["active_border"].startswith(
                "rgba(" + THEMES[theme]["colors"]["fg1"][1:]))
            deco = self.config(calls, "decoration")
            self.assertEqual((deco["rounding"], deco["rounding_power"]), (g["rounding"], g["rounding_power"]))
            self.assertIs(deco["dim_modal"], False)
            self.assertEqual(self.config(calls, "misc")["background_color"], rgb(theme, "bg0"))

    def test_blur_follows_the_theme(self):
        for theme, calls, _ in self.each():
            want = THEMES[theme]["blur"]
            blur = self.config(calls, "decoration")["blur"]
            self.assertEqual((blur["enabled"], blur["size"], blur["passes"]),
                             (want["enabled"], want["size"], want["passes"]))
            self.assertIs(blur["xray"], True)
            self.assertEqual([r["name"] for r in self.of(calls, "hl.window_rule") if r.get("no_blur")], [],
                             "kitty's glass needs window blur")
            spaces = [r["match"]["namespace"] for r in self.of(calls, "hl.layer_rule") if r.get("blur")]
            for ns in ("qs-osd", "rofi", "notifications"):
                self.assertEqual(any(re.fullmatch(s, ns) for s in spaces), want["enabled"], ns)
            # The desk follows blur.desk too: Tinta's glass stands on the sharp sheet.
            self.assertEqual(any(re.fullmatch(s, "qs-desk") for s in spaces),
                             want["enabled"] and want.get("desk", True), f"{theme}: qs-desk")
            self.assertFalse(any(re.fullmatch(s, "qs-frame") for s in spaces), "qs-frame: screen-wide blur")
            # Bars float as plates over the sharp wallpaper: never blurred behind,
            # neither Quickshell's nor the Waybar fallback.
            for bar in ("qs-bar", "waybar"):
                self.assertFalse(any(re.fullmatch(s, bar) for s in spaces), f"{theme}: {bar} blur")

    def test_layer_motion(self):
        for theme, calls, _ in self.each():
            rules = self.of(calls, "hl.layer_rule")
            (qs,) = [r for r in rules if r.get("no_anim")]
            self.assertEqual(qs["match"]["namespace"], "^qs-")
            anims = {r["match"]["namespace"]: r["animation"] for r in rules if "animation" in r}
            # The launcher enters like the theme's layers do.
            rofi = THEMES[theme]["motion"]["hypr"]["leaves"]["layersIn"]["style"]
            self.assertEqual(anims, {"^waybar$": "slide top", "^rofi$": rofi,
                                     "^notifications$": "slide right"})

    def test_every_theme_curve_and_leaf_is_registered(self):
        for theme, calls, _ in self.each():
            motion = THEMES[theme]["motion"]["hypr"]
            curves = {a[0]: a[1] for p, a in calls if p == "hl.curve"}
            self.assertEqual(set(curves), set(motion["curves"]))
            anims = {a["leaf"]: a for a in self.of(calls, "hl.animation")}
            self.assertEqual(set(anims), set(motion["leaves"]))
            for leaf, spec in motion["leaves"].items():
                a = anims[leaf]
                kind = "spring" if motion["curves"][spec["curve"]]["type"] == "spring" else "bezier"
                self.assertEqual(a.get(kind), spec["curve"], leaf)
                self.assertNotIn({"spring": "bezier", "bezier": "spring"}[kind], a, leaf)
                self.assertEqual((a["speed"], a.get("style")), (spec["speed"], spec.get("style")), leaf)
                self.assertIs(a["enabled"], True)
            self.assertNotIn("loop", json.dumps(self.of(calls, "hl.animation")), "loop repaints every frame")

    def test_keyboard_is_english_first_with_ctrl_on_caps(self):
        for _, calls, _ in self.each():
            inp = self.config(calls, "input")
            self.assertEqual(inp["kb_layout"], "us")  # the shared default; the owner adds ",es" in hypr/local.lua
            self.assertEqual(inp["kb_options"], "ctrl:nocaps,grp:alt_shift_toggle")

    def test_session_target_starts_on_hyprland_start(self):
        for _, calls, _ in self.each():
            self.assertIn(("hl.on", ["hyprland.start"]), calls)
        text = (HYPR / "autostart.lua").read_text(encoding="utf-8")
        self.assertIn("systemctl --user start ryce-session.target", text)
        self.assertLess(text.index("reset-failed"), text.index("--user start ryce-session.target"))
        self.assertIn("HYPRLAND_INSTANCE_SIGNATURE", text)

    def test_only_import_environment_gates_the_session(self):
        calls, _ = self.runs["origen"]
        cmd = next(a[0] for p, a in calls if p == "hl.exec_cmd" and "ryce-session.target" in a[0])
        steps = [s.strip() for s in cmd.split(" && ")]
        self.assertTrue(steps[0].startswith("systemctl --user import-environment "))
        self.assertEqual(steps[-1], "systemctl --user start ryce-session.target")
        for s in steps[1:-1]:
            with self.subTest(step=s):
                self.assertRegex(s, r"^\{ .* \|\| true; \}$", "best-effort steps must not gate the start")
        self.assertTrue(any("reset-failed" in s for s in steps[1:-1]))


@unittest.skipUnless(LUA, "no lua interpreter on PATH")
class PaletteFallback(unittest.TestCase):
    """palette.lua is a link through the theme state; a broken link must not cost
    the session its config."""

    @staticmethod
    def gaps(calls):
        (cfg,) = [a[0] for p, a in calls if p == "hl.config" and "general" in a[0]]
        return cfg["general"]["gaps_in"], cfg["general"]["gaps_out"]

    def test_falls_back_to_origen_in_the_theme_state(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as home:
            hypr = Path(home) / ".local/state/ryce/theme/origen/hypr"
            hypr.mkdir(parents=True)
            shutil.copy(ROOT / "themes" / "origen" / "hypr" / "palette.lua", hypr)
            calls, error = run_config(copy_hypr(Path(d), theme=None), home=Path(home))
        self.assertIsNone(error)
        g = THEMES["origen"]["geometry"]
        self.assertEqual(self.gaps(calls), (g["gaps_in"], g["gaps_out"]))
        rules = [a[0] for p, a in calls if p == "hl.window_rule"]
        self.assertEqual(rules[-1]["border_color"], rgb("origen", "signal"), "rules.lua gets the same palette")

    def test_falls_back_to_a_builtin_table_when_nothing_is_there(self):
        with tempfile.TemporaryDirectory() as d:
            calls, error = run_config(copy_hypr(Path(d), theme=None))
        self.assertIsNone(error)
        self.assertEqual(len(self.gaps(calls)), 2)
        rules = [a[0] for p, a in calls if p == "hl.window_rule"]
        self.assertEqual(rules[-1]["match"], {"tag": "agentwait"})
        self.assertRegex(rules[-1]["border_color"], r"^rgb\([0-9a-f]{6}\)$")
        self.assertIn("hl.layer_rule", [p for p, _ in calls])
        signals = {t["colors"][k][1:] for t in THEMES.values() for k in ("signal", "signal_dim")}
        text = (HYPR / "look.lua").read_text(encoding="utf-8")
        self.assertEqual([s for s in signals if s in text], [], "the built-in table speaks no theme's signal")


@unittest.skipUnless(LUA, "no lua interpreter on PATH")
class WorkspaceStep(unittest.TestCase):
    """ryce.ws_step (generated into binds.lua) walks by number, empty ones
    included, from the focused screen's workspace, and stops at 1 and 10: no
    wrap. Past a screen's edge it goes on (5 -> 6, 6 -> 5): focusing a workspace
    is what takes the focus to the screen that keeps it, so ws_step needs no
    screens at all."""

    # Arg: the active workspace of the focused screen (a number, a name, or nil).
    RUN = r"""
local active = arg[1]
hl = {
    bind = function() end,
    get_active_workspace = function()
        if active == "nil" then return nil end
        if tonumber(active) then return { id = tonumber(active), name = active } end
        return { name = active }   -- a named workspace: no number
    end,
    dsp = setmetatable({ focus = function(t) return t.workspace end },
                       { __index = function() return function() end end }),
}
hl.dsp.window = setmetatable({}, { __index = function() return function() end end })
hl.dsp.workspace = setmetatable({}, { __index = function() return function() end end })
dofile(arg[0]:gsub("[^/]+$", "") .. "binds.lua")
print(ryce.ws_step(-1) or "-", ryce.ws_step(1) or "-")
"""
    def step(self, active: str) -> tuple[str, str]:
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(HYPR / "binds.lua", Path(d) / "binds.lua")
            (Path(d) / "run.lua").write_text(self.RUN, encoding="utf-8")
            proc = subprocess.run([LUA, str(Path(d) / "run.lua"), active],
                                  capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        prev, nxt = proc.stdout.split()
        return prev, nxt

    def test_steps(self):
        cases = {
            "1": ("-", "2"), "3": ("2", "4"), "10": ("9", "-"),
            # The screens' edges on the PC (1-5 | 6-10): crossed, not blocked.
            "5": ("4", "6"), "6": ("5", "7"),
            # SUPER+e (hypr/despejar.lua): step from N.
            "despejado-5": ("4", "6"), "despejado-10": ("9", "-"),
            # A stray number past 10 only ever comes back down to 10.
            "12": ("10", "-"),
            # Named, special (negative id) or nothing: no number to step from.
            "notas": ("-", "-"), "-98": ("-", "-"), "nil": ("-", "-"),
        }
        for active, want in cases.items():
            with self.subTest(active=active):
                self.assertEqual(self.step(active), want)

    def test_ctrl_arrows_use_it(self):
        text = (HYPR / "binds.lua").read_text(encoding="utf-8")
        self.assertIn('hl.bind("CTRL + Left", function() local s = ryce.ws_step(-1) if s then hl.dispatch(s) end end)', text)
        self.assertIn('hl.bind("CTRL + Right", function() local s = ryce.ws_step(1) if s then hl.dispatch(s) end end)', text)
        self.assertNotRegex(text, r'workspace = "e[+-]1"', "e-1/e+1 skip empty workspaces")
        self.assertNotRegex(text, r"hl\.dsp\.workspace\.move", "workspaces never change screen")


@unittest.skipUnless(LUA, "no lua interpreter on PATH")
class Isolation(unittest.TestCase):
    def test_a_missing_module_still_loads_the_rest_then_fails_loudly(self):
        with tempfile.TemporaryDirectory() as d:
            calls, error = run_config(copy_hypr(Path(d), skip={"look"}))
        self.assertIsNotNone(error)
        self.assertIn("module 'look' not found", error)
        paths = [p for p, _ in calls]
        self.assertIn("hl.window_rule", paths, "rules.lua must still load after look.lua is missing")
        self.assertIn("hl.on", paths, "autostart.lua must still load after look.lua is missing")

    def test_a_broken_module_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            copy_hypr(Path(d))
            (Path(d) / "env.lua").write_text("hl.env(\n", encoding="utf-8")
            calls, error = run_config(Path(d))
        self.assertIsNotNone(error)
        self.assertIn("env", error)
        self.assertIn("hl.bind", [p for p, _ in calls])

    def test_local_lua_is_optional_and_loads_last(self):
        with tempfile.TemporaryDirectory() as d:
            copy_hypr(Path(d))
            _, error = run_config(Path(d))
            self.assertIsNone(error, "a missing local.lua is not an error")
            (Path(d) / "local.lua").write_text('hl.monitor({ output = "HDMI-A-1" })\n', encoding="utf-8")
            calls, error = run_config(Path(d))
        self.assertIsNone(error)
        self.assertEqual(calls[-1], ("hl.monitor", [{"output": "HDMI-A-1"}]))


class Files(unittest.TestCase):
    def hypr_files(self):
        return [p for p in HYPR.rglob("*") if p.is_file() and "tests" not in p.parts]

    def test_every_module_is_loaded_by_hyprland_lua(self):
        text = (HYPR / "hyprland.lua").read_text(encoding="utf-8")
        code = re.sub(r"--[^\n]*", "", text)
        used = re.findall(r'^use\("(\w+)"', text, re.M)
        self.assertEqual(used, [*MODULES, "local"], "load order: binds first, local last")
        self.assertEqual(re.findall(r"\brequire\(", code), [],
                         "hyprland.lua loads modules only through pcall(require, ...)")
        on_disk = {p.stem for p in HYPR.glob("*.lua")} - {"hyprland", "palette", "local"}
        self.assertEqual(on_disk, set(MODULES), "a module on disk that hyprland.lua never loads is dead config")

    def test_no_hyprland_conf(self):
        self.assertEqual([p.name for p in self.hypr_files() if p.name == "hyprland.conf"], [])

    def test_every_hyprctl_dispatch_is_lua(self):
        for p in self.hypr_files():
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                for m in re.finditer(r"hyprctl\s+dispatch\s+(\S+)", line):
                    with self.subTest(file=p.name, line=n):
                        self.assertRegex(m.group(1), r"^'hl\.dsp\.")

    def test_no_colour_literals_in_lua(self):
        colour = re.compile(r"(?i)rgba?\(\s*[0-9a-f]{6}|#[0-9a-f]{6}\b|0x[0-9a-f]{6,8}\b")
        for p in HYPR.glob("*.lua"):
            if p.name == "palette.lua":
                continue
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                with self.subTest(file=p.name, line=n):
                    self.assertIsNone(colour.search(line), "use palette.lua (P.*) for colours")

    def test_signal_only_in_rules_lua(self):
        for p in HYPR.glob("*.lua"):
            with self.subTest(file=p.name):
                uses = re.findall(r"\bP\.(?:hex\.)?signal\w*|rgba\(\s*\"signal", p.read_text(encoding="utf-8"))
                self.assertEqual(uses, ["P.signal"] if p.name == "rules.lua" else [])

    def test_lock_screen_is_a_template_only(self):
        self.assertFalse((HYPR / "hyprlock.conf").exists(), "the lock screen is rendered per theme")
        self.assertTrue(LOCK_TEMPLATE.is_file())
        for theme in THEMES:
            with self.subTest(theme=theme):
                self.assertTrue((ROOT / "themes" / theme / "hypr" / "hyprlock.conf").is_file(),
                                "run python3 theme/render.py")

    def test_lock_colours_are_the_themes_colours(self):
        for theme, t in THEMES.items():
            allowed = {v[1:] for v in t["colors"].values()} | {v[1:] for v in t["hues"].values()}
            text = lock_conf(theme)
            for hexval in re.findall(r"(?i)rgba?\(([0-9a-f]{6})(?:[0-9a-f]{2})?\)", text):
                with self.subTest(theme=theme, colour=hexval):
                    self.assertIn(hexval.lower(), allowed)
            # Translucent fills (the field, veils, rings) are the theme's own colours too.
            for r, g, b in re.findall(r"rgba\((\d+), (\d+), (\d+), [\d.]+\)", text):
                with self.subTest(theme=theme, colour=(r, g, b)):
                    self.assertIn("%02x%02x%02x" % (int(r), int(g), int(b)), allowed)

    def test_signal_only_on_the_waiting_line_of_the_lock_screen(self):
        for theme, t in THEMES.items():
            with self.subTest(theme=theme):
                signals = {t["colors"][k][1:] for k in ("signal", "signal_dim", "signal_on_pill")}
                with_signal = [b for b in blocks(lock_conf(theme)) if any(s in b for s in signals)]
                self.assertEqual(len(with_signal), 1)
                self.assertIn("agentd/lock.txt", with_signal[0])

    def test_lock_background_is_the_themes_lock_art_never_the_screen(self):
        # The theme's own picture, softened: prettier, and it never shows what was open.
        for theme in THEMES:
            with self.subTest(theme=theme):
                text = lock_conf(theme)
                (bg,) = [b for b in blocks(text) if b.startswith("background {")]
                self.assertIn("path = ~/.local/state/ryce/theme/current/wallpaper/lock.jpg", bg)
                self.assertNotRegex(text, r"path\s*=\s*screenshot")
                if light(theme):
                    # A paper theme's lock art carves a window for the text (paper.py):
                    # sharp and undimmed, or the window and the ink around it go grey.
                    self.assertRegex(bg, r"blur_passes\s*=\s*0\b")
                    self.assertNotRegex(bg, r"brightness\s*=")
                else:
                    self.assertRegex(bg, r"blur_passes\s*=\s*[2-9]")
                    self.assertRegex(bg, r"brightness\s*=\s*0\.[3-7]")

    def test_lock_typography_follows_the_theme(self):
        families = lambda t: {t["fonts"]["ui"], t["fonts"]["display"], t["fonts"]["mono"],
                              "JetBrainsMono Nerd Font Propo"}       # icon glyphs
        for theme, t in THEMES.items():
            with self.subTest(theme=theme):
                labels = [b for b in blocks(lock_conf(theme)) if b.startswith("label {")]
                clock = next(b for b in labels if "date '+%H" in b or "$TIME" in b)
                self.assertIn(f"font_family = {t['fonts']['display']}\n", clock)
                px = int(re.search(r"font_size\s*=\s*(\d+)", clock).group(1)) * 4 / 3  # pt at 96 dpi
                self.assertGreaterEqual(px, max(t["fonts"]["display_min_px"], 48))
                for b in labels:
                    fam = re.search(r"font_family\s*=\s*(.+)", b).group(1).strip()
                    self.assertIn(fam, families(t), b[:80])

    def test_lock_mark_and_field(self):
        for theme, t in THEMES.items():
            with self.subTest(theme=theme):
                text = lock_conf(theme)
                images = [b for b in blocks(text) if b.startswith("image {")]
                (mark,) = [b for b in images if "peonza/logo.png" in b]
                self.assertIn("path = ~/.local/state/ryce/theme/current/peonza/logo.png", mark)
                # Shown big and with no box of its own: the «square» the user saw.
                self.assertRegex(mark, r"border_size\s*=\s*0")
                # Big on a dark lock; a small lockup in the corner of a paper cover.
                size = r"size\s*=\s*(4[0-8])\b" if light(theme) else r"size\s*=\s*(9[6-9]|1[0-9]{2})\b"
                self.assertRegex(mark, size)
                (field,) = [b for b in blocks(text) if b.startswith("input-field {")]
                self.assertRegex(field, r"rounding\s*=\s*\d+")
                self.assertIn("$LAYOUT", field)
                anims = re.search(r"^animations \{.*?^\}", text, re.M | re.S).group(0)
                self.assertRegex(anims, r"animation = fadeIn, 1,")
                self.assertRegex(anims, r"animation = fadeOut, 1,")

    def test_idle_locks_then_blanks_and_never_suspends(self):
        text = (HYPR / "hypridle.conf").read_text(encoding="utf-8")
        listeners = re.findall(r"^listener \{(.*?)^\}", text, re.S | re.M)
        timeouts = {int(re.search(r"timeout\s*=\s*(\d+)", b).group(1)): b for b in listeners}
        self.assertEqual(sorted(timeouts), [600, 900])
        self.assertIn("loginctl lock-session", timeouts[600])
        self.assertIn("'hl.dsp.dpms({ action = \"disable\" })'", timeouts[900])
        self.assertIn("'hl.dsp.dpms({ action = \"enable\" })'", timeouts[900])
        self.assertNotRegex(text, r"systemctl\s+(suspend|hibernate|hybrid-sleep)")
        self.assertRegex(text, r"lock_cmd\s*=\s*pidof hyprlock \|\| hyprlock")

    def test_clipboard_reads_the_tmpfs_history(self):
        text = (HYPR / "scripts" / "clipboard.sh").read_text(encoding="utf-8")
        self.assertIn('db="${XDG_RUNTIME_DIR:?', text)
        self.assertEqual(len(re.findall(r"cliphist -db-path \"\$db\" (?:list|decode)", text)), 2)
        self.assertNotRegex(text, r"cliphist (?:list|decode)", "every cliphist call names the tmpfs db")

    def test_lock_date_is_spanish(self):
        cmd = re.search(r"text = cmd\[update:\d+\] (date '\+%u.*)$", LOCK_TEMPLATE.read_text(encoding="utf-8"),
                        re.M).group(1)
        out = subprocess.run(["sh", "-c", cmd.replace("date '+%u %-d %-m'", "echo 1 9 11")],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        self.assertEqual(out, "lunes, 9 de noviembre")

    def test_scripts_are_executable(self):
        for p in (HYPR / "scripts").iterdir():
            with self.subTest(script=p.name):
                self.assertTrue(p.stat().st_mode & 0o111, f"{p.name} is not executable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
