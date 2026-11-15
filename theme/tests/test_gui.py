"""GUI-family apps: GTK3/GTK4 sheets, qt6ct, the folder icon themes, the VS Code VSIX
and the settings.json editor the switcher uses.

    python3 -m unittest discover -s theme/tests -p 'test_gui.py' -v

The GTK3 sheet is parsed by GTK3 itself (waybar/tests/gtk3_css_gate.py): one unknown
property makes GTK drop the whole user stylesheet, and Thunar would silently fall
back to plain adw-gtk3.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "theme"))
sys.path.insert(0, str(ROOT / "theme" / "vscode"))
sys.path.insert(0, str(ROOT / "tools"))

import build  # noqa: E402
import icons  # noqa: E402
import settings_edit as se  # noqa: E402
import tokens  # noqa: E402
from colormath import contrast  # noqa: E402

THEMES = tokens.load_all()
GATE = ROOT / "waybar" / "tests" / "gtk3_css_gate.py"
PAPIRUS_BLUES = re.compile(r"#5294e2|#4877b1", re.I)


def rendered(tid: str, rel: str) -> Path:
    return ROOT / "themes" / tid / rel


class GtkSheets(unittest.TestCase):
    def test_gtk3_sheet_parses_in_gtk3(self):
        for tid in THEMES:
            r = subprocess.run([sys.executable, str(GATE), str(rendered(tid, "gtk-3.0/gtk.css"))],
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 2:
                self.skipTest(r.stderr.strip() or r.stdout.strip())
            self.assertEqual(r.returncode, 0, f"{tid}: {r.stdout}{r.stderr}")

    def test_gate_catches_an_unknown_property(self):
        # The gate is only worth something if GTK3 reports what would void the sheet.
        with tempfile.NamedTemporaryFile("w", suffix=".css", delete=False) as f:
            f.write(".thunar { corner-shape: squircle; }\n")
        try:
            r = subprocess.run([sys.executable, str(GATE), f.name], capture_output=True, text=True, timeout=60)
        finally:
            os.unlink(f.name)
        if r.returncode == 2:
            self.skipTest(r.stderr.strip())
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_no_8_digit_hex_in_gtk(self):
        # GTK3 has no #rrggbbaa and GTK4 reads it differently: translucency is rgba().
        for tid in THEMES:
            for rel in ("gtk-3.0/gtk.css", "gtk-4.0/gtk.css"):
                text = rendered(tid, rel).read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"#[0-9a-f]{8}\b", text, re.I), f"{tid}/{rel}")

    def test_thunar_hooks_are_styled(self):
        # Style classes Thunar 4.20 really sets (thunar-window.c, thunar-location-button.c,
        # thunar-standard-view.c); a rename upstream would leave these rules dead.
        css = rendered("origen", "gtk-3.0/gtk.css").read_text(encoding="utf-8")
        for hook in (".thunar", ".location-button", ".standard-view", ".sidebar", "statusbar",
                     ".split-view-inactive-pane", "filechooser placessidebar", ".rubberband"):
            self.assertIn(hook, css)

    def test_theme_geometry_reaches_the_sheet(self):
        for tid, t in THEMES.items():
            css = rendered(tid, "gtk-3.0/gtk.css").read_text(encoding="utf-8")
            self.assertIn(f"border-radius: {t['geometry']['rounding']}px", css, tid)
            self.assertIn(t["fonts"]["mono"], css, tid)

    def test_selection_text_is_readable(self):
        for tid, t in THEMES.items():
            c = t["colors"]
            self.assertGreaterEqual(contrast(c["fg0"], c["bg3"]), 4.5, tid)
            self.assertGreaterEqual(contrast(c["ink_on_pill"], c["pill"]), 4.5, tid)


class Qt(unittest.TestCase):
    def test_qt6ct_scheme_has_22_roles(self):
        for tid in THEMES:
            text = rendered(tid, "qt6ct/colors/ryce.conf").read_text(encoding="utf-8")
            for key in ("active_colors", "inactive_colors", "disabled_colors"):
                m = re.search(rf"^{key}=(.*)$", text, re.M)
                self.assertIsNotNone(m, f"{tid}: {key}")
                roles = [r.strip() for r in m.group(1).split(",")]
                self.assertEqual(len(roles), 22, f"{tid}: {key}")
                self.assertTrue(all(re.fullmatch(r"#[0-9a-f]{6}", r) for r in roles), roles)

    def test_qt6ct_conf_points_at_the_linked_scheme(self):
        text = (ROOT / "apps" / "qt6ct" / "qt6ct.conf").read_text(encoding="utf-8")
        self.assertIn("color_scheme_path=~/.config/qt6ct/colors/ryce.conf", text)
        self.assertIn("custom_palette=true", text)


def fake_papirus(root: Path) -> Path:
    """A three-directory Papirus-Dark: 16x16 (one blue file), 48x48 with aliases, 48x48@2x link."""
    src = root / "Papirus-Dark"
    (src / "16x16" / "places").mkdir(parents=True)
    (src / "48x48" / "places").mkdir(parents=True)
    os.symlink("48x48", src / "48x48@2x")
    (src / "index.theme").write_text(
        "[Icon Theme]\nName=Papirus-Dark\nInherits=hicolor\n"
        "Directories=16x16/places,16x16/apps,48x48/places\nScaledDirectories=48x48@2x/places\n\n"
        "[16x16/places]\nContext=Places\nSize=16\nType=Fixed\n\n"
        "[16x16/apps]\nContext=Applications\nSize=16\nType=Fixed\n\n"
        "[48x48/places]\nContext=Places\nSize=48\nType=Fixed\n\n"
        "[48x48@2x/places]\nContext=Places\nSize=48\nScale=2\nType=Fixed\n", encoding="utf-8")
    svg = '<svg><path style="fill:#4877B1"/><rect style="fill:#e4e4e4"/><rect style="fill:#5294e2"/>' \
          '<path style="fill:#1d344f"/><path style="fill:#ffffff"/></svg>\n'
    (src / "16x16" / "places" / "folder-blue.svg").write_text(svg)
    (src / "16x16" / "places" / "folder.svg").write_text('<svg><path class="ColorScheme-Text"/></svg>')
    p48 = src / "48x48" / "places"
    for n in ("folder-blue.svg", "folder-blue-documents.svg", "folder-bluegrey.svg", "folder-red.svg"):
        (p48 / n).write_text(svg)
    os.symlink("folder-blue.svg", p48 / "folder.svg")
    os.symlink("folder-blue-documents.svg", p48 / "folder-documents.svg")
    os.symlink("folder-documents.svg", p48 / "folder_man.svg")      # a chain
    os.symlink("folder-bluegrey.svg", p48 / "folder-grey-ish.svg")  # not ours
    return src


class Icons(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = fake_papirus(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_ships_only_the_blue_folders_recoloured(self):
        t = THEMES["origen"]
        p = icons.plan(t, self.src)
        self.assertEqual(p["48x48/places/folder.svg"], ("link", b"folder-blue.svg"))
        self.assertEqual(p["48x48/places/folder_man.svg"], ("link", b"folder-blue-documents.svg"))
        self.assertEqual(p["48x48@2x"], ("link", b"48x48"))
        self.assertIn("16x16/places/folder-blue.svg", p)
        for absent in ("16x16/places/folder.svg", "48x48/places/folder-bluegrey.svg",
                       "48x48/places/folder-grey-ish.svg", "48x48/places/folder-red.svg"):
            self.assertNotIn(absent, p)
        svg = p["48x48/places/folder-blue.svg"][1].decode()
        self.assertIsNone(PAPIRUS_BLUES.search(svg))
        self.assertIn(t["desktop"]["folder"], svg)
        self.assertIn(t["desktop"]["folder_dark"], svg)
        index = p["index.theme"][1].decode()
        self.assertIn("Inherits=Papirus-Dark", index)
        self.assertIn("Directories=16x16/places,48x48/places\n", index)
        self.assertIn("ScaledDirectories=48x48@2x/places\n", index)
        self.assertIn("[48x48@2x/places]\nContext=Places\nSize=48\nScale=2\nType=Fixed", index)
        self.assertNotIn("16x16/apps", index)

    def test_three_themes_differ_and_build_is_deterministic(self):
        plans = {tid: icons.plan(t, self.src) for tid, t in THEMES.items()}
        self.assertEqual(len({icons.digest(p) for p in plans.values()}), len(THEMES))
        self.assertEqual(icons.digest(plans["ola"]), icons.digest(icons.plan(THEMES["ola"], self.src)))

    def test_install_swaps_by_rename_and_skips_an_identical_build(self):
        dest = self.root / "icons"
        p = icons.plan(THEMES["grafito"], self.src)
        self.assertTrue(icons.install("grafito", p, dest))
        self.assertEqual(icons.verify("grafito", p, dest, self.src), [])
        inode = (dest / "ryce-grafito").stat().st_ino
        self.assertFalse(icons.install("grafito", p, dest))
        self.assertEqual((dest / "ryce-grafito").stat().st_ino, inode)
        p2 = icons.plan(THEMES["ola"], self.src)          # a changed build
        self.assertTrue(icons.install("grafito", p2, dest))
        self.assertNotEqual((dest / "ryce-grafito").stat().st_ino, inode)
        self.assertEqual(sorted(x.name for x in dest.iterdir()), ["ryce-grafito"])

    def test_check_cli_on_the_fake(self):
        r = subprocess.run([sys.executable, str(ROOT / "theme" / "icons.py"), "--check",
                            "--src", str(self.src), "--dest", str(self.root / "out")],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("icons: ok", r.stdout)

    def test_missing_papirus_is_a_clear_error(self):
        r = subprocess.run([sys.executable, str(ROOT / "theme" / "icons.py"), "--check",
                            "--src", str(self.root / "nope")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertIn("papirus-icon-theme", r.stderr)


class Vsix(unittest.TestCase):
    def setUp(self):
        self.data = build.vsix(THEMES)

    def test_check_is_clean_and_bytes_are_deterministic(self):
        self.assertEqual(self.data, build.vsix(tokens.load_all()))
        r = subprocess.run([sys.executable, str(ROOT / "theme" / "vscode" / "build.py"), "--check"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_package_contributes_every_theme_in_its_polarity(self):
        import io
        z = zipfile.ZipFile(io.BytesIO(self.data))
        self.assertIsNone(z.testzip())
        pkg = json.loads(z.read("extension/package.json"))
        self.assertEqual((pkg["publisher"], pkg["name"]), ("ryce", "ryce-themes"))
        labels = [t["label"] for t in pkg["contributes"]["themes"]]
        self.assertEqual(labels, ["Ryce Origen", "Ryce Grafito", "Ryce Ola", "Ryce Tinta", "Ryce Papel"])
        for entry, t in zip(pkg["contributes"]["themes"], THEMES.values()):
            # Papel is paper: VS Code's light base under it, every other theme on the dark one.
            self.assertEqual(entry["uiTheme"], {"dark": "vs-dark", "light": "vs"}[tokens.scheme(t)])
            th = json.loads(z.read("extension/" + entry["path"][2:]))
            self.assertEqual(th["type"], tokens.scheme(t))
            self.assertEqual(th["name"], entry["label"])
            self.assertTrue(th["semanticHighlighting"])
            self.assertGreater(len(th["colors"]), 150)
            for k, v in th["colors"].items():
                self.assertRegex(v, r"^#[0-9a-f]{6}([0-9a-f]{2})?$", k)
        self.assertEqual({i.date_time for i in z.infolist()}, {build.EPOCH})

    def test_no_signal_in_any_theme(self):
        for tid, t in THEMES.items():
            blob = json.dumps(build.theme(t)).lower()
            for role in tokens.SIGNAL:
                self.assertNotIn(t["colors"][role], blob, f"{tid}: {role}")

    def test_editor_text_meets_the_floor(self):
        for tid, t in THEMES.items():
            th = build.theme(t)
            bg = th["colors"]["editor.background"]
            for rule in th["tokenColors"]:
                fg = rule["settings"].get("foreground")
                if fg:
                    self.assertGreaterEqual(contrast(fg, bg), t["contrast_floor"]["text"], f"{tid}: {rule}")


class SettingsEdit(unittest.TestCase):
    JSONC = """{
    // my editor
    "editor.fontSize": 14,
    /* "workbench.colorTheme": "Commented Out", */
    "workbench.colorTheme": "Gruvbox Dark Medium", // picked in 2025
    "[python]": { "workbench.colorTheme": "Nested Stays" },
    "files.exclude": { "**/.git": true, },
    "url": "http://example.com/*not a comment*/",
}
"""

    def test_replaces_only_the_value(self):
        out = se.set_color_theme(self.JSONC, "Ryce Ola")
        self.assertEqual(out, self.JSONC.replace('"Gruvbox Dark Medium"', '"Ryce Ola"'))

    def test_idempotent(self):
        once = se.set_color_theme(self.JSONC, "Ryce Origen")
        self.assertEqual(se.set_color_theme(once, "Ryce Origen"), once)

    def test_adds_the_key_when_missing(self):
        cases = {
            '{\n    "a": 1\n}\n': '{\n    "a": 1,\n    "workbench.colorTheme": "Ryce Grafito"\n}\n',
            '{\n    "a": 1,\n}\n': '{\n    "a": 1,\n    "workbench.colorTheme": "Ryce Grafito"\n}\n',
            '{\n  "a": 1 // note\n}': '{\n  "a": 1, // note\n  "workbench.colorTheme": "Ryce Grafito"\n}',
            "{\n}\n": '{\n    "workbench.colorTheme": "Ryce Grafito"\n}\n',
            "{}": '{ "workbench.colorTheme": "Ryce Grafito" }',
            '{"a": 1}': '{"a": 1, "workbench.colorTheme": "Ryce Grafito" }',
            "": '{\n    "workbench.colorTheme": "Ryce Grafito"\n}\n',
            "// only a comment\n": '{\n    "workbench.colorTheme": "Ryce Grafito"\n}\n',
        }
        for src, want in cases.items():
            self.assertEqual(se.set_color_theme(src, "Ryce Grafito"), want, repr(src))

    def test_non_string_value_and_duplicates(self):
        src = '{\n  "workbench.colorTheme": null,\n  "workbench.colorTheme": "X"\n}'
        self.assertEqual(se.set_color_theme(src, "Y"),
                         '{\n  "workbench.colorTheme": "Y",\n  "workbench.colorTheme": "Y"\n}')

    def test_names_are_json_escaped(self):
        out = se.set_color_theme('{"workbench.colorTheme": "a"}', 'Ryce "Q"')
        self.assertEqual(out, '{"workbench.colorTheme": "Ryce \\"Q\\""}')

    def test_malformed_input_is_refused(self):
        for bad in ('{"a": "unterminated}', '{"a": 1 /* open', '[1, 2]', '{"a": 1', '{"workbench.colorTheme": {}}'):
            with self.assertRaises(se.SettingsError, msg=bad):
                se.set_color_theme(bad, "Ryce Origen")

    def test_atomic_writer_keeps_mode_and_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            real = Path(d) / "real.json"
            real.write_text(self.JSONC, encoding="utf-8")
            real.chmod(0o600)
            link = Path(d) / "settings.json"
            link.symlink_to(real)
            self.assertTrue(se.write_color_theme(link, "Ryce Origen"))
            self.assertTrue(link.is_symlink())
            self.assertIn('"workbench.colorTheme": "Ryce Origen", // picked in 2025', real.read_text())
            self.assertEqual(real.stat().st_mode & 0o777, 0o600)
            self.assertFalse(se.write_color_theme(link, "Ryce Origen"))
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["real.json", "settings.json"])
            fresh = Path(d) / "new" / "settings.json"
            self.assertTrue(se.write_color_theme(fresh, "Ryce Ola"))
            self.assertEqual(json.loads(fresh.read_text()), {"workbench.colorTheme": "Ryce Ola"})

    def test_labels_match_the_vsix(self):
        self.assertEqual([build.label(t) for t in THEMES.values()],
                         ["Ryce Origen", "Ryce Grafito", "Ryce Ola", "Ryce Tinta", "Ryce Papel"])


class Gsettings(unittest.TestCase):
    """gsettings.sh against fake gsettings/xfconf-query that log their argv."""

    def run_script(self, *args, xfconf_has=""):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            bin_ = d / "bin"
            bin_.mkdir()
            log = d / "calls"
            (bin_ / "gsettings").write_text(f'#!/bin/sh\necho "gsettings $*" >> "{log}"\n')
            (bin_ / "xfconf-query").write_text(
                f'#!/bin/sh\necho "xfconf $*" >> "{log}"\n'
                f'case " $* " in *" -n "*) exit 0 ;; esac\n'
                f'case "$4" in {xfconf_has or "/none"}) exit 0 ;; esac\nexit 1\n')
            for f in bin_.iterdir():
                f.chmod(0o755)
            state = d / "state"
            for tid in THEMES:
                (state / tid).mkdir(parents=True)
                (state / tid / "theme.json").write_text(
                    (ROOT / "themes" / tid / "theme.json").read_text(encoding="utf-8"))
            (state / "current").symlink_to("ola")
            env = {"PATH": f"{bin_}:/usr/bin:/bin", "HOME": str(d), "RYCE_THEME_STATE": str(state),
                   "DBUS_SESSION_BUS_ADDRESS": "unix:path=/dev/null"}
            r = subprocess.run(["sh", str(ROOT / "theme" / "gsettings.sh"), *args],
                               capture_output=True, text=True, env=env, timeout=60)
            calls = log.read_text().splitlines() if log.exists() else []
            return r, calls

    def test_sets_the_theme_silently_and_toggles_gtk_theme(self):
        r, calls = self.run_script("origen")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        g = [c for c in calls if c.startswith("gsettings")]
        self.assertIn("gsettings set org.gnome.desktop.interface icon-theme ryce-origen", g)
        self.assertIn("gsettings set org.gnome.desktop.interface font-name Martian Mono 10", g)
        self.assertIn("gsettings set org.gnome.desktop.interface color-scheme prefer-dark", g)
        self.assertEqual(g[-2:], ["gsettings set org.gnome.desktop.interface gtk-theme Adwaita",
                                  "gsettings set org.gnome.desktop.interface gtk-theme adw-gtk3-dark"])

    def test_file_pickers_show_hidden_files(self):
        # Ctrl+H is the focus-left key, so the pickers' own toggle never reaches them.
        r, calls = self.run_script("origen")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gsettings set org.gtk.Settings.FileChooser show-hidden true", calls)
        self.assertIn("gsettings set org.gtk.gtk4.Settings.FileChooser show-hidden true", calls)

    def test_a_paper_theme_asks_for_light(self):
        r, calls = self.run_script("papel")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gsettings set org.gnome.desktop.interface color-scheme prefer-light", calls)
        self.assertIn("gsettings set org.gnome.desktop.interface gtk-theme adw-gtk3", calls)

    def test_no_argument_follows_the_current_link(self):
        r, calls = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gsettings set org.gnome.desktop.interface font-name Inter 11", calls)

    def test_thunar_defaults_only_fill_gaps(self):
        r, calls = self.run_script("grafito", xfconf_has="/last-location-bar")
        self.assertEqual(r.returncode, 0, r.stderr)
        creates = [c for c in calls if " -n " in c]
        self.assertFalse(any("/last-location-bar" in c for c in creates))
        self.assertIn("xfconf -c thunar -p /misc-symbolic-icons-in-sidepane -n -t bool -s true", calls)

    def test_bad_ids_are_refused(self):
        for bad in ("../origen", "Origen", "nope"):
            r, calls = self.run_script(bad)
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertEqual(calls, [], bad)
            self.assertIn("gsettings.sh:", r.stderr)


if __name__ == "__main__":
    unittest.main()
