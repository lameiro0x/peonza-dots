import os
import tempfile
import unittest
from pathlib import Path

from agentd.procfs import Proc
from world import World


class ProcTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = World(Path(self.tmp.name))
        self.w.terminal(1000, "/home/u/Repos/ryce-pc", fg="claude")
        self.p = Proc(self.w.root / "proc")

    def tearDown(self):
        self.tmp.cleanup()

    def test_shell_under_skips_the_kitten_helper(self):
        # kitty → kitten (cwd $HOME) → fish: the shell is fish, not the helper.
        self.assertEqual(self.p.shell_under(1000), 1002)

    def test_foreground_is_tpgid_when_a_job_holds_the_terminal(self):
        self.assertEqual(self.p.foreground(1002), 1003)

    def test_no_foreground_at_the_prompt(self):
        self.w.terminal(2000, "/tmp", bg="claude")
        self.assertIsNone(self.p.foreground(2002))

    def test_start_time_is_field_22_even_with_parens_in_comm(self):
        self.w.proc(3000, "tmux: (server) x", start=777)
        self.assertEqual(self.p.start_time(3000), "777")

    def test_cmdline_is_argv_and_empty_once_gone(self):
        self.w.proc(3100, "claude", argv=("/usr/bin/claude", "attach", "0b6f3f7e", ""))
        self.assertEqual(self.p.cmdline(3100), ["/usr/bin/claude", "attach", "0b6f3f7e", ""])
        self.assertEqual(self.p.cmdline(1000), [])        # no cmdline file: a kernel thread
        self.assertEqual(self.p.cmdline(99999), [])

    def test_descendants_are_bounded_by_depth_and_count(self):
        self.assertEqual(self.p.descendants(1000), [1000, 1001, 1002, 1003])
        self.assertEqual(self.p.descendants(1000, depth=2), [1000, 1001, 1002])
        self.assertEqual(self.p.descendants(1000, limit=2), [1000, 1001])

    def test_a_cycle_in_children_does_not_loop(self):
        self.w.proc(4000, "a", children=[4001])
        self.w.proc(4001, "b", children=[4000])
        self.assertEqual(self.p.descendants(4000), [4000, 4001])

    def test_vanished_process_reads_as_nothing(self):
        self.assertIsNone(self.p.start_time(99999))
        self.assertEqual(self.p.children(99999), [])
        self.assertEqual(self.p.comm(99999), "")
        self.assertIsNone(self.p.cwd(99999))

    def test_cwd_is_the_link_target(self):
        self.assertEqual(self.p.cwd(1002), "/home/u/Repos/ryce-pc")

    @unittest.skipUnless(Path("/proc/self/stat").exists(), "needs Linux /proc")
    def test_real_proc_start_time_of_this_process(self):
        p = Proc()
        self.assertTrue(p.start_time(os.getpid()).isdigit())
        self.assertIn(os.getpid(), p.descendants(os.getppid()))


if __name__ == "__main__":
    unittest.main()
