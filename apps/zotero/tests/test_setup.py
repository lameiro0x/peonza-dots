"""apps/zotero/setup.py against a throwaway HOME: it finds or creates the Zotero profile,
links user.js, installs the pinned Better BibTeX (verified) and the Ryce plugin, is
idempotent, refuses to write while Zotero runs or over a user.js it did not write, and
never touches anything outside the profile (the library in ~/Zotero above all).

    python3 -m unittest discover -s apps/zotero/tests -v

No network: the pinned xpi is replaced by a small fake one with its own pin.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
sys.dont_write_bytecode = True  # no __pycache__ under apps/: theme/tests reads apps/ as text
spec = importlib.util.spec_from_file_location("zotero_setup", APP / "setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

BBT = "better-bibtex@iris-advies.com"


def fake_xpi(path: Path, version: str, ext_id: str = BBT) -> bytes:
    manifest = {"manifest_version": 2, "name": "fake", "version": version,
                "applications": {"zotero": {"id": ext_id}}}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
    return path.read_bytes()


def tree(root: Path) -> dict[str, str]:
    """Every path under root with what it is (link target, file digest, dir)."""
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for name in dirs + files:
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                out[rel] = "-> " + os.readlink(p)
            elif p.is_file():
                out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() + f" {p.stat().st_mtime_ns}"
            else:
                out[rel] = "dir"
    return out


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.home.mkdir()
        self.xpi = base / "bbt.xpi"
        self.bbt_bytes = fake_xpi(self.xpi, "9.0.77")
        self.pin = {"id": BBT, "version": "9.0.77", "url": "https://invalid.example/bbt.xpi",
                    "sha256": hashlib.sha256(self.bbt_bytes).hexdigest()}
        patcher = unittest.mock.patch.object(setup, "PIN", self.pin)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_setup(self, *args: str) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = setup.main(["--home", str(self.home), "--bbt-xpi", str(self.xpi), *args])
        return code, buf.getvalue()

    def root(self) -> Path:
        return self.home / ".zotero" / "zotero"

    def make_profiles(self, ini: str, *dirs: str) -> None:
        self.root().mkdir(parents=True)
        (self.root() / "profiles.ini").write_text(ini)
        for d in dirs:
            (self.root() / d).mkdir()

    def only_profile(self) -> Path:
        dirs = [p for p in self.root().iterdir() if p.is_dir()]
        self.assertEqual(len(dirs), 1, dirs)
        return dirs[0]

    def test_fresh_home_gets_a_default_profile_with_everything(self):
        code, out = self.run_setup()
        self.assertEqual(code, 0, out)
        ini = (self.root() / "profiles.ini").read_text()
        prof = self.only_profile()
        self.assertIn(f"Path={prof.name}", ini)
        self.assertIn("Default=1", ini)
        self.assertIn("IsRelative=1", ini)
        self.assertRegex(prof.name, r"^[a-z0-9]{8}\.default$")
        self.assertEqual(Path(os.readlink(prof / "user.js")), APP / "user.js")
        self.assertEqual((prof / "extensions" / f"{BBT}.xpi").read_bytes(), self.bbt_bytes)
        with zipfile.ZipFile(prof / "extensions" / "ryce@ryce-pc.xpi") as z:
            self.assertEqual(sorted(z.namelist()), ["bootstrap.js", "manifest.json"])
            self.assertEqual(z.read("bootstrap.js"), (APP / "plugin" / "bootstrap.js").read_bytes())

    def test_second_run_changes_nothing(self):
        self.assertEqual(self.run_setup()[0], 0)
        before = tree(self.home)
        code, out = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertEqual(tree(self.home), before)

    def test_dry_run_writes_nothing(self):
        (self.home / "Zotero").mkdir()
        before = tree(self.home)
        code, out = self.run_setup("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertEqual(tree(self.home), before)
        self.assertIn("Better BibTeX", out)

    def test_uses_the_default_profile_zotero_made(self):
        self.make_profiles(
            "[General]\nStartWithLastProfile=1\nVersion=2\n\n"
            "[Profile1]\nName=old\nIsRelative=1\nPath=aaaaaaaa.old\n\n"
            "[Profile0]\nName=default\nIsRelative=1\nPath=bbbbbbbb.default\nDefault=1\n\n"
            "[InstallAB12]\nDefault=bbbbbbbb.default\nLocked=1\n",
            "aaaaaaaa.old", "bbbbbbbb.default")
        code, out = self.run_setup()
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root() / "bbbbbbbb.default" / "user.js").is_symlink())
        self.assertFalse((self.root() / "aaaaaaaa.old" / "user.js").exists())
        self.assertEqual(len([p for p in self.root().iterdir() if p.is_dir()]), 2)

    def test_absolute_profile_path(self):
        elsewhere = self.home / "profiles" / "work"
        elsewhere.mkdir(parents=True)
        self.make_profiles(f"[Profile0]\nName=w\nIsRelative=0\nPath={elsewhere}\nDefault=1\n")
        self.assertEqual(self.run_setup()[0], 0)
        self.assertTrue((elsewhere / "user.js").is_symlink())

    def test_several_profiles_and_no_default_is_an_error(self):
        self.make_profiles("[Profile0]\nName=a\nIsRelative=1\nPath=a.a\n\n"
                           "[Profile1]\nName=b\nIsRelative=1\nPath=b.b\n", "a.a", "b.b")
        before = tree(self.home)
        code, out = self.run_setup()
        self.assertEqual(code, 1)
        self.assertIn("a.a", out)
        self.assertEqual(tree(self.home), before)

    def test_foreign_user_js_is_left_alone(self):
        self.make_profiles("[Profile0]\nName=d\nIsRelative=1\nPath=p.default\nDefault=1\n", "p.default")
        (self.root() / "p.default" / "user.js").write_text('user_pref("mine", 1);\n')
        before = tree(self.home)
        code, out = self.run_setup()
        self.assertEqual(code, 1)
        self.assertIn("user.js", out)
        self.assertEqual(tree(self.home), before)

    def test_an_old_copy_of_our_user_js_becomes_the_link(self):
        self.make_profiles("[Profile0]\nName=d\nIsRelative=1\nPath=p.default\nDefault=1\n", "p.default")
        (self.root() / "p.default" / "user.js").write_text("// Ryce: an older version\n")
        self.assertEqual(self.run_setup()[0], 0)
        self.assertEqual(Path(os.readlink(self.root() / "p.default" / "user.js")), APP / "user.js")

    def test_running_zotero_blocks_every_write(self):
        self.make_profiles("[Profile0]\nName=d\nIsRelative=1\nPath=p.default\nDefault=1\n", "p.default")
        os.symlink(f"127.0.1.1:+{os.getpid()}", self.root() / "p.default" / "lock")
        before = tree(self.home)
        code, out = self.run_setup()
        self.assertEqual(code, 3)
        self.assertIn("Zotero", out)
        self.assertEqual(tree(self.home), before)

    def test_stale_lock_does_not_block(self):
        self.make_profiles("[Profile0]\nName=d\nIsRelative=1\nPath=p.default\nDefault=1\n", "p.default")
        os.symlink("127.0.1.1:+999999999", self.root() / "p.default" / "lock")
        self.assertEqual(self.run_setup()[0], 0)

    def test_newer_bbt_from_its_own_updater_is_kept(self):
        self.make_profiles("[Profile0]\nName=d\nIsRelative=1\nPath=p.default\nDefault=1\n", "p.default")
        ext = self.root() / "p.default" / "extensions"
        ext.mkdir()
        newer = fake_xpi(ext / f"{BBT}.xpi", "9.0.80")
        self.assertEqual(self.run_setup()[0], 0)
        self.assertEqual((ext / f"{BBT}.xpi").read_bytes(), newer)

    def test_older_bbt_is_replaced_by_the_pin(self):
        self.make_profiles("[Profile0]\nName=d\nIsRelative=1\nPath=p.default\nDefault=1\n", "p.default")
        ext = self.root() / "p.default" / "extensions"
        ext.mkdir()
        fake_xpi(ext / f"{BBT}.xpi", "9.0.9")
        self.assertEqual(self.run_setup()[0], 0)
        self.assertEqual((ext / f"{BBT}.xpi").read_bytes(), self.bbt_bytes)

    def test_checksum_mismatch_leaves_no_trace(self):
        fake_xpi(self.xpi, "9.0.77", ext_id="evil@example.com")
        code, out = self.run_setup()
        self.assertEqual(code, 1)
        self.assertIn("sha256", out)
        self.assertEqual(tree(self.home), {})  # not even the new profile

    def test_a_link_to_someone_elses_user_js_is_left_alone(self):
        self.make_profiles("[Profile0]\nName=d\nIsRelative=1\nPath=p.default\nDefault=1\n", "p.default")
        os.symlink("/home/x/dotfiles/zotero/user.js", self.root() / "p.default" / "user.js")
        before = tree(self.home)
        self.assertEqual(self.run_setup()[0], 1)
        self.assertEqual(tree(self.home), before)

    def test_plugin_xpi_is_deterministic_and_loadable(self):
        with unittest.mock.patch("time.time", return_value=4_000_000_000):
            later = setup.plugin_xpi()
        self.assertEqual(setup.plugin_xpi(), later)
        with zipfile.ZipFile(io.BytesIO(setup.plugin_xpi())) as z:
            self.assertEqual({i.date_time for i in z.infolist()}, {(1980, 1, 1, 0, 0, 0)})
            zot = json.loads(z.read("manifest.json"))["applications"]["zotero"]
        # Zotero refuses a plugin without these three (Extension.sys.mjs, manifestError).
        self.assertEqual(zot["id"], "ryce@ryce-pc")
        self.assertTrue(zot["update_url"].startswith("https://"))
        self.assertIn("strict_max_version", zot)


class ThemeFilesTest(unittest.TestCase):
    """What the plugin reads from every theme: a reader paper it accepts and a sheet."""

    def test_every_theme_has_reader_colours_and_a_sheet(self):
        themes = sorted(p.parent.parent.name for p in (APP.parents[1] / "themes").glob("*/zotero/ryce.css"))
        self.assertEqual(themes, ["grafito", "ola", "origen", "papel", "tinta"])
        for tid in themes:
            t = json.loads((APP.parents[1] / "themes" / tid / "zotero" / "reader.json").read_text())
            for key in ("background", "foreground"):
                self.assertRegex(t[key], r"^#[0-9a-f]{6}$", tid)
            self.assertTrue(t["label"])


if __name__ == "__main__":
    unittest.main()
