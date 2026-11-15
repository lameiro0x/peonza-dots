"""qmlcheck must reject each class of defect it claims to catch.

    python3 -m unittest discover -s quickshell/tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qmlcheck  # noqa: E402

SCHEMA = HERE.parent.parent / "contracts" / "roster.v1.schema.json"

CLEAN = {
    "shell.qml": """
import Quickshell
import Quickshell.Wayland
ShellRoot {
    PanelWindow {
        WlrLayershell.namespace: "qs-sidebar"
        color: "transparent"
        Text { text: "hola"; textFormat: Text.PlainText; color: Ryce.Palette.fg0 }
    }
}
""",
    "Cava.qml": """
import Quickshell.Io
Item {
    property bool active: false
    Process {
        running: root.active
        command: ["sh", "-c", "exec cava -p \\"$1\\"", "sh", Quickshell.shellDir + "/cava.conf"]
    }
}
""",
    "agents/Roster.qml": """
Singleton {
    readonly property string dir: Quickshell.env("RYCE_RUNTIME") || Quickshell.env("XDG_RUNTIME_DIR") + "/agentd"
    readonly property string path: dir + "/roster.json"
    function parse(data) { return data.sessions.map(raw => ({ project: raw.project, doing: raw.doing, ws: raw.hypr.focusedWorkspace })); }
    FileView { path: roster.path; watchChanges: true }
}
""",
    "agents/AgentCard.qml": """
Item {
    Rectangle { color: Ryce.Palette.signal }
    Text { text: session.title; textFormat: Text.PlainText; color: Ryce.Palette.fg1 }
}
""",
}


class QmlCheck(unittest.TestCase):
    def run_on(self, **overrides: str) -> list[str]:
        files = dict(CLEAN)
        for name, body in overrides.items():
            files[name.replace("__", "/").replace("_qml", ".qml")] = body
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, body in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(body, encoding="utf-8")
            return qmlcheck.check(root, SCHEMA)

    def assertOneError(self, errors: list[str], needle: str) -> None:
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(needle, errors[0])

    def test_clean_tree_passes(self):
        self.assertEqual(self.run_on(), [])

    def test_roster_key_missing_from_schema(self):
        card = CLEAN["agents/AgentCard.qml"].replace("session.title", "session.titel")
        self.assertOneError(self.run_on(agents__AgentCard_qml=card), "titel")

    def test_nested_roster_key_missing_from_schema(self):
        roster = CLEAN["agents/Roster.qml"].replace("raw.hypr.focusedWorkspace", "raw.hypr.focused")
        self.assertOneError(self.run_on(agents__Roster_qml=roster), "focused")

    def test_text_without_plaintext(self):
        card = CLEAN["agents/AgentCard.qml"].replace("textFormat: Text.PlainText; ", "")
        self.assertOneError(self.run_on(agents__AgentCard_qml=card), "PlainText")

    def test_text_with_rich_format(self):
        card = CLEAN["agents/AgentCard.qml"].replace("Text.PlainText", "Text.RichText")
        self.assertTrue(any("PlainText" in e for e in self.run_on(agents__AgentCard_qml=card)))

    def test_panel_window_without_qs_namespace(self):
        shell = CLEAN["shell.qml"].replace('"qs-sidebar"', '"sidebar"')
        self.assertOneError(self.run_on(shell_qml=shell), "namespace")

    def test_fileview_path_from_roster_data(self):
        roster = CLEAN["agents/Roster.qml"].replace("path: roster.path", "path: raw.cwd + \"/x\"")
        self.assertTrue(any("FileView" in e for e in self.run_on(agents__Roster_qml=roster)))

    def test_cava_always_running(self):
        cava = CLEAN["Cava.qml"].replace("running: root.active", "running: true")
        self.assertOneError(self.run_on(Cava_qml=cava), "cava")

    def test_hex_colour_outside_palette(self):
        shell = CLEAN["shell.qml"].replace("Ryce.Palette.fg0", '"#ffffff"')
        self.assertOneError(self.run_on(shell_qml=shell), "colour")

    def test_hardcoded_rgba_outside_palette(self):
        shell = CLEAN["shell.qml"].replace("Ryce.Palette.fg0", "Qt.rgba(1, 1, 1, 0.5)")
        self.assertOneError(self.run_on(shell_qml=shell), "colour")

    def test_signal_outside_agents(self):
        shell = CLEAN["shell.qml"].replace("Ryce.Palette.fg0", "Ryce.Palette.signal")
        self.assertOneError(self.run_on(shell_qml=shell), "signal")

    def test_state_word_hardcoded_outside_words(self):
        words = 'Singleton { readonly property var state: {"busy": "trabajando"} }'
        card = CLEAN["agents/AgentCard.qml"].replace("session.title", '"trabajando"')
        errors = self.run_on(Words_qml=words, agents__AgentCard_qml=card)
        self.assertOneError(errors, "Words")

    def test_generated_words_is_not_linted(self):
        words = 'Singleton { property color c: "#ffffff"; readonly property var state: {"busy": "trabajando"} }'
        self.assertEqual(self.run_on(Words_qml=words), [])

    def test_unqualified_palette(self):
        # QtQuick exports a `Palette` type that shadows the qs singleton: every colour
        # read through a bare `Palette.` is undefined at runtime (seen on Qt 6.12).
        shell = CLEAN["shell.qml"].replace("Ryce.Palette.fg0", "Palette.fg0")
        self.assertOneError(self.run_on(shell_qml=shell), "Ryce.Palette")


if __name__ == "__main__":
    unittest.main()
