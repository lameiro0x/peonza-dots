"""install/deploy.sh against a fixture repo and a temp home."""
import fcntl
import os
import pathlib
import re
import shlex
import shutil

from harness import REPO, ScriptTest, tree_snapshot

LINKS = (
    "# repo path\thome path\tmode\n"
    "\n"
    "hypr\t.config/hypr\ttree\n"
    "waybar/style.css\t.config/waybar/style.css\tfile\n"
    "bin\t.local/bin\ttree\n"
)


class DeployBase(ScriptTest):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "repo"
        files = {
            "hypr/hyprland.lua": "-- main",
            "hypr/scripts/shot.sh": "#!/bin/sh",
            "hypr/tests/test_x.py": "",
            "hypr/__pycache__/x.cpython-315.pyc": "",
            "hypr/mod.pyc": "",
            "hypr/README.md": "",
            "waybar/style.css": "* {}",
            "bin/ryce-term": "#!/bin/sh",
        }
        for rel, text in files.items():
            p = self.repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        (self.repo / "install").mkdir()
        shutil.copy(REPO / "install" / "deploy.sh", self.repo / "install" / "deploy.sh")
        (self.repo / "install" / "links.tsv").write_text(LINKS)
        self.script = self.repo / "install" / "deploy.sh"
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.repo_real = self.repo.resolve()

    def deploy(self, *args, rc=0):
        r = self.run_script(self.script, "--home", str(self.home), *args)
        self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
        return r.stdout + r.stderr

    def link(self, rel):
        return os.readlink(self.home / rel)


class Deploy(DeployBase):
    def test_links_every_file_and_skips_noise(self):
        self.deploy()
        self.assertEqual(self.link(".config/hypr/hyprland.lua"), f"{self.repo_real}/hypr/hyprland.lua")
        self.assertEqual(self.link(".config/hypr/scripts/shot.sh"), f"{self.repo_real}/hypr/scripts/shot.sh")
        self.assertEqual(self.link(".config/waybar/style.css"), f"{self.repo_real}/waybar/style.css")
        self.assertEqual(self.link(".local/bin/ryce-term"), f"{self.repo_real}/bin/ryce-term")
        hypr = self.home / ".config/hypr"
        self.assertFalse(hypr.is_symlink())
        self.assertFalse((hypr / "scripts").is_symlink())
        self.assertEqual(sorted(p.name for p in hypr.iterdir()), ["hyprland.lua", "scripts"])

    def test_second_run_changes_nothing_and_check_passes(self):
        self.deploy()
        before = tree_snapshot(self.home)
        out = self.deploy()
        self.assertRegex(out, r"4 ya correctos · 0 cambios")
        self.assertEqual(tree_snapshot(self.home), before)
        self.assertIn("4 enlaces correctos · 0 con deriva", self.deploy("--check"))

    def test_check_reports_drift(self):
        self.deploy()
        (self.home / ".config/waybar/style.css").unlink()
        out = self.deploy("--check", rc=1)
        self.assertIn("style.css no existe", out)
        self.assertFalse((self.home / ".config/waybar/style.css").exists())

    def test_existing_files_are_backed_up(self):
        mine = self.home / ".config/hypr/hyprland.lua"
        mine.parent.mkdir(parents=True)
        mine.write_text("-- my old config")
        self.deploy()
        backups = list((self.home / ".local/state/ryce/backup").glob("*/.config/hypr/hyprland.lua"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "-- my old config")
        self.assertTrue(mine.is_symlink())

    def test_orphan_links_are_reported_then_moved_aside(self):
        self.deploy()
        (self.repo / "hypr/scripts/shot.sh").unlink()
        mine = self.home / ".config/hypr/mine.lua"
        mine.symlink_to("/elsewhere/mine.lua")          # a dangling link that is not ours
        out = self.deploy("--check", rc=1)
        self.assertIn("hypr/scripts/shot.sh, que ya no existe en el repo", out)
        self.assertNotIn("mine.lua", out)
        out = self.deploy()
        self.assertIn("enlace huérfano: hypr/scripts/shot.sh", out)
        self.assertFalse((self.home / ".config/hypr/scripts/shot.sh").is_symlink())
        moved = list((self.home / ".local/state/ryce/backup").glob("*/.config/hypr/scripts/shot.sh"))
        self.assertEqual([os.readlink(m) for m in moved], [f"{self.repo_real}/hypr/scripts/shot.sh"])
        self.assertTrue(mine.is_symlink())
        self.assertIn("0 con deriva", self.deploy("--check"))

    def test_wrong_link_is_replaced(self):
        target = self.home / ".config/waybar/style.css"
        target.parent.mkdir(parents=True)
        target.symlink_to("/nonexistent/style.css")
        self.deploy()
        self.assertEqual(self.link(".config/waybar/style.css"), f"{self.repo_real}/waybar/style.css")

    def test_symlinked_parent_of_yours_is_followed_not_moved(self):  # stow setups (finding 2)
        other = self.tmp / "dots/hypr"
        other.mkdir(parents=True)
        (other / "hyprland.conf").write_text("old")
        (self.home / ".config").mkdir()
        (self.home / ".config/hypr").symlink_to(other)
        out = self.deploy()
        self.assertIn("lo sigo", out)
        self.assertEqual(os.readlink(self.home / ".config/hypr"), str(other))
        self.assertEqual((other / "hyprland.conf").read_text(), "old")
        self.assertEqual(os.readlink(other / "hyprland.lua"), f"{self.repo_real}/hypr/hyprland.lua")
        self.assertFalse((self.home / ".local/state/ryce/backup").exists())
        self.assertIn("0 con deriva", self.deploy("--check"))

    def test_symlinked_parent_not_yours_is_refused_not_moved(self):  # finding 2
        (self.home / ".config").mkdir()
        (self.home / ".config/hypr").symlink_to("/")
        (self.home / ".local").mkdir()
        (self.home / ".local/bin").symlink_to(self.tmp / "unmounted/bin")
        out = self.deploy(rc=1)
        self.assertIn(".config/hypr es un enlace a /,", out)
        self.assertIn(".local/bin es un enlace a", out)
        self.assertEqual(os.readlink(self.home / ".config/hypr"), "/")
        self.assertEqual(os.readlink(self.home / ".local/bin"), str(self.tmp / "unmounted/bin"))
        self.assertFalse((self.tmp / "unmounted").exists())
        self.assertTrue((self.home / ".config/waybar/style.css").is_symlink())
        self.assertFalse(list((self.home / ".local/state/ryce").glob("backup/*/.config/hypr")))

    def test_symlinked_parent_into_the_repo_is_moved_aside_not_written_through(self):
        (self.home / ".config").mkdir()
        (self.home / ".config/hypr").symlink_to(self.repo_real / "hypr")
        before = tree_snapshot(self.repo)
        self.deploy()
        self.assertEqual(tree_snapshot(self.repo), before)
        self.assertFalse((self.home / ".config/hypr").is_symlink())
        moved = list((self.home / ".local/state/ryce/backup").glob("*/.config/hypr"))
        self.assertEqual([os.readlink(m) for m in moved], [str(self.repo_real / "hypr")])

    def test_dry_run_changes_nothing(self):
        mine = self.home / ".config/hypr/hyprland.lua"
        mine.parent.mkdir(parents=True)
        mine.write_text("-- mine")
        before = tree_snapshot(self.home)
        out = self.deploy("--dry-run")
        self.assertIn("[simulación]", out)
        self.assertEqual(len(re.findall(r"apartado en", out)), 1, out)
        self.assertEqual(tree_snapshot(self.home), before)

    def test_missing_source_fails_after_linking_the_rest(self):
        with open(self.repo / "install/links.tsv", "a") as f:
            f.write("apps/kitty\t.config/kitty\ttree\n")
        out = self.deploy(rc=1)
        self.assertIn("falta en el repo: apps/kitty/", out)
        self.assertTrue((self.home / ".local/bin/ryce-term").is_symlink())

    def test_malformed_line_is_rejected(self):
        (self.repo / "install/links.tsv").write_text("hypr .config/hypr tree\n")
        self.assertIn("links.tsv:1", self.deploy(rc=1))
        (self.repo / "install/links.tsv").write_text("hypr\t../outside\ttree\n")
        self.assertIn("links.tsv:1", self.deploy(rc=1))

    def test_home_inside_repo_is_refused(self):
        r = self.run_script(self.script, "--home", str(self.repo / "hypr"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("dentro del repo", r.stderr)

    def test_repo_is_never_written(self):
        before = tree_snapshot(self.repo)
        self.deploy()
        self.deploy()
        self.assertEqual(tree_snapshot(self.repo), before)


THEME_LINKS = (
    "apps/kitty\t.config/kitty\ttree\n"
    "kitty/kitty.conf\t.config/kitty/kitty.conf\ttheme\n"
    "theme.json\t.config/ryce/palette.json\ttheme\n"
)
THEME_CONSTANTS = ('{"themes": ["origen", "grafito", "ola"], "default_theme": "origen",'
                   ' "theme_state": ".local/state/ryce/theme"}')


class DeployThemes(DeployBase):
    """`theme` rows link through ~/.local/state/ryce/theme/current, which deploy seeds."""

    def setUp(self):
        super().setUp()
        (self.repo / "contracts").mkdir()
        (self.repo / "contracts/constants.json").write_text(THEME_CONSTANTS)
        for tid in ("origen", "grafito", "ola"):
            d = self.repo / "themes" / tid
            (d / "kitty").mkdir(parents=True)
            (d / "kitty/kitty.conf").write_text(f"# {tid}")
            (d / "theme.json").write_text(f'{{"id": "{tid}"}}')
        (self.repo / "apps/kitty").mkdir(parents=True)
        (self.repo / "apps/kitty/session.conf").write_text("# not themed")
        (self.repo / "install/links.tsv").write_text(THEME_LINKS)
        self.st = self.home / ".local/state/ryce/theme"

    def test_seeds_state_and_links_through_current(self):
        self.deploy()
        for tid in ("origen", "grafito", "ola"):
            self.assertEqual(os.readlink(self.st / tid), f"{self.repo_real}/themes/{tid}")
        self.assertEqual(os.readlink(self.st / "current"), "origen")
        kitty = self.home / ".config/kitty/kitty.conf"
        self.assertEqual(os.readlink(kitty), f"{self.home.resolve()}/.local/state/ryce/theme/current/kitty/kitty.conf")
        self.assertEqual(kitty.read_text(), "# origen")
        self.assertEqual(self.link(".config/kitty/session.conf"), f"{self.repo_real}/apps/kitty/session.conf")
        self.assertEqual((self.home / ".config/ryce/palette.json").read_text(), '{"id": "origen"}')

    def test_switching_current_moves_every_app_and_deploy_keeps_it(self):
        self.deploy()
        os.replace(self._relink("grafito"), self.st / "current")
        self.assertEqual((self.home / ".config/kitty/kitty.conf").read_text(), "# grafito")
        before = tree_snapshot(self.home)
        out = self.deploy()
        self.assertIn(" 0 cambios", out)
        self.assertEqual(tree_snapshot(self.home), before)
        self.assertIn("0 con deriva", self.deploy("--check"))

    def _relink(self, target):
        tmp = self.st / "current.tmp"
        tmp.symlink_to(target)
        return tmp

    def test_invalid_current_is_replaced_by_the_default_and_kept_aside(self):
        self.st.mkdir(parents=True)
        (self.st / "current").symlink_to("bogus")
        self.assertIn("current", self.deploy("--check", rc=1))
        self.deploy()
        self.assertEqual(os.readlink(self.st / "current"), "origen")
        moved = list((self.home / ".local/state/ryce/backup").glob("*/.local/state/ryce/theme/current"))
        self.assertEqual([os.readlink(m) for m in moved], ["bogus"])

    def test_check_flags_a_theme_link_that_bypasses_current(self):
        self.deploy()
        kitty = self.home / ".config/kitty/kitty.conf"
        kitty.unlink()
        kitty.symlink_to(self.repo_real / "themes/origen/kitty/kitty.conf")
        self.assertIn("kitty.conf apunta a", self.deploy("--check", rc=1))
        self.deploy()
        self.assertIn("0 con deriva", self.deploy("--check"))

    def test_a_theme_missing_a_file_is_an_error(self):
        (self.repo / "themes/ola/kitty/kitty.conf").unlink()
        out = self.deploy(rc=1)
        self.assertIn("themes/ola/kitty/kitty.conf", out)
        out = self.deploy("--check", rc=1)
        self.assertIn("themes/ola/kitty/kitty.conf", out)
        self.assertNotIn("themes/grafito", out)

    def test_a_missing_theme_dir_is_an_error(self):
        shutil.rmtree(self.repo / "themes/grafito")
        self.assertIn("themes/grafito", self.deploy("--check", rc=1))

    def test_dry_run_seeds_nothing(self):
        before = tree_snapshot(self.home)
        out = self.deploy("--dry-run")
        self.assertIn("current", out)
        self.assertEqual(tree_snapshot(self.home), before)

    def test_tree_sweep_leaves_theme_links_alone(self):
        self.deploy()
        (self.repo / "apps/kitty/session.conf").unlink()
        out = self.deploy()
        self.assertIn("enlace huérfano: apps/kitty/session.conf", out)
        self.assertTrue((self.home / ".config/kitty/kitty.conf").is_symlink())
        self.assertIn("0 con deriva", self.deploy("--check"))

    def test_uninstall_removes_the_theme_state_after_a_switch(self):
        self.deploy()
        os.replace(self._relink("grafito"), self.st / "current")
        self.deploy("--uninstall")
        self.assertFalse(self.st.exists())
        self.assertFalse((self.home / ".config/kitty").exists())

    def test_theme_rows_need_the_constants(self):
        (self.repo / "contracts/constants.json").unlink()
        self.assertIn("constants.json", self.deploy(rc=1))


class DeployRender(DeployBase):
    """`render` rows: a real file, the repo file with @HOME@ replaced by the home's path."""

    def setUp(self):
        super().setUp()
        (self.repo / "flags.conf").write_text("# mine\n--x=@HOME@/a,@HOME@/b\n")
        with open(self.repo / "install/links.tsv", "a") as f:
            f.write("flags.conf\t.config/flags.conf\trender\n")
        self.dst = self.home / ".config/flags.conf"

    def test_writes_the_home_into_a_real_file(self):
        self.deploy()
        h = self.home.resolve()
        self.assertFalse(self.dst.is_symlink())
        self.assertEqual(self.dst.read_text(), f"# mine\n--x={h}/a,{h}/b\n")
        self.assertRegex(self.deploy(), r"5 ya correctos · 0 cambios")
        self.assertIn("0 con deriva", self.deploy("--check"))

    def test_an_edited_render_is_drift_and_is_moved_aside(self):
        self.deploy()
        self.dst.write_text("edited")
        self.assertIn("flags.conf", self.deploy("--check", rc=1))
        self.deploy()
        moved = list((self.home / ".local/state/ryce/backup").glob("*/.config/flags.conf"))
        self.assertEqual([m.read_text() for m in moved], ["edited"])

    def manifest_kinds(self, rel):
        rows = (self.home / ".local/state/ryce/deploy-manifest.tsv").read_text().splitlines()
        return [r.split("\t")[0] for r in rows if r.split("\t")[1] == rel]

    def test_an_edited_render_comes_back_on_uninstall(self):  # finding 4
        self.deploy()
        self.dst.write_text("edited")
        self.deploy()
        self.assertIn("backup", self.manifest_kinds(".config/flags.conf"))
        self.deploy("--uninstall")
        self.assertEqual(self.dst.read_text(), "edited")

    def test_a_restored_original_is_never_taken_for_a_render(self):  # finding 4
        self.dst.parent.mkdir(parents=True)
        self.dst.write_text("my flags")
        self.deploy()
        self.deploy("--restore")
        self.assertEqual(self.dst.read_text(), "my flags")
        self.assertNotIn("render", self.manifest_kinds(".config/flags.conf"))
        self.deploy()
        self.assertNotIn("old", self.manifest_kinds(".config/flags.conf"))
        self.deploy("--uninstall")
        self.assertEqual(self.dst.read_text(), "my flags")


class DeploySession(DeployBase):
    """A real run on the user's own home: the steps outside the links (finding 1)."""

    def setUp(self):
        super().setUp()
        log = self.tmp / "session.log"
        stub = f'#!/bin/sh\necho "$(basename "$0") $*" >> "{log}"\n'
        for name in ("code", "gsettings", "fish", "fc-cache"):
            (self.bin / name).write_text(stub)
            (self.bin / name).chmod(0o755)
        (self.repo / "bin/ryce-theme").write_text(stub)
        (self.repo / "bin/ryce-theme").chmod(0o755)
        (self.repo / "themes").mkdir()
        (self.repo / "themes/ryce-vscode.vsix").write_bytes(b"vsix")
        self.log = log

    def session(self, *args, **env):
        r = self.run_script(self.script, "--home", str(self.home), *args,
                            env={"HOME": str(self.home), **env})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout + r.stderr

    def logged(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_theme_is_applied_live_only_inside_hyprland(self):
        self.session(WAYLAND_DISPLAY="wayland-0", XDG_CURRENT_DESKTOP="GNOME")
        self.assertNotIn("ryce-theme apply", self.logged())
        self.session(WAYLAND_DISPLAY="wayland-0", HYPRLAND_INSTANCE_SIGNATURE="x")
        self.assertIn("ryce-theme apply", self.logged())

    def test_uninstall_takes_the_vscode_themes_back_and_says_what_it_leaves(self):
        self.session()
        self.assertTrue(any(l.startswith("code --install-extension") for l in self.logged()))
        out = self.session("--uninstall")
        self.assertIn("code --uninstall-extension ryce.ryce-themes", self.logged())
        self.assertIn("no se deshace lo que ryce-theme aplicó", out)
        self.assertFalse((self.home / ".local/state/ryce").exists())


class DeployRealFiles(DeployBase):
    def test_chromium_flags_keep_a_home_with_a_space_in_one_flag(self):  # finding 11
        (self.repo / "apps/chromium").mkdir(parents=True)
        shutil.copy(REPO / "apps/chromium/chromium-flags.conf", self.repo / "apps/chromium")
        (self.repo / "install/links.tsv").write_text(
            "apps/chromium/chromium-flags.conf\t.config/chromium-flags.conf\trender\n")
        self.home = self.tmp / "my home"
        self.home.mkdir()
        self.deploy()
        h = self.home.resolve()
        args = []
        for line in (self.home / ".config/chromium-flags.conf").read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                args += shlex.split(line)   # what the launcher's g_shell_parse_argv does
        self.assertIn(f"--load-extension={h}/.local/share/ryce/chromium/theme,"
                      f"{h}/.local/share/ryce/chromium/newtab", args)


class DeployUndo(DeployBase):
    """The manifest a real run writes, and --uninstall / --restore that read it."""

    def setUp(self):
        super().setUp()
        self.mine = self.home / ".config/hypr/hyprland.lua"
        self.mine.parent.mkdir(parents=True)
        self.mine.write_text("-- my old config")
        self.foreign = self.home / ".config/hypr/mine.lua"
        self.foreign.symlink_to("/elsewhere/mine.lua")

    def repo_links(self):
        return [p for p in self.home.rglob("*")
                if p.is_symlink() and os.path.realpath(p).startswith(f"{self.repo_real}/")]

    def test_uninstall_puts_the_home_back(self):
        before = tree_snapshot(self.home)
        self.deploy()
        self.deploy()
        out = self.deploy("--uninstall")
        self.assertEqual(self.repo_links(), [], out)
        self.assertEqual(self.mine.read_text(), "-- my old config")
        self.assertEqual(os.readlink(self.foreign), "/elsewhere/mine.lua")
        for gone in (".config/hypr/scripts", ".config/waybar", ".local/bin"):
            self.assertFalse((self.home / gone).exists(), gone)
        after = {k: v for k, v in tree_snapshot(self.home).items() if not k.startswith(".local")}
        self.assertEqual(after, before)

    def test_uninstall_leaves_what_the_user_put_in_place(self):
        self.deploy()
        style = self.home / ".config/waybar/style.css"
        style.unlink()
        style.write_text("my own")
        (self.home / ".config/hypr/scripts/new.sh").write_text("mine too")
        out = self.deploy("--uninstall")
        self.assertEqual(style.read_text(), "my own")
        self.assertEqual((self.home / ".config/hypr/scripts/new.sh").read_text(), "mine too")
        self.assertIn("style.css", out)
        self.assertEqual(self.repo_links(), [])

    def test_uninstall_leaves_a_followed_parent_as_it_was(self):  # finding 2
        other = self.tmp / "dotsArch-hypr"
        other.mkdir()
        (other / "hyprland.lua").write_text("-- in my dots")
        shutil.rmtree(self.home / ".config/hypr")
        (self.home / ".config/hypr").symlink_to(other)
        self.deploy()
        self.deploy("--uninstall")
        self.assertEqual(os.readlink(self.home / ".config/hypr"), str(other))
        self.assertEqual(sorted(p.name for p in other.iterdir()), ["hyprland.lua"])
        self.assertEqual((other / "hyprland.lua").read_text(), "-- in my dots")

    def test_state_folder_behind_your_link_stays_reachable(self):  # finding 5
        with open(self.repo / "install/links.tsv", "a") as f:   # a row under the state folder
            f.write("waybar/style.css\t.local/state/ryce/theme/style.css\tfile\n")
        for link in (".local/state", ".local"):
            with self.subTest(link=link):
                real = self.tmp / f"elsewhere-{link.replace('/', '-')}"
                real.mkdir()
                shutil.rmtree(self.home / ".local", ignore_errors=True)
                (self.home / link).parent.mkdir(parents=True, exist_ok=True)
                (self.home / link).symlink_to(real)
                self.deploy()
                self.assertEqual(os.readlink(self.home / link), str(real))
                self.assertTrue((self.home / ".local/state/ryce/deploy-manifest.tsv").is_file())
                self.deploy("--uninstall")
                self.assertEqual(os.readlink(self.home / link), str(real))
                self.assertEqual(self.repo_links(), [])
                self.assertEqual(self.mine.read_text(), "-- my old config")

    def test_state_folder_behind_a_foreign_link_is_refused_before_writing(self):  # finding 5
        (self.home / ".local").mkdir()
        (self.home / ".local/state").symlink_to("/")
        before = tree_snapshot(self.home)
        self.assertIn("manifiesto", self.deploy("--dry-run", rc=1))
        self.assertIn("manifiesto", self.deploy(rc=1))
        self.assertEqual(tree_snapshot(self.home), before)

    def fix_date(self, stamp):
        date = self.bin / "date"
        date.write_text(f"#!/bin/sh\necho {stamp}\n")
        date.chmod(0o755)

    def test_two_runs_in_one_second_keep_both_backups(self):  # finding 3
        self.fix_date("20260101-120000")
        self.deploy()
        self.mine.unlink()
        self.mine.write_text("-- written after the first run")
        self.deploy()
        sets = sorted(p.name for p in (self.home / ".local/state/ryce/backup").iterdir())
        self.assertEqual(len(sets), 2, sets)
        for s in sets:
            self.assertRegex(s, r"^20260101-120000-[A-Za-z0-9]{4}$")
        copies = (self.home / ".local/state/ryce/backup").glob("*/.config/hypr/hyprland.lua")
        self.assertEqual(sorted(c.read_text() for c in copies),
                         ["-- my old config", "-- written after the first run"])
        self.deploy("--uninstall")
        self.assertEqual(self.mine.read_text(), "-- my old config")

    def test_a_second_run_waits_for_the_first(self):  # finding 3
        self.deploy()
        fd = os.open(self.home / ".local/state/ryce", os.O_RDONLY)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        self.assertIn("otro deploy.sh", self.deploy(rc=1))
        self.assertIn("otro deploy.sh", self.deploy("--uninstall", rc=1))

    def test_restore_skips_a_newer_set_of_orphan_links_only(self):  # finding 6
        self.fix_date("20260101-120000")
        self.deploy()
        (self.repo / "hypr/scripts/shot.sh").unlink()
        self.fix_date("20260101-120001")
        self.assertIn("enlace huérfano", self.deploy())
        self.deploy("--restore")
        self.assertEqual(self.mine.read_text(), "-- my old config")

    def test_uninstall_keeps_what_it_could_not_put_back(self):  # finding 7
        style = self.home / ".config/waybar/style.css"
        style.mkdir(parents=True)               # an empty folder where a link goes
        self.deploy()
        style.unlink()
        style.write_text("my own")
        out = self.deploy("--uninstall")
        self.assertIn("tu copia sigue en", out)
        kept = list((self.home / ".local/state/ryce/backup").glob("*/.config/waybar/style.css"))
        self.assertEqual([k.is_dir() for k in kept], [True])
        style.unlink()
        self.deploy("--restore")
        self.assertTrue(style.is_dir())

    def test_uninstall_dry_run_changes_nothing(self):
        self.deploy()
        before = tree_snapshot(self.home)
        out = self.deploy("--uninstall", "--dry-run")
        self.assertIn("[simulación]", out)
        self.assertEqual(tree_snapshot(self.home), before)

    def test_uninstall_without_a_manifest_refuses(self):
        self.assertIn("manifiesto", self.deploy("--uninstall", rc=1))

    def test_restore_puts_back_the_latest_set_only(self):
        self.deploy()
        out = self.deploy("--restore")
        self.assertEqual(self.mine.read_text(), "-- my old config")
        self.assertTrue((self.home / ".local/bin/ryce-term").is_symlink(), out)
        self.assertIn("1 con deriva", self.deploy("--check", rc=1))
        self.assertIn("nada que devolver", self.deploy("--restore", rc=1))

    def test_restore_rejects_an_unknown_set(self):
        self.deploy()
        self.assertIn("../x", self.deploy("--restore", "../x", rc=1))
        self.assertIn("20000101-000000", self.deploy("--restore", "20000101-000000", rc=1))
        self.assertTrue(self.mine.is_symlink())

    def test_a_new_render_does_not_count_as_the_users_file(self):
        (self.repo / "flags.conf").write_text("v1 @HOME@\n")
        with open(self.repo / "install/links.tsv", "a") as f:
            f.write("flags.conf\t.config/flags.conf\trender\n")
        self.deploy()
        (self.repo / "flags.conf").write_text("v2 @HOME@\n")
        self.deploy()
        self.deploy("--uninstall")
        self.assertFalse((self.home / ".config/flags.conf").exists())


class RealLinks(ScriptTest):
    def test_real_links_tsv_parses(self):
        rows = [l.split("\t") for l in (REPO / "install/links.tsv").read_text().splitlines()
                if l and not l.startswith("#")]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(len(row), 3, row)
            self.assertIn(row[2], ("file", "tree", "theme", "render"))
            self.assertFalse(row[1].startswith("/") or ".." in pathlib.PurePosixPath(row[1]).parts, row)
