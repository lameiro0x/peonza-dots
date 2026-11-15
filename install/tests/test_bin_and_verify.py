"""bin/ryce-term, bin/ryce-update --dry-run and install/verify.sh with faked commands."""
import os
import socket
import textwrap

from harness import REPO, ScriptTest

RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Arch Linux: Recent news updates</title>
<item><title>Old news</title><link>https://archlinux.org/news/old/</link>
<pubDate>Mon, 01 Sep 2026 10:00:00 +0000</pubDate></item>
<item><title>iptables now uses the nft backend</title><link>https://archlinux.org/news/nft/</link>
<pubDate>Sat, 08 Nov 2026 10:00:00 +0000</pubDate></item>
</channel></rss>
"""


class FakeTools(ScriptTest):
    def shell_fake(self, name, body):
        p = self.bin / name
        if p.exists() or p.is_symlink():
            p.unlink()
        p.write_text("#!/bin/sh\n" + textwrap.dedent(body))
        p.chmod(0o755)


class RyceTerm(FakeTools):
    def test_runs_kitty_in_the_agents_slice(self):
        runtime = self.tmp / "rt"
        runtime.mkdir()
        try:
            sock = socket.socket(socket.AF_UNIX)
            self.addCleanup(sock.close)
            sock.bind(str(runtime / "bus"))
        except PermissionError:
            self.skipTest("this sandbox forbids unix sockets")
        r = self.run_script(REPO / "bin/ryce-term", "--title", "x", env={"XDG_RUNTIME_DIR": str(runtime)})
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        self.assertRegex(calls[0], r"^systemd-run --user --scope --quiet --collect "
                                   r"--slice=ryce-agents.slice --unit=ryce-term-\d+ -- kitty --title x$")
        self.assertEqual(calls[1], "kitty --title x")

    def test_plain_kitty_without_a_user_bus(self):
        r = self.run_script(REPO / "bin/ryce-term", env={"XDG_RUNTIME_DIR": str(self.tmp / "none")})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), ["kitty"])


class RyceUpdate(FakeTools):
    def setUp(self):
        super().setUp()
        root = self.tmp / "root"
        (root / "var/log").mkdir(parents=True)
        (root / "var/log/pacman.log").write_text(
            "[2026-10-01T09:00:00+0200] [PACMAN] starting full system upgrade\n"
            "[2026-11-01T09:00:00+0100] [PACMAN] starting full system upgrade\n"
            "[2026-11-01T09:01:00+0100] [ALPM] upgraded foo (1-1 -> 2-1)\n")
        (self.tmp / "news.xml").write_text(RSS)
        self.shell_fake("curl", f"""\
            while [ $# -gt 0 ]; do [ "$1" = -o ] && cp '{self.tmp}/news.xml' "$2"; shift; done
            """)
        self.shell_fake("pacman-conf", "printf 'linux-firmware-mediatek\\nhyprland\\nhyprutils\\n'\n")
        self.shell_fake("checkupdates", """\
            echo 'firefox 144.0-1 -> 145.0-1'
            echo 'hyprland 0.57.1-1 -> 0.58.0-1 [ignored]'
            echo 'hyprutils 0.14.3-1 -> 0.15.0-1 [ignored]'
            echo 'hyprlock 0.9.7-1 -> 0.9.8-1 [ignored]'
            echo 'quickshell 0.3.2-1 -> 0.3.2-2'
            """)
        self.env["RYCE_ROOT"] = str(root)

    def test_dry_run_shows_new_news_and_the_deliberate_ritual(self):
        r = self.run_script(REPO / "bin/ryce-update", "--dry-run")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("iptables now uses the nft backend", out)
        self.assertNotIn("Old news", out)
        self.assertIn("sudo pacman -S hyprland hyprutils hyprlock", out)
        self.assertIn("config ok", out)
        self.assertIn("⚠ hyprlock: bloqueo de pantalla", out)
        self.assertNotIn("sudo pacman -Syu", "\n".join(self.calls()))

    def test_refuses_without_the_pin(self):
        self.shell_fake("pacman-conf", "echo linux-firmware-mediatek\n")
        r = self.run_script(REPO / "bin/ryce-update", "--dry-run")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("system-setup.sh", r.stderr)


class Verify(FakeTools):
    def test_fails_gracefully_outside_the_new_pc(self):
        env = {"HYPRLAND_INSTANCE_SIGNATURE": "", "XDG_RUNTIME_DIR": str(self.tmp)}
        r = self.run_script(REPO / "install/verify.sh", env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"Resultado: \d+ ✅ · [1-9]\d* ❌ · \d+ ⚠️")
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse(any(c.startswith("hyprctl dispatch") for c in self.calls()))

    def test_wifi_only_is_a_warning_not_a_failure(self):
        self.shell_fake("nmcli", "printf 'wifi:connected\\nloopback:connected (externally)\\n'\n")
        env = {"HYPRLAND_INSTANCE_SIGNATURE": "", "XDG_RUNTIME_DIR": str(self.tmp)}
        r = self.run_script(REPO / "install/verify.sh", "--no-probe", env=env)
        self.assertIn("⚠️  conectado solo por Wi-Fi", r.stdout)
        self.assertNotIn("❌ sin red", r.stdout)

    def test_probe_never_runs_without_a_terminal(self):
        env = {"HYPRLAND_INSTANCE_SIGNATURE": "x", "XDG_RUNTIME_DIR": str(self.tmp)}
        r = self.run_script(REPO / "install/verify.sh", env=env)
        self.assertIn("prueba del borde de espera omitida", r.stdout)
        self.assertFalse(any(c.startswith("hyprctl dispatch") for c in self.calls()))

    def bar(self, active):
        self.shell_fake("systemctl", f"""\
            [ "$1" = --user ] && [ "$2" = is-active ] || exit 1
            for u in {' '.join(active)}; do [ "$4" = "$u" ] && exit 0; done
            exit 3
            """)
        env = {"HYPRLAND_INSTANCE_SIGNATURE": "", "XDG_RUNTIME_DIR": str(self.tmp)}
        return self.run_script(REPO / "install/verify.sh", "--no-probe", env=env).stdout

    def test_the_bar_is_quickshell_or_the_waybar_fallback(self):
        self.assertIn("✅ barra: Quickshell", self.bar(["quickshell.service"]))
        out = self.bar(["waybar.service"])
        self.assertIn("⚠️  barra de reserva: Waybar", out)
        self.assertNotIn("❌ no hay barra", out)
        self.assertIn("❌ no hay barra", self.bar([]))
