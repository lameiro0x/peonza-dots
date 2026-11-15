#!/usr/bin/env python3
"""bin/ryce-chromium-theme against a temp theme state and a temp output dir.

    python3 -m unittest discover -s tools -p 'test_chromium_theme.py'
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CMD = REPO / "bin" / "ryce-chromium-theme"


class Hook(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ryce-chromium-"))
        self.state = self.tmp / "state"
        self.state.mkdir()
        for d in (REPO / "themes").iterdir():
            if (d / "theme.json").is_file():
                os.symlink(d, self.state / d.name)
        self.out = self.tmp / "out"
        self.use("origen")

    def use(self, tid: str) -> None:
        (self.state / "current").unlink(missing_ok=True)
        os.symlink(tid, self.state / "current")

    def run_hook(self, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "RYCE_THEME_STATE": str(self.state), "RYCE_CHROMIUM_DIR": str(self.out)}
        return subprocess.run([sys.executable, str(CMD), *args], env=env, capture_output=True,
                              text=True, timeout=20)

    def manifest(self) -> dict:
        return json.loads((self.out / "theme" / "manifest.json").read_text(encoding="utf-8"))

    def test_builds_both_extensions_from_the_current_theme(self) -> None:
        r = self.run_hook()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.manifest()["name"], "Ryce · Origen")
        nt = self.out / "newtab"
        for f in ("manifest.json", "newtab.html", "newtab.css", "newtab.js"):
            self.assertEqual((nt / f).read_bytes(), (REPO / "apps/chromium/newtab" / f).read_bytes(), f)
        for f in ("theme.css", "layout.css"):
            self.assertEqual((nt / f).read_bytes(), (REPO / "themes/origen/chromium/newtab" / f).read_bytes(), f)
        for f, size in (("art-1920.jpg", "1920x1080"), ("art-2560.jpg", "2560x1440")):
            self.assertEqual((nt / f).read_bytes(), (REPO / f"themes/origen/chromium/newtab/{size}.jpg").read_bytes(), f)
        self.assertEqual((nt / "peonza.png").read_bytes(), (REPO / "themes/origen/peonza/logo.png").read_bytes())

    def test_a_switch_bumps_the_version_and_drops_chromiums_cached_pack(self) -> None:
        self.run_hook()
        first = self.manifest()["version"]
        pak = self.out / "theme" / "Cached Theme.pak"
        pak.write_bytes(b"old pack")
        self.use("papel")
        self.assertEqual(self.run_hook().returncode, 0)
        self.assertNotEqual(self.manifest()["version"], first)
        self.assertFalse(pak.exists())
        self.assertEqual(self.manifest()["name"], "Ryce · Papel")

    def test_the_same_theme_again_leaves_chromiums_pack_alone(self) -> None:
        self.run_hook()
        pak = self.out / "theme" / "Cached Theme.pak"
        pak.write_bytes(b"pack")
        self.assertEqual(self.run_hook().returncode, 0)
        self.assertTrue(pak.exists())

    def test_the_new_tab_keeps_its_own_picture_and_drops_the_desks(self) -> None:
        old = self.out / "newtab" / "wall.jpg"
        old.parent.mkdir(parents=True)
        old.write_bytes(b"the desk picture an older build copied")
        self.assertEqual(self.run_hook().returncode, 0)
        self.assertFalse(old.exists())
        self.assertNotIn("wall.jpg", (REPO / "apps/chromium/newtab/newtab.css").read_text(encoding="utf-8"))

    def test_a_missing_picture_is_refused_and_nothing_is_written(self) -> None:
        theme = self.tmp / "bare"
        shutil.copytree(REPO / "themes" / "origen", theme, ignore=shutil.ignore_patterns("*.jpg", "*.png"))
        shutil.copy(REPO / "themes/origen/peonza/logo.png", theme / "peonza" / "logo.png")
        os.symlink(theme, self.state / "bare")
        self.use("bare")
        r = self.run_hook()
        self.assertEqual(r.returncode, 2)
        self.assertIn("1920x1080.jpg", r.stderr)
        self.assertFalse(self.out.exists())

    def test_no_current_theme_is_a_clear_error(self) -> None:
        (self.state / "current").unlink()
        r = self.run_hook()
        self.assertEqual(r.returncode, 2)
        self.assertIn("current", r.stderr)


if __name__ == "__main__":
    unittest.main()
