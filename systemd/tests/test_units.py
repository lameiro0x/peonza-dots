"""Static checks of systemd/user: the failure modes the vault paid for, as tests.

`systemd-analyze --user verify` (check-arch.sh) catches syntax; these catch the
units that are valid and still wrong (decisions 2026-08-01, 2026-08-11).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USER = ROOT / "systemd" / "user"
PACKAGES = ROOT / "install" / "packages"
# Units the session wants that Arch packages ship in /usr/lib/systemd/user
# (verified on archlinux.org file lists, 2026-11-09): unit -> package.
PACKAGED = {
    "mako.service": "mako",
    "hypridle.service": "hypridle",
    "hyprpolkitagent.service": "hyprpolkitagent",
}
DEPENDENCY_KEYS = {"Wants", "Requires", "Requisite", "BindsTo", "PartOf", "Upholds",
                   "After", "Before", "WantedBy", "RequiredBy", "UpheldBy"}


def parse(path: Path) -> dict[str, list[tuple[str, str]]]:
    """Section -> [(key, value)], keeping repeats (systemd allows them)."""
    sections: dict[str, list[tuple[str, str]]] = {}
    current = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("["):
            current = line.strip("[]")
            sections.setdefault(current, [])
            continue
        if current is None:
            raise AssertionError(f"{path.name}: key outside a section: {line}")
        key, _, value = line.partition("=")
        sections[current].append((key.strip(), value.strip()))
    return sections


def values(unit: dict, section: str, key: str) -> list[str]:
    return [v for k, v in unit.get(section, []) if k == key]


def words(unit: dict, section: str, key: str) -> list[str]:
    return [w for v in values(unit, section, key) for w in v.split()]


class UnitsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = {p.name: parse(p) for p in sorted(USER.iterdir()) if p.is_file()}
        cls.dropins = {p.parent.name: parse(p) for p in sorted(USER.glob("*.d/*.conf"))}

    def test_expected_units_exist(self) -> None:
        self.assertEqual(set(self.units), {
            "ryce-session.target", "agentd.service", "waybar.service", "quickshell.service",
            "ryce-wallpaper.service", "cliphist.service", "ryce-agents.slice", "ryce-aria.service"})

    def test_target_wants_resolve_to_ours_or_packaged(self) -> None:
        packages = set()
        for f in PACKAGES.glob("*.txt"):
            packages |= {ln.split("#")[0].strip() for ln in f.read_text(encoding="utf-8").splitlines()}
        wants = words(self.units["ryce-session.target"], "Unit", "Wants")
        self.assertEqual(len(wants), len(set(wants)), "duplicate Wants=")
        for w in wants:
            with self.subTest(unit=w):
                if w in self.units:
                    continue
                self.assertIn(w, PACKAGED, f"{w}: neither in systemd/user nor a known packaged unit")
                self.assertIn(PACKAGED[w], packages, f"{w} needs package {PACKAGED[w]} in install/packages")
        for must in ("agentd.service", "quickshell.service", "ryce-wallpaper.service",
                     "cliphist.service", "mako.service", "hypridle.service", "hyprpolkitagent.service"):
            self.assertIn(must, wants)
        # The fallback bar: started by quickshell.service's OnFailure= only.
        self.assertNotIn("waybar.service", wants)

    def test_session_units_stop_with_the_target(self) -> None:
        # hypr/autostart.lua stops ryce-session.target on Hyprland shutdown; the
        # fallback bar is not wanted by it but must stop with it all the same.
        for w in words(self.units["ryce-session.target"], "Unit", "Wants") + ["waybar.service"]:
            unit = self.units.get(w) or self.dropins.get(f"{w}.d")
            with self.subTest(unit=w):
                self.assertIsNotNone(unit, f"{w}: packaged units need a PartOf drop-in in {w}.d/")
                part_of = words(unit, "Unit", "PartOf")
                if w == "agentd.service":
                    self.assertEqual(part_of, [], "agentd outlives the compositor")
                else:
                    self.assertEqual(part_of, ["ryce-session.target"])

    def test_dropins_only_target_packaged_units(self) -> None:
        for d, unit in self.dropins.items():
            with self.subTest(dropin=d):
                self.assertIn(d.removesuffix(".d"), PACKAGED)
                self.assertEqual(unit, {"Unit": [("PartOf", "ryce-session.target")]})

    def test_start_limits_only_in_unit_section(self) -> None:
        for name, unit in self.units.items():
            for section, pairs in unit.items():
                for k, _ in pairs:
                    if k.startswith("StartLimit"):
                        with self.subTest(unit=name, key=k):
                            self.assertEqual(section, "Unit", "systemd ignores it outside [Unit]")

    def test_never_hang_off_graphical_session(self) -> None:
        # greetd never activates graphical-session.target on this machine.
        for name, unit in (self.units | self.dropins).items():
            for section, pairs in unit.items():
                for k, v in pairs:
                    if k in DEPENDENCY_KEYS:
                        with self.subTest(unit=name, key=k):
                            self.assertNotIn("graphical-session.target", v)

    def test_no_hard_dependencies(self) -> None:
        # Every piece fails alone: nothing may take the bar down with it.
        for name, unit in self.units.items():
            for key in ("Requires", "Requisite", "BindsTo", "Upholds"):
                self.assertEqual(values(unit, "Unit", key), [], f"{name}: {key}=")

    def test_only_agentd_is_enabled_at_login(self) -> None:
        for name, unit in self.units.items():
            wanted_by = words(unit, "Install", "WantedBy")
            if name == "agentd.service":
                self.assertEqual(wanted_by, ["default.target"])
            else:
                self.assertNotIn("Install", unit, f"{name} must be started by ryce-session.target only")

    def test_paths_use_specifiers_and_absolute_binaries(self) -> None:
        for name, unit in self.units.items():
            for section, pairs in unit.items():
                for k, v in pairs:
                    with self.subTest(unit=name, key=k):
                        self.assertNotRegex(v, r"(^|[\s=:])(~|/home/)", "home paths go through %h")
                        if k.startswith("Exec"):
                            self.assertRegex(v, r"^[-@:+!]*(/|%h/)", "Exec needs an absolute binary")

    def test_agentd(self) -> None:
        u = self.units["agentd.service"]
        self.assertEqual(values(u, "Unit", "StartLimitIntervalSec"), ["0"])
        self.assertEqual(values(u, "Service", "Environment"), ["PYTHONPATH=%h/.local/lib/ryce"])
        self.assertEqual(values(u, "Service", "ExecStart"), ["/usr/bin/python3 -m agentd"])
        pre = values(u, "Service", "ExecStartPre")
        self.assertEqual(pre, ["-/usr/bin/python3 -m agentd --once --wait 45"])
        self.assertEqual(values(u, "Service", "ReadWritePaths"), ["%t"])
        self.assertEqual(values(u, "Service", "RestrictAddressFamilies"), ["AF_UNIX"])
        self.assertEqual(values(u, "Service", "MemoryMax"), ["64M"])
        self.assertEqual(values(u, "Service", "ProtectSystem"), ["strict"])
        self.assertEqual(values(u, "Service", "Restart"), ["always"])
        self.assertEqual(values(u, "Unit", "PartOf"), [])
        # A dead agentd must not leave rings, tags or a lock line behind.
        self.assertEqual(values(u, "Service", "ExecStopPost"), ["-/usr/bin/python3 -m agentd --reset"])
        # ryce-theme reloads it after a switch: SIGHUP re-reads the palette.
        self.assertEqual(values(u, "Service", "ExecReload"), ["/usr/bin/kill -HUP $MAINPID"])

    def test_clipboard_history_is_on_tmpfs_and_bounded(self) -> None:
        start = values(self.units["cliphist.service"], "Service", "ExecStart")
        self.assertEqual(start, ["/usr/bin/wl-paste --watch /usr/bin/cliphist "
                                 "-db-path %t/cliphist.db -max-items 100 store"])

    def test_waybar_is_supervised_and_shadows_the_package(self) -> None:
        u = self.units["waybar.service"]
        self.assertEqual(values(u, "Service", "ExecStart"), ["/usr/bin/waybar"])
        self.assertEqual(values(u, "Unit", "StartLimitIntervalSec"), ["0"])
        self.assertEqual(values(u, "Service", "Restart"), ["always"])
        self.assertEqual(values(u, "Service", "RestartSec"), ["3"])
        self.assertEqual(values(u, "Service", "OOMScoreAdjust"), ["0"])
        self.assertEqual(values(u, "Service", "MemoryLow"), ["128M"])
        self.assertIn("agentd.service", words(u, "Unit", "After"))
        self.assertIn("agentd.service", words(u, "Unit", "Wants"))

    def test_quickshell_hands_the_bar_to_waybar_when_it_cannot_stay_up(self) -> None:
        u = self.units["quickshell.service"]
        self.assertEqual(values(u, "Service", "ExecStart"), ["/usr/bin/quickshell -c ryce"])
        self.assertEqual(values(u, "Service", "Restart"), ["on-failure"])
        self.assertEqual(values(u, "Unit", "OnFailure"), ["waybar.service"])
        self.assertEqual(values(u, "Unit", "StartLimitBurst"), ["3"])
        # One bar at a time, either way round.
        self.assertEqual(values(self.units["waybar.service"], "Unit", "Conflicts"), ["quickshell.service"])
        # Nothing may depend on Quickshell: it is the fragile layer.
        for name, other in self.units.items():
            for k, v in other.get("Unit", []):
                if k in DEPENDENCY_KEYS - {"Wants"}:
                    self.assertNotIn("quickshell", v, f"{name} {k}= quickshell")

    def test_quickshell_counts_as_started_only_once_the_bar_answers(self) -> None:
        u = self.units["quickshell.service"]
        post = values(u, "Service", "ExecStartPost")
        self.assertEqual(len(post), 1)
        self.assertFalse(post[0].startswith("-"), "a failed probe must fail the start")
        self.assertIn("/usr/bin/qs -c ryce ipc call bar ping", post[0])
        tries = int(re.search(r'-lt (\d+)', post[0]).group(1))
        gap = float(re.search(r"sleep ([\d.]+)", post[0]).group(1))
        self.assertEqual((tries, gap), (20, 0.5))
        self.assertTrue(post[0].rstrip("'").endswith("exit 1"))
        self.assertNotRegex(post[0], r"(?<!\$)\$(?!\$)", "systemd expands a single `$`: write `$$`")
        # The limit must be reachable by the slowest failure (alive, never answering):
        # Burst starts of probe + RestartSec each have to fit inside the window, or
        # the window resets first and Waybar never takes over.
        burst = int(values(u, "Unit", "StartLimitBurst")[0])
        window = float(values(u, "Unit", "StartLimitIntervalSec")[0])
        restart = float(values(u, "Service", "RestartSec")[0])
        self.assertGreater(window, burst * (tries * gap + restart) * 1.25)

    def test_wallpaper_is_the_current_themes(self) -> None:
        u = self.units["ryce-wallpaper.service"]
        self.assertEqual(values(u, "Service", "ExecStart"), ["/usr/bin/awww-daemon --quiet"])
        wait, paint = values(u, "Service", "ExecStartPost")
        for post in (wait, paint):
            self.assertTrue(post.startswith("-"), "a missing image must not stop the daemon")
        self.assertIn("/usr/bin/awww query", wait)
        self.assertNotRegex(wait, r"(?<!\$)\$(?!\$)", "systemd expands a single `$`: write `$$`")
        self.assertEqual(paint, "-%h/.local/bin/ryce-theme wallpaper --no-transition")

    def test_agents_slice_budget(self) -> None:
        u = self.units["ryce-agents.slice"]
        self.assertEqual(values(u, "Slice", "MemoryHigh"), ["24G"])
        self.assertEqual(values(u, "Slice", "MemoryMax"), ["27G"])


if __name__ == "__main__":
    unittest.main()
