"""Terminal-family app themes (kitty, rofi, mako, fish, starship, fastfetch, btop,
cava, nvim): every template renders for every theme into a file its app accepts,
text stays legible on the translucent terminal, the signal never appears, and
the behaviours other parts of the desktop rely on survive a re-theme.

    python3 -m unittest discover -s theme/tests -p 'test_terminal.py' -v

Needs kitty, rofi, fish, starship, fastfetch and nvim on PATH (all in
install/packages); none of them opens a window or touches ~/.config.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "theme"))
sys.path.insert(0, str(ROOT / "tools"))

import colormath as cm  # noqa: E402
import render  # noqa: E402
import tokens  # noqa: E402

THEMES = tokens.load_all()
OUTPUTS = render.render_all(THEMES)
MINE = ("kitty/", "rofi/", "mako/", "fish/", "fastfetch/", "btop/", "cava/", "nvim/", "starship.toml",
        "claude/", "yazi/")
# The prompt's cut of the peonza (theme/peonza/glyph.py), three cells wide: kitty
# draws it over the two spaces that follow it in its colour span.
PEONZA = "\U00100003" + "  "
SGR = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TIMEOUT = 60
# The mid blue the user is tired of: Claude Code's fixed `dark` theme (permission,
# ide, professionalBlue) and fzf's Dark256 prompt and highlight (110).
OLD_BLUES = {"#b1b9f9", "#4782c8", "#6a9bcc", "#87afd7"}
# SGR codes for ANSI blue, foreground and background, normal and bright.
BLUE_SGR = {"34", "44", "94", "104"}


def esc(hexcolour: str) -> str:
    return "\x1b[38;2;%d;%d;%dm" % tuple(int(hexcolour[i:i + 2], 16) for i in (1, 3, 5))


def fish_env(tid: str, *names: str) -> dict[str, str]:
    """What an interactive fish exports after reading the theme's colours."""
    script = f"source {render.THEMES_OUT / tid / 'fish/colors.fish'}; " + "; ".join(
        f"printf '%s\\x1f' \"${n}\"" for n in names)
    r = run("fish", "--no-config", "-c", script)
    assert r.returncode == 0, r.stderr
    return dict(zip(names, r.stdout.split("\x1f")))


def out(tid: str, rel: str) -> str:
    return OUTPUTS[render.THEMES_OUT / tid / rel]


def run(*cmd: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, **kw)


def kitty_opts(text: str) -> dict[str, str]:
    opts = {}
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.strip().partition(" ")
            opts.setdefault(key, value.strip())
    return opts


def worst_glass(tid: str, t: dict) -> str:
    """The brightest colour Hyprland's blur leaves behind the terminal, over every desktop
    picture of the theme, scaled by blur.brightness. The kawase blur is modelled as a
    Gaussian of sigma = size * 2^(passes-1) screen px: stage captures (Hyprland 0.57.2,
    1920x1080) fit 28-32 px for 7x3, 8-10 for 4x2 and 2 for 2x1, and a smaller sigma
    leaves brighter peaks, so the model errs strict. Measured on the 2560x1440 masters
    (the blur covers less of the picture there) at quarter scale."""
    import numpy as np
    from PIL import Image

    b, q = t["blur"], 4
    sigma = b["size"] * 2 ** (b["passes"] - 1) / q
    r = int(3 * sigma) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    best, colour = -1.0, "#000000"
    for d in ["", *(f"alt-{n}/" for n in range(1, len(t["wallpaper"]["alternates"]) + 1))]:
        with Image.open(ROOT / "themes" / tid / "wallpaper" / f"{d}2560x1440.jpg") as im:
            a = np.asarray(im.convert("RGB").resize((2560 // q, 1440 // q), Image.BOX), dtype=np.float64) / 255
        p = np.pad(a, ((r, r), (r, r), (0, 0)), mode="edge")
        h = sum(k[i] * p[:, i:i + a.shape[1]] for i in range(2 * r + 1))
        v = sum(k[i] * h[i:i + a.shape[0]] for i in range(2 * r + 1))
        lum = v @ np.array([0.2126, 0.7152, 0.0722])
        y, x = np.unravel_index(np.argmax(lum), lum.shape)
        if lum[y, x] > best:
            best, colour = lum[y, x], cm.to_hex(tuple(b["brightness"] * v[y, x]))
    return colour


def need(*tools: str):
    missing = [t for t in tools if shutil.which(t) is None]
    return unittest.skipIf(missing, f"not installed: {', '.join(missing)}")


class Rendered(unittest.TestCase):
    def test_every_template_of_the_slice_renders_per_theme(self):
        rels = [r for r in render.templates() if r.startswith(MINE)]
        self.assertGreaterEqual(len(rels), 9)
        for tid in THEMES:
            for rel in rels:
                self.assertIn(render.THEMES_OUT / tid / rel, OUTPUTS)

    def test_no_signal_colour(self):
        # tools/lint.py checks the committed files; this checks what render produces.
        signals = {t["colors"][k][1:].lower() for t in THEMES.values()
                   for k in ("signal", "signal_dim", "signal_on_pill")}
        for path, text in OUTPUTS.items():
            if path.relative_to(render.THEMES_OUT).as_posix().split("/", 1)[1].startswith(MINE):
                for h in signals:
                    self.assertNotIn(h, text.lower(), f"{path}: signal colour #{h}")


class Kitty(unittest.TestCase):
    def test_new_terminal_is_a_new_process(self):
        # agentd attributes AI sessions per kitty process: kitty_mod+n must start
        # another process, never a second OS window inside this one.
        for tid in THEMES:
            text = out(tid, "kitty/kitty.conf")
            self.assertRegex(text, r"(?m)^map kitty_mod\+n launch --type=background ")
            self.assertNotIn("new_os_window", re.sub(r"(?m)^\s*#.*$", "", text))

    def test_term_block_drives_cursor_selection_and_links(self):
        for tid, t in THEMES.items():
            o, term = kitty_opts(out(tid, "kitty/kitty.conf")), t["term"]
            self.assertEqual((o["cursor"], o["selection_background"], o["selection_foreground"], o["url_color"]),
                             (term["cursor"], term["selection_bg"], term["selection_fg"], term["url"]), tid)

    def test_peonza_and_mono_font(self):
        for tid, t in THEMES.items():
            o = kitty_opts(out(tid, "kitty/kitty.conf"))
            self.assertEqual(o["symbol_map"], "U+100000-U+100003 Ryce Peonza")
            self.assertEqual(o["narrow_symbols"], "U+100003 3")
            self.assertEqual(o["font_family"], t["fonts"]["mono"])

    def test_text_contrast_on_the_translucent_ground(self):
        # kitty paints bg1 at background_opacity over Hyprland's xray blur of the
        # wallpaper. The ground is the brightest pixel of the theme's worst picture
        # (alternates included) after that blur and its brightness: text must hold
        # there, and on the bare bg1. Every ANSI slot is text except a dark theme's
        # black, which is its ground.
        for tid, t in THEMES.items():
            o = kitty_opts(out(tid, "kitty/kitty.conf"))
            self.assertEqual(o["background"], t["colors"]["bg1"])
            alpha = float(o["background_opacity"])
            self.assertEqual(alpha, t["alpha"]["term"])
            grounds = [o["background"]]
            if alpha < 1:
                self.assertTrue(t["blur"]["enabled"], f"{tid}: a translucent terminal needs the blur")
                grounds.append(cm.over(o["background"], alpha, worst_glass(tid, t)))
            light = tokens.scheme(t) == "light"
            text = {"foreground": o["foreground"], "fg1": t["colors"]["fg1"]}
            text |= {f"color{i}": o[f"color{i}"] for i in range(16) if light or i != 0}
            for ground in grounds:
                text["faint foreground"] = cm.over(o["foreground"], float(o["dim_opacity"]), ground)
                for name, fg in text.items():
                    self.assertGreaterEqual(cm.contrast(fg, ground), t["contrast_floor"]["text"],
                                            f"{tid}: {name} {fg} on {ground}")
                # Comments, autosuggestions, descriptions: dim by design, UI floor.
                self.assertGreaterEqual(cm.contrast(t["colors"]["fg2"], ground), t["contrast_floor"]["ui"],
                                        f"{tid}: fg2 on {ground}")

    @need("kitty")
    def test_kitty_accepts_every_line(self):
        code = "import sys; from kitty.config import load_config; load_config(sys.argv[-1])"
        with tempfile.TemporaryDirectory() as d:
            for tid in THEMES:
                f = Path(d) / f"{tid}.conf"
                f.write_text(out(tid, "kitty/kitty.conf"), encoding="utf-8")
                r = run("kitty", "+runpy", code, str(f))
                self.assertEqual((r.returncode, r.stderr.strip()), (0, ""), f"{tid}: {r.stderr}")


class Launcher(unittest.TestCase):
    @need("rofi")
    def test_rofi_parses(self):
        for tid in THEMES:
            r = run("rofi", "-dump-theme", "-theme", str(render.THEMES_OUT / tid / "rofi/style.rasi"))
            self.assertEqual(r.returncode, 0, f"{tid}: {r.stderr}")
            self.assertNotIn("error", r.stderr.lower(), tid)
            # -dump-theme prints every url as "(null)" (rofi 2.0.0): check the kind only.
            self.assertIn("background-image: url", r.stdout)

    def test_clipboard_picker_keeps_its_widgets(self):
        # hypr/scripts/clipboard.sh runs `rofi -dmenu` on the same theme: it needs
        # the entry and the listview, and no mode-specific widget.
        for tid in THEMES:
            text = out(tid, "rofi/style.rasi")
            self.assertRegex(text, r"children:\s*\[ inputbar, message, listview \]")
            self.assertRegex(text, r"children:\s*\[ textbox-search, entry \]")


class Mako(unittest.TestCase):
    def test_sections_are_known_criteria(self):
        for tid in THEMES:
            for crit in re.findall(r"(?m)^\[urgency=(\w+)\]", out(tid, "mako/config")):
                self.assertIn(crit, {"low", "normal", "critical"}, f"{tid}: [urgency={crit}]")


@need("fish")
class Fish(unittest.TestCase):
    def test_colors_parse(self):
        for tid in THEMES:
            r = run("fish", "-n", str(render.THEMES_OUT / tid / "fish/colors.fish"))
            self.assertEqual(r.returncode, 0, f"{tid}: {r.stderr}")

    def test_open_shells_follow_a_switch(self):
        # conf.d applies the current theme at start and again on `ryce_theme`
        # changes (set -U by bin/ryce-theme; -g here so no universal is written).
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)
            for tid in THEMES:
                (state / tid).symlink_to(render.THEMES_OUT / tid)
            (state / "current").symlink_to("origen")
            # The exported variables follow too: a child started after the switch
            # (ls, fzf, git) sees the new theme's.
            show = "echo $fish_color_command; string match -r 'GIT_PAGER=.*' (env)"
            script = (f"source {ROOT / 'apps/fish/conf.d/ryce-theme.fish'}; {show}; "
                      f"ln -sfn ola {state}/current.tmp; mv -T {state}/current.tmp {state}/current; "
                      f"set -g ryce_theme ola; {show}")
            r = run("fish", "--no-config", "-i", "-c", script, env={**os.environ, "RYCE_THEME_STATE": d})
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = r.stdout.splitlines()
            self.assertEqual(lines[0::2], [THEMES["origen"]["ansi"][14][1:], THEMES["ola"]["ansi"][14][1:]])
            self.assertIn(THEMES["origen"]["term"]["diff_add"], lines[1])
            self.assertIn(THEMES["ola"]["term"]["diff_add"], lines[3])

    @need("starship")
    def test_a_run_command_collapses_to_one_line(self):
        # config.fish turns on fish's transient prompt: a command's frame is
        # redrawn as "<time> <peonza>  command" once it runs, so no $COLUMNS-wide
        # line stays in the scrollback for kitty to rewrap on a resize.
        t = THEMES["tinta"]
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "XDG_CONFIG_HOME": home, "XDG_DATA_HOME": home,
                   "STARSHIP_CONFIG": str(render.THEMES_OUT / "tinta" / "starship.toml"),
                   "STARSHIP_CACHE": home, "STARSHIP_LOG": "warn"}
            script = (f"source {ROOT / 'apps/fish/config.fish'}; echo $fish_transient_prompt; "
                      "starship_transient_prompt_func --status=1 --terminal-width=90")
            r = run("fish", "--no-config", "-i", "-c", script, env=env, cwd=home)
        self.assertEqual((r.returncode, r.stderr.strip()), (0, ""), r.stderr)
        flag, *lines = r.stdout.split("\n")
        self.assertEqual(flag, "1")
        self.assertEqual(lines[0], "", "the blank line between prompts")
        self.assertEqual(len(lines), 2, repr(r.stdout))
        self.assertRegex(SGR.sub("", lines[1]), r"^\[ \d\d:\d\d \] " + PEONZA)
        # Even after a failure: the collapsed line's peonza would otherwise carry the
        # previous command's status and read as this command's failure.
        self.assertNotIn(esc(t["colors"]["err"]) + PEONZA, lines[1])
        self.assertIn(esc(t["colors"]["fg0"]) + PEONZA, lines[1])

    def test_no_listing_paints_blue(self):
        # ls/lsd directories were bold ANSI blue; grep and fzf had their own blues.
        for tid in THEMES:
            env = fish_env(tid, "LS_COLORS", "GREP_COLORS", "FZF_DEFAULT_OPTS")
            entries = dict(e.split("=", 1) for e in env["LS_COLORS"].split(":") if e)
            self.assertIn("di", entries, tid)
            for key, sgr in [*entries.items(), *(e.split("=", 1) for e in env["GREP_COLORS"].split(":") if "=" in e)]:
                self.assertFalse(set(sgr.split(";")) & BLUE_SGR, f"{tid}: {key}={sgr} is blue")
            # Base 16 makes every slot fzf is not told about a palette colour, never Dark256's.
            self.assertRegex(env["FZF_DEFAULT_OPTS"], r"--color=16,")
            self.assertNotRegex(env["FZF_DEFAULT_OPTS"], r"[:,](4|12|110)(,|'|$)")


@need("starship")
class Starship(unittest.TestCase):
    def prompt(self, tid: str, *args: str) -> str:
        env = {**os.environ, "STARSHIP_CONFIG": str(render.THEMES_OUT / tid / "starship.toml"),
               "STARSHIP_LOG": "warn", "STARSHIP_CACHE": tempfile.gettempdir(), "STARSHIP_SHELL": "fish"}
        with tempfile.TemporaryDirectory() as d:
            r = run("starship", "prompt", *args, env=env, cwd=d)
        self.assertEqual((r.returncode, r.stderr.strip()), (0, ""), f"{tid}: {r.stderr}")
        return r.stdout

    def test_config_loads_without_warnings(self):
        for tid in THEMES:
            env = {**os.environ, "STARSHIP_CONFIG": str(render.THEMES_OUT / tid / "starship.toml"),
                   "STARSHIP_LOG": "warn", "STARSHIP_CACHE": tempfile.gettempdir()}
            r = run("starship", "print-config", env=env)
            self.assertEqual((r.returncode, r.stderr.strip()), (0, ""), f"{tid}: {r.stderr}")

    def test_every_prompt_colour_reads_on_the_terminal(self):
        # The peonza, the path, the clock, the hairline: letters the eye reads, so
        # the text floor on bg0, bg1 and the glass over the worst wallpaper. A chip
        # (a colour used as bg:) is a mark there (3:1), with `ink` read on it.
        for tid, t in THEMES.items():
            text = out(tid, "starship.toml")
            block = re.search(r"^\[palettes\.ryce\]\n(.*?)(?:^\[|\Z)", text, re.S | re.M)
            colours = dict(re.findall(r'^(\w+) = "(#[0-9a-f]{6})"', block.group(1), re.M))
            chips = set(re.findall(r"bg:(\w+)", text))
            self.assertIn("peonza", colours, tid)
            bg1, alpha = t["colors"]["bg1"], t["alpha"]["term"]
            grounds = [t["colors"]["bg0"], bg1] + ([cm.over(bg1, alpha, worst_glass(tid, t))] if alpha < 1 else [])
            for name, fg in colours.items():
                if name == "ink":
                    continue
                for ground in grounds:
                    self.assertGreaterEqual(cm.contrast(fg, ground), 3.0 if name in chips else 4.5,
                                            f"{tid}: {name} {fg} on {ground}")
                if name in chips:
                    self.assertGreaterEqual(cm.contrast(colours["ink"], fg), 4.5, f"{tid}: ink on {name}")

    def test_the_prompt_character_is_the_peonza_in_its_state_colour(self):
        # The second line is the top itself, upright in every state; the state is
        # its colour: the theme's own after a success, err after a failure.
        for tid, t in THEMES.items():
            ok = self.prompt(tid, "--status=0").split("\n")[-1]
            self.assertIn(PEONZA, ok, f"{tid}: {ok!r}")
            bad = self.prompt(tid, "--status=1").split("\n")[-1]
            self.assertIn(esc(t["colors"]["err"]) + PEONZA, bad, f"{tid}: {bad!r}")
            text = out(tid, "starship.toml")
            self.assertEqual(text.count(PEONZA), 3, f"{tid}: success, error and vi's normal mode")
            self.assertNotRegex(text, "[\U00100004\U00100005]", f"{tid}: a retired pose")

    def test_every_theme_is_a_ruled_frame(self):
        # Line 1: a corner, the readings, a rule out to the hour, exactly as wide as
        # the terminal; line 2: the matching corner, then the peonza. Nothing East
        # Asian wide on line 1: a width starship and kitty disagree on wraps the rule
        # into a row fish does not know about, and the frame overprints the command.
        for tid in THEMES:
            first, second = (SGR.sub("", line) for line in
                             self.prompt(tid, "--status=0", "--terminal-width=90").split("\n")[-2:])
            with self.subTest(theme=tid):
                self.assertRegex(first, r"^[╭┌]─.*─{8,}.*\d\d:\d\d\W*$")
                self.assertEqual(len(first), 90, repr(first))
                self.assertFalse([c for c in first if unicodedata.east_asian_width(c) in "WF"], repr(first))
                self.assertRegex(second, "^[╰└]─ " + PEONZA)
                self.assertEqual({"╭": "╰", "┌": "└"}[first[0]], second[0])

    def test_a_failure_shows_its_exit_code(self):
        for tid in THEMES:
            first = self.prompt(tid, "--status=127").split("\n")
            self.assertIn("127", "\n".join(first[:-1]), tid)
            self.assertNotIn("127", "\n".join(self.prompt(tid, "--status=0").split("\n")[:-1]), tid)


class ClaudeCode(unittest.TestCase):
    # Copied to ~/.claude/themes/ryce.json by bin/ryce-theme; selected as custom:ryce.
    TOKENS = {"claude", "permission", "suggestion", "remember", "ide", "professionalBlue",
              "diffAdded", "diffRemoved", "diffAddedWord", "diffRemovedWord", "selectionBg"}

    def test_theme_is_valid_and_never_the_old_blue(self):
        for tid, t in THEMES.items():
            doc = json.loads(out(tid, "claude/ryce.json"))
            # The 16 colours on the matching ground: light-ansi under Papel's paper.
            self.assertEqual(doc["base"], f"{tokens.scheme(t)}-ansi", tid)
            over = doc["overrides"]
            self.assertLessEqual(self.TOKENS, set(over), tid)
            for key, value in over.items():
                self.assertRegex(value, r"^#[0-9a-f]{6}$", f"{tid}: {key}")
                self.assertNotIn(value, OLD_BLUES, f"{tid}: {key}")
            self.assertEqual(over["claude"], t["term"]["claude"])
            self.assertEqual((over["diffAdded"], over["diffRemoved"]), (t["term"]["diff_add"], t["term"]["diff_del"]))
            self.assertEqual(over["selectionBg"], t["term"]["selection_bg"])


class Yazi(unittest.TestCase):
    def test_theme_parses_and_never_names_blue(self):
        import tomllib
        for tid in THEMES:
            text = out(tid, "yazi/theme.toml")
            doc = tomllib.loads(text)
            self.assertNotRegex(text, r'(?i)"(light)?blue"', tid)
            dirs = [r for r in doc["filetype"]["rules"] if r.get("url") == "*/" and "is" not in r]
            self.assertEqual(len(dirs), 1, f"{tid}: one rule for directories")


class Fastfetch(unittest.TestCase):
    def config(self, tid: str) -> dict:
        return json.loads(re.sub(r"(?m)^\s*//.*$", "", out(tid, "fastfetch/config.jsonc")))

    @need("fastfetch")
    def test_config_runs(self):
        for tid in THEMES:
            r = run("fastfetch", "-c", str(render.THEMES_OUT / tid / "fastfetch/config.jsonc"),
                    "--pipe", "--logo-type", "small", "--logo", "")
            self.assertEqual((r.returncode, r.stderr.strip()), (0, ""), f"{tid}: {r.stderr}")
            self.assertIn("sistema", r.stdout)


class Monitors(unittest.TestCase):
    def test_btop_values_are_colours(self):
        for tid in THEMES:
            for key, value in re.findall(r'(?m)^theme\[(\w+)\]="([^"]*)"$', out(tid, "btop/themes/ryce.theme")):
                self.assertRegex(value, r"^(#[0-9a-f]{6})?$", f"{tid}: theme[{key}]")

    def test_cava_colours_are_quoted(self):
        # iniparser reads an unquoted `#` as the start of a comment.
        for tid in THEMES:
            for line in out(tid, "cava/config").splitlines():
                if "#" in line and not line.startswith("#"):
                    self.assertRegex(line, r"= '#[0-9a-f]{6}'$", f"{tid}: {line}")


@need("nvim")
class Neovim(unittest.TestCase):
    def nvim(self, lua: str, state: str | None = None) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "RYCE_THEME_STATE"}
        if state:
            env["RYCE_THEME_STATE"] = state
        with tempfile.TemporaryDirectory() as home:
            env["XDG_STATE_HOME"] = home   # nvim's log, never the user's
            script = Path(home, "t.lua")
            script.write_text(lua, encoding="utf-8")
            return run("nvim", "--headless", "--clean", "--cmd", f"set rtp^={ROOT / 'apps/nvim'}",
                       "-c", f"luafile {script}", "-c", "qa!", env=env, cwd=home)

    def normal_fg(self, tid: str) -> str:
        # Slot 7 is the text on a dark ground; on paper it is a mid grey and prose takes the ink.
        t = THEMES[tid]
        return t["colors"]["fg0"] if tokens.scheme(t) == "light" else t["ansi"][7]

    def test_generated_scheme_loads(self):
        for tid, t in THEMES.items():
            r = self.nvim(
                f"dofile([[{render.THEMES_OUT / tid / 'nvim/colors.lua'}]])\n"
                "local n = vim.api.nvim_get_hl(0, { name = 'Normal' })\n"
                "local term = {}\n"
                "for i = 0, 15 do term[#term + 1] = vim.g['terminal_color_' .. i] end\n"
                "io.stdout:write(vim.g.colors_name, ' ', string.format('#%06x', n.fg), ' ', table.concat(term, ','))\n")
            self.assertEqual(r.stderr.strip(), "", f"{tid}: {r.stderr}")
            self.assertEqual(r.stdout.split(), ["ryce", self.normal_fg(tid), ",".join(t["ansi"])])

    def test_colorscheme_follows_the_state_and_switches(self):
        with tempfile.TemporaryDirectory() as d:
            for tid in THEMES:
                Path(d, tid).symlink_to(render.THEMES_OUT / tid)
            Path(d, "current").symlink_to("origen")
            want = self.normal_fg("grafito")
            r = self.nvim(
                "vim.cmd.colorscheme('ryce')\n"
                "local function fg() return string.format('#%06x', vim.api.nvim_get_hl(0, { name = 'Normal' }).fg) end\n"
                "local before = fg()\n"
                f"vim.uv.fs_symlink('grafito', [[{d}/current.tmp]])\n"
                f"vim.uv.fs_rename([[{d}/current.tmp]], [[{d}/current]])\n"
                f"vim.wait(3000, function() return fg() == '{want}' end, 20)\n"
                "io.stdout:write(before, ' ', fg())\n", state=d)
            self.assertEqual(r.stderr.strip(), "", r.stderr)
            self.assertEqual(r.stdout.split(), [self.normal_fg("origen"), want])

    def test_missing_state_falls_back_to_habamax(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.nvim("vim.cmd.colorscheme('ryce')\nio.stdout:write(vim.g.colors_name)\n", state=d)
        self.assertEqual(r.stdout.strip(), "ryce")
        self.assertIn("using habamax", r.stderr)


if __name__ == "__main__":
    unittest.main()
