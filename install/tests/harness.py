"""Shared helpers for the install tests: temp dirs, the fake command directory, script runs."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
FAKE = pathlib.Path(__file__).with_name("fakebin.py")
FAKED = ("pacman systemctl btrfs chattr chown findmnt lsblk getent usermod runuser virsh "
         "sysctl nft hyprctl claude systemd-run kitty ip").split()


class ScriptTest(unittest.TestCase):
    """Each test gets self.tmp, a fake bin dir first on PATH and a state dir for the fakes."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="ryce-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bin = self.tmp / "fakebin"
        self.bin.mkdir()
        fake = self.bin / "_fake.py"
        shutil.copy(FAKE, fake)
        fake.chmod(0o755)
        for name in FAKED:
            (self.bin / name).symlink_to(fake)
        self.state = self.tmp / "state"
        self.env = {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": os.environ["HOME"],
            "FAKE_STATE": str(self.state),
            "LC_ALL": "C.UTF-8",
            "TMPDIR": tempfile.gettempdir(),
        }

    def run_script(self, script, *args, env=None, input_text=""):
        full = {**self.env, **(env or {})}
        return subprocess.run(["bash", str(script), *args], env=full, input=input_text,
                              capture_output=True, text=True, timeout=120)

    def calls(self):
        log = self.state / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def drop_fake(self, name):
        (self.bin / name).unlink()

    def foreign_owner(self, *paths):
        """Make the scripts' ownership probe (stat -c '%u:%g %a %n') see PATHS as owned by
        another user: a test cannot chown, and chown itself is faked (logged)."""
        stat = self.bin / "stat"
        stat.write_text(f"""#!/usr/bin/env python3
import subprocess, sys
foreign = set({sorted(str(p) for p in paths)!r})
r = subprocess.run([{shutil.which("stat")!r}, *sys.argv[1:]], capture_output=True, text=True)
for line in r.stdout.splitlines():
    if sys.argv[1:3] == ["-c", "%u:%g %a %n"] and line.split(" ", 2)[2] in foreign:
        line = "4242:4242 " + line.split(" ", 1)[1]
    print(line)
sys.stderr.write(r.stderr)
sys.exit(r.returncode)
""")
        stat.chmod(0o755)


def tree_snapshot(root):
    """{relative path: (kind, content or link target)} for every entry under root."""
    out = {}
    for p in sorted(pathlib.Path(root).rglob("*")):
        rel = str(p.relative_to(root))
        if p.is_symlink():
            out[rel] = ("link", os.readlink(p))
        elif p.is_dir():
            out[rel] = ("dir", None)
        else:
            out[rel] = ("file", p.read_bytes())
    return out
