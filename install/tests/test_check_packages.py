"""install/check-packages.py logic with a fake package database (no network)."""
import importlib.util
import pathlib
import tempfile
import unittest

from harness import REPO

spec = importlib.util.spec_from_file_location("check_packages", REPO / "install" / "check-packages.py")
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


def pkg(name, depends=(), provides=()):
    return {"pkgname": name, "repo": "extra", "depends": list(depends), "provides": list(provides)}


# Shapes copied from archlinux.org on 2026-11-09 (trimmed).
DB = {p["pkgname"]: p for p in [
    pkg("hyprutils", ["pixman", "libpixman-1.so=0-64"], ["libhyprutils.so=13-64"]),
    pkg("hyprlang", ["hyprutils", "libhyprutils.so=13-64"], ["libhyprlang.so=2-64"]),
    pkg("hyprland", ["hyprutils", "hyprlang", "hyprland-guiutils", "cairo",
                     "libhyprutils.so=13-64", "libhyprlang.so"]),
    pkg("hyprland-guiutils", ["hyprtoolkit", "libhyprtoolkit.so=6-64"]),
    pkg("hyprtoolkit", ["hyprutils", "libhyprutils.so=13-64"], ["libhyprtoolkit.so=6-64"]),
    pkg("hyprpicker", ["hyprutils", "wayland"]),            # links by package name only
    pkg("pixman"), pkg("cairo", ["pixman"]), pkg("wayland"),
    pkg("kitty", ["wayland"]),
]}


class CheckPackages(unittest.TestCase):
    def fetch(self, name):
        self.asked.append(name)
        return DB.get(name)

    def setUp(self):
        self.asked = []

    def test_clean_when_family_is_pinned(self):
        pin = ["hyprland", "hyprutils", "hyprlang", "hyprland-guiutils", "hyprtoolkit", "hyprpicker"]
        self.assertEqual(cp.check({"hyprland": "d", "hyprpicker": "d", "kitty": "d"}, pin, self.fetch), [])

    def test_name_only_dependency_counts(self):
        pin = ["hyprland", "hyprutils", "hyprlang", "hyprland-guiutils", "hyprtoolkit"]
        problems = cp.check({"hyprland": "d", "hyprpicker": "d"}, pin, self.fetch)
        self.assertEqual(problems, ["enlaza la familia hypr y falta en HYPR_PIN (install/system-setup.sh): hyprpicker"])

    def test_transitive_family_members_are_found(self):
        problems = cp.check({"hyprland": "d"}, ["hyprland", "hyprutils", "hyprlang"], self.fetch)
        self.assertIn("enlaza la familia hypr y falta en HYPR_PIN (install/system-setup.sh): hyprland-guiutils", problems)
        self.assertIn("enlaza la familia hypr y falta en HYPR_PIN (install/system-setup.sh): hyprtoolkit", problems)

    def test_unrelated_dependencies_are_not_expanded(self):
        cp.check({"kitty": "d"}, [], self.fetch)
        self.assertEqual(self.asked, ["kitty"])

    def test_missing_package_and_pin_typo(self):
        problems = cp.check({"kitty": "dev.txt", "yay": "dev.txt"}, ["hyprlandd"], self.fetch)
        self.assertIn("no está en core/extra: yay (dev.txt)", problems)
        self.assertIn("está en HYPR_PIN pero no existe en core/extra: hyprlandd", problems)

    def test_http_fetch_wants_exact_name_in_core_or_extra(self):
        results = [{"pkgname": "foo-git", "repo": "extra"}, {"pkgname": "foo", "repo": "extra-testing"}]
        with tempfile.TemporaryDirectory() as d:
            old = cp.CACHE
            cp.CACHE = pathlib.Path(d)
            try:
                (cp.CACHE / "foo.json").write_text(cp.json.dumps(results))
                self.assertIsNone(cp.http_fetch("foo"))
                results.append({"pkgname": "foo", "repo": "core"})
                (cp.CACHE / "foo.json").write_text(cp.json.dumps(results))
                self.assertEqual(cp.http_fetch("foo")["repo"], "core")
                self.assertIsNone(cp.http_fetch("../etc/passwd"))
            finally:
                cp.CACHE = old

    def test_real_lists_and_pin_parse(self):
        lists = cp.read_lists(REPO / "install" / "packages")
        pin = cp.read_pin(REPO / "install" / "system-setup.sh")
        self.assertIn("hyprland", lists)
        self.assertNotIn("#", "".join(lists))
        self.assertIn("hyprland", pin)
        self.assertEqual(len(pin), len(set(pin)))
        self.assertTrue(set(pin) - set(lists) <= {"aquamarine", "hyprutils", "hyprlang", "hyprcursor",
                                                  "hyprgraphics", "hyprwire", "hyprland-guiutils", "hyprtoolkit",
                                                  "hyprland-qt-support"},
                        "pinned packages outside the lists should only be hypr libraries")


if __name__ == "__main__":
    unittest.main()
