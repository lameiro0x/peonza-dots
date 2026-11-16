"""install/system-setup.sh against a temp root (RYCE_ROOT) with every system command faked."""
import json
import os
import re
import shutil
import subprocess
import unittest

from harness import REPO, ScriptTest, tree_snapshot

SCRIPT = REPO / "install" / "system-setup.sh"

# Arch's stock /etc/pacman.conf [options] (pacman 7), trimmed, plus one user pin.
PACMAN_CONF = """\
[options]
#RootDir     = /
HoldPkg     = pacman glibc
Architecture = auto

# Pacman won't upgrade packages listed in IgnorePkg and members of IgnoreGroup
IgnorePkg   = linux-firmware-mediatek
#IgnoreGroup =

# Misc options
#UseSyslog
#Color
#NoProgressBar
CheckSpace
#VerbosePkgLists
ParallelDownloads = 5
DownloadUser = alpm

[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist
"""

SNAPPER = """\
SUBVOLUME="/"
FSTYPE="btrfs"
TIMELINE_CREATE="yes"
TIMELINE_CLEANUP="yes"
TIMELINE_MIN_AGE="3600"
TIMELINE_LIMIT_HOURLY="10"
TIMELINE_LIMIT_DAILY="10"
TIMELINE_LIMIT_WEEKLY="0"
TIMELINE_LIMIT_MONTHLY="10"
TIMELINE_LIMIT_YEARLY="10"
"""

MUTATING = re.compile(r"^(pacman -S|systemctl (enable|start|restart|try-restart|daemon-reload)|"
                      r"btrfs subvolume create|chattr|chown|usermod|runuser|virsh|sysctl --system|nft -f)")


class SystemSetup(ScriptTest):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "root"
        self.home = self.root / "home" / "ana"
        self.home.mkdir(parents=True)
        files = {
            "etc/arch-release": "",
            "etc/pacman.conf": PACMAN_CONF,
            "etc/snapper/configs/root": SNAPPER,
            "etc/snapper/configs/home": SNAPPER.replace('"/"', '"/home"'),
            "etc/greetd/config.toml": '[terminal]\nvt = 1\n\n[default_session]\ncommand = "agreety --cmd /bin/sh"\nuser = "greeter"\n',
            "etc/locale.conf": "LANG=es_ES.UTF-8\n",
            "etc/vconsole.conf": "KEYMAP=es\n",
            "proc/cmdline": "root=/dev/mapper/root rootflags=subvol=@ zswap.enabled=0 rw\n",
            "usr/share/libalpm/hooks/05-snap-pac-pre.hook": "",
        }
        for rel, text in files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        (self.root / "var/lib/libvirt/images").mkdir(parents=True)   # shipped empty by libvirt
        self.env.update(RYCE_ROOT=str(self.root), FAKE_HOME=str(self.home))
        self.user = "ana"

    def setup(self, *args, **env):
        r = self.run_script(SCRIPT, "--yes", "--user", self.user, *args, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def changes(self, out):
        return int(re.search(r"Resumen: (\d+) cambios", out).group(1))

    def read(self, rel):
        return (self.root / rel).read_text()

    def test_second_run_changes_nothing(self):
        first = self.setup()
        self.assertGreater(self.changes(first), 10)
        n = len(self.calls())
        second = self.setup()
        self.assertEqual(self.changes(second), 0, second)
        mutating = [c for c in self.calls()[n:] if MUTATING.match(c)]
        self.assertEqual(mutating, [])

    def test_first_run_writes_the_system_layer(self):
        self.setup()
        self.assertIn("zram-size = ram / 2", self.read("etc/systemd/zram-generator.conf"))
        sysctl = self.read("etc/sysctl.d/99-ryce.conf")
        for line in ("vm.swappiness = 180", "vm.watermark_boost_factor = 0", "vm.watermark_scale_factor = 125",
                     "vm.page-cluster = 0", "fs.inotify.max_user_watches = 1048576",
                     "fs.inotify.max_user_instances = 1024"):
            self.assertIn(line, sysctl)
        self.assertIn("ManagedOOMMemoryPressure=kill",
                      self.read("etc/systemd/system/user@.service.d/90-ryce-oomd.conf"))
        self.assertIn("SystemMaxUse=1G", self.read("etc/systemd/journald.conf.d/90-ryce.conf"))
        pre = self.read("etc/pacman.d/hooks/55-bootbackup_pre.hook")
        self.assertIn("When = PreTransaction", pre)
        self.assertIn("/boot/ /.bootbackup/pre/", pre)
        self.assertIn("When = PostTransaction", self.read("etc/pacman.d/hooks/95-bootbackup_post.hook"))
        root = self.read("etc/snapper/configs/root")
        self.assertIn('TIMELINE_LIMIT_HOURLY="5"', root)
        self.assertIn('TIMELINE_LIMIT_MONTHLY="0"', root)
        home = self.read("etc/snapper/configs/home")
        self.assertIn('TIMELINE_LIMIT_HOURLY="0"', home)
        self.assertIn('TIMELINE_LIMIT_DAILY="7"', home)
        self.assertEqual(root.count("TIMELINE_LIMIT_HOURLY"), 1)
        self.assertIn("--protocol https", self.read("etc/xdg/reflector/reflector.conf"))
        calls = "\n".join(self.calls())
        for unit in ("greetd.service", "docker.service", "libvirtd.service", "systemd-oomd.service",
                     "fstrim.timer", "paccache.timer", "reflector.timer", "NetworkManager.service"):
            self.assertIn(f"systemctl enable --quiet {unit}", calls)
        self.assertNotIn("thermald", calls.replace("pacman -Q thermald", ""))
        self.assertIn("usermod -aG docker,kvm,libvirt,render,video ana", calls)
        self.assertTrue((self.home / ".config/user-dirs.dirs").exists())

    def test_sshd_answers_the_lan_read_at_install_time_never_a_public_one(self):
        # Made-up networks (allowed for this file in tools/publish/denylist.json).
        out = self.setup(FAKE_LAN="10.0.0.0/24")
        nft = self.read("etc/nftables.conf")
        self.assertIn('ip saddr 10.0.0.0/24 tcp dport ssh accept comment "sshd: the home LAN only"', nft)
        self.assertIn('iifname "tailscale0" tcp dport ssh accept', nft)
        self.assertNotIn("no veo la red local", out)
        for lan in ("", "203.0.113.0/24", "10.0.0.0"):          # no network, a public link, junk
            with self.subTest(lan=lan):
                out = self.setup(FAKE_LAN=lan)
                nft = self.read("etc/nftables.conf")
                self.assertNotIn("ip saddr", nft)
                self.assertIn("# sshd: no private LAN was up at install time", nft)
                self.assertIn("no veo la red local", out)

    def test_firewall_and_docker_on_localhost(self):
        out = self.setup()
        nft = self.read("etc/nftables.conf")
        self.assertIn("destroy table inet filter", nft)
        self.assertRegex(nft, r"chain input \{\n\s+type filter hook input priority filter\n\s+policy drop")
        self.assertIn('iifname "virbr*" accept', nft)
        self.assertNotIn("flush ruleset", nft)
        calls = self.calls()
        self.assertIn(f"nft -c -f {self.root}/etc/nftables.conf", calls)
        self.assertIn(f"nft -f {self.root}/etc/nftables.conf", calls)
        self.assertIn("systemctl enable --quiet nftables.service", calls)
        self.assertLess(calls.index(f"nft -f {self.root}/etc/nftables.conf"),
                        calls.index("systemctl enable --quiet docker.service"))
        daemon = json.loads(self.read("etc/docker/daemon.json"))
        self.assertEqual(daemon["ip"], "127.0.0.1")
        self.assertIs(daemon["ip-forward-no-drop"], True)
        self.assertEqual(daemon["default-network-opts"]["bridge"]["com.docker.network.bridge.host_binding_ipv4"],
                         "127.0.0.1")
        self.assertIn("After=nftables.service",
                      self.read("etc/systemd/system/docker.service.d/90-ryce-nftables.conf"))
        self.assertIn("root sin contraseña", out)

    def test_docker_config_merges_and_restarts_only_when_it_changes(self):
        self.setup()
        n = len(self.calls())
        path = self.root / "etc/docker/daemon.json"
        conf = json.loads(path.read_text())
        conf["log-driver"] = "journald"
        conf["ip"] = "0.0.0.0"
        path.write_text(json.dumps(conf))
        self.setup()
        merged = json.loads(path.read_text())
        self.assertEqual((merged["log-driver"], merged["ip"]), ("journald", "127.0.0.1"))
        self.assertIn("systemctl restart docker.service", self.calls()[n:])

    def test_invalid_docker_json_stops_without_touching_it(self):
        path = self.root / "etc/docker/daemon.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"ip": ')
        r = self.run_script(SCRIPT, "--yes", "--user", self.user)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("daemon.json no es JSON válido", r.stderr)
        self.assertEqual(path.read_text(), '{"ip": ')

    def test_rerun_with_the_pin_never_upgrades(self):
        self.setup()
        state = self.state / "state.json"
        st = json.loads(state.read_text())
        st["installed"].remove("kitty")
        state.write_text(json.dumps(st))
        n = len(self.calls())
        self.setup()
        installs = [c for c in self.calls()[n:] if c.startswith("pacman -S")]
        self.assertEqual(installs, ["pacman -S --needed --noconfirm -- kitty"])

    def test_local_bin_on_path_for_login_shells(self):
        self.setup()
        profile = self.read("etc/profile.d/ryce-localbin.sh")
        self.assertIn('PATH="$HOME/.local/bin:$PATH"; export PATH', profile)
        for home_path in ("/usr/bin:/bin", "/home/ana/.local/bin:/usr/bin"):
            r = subprocess.run(["/bin/sh", "-c", f'. "$1"; printf %s "$PATH"', "sh",
                                str(self.root / "etc/profile.d/ryce-localbin.sh")],
                               env={"PATH": home_path, "HOME": "/home/ana"}, capture_output=True, text=True, timeout=10)
            self.assertEqual(r.stdout.count("/home/ana/.local/bin"), 1, r.stdout)

    def test_libvirt_membership_is_granted_not_flagged(self):
        # Without it polkit asked for the password on every virsh process (2026-11-16).
        st = {"installed": [], "enabled": [], "active": [], "subvols": [],
              "groups": {g: ["ana"] for g in ("docker", "kvm", "libvirt", "render", "video")}}
        self.state.mkdir()
        (self.state / "state.json").write_text(json.dumps(st))
        out = self.setup()
        self.assertNotIn("gpasswd -d ana libvirt", out)
        self.assertIn("ana está en docker kvm libvirt render video", out)
        self.assertNotIn("usermod", "\n".join(self.calls()))

    def test_pacman_conf_edit_is_idempotent_and_keeps_user_pins(self):
        self.setup()
        conf = self.read("etc/pacman.conf")
        self.assertEqual(self.read("etc/pacman.conf.ryce-orig"), PACMAN_CONF)
        ignore = [l for l in conf.splitlines() if l.startswith("IgnorePkg")]
        self.assertEqual(len(ignore), 1, conf)
        names = ignore[0].split("=", 1)[1].split()
        self.assertEqual(names[0], "linux-firmware-mediatek")
        for pkg in ("hyprland", "hyprutils", "aquamarine", "hyprpicker", "hyprland-qt-support"):
            self.assertIn(pkg, names)
        self.assertNotIn("quickshell", names)
        self.assertEqual(len(names), len(set(names)))
        self.assertRegex(conf, r"(?m)^Color$")
        self.assertRegex(conf, r"(?m)^VerbosePkgLists$")
        self.assertRegex(conf, r"(?m)^ParallelDownloads = 10$")
        self.assertNotIn("ParallelDownloads = 5", conf)
        self.assertIn("[core]\nInclude = /etc/pacman.d/mirrorlist", conf)
        self.setup()
        self.assertEqual(self.read("etc/pacman.conf"), conf)

    def test_retired_pin_is_removed_from_an_earlier_run(self):
        earlier = PACMAN_CONF.replace(
            "IgnorePkg   = linux-firmware-mediatek",
            "# ryce-pc: the hypr family moves as one unit; ryce-update explains how to upgrade it\n"
            "IgnorePkg   = linux-firmware-mediatek hyprland quickshell hyprutils")
        (self.root / "etc/pacman.conf").write_text(earlier)
        self.setup()
        conf = self.read("etc/pacman.conf")
        line = next(l for l in conf.splitlines() if l.startswith("IgnorePkg"))
        self.assertNotIn("quickshell", line.split())
        self.assertEqual(line.split()[2:5], ["linux-firmware-mediatek", "hyprland", "hyprutils"])
        self.assertEqual(conf.count("# ryce-pc: the hypr family"), 1)
        self.setup()
        self.assertEqual(self.read("etc/pacman.conf"), conf)

    def test_pacman_conf_without_any_ignorepkg_line(self):
        (self.root / "etc/pacman.conf").write_text("[options]\nArchitecture = auto\n\n[core]\nInclude = x\n")
        self.setup()
        conf = self.read("etc/pacman.conf")
        options = conf.split("[core]")[0]
        self.assertIn("IgnorePkg   = hyprland", options)
        self.assertIn("Color\n", options)
        self.setup()
        self.assertEqual(self.read("etc/pacman.conf"), conf)

    def test_greetd_never_logs_in_by_itself(self):
        # The LUKS passphrase opens the disk; the login page asks for the password after it.
        for crypt in ("0", "1"):
            self.setup(FAKE_CRYPT=crypt)
            cfg = self.read("etc/greetd/config.toml")
            self.assertIn('[default_session]\ncommand = "/usr/local/bin/ryce-greeter"\nuser = "greeter"', cfg)
            self.assertNotIn("initial_session", cfg)

    def test_an_old_autologin_is_replaced(self):
        cfg = self.root / "etc/greetd/config.toml"
        cfg.write_text(cfg.read_text() + '\n[initial_session]\ncommand = "start-hyprland"\nuser = "ana"\n')
        self.setup()
        self.assertNotIn("initial_session", self.read("etc/greetd/config.toml"))

    def test_login_page_regreet_and_fonts_outside_home(self):
        stale = self.root / "usr/local/share/ryce/greeter/Old.qml"
        stale.parent.mkdir(parents=True)
        stale.write_text("Item {}\n")
        spool = self.root / "var/lib/ryce/greeter"   # the retired theme spool: left as it is
        spool.mkdir(parents=True)
        (spool / "theme.json").write_text("{}\n")
        self.setup()
        art = REPO / "theme/boot/greeter/background.jpg"
        page = self.root / "usr/local/share/ryce/greeter"
        qml = sorted(p.name for p in (REPO / "quickshell/greeter").glob("*.qml"))
        self.assertEqual(sorted(p.name for p in page.iterdir()), sorted(qml + ["background.jpg"]))
        for name in qml:
            self.assertEqual((page / name).read_bytes(), (REPO / "quickshell/greeter" / name).read_bytes())
            self.assertEqual((page / name).stat().st_mode & 0o777, 0o644)
        installed = {
            "usr/local/share/ryce/greeter/background.jpg": art,
            "usr/share/ryce/greeter/background.jpg": art,
            "etc/greetd/regreet.toml": REPO / "install/boot/greeter/regreet.toml",
            "etc/greetd/regreet.css": REPO / "install/boot/greeter/regreet.css",
            "usr/local/share/wayland-sessions/hyprland-uwsm.desktop": REPO / "install/boot/greeter/hyprland-uwsm.desktop",
        }
        for rel, src in installed.items():
            self.assertEqual((self.root / rel).read_bytes(), src.read_bytes(), rel)
            self.assertEqual((self.root / rel).stat().st_mode & 0o777, 0o644, rel)
        fonts = self.root / "usr/local/share/fonts/ryce"
        self.assertTrue((fonts / "InstrumentSerif-Regular.ttf").is_file())
        self.assertTrue((fonts / "licenses/Doto-OFL.txt").is_file())
        icons = self.root / "usr/share/icons/ryce-peonza"
        src = REPO / "assets/cursors/ryce-peonza"
        self.assertEqual((icons / "index.theme").read_bytes(), (src / "index.theme").read_bytes())
        self.assertEqual(sorted(p.name for p in (icons / "cursors").iterdir()),
                         sorted(p.name for p in (src / "cursors").iterdir()))
        for name in ("left_ptr", "default", "progress"):   # an alias is a plain copy
            self.assertEqual((icons / "cursors" / name).read_bytes(), (src / "cursors" / name).read_bytes())
            self.assertEqual((icons / "cursors" / name).stat().st_mode & 0o777, 0o644)
        self.assertEqual(sorted(p.name for p in spool.iterdir()), ["theme.json"])
        self.assertFalse([c for c in self.calls() if "var/lib/ryce" in c])

    def test_root_takes_back_login_files_with_the_right_content(self):
        # Installed once by `cp -a` out of the repo: the user's, so a user process could
        # rewrite the wrapper and read the next login's password. Same content still changes.
        self.setup()
        wrapper = self.root / "usr/local/bin/ryce-greeter"
        css = self.root / "etc/greetd/regreet.css"
        css.chmod(0o666)
        self.foreign_owner(wrapper)
        n = len(self.calls())
        out = self.setup()
        self.assertIn("/usr/local/bin/ryce-greeter: de root y con su modo (el contenido ya estaba)", out)
        self.assertIn("/etc/greetd/regreet.css: de root y con su modo", out)
        self.assertEqual(css.stat().st_mode & 0o777, 0o644)
        me = f"{os.getuid()}:{os.getgid()}"
        self.assertIn(f"chown {me} {wrapper}.ryce-tmp", self.calls()[n:])
        self.assertFalse((self.root / "etc/greetd/regreet.css.ryce-orig").exists())   # same content: no original

    def test_a_user_owned_page_folder_goes_back_to_root(self):
        self.setup()
        page = self.root / "usr/local/share/ryce/greeter"
        (page / "shell.qml").unlink()   # so this run writes into the folder too
        self.foreign_owner(page)
        n = len(self.calls())
        out = self.setup()
        self.assertIn("/usr/local/share/ryce/greeter: de root y sin escritura para otros", out)
        me = f"{os.getuid()}:{os.getgid()}"
        calls = self.calls()[n:]
        # put right BEFORE anything is written into it
        self.assertLess(calls.index(f"chown -R {me} {page}"), calls.index(f"chown {me} {page}/.shell.qml.ryce-tmp"))

    def fake_repo(self):
        """What system-setup.sh reads from the repo, copied: links can be planted there."""
        repo = self.tmp / "repo"
        for rel in ("install", "quickshell/greeter", "theme/boot/greeter", "assets/fonts", "assets/cursors"):
            shutil.copytree(REPO / rel, repo / rel, symlinks=True,
                            ignore=shutil.ignore_patterns("__pycache__", "tests"))
        secret = self.tmp / "secret"   # stands for a root-only folder (NetworkManager's…)
        secret.mkdir()
        (secret / "home-wifi.nmconnection").write_text("psk=hunter2\n")
        return repo, secret

    def assertRefusedAndNotCopied(self, repo, what):
        r = self.run_script(repo / "install/system-setup.sh", "--yes", "--user", self.user)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(what, r.stderr)
        self.assertIn("como root no lo copio", r.stderr)
        for p in self.root.rglob("*"):
            if p.is_file() and not p.is_symlink():
                self.assertNotIn(b"hunter2", p.read_bytes(), p)
        self.assertEqual([c for c in self.calls() if MUTATING.match(c)], [])   # refused before any change

    def test_a_licenses_folder_swapped_for_a_link_is_refused(self):
        repo, secret = self.fake_repo()
        shutil.rmtree(repo / "assets/fonts/licenses")
        (repo / "assets/fonts/licenses").symlink_to(secret)
        self.assertRefusedAndNotCopied(repo, "«licenses» no es una carpeta normal del repo")

    def test_a_font_swapped_for_a_link_is_refused(self):
        repo, secret = self.fake_repo()
        font = repo / "assets/fonts/MartianMono-Regular.ttf"
        font.unlink()
        font.symlink_to(secret / "home-wifi.nmconnection")
        self.assertRefusedAndNotCopied(repo, "«MartianMono-Regular.ttf» no se puede abrir sin seguir enlaces")

    def test_a_cursor_alias_swapped_for_a_link_is_refused(self):
        repo, secret = self.fake_repo()
        alias = repo / "assets/cursors/ryce-peonza/cursors/left_ptr"
        alias.unlink()
        alias.symlink_to(secret / "home-wifi.nmconnection")
        self.assertRefusedAndNotCopied(repo, "«left_ptr» no se puede abrir sin seguir enlaces")

    def test_refuses_to_run_from_a_worktree(self):
        # From .worktrees/ the sandbox can write quickshell/: a planted login page would see
        # the password. Dry run, no RYCE_ROOT: the guard runs before anything is read.
        repo, _ = self.fake_repo()
        (repo / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n")
        env = {k: v for k, v in self.env.items() if k != "RYCE_ROOT"}
        r = subprocess.run(["bash", str(repo / "install/system-setup.sh"), "--dry-run", "--user", self.user],
                           env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("no es el checkout principal de git", r.stderr)

    def test_greeter_wrapper_installed_without_any_theme(self):
        self.setup()
        wrapper = self.root / "usr/local/bin/ryce-greeter"
        self.assertEqual(wrapper.read_bytes(), (REPO / "install/boot/ryce-greeter").read_bytes())
        self.assertEqual(wrapper.stat().st_mode & 0o777, 0o755)
        self.assertIn("exec tuigreet", wrapper.read_text())

    def test_subvolumes_only_when_empty_or_new(self):
        images = self.root / "var/lib/libvirt/images"
        (images / "kali.qcow2").write_text("disk")
        out = self.setup()
        self.assertEqual((images / "kali.qcow2").read_text(), "disk")
        self.assertIn("ya tiene datos", out)
        calls = self.calls()
        self.assertIn(f"btrfs subvolume create {self.root}/var/lib/docker", calls)
        self.assertIn(f"btrfs subvolume create {self.home}/.cache", calls)
        self.assertNotIn(f"btrfs subvolume create {images}", calls)
        self.assertIn(f"chattr +C {self.root}/var/lib/docker", calls)

    def test_not_btrfs_leaves_paths_alone(self):
        out = self.setup(FAKE_FSTYPE="ext4")
        self.assertIn("no en btrfs", out)
        self.assertFalse(any(c.startswith("btrfs subvolume create") for c in self.calls()))

    def test_dry_run_changes_nothing(self):
        before = tree_snapshot(self.root)
        r = self.run_script(SCRIPT, "--dry-run", "--user", self.user)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[simulación]", r.stdout)
        self.assertGreater(self.changes(r.stdout), 10)
        self.assertEqual(tree_snapshot(self.root), before)
        self.assertEqual([c for c in self.calls() if MUTATING.match(c)], [])

    def test_already_installed_packages_are_not_reinstalled(self):
        self.setup()
        installs = [c for c in self.calls() if c.startswith("pacman -S")]
        self.assertEqual(len(installs), 1)
        self.assertIn("--noconfirm", installs[0])
        self.assertIn(" hyprland", installs[0])

    def test_other_display_manager_is_not_overridden(self):
        dm = self.root / "etc/systemd/system/display-manager.service"
        dm.parent.mkdir(parents=True)
        dm.symlink_to("/usr/lib/systemd/system/sddm.service")
        out = self.setup()
        self.assertIn("sddm.service", out)
        self.assertNotIn("systemctl enable --quiet greetd.service", self.calls())

    def test_thermald_installed_is_reported(self):
        out = self.setup(FAKE_INSTALLED="thermald")
        self.assertIn("pacman -Rns thermald", out)

    def test_zswap_left_on_is_reported(self):
        (self.root / "proc/cmdline").write_text("root=/dev/nvme0n1p2 rw\n")
        self.assertIn("zswap.enabled=0", self.setup())

    def test_refuses_without_a_user(self):
        r = self.run_script(SCRIPT, "--user", "root")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usuario", r.stderr)

    def test_refuses_outside_arch(self):
        (self.root / "etc/arch-release").unlink()
        r = self.run_script(SCRIPT, "--user", self.user)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Arch", r.stderr)


if __name__ == "__main__":
    unittest.main()
