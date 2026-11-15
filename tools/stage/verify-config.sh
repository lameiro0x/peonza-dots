#!/bin/sh
# Config gate: run Hyprland 0.57.1 --verify-config on a Lua config.
#   tools/stage/verify-config.sh hypr/hyprland.lua
# Exit 0 only when Hyprland prints `config ok` and nothing else in its result.
# (Hyprland itself exits 0 even when the config has errors — grep the text.)
# RYCE_STRICT=1 is exported so hyprland.lua re-raises errors from its pcall'd
# modules instead of swallowing them for the live session.
set -u
D="${RYCE_VERIFY:-$HOME/.cache/ryce-verify}"
cfg="${1:?usage: verify-config.sh path/to/hyprland.lua}"
export LD_LIBRARY_PATH="$D/root/usr/lib" RYCE_STRICT=1
# A private runtime dir keeps the probe away from the live session's sockets.
RT=$(mktemp -d /tmp/ryce-vc.XXXXXX); export XDG_RUNTIME_DIR="$RT"
unset HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY
cd "$(dirname "$cfg")" || exit 2
out=$("$D/root/usr/bin/Hyprland" --verify-config -c "$(pwd)/$(basename "$cfg")" 2>&1 \
      | sed -n '/Config parsing result/,$p' | grep -v 'Config parsing result' | sed '/^[[:space:]]*$/d')
rm -rf "$RT"
printf '%s\n' "$out"
[ "$out" = "config ok" ]
