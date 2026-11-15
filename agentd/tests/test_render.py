import json
import sys
import tempfile
import unittest
from pathlib import Path

from agentd import render
from agentd.claude import Subagent
from agentd.model import Session, Snapshot, Window, Workspace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "contracts"))
import check_roster  # noqa: E402

THEMES = {t: REPO / "themes" / t / "theme.json"
          for t in json.loads((REPO / "contracts" / "constants.json").read_text())["themes"]}
PAL = render.load_palette(THEMES["origen"])
CLAUDE = "\U000f1719"
CONSOLE = "\U000f018d"


def I(s):
    """A label as it appears in markup: wrapped in FSI … PDI."""
    return f"⁨{s}⁩"


def sess(pid=1, state="busy", project="ryce-pc", title="Montar el rice del PC nuevo",
         lines=("Generar el fondo de pantalla", "Validar la barra en el escenario"), source="ahora",
         **kw):
    base = dict(pid=pid, sid=f"s{pid}", kind="interactive", cwd=f"/r/{project}", project=project,
                title=title, name=None, state=state, waiting_for=None, since=100.0 + pid,
                source=source, lines=list(lines), subagents=[])
    base.update(kw)
    return Session(**base)


def claude_win(s, ws, addr="0xa", focus=0):
    s.window, s.workspace = addr, ws
    return Window(addr, ws, focus, "claude", s.project, "✳ x", [s], s)


def snap(workspaces, sessions=(), focused=None, outputs=("DP-1",)):
    return Snapshot(True, list(outputs), 1, workspaces, focused or {o: None for o in outputs},
                    list(sessions), set(), set())


def row(n, **kw):
    """n occupied Claude slots on DP-1; returns the payloads."""
    ss = [sess(pid=i, **kw) for i in range(1, n + 1)]
    return render.waybar(snap([Workspace(i, "DP-1", False, [claude_win(ss[i - 1], i, f"0x{i}")])
                               for i in range(1, n + 1)], ss), PAL)


def label_and_title(payload):
    """(label, title or None) as shown, isolates removed."""
    spans = [x.split(">", 1)[1] for x in payload["text"].split("</span>") if ">" in x]
    title = spans[3].removeprefix(" · ").strip("⁨⁩") if len(spans) > 3 else None
    return spans[2].strip("⁨⁩"), title


class SlotTest(unittest.TestCase):
    def test_waiting_slot_off_focus(self):
        s = sess(state="waiting", project="brujula", title="Arreglar el login con passkeys",
                 lines=["Probar el login en el navegador"], source="tool", waiting_for="permission prompt")
        out = render.waybar(snap([Workspace(3, "DP-1", False, [claude_win(s, 3)])], [s]), PAL)
        self.assertEqual(out["DP-1-3.json"], {
            "text": f'<span foreground="#bdae93">3</span> <span foreground="#ae9f90">{CLAUDE}</span> '
                    f'<span foreground="#ebdbb2">{I("brujula")}</span>'
                    f'<span foreground="#bdae93"> · {I("Arreglar el login con passkeys")}</span>',
            "tooltip": "brujula — Arreglar el login con passkeys\n• Probar el login en el navegador\n"
                       "pide permiso",
            "class": ["occupied", "waiting"]})

    def test_active_working_slot_is_ink_on_pill(self):
        s = sess(subagents=[Subagent(f"a{i}", "Explore", "x", i < 3, "", 0.0) for i in range(4)])
        out = render.waybar(snap([Workspace(2, "DP-1", True, [claude_win(s, 2)])], [s]), PAL)
        self.assertEqual(out["DP-1-2.json"], {
            "text": f'<span foreground="#665c54">2</span> <span foreground="#665c54">{CLAUDE}</span> '
                    f'<span foreground="#1d2021">{I("ryce-pc")}</span>'
                    f'<span foreground="#665c54"> · {I("Montar el rice del PC nuevo")}</span>',
            "tooltip": "ryce-pc — Montar el rice del PC nuevo\n• Generar el fondo de pantalla\n"
                       "• Validar la barra en el escenario\ntrabajando · 3 subagentes",
            "class": ["occupied", "active", "working"]})

    def test_working_icon_warms_one_step_off_focus(self):
        text = row(1)["DP-1-1.json"]["text"]
        self.assertIn(f'<span foreground="#bdae93">{CLAUDE}</span>', text)

    def test_terminal_icon_is_a_console(self):
        w = Window("0x1", 1, 0, "term", "Downloads", "fish")
        text = render.waybar(snap([Workspace(1, "DP-1", False, [w])]), PAL)["DP-1-1.json"]["text"]
        self.assertIn(CONSOLE, text)

    def test_a_session_names_its_slot_over_a_terminal_focused_later(self):
        s = sess(state="idle", project="brujula", title="Arreglar el login")
        term = Window("0xa", 3, 0, "term", "Downloads", "fish")
        out = render.waybar(snap([Workspace(3, "DP-1", False, [term, claude_win(s, 3, "0xb", 1)])], [s]), PAL)
        self.assertIn(CLAUDE, out["DP-1-3.json"]["text"])
        self.assertEqual(label_and_title(out["DP-1-3.json"]), ("brujula", "Arreglar el login"))

    def test_idle_and_shell_tooltips_use_the_shared_words(self):
        s = sess(state="idle", project="web-de-ejemplo", title="Nueva entrada del blog", source="hecho",
                 lines=["Entrada publicada en borrador", "Imágenes optimizadas"])
        tip = render.waybar(snap([Workspace(4, "DP-1", False, [claude_win(s, 4)])], [s]), PAL)["DP-1-4.json"]["tooltip"]
        self.assertEqual(tip, "web-de-ejemplo — Nueva entrada del blog\nhecho: Entrada publicada en borrador")
        s = sess(state="shell", title=None, lines=[], source="none")
        tip = render.waybar(snap([Workspace(4, "DP-1", False, [claude_win(s, 4)])], [s]), PAL)["DP-1-4.json"]["tooltip"]
        self.assertEqual(tip, "ryce-pc\ncomando en marcha")

    def test_an_unknown_waiting_reason_falls_back_to_plain_spanish(self):
        s = sess(state="waiting", waiting_for="quantum flux request")
        tip = render.waybar(snap([Workspace(1, "DP-1", False, [claude_win(s, 1)])], [s]), PAL)["DP-1-1.json"]["tooltip"]
        self.assertTrue(tip.endswith("\nte espera"))
        self.assertNotIn("quantum", tip)

    def test_empty_and_off_slots(self):
        out = render.waybar(snap([Workspace(5, "DP-1", False, []), Workspace(6, "DP-1", True, [])]), PAL)
        self.assertEqual(out["DP-1-5.json"], {"text": "五", "tooltip": "", "class": ["empty"]})
        self.assertEqual(out["DP-1-6.json"], {"text": "六", "tooltip": "", "class": ["empty", "active"]})
        self.assertEqual(out["DP-1-11.json"], {"text": "", "tooltip": "", "class": ["off"]})
        self.assertEqual(len([k for k in out if k.startswith("DP-1-") and k != "DP-1-window.json"]), 11)

    def test_untrusted_text_is_escaped_for_pango_and_isolated(self):
        w = Window("0xb", 1, 0, "browser", "Tom & <b>Jerry</b> en el jardín de casa", "x")
        out = render.waybar(snap([Workspace(1, "DP-1", False, [w])], focused={"DP-1": w}), PAL)
        self.assertIn(I("Tom &amp; &lt;b&gt;Jerry&lt;/b&gt; en el jardín de casa"), out["DP-1-1.json"]["text"])
        self.assertNotIn("<b>", out["DP-1-1.json"]["tooltip"] + out["DP-1-window.json"]["text"])

    def test_width_depends_on_load_never_on_focus(self):
        wins = [Window(f"0x{i}", i, i, "term", "inventario-de-subredes", "") for i in range(1, 9)]
        a = render.waybar(snap([Workspace(i, "DP-1", i == 1, [wins[i - 1]]) for i in range(1, 9)]), PAL)
        b = render.waybar(snap([Workspace(i, "DP-1", i == 2, [wins[i - 1]]) for i in range(1, 9)]), PAL)
        self.assertEqual(label_and_title(a["DP-1-1.json"]), ("inven…edes", None))    # 8 occupied: 10 cells
        self.assertEqual(label_and_title(a["DP-1-1.json"]), label_and_title(b["DP-1-1.json"]))

    def test_names_clip_from_the_middle_and_page_titles_from_the_tail(self):
        wins = [Window("0x1", 1, 0, "term", "radio-web.github.io-old-mirror-backup-2024", ""),
                Window("0x2", 2, 1, "browser", "Pull request #12 · lameiro0x/peonza-dots · GitHub", "")]
        wins += [Window(f"0x{i}", i, i, "term", "x", "") for i in (3, 4)]
        out = render.waybar(snap([Workspace(i + 1, "DP-1", False, [w]) for i, w in enumerate(wins)]), PAL)
        # Four occupied: 26 cells each, no title on either.
        self.assertEqual(label_and_title(out["DP-1-1.json"])[0], "radio-web.git…backup-2024")
        self.assertEqual(label_and_title(out["DP-1-2.json"])[0], "Pull request #12…")

    def test_title_takes_what_the_label_leaves_and_shrinks_with_load(self):
        self.assertEqual(label_and_title(row(2)["DP-1-1.json"]), ("ryce-pc", "Montar el rice del PC nuevo"))
        self.assertEqual(label_and_title(row(4)["DP-1-1.json"]), ("ryce-pc", "Montar el rice…"))
        self.assertEqual(label_and_title(row(4, project="x")["DP-1-1.json"]), ("x", "Montar el rice del PC…"))
        self.assertEqual(label_and_title(row(5)["DP-1-1.json"]), ("ryce-pc", "Montar el…"))
        self.assertEqual(label_and_title(row(6)["DP-1-1.json"]), ("ryce-pc", None))
        self.assertEqual(label_and_title(row(8)["DP-1-1.json"]), ("ryce-pc", None))

    def test_a_label_gets_the_whole_budget_when_no_title_fits(self):
        self.assertEqual(label_and_title(row(8, project="inventario-de-subredes")["DP-1-1.json"]),
                         ("inven…edes", None))

    def test_wide_characters_count_double(self):
        out = row(8, project="漢字のリポジトリ名前")
        self.assertEqual(label_and_title(out["DP-1-1.json"])[0], "漢字…名前")


class WindowLineTest(unittest.TestCase):
    def line(self, s=None, w=None):
        w = w or claude_win(s, 2)
        return render.waybar(snap([Workspace(2, "DP-1", True, [w])], [s] if s else [],
                                  focused={"DP-1": w}), PAL)["DP-1-window.json"]

    def test_claude_window_line_is_project_and_what_it_does(self):
        self.assertEqual(self.line(sess()), {
            "text": f"{I('ryce-pc')} › {I('Generar el fondo de pantalla')}",
            "tooltip": "ryce-pc — Montar el rice del PC nuevo\n• Generar el fondo de pantalla\n"
                       "• Validar la barra en el escenario",
            "class": ["window", "claude"]})

    def test_without_doing_the_title_stands_in_and_without_either_the_project_alone(self):
        self.assertEqual(self.line(sess(lines=(), source="none"))["text"],
                         f"{I('ryce-pc')} › {I('Montar el rice del PC nuevo')}")
        self.assertEqual(self.line(sess(lines=(), source="none", title=None))["text"], I("ryce-pc"))

    def test_window_line_fits_the_left_island(self):
        s = sess(project="inventario-de-subredes-v2-final",
                 lines=["Validar la barra en el escenario con capturas de pantalla reales"])
        text = self.line(s)["text"]
        self.assertEqual(text, f"{I('inventario…v2-final')} › {I('Validar la barra en…')}")
        self.assertLessEqual(len(text.replace("⁨", "").replace("⁩", "")), render.WINDOW_WIDTH)

    def test_plain_and_empty_window_lines(self):
        w = Window("0xc", 9, 0, "code", "main.py - agentd", "main.py - agentd - Visual Studio Code")
        self.assertEqual(self.line(w=w), {"text": I("main.py - agentd - Visual Studio Code"),
                                          "tooltip": "main.py - agentd - Visual Studio Code",
                                          "class": ["window"]})
        out = render.waybar(snap([]), PAL)
        self.assertEqual(out["DP-1-window.json"], {"text": "", "tooltip": "", "class": ["empty"]})


class CountersTest(unittest.TestCase):
    def test_agents_counter_names_who_waits_first(self):
        ss = [sess(1, "waiting"), sess(2), sess(3), sess(4, "idle"), sess(5, "shell"), sess(6, "unknown")]
        self.assertEqual(render.agents(snap([], ss)), {
            "text": f"{CLAUDE} 1", "tooltip": "1 agente te espera · 2 trabajando · 3 en reposo",
            "class": ["waiting"]})
        self.assertEqual(render.agents(snap([], ss[1:3])), {
            "text": f"{CLAUDE} 2", "tooltip": "2 trabajando", "class": ["busy"]})
        self.assertEqual(render.agents(snap([], [])), {
            "text": f"{CLAUDE} 0", "tooltip": "sin agentes", "class": ["calm"]})
        self.assertEqual(render.agents(snap([], [sess(1, "waiting"), sess(2, "waiting")]))["tooltip"],
                         "2 agentes te esperan")

    def test_lock_line(self):
        self.assertEqual(render.lock_text(snap([], [sess(1, "idle")])), "")
        self.assertEqual(render.lock_text(snap([], [sess(1, "waiting")])), "1 agente te espera")
        self.assertEqual(render.lock_text(snap([], [sess(i, "waiting") for i in range(3)])), "3 agentes te esperan")

    def test_reset_slots_show_numerals_up_to_always_shown(self):
        self.assertEqual(render.idle_slot(3), {"text": "三", "tooltip": "", "class": ["empty"]})
        self.assertEqual(render.idle_slot(6), {"text": "", "tooltip": "", "class": ["off"]})


class RosterTest(unittest.TestCase):
    def test_roster_passes_the_contract_checker(self):
        s1, s2 = sess(1, "waiting", waiting_for="input needed"), sess(2, window="0xbad", workspace=None)
        s1.tagged = True
        doc = render.roster(snap([Workspace(3, "DP-1", False, [claude_win(s1, 3, "0x55d0")]),
                                  Workspace(4, "DP-1", False, [])], [s1, s2]), 1794220000.0)
        self.assertEqual(check_roster.check(doc), [])
        self.assertEqual(doc["sessions"][0]["waitingFor"], "input needed")
        self.assertEqual(doc["workspaces"][1], {"id": 4, "output": "DP-1", "active": False,
                                                "occupied": False, "label": "", "icon": "window",
                                                "state": None, "lead": None})
        self.assertEqual(doc["workspaces"][0]["lead"], "s1")

    def test_doing_asked_waiting_on_and_subagents_are_the_whole_session_story(self):
        s = sess(1, "busy", doing="Correr los tests", asked="Arregla la barra.", waiting_on="shell",
                 subagents=[Subagent("a1", "forge-scout", "Medir el contraste", True, "toolu_x", 5.0)])
        doc = render.roster(snap([], [s]), 0.0)
        got = {k: doc["sessions"][0][k] for k in ("doing", "asked", "did", "waiting_on", "subagents")}
        self.assertEqual(got, {"doing": "Correr los tests", "asked": "Arregla la barra.", "did": "",
                               "waiting_on": "shell",
                               "subagents": [{"id": "a1", "type": "forge-scout",
                                              "description": "Medir el contraste", "live": True}]})
        self.assertEqual(check_roster.check(doc), [])

    def test_the_checker_holds_the_session_story_to_its_promises(self):
        s = sess(1, "busy", doing="x", subagents=[Subagent("a1", "Explore", "d", True, "", 0.0)])
        good = render.roster(snap([], [s]), 0.0)
        cases = (("doing", "y" * 61, "doing"), ("asked", "<b>", "asked"), ("waiting_on", "pizza", "waiting_on"),
                 ("did", "a\nb", "did"), ("did", None, "did"),
                 ("subagents", [{"id": "a1", "type": "t", "description": "d"}], "subagents[0]"),
                 ("subagents", 2, "subagents"))
        for key, value, why in cases:
            bad = json.loads(json.dumps(good))
            bad["sessions"][0][key] = value
            self.assertTrue(any(why in e for e in check_roster.check(bad)), key)
        idle = json.loads(json.dumps(good))
        idle["sessions"][0].update(state="idle", waiting_on="shell")
        idle["counts"] = {"waiting": 0, "busy": 0, "idle": 1}
        self.assertTrue(any("waiting_on" in e for e in check_roster.check(idle)))
        del good["sessions"][0]["did"]
        self.assertEqual(check_roster.check(good), [], "did is optional")

    def test_did_is_published_as_it_came(self):
        doc = render.roster(snap([], [sess(1, "idle", did="Arreglé la barra")]), 0.0)
        self.assertEqual(doc["sessions"][0]["did"], "Arreglé la barra")

    def test_the_checker_holds_lead_to_its_promises(self):
        s1, s2 = sess(1, "waiting"), sess(2, "busy")
        doc = render.roster(snap([Workspace(3, "DP-1", False, [claude_win(s2, 3, "0x2"), claude_win(s1, 3, "0x1")])],
                                 [s1, s2]), 0.0)
        self.assertEqual(doc["workspaces"][0]["lead"], "s1")     # waiting beats the focused busy window
        for lead, why in (("nope", "listed session"), (None, "null exactly"), ("s2", "most urgent")):
            bad = json.loads(json.dumps(doc))
            bad["workspaces"][0]["lead"] = lead
            self.assertTrue(any(why in e for e in check_roster.check(bad)), lead)
        del doc["workspaces"][0]["lead"]
        self.assertEqual(check_roster.check(doc), [], "lead is optional")
        for icon, state in (("term", "waiting"), ("claude", None)):
            bad = json.loads(json.dumps(doc))
            bad["workspaces"][0].update(icon=icon, state=state)
            self.assertTrue(any("exactly when a session lives here" in e for e in check_roster.check(bad)), icon)

    def test_an_address_hyprland_never_sends_is_not_passed_on(self):
        s = sess(window='0x1"); hl.exec("x', workspace=1)
        doc = render.roster(snap([], [s]), 0.0)
        self.assertIsNone(doc["sessions"][0]["window"])


class PaletteTest(unittest.TestCase):
    def test_markup_carries_greys_only_in_every_theme(self):
        for theme, path in THEMES.items():
            with self.subTest(theme=theme):
                colors = json.loads(path.read_text())["colors"]
                pal = render.load_palette(path)
                self.assertEqual(pal, {k: colors[k] for k in render.GREYS})
                s, t = sess(1, state="waiting"), sess(2, state="waiting")
                out = json.dumps(render.waybar(snap([Workspace(1, "DP-1", True, [claude_win(s, 1)]),
                                                     Workspace(2, "DP-1", False, [claude_win(t, 2, "0xb")])],
                                                    [s, t]), pal)).lower()
                for role in ("signal", "signal_dim", "signal_on_pill"):
                    self.assertNotIn(colors[role].lower(), out, role)

    def test_missing_or_broken_palette_falls_back_to_built_in_greys(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(render.load_palette(Path(t) / "nope.json"), render.GREYS)
            bad = Path(t, "p.json")
            bad.write_text("{")
            self.assertEqual(render.load_palette(bad), render.GREYS)
            bad.write_text(json.dumps({"colors": {"fg0": "red", "fg1": "#123456"}}))
            pal = render.load_palette(bad)
            self.assertEqual((pal["fg0"], pal["fg1"]), (render.GREYS["fg0"], "#123456"))


if __name__ == "__main__":
    unittest.main()
