#!/bin/sh
# Render a scene of this repo on an invisible headless sway and screenshot it.
#   tools/stage/scene.sh bar|sidebar|desktop|lock [OUT.png]
# Runs on the stage box (the Arch laptop) from a copy of the repo; needs
# tools/stage/harness.sh to have run once. Nothing shows on the box's screen.
#
#   bar      wallpaper + Waybar (repo config/CSS) fed with agentd files
#   sidebar  bar + Quickshell `ryce` config with the sidebar opened over IPC
#   desktop  sidebar + two kitty windows (software GL) tiled by sway
#   lock     bar + hyprlock (repo hypr/hyprlock.conf) with a waiting line in lock.txt
#
# agentd files: RYCE_AGENTD=sample (default) copies contracts/waybar.sample and
# contracts/roster.sample.json; RYCE_AGENTD=fixtures runs
# `python3 -m agentd --once --no-dispatch --fixtures agentd/tests/fixtures/stage`.
# This is a stand-in for Hyprland: borders, blur and glow are NOT represented.
set -u
REPO=$(cd "$(dirname "$0")/../.." && pwd)
D="${RYCE_VERIFY:-$HOME/.cache/ryce-verify}"
# One scene at a time on the box: scenes share the runtime dir and kill the
# stage's processes on exit. Parallel makers queue here instead of colliding.
exec 9>/tmp/ryce-stage.lock
flock -w 300 9 || { echo "stage busy for 300 s, giving up" >&2; exit 3; }
scene="${1:-bar}"; shot="${2:-/tmp/ryce-scene-$scene.png}"
RT=/tmp/ryce-rt
OUT=HEADLESS-1

pkill -f "$D/root/usr/bin/" 2>/dev/null; sleep 0.5
rm -rf "$RT"; mkdir -p "$RT"; chmod 700 "$RT"
export XDG_RUNTIME_DIR="$RT" LD_LIBRARY_PATH="$D/root/usr/lib"
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 WLR_HEADLESS_OUTPUTS=1
unset WAYLAND_DISPLAY DISPLAY HYPRLAND_INSTANCE_SIGNATURE SWAYSOCK

# Fonts: system fonts + the repo's vendored ones (Departure Mono).
cat > "$RT/fonts.conf" <<EOF
<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>
<dir>$REPO/assets/fonts</dir><cachedir>$RT/fc-cache</cachedir></fontconfig>
EOF
export FONTCONFIG_FILE="$RT/fonts.conf"

wall=$(ls "$REPO"/assets/wallpapers/*.png 2>/dev/null | head -1)
{
  echo "output $OUT resolution 1920x1080"
  if [ -n "$wall" ]; then echo "output $OUT bg $wall fill"; else echo "output $OUT bg #0e0e13 solid_color"; fi
  echo "default_border pixel 2"
  echo "gaps inner 6"; echo "gaps outer 10"
  echo "client.focused #ffffff #0e0e13 #e6e6ec #ffffff #ffffff"
  echo "client.unfocused #2c2c37 #0e0e13 #a4a4b2 #2c2c37 #2c2c37"
} > "$RT/sway.cfg"
setsid "$D/root/usr/bin/sway" -c "$RT/sway.cfg" > "$RT/sway.log" 2>&1 < /dev/null &
W=""
for _ in 1 2 3 4 5 6 7 8 9 10; do
  for s in "$RT"/wayland-[0-9]; do [ -S "$s" ] && W=$(basename "$s"); done
  [ -n "$W" ] && break; sleep 0.5
done
SWAYSOCK=""
for s in "$RT"/sway-ipc.*.sock; do [ -S "$s" ] && SWAYSOCK="$s"; done
export WAYLAND_DISPLAY="$W" SWAYSOCK

# agentd state for the bar and the sidebar.
AG="$RT/agentd"; mkdir -p "$AG/waybar"
if [ "${RYCE_AGENTD:-sample}" = fixtures ]; then
  (cd "$REPO" && PYTHONPATH=agentd python3 -m agentd --once --no-dispatch \
      --fixtures agentd/tests/fixtures/stage --outdir "$AG") > "$RT/agentd.log" 2>&1
else
  for f in "$REPO"/contracts/waybar.sample/OUTPUT-*.json; do
    cp "$f" "$AG/waybar/$(basename "$f" | sed "s/^OUTPUT-/$OUT-/")"
  done
  cp "$REPO/contracts/waybar.sample/agents.json" "$AG/waybar/agents.json"
  cp "$REPO/contracts/roster.sample.json" "$AG/roster.json"
fi

# Waybar with the repo config. jsonc comments are fine for Waybar.
setsid "$D/root/usr/bin/waybar" -l debug -c "$REPO/waybar/config.jsonc" -s "$REPO/waybar/style.css" \
  > "$RT/waybar.log" 2>&1 < /dev/null &

if [ "$scene" = sidebar ] || [ "$scene" = desktop ]; then
  export QT_PLUGIN_PATH="$D/root/usr/lib/qt6/plugins" QML_IMPORT_PATH="$D/root/usr/lib/qt6/qml" \
         QML2_IMPORT_PATH="$D/root/usr/lib/qt6/qml" QT_QPA_PLATFORM=wayland
  export RYCE_RUNTIME="$AG"
  setsid "$D/root/usr/bin/quickshell" -p "$REPO/quickshell/ryce" > "$RT/quickshell.log" 2>&1 < /dev/null &
  sleep 3
  "$D/root/usr/bin/quickshell" -p "$REPO/quickshell/ryce" ipc call sidebar open >> "$RT/quickshell.log" 2>&1
fi

if [ "$scene" = lock ]; then
  # hyprlock over the stage (ext-session-lock). Software GL: the stage has no dmabuf.
  # A private HOME so `~/Pictures/wallpapers/ryce/...` in hyprlock.conf resolves to
  # the repo's generated wallpaper, as it will after deploy.sh on the real PC.
  printf '%s' "${RYCE_LOCK_TEXT:-1 agente te espera}" > "$AG/lock.txt"
  FH="$RT/home"; mkdir -p "$FH/Pictures/wallpapers"
  ln -sfn "$REPO/assets/wallpapers" "$FH/Pictures/wallpapers/ryce"
  HOME="$FH" LC_TIME="${RYCE_LC_TIME:-es_ES.UTF-8}" LIBGL_ALWAYS_SOFTWARE=1 \
    setsid "$D/root/usr/bin/hyprlock" -c "$REPO/hypr/hyprlock.conf" > "$RT/hyprlock.log" 2>&1 < /dev/null &
fi

if [ "$scene" = desktop ]; then
  export LIBGL_ALWAYS_SOFTWARE=1
  setsid kitty -c "$REPO/apps/kitty/kitty.conf" sh -c 'fastfetch; sleep 30' > "$RT/kitty1.log" 2>&1 < /dev/null &
  sleep 1.5
  setsid kitty -c "$REPO/apps/kitty/kitty.conf" sh -c 'btop' > "$RT/kitty2.log" 2>&1 < /dev/null &
fi

sleep "${RYCE_SETTLE:-4}"
grim -o "$OUT" "$shot" && echo "shot: $shot"
echo "--- waybar log (warnings/errors):"; grep -E '\[(warning|error|critical)\]' "$RT/waybar.log" | head -20
[ -f "$RT/hyprlock.log" ] && { echo "--- hyprlock log:"; grep -i -E "err|fail|warn" "$RT/hyprlock.log" | head -20; }
[ -f "$RT/quickshell.log" ] && { echo "--- quickshell log:"; grep -i -E 'warn|error|fail|unavailable' "$RT/quickshell.log" | head -30; }
pgrep -f "$D/root/usr/bin/waybar" >/dev/null && echo "waybar: alive" || echo "waybar: DEAD"
if [ "$scene" = sidebar ] || [ "$scene" = desktop ]; then pgrep -f "$D/root/usr/bin/quickshell" >/dev/null && echo "quickshell: alive" || echo "quickshell: DEAD"; fi
pkill -f "$D/root/usr/bin/" 2>/dev/null; pkill -f "kitty -c $REPO" 2>/dev/null
exit 0
