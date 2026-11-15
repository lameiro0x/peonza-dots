#!/usr/bin/env bash
# A hidden, real Hyprland 0.57 stage inside the running session, for screenshots.
#
#   bash tools/stage/nested.sh start [THEME]      start the stage (default theme: origen)
#   bash tools/stage/nested.sh windows            open three kitty windows on workspaces 1-3
#   bash tools/stage/nested.sh qs [DIR]           run this worktree's quickshell/ryce (or DIR) in it
#   bash tools/stage/nested.sh wall               paint the stage theme's wallpaper (awww)
#   bash tools/stage/nested.sh run CMD...         run CMD inside the stage (its env)
#   bash tools/stage/nested.sh shot OUT.png       grim the stage's 1920x1080 output
#   bash tools/stage/nested.sh theme THEME        switch the stage to THEME, as ryce-theme set does
#   bash tools/stage/nested.sh stop               kill the stage and everything in it
#
# How: the running Hyprland spawns a nested Hyprland (Aquamarine's Wayland backend) as a
# floating 1920x1080 window on the hidden workspace special:ryce-stage-<name> with
# `render_unfocused`, so it keeps rendering while you never see it. Headless Hyprland
# does not start here (no backend), and a hidden window without render_unfocused gets
# no frame callbacks, so grim would hang.
#
# The stage loads THIS worktree's hypr/*.lua with the chosen theme's palette — but never
# autostart.lua: it would import the stage's WAYLAND_DISPLAY into the user's systemd
# manager and start the real session units against the stage. The stage has its own
# theme state (RYCE_THEME_STATE) and agentd dir (RYCE_AGENTD_DIR) so nothing it does
# touches ~/.local/state/ryce or $XDG_RUNTIME_DIR/agentd, and its own D-Bus session bus:
# on the user's, the stage's bar would list the user's players (MPRIS) and tray icons.
# `theme` is the stage's `ryce-theme set`: the wallpaper with the theme's transition, the
# compositor, the shell, and the stage's own kitty, cava, btop and fish (told apart from
# the user's by their WAYLAND_DISPLAY). The shell's theme picker reaches it through a
# `ryce-theme` stub first on its PATH, so the picker never switches the real desktop.
#
# Needs the real session (WAYLAND_DISPLAY, HYPRLAND_INSTANCE_SIGNATURE) and must run
# outside Claude Code's sandbox (hyprctl, sockets).
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
# RYCE_STAGE=<name> runs an independent stage, so parallel makers do not collide.
STAGE=${RYCE_STAGE:-main}
case $STAGE in *[!a-z0-9-]*) echo "nested.sh: RYCE_STAGE must be [a-z0-9-]" >&2; exit 2 ;; esac
RUN=${XDG_RUNTIME_DIR:?}/ryce-stage-$STAGE
ENVF=$RUN/env
die() { printf 'nested.sh: %s\n' "$*" >&2; exit 1; }

# Wayland sockets in the runtime dir, one per line, sorted.
sockets() {
  local f
  for f in "$XDG_RUNTIME_DIR"/wayland-*; do
    case ${f##*/} in wayland-*[!0-9]*) continue ;; esac
    [ -S "$f" ] && printf '%s\n' "${f##*/}"
  done | sort
}

load_env() {
  [ -f "$ENVF" ] || die "no stage running (bash tools/stage/nested.sh start)"
  # shellcheck disable=SC1090
  . "$ENVF"
  export WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE RYCE_THEME_STATE RYCE_AGENTD_DIR DBUS_SESSION_BUS_ADDRESS
}

# Processes called $1 that live in this stage: their WAYLAND_DISPLAY is the stage's.
stage_pids() {
  local p
  for p in $(pgrep -u "$(id -u)" -x "$1"); do
    tr '\0' '\n' 2>/dev/null < "/proc/$p/environ" | grep -qxF "WAYLAND_DISPLAY=$WAYLAND_DISPLAY" && echo "$p"
  done
  return 0
}

# The stage's awww shows the current theme's picture through the real ryce-theme's
# `wallpaper`, which only paints: the theme's transition, or none with --no-transition.
paint() {
  awww query >/dev/null 2>&1 || return 0
  python3 "$ROOT/bin/ryce-theme" wallpaper "$@" || true
}

set_theme() {
  local t=$1
  [ -d "$ROOT/themes/$t" ] || die "unknown theme $t"
  mkdir -p "$RUN/state"
  # Only the missing ones: a caller may have put its own copy of a theme there.
  for d in "$ROOT"/themes/*/; do
    d=${d%/}; [ -e "$RUN/state/${d##*/}" ] || ln -sfn "$d" "$RUN/state/${d##*/}"
  done
  ln -sfn "$t" "$RUN/state/current.tmp" && mv -T "$RUN/state/current.tmp" "$RUN/state/current"
  cp "$ROOT/themes/$t/hypr/palette.lua" "$RUN/hypr/palette.lua"
}

cmd=${1:-}; shift || true
case $cmd in
  start)
    theme=${1:-origen}
    [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || die "run it from the real Hyprland session"
    [ ! -f "$ENVF" ] || die "a stage is already running (stop it first)"
    rm -rf "$RUN"; mkdir -p "$RUN/hypr" "$RUN/agentd/waybar"
    for f in "$ROOT"/hypr/*.lua; do
      case $(basename "$f") in autostart.lua|local.lua|palette.lua) continue ;; esac
      cp "$f" "$RUN/hypr/"
    done
    # hyprland.lua loads autostart: give it an empty one.
    printf -- '-- stage: no session units here\n' > "$RUN/hypr/autostart.lua"
    printf -- 'hl.monitor({ output = "", mode = "1920x1080", position = "0x0", scale = 1 })\n' > "$RUN/hypr/monitors.lua"
    set_theme "$theme"
    before=$(sockets)
    # Instances that existed before this start: never adopt one of them.
    known=$(for d in "$XDG_RUNTIME_DIR"/hypr/*/; do d=${d%/}; printf '%s\n' "${d##*/}"; done)
    hyprctl dispatch "hl.dsp.exec_cmd(\"start-hyprland -- --config $RUN/hypr/hyprland.lua\", { workspace = \"special:ryce-stage-$STAGE silent\", float = true, size = { 1920, 1080 }, render_unfocused = true })" >/dev/null
    disp=""
    for _ in $(seq 1 40); do
      sleep 0.25
      disp=$(comm -13 <(printf '%s\n' "$before") <(sockets) | head -1)
      [ -n "$disp" ] && break
    done
    [ -n "$disp" ] || die "the nested Hyprland did not create a Wayland socket"
    sig=""
    for _ in $(seq 1 120); do
      sleep 0.25
      for d in "$XDG_RUNTIME_DIR"/hypr/*/; do
        d=${d%/}; d=${d##*/}
        [ "$d" = "$HYPRLAND_INSTANCE_SIGNATURE" ] && continue
        # Only instances that appeared after this start: parallel stages must not
        # adopt each other's compositor.
        printf '%s\n' "$known" | grep -qxF "$d" && continue
        # A killed compositor leaves its directory and sockets behind: only a socket
        # that answers counts.
        [ -S "$XDG_RUNTIME_DIR/hypr/$d/.socket.sock" ] || continue
        HYPRLAND_INSTANCE_SIGNATURE=$d timeout 2 hyprctl version >/dev/null 2>&1 && { sig=$d; break; }
      done
      [ -n "$sig" ] && break
    done
    [ -n "$sig" ] || die "no instance signature for the stage"
    bus=unix:path=$RUN/bus
    dbus-daemon --session --address="$bus" --fork --print-pid > "$RUN/bus.pid"
    printf 'WAYLAND_DISPLAY=%s\nHYPRLAND_INSTANCE_SIGNATURE=%s\nRYCE_THEME_STATE=%s\nRYCE_AGENTD_DIR=%s\nDBUS_SESSION_BUS_ADDRESS=%s\n' \
      "$disp" "$sig" "$RUN/state" "$RUN/agentd" "$bus" > "$ENVF"
    echo "stage up: $disp ($sig), theme $theme"
    ;;
  windows)
    load_env
    for ws in 1 2 3; do
      hyprctl dispatch "hl.dsp.exec_cmd(\"kitty --title stage-$ws sh -c 'printf \\\"workspace $ws\\\\n\\\"; sleep 3600'\", { workspace = \"$ws silent\" })" >/dev/null
    done
    sleep 1.5
    hyprctl dispatch 'hl.dsp.focus({ workspace = 1 })' >/dev/null
    ;;
  qs)
    load_env
    [ -f "$RUN/qs.pid" ] && kill "$(cat "$RUN/qs.pid")" 2>/dev/null || true
    # Its own XDG_STATE_HOME: desk/wall toggles in the stage never write the user's state.
    # The widgets that talk to the user's services get stage paths too: Aria's mpv socket
    # and credentials, Hito's .env (absent: «not configured»), and a systemctl that only
    # logs, so opening Aria never starts the real ryce-aria.service. The theme picker
    # finds a ryce-theme that switches this stage only (the picture picker is not staged).
    mkdir -p "$RUN/xdg-state" "$RUN/aria" "$RUN/bin"
    printf '#!/bin/sh\nprintf "%%s\\n" "$*" >> "%s/systemctl.log"\n' "$RUN" > "$RUN/bin/systemctl"
    cat > "$RUN/bin/ryce-theme" <<EOF
#!/bin/sh
# The stage's ryce-theme (tools/stage/nested.sh): switches stage $STAGE, never the desktop.
case \$1 in
  set) [ -n "\$2" ] && [ -d "$ROOT/themes/\$2" ] || { echo "ryce-theme: no existe el tema «\$2»" >&2; exit 2; }
       RYCE_STAGE=$STAGE exec bash "$ROOT/tools/stage/nested.sh" theme "\$2" ;;
  get) readlink "$RUN/state/current" ;;
  *) echo "ryce-theme: en el escenario solo hay set y get" >&2; exit 2 ;;
esac
EOF
    chmod +x "$RUN/bin/systemctl" "$RUN/bin/ryce-theme"
    XDG_STATE_HOME="$RUN/xdg-state" RYCE_ARIA_RUN="${RYCE_ARIA_RUN:-$RUN/aria}" RYCE_ARIA_CONFIG="${RYCE_ARIA_CONFIG:-$RUN/aria/aria.json}" \
      RYCE_HITO_ENV="${RYCE_HITO_ENV:-$RUN/hito.env}" PATH="$RUN/bin:$PATH" \
      nohup qs -p "${1:-$ROOT/quickshell/ryce}" > "$RUN/qs.log" 2>&1 &
    echo $! > "$RUN/qs.pid"
    sleep 2.5
    echo "qs log: $RUN/qs.log"; tail -n 15 "$RUN/qs.log"
    ;;
  wall)
    load_env
    awww query >/dev/null 2>&1 || (nohup awww-daemon > "$RUN/awww.log" 2>&1 &)
    for _ in $(seq 1 20); do awww query >/dev/null 2>&1 && break; sleep 0.25; done
    paint --no-transition
    ;;
  run)
    load_env
    "$@"
    ;;
  shot)
    load_env
    out=${1:?shot OUT.png}
    timeout 10 grim -t png "$out"
    echo "$out"
    ;;
  theme)
    load_env
    set_theme "${1:?theme NAME}"
    # bin/ryce-theme's order: the picture starts moving first, the rest lands behind it.
    paint
    # By pid: `-p <path>` would also reach the user's live shell running the same path.
    [ -f "$RUN/qs.pid" ] && qs ipc --pid "$(cat "$RUN/qs.pid")" call theme reload >/dev/null 2>&1 || true
    hyprctl reload >/dev/null || true
    for p in $(stage_pids kitty); do kill -USR1 "$p" 2>/dev/null || true; done
    for n in cava btop; do
      for p in $(stage_pids "$n"); do kill -USR2 "$p" 2>/dev/null || true; done
    done
    # A stage with its own HOME (tools/showcase/stage.sh): its fish shells repaint on this.
    [ ! -d "$RUN/home" ] || HOME=$RUN/home fish --no-config -c "set -U ryce_theme $1" || true
    ;;
  stop)
    if [ -f "$ENVF" ]; then
      load_env
      [ -f "$RUN/qs.pid" ] && kill "$(cat "$RUN/qs.pid")" 2>/dev/null || true
      for p in $(stage_pids awww-daemon); do kill "$p" 2>/dev/null || true; done
      hyprctl dispatch 'hl.dsp.exit()' >/dev/null 2>&1 || true
    fi
    [ -f "$RUN/bus.pid" ] && kill "$(cat "$RUN/bus.pid")" 2>/dev/null || true
    sleep 0.5
    pkill -f "start-hyprland -- --config $RUN/hypr/hyprland.lua" 2>/dev/null || true
    pkill -f "Hyprland --config $RUN/hypr/hyprland.lua" 2>/dev/null || true
    rm -f "$ENVF"
    echo "stage stopped"
    ;;
  *)
    sed -n '2,10s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; exit 2 ;;
esac
