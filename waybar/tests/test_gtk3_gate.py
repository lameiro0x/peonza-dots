"""Run gtk3_css_gate.py inside the unittest suite where GTK3 exists (Linux).

style.css imports "palette.css" relative to itself, which on the machine is a link
to the current theme's file: the gate parses it beside each theme's palette in turn.
"""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import gtk3_css_gate
from gtkcss import THEMES, WAYBAR, palette_css


@unittest.skipUnless(sys.platform.startswith("linux"), "GTK3 gate runs on Linux")
class Gtk3GateTest(unittest.TestCase):
    def test_style_parses_with_every_theme(self) -> None:
        if gtk3_css_gate.import_gtk() is None:
            self.skipTest("python-gobject not importable")
        for theme in THEMES:
            with self.subTest(theme=theme), tempfile.TemporaryDirectory() as t:
                shutil.copy(WAYBAR / "style.css", Path(t) / "style.css")
                shutil.copy(palette_css(theme), Path(t) / "palette.css")
                out = io.StringIO()
                with redirect_stdout(out):
                    rc = gtk3_css_gate.main(["gate", str(Path(t) / "style.css")])
                self.assertEqual(rc, 0, out.getvalue())
                self.assertIn("0 error(s)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
