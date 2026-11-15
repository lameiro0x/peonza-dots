"""bin/ryce-launcher: the text it hands rofi, the slice every app starts in, and the
contract with the themes' rofi/style.rasi (every widget it fills exists there)."""
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from harness import REPO

LAUNCHER = REPO / "bin" / "ryce-launcher"
THEMES = json.loads((REPO / "contracts" / "constants.json").read_text(encoding="utf-8"))["themes"]
SCOPE = "systemd-run --user --scope --slice=app.slice --collect"

FAKE_ROFI = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_ARGV"], "w") as f:
    json.dump(sys.argv[1:], f)
"""


def load():
    loader = importlib.machinery.SourceFileLoader("ryce_launcher", str(LAUNCHER))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


L = load()


class Words(unittest.TestCase):
    def test_greeting_follows_the_spanish_day(self):
        for hour, want in ((0, "Buenas noches"), (5, "Buenas noches"), (6, "Buenos días"),
                           (13, "Buenos días"), (14, "Buenas tardes"), (20, "Buenas tardes"),
                           (21, "Buenas noches"), (23, "Buenas noches")):
            self.assertEqual(L.greeting(hour), want, hour)

    def test_date_in_spanish(self):
        t = time.strptime("2026-11-09", "%Y-%m-%d")      # a Monday
        self.assertEqual(L.spanish_date(t), "lunes, 9 de noviembre")
        t = time.strptime("2027-01-03", "%Y-%m-%d")
        self.assertEqual(L.spanish_date(t), "domingo, 3 de enero")

    def test_uptime(self):
        self.assertEqual(L.uptime_text(59), "0 min")
        self.assertEqual(L.uptime_text(42 * 60 + 5), "42 min")
        self.assertEqual(L.uptime_text(3 * 3600 + 7 * 60), "3 h 07 min")
        self.assertEqual(L.uptime_text(2 * 86400 + 5 * 3600 + 59), "2 d 5 h")

    def test_agents_counts_only(self):
        self.assertEqual(L.agents_text(None), "")
        self.assertEqual(L.agents_text({}), "ninguno")
        self.assertEqual(L.agents_text({"busy": 0, "waiting": 0, "idle": 3}), "ninguno")
        self.assertEqual(L.agents_text({"busy": 1}), "1 trabajando")
        self.assertEqual(L.agents_text({"waiting": 1}), "1 te espera")
        self.assertEqual(L.agents_text({"busy": 2, "waiting": 3}), "2 trabajando · 3 te esperan")
        # Garbage from a half-written or foreign file never reaches the screen.
        self.assertEqual(L.agents_text({"busy": "2; } evil {", "waiting": -1}), "ninguno")
        self.assertEqual(L.agents_text(["busy"]), "")

    def test_rasi_strings_are_escaped(self):
        self.assertEqual(L.rasi('a "b" \\c'), '"a \\"b\\" \\\\c"')


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="ryce-launcher-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        (bin_ / "rofi").write_text(FAKE_ROFI)
        (bin_ / "rofi").chmod(0o755)
        self.state = self.tmp / "state"
        (self.state / "tinta").mkdir(parents=True)
        (self.state / "current").symlink_to(REPO / "themes" / "tinta")
        self.agentd = self.tmp / "agentd"
        self.agentd.mkdir()
        self.argv_file = self.tmp / "argv.json"
        self.env = {"PATH": f"{bin_}:/usr/bin:/bin", "HOME": str(self.tmp), "LC_ALL": "C.UTF-8",
                    "RYCE_THEME_STATE": str(self.state), "RYCE_AGENTD_DIR": str(self.agentd),
                    "FAKE_ARGV": str(self.argv_file)}

    def launch(self, *args, env=None):
        r = subprocess.run([sys.executable, str(LAUNCHER), *args], env={**self.env, **(env or {})},
                           capture_output=True, text=True, timeout=30)
        argv = json.loads(self.argv_file.read_text()) if self.argv_file.exists() else None
        return r, argv

    def opt(self, argv, flag):
        return argv[argv.index(flag) + 1]

    def test_rofi_gets_the_theme_the_modes_and_the_slice(self):
        r, argv = self.launch()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(argv[:4], ["-show", "drun", "-modes", "drun,window,filebrowser,run"])
        self.assertEqual(self.opt(argv, "-theme"), str(self.state / "current" / "rofi" / "style.rasi"))
        self.assertEqual(self.opt(argv, "-run-command"), f"{SCOPE} {{cmd}}")
        self.assertEqual(self.opt(argv, "-run-shell-command"), f"{SCOPE} kitty -e {{cmd}}")
        ts = self.opt(argv, "-theme-str")
        self.assertRegex(ts, r'textbox-hh \{ content: "\d\d"; \}')
        self.assertRegex(ts, r'textbox-greet \{ content: "Buen(os días|as tardes|as noches)"; \}')
        self.assertIn("face { enabled: true; }", ts)
        panel = self.state / "current" / "wallpaper" / "panel.png"
        self.assertIn(f'still {{ background-image: url("{panel}", both); }}', ts)
        # rofi 2.0.0 reads a string up to the last quote on its line: one string per line.
        for line in ts.splitlines():
            self.assertLessEqual(line.count('"'), 2, line)

    def test_each_mode_opens_on_its_tab(self):
        for mode in ("window", "filebrowser", "run"):
            r, argv = self.launch(mode)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(argv[:2], ["-show", mode])

    def test_roster_counts_but_never_names(self):
        (self.agentd / "roster.json").write_text(json.dumps({
            "schema": "agentd.roster/1", "counts": {"waiting": 1, "busy": 2, "idle": 0},
            "sessions": [{"project": "secret-client", "title": "Informe confidencial", "cwd": "/srv/x"}]}))
        r, argv = self.launch()
        ts = self.opt(argv, "-theme-str")
        self.assertIn('textbox-agents { content: "2 trabajando · 1 te espera"; }', ts)
        self.assertNotIn("agents-row { enabled: false; }", ts)
        blob = json.dumps(argv)
        for leak in ("secret-client", "Informe", "/srv/x"):
            self.assertNotIn(leak, blob)

    def test_no_agentd_hides_the_row(self):
        for content in (None, "{not json", json.dumps({"schema": "other/1", "counts": {"busy": 9}})):
            if content is not None:
                (self.agentd / "roster.json").write_text(content)
            r, argv = self.launch()
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("agents-row { enabled: false; }", self.opt(argv, "-theme-str"))

    def test_missing_theme_still_opens_rofi(self):
        (self.state / "current").unlink()
        r, argv = self.launch()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("-theme", argv)
        self.assertNotIn("background-image", self.opt(argv, "-theme-str"))
        self.assertIn("deploy.sh", r.stderr)

    def test_bad_usage_and_no_rofi(self):
        for args in (["ssh"], ["drun", "extra"]):
            r, argv = self.launch(*args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("uso: ryce-launcher", r.stderr)
            self.assertIsNone(argv)
        r, argv = self.launch(env={"PATH": "/nonexistent"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("rofi no está instalado", r.stderr)


class ThemeContract(unittest.TestCase):
    """Every widget the launcher fills or toggles is declared in every theme's sheet,
    and the clipboard picker (no launcher) starts with the face and readout off."""

    def test_every_theme_declares_the_widgets(self):
        widgets = set(re.findall(r"^([a-z-]+) \{", L.theme_str(time.localtime(), 60.0, "ninguno", "/x"), re.M))
        widgets.add("agents-row")
        for tid in THEMES:
            text = (REPO / "themes" / tid / "rofi" / "style.rasi").read_text(encoding="utf-8")
            with self.subTest(theme=tid):
                for w in widgets:
                    self.assertRegex(text, rf"(?m)^{re.escape(w)}\b.*\{{|[\[,] {re.escape(w)}\b", w)
                self.assertRegex(text, r"children:\s*\[ face, still-air, readout, signature \]")
                for w in ("face", "readout"):
                    block = re.search(rf"(?ms)^{w} \{{(.*?)^\}}", text).group(1)
                    self.assertRegex(block, r"enabled:\s+false;", w)
                self.assertIn("--slice=app.slice", text)     # the filebrowser's opener


if __name__ == "__main__":
    unittest.main()
