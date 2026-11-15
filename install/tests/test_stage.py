"""install/boot/stage.py: root's private copy of repo files, never through a link."""
import importlib.util
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from harness import REPO

STAGE = REPO / "install" / "boot" / "stage.py"
_spec = importlib.util.spec_from_file_location("stage", STAGE)
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)


class Stage(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="ryce-stage-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        files = {
            "install/boot/ryce-greeter": "#!/bin/sh\n",
            "assets/fonts/A.ttf": "font a",
            "assets/fonts/B.ttf": "font b",
            "assets/fonts/.hidden.ttf": "not shell-globbed",
            "assets/fonts/licenses/A-OFL.txt": "ofl a",
            "assets/fonts/licenses/B-OFL.txt": "ofl b",
        }
        for rel, text in files.items():
            p = self.repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        # stands for what only root (or only the user, behind the sandbox) may read
        self.secret = self.tmp / "secret"
        self.secret.mkdir()
        (self.secret / "shadow").write_text("root:$6$hunter2\n")
        self.dest = self.tmp / "stage"

    def stage(self, *specs):
        S.stage(str(self.repo), str(self.dest), list(specs))

    def refused(self, *specs, why=""):
        with self.assertRaises(S.Refused) as cm:
            self.stage(*specs)
        self.assertIn(why, str(cm.exception))
        self.assertNoSecret()
        return str(cm.exception)

    def assertNoSecret(self):
        for p in self.dest.rglob("*") if self.dest.exists() else ():
            if p.is_file():
                self.assertNotIn(b"hunter2", p.read_bytes(), p)

    def test_files_globs_and_folders(self):
        self.stage("install/boot/ryce-greeter", "assets/fonts/*.ttf", f"{self.repo}/assets/fonts/licenses/")
        got = sorted(str(p.relative_to(self.dest)) for p in self.dest.rglob("*") if p.is_file())
        self.assertEqual(got, ["A.ttf", "B.ttf", "licenses/A-OFL.txt", "licenses/B-OFL.txt", "ryce-greeter"])
        self.assertEqual((self.dest / "licenses/B-OFL.txt").read_text(), "ofl b")
        self.assertEqual(self.dest.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.dest / "A.ttf").stat().st_mode & 0o777, 0o644)

    def test_a_linked_folder_anywhere_on_the_way(self):
        (self.secret / "fonts/licenses").mkdir(parents=True)
        (self.secret / "fonts/licenses/x.txt").write_text("hunter2")
        (self.secret / "fonts/A.ttf").write_text("hunter2")
        shutil.rmtree(self.repo / "assets/fonts")
        (self.repo / "assets/fonts").symlink_to(self.secret / "fonts")   # a middle part
        self.refused("assets/fonts/licenses/", why="«fonts» no es una carpeta normal")
        shutil.rmtree(self.dest)
        self.refused("assets/fonts/A.ttf", why="«fonts» no es una carpeta normal")
        shutil.rmtree(self.dest)
        (self.repo / "assets/fonts").unlink()
        (self.repo / "assets/fonts").mkdir()
        (self.repo / "assets/fonts/licenses").symlink_to(self.secret)     # the last folder
        self.refused("assets/fonts/licenses/", why="«licenses» no es una carpeta normal")

    def test_a_linked_file(self):
        (self.repo / "assets/fonts/C.ttf").symlink_to(self.secret / "shadow")
        self.refused("assets/fonts/C.ttf", why="«C.ttf» no se puede abrir sin seguir enlaces")
        shutil.rmtree(self.dest)
        self.refused("assets/fonts/*.ttf", why="«C.ttf»")

    def test_a_fifo_is_refused_without_hanging(self):
        os.mkfifo(self.repo / "assets/fonts/licenses/fifo")
        self.refused("assets/fonts/licenses/", why="«fifo» no es un fichero normal")

    def test_a_hard_link_to_a_file_elsewhere(self):
        os.link(self.secret / "shadow", self.repo / "assets/fonts/licenses/shadow")
        self.refused("assets/fonts/licenses/", why="«shadow» tiene 2 nombres")

    def test_a_file_of_another_owner(self):
        real = os.fstat

        def fstat(fd):
            st = real(fd)
            if not stat.S_ISREG(st.st_mode):
                return st
            fields = list(st)
            fields[stat.ST_UID] = st.st_uid + 1
            return os.stat_result(fields)

        with mock.patch.object(S.os, "fstat", fstat):
            self.refused("assets/fonts/A.ttf", why="no del dueño del repo")

    def test_size_caps(self):
        with mock.patch.object(S, "MAX_FILE", 5):
            self.refused("assets/fonts/A.ttf", why="pasa de")
        shutil.rmtree(self.dest)
        with mock.patch.object(S, "MAX_TOTAL", 8):
            self.refused("assets/fonts/*.ttf", why="tamaño máximo")

    def test_a_folder_swapped_for_a_link_after_it_was_listed(self):
        # mv --exchange licenses .l between the listing and the opens: the open folder is still
        # the real one, wherever it now is, and nothing is read through the link.
        real = os.listdir
        lic = self.repo / "assets/fonts/licenses"

        def listdir(fd):
            names = real(fd)
            lic.rename(lic.with_name(".l"))
            lic.symlink_to(self.secret)
            return names

        with mock.patch.object(S.os, "listdir", listdir):
            self.stage("assets/fonts/licenses/")
        self.assertEqual(sorted(p.name for p in (self.dest / "licenses").iterdir()), ["A-OFL.txt", "B-OFL.txt"])
        self.assertNoSecret()

    def test_a_file_swapped_for_a_link_after_it_was_listed(self):
        real = os.listdir
        victim = self.repo / "assets/fonts/licenses/B-OFL.txt"

        def listdir(fd):
            names = real(fd)
            victim.unlink()
            victim.symlink_to(self.secret / "shadow")
            return names

        with mock.patch.object(S.os, "listdir", listdir):
            self.refused("assets/fonts/licenses/", why="«B-OFL.txt» no se puede abrir sin seguir enlaces")

    def test_paths_outside_the_repo_or_missing(self):
        for spec in ("../secret/shadow", "/etc/passwd", "assets//fonts/A.ttf", "assets/./fonts/A.ttf"):
            with self.subTest(spec):
                self.refused(spec)
                shutil.rmtree(self.dest, ignore_errors=True)
        self.refused("assets/fonts/*.otf", why="no hay ningún fichero así")
        shutil.rmtree(self.dest)
        self.refused("assets/fonts/A.ttf", "install/../assets/fonts/A.ttf")

    def test_two_sources_with_one_name(self):
        (self.repo / "install/A.ttf").write_text("other")
        self.refused("assets/fonts/A.ttf", "install/A.ttf", why="dos fuentes con el mismo nombre")

    def test_command_line(self):
        run = lambda *a: subprocess.run([sys.executable, "-I", str(STAGE), *a],
                                        capture_output=True, text=True, timeout=30)
        r = run(str(self.repo), str(self.dest), "assets/fonts/*.ttf")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run(str(self.repo), str(self.dest), "assets/fonts/*.ttf")   # DEST must be new
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stderr.startswith("stage.py: "), r.stderr)
        (self.repo / "assets/fonts/C.ttf").symlink_to(self.secret / "shadow")
        r = run(str(self.repo), str(self.tmp / "other"), "assets/fonts/C.ttf")
        self.assertEqual(r.returncode, 1)
        self.assertIn("como root no lo copio", r.stderr)
        self.assertEqual(run().returncode, 2)
        r = run(str(self.tmp / "repo/../repo"), str(self.tmp / "third"), "assets/fonts/A.ttf")
        self.assertIn("ruta física", r.stderr)


if __name__ == "__main__":
    unittest.main()
