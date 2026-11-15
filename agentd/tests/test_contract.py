"""agentd against the repo's contracts, the goldens and the stage fixtures.

    AGENTD_REGEN=1 python3 -m unittest discover -s agentd/tests -p test_contract.py
regenerates the goldens; review the diff before keeping it.
"""

import filecmp
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from agentd import const, render
from agentd.claude import ClaudeHome
from agentd.hypr import FakeHypr
from agentd.model import collect
from agentd.procfs import Proc
import world

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GOLDEN = HERE / "golden"
REGEN = os.environ.get("AGENTD_REGEN") == "1"
sys.path.insert(0, str(REPO / "contracts"))
import check_roster  # noqa: E402


class ConstantsTest(unittest.TestCase):
    def test_agentd_restates_contracts_constants_exactly(self):
        c = json.loads((REPO / "contracts" / "constants.json").read_text())
        self.assertEqual(
            (const.TAG, const.SIGNAL, const.RUNTIME, const.ROSTER_FILE, const.LOCK_FILE,
             const.WAYBAR_DIR, const.AGENTS_FILE, const.MAX_WS, const.DISPATCH_TAG),
            (c["tag"], c["signal"], c["runtime"], c["roster_file"], c["lock_file"],
             c["waybar_dir"], c["agents_file"], c["max_ws"], c["dispatch_tag"]))

    def test_always_shown_and_spanish_words_mirror_the_contract(self):
        c = json.loads((REPO / "contracts" / "constants.json").read_text())
        self.assertEqual(const.ALWAYS_SHOWN, c["always_shown"])
        self.assertEqual(const.WORDS, {k: v for k, v in c["words_es"].items() if k != "note"})

    def test_built_in_greys_are_the_default_themes_greys(self):
        c = json.loads((REPO / "contracts" / "constants.json").read_text())
        theme = json.loads((REPO / "contracts" / "themes" / f"{c['default_theme']}.json").read_text())
        self.assertEqual(render.GREYS, {k: theme["colors"][k] for k in render.GREYS})


class GoldenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        r = world.main_world(Path(cls.tmp.name)).root
        snap = collect(FakeHypr(r / "hypr"), Proc(r / "proc"),
                       ClaudeHome(r / "claude", clock=lambda: world.NOW), str(r / "fs"))
        cls.roster = render.roster(snap, world.NOW)
        cls.slots = render.waybar(snap, render.GREYS)
        if REGEN:
            (GOLDEN / "waybar").mkdir(parents=True, exist_ok=True)
            (GOLDEN / "roster.json").write_text(json.dumps(cls.roster, ensure_ascii=False, indent=1) + "\n")
            for name, payload in cls.slots.items():
                (GOLDEN / "waybar" / name).write_text(json.dumps(payload, ensure_ascii=False) + "\n")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_golden_roster_passes_the_contract(self):
        self.assertEqual(check_roster.check(json.loads((GOLDEN / "roster.json").read_text())), [])

    def test_roster_matches_golden(self):
        self.assertEqual(self.roster, json.loads((GOLDEN / "roster.json").read_text()))

    def test_waybar_slots_match_golden(self):
        on_disk = {p.name: json.loads(p.read_text()) for p in (GOLDEN / "waybar").iterdir()}
        self.assertEqual(self.slots, on_disk)


class StageFixtureTest(unittest.TestCase):
    def test_committed_stage_fixtures_are_what_world_py_generates(self):
        for committed, build in ((world.STAGE, world.stage_world), (world.STAGE8, world.stage8_world)):
            with self.subTest(committed.name):
                self.assert_same(committed, build)

    def assert_same(self, committed, build):
        with tempfile.TemporaryDirectory() as t:
            fresh = Path(t) / "stage"
            build(fresh)
            # Files and links only: git keeps no empty directories.
            leaves = lambda d: sorted(p.relative_to(d).as_posix() for p in d.rglob("*")
                                      if p.is_symlink() or p.is_file())
            a, b = leaves(fresh), leaves(committed)
            self.assertEqual(a, b, "run: python3 agentd/tests/world.py --write-stage")
            for rel in a:
                x, y = fresh / rel, committed / rel
                if x.is_symlink():
                    self.assertEqual(os.readlink(x), os.readlink(y), rel)
                else:
                    self.assertTrue(filecmp.cmp(x, y, shallow=False), rel)

    def test_stage_fixture_has_one_output_named_headless_1(self):
        snap = collect(FakeHypr(world.STAGE / "hypr"), Proc(world.STAGE / "proc"),
                       ClaudeHome(world.STAGE / "claude"), str(world.STAGE / "fs"))
        self.assertEqual(snap.outputs, ["HEADLESS-1"])
        self.assertEqual(snap.counts, {"waiting": 1, "busy": 2, "idle": 1})
        self.assertEqual(check_roster.check(render.roster(snap, 0.0)), [])

    def test_stage8_fills_eight_slots_on_one_output(self):
        snap = collect(FakeHypr(world.STAGE8 / "hypr"), Proc(world.STAGE8 / "proc"),
                       ClaudeHome(world.STAGE8 / "claude"), str(world.STAGE8 / "fs"))
        self.assertEqual([w.id for w in snap.workspaces if w.occupied], list(range(1, 9)))
        self.assertEqual(snap.counts, {"waiting": 1, "busy": 4, "idle": 3})


if __name__ == "__main__":
    unittest.main()
