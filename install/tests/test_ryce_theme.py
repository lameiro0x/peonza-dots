"""bin/ryce-theme against a temp repo, a temp state dir and fake system commands.

PATH holds only the fakes plus python3 and sh, so a command a test does not fake is absent,
exactly like a machine without that app. Every fake appends its argv to calls.log.
"""
import fcntl
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from harness import REPO

THEMES = ("origen", "grafito", "ola", "tinta", "papel")
NAMES = {"origen": "Origen", "grafito": "Grafito", "ola": "Ola", "tinta": "Tinta", "papel": "Papel"}
TRANSITION = {"origen": "grow", "grafito": "wipe", "ola": "wave", "tinta": "fade", "papel": "fade"}

FAKE = r'''#!/usr/bin/env python3
import json, os, re, sys
name, args = os.path.basename(sys.argv[0]), sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps([name] + args) + "\n")
procs = os.environ.get("FAKE_PROCS", "").split()
if name in os.environ.get("FAKE_FAIL", "").split():
    print(f"{name}: boom", file=sys.stderr)
    sys.exit(1)
if name == "pgrep":
    sys.exit(0 if any(re.fullmatch(args[-1], p) for p in procs) else 1)
if name == "pkill":
    sys.exit(0 if args[-1] in procs else 1)
if name == "hyprctl" and args[:1] == ["monitors"]:
    print(os.environ.get("FAKE_MONITORS", "[]"))
if name == "awww" and args[:1] == ["query"]:
    print(os.environ.get("FAKE_AWWW_QUERY", ""))
if name == "systemctl" and "is-active" in args:
    sys.exit(0 if "agentd" in procs else 3)
'''

FAKED = "pgrep pkill qs hyprctl awww makoctl fish systemctl pkexec".split()
ALL_PROCS = "quickshell mako awww-daemon kitty btop cava waybar agentd"
MONITORS = json.dumps([
    {"name": "DP-1", "width": 2560, "height": 1440, "transform": 0, "refreshRate": 59.95},
    {"name": "HDMI-A-1", "width": 1920, "height": 1080, "transform": 0, "refreshRate": 143.98},
    {"name": "DP-2", "width": 1440, "height": 2560, "transform": 1, "refreshRate": 60.0},
])

SETTINGS = """// VS Code user settings — mine
{
    // the font I like
    "editor.fontSize": 14,
    "workbench.colorTheme": "Default Dark+", // old
    // "workbench.colorTheme": "Commented Out",
    "files.trimTrailingWhitespace": true,
}
"""


class RyceTheme(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="ryce-theme-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        (self.repo / "bin").mkdir(parents=True, exist_ok=True)
        (self.repo / "contracts").mkdir()
        shutil.copy(REPO / "bin/ryce-theme", self.repo / "bin/ryce-theme")
        shutil.copy(REPO / "contracts/constants.json", self.repo / "contracts/constants.json")
        self.files = json.loads((REPO / "contracts/constants.json").read_text())["theme_files"]
        self.home = self.tmp / "home"
        self.state = self.home / ".local/state/ryce/theme"
        self.state.mkdir(parents=True, exist_ok=True)
        for tid in THEMES:
            d = self.repo / "themes" / tid
            for rel in self.files:
                (d / rel).parent.mkdir(parents=True, exist_ok=True)
                (d / rel).write_text(f"{tid} {rel}\n")
            alternates = ["assets/wallpapers/tinta-peonza.jpg"] if tid == "tinta" else []
            (d / "theme.json").write_text(json.dumps({
                "id": tid, "name": NAMES[tid], "tagline": f"tagline {tid}",
                "wallpaper": {"scene": tid, "transition": TRANSITION[tid], "animated": False,
                              "alternates": alternates}}))
            for sub in ["wallpaper"] + [f"wallpaper/alt-{i}" for i in range(1, len(alternates) + 1)]:
                (d / sub).mkdir(exist_ok=True)
                for size in ("1920x1080", "2560x1440"):
                    (d / sub / f"{size}.jpg").write_bytes(b"jpg")
            (self.state / tid).symlink_to(d)
        (self.state / "current").symlink_to("origen")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        fake = self.bin / "_fake.py"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        for name in FAKED:
            (self.bin / name).symlink_to(fake)
        for real in ("python3", "sh"):
            (self.bin / real).symlink_to(shutil.which(real))
        self.log = self.tmp / "calls.log"
        self.env = {
            "PATH": str(self.bin), "HOME": str(self.home), "RYCE_HOME": str(self.home),
            "RYCE_THEME_STATE": str(self.state), "FAKE_LOG": str(self.log),
            "FAKE_PROCS": ALL_PROCS, "FAKE_MONITORS": MONITORS,
            "HYPRLAND_INSTANCE_SIGNATURE": "test", "LC_ALL": "C.UTF-8",
        }

    def theme(self, *args, rc=0, env=None):
        r = subprocess.run([str(self.repo / "bin/ryce-theme"), *args], env={**self.env, **(env or {})},
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
        return r

    def calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

    def current(self):
        return os.readlink(self.state / "current")

    def gsettings_script(self):
        script = self.home / ".local/lib/ryce/gsettings.sh"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(f'echo "[\\"gsettings.sh\\", \\"$1\\"]" >> "{self.log}"\n')

    # --- set: commit, then fan out --------------------------------------------------------

    def test_set_swaps_current_and_reloads_every_app_in_order(self):
        self.gsettings_script()
        self.theme("set", "grafito")
        self.assertEqual(self.current(), "grafito")
        self.assertFalse((self.state / "current.tmp").exists())
        uid = str(os.getuid())
        effects = [c for c in self.calls() if c[0] not in ("pgrep",) and "is-active" not in c]
        wall = self.repo.resolve() / "themes/grafito/wallpaper"
        trans = ["--transition-type", "wipe", "--transition-angle", "30", "--transition-duration", "1.0",
                 "--transition-fps", "144"]
        self.assertEqual(effects, [
            ["hyprctl", "monitors", "-j"],
            ["awww", "img", *trans, "--outputs", "DP-1,DP-2", str(wall / "2560x1440.jpg")],
            ["awww", "img", *trans, "--outputs", "HDMI-A-1", str(wall / "1920x1080.jpg")],
            ["qs", "-c", "ryce", "ipc", "call", "theme", "reload"],
            ["hyprctl", "reload"],
            ["pkill", "-USR1", "-x", "-u", uid, "kitty"],
            ["makoctl", "reload"],
            ["fish", "-c", "set -U ryce_theme grafito"],
            ["gsettings.sh", "grafito"],
            ["pkill", "-USR2", "-x", "-u", uid, "btop"],
            ["pkill", "-USR2", "-x", "-u", uid, "cava"],
            ["pkill", "-USR2", "-x", "-u", uid, "waybar"],
            ["systemctl", "--user", "kill", "--kill-whom=main", "-s", "HUP", "agentd.service"],
        ])

    def test_a_failing_step_does_not_stop_the_rest_and_exits_3(self):
        r = self.theme("set", "ola", rc=3, env={"FAKE_FAIL": "qs makoctl"})
        self.assertEqual(self.current(), "ola")
        self.assertEqual((self.state / "current/theme.json").resolve().parent.name, "ola")
        self.assertEqual(len(r.stderr.strip().splitlines()), 2, r.stderr)
        self.assertIn("boom", r.stderr)
        self.assertIn(["systemctl", "--user", "kill", "--kill-whom=main", "-s", "HUP", "agentd.service"], self.calls())

    def test_absent_apps_and_binaries_are_skipped_silently(self):
        for name in ("qs", "awww", "makoctl", "fish", "systemctl"):
            (self.bin / name).unlink()
        r = self.theme("set", "grafito", env={"FAKE_PROCS": "", "HYPRLAND_INSTANCE_SIGNATURE": ""})
        self.assertEqual(r.stderr, "")
        self.assertEqual(self.current(), "grafito")
        self.assertEqual({c[0] for c in self.calls()}, {"pgrep", "pkill"})

    def test_unknown_or_incomplete_theme_is_refused_and_current_untouched(self):
        r = self.theme("set", "magenta", rc=2)
        self.assertIn("origen, grafito, ola", r.stderr)
        (self.repo / "themes/ola" / self.files[-1]).unlink()
        r = self.theme("set", "ola", rc=2)
        self.assertIn(self.files[-1], r.stderr)
        self.assertEqual(self.current(), "origen")
        self.assertEqual(self.calls(), [])

    def test_theme_not_deployed_is_refused(self):
        (self.state / "grafito").unlink()
        self.assertIn("deploy.sh", self.theme("set", "grafito", rc=2).stderr)
        self.assertEqual(self.current(), "origen")

    def test_stale_tmp_link_from_a_crash_is_replaced(self):
        (self.state / "current.tmp").symlink_to("nowhere")
        self.theme("set", "ola")
        self.assertEqual(self.current(), "ola")
        self.assertFalse((self.state / "current.tmp").is_symlink())

    def test_lock_contention_refuses_without_switching(self):
        fd = os.open(self.state / ".lock", os.O_RDWR | os.O_CREAT)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        t = time.monotonic()
        r = self.theme("set", "grafito", rc=2, env={"RYCE_THEME_LOCK_WAIT": "0.3"})
        self.assertGreaterEqual(time.monotonic() - t, 0.3)
        self.assertIn("en curso", r.stderr)
        self.assertEqual(self.current(), "origen")

    def test_concurrent_switches_never_leave_current_dangling(self):
        env = {**self.env, "FAKE_PROCS": ""}
        procs = [subprocess.Popen([str(self.repo / "bin/ryce-theme"), "set", t], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for t in THEMES * 2]
        for _ in range(200):
            target = os.readlink(self.state / "current")
            self.assertIn(target, THEMES)
            if all(p.poll() is not None for p in procs):
                break
        self.assertEqual([p.wait(timeout=30) for p in procs], [0] * len(procs))
        self.assertTrue((self.state / "current/theme.json").is_file())

    def test_boot_runs_boot_setup_through_pkexec_or_says_it_is_missing(self):
        r = self.theme("set", "grafito", "--boot", rc=3, env={"FAKE_PROCS": ""})
        self.assertIn("boot-setup.sh", r.stderr)
        self.assertEqual(self.current(), "grafito")
        (self.repo / "install").mkdir()
        (self.repo / "install/boot-setup.sh").write_text("exit 0\n")
        self.theme("set", "ola", "--boot", env={"FAKE_PROCS": ""})
        self.assertIn(["pkexec", "bash", str(self.repo.resolve() / "install/boot-setup.sh"), "--theme", "ola",
                       "--only", "plymouth"],
                      self.calls())

    # --- reading and cycling ----------------------------------------------------------------

    def test_get_and_list(self):
        self.assertEqual(self.theme("get").stdout, "origen\n")
        rows = json.loads(self.theme("list", "--json").stdout)
        self.assertEqual(rows, [
            {"id": t, "name": NAMES[t], "tagline": f"tagline {t}", "current": t == "origen"} for t in THEMES])
        text = self.theme("list").stdout.splitlines()
        self.assertEqual(len(text), len(THEMES))
        self.assertTrue(text[0].startswith("*") and "Origen" in text[0], text)

    def test_get_without_a_current_theme_fails(self):
        (self.state / "current").unlink()
        self.assertIn("deploy.sh", self.theme("get", rc=2).stderr)

    def test_next_and_prev_wrap_in_constants_order(self):
        env = {"FAKE_PROCS": ""}
        self.theme("prev", env=env)
        self.assertEqual(self.current(), THEMES[-1])
        self.theme("next", env=env)
        self.assertEqual(self.current(), "origen")
        self.theme("next", env=env)
        self.assertEqual(self.current(), "grafito")

    def test_apply_refans_the_current_theme(self):
        self.theme("apply")
        self.assertEqual(self.current(), "origen")
        self.assertIn(["fish", "-c", "set -U ryce_theme origen"], self.calls())

    def test_bad_usage_exits_2(self):
        self.theme("bogus", rc=2)
        self.theme("set", rc=2)
        self.theme("set", "origen", "--force", rc=2)

    # --- wallpaper ----------------------------------------------------------------------------

    def awww_imgs(self):
        return [c for c in self.calls() if c[:2] == ["awww", "img"]]

    def test_wallpaper_without_transition_and_from_awww_query(self):
        query = "DP-1: 2560x1440, scale: 1, currently displaying: image: x\neDP-1: 1920x1200, scale: 1"
        self.theme("wallpaper", "--no-transition",
                   env={"HYPRLAND_INSTANCE_SIGNATURE": "", "FAKE_AWWW_QUERY": query})
        wall = self.repo.resolve() / "themes/origen/wallpaper"
        self.assertEqual(self.awww_imgs(), [
            ["awww", "img", "--transition-type", "none", "--outputs", "DP-1", str(wall / "2560x1440.jpg")],
            ["awww", "img", "--transition-type", "none", "--outputs", "eDP-1", str(wall / "1920x1080.jpg")],
        ])

    def test_wallpaper_transitions_per_theme(self):
        self.theme("set", "ola")
        self.assertEqual(self.awww_imgs()[0][2:4], ["--transition-type", "wave"])
        self.log.unlink()
        self.theme("set", "origen")
        self.assertEqual(self.awww_imgs()[0][2:7],
                         ["--transition-type", "grow", "--transition-pos", "center", "--transition-duration"])
        self.log.unlink()
        self.theme("set", "tinta")
        imgs = self.awww_imgs()[0]
        self.assertEqual(imgs[2:4], ["--transition-type", "fade"])
        # awww's own default is 30 fps: the frame rate follows the fastest monitor.
        self.assertEqual(imgs[imgs.index("--transition-fps") + 1], "144")

    def test_wallpaper_with_no_known_outputs_paints_every_output(self):
        self.theme("wallpaper", env={"FAKE_MONITORS": "not json"})
        self.assertEqual(self.awww_imgs()[0][-1], str(self.repo.resolve() / "themes/origen/wallpaper/2560x1440.jpg"))
        self.assertNotIn("--outputs", self.awww_imgs()[0])

    def test_missing_wallpaper_refuses_the_switch(self):
        # The wallpapers are in constants.json `theme_files`: a theme without one is
        # incomplete, so the switch is refused before `current` moves (rc 2).
        (self.repo / "themes/grafito/wallpaper/1920x1080.jpg").unlink()
        before = os.readlink(self.state / "current")
        r = self.theme("set", "grafito", rc=2)
        self.assertIn("1920x1080.jpg", r.stderr)
        self.assertEqual(os.readlink(self.state / "current"), before)
        self.assertEqual(self.awww_imgs(), [])

    # --- wall: the current theme's pictures -----------------------------------------------------

    def painted(self):
        """The folder each awww img call painted from, relative to the theme's wallpaper/."""
        return [str(pathlib.Path(c[-1]).parent.relative_to(self.repo.resolve() / "themes" / self.current()))
                for c in self.awww_imgs()]

    def remembered(self):
        p = self.state / "wallpapers.json"
        return json.loads(p.read_text()) if p.exists() else None

    def test_wall_cycles_the_current_theme_and_remembers_it(self):
        self.theme("set", "tinta")
        self.log.unlink()
        self.theme("wall", "next")
        self.assertEqual(self.painted(), ["wallpaper/alt-1", "wallpaper/alt-1"])
        imgs = self.awww_imgs()[0]
        self.assertEqual(imgs[2:4], ["--transition-type", "fade"])          # the theme's transition
        self.assertEqual(imgs[imgs.index("--transition-fps") + 1], "144")   # at the monitor's rate
        self.assertEqual(self.remembered(), {"tinta": 1})
        self.log.unlink()
        self.theme("wall", "next")                                          # wraps to the main picture
        self.assertEqual(self.painted(), ["wallpaper", "wallpaper"])
        self.assertEqual(self.remembered(), {})                             # the main one is the default
        self.log.unlink()
        self.theme("wall", "prev")
        self.assertEqual(self.painted(), ["wallpaper/alt-1", "wallpaper/alt-1"])
        self.log.unlink()
        self.theme("wall", "reset")
        self.assertEqual(self.painted(), ["wallpaper", "wallpaper"])
        self.assertEqual(self.remembered(), {})
        self.assertEqual(sorted(p.name for p in self.state.glob("*wallpapers*")), ["wallpapers.json"])

    def test_bare_wall_is_next(self):
        self.theme("set", "tinta")
        self.theme("wall")
        self.assertEqual(self.remembered(), {"tinta": 1})

    def test_set_and_wallpaper_honour_the_remembered_picture(self):
        self.theme("set", "tinta")
        self.theme("wall", "next")
        self.theme("set", "origen")
        self.log.unlink()
        self.theme("set", "tinta")
        self.assertEqual(self.painted(), ["wallpaper/alt-1", "wallpaper/alt-1"])
        self.log.unlink()
        self.theme("wallpaper", "--no-transition")
        self.assertEqual(self.painted(), ["wallpaper/alt-1", "wallpaper/alt-1"])
        self.assertEqual(self.remembered(), {"tinta": 1})

    def test_the_choice_is_per_theme(self):
        (self.state / "wallpapers.json").write_text(json.dumps({"ola": 0, "tinta": 1}))
        self.theme("set", "tinta")
        self.theme("wall", "reset")
        self.assertEqual(self.remembered(), {"ola": 0})

    def test_a_theme_with_one_picture_does_not_repaint(self):
        r = self.theme("wall", "next")                                      # origen: no alternates
        self.assertEqual(self.awww_imgs(), [])
        self.assertIn("un solo fondo", r.stderr)
        self.assertIsNone(self.remembered())

    def test_a_bad_or_stale_memory_falls_back_to_the_main_picture(self):
        for text in ("not json", '["tinta"]', '{"tinta": 7}', '{"tinta": "1"}', '{"tinta": true}'):
            with self.subTest(text=text):
                (self.state / "wallpapers.json").write_text(text)
                self.log.unlink(missing_ok=True)
                self.theme("set", "tinta")
                self.assertEqual(self.painted(), ["wallpaper", "wallpaper"])

    def test_a_missing_alternate_is_refused_and_not_remembered(self):
        self.theme("set", "tinta")
        (self.repo / "themes/tinta/wallpaper/alt-1/2560x1440.jpg").unlink()
        self.log.unlink()
        r = self.theme("wall", "next", rc=2)
        self.assertIn("alt-1/2560x1440.jpg", r.stderr)
        self.assertEqual(self.awww_imgs(), [])
        self.assertIsNone(self.remembered())

    def more_pictures(self, tid, n):
        """Give `tid` n alternates (the wallpaper picker's grid)."""
        d = self.repo / "themes" / tid
        info = json.loads((d / "theme.json").read_text())
        info["wallpaper"]["alternates"] = [f"assets/wallpapers/{tid}-{i}.jpg" for i in range(1, n + 1)]
        (d / "theme.json").write_text(json.dumps(info))
        for i in range(1, n + 1):
            (d / f"wallpaper/alt-{i}").mkdir(exist_ok=True)
            for size in ("1920x1080", "2560x1440"):
                (d / f"wallpaper/alt-{i}/{size}.jpg").write_bytes(b"jpg")

    def test_wall_picks_a_picture_by_its_number(self):
        self.more_pictures("tinta", 3)
        self.theme("set", "tinta")
        self.log.unlink()
        self.theme("wall", "2")
        self.assertEqual(self.painted(), ["wallpaper/alt-2", "wallpaper/alt-2"])
        self.assertEqual(self.remembered(), {"tinta": 2})
        self.log.unlink()
        self.theme("wall", "next")                                          # next goes on from the pick
        self.assertEqual(self.painted(), ["wallpaper/alt-3", "wallpaper/alt-3"])
        self.theme("wall", "0")                                             # 0 is the main picture
        self.assertEqual(self.remembered(), {})

    def test_wall_number_zero_works_on_a_theme_with_one_picture(self):
        self.theme("wall", "0")                                             # origen: no alternates
        self.assertEqual(self.painted(), ["wallpaper", "wallpaper"])
        self.assertEqual(self.remembered(), {})

    def test_wall_number_out_of_range_is_refused_and_nothing_changes(self):
        self.theme("set", "tinta")
        self.theme("wall", "1")
        self.log.unlink()
        r = self.theme("wall", "2", rc=2)                                  # tinta here: main + alt-1
        self.assertIn("de 0 a 1", r.stderr)
        self.assertEqual(self.awww_imgs(), [])
        self.assertEqual(self.remembered(), {"tinta": 1})

    def test_wall_bad_usage_and_no_current_theme(self):
        self.theme("wall", "sideways", rc=2)
        self.theme("wall", "next", "now", rc=2)
        for bad in ("-1", "1.5", "\u0661", "+1", "", "1000"):
            with self.subTest(bad=bad):
                self.theme("wall", bad, rc=2)
        (self.state / "current").unlink()
        self.theme("wall", "next", rc=2)

    # --- files rewritten in place ----------------------------------------------------------------

    def vscode(self, text=SETTINGS):
        p = self.home / ".config/Code/User/settings.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def test_vscode_edit_keeps_comments_and_other_keys(self):
        p = self.vscode()
        self.theme("set", "grafito", env={"FAKE_PROCS": ""})
        self.assertEqual(p.read_text(), SETTINGS.replace('"Default Dark+", // old', '"Ryce Grafito", // old'))
        bak = p.with_name("settings.json.ryce-bak")
        self.assertEqual(bak.read_text(), SETTINGS)
        self.theme("set", "ola", env={"FAKE_PROCS": ""})
        self.assertIn('"workbench.colorTheme": "Ryce Ola", // old', p.read_text())
        self.assertEqual(bak.read_text(), SETTINGS)

    def test_vscode_key_is_added_when_absent_and_empty_file_handled(self):
        p = self.vscode('{\n    "editor.fontSize": 14\n}\n')
        self.theme("set", "ola", env={"FAKE_PROCS": ""})
        self.assertEqual(p.read_text(), '{\n    "workbench.colorTheme": "Ryce Ola",\n    "editor.fontSize": 14\n}\n')
        p.write_text("")
        self.theme("set", "grafito", env={"FAKE_PROCS": ""})
        self.assertEqual(json.loads(p.read_text()), {"workbench.colorTheme": "Ryce Grafito"})

    def test_vscode_uses_the_repo_editor_when_present(self):
        p = self.vscode()
        mod = self.repo / "theme/vscode/settings_edit.py"
        mod.parent.mkdir(parents=True, exist_ok=True)
        mod.write_text("def set_color_theme(text, name):\n    return text + '// via module ' + name + '\\n'\n")
        self.theme("set", "grafito", env={"FAKE_PROCS": ""})
        self.assertTrue(p.read_text().endswith("// via module Ryce Grafito\n"))

    def test_vscode_absent_is_skipped(self):
        self.theme("set", "grafito", env={"FAKE_PROCS": ""})
        self.assertFalse((self.home / ".config/Code").exists())

    def test_qt6ct_conf_is_replaced_with_the_same_content(self):
        conf = self.home / ".config/qt6ct/qt6ct.conf"
        conf.parent.mkdir(parents=True, exist_ok=True)
        conf.write_text("[Appearance]\ncolor_scheme_path=x\n")
        conf.chmod(0o640)
        inode = conf.stat().st_ino
        self.theme("set", "grafito", env={"FAKE_PROCS": ""})
        self.assertEqual(conf.read_text(), "[Appearance]\ncolor_scheme_path=x\n")
        self.assertNotEqual(conf.stat().st_ino, inode)
        self.assertEqual(conf.stat().st_mode & 0o777, 0o640)
        self.assertEqual(sorted(p.name for p in conf.parent.iterdir()), ["qt6ct.conf"])


if __name__ == "__main__":
    unittest.main()
