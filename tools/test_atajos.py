#!/usr/bin/env python3
"""Tests for tools/atajos.py's second output, the SUPER+F1 cheat sheet's JSON.

    python3 -m unittest discover -s tools -p 'test_atajos.py'
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atajos  # noqa: E402


def rows(groups: list[dict], title: str) -> list[dict]:
    return next(g["rows"] for g in groups if g["title"] == title)


class Cheatsheet(unittest.TestCase):
    def setUp(self) -> None:
        self.groups = atajos.cheatsheet(atajos.SRC.read_text(encoding="utf-8"))["groups"]

    def test_groups_in_order_and_none_empty(self) -> None:
        titles = [g["title"] for g in self.groups]
        self.assertEqual(titles, [t for t in atajos.GROUPS if t in titles])
        self.assertTrue(all(g["rows"] for g in self.groups))
        self.assertEqual(titles[:2], ["Ventanas", "Workspaces"])

    def test_a_series_reads_as_one_row(self) -> None:
        ws = rows(self.groups, "Workspaces")
        go = [r for r in ws if r["keys"][0] == "Ctrl" and len(r["keys"]) == 2 and r["keys"][1].startswith("1")]
        self.assertEqual(len(go), 1, ws)
        self.assertEqual(go[0], {"keys": ["Ctrl", "1 … 0"], "what": "Ir a un workspace (1–10)"})
        steps = [r for r in ws if r["keys"] == ["Ctrl", "← →"]]
        self.assertEqual(steps, [{"keys": ["Ctrl", "← →"], "what": "Workspace anterior / siguiente; en el borde pasa a la otra pantalla"}])
        self.assertNotIn("11", json.dumps(ws, ensure_ascii=False))
        focus = [r for r in rows(self.groups, "Ventanas") if r["what"] == "Mover el foco"]
        self.assertEqual(focus[0]["keys"], ["Ctrl", "H L K J"])

    def test_screens_have_their_own_group(self) -> None:
        self.assertEqual(rows(self.groups, "Pantallas"), [
            {"keys": ["Ctrl", "Tab"], "what": "Foco a la otra pantalla"},
            {"keys": ["Ctrl", "Mayús", "Tab"], "what": "Mover la ventana a la otra pantalla"},
            {"keys": ["Ctrl", "Alt", "← →"], "what": "Foco a la pantalla de la izquierda / derecha"},
            {"keys": ["Ctrl", "Super", "← →"], "what": "Mover la ventana a la otra pantalla"},
        ])

    def test_songs_without_media_keys(self) -> None:
        songs = {r["what"]: r["keys"] for r in rows(self.groups, "Sonido") if r["keys"][0] == "Alt"}
        self.assertEqual(songs, {
            "Canción siguiente": ["Alt", "Super", "→"],
            "Canción anterior": ["Alt", "Super", "←"],
            "Pausar o seguir la música": ["Alt", "Super", "Espacio"],
        })

    def test_every_bind_lands_somewhere(self) -> None:
        text = atajos.SRC.read_text(encoding="utf-8")
        series = sum(len(r["keys"][-1].split()) if r["what"] in atajos.SERIES.values() else 1
                     for g in self.groups for r in g["rows"])
        self.assertLessEqual(series, len(atajos.gen.parse(text)))
        self.assertTrue(all(r["what"] and r["keys"] for g in self.groups for r in g["rows"]))

    def test_new_rows_flow_through(self) -> None:
        text = "\n".join([
            "SUPER\th\texec\tqs -c ryce ipc call hito toggle",
            "SUPER\tF1\texec\tqs -c ryce ipc call keys toggle",
            "SUPER\tm\texec\tqs -c ryce ipc call aria toggle",
            "SUPER SHIFT\tw\texec\t~/.local/bin/ryce-wall next",
            "-\tXF86AudioPlay\texec\tplayerctl play-pause\tlocked",
        ])
        groups = atajos.cheatsheet(text)["groups"]
        ryce = rows(groups, "ryce")
        self.assertEqual([r["keys"] for r in ryce],
                         [["Super", "H"], ["Super", "F1"], ["Super", "M"], ["Mayús", "Super", "W"]])
        self.assertNotIn("Ejecutar", " ".join(r["what"] for r in ryce))
        self.assertEqual(rows(groups, "Sonido")[0]["keys"], ["Play"])


    def test_desk_keyboard_and_wallpaper_rows(self) -> None:
        text = "\n".join([
            "SUPER\te\tcall\tryce.despejar",
            "SUPER\tspace\texec\thyprctl switchxkblayout all next",
            "SUPER SHIFT\tw\texec\tqs -c ryce ipc call wallpick toggle",
        ])
        groups = atajos.cheatsheet(text)["groups"]
        self.assertEqual(rows(groups, "Ventanas"), [{"keys": ["Super", "E"], "what": "Despejar el escritorio"}])
        self.assertEqual(rows(groups, "ryce"), [
            {"keys": ["Super", "Espacio"], "what": "Cambiar teclado inglés/español"},
            {"keys": ["Mayús", "Super", "W"], "what": "Elegir fondo"},
        ])


class Check(unittest.TestCase):
    def test_check_covers_the_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            md, js = Path(tmp) / "atajos.md", Path(tmp) / "atajos.json"
            md.write_text(atajos.render(), encoding="utf-8")
            js.write_text("{}\n", encoding="utf-8")
            old = atajos.OUT, atajos.JSON_OUT
            atajos.OUT, atajos.JSON_OUT = md, js
            try:
                self.assertEqual(atajos.main(["--check"]), 1)
                js.write_text(atajos.render_json(), encoding="utf-8")
                self.assertEqual(atajos.main(["--check"]), 0)
                json.loads(js.read_text(encoding="utf-8"))
            finally:
                atajos.OUT, atajos.JSON_OUT = old


if __name__ == "__main__":
    unittest.main()
