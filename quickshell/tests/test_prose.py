"""Papel's Spanish prose (quickshell/ryce/prose.js) against the shared fixture.

    python3 -m unittest discover -s quickshell/tests -p 'test_prose.py'

prose.js is a QML JavaScript library (`.pragma library`): node runs it in a fresh vm context
with that line dropped and answers every case of prose_es.json, the fixture the lock's
Python mirror reads too. Skipped where node is not installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROSE = HERE.parent / "ryce" / "prose.js"
FIXTURE = HERE / "prose_es.json"

# Loads prose.js into its own context and maps every fixture case to what it answers.
RUNNER = r"""
const fs = require("fs"), vm = require("vm");
const [src, fixture] = process.argv.slice(1);
const code = fs.readFileSync(src, "utf8").replace(/^\.pragma library\s*$/m, "");
const ctx = vm.createContext({});
vm.runInContext(code, ctx, { filename: src });
const f = JSON.parse(fs.readFileSync(fixture, "utf8"));
const out = {
  hour: f.hour.map(c => ({ phrase: ctx.hour(c.h, c.m), part: ctx.partOfDay(c.h, c.m) })),
  number: f.number.map(c => ctx.number(c.n, c.feminine)),
  roman: f.roman.map(c => ctx.roman(c.n)),
  day: Array.from({ length: 24 * 60 }, (_, i) => ctx.hour(Math.floor(i / 60), i % 60)),
};
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Prose(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        proc = subprocess.run(["node", "-e", RUNNER, str(PROSE), str(FIXTURE)],
                              capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            raise AssertionError(f"node could not run {PROSE.name}:\n{proc.stderr[-2000:]}")
        cls.got = json.loads(proc.stdout)

    def test_fixture_covers_the_edges(self) -> None:
        cases = {(c["h"], c["m"]) for c in self.fixture["hour"]}
        self.assertGreaterEqual(len(cases), 40)
        self.assertTrue({0, 1, 15, 29, 30, 31, 39, 40, 44, 45, 46, 59} <= {m for _, m in cases})
        self.assertTrue({0, 1, 12, 13, 23} <= {h for h, _ in cases})

    def test_hour_in_words(self) -> None:
        for case, got in zip(self.fixture["hour"], self.got["hour"]):
            with self.subTest(at=f"{case['h']:02d}:{case['m']:02d}"):
                self.assertEqual(got["phrase"], case["phrase"])

    def test_part_of_day(self) -> None:
        for case, got in zip(self.fixture["hour"], self.got["hour"]):
            with self.subTest(at=f"{case['h']:02d}:{case['m']:02d}"):
                self.assertEqual(got["part"], case["part"])

    def test_numbers_in_words(self) -> None:
        for case, got in zip(self.fixture["number"], self.got["number"]):
            with self.subTest(n=case["n"], feminine=case["feminine"]):
                self.assertEqual(got, case["words"])

    def test_lowercase_roman(self) -> None:
        for case, got in zip(self.fixture["roman"], self.got["roman"]):
            with self.subTest(n=case["n"]):
                self.assertEqual(got, case["roman"])

    # Every minute of the day said on a 12-hour face: each phrase twice but midnight's and noon's.
    def test_a_day_says_a_twelve_hour_face(self) -> None:
        phrases = set(self.got["day"])
        self.assertIn("Medianoche", phrases)
        self.assertIn("Las siete y treinta y ocho", phrases)
        # A 12-hour face says 720 phrases; «Las doce en punto» is never said, Mediodía and
        # Medianoche are.
        self.assertEqual(len(phrases), 12 * 60 + 1)
        self.assertNotIn("Las doce en punto", phrases)


if __name__ == "__main__":
    unittest.main()
