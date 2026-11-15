"""install/boot-setup.sh against a fake root (--root) whose /etc has the real machine's shapes,
with mkinitcpio, lsinitcpio, grub-*, snapper and the greeter binaries faked."""
import json
import os
import re
import shutil
import signal
import subprocess
import time
import unittest

from PIL import Image

from harness import REPO, ScriptTest, tree_snapshot

SCRIPT = REPO / "install" / "boot-setup.sh"
GREETER = REPO / "install" / "boot" / "ryce-greeter"
IMAGES = REPO / "install" / "boot" / "images.py"
GRUB_ART = REPO / "theme" / "boot" / "grub"
GREETER_ART = REPO / "theme" / "boot" / "greeter" / "background.jpg"
GREETER_ETC = REPO / "install" / "boot" / "greeter"
UWSM_MASK = "usr/local/share/wayland-sessions/hyprland-uwsm.desktop"
DROPIN = "etc/default/grub.d/ryce.cfg"
MEMTEST = "etc/grub.d/60_memtest86+-efi"
PLYMOUTH_FRAMES = json.loads((REPO / "contracts/constants.json").read_text())["peonza_assets"]["plymouth_frames"]
THEMES = sorted(p.stem for p in (REPO / "contracts/themes").glob("*.json"))

HOOKS = "HOOKS=(base udev autodetect microcode modconf kms keyboard keymap consolefont block encrypt filesystems fsck)"
MKINITCPIO = f"""\
# vim:set ft=sh
MODULES=()
BINARIES=()
FILES=()
#    HOOKS=(base udev microcode modconf keyboard keymap consolefont block mdadm_udev encrypt filesystems fsck)
#    HOOKS=(base systemd autodetect microcode modconf kms keyboard sd-vconsole block sd-encrypt filesystems fsck)
{HOOKS}
#COMPRESSION="zstd"
"""
LTS_PRESET = """\
# mkinitcpio preset file for the 'linux-lts' package

#ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/boot/vmlinuz-linux-lts"

PRESETS=('default')

#default_config="/etc/mkinitcpio.conf"
default_image="/boot/initramfs-linux-lts.img"
"""
LINUX_PRESET = LTS_PRESET.replace("-lts", "")
DEFAULT_GRUB = """\
# GRUB boot loader configuration

GRUB_DEFAULT=0
GRUB_TIMEOUT=5
GRUB_DISTRIBUTOR="Arch"
GRUB_CMDLINE_LINUX_DEFAULT="loglevel=3 quiet"
GRUB_CMDLINE_LINUX="cryptdevice=UUID=x:root root=/dev/mapper/root zswap.enabled=0"
GRUB_PRELOAD_MODULES="part_gpt part_msdos"
GRUB_TIMEOUT_STYLE=menu
GRUB_TERMINAL_INPUT=console
#GRUB_TERMINAL_OUTPUT=console
GRUB_GFXMODE=auto
GRUB_GFXPAYLOAD_LINUX=keep
GRUB_DISABLE_RECOVERY=true
#GRUB_BACKGROUND="/path/to/wallpaper"
#GRUB_THEME="/path/to/gfxtheme"
#GRUB_DISABLE_OS_PROBER=false
GRUB_TOP_LEVEL="/boot/vmlinuz-linux"
"""
PLYMOUTHD = "# Administrator customizations go in this file\n#[Daemon]\n#Theme=fade-in\n"
GREETD = """\
# Managed by ryce-pc (install/system-setup.sh): change it in the repo and re-run.
[terminal]
vt = 1

[default_session]
command = "tuigreet --time --remember --asterisks --cmd start-hyprland"
user = "greeter"

# / is on dm-crypt: the LUKS passphrase is the login.
[initial_session]
command = "start-hyprland"
user = "lameiro0x"
"""
GREETD_THEMED = """\
# Managed by ryce-pc (install/system-setup.sh): change it in the repo and re-run.
[terminal]
vt = 1

[default_session]
command = "/usr/local/bin/ryce-greeter"
user = "greeter"
"""
REGREET = '[commands]\nreboot = [ "systemctl", "reboot" ]\npoweroff = [ "systemctl", "poweroff" ]\n'

# One fake for the boot tools: logs to the harness's calls.log, and mkinitcpio "builds" an
# image that lists the hooks and the plymouth theme it would carry, so lsinitcpio can be read.
FAKE = r'''#!/usr/bin/env python3
import os, pathlib, re, sys
root = pathlib.Path(os.environ["FAKE_ROOT"])
state = pathlib.Path(os.environ["FAKE_STATE"])
name, args = os.path.basename(sys.argv[0]), sys.argv[1:]
state.mkdir(parents=True, exist_ok=True)
with open(state / "calls.log", "a") as log:
    log.write(" ".join([name] + args) + "\n")
knob = lambda k: os.environ.get(k) == "1"
def value(text, key):
    m = re.search(rf'^{key}="?([^"\n]*)"?', text, re.M)
    return m.group(1) if m else None
def build(preset):
    conf = value((root / f"etc/mkinitcpio.d/{preset}.preset").read_text(), "ALL_config") or "/etc/mkinitcpio.conf"
    hooks = re.search(r"^HOOKS=\(([^)]*)\)", (root / conf.lstrip("/")).read_text(), re.M).group(1).split()
    out = [f"hooks/{h}" for h in hooks]
    if "plymouth" in hooks:
        theme = value((root / "etc/plymouth/plymouthd.conf").read_text(), "Theme") or "bgrt"
        out += ["usr/bin/plymouthd", f"usr/share/plymouth/themes/{theme}/{theme}.script"]
    (root / f"boot/initramfs-{preset}.img").write_text("\n".join(out) + "\n")
if name == "mkinitcpio":
    if knob("FAKE_MKINITCPIO_FAIL"):
        sys.exit(1)
    for p in (["linux", "linux-lts"] if args == ["-P"] else [args[1]]):
        build(p)
elif name == "lsinitcpio":
    if knob("FAKE_LSINITCPIO_EMPTY"):
        sys.exit(0)
    sys.stdout.write(pathlib.Path(args[-1]).read_text())
elif name == "grub-mkconfig":
    if knob("FAKE_GRUB_FAIL"):
        sys.exit(1)
    out = pathlib.Path(args[args.index("-o") + 1])
    dropins = sorted((root / "etc/default/grub.d").glob("*.cfg"))
    out.write_text("# fake grub.cfg\n" + "".join(p.read_text() for p in [root / "etc/default/grub", *dropins]))
elif name == "grub-mkfont":
    out, size, n = (args[args.index(f) + 1] for f in ("-o", "-s", "-n"))
    pathlib.Path(out).write_bytes(b"FILE\0\0\0\4PFF2NAME" + f"{n} Regular {size}".encode())
elif name == "dbus-run-session":
    os.execvp(args[0], args)
elif name == "cage":
    if "FAKE_CAGE_RC" in os.environ:
        sys.exit(int(os.environ["FAKE_CAGE_RC"]))
    cmd = args[args.index("--") + 1:]
    os.execvp(cmd[0], cmd)
elif name in ("regreet", "tuigreet"):
    (state / f"{name}.env").write_text(os.environ.get("XDG_DATA_DIRS", ""))
elif name == "qs":
    # The login page: FAKE_QS=launch (beats "up", then "launch"), crash (beats, dies),
    # late (beats, dies 1.5 s later), silent (a QML error: never beats, waits to be killed).
    import time
    (state / "qs.env").write_text(" ".join(f"{k}={os.environ.get(k, '')}" for k in
                                  ("XKB_DEFAULT_LAYOUT", "XKB_DEFAULT_OPTIONS", "RYCE_GREETER_LAYOUTS",
                                   "XCURSOR_THEME", "XCURSOR_SIZE")))
    beat = pathlib.Path(os.environ["RYCE_GREETER_HEARTBEAT"])
    mode = os.environ.get("FAKE_QS", "launch")
    if mode == "silent":
        time.sleep(60)
    beat.write_text("up\n")
    if mode == "late":
        time.sleep(1.5)
    if mode in ("crash", "late"):
        sys.exit(1)
    beat.write_text("launch\n")
'''
BOOT_FAKES = ("mkinitcpio lsinitcpio grub-mkconfig grub-script-check grub-mkfont snapper fc-cache "
              "plymouth cage regreet tuigreet dbus-run-session qs").split()
MUTATING = re.compile(r"^(mkinitcpio|grub-mkconfig|snapper|fc-cache)")
GENERATED = ("boot/initramfs-linux.img", "boot/initramfs-linux-lts.img", "boot/grub/grub.cfg")


class BootSetup(ScriptTest):
    def setUp(self):
        super().setUp()
        fake = self.bin / "_boot.py"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        for name in BOOT_FAKES:
            (self.bin / name).symlink_to(fake)
        self.root = self.tmp / "root"
        files = {
            "etc/mkinitcpio.conf": MKINITCPIO,
            "etc/mkinitcpio.d/linux.preset": LINUX_PRESET,
            "etc/mkinitcpio.d/linux-lts.preset": LTS_PRESET,
            "etc/default/grub": DEFAULT_GRUB,
            "etc/plymouth/plymouthd.conf": PLYMOUTHD,
            "etc/greetd/config.toml": GREETD,
            "etc/greetd/regreet.toml": REGREET,
            "etc/snapper/configs/root": 'SUBVOLUME="/"\n',
            "etc/locale.conf": "LANG=es_ES.UTF-8\n",
            "usr/lib/plymouth/script.so": "",
            "usr/lib/tmpfiles.d/regreet.conf": "d /var/lib/regreet 0755 greeter greeter - -\n",
            "boot/grub/grub.cfg": "# grub.cfg from archinstall\n",
            "boot/initramfs-linux.img": "hooks/base\n",
            "boot/initramfs-linux-lts.img": "hooks/base\n",
            MEMTEST: "#! /bin/sh\nexec tail -n +3 $0\n",
        }
        for rel, text in files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        (self.root / MEMTEST).chmod(0o755)
        self.env.update(FAKE_ROOT=str(self.root))

    def boot(self, *args, expect=0, **env):
        r = self.run_script(SCRIPT, "--root", str(self.root), *args, env=env)
        if expect is not None:
            self.assertEqual(r.returncode, expect, r.stdout + r.stderr)
        return r

    def read(self, rel):
        return (self.root / rel).read_text()

    def mode(self, rel):
        return (self.root / rel).stat().st_mode & 0o777

    def changes(self, out):
        return int(re.search(r"Resumen: (\d+) cambios", out).group(1))

    def system(self):
        """The fake root's files minus our backups and the images/grub.cfg the fakes regenerate.
        Folders are left out: a rollback keeps the empty parents it made (/usr/local/bin…)."""
        snap = tree_snapshot(self.root)
        return {k: v for k, v in snap.items()
                if v[0] != "dir" and not k.startswith("var/backups") and k not in GENERATED}

    def test_full_run_rescue_first_then_plymouth_grub_greeter(self):
        out = self.boot("--theme", "origen").stdout
        calls = self.calls()
        order = [c for c in calls if MUTATING.match(c)]
        self.assertEqual(order[0], "snapper -c root create -d antes de ryce boot")
        self.assertLess(order.index("mkinitcpio -p linux-lts"), order.index("mkinitcpio -p linux"))
        self.assertEqual(order[-1], f"grub-mkconfig -o {self.root}/boot/grub/grub.cfg")
        self.assertIn(f"grub-script-check {self.root}/boot/grub/grub.cfg", calls)
        # rescue: the LTS image comes from the old config, without plymouth
        lts = self.read("etc/mkinitcpio-lts.conf")
        self.assertIn(MKINITCPIO, lts)
        self.assertIn(f"\n{HOOKS}\n", lts)
        preset = self.read("etc/mkinitcpio.d/linux-lts.preset")
        self.assertIn('#ALL_config="/etc/mkinitcpio.conf"\nALL_config="/etc/mkinitcpio-lts.conf"', preset)
        self.assertNotIn("plymouth", self.read("boot/initramfs-linux-lts.img"))
        # plymouth after kms, before encrypt; the theme in the image
        self.assertIn(HOOKS.replace("kms keyboard", "kms plymouth keyboard"), self.read("etc/mkinitcpio.conf"))
        self.assertIn("usr/share/plymouth/themes/ryce/ryce.script", self.read("boot/initramfs-linux.img"))
        self.assertIn("[Daemon]\nTheme=ryce\nShowDelay=0\nDeviceTimeout=8\n", self.read("etc/plymouth/plymouthd.conf"))
        ply = sorted(p.name for p in (self.root / "usr/share/plymouth/themes/ryce").iterdir())
        self.assertEqual(len([n for n in ply if n.startswith("plymouth-")]), PLYMOUTH_FRAMES)
        self.assertTrue({"ryce.plymouth", "ryce.script", "dot.png", "prompt.png"} <= set(ply))
        self.assertEqual(self.read("usr/share/plymouth/themes/ryce/ryce.script"),
                         (REPO / "themes/origen/boot/plymouth/ryce.script").read_text())
        # grub: /etc/default/grub only gains splash; the rest is the drop-in
        self.assertEqual(self.read("etc/default/grub"), DEFAULT_GRUB.replace("quiet", "quiet splash"))
        self.assertGrubMenu(calls)
        # greeter: the command changes and the autologin goes, comment included
        self.assertEqual(self.read("etc/greetd/config.toml"), GREETD_THEMED)
        self.assertGreeter()
        self.assertIn("Resumen:", out)

    def assertGreeter(self):
        """The login's fixed files: wrapper, page and its background, regreet's, the uwsm mask."""
        installed = {
            "usr/local/bin/ryce-greeter": (REPO / "install/boot/ryce-greeter", 0o755),
            "usr/share/ryce/greeter/background.jpg": (GREETER_ART, 0o644),
            "usr/local/share/ryce/greeter/background.jpg": (GREETER_ART, 0o644),
            "etc/greetd/regreet.toml": (GREETER_ETC / "regreet.toml", 0o644),
            "etc/greetd/regreet.css": (GREETER_ETC / "regreet.css", 0o644),
            UWSM_MASK: (GREETER_ETC / "hyprland-uwsm.desktop", 0o644),
        }
        for qml in (REPO / "quickshell/greeter").glob("*.qml"):
            installed[f"usr/local/share/ryce/greeter/{qml.name}"] = (qml, 0o644)
        # The cursor's XCursor half (every alias a plain copy), not its hyprcursor build.
        cursor = REPO / "assets/cursors/ryce-peonza"
        installed["usr/share/icons/ryce-peonza/index.theme"] = (cursor / "index.theme", 0o644)
        for f in (cursor / "cursors").iterdir():
            installed[f"usr/share/icons/ryce-peonza/cursors/{f.name}"] = (f, 0o644)
        for rel, (src, mode) in installed.items():
            self.assertEqual((self.root / rel).read_bytes(), src.read_bytes(), rel)
            self.assertEqual(self.mode(rel), mode, rel)
        page = sorted(p.name for p in (self.root / "usr/local/share/ryce/greeter").iterdir())
        self.assertEqual(page, sorted(k.rsplit("/", 1)[1] for k in installed if k.startswith("usr/local/share/ryce/")))
        self.assertIn("\nHidden=true\n", self.read(UWSM_MASK))
        icons = self.root / "usr/share/icons/ryce-peonza"
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in icons.rglob("*") if not p.is_dir()),
                         sorted(k for k in installed if k.startswith("usr/share/icons/")))
        self.assertFalse(any(p.is_symlink() for p in icons.rglob("*")))
        self.assertTrue((self.root / "usr/local/share/fonts/ryce/MartianMono-Regular.ttf").exists())

    def assertGrubMenu(self, calls):
        """The four-entry menu: the drop-in, memtest out, ryce's own art and its fonts."""
        dropin = self.read(DROPIN)
        for line in ('GRUB_THEME="/boot/grub/themes/ryce/theme.txt"', "GRUB_GFXMODE=1920x1080,auto",
                     "GRUB_DISABLE_SUBMENU=true", "GRUB_DISABLE_BOOTNEXT=true"):
            self.assertIn(f"\n{line}\n", dropin)
        self.assertTrue(dropin.startswith("# Managed by ryce-pc"))
        self.assertEqual(self.mode(DROPIN), 0o644)
        self.assertEqual(self.mode(MEMTEST), 0o644)
        self.assertIn("GRUB_DISABLE_SUBMENU=true", self.read("boot/grub/grub.cfg"))
        installed = self.root / "boot/grub/themes/ryce"
        for art in GRUB_ART.iterdir():
            self.assertEqual((installed / art.name).read_bytes(), art.read_bytes(), art.name)
        sizes = sorted(set(re.findall(r'"Ryce Regular (\d+)"', (GRUB_ART / "theme.txt").read_text())), key=int)
        self.assertTrue(sizes)
        self.assertEqual(sorted(p.name for p in installed.glob("*.pf2")), sorted(f"ryce-{n}.pf2" for n in sizes))
        mkfont = [c for c in calls if c.startswith("grub-mkfont")]
        self.assertEqual(len(mkfont), len(sizes))
        # root's staged copy of assets/fonts/MartianMono-Regular.ttf, never the repo's file
        self.assertTrue(all(c.endswith("/grub-face/MartianMono-Regular.ttf") and "-n Ryce" in c for c in mkfont), mkfont)

    def test_only_grub_needs_no_theme(self):
        before = self.system()
        out = self.boot("--only", "grub").stdout
        self.assertIn("ryce-pc · arranque (grub)\n", out)
        self.assertGrubMenu(self.calls())
        after = self.system()
        touched = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        self.assertEqual({k for k in touched if not k.startswith("boot/grub/themes/ryce/")}, {DROPIN})
        self.assertEqual(self.read("etc/default/grub"), DEFAULT_GRUB)
        self.assertEqual([c for c in self.calls() if c.startswith("mkinitcpio")], [])
        manifest = next((self.root / "var/backups/ryce").glob("2*/manifest")).read_text()
        self.assertIn("mode\t/etc/grub.d/60_memtest86+-efi\t755\n", manifest)
        self.assertIn("absent\t/etc/default/grub.d/ryce.cfg\n", manifest)
        # --theme is still accepted and changes nothing for GRUB
        out = self.boot("--theme", "ola", "--only", "grub").stdout
        self.assertEqual(self.changes(out), 0, out)

    def test_a_second_grub_run_leaves_grub_cfg_alone(self):
        self.boot("--only", "grub")
        n = len(self.calls())
        out = self.boot("--only", "grub").stdout
        self.assertEqual(self.changes(out), 0, out)
        self.assertIn("el test de memoria no sale en el menú", out)
        self.assertIn("/boot/grub/grub.cfg al día", out)
        self.assertEqual([c for c in self.calls()[n:] if MUTATING.match(c)], [])

    def test_grub_dry_run_prints_the_plan(self):
        before = tree_snapshot(self.root)
        out = self.boot("--only", "grub", "--dry-run").stdout
        for planned in ("[simulación] /boot/grub/themes/ryce (nuevo)",
                        "[simulación] /etc/default/grub.d/ryce.cfg (nuevo)",
                        "[simulación] /etc/grub.d/60_memtest86+-efi sin permiso de ejecución",
                        "[simulación] /boot/grub/grub.cfg (grub-mkconfig)"):
            self.assertIn(planned, out)
        self.assertEqual(self.changes(out), 4, out)
        self.assertIn(f"Para aplicarlo: pkexec bash {REPO}/install/boot-setup.sh --root {self.root} --only grub\n", out)
        self.assertEqual(tree_snapshot(self.root), before)
        self.assertEqual(self.mode(MEMTEST), 0o755)
        self.assertEqual([c for c in self.calls() if MUTATING.match(c)], [])

    def test_rollback_gives_memtest_its_mode_back(self):
        (self.root / MEMTEST).chmod(0o750)
        self.boot("--only", "grub")
        self.assertEqual(self.mode(MEMTEST), 0o640)
        out = self.boot("--rollback").stdout
        self.assertIn("devolver a /etc/grub.d/60_memtest86+-efi el modo 750", out)
        self.assertEqual(self.mode(MEMTEST), 0o750)
        self.assertFalse((self.root / DROPIN).exists())
        self.assertFalse((self.root / "boot/grub/themes/ryce").exists())
        self.assertNotIn("GRUB_DISABLE_SUBMENU", self.read("boot/grub/grub.cfg"))

    def test_without_memtest_the_menu_is_still_trimmed(self):
        (self.root / MEMTEST).unlink()
        out = self.boot("--only", "grub").stdout
        self.assertNotIn("memoria", out)
        self.assertIn("GRUB_DISABLE_BOOTNEXT=true", self.read(DROPIN))

    def test_rollback_refuses_a_bad_mode_record(self):
        self.boot("--only", "grub")
        manifest = next((self.root / "var/backups/ryce").glob("2*/manifest"))
        manifest.write_text(manifest.read_text().replace("\t755\n", "\t7;rm\n"))
        r = self.boot("--rollback", expect=1)
        self.assertIn("manifiesto ilegible", r.stderr)
        self.assertEqual(self.mode(MEMTEST), 0o644)

    def test_plymouth_prompt_is_a_picture_with_the_ene(self):
        self.boot("--theme", "grafito", "--only", "plymouth")
        script = self.read("usr/share/plymouth/themes/ryce/ryce.script")
        self.assertIn('prompt.image = Image("prompt.png");', script)
        with Image.open(self.root / "usr/share/plymouth/themes/ryce/prompt.png") as im:
            self.assertEqual(im.mode, "RGBA")
            self.assertTrue(120 < im.width < 320 and 16 < im.height < 32, im.size)
            ink = json.loads((REPO / "themes/grafito/theme.json").read_text())["colors"]["fg1"]
            self.assertEqual(im.getpixel((im.width // 2, im.height // 2))[:3],
                             tuple(int(ink[i:i + 2], 16) for i in (1, 3, 5)))

    def test_images_refuses_a_font_without_the_ene(self):
        out = self.tmp / "prompt.png"
        r = subprocess.run(["python3", str(IMAGES), "prompt", str(REPO / "themes/origen"),
                            str(REPO / "assets/fonts/RycePeonza.otf"), "0", str(out)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("ñ", r.stderr)
        self.assertFalse(out.exists())

    def test_image_text_only_ever_gets_ascii(self):
        # plymouth's label-freetype garbles non-ASCII in the initramfs (C locale): every
        # literal handed to Image.Text in the rendered scripts must be plain ASCII.
        for theme in ("origen", "grafito", "ola", "tinta"):
            script = (REPO / f"themes/{theme}/boot/plymouth/ryce.script").read_text()
            code = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))
            calls = re.findall(r"Image\.Text\s*\(([^;]*)\)\s*;", code)
            self.assertTrue(calls, theme)
            for args in calls:
                for literal in re.findall(r'"([^"]*)"', args):
                    self.assertTrue(literal.isascii(), f"{theme}: Image.Text gets {literal!r}")

    def test_second_run_changes_nothing(self):
        self.boot("--theme", "origen")
        before, n = self.system(), len(self.calls())
        out = self.boot("--theme", "origen").stdout
        self.assertEqual(self.changes(out), 0, out)
        self.assertEqual([c for c in self.calls()[n:] if MUTATING.match(c)], [])
        self.assertEqual(self.system(), before)
        self.assertEqual(len(list((self.root / "var/backups/ryce").glob("2*"))), 1)

    def test_hook_and_splash_are_never_duplicated(self):
        (self.root / "etc/mkinitcpio.conf").write_text(MKINITCPIO.replace("kms keyboard", "kms plymouth keyboard"))
        (self.root / "etc/default/grub").write_text(DEFAULT_GRUB.replace("quiet", "quiet splash"))
        self.boot("--theme", "origen")
        self.boot("--theme", "grafito")
        hooks = re.search(r"^HOOKS=\((.*)\)", self.read("etc/mkinitcpio.conf"), re.M).group(1).split()
        self.assertEqual(hooks.count("plymouth"), 1)
        self.assertEqual(self.read("etc/default/grub").count("splash"), 1)
        self.assertNotIn("plymouth", self.read("etc/mkinitcpio-lts.conf").split("HOOKS=(")[-1].split(")")[0])

    def test_dry_run_changes_nothing(self):
        before = tree_snapshot(self.root)
        r = self.boot("--theme", "origen", "--dry-run")
        self.assertIn("[simulación]", r.stdout)
        self.assertGreater(self.changes(r.stdout), 10)
        self.assertEqual(tree_snapshot(self.root), before)
        self.assertEqual(self.mode(MEMTEST), 0o755)
        self.assertEqual([c for c in self.calls() if MUTATING.match(c)], [])

    def test_image_without_the_theme_restores_mkinitcpio_conf(self):
        r = self.boot("--theme", "origen", expect=1, FAKE_LSINITCPIO_EMPTY="1")
        self.assertIn("lsinitcpio no encuentra el tema", r.stderr)
        self.assertEqual(self.read("etc/mkinitcpio.conf"), MKINITCPIO)
        self.assertEqual(self.read("etc/plymouth/plymouthd.conf"), PLYMOUTHD)
        self.assertFalse((self.root / "usr/share/plymouth/themes/ryce").exists())
        self.assertNotIn("plymouth", self.read("boot/initramfs-linux.img"))
        self.assertEqual([c for c in self.calls() if c.startswith("mkinitcpio")],
                         ["mkinitcpio -p linux-lts", "mkinitcpio -p linux", "mkinitcpio -p linux"])
        self.assertEqual(self.read("etc/default/grub"), DEFAULT_GRUB)   # GRUB comes after: untouched
        self.assertFalse(any(c.startswith("grub-mkconfig") for c in self.calls()))

    def test_failed_grub_cfg_restores_default_grub(self):
        r = self.boot("--theme", "origen", "--only", "grub", expect=1, FAKE_GRUB_FAIL="1")
        self.assertIn("no se pudo generar grub.cfg", r.stderr)
        self.assertEqual(self.read("etc/default/grub"), DEFAULT_GRUB)
        self.assertFalse((self.root / DROPIN).exists())
        self.assertEqual(self.mode(MEMTEST), 0o755)
        self.assertEqual(self.read("boot/grub/grub.cfg"), "# grub.cfg from archinstall\n")

    def test_rollback_restores_every_file_byte_for_byte(self):
        pristine = self.system()
        self.boot("--theme", "ola")
        self.assertNotEqual(self.system(), pristine)
        n = len(self.calls())
        out = self.boot("--rollback").stdout
        self.assertEqual(self.system(), pristine)
        self.assertEqual(self.mode(MEMTEST), 0o755)
        self.assertIn("mkinitcpio -P", self.calls()[n:])
        self.assertIn(f"grub-mkconfig -o {self.root}/boot/grub/grub.cfg", self.calls()[n:])
        self.assertNotIn("plymouth", self.read("boot/initramfs-linux.img"))
        self.assertIn("quitar /etc/mkinitcpio-lts.conf", out)
        sets = [p.name for p in (self.root / "var/backups/ryce").iterdir() if not p.name.startswith(".")]
        self.assertEqual(len(sets), 1)
        self.assertTrue(sets[0].endswith(".restored"))
        r = self.boot("--rollback", expect=1)
        self.assertIn("no hay nada que deshacer", r.stderr)

    def test_rollback_after_a_theme_switch_returns_to_the_first_theme(self):
        self.boot("--theme", "origen")
        first = self.system()
        self.boot("--theme", "grafito")
        self.assertNotEqual(self.system(), first)
        self.boot("--rollback")
        self.assertEqual(self.system(), first)

    def test_rollback_refuses_a_manifest_outside_its_targets(self):
        self.boot("--only", "greeter")
        manifest = next((self.root / "var/backups/ryce").glob("2*/manifest"))
        manifest.write_text(manifest.read_text() + "absent\t/etc/passwd\n")
        r = self.boot("--rollback", expect=1)
        self.assertIn("/etc/passwd", r.stderr)
        self.assertTrue((self.root / "usr/local/bin/ryce-greeter").exists())

    def test_rollback_never_leaves_greetd_without_its_greeter(self):
        cfg = GREETD.replace('"tuigreet --time --remember --asterisks --cmd start-hyprland"', '"/usr/local/bin/ryce-greeter"')
        (self.root / "etc/greetd/config.toml").write_text(cfg)   # system-setup.sh, before the wrapper existed
        self.boot("--only", "greeter")
        out = self.boot("--rollback").stdout
        self.assertEqual(self.read("etc/greetd/config.toml"), cfg)
        self.assertTrue((self.root / "usr/local/bin/ryce-greeter").exists())
        self.assertIn("lo dejo instalado", out)

    def test_only_greeter_needs_no_theme_and_touches_only_greeter_files(self):
        spool = self.root / "var/lib/ryce/greeter"   # the retired theme spool: left as it is
        spool.mkdir(parents=True)
        (spool / "theme.json").write_text("{}\n")
        before = self.system()
        out = self.boot("--only", "greeter").stdout
        self.assertIn("ryce-pc · arranque (greeter)\n", out)
        self.assertGreeter()
        after = self.system()
        touched = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        outside = [k for k in touched if not k.startswith(("etc/greetd/", "usr/local/", "usr/share/ryce/",
                                                            "usr/share/icons/ryce-peonza/"))]
        self.assertEqual(outside, [])
        self.assertEqual([c for c in self.calls() if c.startswith(("mkinitcpio", "grub-"))], [])
        self.assertNotIn("initial_session", self.read("etc/greetd/config.toml"))
        manifest = next((self.root / "var/backups/ryce").glob("2*/manifest")).read_text()
        self.assertIn(f"absent\t/{UWSM_MASK}\n", manifest)
        self.assertIn("saved\t/etc/greetd/regreet.toml\n", manifest)
        # the theme changes nothing for the login, and a second run nothing at all
        for args in ((), ("--theme", "ola")):
            out = self.boot(*args, "--only", "greeter").stdout
            self.assertEqual(self.changes(out), 0, out)
        self.assertEqual(self.system(), after)

    def test_root_takes_back_login_files_with_the_right_content(self):
        # main's first install copied them with `cp -a` out of the repo: the user's. Equal
        # content must not hide a wrapper a user process could rewrite.
        self.boot("--only", "greeter")
        wrapper = self.root / "usr/local/bin/ryce-greeter"
        page = self.root / "usr/local/share/ryce/greeter"
        (self.root / "etc/greetd/regreet.css").chmod(0o664)
        self.foreign_owner(wrapper, page / "shell.qml")
        n = len(self.calls())
        out = self.boot("--only", "greeter").stdout
        for rel in ("/usr/local/bin/ryce-greeter", "/usr/local/share/ryce/greeter", "/etc/greetd/regreet.css"):
            self.assertIn(f"{rel}: de root y con su modo (el contenido ya estaba)", out)
        self.assertEqual(self.mode("etc/greetd/regreet.css"), 0o644)
        me = f"{os.getuid()}:{os.getgid()}"
        calls = self.calls()[n:]
        self.assertIn(f"chown -R {me} {wrapper}.ryce-new", calls)
        self.assertIn(f"chown -R {me} {page}.ryce-new", calls)
        self.assertNotIn("/etc/greetd/regreet.toml: de root", out)   # right owner and mode: left alone

    def test_rollback_hands_restored_files_to_root(self):
        self.boot("--only", "greeter")
        n = len(self.calls())
        self.boot("--rollback")
        me = f"{os.getuid()}:{os.getgid()}"
        calls = self.calls()[n:]
        for rel in ("etc/greetd/config.toml", "etc/greetd/regreet.toml"):   # saved, so restored
            self.assertIn(f"chown -R {me} {self.root}/{rel}", calls)
        self.assertFalse([c for c in calls if c.startswith("chown") and "/boot/" in c])

    def test_greeter_dry_run_prints_the_plan(self):
        before = tree_snapshot(self.root)
        out = self.boot("--only", "greeter", "--dry-run").stdout
        for planned in ("/usr/local/bin/ryce-greeter (nuevo)", "/usr/local/share/ryce/greeter (nuevo)",
                        "/usr/share/ryce/greeter (nuevo)", "/etc/greetd/regreet.toml",
                        "/etc/greetd/regreet.css (nuevo)", f"/{UWSM_MASK} (nuevo)", "/etc/greetd/config.toml"):
            self.assertIn(f"[simulación] {planned}\n", out)
        self.assertEqual(tree_snapshot(self.root), before)

    def test_rollback_restores_the_login_as_it_was(self):
        page = self.root / "usr/local/share/ryce/greeter"   # system-setup.sh's older page
        page.mkdir(parents=True)
        (page / "shell.qml").write_text("ShellRoot {}\n")
        (self.root / "usr/share/ryce/greeter").mkdir(parents=True)
        (self.root / "usr/share/ryce/greeter/background.jpg").write_bytes(b"old lock art")
        pristine = self.system()
        self.boot("--only", "greeter")
        self.assertNotEqual(self.system(), pristine)
        out = self.boot("--rollback").stdout
        self.assertIn(f"quitar /{UWSM_MASK} (lo creó este script)", out)
        self.assertIn("restaurar /usr/local/share/ryce/greeter", out)
        self.assertEqual(self.system(), pristine)
        self.assertNotIn(f"grub-mkconfig -o {self.root}/boot/grub/grub.cfg", self.calls())

    def test_autologin_between_sections_goes_alone(self):
        (self.root / "etc/greetd/config.toml").write_text(GREETD + "\n[extra]\nkey = 1\n")
        self.boot("--only", "greeter")
        self.assertEqual(self.read("etc/greetd/config.toml"), GREETD_THEMED + "\n[extra]\nkey = 1\n")

    def test_refusals(self):
        r = self.boot("--theme", "nope", expect=1)
        self.assertIn("no conozco el tema", r.stderr)
        for parts in ([], ["--only", "plymouth"], ["--only", "greeter", "--only", "plymouth"]):
            r = self.boot(*parts, expect=1)
            self.assertIn("falta --theme", r.stderr)
        r = self.boot("--rollback", "--theme", "origen", expect=1)
        self.assertIn("--rollback no admite", r.stderr)
        r = self.boot("--theme", "origen", "--only", "kernel", expect=1)
        self.assertIn("plymouth, grub o greeter", r.stderr)
        (self.root / "etc/mkinitcpio.d/linux-lts.preset").unlink()
        r = self.boot("--theme", "origen", expect=1)
        self.assertIn("linux-lts", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_multiline_hooks_stop_before_any_change(self):
        (self.root / "etc/mkinitcpio.conf").write_text("HOOKS=(base udev\n  kms block encrypt)\n")
        before = self.system()
        r = self.boot("--theme", "origen", "--only", "plymouth", expect=1)
        self.assertIn("varias líneas", r.stderr)
        self.assertEqual(self.system(), before)
        self.assertEqual([c for c in self.calls() if MUTATING.match(c)], [])

    def test_frame_count_matches_the_contract(self):
        self.assertIn(f"FRAMES={PLYMOUTH_FRAMES} ", SCRIPT.read_text())
        for theme in THEMES:
            self.assertIn(f"FRAMES = {PLYMOUTH_FRAMES};", (REPO / f"themes/{theme}/boot/plymouth/ryce.script").read_text())

    def test_one_frame_per_refresh_over_the_period(self):
        # The splash advances one frame per refresh call, so the call rate times the brand's
        # think period (1.2 s) is the frame count: the turn keeps its speed.
        for theme in THEMES:
            script = (REPO / f"themes/{theme}/boot/plymouth/ryce.script").read_text()
            rate = int(re.search(r"^Plymouth\.SetRefreshRate\((\d+)\);$", script, re.M).group(1))
            self.assertEqual(rate * 12, PLYMOUTH_FRAMES * 10, theme)
            self.assertIn("peonza.frame = (peonza.frame + 1) % FRAMES;", script)


class Greeter(ScriptTest):
    """install/boot/ryce-greeter: ryce's page in cage, then regreet in cage, then tuigreet."""

    def setUp(self):
        super().setUp()
        fake = self.bin / "_boot.py"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        self.env.update(FAKE_ROOT=str(self.tmp), XDG_RUNTIME_DIR=str(self.tmp), RYCE_GREETER_WAIT="1",
                        RYCE_GREETER_SETTLE="1")
        for name in ("cage", "qs", "regreet", "tuigreet"):
            (self.bin / name).symlink_to(fake)
        # The fakes plus what the wrapper itself runs, never the machine's own cage or
        # dbus-run-session.
        tools = self.tmp / "tools"
        tools.mkdir()
        for name in ("env", "python3", "mktemp", "sleep", "cat", "rm"):
            (tools / name).symlink_to(shutil.which(name))
        self.env["PATH"] = f"{self.bin}:{tools}"
        self.qml = self.tmp / "qml"
        self.qml.mkdir()
        (self.qml / "shell.qml").write_text("ShellRoot {}\n")
        self.env["RYCE_GREETER_QML"] = str(self.qml)

    def greet(self, **env):
        r = subprocess.run([shutil.which("bash"), str(GREETER)], env={**self.env, **env},
                           capture_output=True, text=True, timeout=30)
        return r, [c.split()[0] for c in self.calls()]

    def test_the_page_hands_over_the_session(self):
        r, calls = self.greet(FAKE_QS="launch")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(calls, ["cage", "qs"])
        self.assertIn(f"cage -s -m last -d -- qs -p {self.qml}", self.calls())
        # the desktop's keyboard: the password was typed with the US map
        self.assertEqual((self.state / "qs.env").read_text(),
                         "XKB_DEFAULT_LAYOUT=us,es XKB_DEFAULT_OPTIONS=ctrl:nocaps,grp:alt_shift_toggle "
                         "RYCE_GREETER_LAYOUTS=us,es XCURSOR_THEME=ryce-peonza XCURSOR_SIZE=32")
        self.assertEqual(list(self.tmp.glob("ryce-greeter.*")), [])   # its heartbeat dir is gone

    def test_no_heartbeat_falls_back_to_regreet(self):
        # A QML error leaves quickshell running with nothing on screen: it never beats.
        r, calls = self.greet(FAKE_QS="silent")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(calls, ["cage", "qs", "cage", "regreet"])
        self.assertIn("no ha dado señales en 1 s; uso regreet", r.stderr)
        self.assertIn("cage -s -m last -d -- regreet", self.calls())

    def test_a_page_that_dies_early_falls_back_to_regreet(self):
        r, calls = self.greet(FAKE_QS="crash")
        self.assertEqual(calls, ["cage", "qs", "cage", "regreet"])
        self.assertIn("salió con 1", r.stderr)

    def test_a_page_that_dies_late_without_launch_falls_back_to_regreet(self):
        # Restarting it would loop forever on a page that keeps dying after GRACE.
        r, calls = self.greet(FAKE_QS="late", RYCE_GREETER_GRACE="1")
        self.assertEqual(calls, ["cage", "qs", "cage", "regreet"])
        self.assertIn("sin abrir sesión; uso regreet", r.stderr)

    def test_sessions_are_read_from_usr_local_first(self):
        # where the mask hides «Hyprland (uwsm-managed)»
        (self.qml / "shell.qml").unlink()
        self.greet()
        self.assertEqual((self.state / "regreet.env").read_text(), "/usr/local/share:/usr/share")
        self.greet(FAKE_CAGE_RC="1")
        self.assertEqual((self.state / "tuigreet.env").read_text(), "/usr/local/share:/usr/share")

    def test_cage_crashing_after_a_login_never_shows_tuigreet(self):
        # cage 0.3.1 segfaults (139) when regreet exits after starting a session; greetd then
        # SIGTERMs the greeter within 5 s. The wrapper must still be waiting when that comes.
        (self.qml / "shell.qml").unlink()
        p = subprocess.Popen([shutil.which("bash"), str(GREETER)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env={**self.env, "FAKE_CAGE_RC": "139", "RYCE_GREETER_SETTLE": "5"})
        self.addCleanup(p.kill)
        deadline = time.monotonic() + 10
        while not any(c.endswith("-- regreet") for c in self.calls()):
            self.assertLess(time.monotonic(), deadline, "cage never ran regreet")
            time.sleep(0.05)
        time.sleep(0.5)   # cage has exited 139 by now
        p.send_signal(signal.SIGTERM)   # greetd, 5 s after the session started
        p.communicate(timeout=10)
        self.assertEqual(p.returncode, -signal.SIGTERM)
        self.assertNotIn("tuigreet", [c.split()[0] for c in self.calls()])

    def test_cage_crashing_with_nobody_ending_us_falls_to_tuigreet(self):
        # regreet really failed: no session, so nobody ends the wrapper during the wait
        (self.qml / "shell.qml").unlink()
        start = time.monotonic()
        r, calls = self.greet(FAKE_CAGE_RC="139")
        self.assertEqual(calls, ["cage", "tuigreet"])
        self.assertGreaterEqual(time.monotonic() - start, 1)   # after the settle wait
        self.assertIn("regreet salió con 139", r.stderr)

    def test_without_quickshell_or_its_files_regreet(self):
        (self.qml / "shell.qml").unlink()
        r, calls = self.greet()
        self.assertEqual(calls, ["cage", "regreet"])
        self.assertIn("falta cage, quickshell o", r.stderr)
        self.drop_fake("qs")
        (self.qml / "shell.qml").write_text("ShellRoot {}\n")
        r, calls = self.greet()
        self.assertEqual(calls[-2:], ["cage", "regreet"])

    def test_quick_failure_falls_back_to_tuigreet(self):
        r, calls = self.greet(FAKE_CAGE_RC="1")
        self.assertEqual(calls, ["cage", "cage", "tuigreet"])
        self.assertIn("--cmd start-hyprland", self.calls()[-1])

    def test_missing_cage_falls_back_to_tuigreet(self):
        self.drop_fake("cage")
        r, calls = self.greet()
        self.assertEqual(calls, ["tuigreet"])
        self.assertIn("falta cage o regreet", r.stderr)


if __name__ == "__main__":
    unittest.main()
