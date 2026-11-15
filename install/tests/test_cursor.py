"""One cursor, one size, everywhere it is named: the contracts, Hyprland's env, GTK, GSettings,
the greeter (its wrapper, regreet, the system copy) and the user-level deploy."""
import json
import re
import unittest

from harness import REPO

NAME, SIZE = "ryce-peonza", "32"


class CursorWiring(unittest.TestCase):
    def test_every_theme_names_the_shipped_cursor(self):
        for path in sorted((REPO / "contracts/themes").glob("*.json")):
            self.assertEqual(json.loads(path.read_text())["desktop"]["cursor"], NAME, path.name)
        self.assertIn(f"Name={NAME}\n", (REPO / "assets/cursors" / NAME / "index.theme").read_text())

    def test_hyprland_reads_both_builds_at_one_size(self):
        env = dict(re.findall(r'hl\.env\("(\w+)", "([^"]*)"\)', (REPO / "hypr/env.lua").read_text()))
        self.assertEqual((env["HYPRCURSOR_THEME"], env["XCURSOR_THEME"]), (NAME, NAME))
        self.assertEqual((env["HYPRCURSOR_SIZE"], env["XCURSOR_SIZE"]), (SIZE, SIZE))

    def test_gtk_and_gsettings_match(self):
        for ini in ("apps/gtk-3.0/settings.ini", "apps/gtk-4.0/settings.ini"):
            text = (REPO / ini).read_text()
            self.assertIn(f"gtk-cursor-theme-name={NAME}\n", text, ini)
            self.assertIn(f"gtk-cursor-theme-size={SIZE}\n", text, ini)
        self.assertRegex((REPO / "theme/gsettings.sh").read_text(), rf"cursor-size {SIZE}\b")

    def test_the_greeter_wears_it(self):
        self.assertIn(f"export XCURSOR_THEME={NAME} XCURSOR_SIZE={SIZE}\n",
                      (REPO / "install/boot/ryce-greeter").read_text())
        self.assertIn(f"CURSOR_DIR=/usr/share/icons/{NAME}\n", (REPO / "install/boot-setup.sh").read_text())
        self.assertIn(f"install_tree /usr/share/icons/{NAME}/cursors ", (REPO / "install/system-setup.sh").read_text())
        self.assertIn(f'cursor_theme_name = "{NAME}"\n', (REPO / "install/boot/greeter/regreet.toml").read_text())

    def test_deployed_to_the_user_icons(self):
        rows = [l.split("\t") for l in (REPO / "install/links.tsv").read_text().splitlines()
                if l and not l.startswith("#")]
        self.assertIn([f"assets/cursors/{NAME}", f".local/share/icons/{NAME}", "tree"], rows)


if __name__ == "__main__":
    unittest.main()
