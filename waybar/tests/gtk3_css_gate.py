#!/usr/bin/env python3
"""GTK3 CSS gate: parse a stylesheet with the same GtkCssProvider Waybar uses.

    python3 waybar/tests/gtk3_css_gate.py waybar/style.css

Waybar exits 1 on the first property or value GTK3 rejects, which under
`Restart=always` becomes a bar that flaps every 3 s. This catches it first.
Exit 0 = clean, 1 = parse errors (one line each, file:line:col), 2 = no GTK3 to
ask. Off Linux it prints SKIP and exits 0: there is no Waybar to protect there,
and test_style.py carries the offline twin of this check.

python-gobject comes from the system, or else from the stage harness prefix
(~/.cache/ryce-verify/root, override with RYCE_VERIFY) so the stage box needs no
install.
"""

from __future__ import annotations

import glob
import os
import sys


def import_gtk():
    """Return (Gtk, GLib) for GTK 3, or None when python-gobject is unavailable."""
    def attempt():
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import GLib, Gtk
        return Gtk, GLib

    try:
        return attempt()
    except (ImportError, AttributeError, ValueError):
        pass
    root = os.path.join(os.environ.get("RYCE_VERIFY", os.path.expanduser("~/.cache/ryce-verify")), "root", "usr")
    sites = sorted(glob.glob(f"{root}/lib/python3*/site-packages"))
    if not sites:
        return None
    sys.path.insert(0, sites[-1])
    os.environ["GI_TYPELIB_PATH"] = os.pathsep.join(
        filter(None, [f"{root}/lib/girepository-1.0", os.environ.get("GI_TYPELIB_PATH")]))
    for name in [m for m in sys.modules if m == "gi" or m.startswith("gi.")]:
        del sys.modules[name]
    try:
        return attempt()
    except (ImportError, AttributeError, ValueError):
        return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    path = os.path.abspath(argv[1])
    if not sys.platform.startswith("linux"):
        print(f"gtk3_css_gate: SKIP ({sys.platform}: no GTK3 here; test_style.py covers the offline rules)")
        return 0
    if not os.path.isfile(path):
        print(f"gtk3_css_gate: {path}: no such file", file=sys.stderr)
        return 2
    mods = import_gtk()
    if mods is None:
        print("gtk3_css_gate: python-gobject (gi) with GTK 3 is not importable; "
              "install python-gobject, or add it to tools/stage/harness.sh", file=sys.stderr)
        return 2
    Gtk, GLib = mods

    errors: list[str] = []

    def on_error(_provider, section, error) -> None:
        f = section.get_file()
        where = f.get_path() if f is not None else path
        errors.append(f"{where}:{section.get_start_line() + 1}:{section.get_start_position() + 1}: {error.message}")

    provider = Gtk.CssProvider()
    provider.connect("parsing-error", on_error)
    try:
        provider.load_from_path(path)
    except GLib.Error as e:  # GTK3 also raises the first error for compatibility
        if not errors:
            errors.append(f"{path}: {e.message}")
    for line in errors:
        print(line)
    print(f"gtk3_css_gate: {'FAIL' if errors else 'ok'} (GTK {Gtk.get_major_version()}."
          f"{Gtk.get_minor_version()}.{Gtk.get_micro_version()}, {len(errors)} error(s))")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
