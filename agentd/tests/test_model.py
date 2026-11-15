import tempfile
import unittest
from pathlib import Path

from agentd.claude import ClaudeHome
from agentd.hypr import FakeHypr
from agentd.model import Session, Window, Workspace, collect
from agentd.procfs import Proc
from world import NOW, World, ack, ai_title, main_world, note, tool, turn_end


def snap_of(w: World):
    r = w.root
    return collect(FakeHypr(r / "hypr"), Proc(r / "proc"),
                   ClaudeHome(r / "claude", clock=lambda: NOW), str(r / "fs"))


class MainWorldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.s = snap_of(main_world(Path(cls.tmp.name)))
        cls.by_pid = {x.pid: x for x in cls.s.sessions}
        cls.ws = {(w.output, w.id): w for w in cls.s.workspaces}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_outputs_and_focus(self):
        self.assertTrue(self.s.connected)
        self.assertEqual(self.s.outputs, ["DP-1", "HDMI-A-1"])
        self.assertEqual(self.s.focused_ws, 2)

    def test_slots_follow_rules_and_an_unplugged_rule_falls_back_to_the_live_monitor(self):
        # 1..5 always; past that only occupied or active. 6 holds only a hidden
        # window, 10 is empty; 11's rule names an unplugged monitor.
        self.assertEqual(sorted(self.ws), [("DP-1", i) for i in range(1, 6)]
                         + [("HDMI-A-1", 9), ("HDMI-A-1", 11)])

    def test_only_live_matching_visible_sessions_in_contract_order(self):
        # waiting oldest first, busy newest first, then the rest newest first.
        # Gone: sdk ghost 2100, reused pid 2200, torn file 2300, no procStart 2500.
        self.assertEqual([x.pid for x in self.s.sessions], [1103, 1003, 2000, 1404, 1203, 2400])
        self.assertEqual(self.s.counts, {"waiting": 1, "busy": 2, "idle": 3})

    def test_kitty_kitten_fish_claude_chain_maps_session_to_window(self):
        s = self.by_pid[1003]
        self.assertEqual((s.window, s.workspace, s.project), ("0x5500000002", 2, "ryce-pc"))
        self.assertEqual((s.source, s.lines), ("ahora", ["Generar el fondo de pantalla",
                                                         "Validar la barra en el escenario"]))
        self.assertEqual((s.title, s.name), ("Montar el rice del PC nuevo", None))
        # a3 finished two hours ago: past SUBAGENT_KEEP_S, no longer listed.
        self.assertEqual([(a.id, a.live) for a in s.subagents], [("a1", True), ("a2", True)])
        self.assertEqual((s.doing, s.asked, s.waiting_on),
                         ("Generar el fondo de pantalla",       # the second bullet does not fit whole
                          "Haz el fondo de pantalla de la peonza para cada tema.", None))

    def test_waiting_session_is_the_only_tag_wanted(self):
        s = self.by_pid[1103]
        self.assertEqual((s.state, s.waiting_for, s.tagged), ("waiting", "permission prompt", True))
        self.assertEqual((s.source, s.lines), ("tool", ["Probar el login en el navegador"]))
        self.assertEqual(self.s.desired_tags, {"0x5500000003"})
        self.assertEqual(self.s.current_tags, {"0x5500000004"})
        self.assertFalse(any(x.tagged for x in self.s.sessions if x.pid != 1103))

    def test_idle_session_in_a_subdirectory_with_a_user_name(self):
        s = self.by_pid[1203]
        self.assertEqual((s.project, s.name, s.source), ("web-de-ejemplo", "blog", "hecho"))
        self.assertEqual(s.lines, ["Entrada publicada en borrador", "Imágenes optimizadas con sharp"])
        self.assertEqual(s.did, "Entrada publicada en borrador")

    def test_background_claude_under_a_prompt_still_owns_the_window(self):
        s = self.by_pid[1404]
        self.assertEqual((s.state, s.window, s.source), ("shell", "0x5500000006", "away"))
        self.assertEqual(s.lines, ["Estabas revisando los atajos de teclado. Siguiente paso: probarlos."])

    def test_windowless_and_unknown_sessions(self):
        bg, unk = self.by_pid[2000], self.by_pid[2400]
        self.assertEqual((bg.kind, bg.window, bg.workspace, bg.source), ("bg", None, None, "away"))
        self.assertEqual((unk.state, unk.since, unk.title, unk.project, unk.source),
                         ("unknown", None, None, "lameiro0x", "none"))
        self.assertEqual(bg.since, NOW - 300)

    def test_workspace_heads(self):
        want = {
            1: ("browser", "Pull request #12 · lameiro0x/peonza-dots", None),
            2: ("claude", "ryce-pc", "busy"),
            3: ("claude", "brujula", "waiting"),
            4: ("claude", "web-de-ejemplo", "idle"),
            5: ("claude", "teclados", "idle"),
            9: ("code", "main.py - agentd", None),
            11: ("term", "Downloads", None),
        }
        got = {w.id: (w.kind, w.label, w.state) for w in self.s.workspaces if w.occupied}
        self.assertEqual(got, want)
        self.assertEqual(self.ws[("DP-1", 4)].windows[1].kind, "nvim")
        self.assertEqual(self.ws[("DP-1", 4)].windows[1].label, "notes")
        self.assertNotIn(("DP-1", 6), self.ws)             # only a hidden window there

    def test_focused_window_per_output(self):
        f = self.s.focused
        self.assertEqual((f["DP-1"].address, f["HDMI-A-1"].address), ("0x5500000002", "0x5500000008"))
        self.assertEqual(f["DP-1"].lead.pid, 1003)


class EdgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = World(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_compositor_still_lists_sessions(self):
        self.w.proc(10, "claude")
        self.w.session(10, 1, "/r/a", "busy")
        s = snap_of(self.w)        # no hypr/*.json written
        self.assertFalse(s.connected)
        self.assertEqual((s.outputs, s.workspaces, s.focused_ws), ([], [], None))
        self.assertEqual([(x.pid, x.window) for x in s.sessions], [(10, None)])

    def test_label_comes_from_the_foreground_session_not_the_newest(self):
        self.w.monitor(0, "DP-1", 1, True)
        self.w.terminal(100, "/r/fg", fg="claude", bg="claude")
        self.w.client("0xa", 1, "kitty", "t", 100, 0)
        self.w.session(103, 1, "/r/fg", "idle", ago=900)
        self.w.session(104, 2, "/r/bg", "waiting", ago=5, waitingFor="input needed")
        self.w.save()
        s = snap_of(self.w)
        ws = s.workspaces[0]
        self.assertEqual((ws.head.label, ws.state), ("fg", "waiting"))
        # The slot names the session it rings for, the workspace's lead.
        self.assertEqual(ws.label, "bg")
        self.assertEqual(s.desired_tags, {"0xa"})

    def test_without_rules_one_monitor_shows_the_first_five_and_the_active_one(self):
        self.w.monitor(0, "HEADLESS-1", 8, True)
        self.w.workspace(8, "HEADLESS-1")
        self.w.save()
        s = snap_of(self.w)
        self.assertEqual([(w.id, w.active) for w in s.workspaces],
                         [(1, False), (2, False), (3, False), (4, False), (5, False), (8, True)])

    def test_a_workspace_with_a_session_is_its_slot_whichever_window_was_focused_last(self):
        self.w.monitor(0, "DP-1", 1, True)
        self.w.terminal(100, "/home/u/Downloads")
        self.w.client("0xa", 1, "kitty", "fish", 100, 0)           # the plain terminal, focused last
        self.w.terminal(200, "/r/a", fg="claude")
        self.w.client("0xb", 1, "kitty", "✳ a", 200, 1)
        self.w.session(203, 1, "/r/a", "idle")
        ws = snap_of(self.w.save()).workspaces[0]
        self.assertEqual((ws.head.kind, ws.kind, ws.label, ws.lead.pid), ("term", "claude", "a", 203))
        self.w.clients.pop()                                       # the Claude window closes
        ws = snap_of(self.w.save()).workspaces[0]
        self.assertEqual((ws.kind, ws.label, ws.lead), ("term", "Downloads", None))

    def test_a_rule_naming_a_monitor_by_description_is_that_monitor(self):
        # Hyprland's `desc:` selector is a prefix of the description. An empty
        # workspace 1 ruled onto DP-1 that way is still DP-1's slot.
        self.w.monitor(0, "HDMI-A-1", 9, False)
        self.w.monitor(1, "DP-1", 2, True)
        self.w.monitors[0]["description"] = "Samsung Electric Company S24F350 H4ZN701082"
        self.w.monitors[1]["description"] = "AOC 24G2W1G4 ATNN21A005487"
        for i in range(1, 9):
            self.w.rule(i, "desc:AOC 24G2W1G4")
        for i in (9, 10):
            self.w.rule(i, "desc:Samsung Electric Company S24F350 H4ZN701082")
        self.w.rule(11, "desc:Unplugged Monitor")
        self.w.save()
        got = [(w.output, w.id) for w in snap_of(self.w).workspaces]
        self.assertEqual(got, [("HDMI-A-1", 9)] + [("DP-1", i) for i in range(1, 6)])

    def test_two_windows_of_one_process_host_nothing(self):
        # kitty's new_os_window: one pid, two windows. Which one holds the
        # session is unknowable from /proc, so neither rings nor gets the tag.
        self.w.monitor(0, "DP-1", 1, True)
        self.w.terminal(100, "/r/a", fg="claude")
        self.w.client("0xa", 1, "kitty", "a", 100, 0)
        self.w.client("0xb", 2, "kitty", "b", 100, 1)
        self.w.session(103, 1, "/r/a", "waiting", waitingFor="input needed")
        self.w.save()
        s = snap_of(self.w)
        self.assertEqual(s.desired_tags, set())
        self.assertEqual([w.state for w in s.workspaces if w.occupied], [None, None])
        self.assertEqual((s.sessions[0].window, s.sessions[0].state), (None, "waiting"))

    def test_window_titles_are_one_printable_line(self):
        self.w.monitor(0, "DP-1", 1, True)
        self.w.client("0xa", 1, "firefox", "uno\ndos\u202e" + "x" * 5000 + " — Mozilla Firefox", 1, 0)
        self.w.save()
        win = snap_of(self.w).workspaces[0].head
        self.assertTrue(win.title.startswith("uno dos x"))
        self.assertLessEqual(len(win.title), 512)
        self.assertNotIn("\n", win.label)

    def test_title_survives_and_name_only_when_user_given(self):
        self.w.proc(10, "claude")
        self.w.session(10, 1, "/r/a", "idle", name="mi-nombre", nameSource="rename")
        self.w.transcript(1, "/r/a", [ai_title("Título")])
        s = snap_of(self.w).sessions[0]
        self.assertEqual((s.title, s.name), ("Título", "mi-nombre"))


class AttachTest(unittest.TestCase):
    """`claude` can run a session in Claude Code's daemon (kind bg) and leave
    only a `claude attach <job>` client in the terminal: the session's own
    process is under no window, the client is."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = World(Path(self.tmp.name))
        self.w.monitor(0, "DP-1", 3, True)
        # The daemon's tree: claude → worker → the session (no window above it).
        self.w.proc(900, "claude", children=[901])
        self.w.proc(901, "2.1.325", 900, children=[902])
        self.w.proc(902, "2.1.325", 901, cwd="/r/a")
        self.w.session(902, 1, "/r/a", "idle", kind="bg", jobId="0b6f3f7e")
        self.w.terminal(100, "/home/u")                        # the terminal opened first
        self.w.terminal(200, "/r/a", fg="claude")
        self.attach("claude", "/home/u/.local/bin/claude", "attach", "0b6f3f7e")

    def tearDown(self):
        self.tmp.cleanup()

    def attach(self, comm, *argv):
        self.w.proc(203, comm, 202, tpgid=203, argv=argv)         # terminal() made 203

    def snap(self, *clients):
        self.w.clients = []
        for addr, pid, focus in clients:
            self.w.client(addr, 3, "kitty", "t", pid, focus)
        return snap_of(self.w.save())

    def test_the_attached_session_lives_in_the_attaching_window(self):
        s = self.snap(("0xa", 100, 1), ("0xb", 200, 0))
        self.assertEqual((s.sessions[0].window, s.sessions[0].workspace), ("0xb", 3))
        ws = s.workspaces[2]
        self.assertEqual((ws.kind, ws.label, ws.state, ws.lead.pid), ("claude", "a", "idle", 902))
        self.assertEqual(ws.windows[0].lead.pid, 902)

    def test_closing_the_first_terminal_leaves_a_claude_workspace(self):
        s = self.snap(("0xb", 200, 0))
        self.assertEqual((s.workspaces[2].kind, s.workspaces[2].label), ("claude", "a"))

    def test_a_waiting_attached_session_rings_its_window(self):
        self.w.session(902, 1, "/r/a", "waiting", kind="bg", jobId="0b6f3f7e", waitingFor="input needed")
        self.assertEqual(self.snap(("0xa", 100, 0), ("0xb", 200, 1)).desired_tags, {"0xb"})

    def test_a_session_id_prefix_names_the_job_too(self):
        self.w.session(902, 1, "/r/a", "idle", kind="bg")
        self.assertEqual(self.snap(("0xb", 200, 0)).sessions[0].window, "0xb")

    def test_an_attach_that_names_no_session_or_too_little_claims_nothing(self):
        for argv in (("claude", "attach", "deadbeef"), ("claude", "attach", "0b6f"),
                     ("claude", "attach"), ("claude", "attach", "--help"), ("vim", "attach", "0b6f3f7e")):
            with self.subTest(argv=argv):
                self.attach("claude", *argv)
                s = self.snap(("0xb", 200, 0))
                self.assertEqual((s.sessions[0].window, s.workspaces[2].kind), (None, "term"))

    def test_two_sessions_behind_one_job_id_claim_nothing(self):
        self.w.proc(950, "2.1.325", cwd="/r/b")
        self.w.session(950, 2, "/r/b", "idle", kind="bg", jobId="0b6f3f7e")
        self.assertEqual([x.window for x in self.snap(("0xb", 200, 0)).sessions], [None, None])

    def test_a_session_under_a_window_is_not_also_claimed_by_an_attach(self):
        self.w.proc(100, "kitty", children=[101, 902])
        s = self.snap(("0xa", 100, 1), ("0xb", 200, 0))
        self.assertEqual(s.sessions[0].window, "0xa")
        self.assertEqual(s.workspaces[2].windows[0].kind, "term")


class BackgroundTest(unittest.TestCase):
    """A turn that ended with its own background work out keeps the session working."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = World(Path(self.tmp.name))
        self.w.proc(10, "claude")

    def tearDown(self):
        self.tmp.cleanup()

    def one(self, status, *records):
        self.w.session(10, 1, "/r/a", status)
        self.w.transcript(1, "/r/a", [ai_title("t"), *records])
        s = snap_of(self.w)
        return s.sessions[0], s.counts

    def test_idle_with_a_background_shell_is_busy_waiting_on_it(self):
        s, counts = self.one("idle", tool("Bash", "Correr los tests", tid="t1", run_in_background=True),
                             ack("t1", backgroundTaskId="b1"), turn_end())
        self.assertEqual((s.state, s.waiting_on, s.doing), ("busy", "shell", "Correr los tests"))
        self.assertEqual(counts["busy"], 1)

    def test_shell_status_with_a_pending_agent_is_busy_waiting_on_the_agent(self):
        s, _ = self.one("shell", tool("Bash", "x", tid="t1", run_in_background=True),
                        tool("Agent", "Revisar", tid="t2", run_in_background="true"), turn_end())
        self.assertEqual((s.state, s.waiting_on), ("busy", "agent"))

    def test_once_reported_back_it_is_idle_again(self):
        s, _ = self.one("idle", tool("Bash", "x", tid="t1", run_in_background=True), turn_end(),
                        note("t1", "completed"))
        self.assertEqual((s.state, s.waiting_on, s.doing), ("idle", None, ""))

    def test_a_launch_from_before_the_process_started_is_dead(self):
        # startedAt is NOW - 9000; the launch is older (a resumed session).
        s, _ = self.one("idle", tool("Bash", "x", tid="t1", run_in_background=True,
                                     at="2026-11-09T07:00:00.000Z"), turn_end())
        self.assertEqual((s.state, s.waiting_on), ("idle", None))

    def test_an_agent_whose_meta_finished_is_not_waited_on(self):
        self.w.subagent(1, "/r/a", "a1", NOW - 30, finished=True, tool_use="t2")
        s, _ = self.one("idle", tool("Agent", "Revisar", tid="t2", run_in_background="true"), turn_end())
        self.assertEqual((s.state, s.waiting_on), ("idle", None))

    def test_waiting_stays_waiting(self):
        s, _ = self.one("waiting", tool("Bash", "x", tid="t1", run_in_background=True))
        self.assertEqual((s.state, s.waiting_on), ("waiting", None))

    def test_an_idle_session_lists_no_subagents(self):
        self.w.subagent(1, "/r/a", "a1", NOW - 30)
        s, _ = self.one("idle")
        self.assertEqual(s.subagents, [])


def _s(sid, state, since=None):
    return Session(pid=0, sid=sid, kind="interactive", cwd="/r/x", project="x", title=None, name=None,
                   state=state, waiting_for=None, since=since, source="none", lines=[], subagents=[])


def _w(addr, *sessions, lead=None):
    return Window(addr, 1, 0, "claude", "x", "", list(sessions), lead or (sessions[0] if sessions else None))


class LeadTest(unittest.TestCase):
    """The workspace's lead: what a bar shows for the slot (roster `lead`)."""

    def lead(self, *windows):
        ws = Workspace(1, "DP-1", False, list(windows))
        return ws.lead.sid if ws.lead else None

    def test_no_sessions_no_lead(self):
        self.assertIsNone(self.lead())
        self.assertIsNone(self.lead(Window("0x1", 1, 0, "browser", "x", "")))

    def test_waiting_beats_busy_beats_the_rest_wherever_it_is(self):
        self.assertEqual(self.lead(_w("0x1", _s("idle", "idle", 1)), _w("0x2", _s("busy", "busy", 2)),
                                   _w("0x3", _s("wait", "waiting", 3))), "wait")
        self.assertEqual(self.lead(_w("0x1", _s("shell", "shell", 1), _s("unk", "unknown", 0)),
                                   _w("0x2", _s("busy", "busy", 9))), "busy")

    def test_a_tie_goes_to_the_most_recently_focused_window(self):
        # Windows are kept most recently focused first.
        self.assertEqual(self.lead(_w("0x1", _s("new", "busy", 200)), _w("0x2", _s("old", "busy", 100))), "new")

    def test_inside_a_window_the_session_naming_it_wins_then_the_oldest(self):
        a, b, c = _s("a", "busy", 300), _s("b", "busy", 100), _s("c", "busy", None)
        self.assertEqual(self.lead(_w("0x1", a, b, c, lead=a)), "a")
        self.assertEqual(self.lead(_w("0x1", a, b, c, lead=_s("z", "idle"))), "b")
        self.assertEqual(self.lead(_w("0x1", _s("y", "idle"), _s("x", "idle"), lead=_s("z", "idle"))), "x")

    def test_main_world_leads(self):
        with tempfile.TemporaryDirectory() as t:
            s = snap_of(main_world(Path(t)))
        leads = {(w.output, w.id): (w.lead.pid if w.lead else None) for w in s.workspaces}
        self.assertEqual(leads[("DP-1", 2)], 1003)
        self.assertEqual(leads[("DP-1", 3)], 1103)
        self.assertEqual(leads[("DP-1", 5)], 1404)
        self.assertIsNone(leads[("DP-1", 1)])


if __name__ == "__main__":
    unittest.main()
