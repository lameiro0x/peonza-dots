"""install.sh against the real repo and a temp home: the plan, the links, the way back."""
import os
import pathlib
import subprocess
import unittest

from harness import REPO, ScriptTest, tree_snapshot

SCRIPT = REPO / "install.sh"


@unittest.skipUnless(pathlib.Path("/etc/arch-release").exists(), "install.sh runs on Arch only")
class Install(ScriptTest):
    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home"
        for rel, text in {".config/kitty/kitty.conf": "# mine", ".config/hypr/hyprland.lua": "-- mine"}.items():
            p = self.home / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        # Root and the user's editor are never reached by these runs: any call fails the test.
        for name in ("sudo", "pkexec", "code"):
            stub = self.bin / name
            stub.write_text(f"#!/bin/sh\necho '{name} must not run here' >&2\nexit 99\n")
            stub.chmod(0o755)

    def install(self, *args, rc=0, script=SCRIPT, **env):
        r = self.run_script(script, *args, env={"HOME": str(self.home), **env})
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, rc, out)
        return out

    def repo_links(self):
        return [p for p in self.home.rglob("*")
                if p.is_symlink() and os.path.realpath(p).startswith(f"{REPO}/")]

    def test_dry_run_prints_the_plan_and_changes_nothing(self):
        before = tree_snapshot(self.home)
        out = self.install("--dry-run", "--yes")
        for part in ("The plan", "Packages", "Configs", "2 of your files moved aside", "dry run"):
            self.assertIn(part, out)
        self.assertEqual(tree_snapshot(self.home), before)
        self.assertEqual([c for c in self.calls() if c.split()[:2] == ["pacman", "-S"]], [])

    def test_configs_only_then_uninstall_gives_the_home_back(self):
        out = self.install("--configs-only", "--yes")
        self.assertIn("2 of your files moved aside", out)
        self.assertTrue((self.home / ".config/kitty/kitty.conf").is_symlink())
        self.assertTrue(self.repo_links())
        out = self.install("--uninstall", "--yes")
        self.assertIn("2 files back", out)
        self.assertEqual(self.repo_links(), [])
        self.assertEqual((self.home / ".config/kitty/kitty.conf").read_text(), "# mine")
        self.assertEqual((self.home / ".config/hypr/hyprland.lua").read_text(), "-- mine")
        self.assertFalse((self.home / ".local/state/ryce/deploy-manifest.tsv").exists())

    def test_bad_input_is_refused_before_anything_runs(self):
        self.assertIn("no theme 'nope'", self.install("--theme", "nope", "--dry-run", rc=1))
        self.assertIn("core, apps or dev", self.install("--packages", "all", rc=1))
        self.assertIn("unknown option", self.install("--frobnicate", rc=1))
        self.assertIn("no root", self.install("--configs-only", "--boot", rc=1))
        self.assertEqual(self.calls(), [])

    def test_no_terminal_and_no_yes_changes_nothing(self):
        before = tree_snapshot(self.home)
        self.assertIn("--yes", self.install("--configs-only", rc=1))
        self.assertEqual(tree_snapshot(self.home), before)

    def test_theme_outside_hyprland_is_only_chosen(self):  # finding 1
        for name in ("gsettings", "fish"):
            (self.bin / name).symlink_to(self.bin / "_fake.py")
        out = self.install("--configs-only", "--yes", "--theme", "grafito",
                           WAYLAND_DISPLAY="wayland-0", XDG_CURRENT_DESKTOP="GNOME")
        self.assertIn("applied when you log into Hyprland", out)
        self.assertEqual(os.readlink(self.home / ".local/state/ryce/theme/current"), "grafito")
        self.assertEqual([c for c in self.calls() if c.split()[0] in ("gsettings", "fish")], [])

    def sudo_runs_through(self):
        (self.bin / "sudo").write_text('#!/bin/sh\nexec "$@"\n')

    def test_a_known_conflict_lets_pacman_ask(self):  # finding 8
        self.sudo_runs_through()
        out = self.install("--yes", FAKE_INSTALLED="pulseaudio")
        self.assertIn("pipewire-pulse replaces pulseaudio", out)
        installs = [c for c in self.calls() if c.startswith("pacman -S ")]
        self.assertEqual(len(installs), 1, installs)
        self.assertNotIn("--noconfirm", installs[0])

    def test_yes_without_conflicts_means_noconfirm(self):  # finding 8
        self.sudo_runs_through()
        self.install("--yes")
        installs = [c for c in self.calls() if c.startswith("pacman -S ")]
        self.assertIn("--noconfirm", installs[0])

    def test_a_deploy_refusal_says_why(self):  # finding 9
        (self.home / ".local").mkdir()
        (self.home / ".local/state").symlink_to("/")
        out = self.install("--dry-run", "--yes", rc=1)
        self.assertIn("deploy.sh:", out)
        self.assertIn("manifiesto", out)

    def test_no_home_is_refused_plainly(self):  # finding 9
        env = {k: v for k, v in self.env.items() if k != "HOME"}
        r = subprocess.run(["bash", str(SCRIPT), "--dry-run", "--yes"], env=env,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertIn("HOME is not set", r.stderr)
        self.assertNotIn("unbound variable", r.stderr)

    def test_runs_through_a_symlink(self):  # finding 10
        link = self.tmp / "peonza-install"
        link.symlink_to(SCRIPT)
        self.assertIn("The plan", self.install("--dry-run", "--yes", script=link))
