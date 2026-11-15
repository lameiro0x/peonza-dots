"""The headset's state machine and its OSD's life, run headless against stand-ins.

    python3 -m unittest discover -s quickshell/tests -p 'test_headset.py'

Copies quickshell/ryce/HeadsetLogic.qml and quickshell/ryce/osd/HeadsetOsdLife.qml next to
the scenarios in quickshell/tests/headset/ and runs them with Quickshell on Qt's offscreen
platform, in a throwaway runtime, cache and state dir (nothing of the session is touched).
Skipped where Quickshell is not installed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RYCE = HERE.parent / "ryce"
UNDER_TEST = {
    RYCE / "HeadsetLogic.qml": "HeadsetLogic.qml",
    RYCE / "osd" / "HeadsetOsdLife.qml": "HeadsetOsdLife.qml",
}


@unittest.skipUnless(shutil.which("qs"), "Quickshell (qs) is not installed")
class HeadsetScenarios(unittest.TestCase):
    def run_scenarios(self) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "cfg"
            cfg.mkdir()
            for src in (HERE / "headset").glob("*.qml"):
                shutil.copy(src, cfg / src.name)
            for src, name in UNDER_TEST.items():
                shutil.copy(src, cfg / name)
            runtime = root / "run"
            runtime.mkdir(mode=0o700)
            env = {k: v for k, v in os.environ.items()
                   if k not in ("WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE", "QS_CONFIG_NAME")}
            env.update(
                QT_QPA_PLATFORM="offscreen",
                XDG_RUNTIME_DIR=str(runtime),
                XDG_CACHE_HOME=str(root / "cache"),
                XDG_STATE_HOME=str(root / "state"),
            )
            proc = subprocess.run(["qs", "-p", str(cfg), "--no-color"], env=env,
                                  capture_output=True, text=True, timeout=120)
            out = proc.stdout + proc.stderr
            self.returncode = proc.returncode
            return out

    def test_scenarios(self) -> None:
        out = self.run_scenarios()
        fails = re.findall(r"FAIL [^\n]*", out)
        done = re.search(r"DONE checks=(\d+) failures=(\d+)", out)
        self.assertIsNotNone(done, f"the scenarios never finished:\n{out[-4000:]}")
        assert done is not None
        self.assertEqual(fails, [], "\n".join(fails))
        errors = re.findall(r"[^\n]*(?:TypeError|ReferenceError|SyntaxError|is not a type|Failed to load|Binding loop)[^\n]*", out)
        self.assertEqual(errors, [], "\n".join(errors))
        self.assertEqual(self.returncode, 0, out[-2000:])
        self.assertGreaterEqual(int(done.group(1)), 250, "fewer checks ran than written")


if __name__ == "__main__":
    unittest.main()
