"""install/polkit-setup.sh (the admin window) against a fake root, its PAM stamp program in a
temp folder, and the polkit rule it writes run under node with a stand-in for polkit's
JavaScript API. polkitd runs rules in duktape (ES5): the rule keeps to ES5, and a test says so."""
import json
import os
import pwd
import re
import shutil
import subprocess
import unittest

from harness import REPO, ScriptTest

SCRIPT = REPO / "install" / "polkit-setup.sh"
MARK = "Managed by ryce-pc (install/polkit-setup.sh): change it in the repo and re-run."
RULE = "etc/polkit-1/rules.d/49-ryce-admin-window.rules"
PAM = "etc/pam.d/polkit-1"
STAMP = "usr/local/lib/ryce/polkit-stamp"
TMPFILES = "etc/tmpfiles.d/ryce-polkit.conf"
DROPIN = "etc/systemd/system/polkit-agent-helper@.service.d/ryce-polkit.conf"
OURS = (RULE, PAM, STAMP, TMPFILES, DROPIN)
VENDOR = ("#%PAM-1.0\n\nauth       include      system-auth\naccount    include      system-auth\n"
          "password   include      system-auth\nsession    include      system-auth\n")
ME = pwd.getpwuid(os.getuid()).pw_name
EXEC = "org.freedesktop.policykit.exec"
UNITS = "org.freedesktop.systemd1.manage-units"

# polkit's JS API as polkitd 128 exposes it to rules, with a clock and stat outputs the
# scenario sets. Each step calls every rule like polkitd does and records the result.
NODE = r'''
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const sc = JSON.parse(process.argv[3]);
const rules = [], logs = [], results = [];
let clock = sc.start, spawned = 0, mtimes = sc.mtimes || {};
const polkit = {
  Result: {YES: "yes", NO: "no", NOT_HANDLED: null, AUTH_ADMIN: "auth_admin"},
  addRule: (f) => rules.push(f),
  log: (s) => logs.push(s),
  spawn: (argv) => {   // stat -c %Y FILE...: one line per file, exit 1 if any is missing
    spawned++;
    const files = argv.slice(3);
    if (files.some((f) => mtimes[f] === undefined)) throw new Error("stat: exit 1");
    return files.map((f) => String(mtimes[f]) + "\n").join("");
  },
};
Date.now = () => clock;
new Function("polkit", src)(polkit);
for (const st of sc.steps) {
  clock = sc.start + st.t;
  if (st.mtimes) mtimes = st.mtimes;
  const action = {id: st.action || "org.freedesktop.policykit.exec",
                  lookup: (k) => (k === "command_line" ? (st.command || "/usr/bin/true") : undefined)};
  const subject = {user: st.user || "ana", local: st.local !== false, active: st.active !== false,
                   isInGroup: (g) => (st.groups || ["wheel"]).includes(g)};
  let r = null;
  for (const f of rules) { r = f(action, subject); if (r !== null) break; }
  results.push(r);
}
console.log(JSON.stringify({results, spawned, logs}));
'''


class PolkitSetup(ScriptTest):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "root"
        (self.root / "usr/lib/pam.d").mkdir(parents=True)
        (self.root / "usr/lib/pam.d/polkit-1").write_text(VENDOR)
        self.env.pop("PKEXEC_UID", None)

    def setup_run(self, *args, rc=0, env=None):
        r = self.run_script(SCRIPT, "--root", str(self.root), *args, env=env)
        self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
        return r

    def read(self, rel):
        return (self.root / rel).read_text()

    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.read_bytes() if p.is_file() else None)
                for p in sorted(self.root.rglob("*"))}

    # --- the script -----------------------------------------------------------------------

    def test_apply_writes_every_piece_then_changes_nothing(self):
        out = self.setup_run().stdout
        for rel in OURS:
            self.assertIn(MARK, self.read(rel), rel)
        self.assertEqual(oct((self.root / STAMP).stat().st_mode & 0o777), "0o755")
        self.assertEqual(oct((self.root / RULE).stat().st_mode & 0o777), "0o644")
        self.assertTrue((self.root / "run/ryce-polkit").is_dir())
        self.assertIn("systemctl daemon-reload", "\n".join(self.calls()))
        self.assertIn("ReadWritePaths=-/run/ryce-polkit", self.read(DROPIN))
        self.assertIn("d /run/ryce-polkit 0755 root root -", self.read(TMPFILES))
        self.assertRegex(out, r"==> \d+ cambios")
        before = self.snapshot()
        self.assertIn("==> 0 cambios", self.setup_run().stdout)
        self.assertEqual(self.snapshot(), before)

    def test_pam_is_polkits_stack_plus_the_two_stamp_lines(self):
        self.setup_run()
        lines = [re.sub(r"\s+", " ", l).strip() for l in self.read(PAM).splitlines()
                 if l.strip() and not l.startswith("#")]
        stamp = "pam_exec.so quiet seteuid /usr/local/lib/ryce/polkit-stamp"
        self.assertEqual(lines, [
            "auth include system-auth",
            "account include system-auth",
            f"account optional {stamp}",
            "password include system-auth",
            "session include system-auth",
            f"session optional {stamp}",
        ])
        self.assertTrue(self.read(PAM).startswith("#%PAM-1.0\n"))

    def test_a_changed_polkit_stack_is_refused_and_nothing_written(self):
        (self.root / "usr/lib/pam.d/polkit-1").write_text(VENDOR + "auth optional pam_gnome_keyring.so\n")
        r = self.setup_run(rc=1)
        self.assertIn("ya no es la pila que conozco", r.stderr)
        for rel in OURS:
            self.assertFalse((self.root / rel).exists(), rel)

    def test_a_foreign_file_in_the_way_is_refused_and_nothing_written(self):
        (self.root / "etc/pam.d").mkdir(parents=True)
        (self.root / PAM).write_text("auth include system-auth\n")
        r = self.setup_run(rc=1)
        self.assertIn("no es de ryce-pc", r.stderr)
        self.assertFalse((self.root / RULE).exists())
        self.assertEqual(self.read(PAM), "auth include system-auth\n")

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        self.assertIn("[simulación]", self.setup_run("--dry-run").stdout)
        self.assertEqual(self.snapshot(), before)

    def test_check_passes_after_apply_and_catches_a_tampered_rule(self):
        self.setup_run("--check", rc=1)
        self.setup_run()
        self.assertIn("todo en su sitio", self.setup_run("--check").stdout)
        (self.root / RULE).write_text(self.read(RULE).replace("1800", "999999"))
        self.assertIn(f"/{RULE} falta o cambió", self.setup_run("--check", rc=1).stdout)

    def test_the_caller_gets_the_window_at_once(self):
        self.setup_run(env={"PKEXEC_UID": str(os.getuid())})
        self.assertTrue((self.root / "run/ryce-polkit" / ME).is_file())
        self.assertTrue((self.root / "run/ryce-polkit" / f"{ME}.auth").is_file())
        self.assertIn(f"{ME}: abierta", self.setup_run("--check").stdout)

    def test_rollback_removes_every_piece_and_leaves_a_foreign_file(self):
        self.setup_run()
        (self.root / "etc/polkit-1/rules.d/10-mine.rules").write_text("// mine\n")
        self.setup_run("--rollback")
        for rel in OURS:
            self.assertFalse((self.root / rel).exists(), rel)
        self.assertFalse((self.root / "run/ryce-polkit").exists())
        self.assertTrue((self.root / "etc/polkit-1/rules.d/10-mine.rules").exists())
        self.assertEqual(self.read("usr/lib/pam.d/polkit-1"), VENDOR)
        self.assertIn("==> 0 cambios", self.setup_run("--rollback").stdout)

    # --- the stamp program (run from PAM as root) ------------------------------------------

    def stamp_program(self):
        """The installed program with its folder moved into the temp dir and logger silenced."""
        self.setup_run()
        stamps = self.tmp / "stamps"
        stamps.mkdir()
        prog = self.tmp / "polkit-stamp"
        prog.write_text(self.read(STAMP).replace("/run/ryce-polkit", str(stamps))
                        .replace("logger -t", ": logger -t"))
        prog.chmod(0o755)
        return prog, stamps

    def stamp(self, prog, **pam):
        env = {"PATH": "/usr/bin", **pam}
        r = subprocess.run([str(prog)], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_stamp_after_a_password_names_the_user_who_typed_it(self):
        prog, stamps = self.stamp_program()
        self.stamp(prog, PAM_TYPE="account", PAM_USER="ana")
        self.assertEqual(sorted(p.name for p in stamps.iterdir()), ["ana", "ana.auth"])

    def test_stamp_from_pkexec_names_the_caller_and_never_counts_as_a_password(self):
        prog, stamps = self.stamp_program()
        self.stamp(prog, PAM_TYPE="open_session", PAM_USER="root")
        self.assertEqual([p.name for p in stamps.iterdir()], [ME])

    def test_stamp_ignores_odd_names_other_stacks_and_a_missing_folder(self):
        prog, stamps = self.stamp_program()
        for user in ("", "../etc", "a b", "-rf", "Ana", "ana/x"):
            self.stamp(prog, PAM_TYPE="account", PAM_USER=user)
        self.stamp(prog, PAM_TYPE="close_session", PAM_USER="ana")
        self.stamp(prog, PAM_TYPE="auth", PAM_USER="ana")
        self.assertEqual(list(stamps.iterdir()), [])
        stamps.rmdir()
        self.stamp(prog, PAM_TYPE="account", PAM_USER="ana")
        self.assertFalse(stamps.exists())

    # --- the rule --------------------------------------------------------------------------

    def rule(self, steps, mtimes=None):
        if not shutil.which("node"):
            self.skipTest("node is needed to run the rule")
        self.setup_run()
        start = 1_800_000_000_000
        sc = {"start": start, "mtimes": mtimes or {}, "steps": steps}
        harness = self.tmp / "harness.js"
        harness.write_text(NODE)
        r = subprocess.run(["node", str(harness), str(self.root / RULE), json.dumps(sc)],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    @staticmethod
    def ago(seconds, auth=None, user="ana"):
        """Stamps: last use `seconds` ago, last password `auth` seconds ago (default: the same)."""
        now = 1_800_000_000
        return {f"/run/ryce-polkit/{user}": now - seconds,
                f"/run/ryce-polkit/{user}.auth": now - (seconds if auth is None else auth)}

    def test_rule_is_es5_for_duktape(self):
        self.setup_run()
        text = "\n".join(l for l in self.read(RULE).splitlines() if not l.lstrip().startswith("//"))
        self.assertIn("polkit.addRule(function (action, subject)", text)
        for es6 in ("=>", "let ", "const ", "`", "class "):
            self.assertNotIn(es6, text)

    def test_inside_the_window_anything_passes_without_asking(self):
        out = self.rule([{"t": 0}, {"t": 0, "action": UNITS}, {"t": 0, "action": "org.libvirt.unix.manage"}],
                        mtimes=self.ago(29 * 60))
        self.assertEqual(out["results"], ["yes", "yes", "yes"])

    def test_outside_the_window_the_usual_rules_ask(self):
        self.assertEqual(self.rule([{"t": 0}, {"t": 0, "action": UNITS, "command": "x"}],
                                   mtimes=self.ago(31 * 60))["results"], [None, None])
        self.assertEqual(self.rule([{"t": 0}])["results"], [None])   # no stamp at all

    def test_the_window_is_for_admins_of_the_active_local_session_only(self):
        fresh = self.ago(60)
        out = self.rule([{"t": 0, "groups": []}, {"t": 0, "local": False}, {"t": 0, "active": False},
                         {"t": 0, "user": "bob"}], mtimes=fresh)
        self.assertEqual(out["results"], [None, None, None, None])

    def test_a_stamp_from_the_future_does_not_open_it(self):
        self.assertEqual(self.rule([{"t": 0}], mtimes=self.ago(-600))["results"], [None])

    def test_use_extends_it_but_never_past_eight_hours_since_the_password(self):
        out = self.rule([{"t": 0}], mtimes=self.ago(60, auth=8 * 3600 - 120))
        self.assertEqual(out["results"], ["yes"])
        out = self.rule([{"t": 0}], mtimes=self.ago(60, auth=8 * 3600 + 60))
        self.assertEqual(out["results"], [None])

    def test_without_the_password_stamp_it_stays_closed(self):
        use_only = {"/run/ryce-polkit/ana": 1_800_000_000 - 60}
        self.assertEqual(self.rule([{"t": 0}], mtimes=use_only)["results"], [None])

    def test_the_same_refused_command_is_not_asked_again_for_two_minutes(self):
        stale = self.ago(3600)
        out = self.rule([
            {"t": 0, "command": "/usr/bin/nft list ruleset"},
            {"t": 30_000, "command": "/usr/bin/nft list ruleset"},
            {"t": 31_000, "command": "/usr/bin/nft list tables"},
            {"t": 31_000, "command": "/usr/bin/nft list ruleset", "user": "eve"},
            {"t": 31_000, "command": "/usr/bin/nft list ruleset", "action": UNITS},
            {"t": 121_000, "command": "/usr/bin/nft list ruleset"},
        ], mtimes=stale)
        self.assertEqual(out["results"], [None, "no", None, None, None, None])
        self.assertEqual(len(out["logs"]), 1)
        self.assertIn("nft list ruleset", out["logs"][0])

    def test_once_the_password_is_typed_the_repeat_passes(self):
        out = self.rule([
            {"t": 0, "command": "/usr/bin/pacman -Syu"},
            {"t": 20_000, "command": "/usr/bin/pacman -Syu",
             "mtimes": {"/run/ryce-polkit/ana": 1_800_000_010, "/run/ryce-polkit/ana.auth": 1_800_000_010}},
        ], mtimes=self.ago(3600))
        self.assertEqual(out["results"], [None, "yes"])

    def test_the_stamp_is_read_at_most_every_five_seconds(self):
        steps = [{"t": i * 400} for i in range(10)] + [{"t": 5_000}, {"t": 5_100}]
        out = self.rule(steps, mtimes=self.ago(60))
        self.assertEqual(out["results"], ["yes"] * 12)
        self.assertEqual(out["spawned"], 2)

    def test_closing_the_window_takes_effect_within_five_seconds(self):
        out = self.rule([{"t": 0}, {"t": 1_000, "mtimes": {}}, {"t": 5_000, "mtimes": {}}],
                        mtimes=self.ago(60))
        self.assertEqual(out["results"], ["yes", "yes", None])


if __name__ == "__main__":
    unittest.main()
