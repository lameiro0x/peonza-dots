"""The screen stays awake while a Claude Code session works (agentd/awake.py)."""

import io
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

import agentd.__main__ as entry
from agentd.__main__ import App, main
from agentd.awake import COMMAND, GRACE_S, LEASE, LOCKER, RETRY_S, STALE_S, Awake, working
from agentd.claude import ClaudeHome
from agentd.hypr import FakeHypr
from agentd.model import Session, collect
from agentd.procfs import Proc
from agentd.publish import Publisher
from world import NOW, World, ai_title, main_world, note, tool, turn_end
from world import sid as world_sid

AGENTD = Path(__file__).resolve().parents[1]
WIN = "0x5500000001"


def session(state, moved=None, agents_moved=None, waiting_on=None, window=WIN):
    return Session(pid=1, sid="s", kind="interactive", cwd="/r", project="r", title=None, name=None,
                   state=state, waiting_for=None, since=None, source="none", lines=[], subagents=[],
                   window=window, waiting_on=waiting_on, moved=moved, agents_moved=agents_moved)


class WorkingTest(unittest.TestCase):
    def test_a_turn_that_runs_and_writes_is_working(self):
        self.assertTrue(working(session("busy", moved=NOW - 5), NOW))

    def test_a_turn_silent_past_the_stale_limit_is_hung_not_working(self):
        self.assertTrue(working(session("busy", moved=NOW - STALE_S + 1), NOW))
        self.assertFalse(working(session("busy", moved=NOW - STALE_S), NOW))
        self.assertFalse(working(session("busy"), NOW))

    def test_a_timestamp_from_the_future_is_no_sign_of_life(self):
        # A clock stepped back, or a restored transcript: it must not dodge STALE_S.
        self.assertTrue(working(session("busy", moved=NOW + 30), NOW))
        self.assertFalse(working(session("busy", moved=NOW + 7200), NOW))
        self.assertFalse(working(session("busy", agents_moved=NOW + 7200), NOW))

    def test_a_session_with_no_window_shows_nothing_so_keeps_nothing_on(self):
        # A daemon job nobody attached, or one agentd cannot place in a terminal.
        self.assertFalse(working(session("busy", moved=NOW, window=None), NOW))

    def test_a_quiet_turn_with_a_writing_foreground_subagent_is_working(self):
        self.assertTrue(working(session("busy", moved=NOW - STALE_S - 60, agents_moved=NOW - 3), NOW))

    def test_waiting_shell_idle_and_unknown_never_keep_the_screen_on(self):
        for state in ("waiting", "shell", "idle", "unknown"):
            with self.subTest(state=state):
                self.assertFalse(working(session(state, moved=NOW, agents_moved=NOW), NOW))

    def test_background_shells_and_monitors_do_not_count(self):
        # A dev server or a tail -f in the background would keep it on for ever.
        for kind in ("shell", "monitor"):
            with self.subTest(kind=kind):
                self.assertFalse(working(session("busy", moved=NOW, waiting_on=kind), NOW))

    def test_a_background_subagent_counts_only_while_it_writes(self):
        self.assertTrue(working(session("busy", moved=NOW - 9999, agents_moved=NOW - 10, waiting_on="agent"), NOW))
        self.assertFalse(working(session("busy", moved=NOW, agents_moved=NOW - STALE_S - 1,
                                         waiting_on="agent"), NOW))
        self.assertFalse(working(session("busy", moved=NOW, waiting_on="agent"), NOW))


def desk(root: Path) -> World:
    """One kitty on workspace 1 with `claude` (pid 103) in the foreground."""
    w = World(root)
    w.monitor(0, "DP-1", 1, True)
    w.workspace(1, "DP-1")
    w.terminal(100, "/r/a", fg="claude")
    w.client(WIN, 1, "kitty", "t", 100, 0)
    return w.save()


def snap_of(w: World):
    r = w.root
    return collect(FakeHypr(r / "hypr"), Proc(r / "proc"), ClaudeHome(r / "claude", clock=lambda: NOW),
                   str(r / "fs"))


class ActivityTest(unittest.TestCase):
    """Session.moved and agents_moved, read from the files a working session writes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = desk(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def one(self, status, records, wrote, ago=100):
        self.w.session(103, 1, "/r/a", status, ago=ago)
        f = self.w.transcript(1, "/r/a", [ai_title("t"), *records])
        os.utime(f, (wrote, wrote))
        s = snap_of(self.w).sessions[0]
        self.assertEqual(s.window, WIN)
        return s

    def jsonl(self, name, mtime):
        f = next((self.w.root / "claude" / "projects").glob(f"*/*/subagents/agent-{name}.jsonl"))
        os.utime(f, (mtime, mtime))

    def test_moved_is_the_newest_of_status_change_and_transcript_write(self):
        s = self.one("busy", [], wrote=NOW - 7, ago=500)
        self.assertEqual(s.moved, NOW - 7)
        s = self.one("busy", [], wrote=NOW - 900, ago=40)
        self.assertEqual(s.moved, NOW - 40)
        self.assertTrue(working(s, NOW))

    def test_a_busy_status_nobody_touched_for_half_an_hour_reads_as_hung(self):
        s = self.one("busy", [], wrote=NOW - 1800, ago=1800)
        self.assertEqual(s.state, "busy")
        self.assertFalse(working(s, NOW))

    def test_idle_and_waiting_sessions_are_not_even_stat_ed(self):
        for status in ("idle", "waiting"):
            with self.subTest(status=status):
                s = self.one(status, [], wrote=NOW - 1)
                self.assertEqual((s.moved, s.agents_moved), (None, None))

    def test_a_background_agent_that_writes_keeps_an_ended_turn_working(self):
        self.w.subagent(1, "/r/a", "a1", NOW - 600, tool_use="t2")
        self.jsonl("a1", NOW - 4)
        launch = [tool("Agent", "Revisar", tid="t2", run_in_background="true"), turn_end()]
        s = self.one("idle", launch, wrote=NOW - 3000, ago=3000)
        self.assertEqual((s.state, s.waiting_on, s.agents_moved), ("busy", "agent", NOW - 4))
        self.assertTrue(working(s, NOW))
        self.jsonl("a1", NOW - STALE_S - 5)          # it stopped writing: hung or gone quiet
        self.assertFalse(working(self.one("idle", launch, wrote=NOW - 3000, ago=3000), NOW))

    def test_a_finished_subagent_s_last_write_is_not_work(self):
        # Busy only because of a background shell; the agent that just ended wrote 2 s ago.
        self.w.subagent(1, "/r/a", "a1", NOW - 2, finished=True, tool_use="t2")
        self.jsonl("a1", NOW - 2)
        s = self.one("idle", [tool("Agent", "Revisar", tid="t2", run_in_background="true"),
                              tool("Bash", "npm run dev", tid="t1", run_in_background=True), turn_end(),
                              note("t2", "completed", task="a1")], wrote=NOW - 3000, ago=3000)
        self.assertEqual((s.state, s.waiting_on, s.agents_moved), ("busy", "shell", None))
        self.assertFalse(working(s, NOW))

    def test_a_background_shell_keeps_the_bar_busy_but_not_the_screen(self):
        s = self.one("idle", [tool("Bash", "npm run dev", tid="t1", run_in_background=True), turn_end()],
                     wrote=NOW - 1)
        self.assertEqual((s.state, s.waiting_on), ("busy", "shell"))
        self.assertFalse(working(s, NOW))

    def test_an_agent_id_that_is_not_a_plain_name_is_never_joined_into_a_path(self):
        self.w.session(103, 1, "/r/a", "busy")
        self.w.transcript(1, "/r/a", [ai_title("t")])
        sid = world_sid(1)
        sub = next((self.w.root / "claude" / "projects").glob("*")) / sid / "subagents"
        (sub / "agent-..").mkdir(parents=True)
        (sub / "agent-..").joinpath("x.jsonl").write_text("{}\n")       # only "../x" reaches it
        (sub / "agent-ok\n.jsonl").write_text("{}\n")                    # only "ok\n" reaches it
        (sub / "agent-a1.jsonl").write_text("{}\n")
        home = ClaudeHome(self.w.root / "claude", clock=lambda: NOW)
        wrote = home.activity(sid, "/r/a")[0]
        self.assertIsNotNone(wrote)                                     # the test reaches the files
        self.assertIsNotNone(home.activity(sid, "/r/a", ["a1"])[1])
        self.assertEqual(home.activity(sid, "/r/a", ["../x", "ok\n"]), (wrote, None))


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class AwakeTest(unittest.TestCase):
    """The holder, with `cat` standing in for `systemd-inhibit … bash`."""

    def setUp(self):
        self.clock, self.logged, self.spawned = Clock(), [], []
        self.awake = Awake(spawn=self.spawn, log=self.logged.append, clock=self.clock)

    def tearDown(self):
        self.awake.release()
        for p in self.spawned:
            if p.poll() is None:
                p.kill()
                p.wait(2)
            if p.stdin:
                p.stdin.close()

    def spawn(self):
        p = subprocess.Popen(["cat"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
        self.spawned.append(p)
        return p

    def kill_child(self):
        self.awake.child.kill()
        self.awake.child.wait(2)

    def test_the_command_is_an_idle_block_lock_that_never_asks_for_a_password(self):
        self.assertEqual(COMMAND[0], "systemd-inhibit")
        self.assertIn("--what=idle", COMMAND)        # not sleep: a deliberate hibernate still works
        self.assertIn("--mode=block", COMMAND)       # hypridle never reads BlockWeakInhibited
        self.assertIn("--no-ask-password", COMMAND)
        self.assertEqual(COMMAND[-len(LEASE):], LEASE)   # the pipe is the lock's lifetime

    def test_taken_at_once_held_through_the_grace_then_released(self):
        self.awake.update(True)
        self.assertTrue(self.awake.held)
        child = self.awake.child
        self.awake.update(True)
        self.assertIs(self.awake.child, child)       # one lock, not one per cycle
        self.clock.t += GRACE_S - 1
        self.awake.update(False)
        self.assertTrue(self.awake.held)             # a permission prompt does not drop it
        self.clock.t += 1
        self.awake.update(False)
        self.assertFalse(self.awake.held)
        self.assertEqual(child.returncode, 0)        # cat saw EOF and exited, reaped
        self.assertEqual(len(self.spawned), 1)

    def test_held_is_logged_only_once_the_child_outlived_a_cycle(self):
        self.awake.update(True)
        self.assertEqual(self.logged, [])
        self.clock.t += 2
        self.awake.update(True)
        self.assertEqual(len(self.logged), 1)
        self.assertIn("held", self.logged[0])

    def test_work_inside_the_grace_keeps_the_same_lock(self):
        self.awake.update(True)
        self.clock.t += 50
        self.awake.update(False)
        self.awake.update(True)
        self.clock.t += 50
        self.awake.update(False)
        self.assertTrue(self.awake.held)
        self.assertEqual(len(self.spawned), 1)

    def test_a_lock_refused_at_once_is_reported_once_and_retried_every_retry_period(self):
        for _ in range(3):
            self.awake.update(True)
            self.kill_child()
            self.awake.update(True)
            self.assertFalse(self.awake.held)
            self.clock.t += RETRY_S - 1
            self.awake.update(True)
            self.assertFalse(self.awake.held)
            self.clock.t += 1
        self.assertEqual(len(self.spawned), 3)
        self.assertEqual([m for m in self.logged if "exited" in m], [self.logged[0]])

    def test_a_lock_lost_after_holding_well_is_taken_again_at_once(self):
        # logind restarted under a working session: no 30 s hole for the 600 s mark to fall in.
        self.awake.update(True)
        self.clock.t += RETRY_S
        self.awake.update(True)
        self.kill_child()
        self.awake.update(True)
        self.assertTrue(self.awake.held)
        self.assertEqual(len(self.spawned), 2)

    def test_a_missing_binary_is_reported_once_not_every_cycle(self):
        def missing():
            raise FileNotFoundError("systemd-inhibit")
        awake = Awake(spawn=missing, log=self.logged.append, clock=self.clock)
        for _ in range(5):
            awake.update(True)
            self.clock.t += RETRY_S
        self.assertFalse(awake.held)
        self.assertEqual(len(self.logged), 1)
        self.assertIn("FileNotFoundError", self.logged[0])

    def test_a_child_that_ignores_eof_is_killed(self):
        def stubborn():
            p = subprocess.Popen(["sleep", "30"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
            self.spawned.append(p)
            return p
        awake = Awake(spawn=stubborn, log=self.logged.append, clock=self.clock)
        awake.update(True)
        child = awake.child
        start = time.monotonic()
        awake.release()
        self.assertIsNotNone(child.returncode)
        self.assertLess(time.monotonic() - start, 2.5)

    def test_nothing_held_nothing_to_release(self):
        self.awake.update(False)
        self.awake.release()
        self.assertEqual(self.spawned, [])
        self.assertEqual(self.logged, [])


class LeaseTest(unittest.TestCase):
    """The real spawn path and the lease, with bash alone (no logind)."""

    def awake(self, lease_s):
        cmd = (LEASE[0], LEASE[1], LEASE[2].replace("-t 120", f"-t {lease_s}"))
        self.assertNotEqual(cmd, LEASE)
        a = Awake(log=lambda m: None, command=cmd)
        self.addCleanup(a.release)
        return a

    def test_the_lease_is_bash_reading_with_a_timeout(self):
        self.assertEqual(LEASE[2], "while read -r -t 120 _; do :; done")

    def test_fed_every_cycle_the_lease_holds(self):
        a = self.awake(1)
        a.update(True)
        child = a.child
        self.assertIsNotNone(child.stdin)                    # a pipe, never the service's /dev/null
        for _ in range(8):
            time.sleep(0.25)
            a.update(True)
        self.assertIsNone(child.poll())

    def test_a_hung_owner_loses_the_lock_when_the_lease_runs_out(self):
        a = self.awake(1)
        a.update(True)
        child = a.child
        child.wait(5)                                        # nobody feeds it: agentd stuck
        self.assertEqual(child.returncode, 0)

    def test_a_closed_pipe_ends_it_at_once(self):
        a = self.awake(60)
        a.update(True)
        child = a.child
        start = time.monotonic()
        a.release()
        self.assertEqual(child.returncode, 0)
        self.assertLess(time.monotonic() - start, 1.0)


class OwnerDeathTest(unittest.TestCase):
    def test_a_sigkilled_owner_takes_the_lock_with_it(self):
        """No --reset, no ExecStopPost: the kernel closing the pipe is the release."""
        script = textwrap.dedent("""
            import sys, time
            from agentd.awake import LEASE, Awake
            a = Awake(log=lambda m: None, command=LEASE)
            a.update(True)
            print(a.child.pid, flush=True)
            time.sleep(60)
        """)
        owner = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True,
                                 env={**os.environ, "PYTHONPATH": str(AGENTD)})
        try:
            pid = int(owner.stdout.readline())
            os.kill(owner.pid, signal.SIGKILL)
            owner.wait(5)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and _alive(pid):
                time.sleep(0.05)
            self.assertFalse(_alive(pid), "the inhibitor outlived its owner")
        finally:
            if owner.poll() is None:
                owner.kill()
                owner.wait(2)
            owner.stdout.close()


def _alive(pid):
    """Alive and not a zombie (an orphan is reaped by init or the subreaper)."""
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


class FakeAwake:
    def __init__(self):
        self.wants, self.held = [], False

    def update(self, want):
        self.wants.append(want)
        self.held = want or self.held


class AppTest(unittest.TestCase):
    """What the daemon asks for, from a whole snapshot, on the App's wall clock."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = desk(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def app(self, status, ago=10):
        self.w.session(103, 1, "/r/a", status, ago=ago)
        f = self.w.transcript(1, "/r/a", [ai_title("t")])
        os.utime(f, (NOW - ago, NOW - ago))
        r = self.w.root
        app = App(FakeHypr(r / "hypr"), Proc(r / "proc"), ClaudeHome(r / "claude", clock=lambda: NOW),
                  str(r / "fs"), Publisher(r / "out", signal=None), r / "none.json", dispatch=False,
                  clock=lambda: NOW, err=io.StringIO())
        app.awake = FakeAwake()
        return app

    def test_a_working_session_asks_for_the_lock_and_keeps_the_loop_cycling(self):
        app = self.app("busy")
        app.cycle()
        self.assertEqual(app.awake.wants, [True])
        self.assertTrue(app.active)

    def test_staleness_is_judged_on_the_app_clock_against_file_times(self):
        app = self.app("busy", ago=STALE_S + 1)
        app.cycle()
        self.assertEqual(app.awake.wants, [False])

    def test_a_held_lock_keeps_cycling_after_the_work_stops_so_it_can_be_released(self):
        app = self.app("idle")
        app.awake.held = True
        app.cycle()
        self.assertEqual(app.awake.wants, [False])
        self.assertTrue(app.active)

    def test_waiting_for_the_user_does_not_ask(self):
        app = self.app("waiting")
        app.cycle()
        self.assertEqual(app.awake.wants, [False])

    def test_a_locked_screen_asks_for_nothing(self):
        self.w.proc(77, LOCKER)
        app = self.app("busy")
        app.cycle()
        self.assertEqual(app.awake.wants, [False])

    def test_a_failing_cycle_fails_toward_locking(self):
        app = self.app("busy")
        app.hypr = None          # collect() raises on it
        self.assertIsNone(app.safe_cycle())
        self.assertEqual(app.awake.wants, [False])


class ModesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_shot_modes_never_hold_a_lock(self):
        fx = main_world(self.root / "fx").root
        real = Awake.update
        calls = []
        Awake.update = lambda self, want: calls.append(want)
        try:
            rc = main(["--once", "--fixtures", str(fx), "--outdir", str(self.root / "o"), "--no-dispatch"],
                      stdout=io.StringIO(), stderr=io.StringIO())
        finally:
            Awake.update = real
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])

    def test_a_no_dispatch_daemon_holds_no_lock(self):
        seen = []
        run, signals = entry.Loop.run, entry.handle_signals
        entry.Loop.run = lambda loop: seen.append(loop.app.awake)
        entry.handle_signals = lambda loop: None
        try:
            rc = main(["--no-dispatch", "--outdir", str(self.root / "o"), "--palette", str(self.root / "p.json")],
                      stdout=io.StringIO(), stderr=io.StringIO(),
                      env={"HOME": str(self.root), "XDG_RUNTIME_DIR": str(self.root)})
        finally:
            entry.Loop.run, entry.handle_signals = run, signals
        self.assertEqual((rc, seen), (0, [None]))


@unittest.skipUnless(os.environ.get("AGENTD_LIVE") == "1",
                     "AGENTD_LIVE=1 takes a real logind lock (needs the system bus)")
class LiveLogindTest(unittest.TestCase):
    def listed(self):
        out = subprocess.run(["systemd-inhibit", "--list", "--no-pager", "--no-legend"],
                             capture_output=True, text=True, timeout=10).stdout
        return [line for line in out.splitlines() if line.split()[:1] == ["agentd"] and " idle " in line]

    def test_logind_lists_the_lock_while_held_and_drops_it_on_release(self):
        before = len(self.listed())
        awake = Awake(log=lambda m: None)
        awake.update(True)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and len(self.listed()) == before:
                time.sleep(0.1)
            self.assertEqual(len(self.listed()), before + 1)
            self.assertIn("block", self.listed()[-1])
            awake.update(True)
            self.assertTrue(awake.confirmed)
        finally:
            awake.release()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and len(self.listed()) != before:
            time.sleep(0.1)
        self.assertEqual(len(self.listed()), before)


if __name__ == "__main__":
    unittest.main()
