#!/bin/sh
# Point GSettings (and Thunar's xfconf channel) at theme ID. On Wayland GTK takes
# its theme, icons, cursor and fonts from org.gnome.desktop.interface, not from
# settings.ini, and the portal's color-scheme decides dark mode for libadwaita and
# Firefox. bin/ryce-theme runs it after the theme link moved; deploy runs it once.
#
#   sh gsettings.sh [ID]      e.g. origen; reads <state>/ID/theme.json, where
#                             <state> = $RYCE_THEME_STATE or ~/.local/state/ryce/theme;
#                             no ID = the theme <state>/current points at (autostart)
#
# Running GTK3 apps (Thunar) re-read ~/.config/gtk-3.0/gtk.css only when gtk-theme
# changes, so it is toggled away and back. GTK4/libadwaita apps restyle on restart.
# Idempotent, silent on success. Needs the session bus: run it inside the Hyprland
# session (or a user shell on the same seat), not from a bare TTY or chroot.
set -eu
state=${RYCE_THEME_STATE:-$HOME/.local/state/ryce/theme}
if [ $# -gt 0 ]; then id=$1; else
  id=$(readlink "$state/current" 2>/dev/null || true)
  id=${id%/} id=${id##*/}
fi
case $id in
  '' | *[!a-z0-9-]*) echo "gsettings.sh: usage: gsettings.sh [THEME_ID] (got '$id'; no $state/current either)" >&2; exit 2 ;;
esac
json=$state/$id/theme.json
schema=org.gnome.desktop.interface

[ -r "$json" ] || { echo "gsettings.sh: cannot read $json (render the themes and deploy first)" >&2; exit 1; }
command -v gsettings >/dev/null 2>&1 || { echo "gsettings.sh: gsettings missing (package glib2)" >&2; exit 1; }
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ ! -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/bus" ]; then
  echo "gsettings.sh: no session D-Bus; values would land in a memory backend and vanish" >&2
  exit 1
fi

# One value per line: gtk theme, icon theme, cursor, UI font, mono font, scheme
# (light|dark: tools/tokens.py derives it from bg0; one rule for every toolkit).
vals=$(python3 -c '
import json, sys
t = json.load(open(sys.argv[1], encoding="utf-8"))
d, f = t["desktop"], t["fonts"]
print(d["gtk_theme"], d["icon_theme"], d["cursor"], f["ui"], f["mono"], t["scheme"], sep="\n")
' "$json") || { echo "gsettings.sh: $json is not a rendered ryce theme (desktop/fonts/scheme keys)" >&2; exit 1; }
line() { printf '%s\n' "$vals" | sed -n "$1p"; }
gtk=$(line 1) icons=$(line 2) cursor=$(line 3) ui=$(line 4) mono=$(line 5) scheme=$(line 6)
# Martian Mono is a wide monospace: at 10 it sets the same measure as a grotesque at 11.
case $ui in "Martian Mono") size=10 ;; *) size=11 ;; esac

gsettings set $schema icon-theme "$icons"
gsettings set $schema cursor-theme "$cursor"
gsettings set $schema cursor-size 32   # as hypr/env.lua's XCURSOR_SIZE
gsettings set $schema font-name "$ui $size"
gsettings set $schema monospace-font-name "$mono 11"
# The portal's colour-scheme (libadwaita, Firefox) follows the theme's polarity.
gsettings set $schema color-scheme "prefer-$scheme"
# File pickers (GTK3, GTK4 and the portal's) show hidden files: Ctrl+H, their own toggle,
# is the desk's focus-left key (keys/keymap.tsv) and never reaches them; the user keeps
# Ctrl+H/J/K/L for the focus (2026-11-15).
gsettings set org.gtk.Settings.FileChooser show-hidden true
gsettings set org.gtk.gtk4.Settings.FileChooser show-hidden true 2>/dev/null || true
# The toggle goes last: running GTK3 apps re-read gtk.css only on a gtk-theme change.
[ "$gtk" = Adwaita ] && away=HighContrast || away=Adwaita
gsettings set $schema gtk-theme "$away"
gsettings set $schema gtk-theme "$gtk"

# Thunar: the look in gtk.css assumes breadcrumbs, symbolic side-pane icons (they
# take the text colour) and a status line. Set only while unset, so a choice made
# later in Thunar's own menus survives the next theme switch.
if command -v xfconf-query >/dev/null 2>&1; then
  default() {
    xfconf-query -c thunar -p "$1" >/dev/null 2>&1 ||
      xfconf-query -c thunar -p "$1" -n -t "$2" -s "$3" ||
      echo "gsettings.sh: xfconf thunar $1 not set (is xfconfd reachable?)" >&2
  }
  default /last-location-bar string ThunarLocationButtons
  default /last-side-pane string ThunarShortcutsPane
  default /last-statusbar-visible bool true
  default /last-menubar-visible bool false
  default /misc-symbolic-icons-in-sidepane bool true
  default /misc-symbolic-icons-in-toolbar bool true
  default /misc-small-toolbar-icons bool true
  default /misc-folders-first bool true
  default /misc-thumbnail-draw-frames bool false
fi
