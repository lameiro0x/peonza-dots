"""bin/ryce-hora: Papel's lock says the hour in words, the same words as the desk.

Every case of quickshell/tests/prose_es.json, the fixture prose.js (the desk clock) answers
too, so the lock and the desk never say the same minute two ways; then the command line
hyprlock calls (@papel/hypr/hyprlock.conf).
"""
import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import unittest

from harness import REPO

HORA = REPO / "bin" / "ryce-hora"
FIXTURE = REPO / "quickshell" / "tests" / "prose_es.json"


def load():
    loader = importlib.machinery.SourceFileLoader("ryce_hora", str(HORA))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


H = load()


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HORA), *args], capture_output=True, text=True, timeout=30)


@unittest.skipUnless(FIXTURE.exists(), f"no {FIXTURE.relative_to(REPO)} (the desk's prose fixture)")
class Fixture(unittest.TestCase):
    def test_every_case_of_the_shared_fixture(self):
        for case in json.loads(FIXTURE.read_text(encoding="utf-8"))["hour"]:
            with self.subTest(h=case["h"], m=case["m"]):
                self.assertEqual(H.hour(case["h"], case["m"]), case["phrase"])
                self.assertEqual(H.part_of_day(case["h"], case["m"]), case["part"])


class Rule(unittest.TestCase):
    def test_every_minute_has_one_phrase_and_no_digits(self):
        said = {H.hour(h, m) for h in range(24) for m in range(60)}
        # 12 hours x 60 minutes, less the two named ones that replace «Las doce en punto».
        self.assertEqual(len(said), 12 * 60 - 1 + 2)
        self.assertFalse(any(c.isdigit() for p in said for c in p))
        self.assertTrue(all(p[0] in "LM" for p in said), "the swash capital is always L or M")


class Command(unittest.TestCase):
    def test_at_prints_the_phrase(self):
        r = run("--at", "22:15")
        self.assertEqual((r.returncode, r.stdout), (0, "Las diez y cuarto\n"), r.stderr)

    def test_part_prints_the_part_of_day(self):
        self.assertEqual(run("--at", "07:05", "--parte").stdout, "de la mañana\n")
        self.assertEqual(run("--at", "00:00", "--parte").stdout, "\n")

    def test_pango_puts_the_swash_on_the_first_letter_only(self):
        r = run("--at", "13:45", "--pango")
        self.assertEqual(r.stdout, '<span font_features="swsh">L</span>as dos menos cuarto\n')

    def test_pango_colours_the_swash_when_asked(self):
        r = run("--at", "00:00", "--pango", "--color", "#e2bf76")
        self.assertEqual(r.stdout, '<span font_features="swsh" foreground="#e2bf76">M</span>edianoche\n')
        bad = run("--pango", "--color", "red\"><b")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("#rrggbb", bad.stderr)

    def test_date_is_written_as_the_desk_writes_it(self):
        for day, words in (("2026-11-19", "jueves, diecinueve de noviembre"),
                           ("2026-03-01", "domingo, uno de marzo"),
                           ("2028-02-29", "martes, veintinueve de febrero"),
                           ("2026-12-31", "jueves, treinta y uno de diciembre")):
            with self.subTest(day=day):
                r = run("--fecha", "--dia", day)
                self.assertEqual((r.returncode, r.stdout), (0, words + "\n"), r.stderr)
        for bad in ("2026-02-30", "19/11/2026", "２０２６-11-19"):
            with self.subTest(dia=bad):
                r = run("--fecha", "--dia", bad)
                self.assertEqual(r.returncode, 2)
                self.assertIn("AAAA-MM-DD", r.stderr)
        self.assertEqual(run("--fecha").returncode, 0)

    def test_bad_time_is_refused_with_a_reason(self):
        for bad in ("24:00", "7", "12:60", "aa:bb", "٠٩:٠٥", "9:05"):
            with self.subTest(at=bad):
                r = run("--at", bad)
                self.assertEqual(r.returncode, 2)
                self.assertIn("HH:MM", r.stderr)

    def test_now_is_one_of_the_phrases(self):
        r = run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(r.stdout.strip(), {H.hour(h, m) for h in range(24) for m in range(60)})


if __name__ == "__main__":
    unittest.main()
