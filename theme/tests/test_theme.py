"""Theme engine invariants: the three contracts validate and share one shape, the
renderer is fresh, refuses the signal outside its allowlist, never types a glyph,
and the vendored fonts match their README hashes.

    python3 -m unittest discover -s theme/tests -p 'test_theme.py' -v

Wallpapers: test_wallpaper.py. Peonza assets: test_peonza.py. Terminal-family
apps: test_terminal.py. GUI-family apps: test_gui.py.
"""

from __future__ import annotations

import copy
import hashlib
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "theme"))
sys.path.insert(0, str(ROOT / "tools"))

import render  # noqa: E402
from colormath import contrast  # noqa: E402
import tokens  # noqa: E402

THEMES = tokens.load_all()
ORIGEN = THEMES["origen"]
MD_FIRST, MD_LAST = 0xF0001, 0xF1AF0   # nf-md-* in Nerd Fonts 3.x (glyphnames.json 3.5.1)
PEONZA = set(range(0x100000, 0x100004))     # bar cuts and the prompt cut (theme/peonza/glyph.py)
PUA = re.compile("[-\U000f0000-\U000ffffd\U00100000-\U0010fffd]")


def text_files(*roots: Path):
    for root in roots:
        for p in sorted(root.rglob("*")):
            if "__pycache__" in p.parts:
                continue
            if p.is_file() and p.suffix not in {".png", ".otf", ".ttf", ".woff", ".woff2", ".vsix", ".pf2"}:
                yield p


class Contracts(unittest.TestCase):
    def test_five_themes_validate(self):
        self.assertEqual(list(THEMES), ["origen", "grafito", "ola", "tinta", "papel"])

    def test_scheme_follows_the_ground(self):
        self.assertEqual({tid: tokens.scheme(t) for tid, t in THEMES.items()},
                         {"origen": "dark", "grafito": "dark", "ola": "dark", "tinta": "dark", "papel": "dark"})
        # Papel moved from cream paper to a green reading-room desk (2026-11-19); the light
        # path stays for a theme on paper, and bg0 alone decides it.
        paper = copy.deepcopy(THEMES["papel"])
        paper["colors"]["bg0"] = "#f7f3eb"
        self.assertEqual(tokens.scheme(paper), "light")
        self.assertEqual(render.render_text("{{theme.scheme}}", paper, "t.conf"), "light")
        self.assertEqual(render.render_text("{{theme.scheme}}", THEMES["papel"], "t.conf"), "dark")

    def test_tokens_check_is_clean(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "tokens.py"), "--check"],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_low_contrast_text_is_refused(self):
        t = copy.deepcopy(ORIGEN)
        t["colors"]["fg1"] = "#2a2622"
        with self.assertRaises(tokens.ThemeError):
            tokens.validate(t)

    def test_every_text_role_reads_on_both_grounds(self):
        # WCAG AA, typed here and not read from the contract, so a theme cannot lower
        # its own floor: letters 4.5:1 on bg0 and bg1, the signal (a mark) 3:1.
        for tid, t in THEMES.items():
            c = t["colors"]
            text = {k: c[k] for k in tokens.TEXT_ROLES} | {f"term.{k}": t["term"][k] for k in tokens.TEXT_TERM}
            text |= {f"hues.{k}": v for k, v in t["hues"].items()}
            for bg in ("bg0", "bg1"):
                for name, fg in text.items():
                    self.assertGreaterEqual(contrast(fg, c[bg]), 4.5, f"{tid}: {name} {fg} on {bg} {c[bg]}")
                self.assertGreaterEqual(contrast(c["signal"], c[bg]), 3.0, f"{tid}: signal on {bg}")

    def test_dim_text_is_refused(self):
        for key in ("fg2", "claude"):
            t = copy.deepcopy(THEMES["papel"])
            t["colors"][key] = "#4d5e55"     # a baize grey: 2.0:1 on Papel's green desk
            with self.subTest(key=key), self.assertRaises(tokens.ThemeError):
                tokens.validate(t)

    def test_signal_near_a_grey_is_refused(self):
        t = copy.deepcopy(ORIGEN)
        t["colors"]["signal"] = t["colors"]["fg1"]
        with self.assertRaises(tokens.ThemeError):
            tokens.validate(t)

    def test_animated_wallpaper_ships_off(self):
        t = copy.deepcopy(ORIGEN)
        t["wallpaper"]["animated"] = True
        with self.assertRaises(tokens.ThemeError):
            tokens.validate(t)

    def test_themes_differ_in_more_than_colour(self):
        # The direction: each theme is a stance (type, geometry, motion), not a hue.
        for key in (("fonts", "ui"), ("geometry", "frame_radius"), ("motion", "preset"), ("wallpaper", "source"),
                    ("colors", "signal"), ("colors", "bg0")):
            values = {THEMES[t][key[0]][key[1]] for t in THEMES}
            self.assertEqual(len(values), len(THEMES), f"{key}: themes share {values}")


class Render(unittest.TestCase):
    def test_check_is_clean(self):
        r = subprocess.run([sys.executable, str(ROOT / "theme" / "render.py"), "--check"],
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_output_has_header(self):
        outputs = render.render_all(THEMES)
        self.assertTrue(outputs, "no templates found")
        for path, text in outputs.items():
            if path.suffix == ".json":
                continue          # JSON has no comments: render.py writes these bare
            self.assertIn(render.HEADER_MARK, "\n".join(text.splitlines()[:2]), f"{path}: header missing")

    def test_one_output_per_theme_per_template(self):
        outputs = render.render_all(THEMES)
        self.assertEqual(len(outputs), len(render.templates()) * len(THEMES))

    def test_refuses_signal_tokens(self):
        for token in ("signal", "signal_dim", "signal_on_pill", "signal.hex", "signal@0.5"):
            with self.assertRaises(render.RenderError, msg=token):
                render.render_text("x {{%s}} y" % token, ORIGEN, "kitty/kitty.conf")

    def test_signal_allowed_on_the_lock_screen(self):
        out = render.render_text("{{signal}}", ORIGEN, "hypr/hyprlock.conf")
        self.assertEqual(out, ORIGEN["colors"]["signal"])

    def test_unknown_token_names_file_and_line(self):
        with self.assertRaises(render.RenderError) as cm:
            render.render_text("ok\n{{nope}}\n", ORIGEN, "kitty/kitty.conf")
        self.assertIn("kitty/kitty.conf:2", str(cm.exception))

    def test_tokens(self):
        t = render.render_text(
            "{{bg1}} {{bg1.hex}} {{bg1.rgb}} {{bg1@0.5}} {{bg1@alpha.term}} {{ansi.4}} {{ansi.4.hex}} "
            "{{alpha.term}} {{font.ui}} {{geometry.rounding}} {{theme.name}} {{desktop.icon_theme}} "
            "{{blur.enabled}} {{glyph.magnify}} {{glyph.peonza}} {{white}}", ORIGEN, "t.conf")
        self.assertEqual(t, "#282828 282828 40, 40, 40 #28282880 #282828c7 #7daea3 7daea3 0.78 Martian Mono 3 "
                            "Origen ryce-origen true \U000f0349 \U00100000 #ebdbb2")

    def test_theme_extras_and_any_glyph(self):
        t = render.render_text("{{hue.cpu}} {{hue.cpu.hex}} {{term.diff_add}} {{hue.mem@0.5}} {{glyph.uF0425}}",
                               ORIGEN, "t.conf")
        self.assertEqual(t, "#fabd2f fabd2f #2f3518 #8ec07c80 \U000f0425")

    def test_a_theme_template_replaces_the_shared_one(self):
        own = {tid: render.own_templates(tid) for tid in THEMES}
        outputs = render.render_all(THEMES)
        for tid, rels in own.items():
            for rel in rels:
                src = (render.TEMPLATES / f"@{tid}" / rel).read_text(encoding="utf-8")
                if "{{" not in src:
                    self.assertIn(src.strip()[:40], outputs[render.THEMES_OUT / tid / rel])

    def test_glyphs_are_material_design_or_peonza(self):
        for name, cp in render.GLYPHS.items():
            self.assertTrue(MD_FIRST <= cp <= MD_LAST or cp in PEONZA, f"glyph {name} U+{cp:X}")


class Glyphs(unittest.TestCase):
    def test_templates_never_type_a_glyph(self):
        for p in text_files(ROOT / "theme" / "templates"):
            m = PUA.search(p.read_text(encoding="utf-8"))
            self.assertIsNone(m, f"{p.relative_to(ROOT)}: typed glyph; use {{{{glyph.name}}}}")

    def test_apps_use_only_known_glyphs(self):
        for p in text_files(ROOT / "apps"):
            for ch in PUA.findall(p.read_text(encoding="utf-8")):
                self.assertTrue(MD_FIRST <= ord(ch) <= MD_LAST or ord(ch) in PEONZA,
                                f"{p.relative_to(ROOT)}: U+{ord(ch):X} is not an nf-md glyph or the peonza")


class Vendored(unittest.TestCase):
    def test_font_hashes_match_readme(self):
        readme = (ROOT / "assets" / "fonts" / "README.md").read_text(encoding="utf-8")
        rows = dict(re.findall(r"\| `([^`]+)` \| `([0-9a-f]{64})` \|", readme))
        on_disk = {p.name for p in (ROOT / "assets" / "fonts").iterdir()
                   if p.is_file() and p.suffix in {".otf", ".ttf"}}
        self.assertEqual(set(rows), on_disk, "every font file has a README row and vice versa")
        for name, digest in rows.items():
            data = (ROOT / "assets" / "fonts" / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest, f"{name} changed; update README")


if __name__ == "__main__":
    unittest.main()
