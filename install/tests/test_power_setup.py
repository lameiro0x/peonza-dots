"""install/power-setup.sh (hibernation) against a fake root (--root): every system command it
calls is one fake below, which keeps mounts, swaps, units and subvolumes in a JSON state file,
"builds" initramfs images that list their hooks, and "generates" a grub.cfg whose kernel lines
carry the command line the real grub-mkconfig would compute from /etc/default/grub + grub.d."""
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import tempfile
import unittest

from harness import REPO, ScriptTest

SCRIPT = REPO / "install" / "power-setup.sh"
EDIT = REPO / "install" / "boot" / "edit.py"
MARK = "# Managed by ryce-pc (install/power-setup.sh): change it in the repo and re-run."
UUID = "d1d22648-dcf2-4ce1-be7c-f7c4f858388d"
LOGIND = "etc/systemd/logind.conf.d/ryce-power.conf"
SLEEP = "etc/systemd/sleep.conf.d/ryce-sleep.conf"
NOBEEP = "etc/modprobe.d/ryce-nobeep.conf"
MOUNT = "etc/systemd/system/swap.mount"
SWAP = "etc/systemd/system/swap-swapfile.swap"
GRUBD = "etc/default/grub.d/ryce-resume.cfg"
GUARD_UNIT = "etc/systemd/system/systemd-hibernate.service.d/ryce-guard.conf"
GUARD_BIN = "usr/local/lib/ryce/hibernate-guard"
OURS = (LOGIND, SLEEP, NOBEEP, MOUNT, SWAP, GRUBD, GUARD_UNIT, GUARD_BIN)
HOOKS = ("HOOKS=(base udev autodetect microcode modconf kms plymouth keyboard keymap consolefont "
         "block encrypt filesystems fsck)")
LTS_HOOKS = HOOKS.replace(" plymouth", "")
MAIN_CONF = f"# vim:set ft=sh\nMODULES=()\n{HOOKS}\n#HOOKS=(old)\n"
LTS_CONF = f"# managed by boot-setup\n{LTS_HOOKS}\n"
OLD_GRUB = "# grub.cfg from boot-setup\n"
# A bzImage carries "<release> (<builder>) #1 ..." in plain text in its setup header.
VMLINUZ = f"MZ\x00HdrS {platform.release()} (builder@host) #1 SMP\x00junk"
UPDATED = "MZ\x00HdrS 9.9.9-arch1-1 (builder@host) #1 SMP\x00"

def tree_snapshot(root):
    """{relative path: (kind, content)}; the (sparse, 31 GiB) swapfile by size only."""
    out = {}
    for p in sorted(pathlib.Path(root).rglob("*")):
        rel = str(p.relative_to(root))
        if p.is_symlink():
            out[rel] = ("link", os.readlink(p))
        elif p.is_dir():
            out[rel] = ("dir", None)
        elif rel == "swap/swapfile":
            out[rel] = ("swap", p.stat().st_size)
        else:
            out[rel] = ("file", p.read_bytes())
    return out


FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, re, subprocess, sys
root = pathlib.Path(os.environ["FAKE_ROOT"])
state = pathlib.Path(os.environ["FAKE_STATE"])
name, args = os.path.basename(sys.argv[0]), sys.argv[1:]
state.mkdir(parents=True, exist_ok=True)
with open(state / "calls.log", "a") as log:
    log.write(" ".join([name] + [a.replace(str(root), "") for a in args]) + "\n")
db = state / "power.json"
st = json.loads(db.read_text()) if db.exists() else {"mounts": [], "swaps": [], "active": [],
                                                       "enabled": [], "subvols": []}
def save(): db.write_text(json.dumps(st))
def knob(k): return os.environ.get(k) == "1"
rc = 0
if name == "findmnt":
    if "FSTYPE" in args: print("btrfs")
    elif "UUID" in args: print(os.environ["FAKE_UUID"])
    elif "SOURCE" in args: print("/dev/mapper/root")
elif name == "mount":
    st["mounts"].append(args[-1]); save()
    (pathlib.Path(args[-1]) / "canary").write_text("the whole btrfs lives here\n")
elif name == "umount":
    if knob("FAKE_UMOUNT_FAIL"):
        print("umount: target is busy.", file=sys.stderr); sys.exit(32)
    (pathlib.Path(args[-1]) / "canary").unlink(missing_ok=True)
    st["mounts"] = [m for m in st["mounts"] if m != args[-1]]; save()
elif name == "mountpoint":
    rc = 0 if args[-1] in st["mounts"] else 1
elif name == "btrfs":
    if args[:2] == ["subvolume", "show"]:
        rc = 0 if os.path.basename(args[2]) in st["subvols"] else 1
    elif args[:2] == ["subvolume", "create"]:
        st["subvols"].append(os.path.basename(args[2])); save()
    elif args[:2] == ["subvolume", "delete"]:
        st["subvols"] = [s for s in st["subvols"] if s != os.path.basename(args[2])]; save()
    elif args[:2] == ["filesystem", "mkswapfile"]:
        gib = int(args[args.index("--size") + 1].rstrip("g"))
        with open(args[-1], "wb") as f:          # sparse, with a real swap signature
            f.truncate(gib << 30); f.seek(4086); f.write(b"SWAPSPACE2")
    elif args[:2] == ["inspect-internal", "map-swapfile"]:
        print(os.environ.get("FAKE_OFFSET", "533760"))
elif name == "swapon":
    print("\n".join(st["swaps"]))
elif name == "systemctl":
    verb, units = args[0], [a for a in args[1:] if not a.startswith("-")]
    if verb == "is-active":
        rc = 0 if units[0] in st["active"] else 3
    elif verb in ("enable", "start"):
        for u in units:
            st["enabled"].append(u)
            if "--now" in args or verb == "start":
                st["active"].append(u)
                if u == "swap.mount":
                    (root / "swap").mkdir(exist_ok=True); st["mounts"].append(str(root / "swap"))
                if u == "swap-swapfile.swap":
                    st["swaps"].append("/swap/swapfile")
        save()
    elif verb == "disable":
        if knob("FAKE_SWAPOFF_FAIL") and "swap-swapfile.swap" in units:
            sys.exit(1)
        for u in units:
            st["enabled"] = [e for e in st["enabled"] if e != u]
            st["active"] = [e for e in st["active"] if e != u]
            if u == "swap.mount":
                st["mounts"] = [m for m in st["mounts"] if m != str(root / "swap")]
            if u == "swap-swapfile.swap":
                st["swaps"] = [s for s in st["swaps"] if s != "/swap/swapfile"]
        save()
elif name == "mkinitcpio":
    if knob("FAKE_MKINITCPIO_FAIL"):
        sys.exit(1)
    for conf, img in (("etc/mkinitcpio.conf", "boot/initramfs-linux.img"),
                      ("etc/mkinitcpio-lts.conf", "boot/initramfs-linux-lts.img")):
        m = re.search(r"^HOOKS=\(([^)]*)\)", (root / conf).read_text(), re.M)
        hooks = m.group(1).split() if m else []
        (root / img).write_text("\n".join(f"hooks/{h}" for h in hooks if h not in ("filesystems", "fsck")) + "\n")
elif name == "lsinitcpio":
    if knob("FAKE_LSINITCPIO_EMPTY"):
        sys.exit(0)
    print(pathlib.Path(args[-1]).read_text(), end="")
elif name == "grub-mkconfig":
    if knob("FAKE_GRUB_FAIL"):
        sys.exit(1)
    srcs = [root / "etc/default/grub", *sorted((root / "etc/default/grub.d").glob("*.cfg"))]
    line = subprocess.run(["bash", "-c", "".join(f'. "{p}"; ' for p in srcs) +
                           'printf %s "$GRUB_CMDLINE_LINUX $GRUB_CMDLINE_LINUX_DEFAULT"'],
                          capture_output=True, text=True, check=True).stdout
    out = ["# fake grub.cfg"]
    for k in ("linux", "linux-lts"):
        out.append(f"menuentry '{k}' {{\n\tlinux /vmlinuz-{k} root=UUID=x rw {line}\n}}")
    if knob("FAKE_GRUB_STRIP"):
        out.append("menuentry 'snap' {\n\tlinux /vmlinuz-linux root=UUID=x rw quiet\n}")
    pathlib.Path(args[args.index("-o") + 1]).write_text("\n".join(out) + "\n")
elif name == "grub-script-check":
    rc = 1 if knob("FAKE_GRUB_CHECK_FAIL") else 0
elif name == "loginctl":
    print("1000 someone no active")
sys.exit(rc)
'''
FAKES = ("findmnt mount umount mountpoint btrfs swapon systemctl mkinitcpio lsinitcpio "
         "grub-mkconfig grub-script-check modprobe loginctl systemd-run").split()
MUTATING = re.compile(r"^(mkinitcpio|grub-mkconfig|btrfs (subvolume (create|delete)|filesystem)|"
                      r"systemctl (enable|disable|reload|daemon-reload|hibernate)|modprobe|mount )")


class PowerSetup(ScriptTest):
    def setUp(self):
        super().setUp()
        fake = self.bin / "_power.py"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        for name in FAKES:
            link = self.bin / name
            if link.is_symlink():
                link.unlink()
            link.symlink_to(fake)
        self.root = self.tmp / "root"
        files = {
            "etc/mkinitcpio.conf": MAIN_CONF,
            "etc/mkinitcpio-lts.conf": LTS_CONF,
            "etc/default/grub": 'GRUB_CMDLINE_LINUX_DEFAULT="quiet"\n'
                                'GRUB_CMDLINE_LINUX="cryptdevice=UUID=c:root rootfstype=btrfs"\n',
            "etc/default/grub.d/ryce.cfg": "# boot-setup\nGRUB_CMDLINE_LINUX_DEFAULT=\"loglevel=3 quiet splash\"\n",
            "boot/grub/grub.cfg": OLD_GRUB,
            "boot/vmlinuz-linux": VMLINUZ,
            "boot/vmlinuz-linux-lts": "MZ\x00HdrS 6.18.60-1-lts (builder@host) #1 SMP\x00",
            "proc/meminfo": "MemTotal:       32237456 kB\n",
            "proc/cmdline": "BOOT_IMAGE=/vmlinuz-linux root=UUID=x rw quiet\n",
        }
        for rel, text in files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        (self.root / "sys/module/pcspkr").mkdir(parents=True)
        self.env.update(FAKE_ROOT=str(self.root), FAKE_UUID=UUID)
        # The images exist from before (boot-setup built them), without resume.
        subprocess.run([str(self.bin / "mkinitcpio"), "-P"], env=self.env, check=True, timeout=30)
        (self.state / "calls.log").unlink()

    def go(self, *args, **env):
        return self.run_script(SCRIPT, "--root", str(self.root), *args, env=env or None)

    def text(self, rel):
        return (self.root / rel).read_text()

    def mutating(self):
        return [c for c in self.calls() if MUTATING.match(c)]

    def system(self):
        """The fake root minus the backups (a run may add those and still change nothing)."""
        return {k: v for k, v in tree_snapshot(self.root).items() if not k.startswith("var/backups")}

    def hooks(self, rel):
        m = re.search(r"^HOOKS=\(([^)]*)\)", self.text(rel), re.M)
        return m.group(1).split() if m else []

    def forget_calls(self):
        (self.state / "calls.log").unlink(missing_ok=True)

    # --- apply ----------------------------------------------------------------------------------
    def test_apply_sets_up_every_piece(self):
        r = self.go()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("HandlePowerKey=hibernate", self.text(LOGIND).splitlines())
        self.assertIn("HandleSuspendKey=hibernate", self.text(LOGIND).splitlines())
        self.assertIn("AllowSuspend=no", self.text(SLEEP).splitlines())
        self.assertNotIn("MemorySleepMode", self.text(SLEEP))
        self.assertIn(f"What=/dev/disk/by-uuid/{UUID}", self.text(MOUNT).splitlines())
        self.assertIn("Options=subvol=/@swap,noatime", self.text(MOUNT).splitlines())
        self.assertIn("Priority=-2", self.text(SWAP).splitlines())
        self.assertIn('resume=/dev/mapper/root resume_offset=533760"', self.text(GRUBD))
        self.assertIn(f"ExecStartPre=/{GUARD_BIN}", self.text(GUARD_UNIT).splitlines())
        for rel in OURS:
            self.assertIn(MARK, self.text(rel).splitlines()[:2], rel)
            want = "0o755" if rel == GUARD_BIN else "0o644"
            self.assertEqual(oct((self.root / rel).stat().st_mode & 0o777), want, rel)
        for conf in ("etc/mkinitcpio.conf", "etc/mkinitcpio-lts.conf"):
            h = self.hooks(conf)
            self.assertEqual(h.index("resume"), h.index("encrypt") + 1, conf)
        self.assertIn("#HOOKS=(old)", self.text("etc/mkinitcpio.conf"))
        for img in ("boot/initramfs-linux.img", "boot/initramfs-linux-lts.img"):
            self.assertIn("hooks/resume", self.text(img).splitlines(), img)
        kernels = [l for l in self.text("boot/grub/grub.cfg").splitlines() if l.strip().startswith("linux ")]
        self.assertEqual(len(kernels), 2)
        for line in kernels:
            self.assertIn("resume=/dev/mapper/root resume_offset=533760", line)
            self.assertIn("cryptdevice=UUID=c:root", line)
            self.assertIn("splash", line)
        self.assertIn("btrfs filesystem mkswapfile --size 31g --uuid clear /swap/swapfile", self.calls())
        self.assertIn("@swap", json.loads((self.state / "power.json").read_text())["subvols"])
        self.assertFalse((self.root / "boot/grub/grub.cfg.ryce-new").exists())

    def test_order_swap_on_only_once_the_boot_can_read_it_button_last(self):
        self.go()
        calls = self.calls()
        idx = lambda prefix: next(i for i, c in enumerate(calls) if c.startswith(prefix))
        self.assertLess(idx("systemctl enable --now swap.mount"), idx("btrfs filesystem mkswapfile"))
        self.assertLess(idx("btrfs filesystem mkswapfile"), idx("mkinitcpio -P"))
        self.assertLess(idx("mkinitcpio -P"), idx("grub-mkconfig"))
        self.assertLess(idx("grub-mkconfig"), idx("systemctl enable --now swap-swapfile.swap"))
        self.assertLess(idx("systemctl enable --now swap-swapfile.swap"), idx("systemctl reload systemd-logind"))
        self.assertEqual(calls[-1], "systemctl reload systemd-logind")

    def test_a_stuck_top_level_mount_is_never_deleted_through(self):
        r = self.go(FAKE_UMOUNT_FAIL="1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("sigue montado", r.stderr)
        top = next(c.split()[-1] for c in self.calls() if c.startswith("mount -o subvolid=5"))
        self.addCleanup(shutil.rmtree, top, ignore_errors=True)
        self.assertTrue((pathlib.Path(top) / "canary").exists())
        self.assertFalse(str(top).startswith(str(self.root)))

    def test_a_half_made_swapfile_is_made_again(self):
        self.go()
        st = json.loads((self.state / "power.json").read_text())
        st["swaps"] = []
        (self.state / "power.json").write_text(json.dumps(st))
        os.truncate(self.root / "swap/swapfile", 4096)
        self.forget_calls()
        r = self.go()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("btrfs filesystem mkswapfile --size 31g --uuid clear /swap/swapfile", self.calls())
        self.assertEqual((self.root / "swap/swapfile").stat().st_size, 31 << 30)

    def test_second_run_changes_nothing(self):
        self.go()
        before = self.system()
        self.forget_calls()
        r = self.go()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("==> 0 cambios", r.stdout)
        self.assertEqual(self.system(), before)
        self.assertEqual(self.mutating(), [])

    def test_dry_run_changes_nothing(self):
        before = tree_snapshot(self.root)
        r = self.go("--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[simulación]", r.stdout)
        self.assertEqual(tree_snapshot(self.root), before)
        self.assertEqual(self.mutating(), [])

    def test_a_moved_swapfile_rewrites_the_offset_everywhere(self):
        self.go()
        self.forget_calls()
        r = self.go(FAKE_OFFSET="999424")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("resume_offset=999424", self.text(GRUBD))
        self.assertIn("grub-mkconfig -o /boot/grub/grub.cfg.ryce-new", self.calls())
        self.assertEqual(self.text("boot/grub/grub.cfg").count("resume_offset=999424"), 2)

    # --- failures leave the button alone ----------------------------------------------------------
    def assert_button_untouched(self):
        """A failure midway leaves nothing that can hibernate: no button, and no active swap
        (the lock screen and the keybind call systemctl hibernate on their own)."""
        self.assertFalse((self.root / LOGIND).exists())
        self.assertNotIn("systemctl reload systemd-logind", self.calls())
        self.assertNotIn("systemctl enable --now swap-swapfile.swap", self.calls())
        self.assertEqual(json.loads((self.state / "power.json").read_text())["swaps"], [])

    def test_failed_initramfs_restores_the_configs(self):
        r = self.go(FAKE_MKINITCPIO_FAIL="1")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.text("etc/mkinitcpio.conf"), MAIN_CONF)
        self.assertEqual(self.text("etc/mkinitcpio-lts.conf"), LTS_CONF)
        self.assertEqual(self.text("boot/grub/grub.cfg"), OLD_GRUB)
        self.assert_button_untouched()
        self.assertIn("AllowSuspend=no", self.text(SLEEP))   # the safety net stays

    def test_an_image_without_the_hook_is_a_failure(self):
        r = self.go(FAKE_LSINITCPIO_EMPTY="1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no lleva el hook resume", r.stderr)
        self.assertNotIn("resume", self.hooks("etc/mkinitcpio.conf"))
        self.assert_button_untouched()

    def test_failed_grub_keeps_the_old_menu(self):
        for knob in ("FAKE_GRUB_FAIL", "FAKE_GRUB_CHECK_FAIL", "FAKE_GRUB_STRIP"):
            with self.subTest(knob=knob):
                r = self.go(**{knob: "1"})
                self.assertEqual(r.returncode, 1)
                self.assertEqual(self.text("boot/grub/grub.cfg"), OLD_GRUB)
                self.assertFalse((self.root / "boot/grub/grub.cfg.ryce-new").exists())
                self.assert_button_untouched()

    def test_refuses_a_foreign_file_before_any_change(self):
        (self.root / GRUBD).write_text('GRUB_CMDLINE_LINUX="mine"\n')
        before = tree_snapshot(self.root)
        r = self.go()
        self.assertEqual(r.returncode, 1)
        self.assertIn("no es de ryce-pc", r.stderr)
        self.assertEqual(tree_snapshot(self.root), before)
        self.assertEqual(self.mutating(), [])

    def test_refuses_symlinks(self):
        (self.tmp / "elsewhere").mkdir()
        os.symlink(self.tmp / "elsewhere", self.root / "etc/modprobe.d")
        r = self.go()
        self.assertEqual(r.returncode, 1)
        self.assertIn("enlace simbólico", r.stderr)
        self.assertEqual(list((self.tmp / "elsewhere").iterdir()), [])

    # --- check, guard, test, rollback -------------------------------------------------------------
    def test_check_fails_before_and_passes_after(self):
        r = self.go("--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no hibernes todavía", r.stdout)
        self.go()
        r = self.go("--check")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("todo listo para hibernar", r.stdout)
        self.assertNotIn("✗", r.stdout)

    def test_check_catches_a_stale_offset_and_an_updated_kernel(self):
        self.go()
        r = self.go("--check", FAKE_OFFSET="1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("GRUB no lleva", r.stdout)
        (self.root / "proc/cmdline").write_text("root=x resume=UUID=y resume_offset=12345 quiet\n")
        r = self.go("--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("apunta a resume_offset=12345", r.stdout)
        (self.root / "proc/cmdline").write_text("root=x resume_offset=533760\n")
        self.assertEqual(self.go("--check").returncode, 0)
        (self.root / "boot/vmlinuz-linux").write_text(UPDATED)
        r = self.go("--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no es el que arrancará al encender", r.stdout)

    def test_check_running_lts_is_not_ready(self):
        # Booted linux-lts: its release is in /boot (vmlinuz-linux-lts) but the next power-on
        # boots vmlinuz-linux, which would discard the image.
        self.go()
        (self.root / "boot/vmlinuz-linux-lts").write_text(VMLINUZ)
        (self.root / "boot/vmlinuz-linux").write_text(UPDATED)
        self.assertEqual(self.go("--check").returncode, 1)
        self.assertEqual(self.run_guard().returncode, 1)

    def test_check_catches_a_resume_hook_before_encrypt(self):
        self.go()
        conf = self.root / "etc/mkinitcpio.conf"
        conf.write_text(conf.read_text().replace("encrypt resume", "encrypt").replace("block", "resume block"))
        r = self.go("--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("/etc/mkinitcpio.conf no lleva resume justo después de encrypt", r.stdout)

    def run_guard(self):
        return subprocess.run(["sh", str(self.root / GUARD_BIN)], capture_output=True, text=True,
                              env={**self.env, "RYCE_ROOT": str(self.root)}, timeout=30)

    def test_the_guard_lets_the_booted_kernel_hibernate(self):
        self.go()
        self.forget_calls()
        r = self.run_guard()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        self.assertEqual([c for c in self.calls() if c.startswith("systemd-run")], [])
        self.assertIn("lsinitcpio /boot/initramfs-linux.img", self.calls())

    def test_the_guard_refuses_after_a_kernel_update_and_says_so(self):
        self.go()
        self.forget_calls()
        (self.root / "boot/vmlinuz-linux").write_text(UPDATED)
        r = self.run_guard()
        self.assertEqual(r.returncode, 1)
        self.assertIn("reinicia en el normal antes de hibernar", r.stderr)
        sent = [c for c in self.calls() if c.startswith("systemd-run")]
        self.assertEqual(len(sent), 1)
        self.assertIn("--machine=someone@.host", sent[0])
        self.assertIn("notify-send", sent[0])

    def test_the_guard_refuses_when_the_boot_chain_lost_resume(self):
        # boot-setup.sh --rollback (or a .pacnew) puts back a mkinitcpio.conf without resume.
        self.go()
        (self.root / "etc/mkinitcpio.conf").write_text(MAIN_CONF)
        subprocess.run([str(self.bin / "mkinitcpio"), "-P"], env=self.env, check=True, timeout=30)
        r = self.run_guard()
        self.assertEqual(r.returncode, 1)
        self.assertIn("falta resume en el initramfs", r.stderr)

    def test_the_guard_refuses_when_grub_lost_the_offset(self):
        self.go()
        (self.root / "boot/grub/grub.cfg").write_text(OLD_GRUB + "\tlinux /vmlinuz-linux root=UUID=x rw quiet\n")
        r = self.run_guard()
        self.assertEqual(r.returncode, 1)
        self.assertIn("no apunta al swapfile", r.stderr)
        r = self.run_guard_with(FAKE_OFFSET="999424")
        self.assertEqual(r.returncode, 1)

    def run_guard_with(self, **env):
        return subprocess.run(["sh", str(self.root / GUARD_BIN)], capture_output=True, text=True,
                              env={**self.env, "RYCE_ROOT": str(self.root), **env}, timeout=30)

    def test_test_hibernates_only_after_a_clean_check(self):
        r = self.go("--test")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("systemctl hibernate", self.calls())
        self.go()
        self.forget_calls()
        r = self.go("--test")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls()[-1], "systemctl hibernate")

    def test_rollback_undoes_everything(self):
        self.go()
        self.forget_calls()
        r = self.go("--rollback")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for rel in OURS:
            self.assertFalse((self.root / rel).exists(), rel)
        self.assertTrue((self.root / "etc/default/grub.d/ryce.cfg").exists())
        self.assertNotIn("resume", self.hooks("etc/mkinitcpio.conf"))
        self.assertNotIn("resume", self.hooks("etc/mkinitcpio-lts.conf"))
        self.assertNotIn("hooks/resume", self.text("boot/initramfs-linux.img"))
        self.assertNotIn("resume=", self.text("boot/grub/grub.cfg"))
        self.assertFalse((self.root / "swap/swapfile").exists())
        st = json.loads((self.state / "power.json").read_text())
        self.assertNotIn("@swap", st["subvols"])
        self.assertEqual(st["swaps"], [])
        calls = self.calls()
        self.assertEqual(calls[0:1] + [c for c in calls if c.startswith("systemctl disable")][:1],
                         [calls[0], "systemctl disable --now swap-swapfile.swap"])
        self.assertLess(calls.index("systemctl disable --now swap-swapfile.swap"), calls.index("grub-mkconfig -o /boot/grub/grub.cfg.ryce-new"))
        self.assertLess(calls.index("systemctl disable --now swap-swapfile.swap"), calls.index("mkinitcpio -P"))
        self.assertIn("ojo", r.stdout)

    def test_rollback_stops_before_the_boot_chain_if_the_swap_will_not_go(self):
        self.go()
        before = self.system()
        self.forget_calls()
        r = self.go("--rollback", FAKE_SWAPOFF_FAIL="1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no pude apagar", r.stderr)
        self.assertEqual(self.system(), before)
        self.assertNotIn("mkinitcpio -P", self.calls())

    def test_a_failed_rollback_of_grub_is_finished_by_the_next_one(self):
        self.go()
        r = self.go("--rollback", FAKE_GRUB_FAIL="1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("resume_offset=", self.text("boot/grub/grub.cfg"))
        r = self.go("--rollback")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("resume_offset=", self.text("boot/grub/grub.cfg"))
        self.assertNotIn("resume", self.hooks("etc/mkinitcpio.conf"))

    @unittest.skipIf(os.geteuid() == 0, "needs a non-root run")
    def test_needs_root_without_dry_run(self):
        r = self.run_script(SCRIPT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("necesito root", r.stderr)
        self.assertEqual(self.mutating(), [])


class ResumeHookEdit(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp(prefix="ryce-edit-"))
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def edit(self, text, mode):
        p = self.d / "mkinitcpio.conf"
        p.write_text(text)
        return subprocess.run(["python3", "-I", str(EDIT), "resume", str(p), mode],
                              capture_output=True, text=True, timeout=30)

    def test_add_goes_right_after_encrypt_and_is_idempotent(self):
        r = self.edit(f"{HOOKS}\n", "add")
        self.assertIn("block encrypt resume filesystems fsck", r.stdout)
        self.assertEqual(self.edit(r.stdout, "add").stdout, r.stdout)

    def test_a_misplaced_resume_moves(self):
        r = self.edit(HOOKS.replace("base udev", "base resume udev") + "\n", "add")
        self.assertEqual(r.stdout.count("resume"), 1)
        self.assertIn("encrypt resume filesystems", r.stdout)

    def test_drop_gives_back_the_original(self):
        added = self.edit(f"{HOOKS}\n", "add").stdout
        self.assertEqual(self.edit(added, "drop").stdout, f"{HOOKS}\n")

    def test_refusals(self):
        for text in ("HOOKS=(base systemd autodetect block sd-encrypt filesystems)\n",
                     "HOOKS=(base udev block encrypt)\n",
                     f"{HOOKS}\n{HOOKS}\n"):
            with self.subTest(text=text):
                r = self.edit(text, "add")
                self.assertEqual(r.returncode, 2)
                self.assertEqual(r.stdout, "")


if __name__ == "__main__":
    unittest.main()
