#!/usr/bin/env bash
# The showcase stage: tools/stage/nested.sh's hidden Hyprland, fully populated with invented
# data, for recording the README's video and screenshots.
#
#   bash tools/showcase/stage.sh up [THEME]           start it (default theme: origen), music playing
#   bash tools/showcase/stage.sh down                 stop it and put the desktop's audio back
#   bash tools/showcase/stage.sh theme THEME          switch the stage's theme (transition included)
#   bash tools/showcase/stage.sh ipc TARGET FN [ARG]  the stage shell's IPC (`qs ipc --pid … call`)
#   bash tools/showcase/stage.sh term WS [CMD...]     a kitty on workspace WS running CMD (fish)
#   bash tools/showcase/stage.sh run CMD...           run CMD in the stage's env (hyprctl, grim…)
#   bash tools/showcase/stage.sh shot OUT.png         screenshot the stage's 1920x1080 output
#   bash tools/showcase/stage.sh record OUT.mp4 [ARG...]  record at 60 fps (ARGs go to wf-recorder)
#   bash tools/showcase/stage.sh stop-record          finish the recording
#
# Nothing of the owner's shows and nothing of the live desktop changes, except two things
# held only while the stage is up and put back by `down` (and by `up` when it fails):
# the default audio sink is a null sink, so the music never plays aloud while the volume
# OSD and every visualiser (they follow the default sink) hear it; and while recording,
# the host's misc.render_unfocused_fps is 60 (the hidden stage renders at 15 otherwise).
#
# The world in it: Hito and Aria's Navidrome are tools/showcase/demo/demo.py on 127.0.0.1
# (invented tasks; five tagged copies of synth.py's track with the themes' own art as
# covers), agentd is demo/roster.json, the players and tray are on the stage's own D-Bus.
# Terminals run in a fresh home made by install/deploy.sh --home (no history, the stage's
# theme), in ~/peonza-dots, with btop's process list hidden (real command lines); open them
# with `term`, not the stage's keybinds (those inherit the user's environment). Tinta and
# Origen show their redistributable pictures (despiece, ocaso): the public repo drops the
# main ones. Must run outside Claude Code's sandbox (hyprctl, sockets, pactl).
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
HERE=$ROOT/tools/showcase
export RYCE_STAGE=showcase
NESTED=(bash "$ROOT/tools/stage/nested.sh")
RUN=${XDG_RUNTIME_DIR:?}/ryce-stage-$RYCE_STAGE
# What `down` must put back lives beside the stage, not in it: `up` wipes the stage dir.
KEEP=$XDG_RUNTIME_DIR/ryce-showcase.restore
SINK=ryce-showcase
RECORDER=${XDG_CACHE_HOME:-$HOME/.cache}/ryce-showcase/wf-recorder/build/wf-recorder
HOST_SIG=${HYPRLAND_INSTANCE_SIGNATURE:-}
die() { printf 'stage.sh: %s\n' "$*" >&2; exit 1; }

stage_env() {
  [ -f "$RUN/env" ] || die "no showcase stage running (bash tools/showcase/stage.sh up)"
  # shellcheck disable=SC1091
  . "$RUN/env"
  export WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE RYCE_THEME_STATE RYCE_AGENTD_DIR DBUS_SESSION_BUS_ADDRESS
}
host() { HYPRLAND_INSTANCE_SIGNATURE=$HOST_SIG hyprctl "$@"; }
fps() { host -j getoption misc.render_unfocused_fps | python3 -c 'import json,sys; print(json.load(sys.stdin)["int"])'; }
set_fps() { host eval "hl.config({ misc = { render_unfocused_fps = $1 } })" >/dev/null; }
# wireplumber's chosen default ("" when none was ever chosen: it then follows priority).
configured_sink() {
  pw-metadata 0 default.configured.audio.sink 2>/dev/null | sed -n "s/.*value:'\(.*\)' type:.*/\1/p"
}
mpv_cmd() { printf '%s\n' "$1" | socat - "UNIX-CONNECT:$RUN/aria/ryce-aria.sock" >/dev/null; }

stop_record() {
  [ -f "$RUN/record.pid" ] || return 0
  kill -INT "$(cat "$RUN/record.pid")" 2>/dev/null || true
  for _ in $(seq 1 40); do kill -0 "$(cat "$RUN/record.pid")" 2>/dev/null || break; sleep 0.25; done
  rm -f "$RUN/record.pid"
  [ ! -f "$KEEP/fps" ] || { set_fps "$(cat "$KEEP/fps")"; rm -f "$KEEP/fps"; }
}

down() {
  stop_record
  [ ! -f "$KEEP/fps" ] || { set_fps "$(cat "$KEEP/fps")"; rm -f "$KEEP/fps"; }
  local f
  for f in demo mpv; do [ -f "$RUN/$f.pid" ] && kill "$(cat "$RUN/$f.pid")" 2>/dev/null || true; done
  "${NESTED[@]}" stop >/dev/null 2>&1 || true
  if [ -f "$KEEP/sink" ]; then
    if [ -s "$KEEP/default" ]; then
      pw-metadata 0 default.configured.audio.sink "$(cat "$KEEP/default")" Spa:String:JSON >/dev/null
    else
      pw-metadata -d 0 default.configured.audio.sink >/dev/null
    fi
    pactl unload-module "$(cat "$KEEP/sink")" 2>/dev/null || true
  fi
  rm -rf "$KEEP"
  echo "showcase down"
}

# A theme of the stage whose main picture is its alternate $2 (an overlay of links).
redistributable() {
  local t=$1 n=$2 o=$RUN/themes/$1 f
  mkdir -p "$o/wallpaper"
  for f in "$ROOT/themes/$t"/*; do [ "${f##*/}" = wallpaper ] || ln -s "$f" "$o/"; done
  for f in "$ROOT/themes/$t/wallpaper"/*; do ln -s "$f" "$o/wallpaper/"; done
  for f in "$ROOT/themes/$t/wallpaper/alt-$n"/*; do ln -sfn "$f" "$o/wallpaper/"; done
  ln -sfn "$o" "$RUN/state/$t"
}

up() {
  local theme=${1:-origen} c port i
  for c in hyprctl dbus-daemon pactl pw-metadata mpv socat ffmpeg kitty fish awww qs python3; do
    command -v "$c" >/dev/null || die "falta $c"
  done
  python3 -c 'import numpy' 2>/dev/null || die "falta numpy (python-numpy): synth.py lo usa"
  [ -n "$HOST_SIG" ] || die "run it from the real Hyprland session"
  [ ! -e "$KEEP" ] || die "a showcase is already up, or did not come down cleanly: bash $0 down"
  mkdir -p "$KEEP"
  trap 'echo "stage.sh: up failed, taking it down" >&2; down >&2' EXIT

  # Audio first: nothing the stage plays may reach the speakers, not even for a moment.
  configured_sink > "$KEEP/default"
  pactl load-module module-null-sink sink_name=$SINK "sink_properties=device.description=peonza-dots" > "$KEEP/sink"
  pw-metadata 0 default.configured.audio.sink "{\"name\":\"$SINK\"}" Spa:String:JSON >/dev/null
  pactl set-sink-volume $SINK 64%

  "${NESTED[@]}" start "$theme"
  stage_env
  redistributable tinta 2      # tinta-despiece, the parts-list sheet
  redistributable origen 1     # origen-ocaso (public domain)

  # The invented world.
  python3 "$HERE/synth.py" "$RUN/track.wav" >/dev/null
  python3 "$HERE/demo/demo.py" media "$RUN/track.wav" "$RUN/media"
  python3 "$HERE/demo/demo.py" roster "$RUN/agentd"
  nohup python3 "$HERE/demo/demo.py" serve "$RUN/demo.port" "$RUN/media" > "$RUN/demo.log" 2>&1 &
  echo $! > "$RUN/demo.pid"
  for _ in $(seq 1 40); do [ -s "$RUN/demo.port" ] && break; sleep 0.1; done
  port=$(cat "$RUN/demo.port" 2>/dev/null) || die "the demo server did not start ($RUN/demo.log)"
  printf 'VITE_SUPABASE_URL=http://127.0.0.1:%s\nVITE_SUPABASE_ANON_KEY=demo\nVITE_APP_EMAIL=demo@peonza.invalid\nVITE_APP_PASSWORD=demo\n' \
    "$port" > "$RUN/hito.env"
  mkdir -p "$RUN/aria"
  printf '{"url":"http://127.0.0.1:%s","user":"demo","pass":"demo"}\n' "$port" > "$RUN/aria/aria.json"
  # Aria's queue as Aria writes it (it reads it once, at start), and the mpv of
  # ryce-aria.service with mpv-mpris on the stage's bus, into the null sink.
  python3 - "$HERE/demo/music.json" "$RUN/aria/ryce-aria-queue.json" <<'EOF'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
songs = {s["id"]: {"id": s["id"], "title": s["title"], "artist": doc["artist"], "album": doc["album"],
                   "duration": s["duration"], "track": n, "coverArt": s["coverArt"]}
         for n, s in enumerate(doc["songs"], 1)}
json.dump(songs, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
EOF
  nohup mpv --idle=yes --no-video --no-terminal --msg-level=all=no --input-ipc-server="$RUN/aria/ryce-aria.sock" \
    --ytdl=no --audio-display=no --save-position-on-quit=no --resume-playback=no --cache=yes \
    --audio-device=pipewire/$SINK --loop-playlist=inf > "$RUN/mpv.log" 2>&1 &
  echo $! > "$RUN/mpv.pid"

  # The terminals' home: a fresh install of this repo, on the stage's theme state.
  mkdir -p "$RUN/home"
  bash "$ROOT/install/deploy.sh" --home "$RUN/home" > "$RUN/deploy.log"
  rm -rf "$RUN/home/.local/state/ryce/theme"
  ln -s "$RUN/state" "$RUN/home/.local/state/ryce/theme"
  ln -sfn "$RUN/bin/ryce-theme" "$RUN/home/.local/bin/ryce-theme"
  # btop without its process list (the host's real command lines), on loopback (the demo
  # server's stream, never the LAN address).
  rm "$RUN/home/.config/btop/btop.conf"
  { sed 's/^shown_boxes = .*/shown_boxes = "cpu mem net"/' "$ROOT/apps/btop/btop.conf"; echo 'net_iface = "lo"'; } \
    > "$RUN/home/.config/btop/btop.conf"
  mkdir -p "$RUN/home/peonza-dots"
  for i in README.md agentd apps assets bin contracts hypr install keys quickshell systemd theme themes tools waybar; do
    [ ! -e "$ROOT/$i" ] || cp -as "$ROOT/$i" "$RUN/home/peonza-dots/"
  done
  mkdir -p "$RUN/bin"
  cat > "$RUN/bin/peonza-term" <<EOF
#!/bin/sh
# kitty in the showcase's home (tools/showcase/stage.sh term): spawned by the stage's
# Hyprland, whose environment is the user's session's.
unset XDG_CONFIG_HOME XDG_DATA_HOME XDG_STATE_HOME XDG_CACHE_HOME
export HOME="$RUN/home" DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" RYCE_THEME_STATE="$RUN/state"
export RYCE_AGENTD_DIR="$RUN/agentd"
export PATH="$RUN/bin:\$PATH"
cd "\$HOME/peonza-dots" || exit 1
exec kitty "\$@"
EOF
  chmod +x "$RUN/bin/peonza-term"

  RYCE_HITO_ANY_HOST=1 "${NESTED[@]}" qs >/dev/null
  "${NESTED[@]}" wall
  # Play: the stream URLs Aria builds (it reads the song id from them, and the bar tells
  # Aria by /rest/stream), titled as Aria titles them.
  python3 - "$RUN/aria/ryce-aria-queue.json" "$port" <<'EOF' | socat - "UNIX-CONNECT:$RUN/aria/ryce-aria.sock" >/dev/null
import json, sys
for sid, s in json.load(open(sys.argv[1], encoding="utf-8")).items():
    print(json.dumps({"command": {"name": "loadfile", "flags": "append-play",
        "url": f"http://127.0.0.1:{sys.argv[2]}/rest/stream.view?u=demo&id={sid}",
        "options": {"force-media-title": f"{s['artist']} — {s['title']}"}}}))
EOF
  mpv_cmd '{"command":["set_property","pause",false]}'
  trap - EXIT
  echo "showcase up: theme $theme, demo server :$port, stage $WAYLAND_DISPLAY"
}

cmd=${1:-}; shift || true
case $cmd in
  up) up "$@" ;;
  down) down ;;
  theme) "${NESTED[@]}" theme "${1:?theme NAME}" ;;
  ipc) [ -f "$RUN/qs.pid" ] || die "no stage shell running"; qs ipc --pid "$(cat "$RUN/qs.pid")" call "$@" ;;
  term)
    stage_env
    ws=${1:?term WS [CMD...]}; shift
    case "$ws $*" in *[\"\\]*) die "term: no quotes or backslashes in the command" ;; esac
    hyprctl dispatch "hl.dsp.exec_cmd(\"$RUN/bin/peonza-term $*\", { workspace = \"$ws silent\" })" >/dev/null ;;
  run) stage_env; "$@" ;;
  shot) "${NESTED[@]}" shot "${1:?shot OUT.png}" ;;
  record)
    stage_env
    out=${1:?record OUT.mp4 [wf-recorder args]}; shift
    [ ! -f "$RUN/record.pid" ] || die "already recording (stop-record)"
    [ -x "$RECORDER" ] || RECORDER=$(command -v wf-recorder) || die "no wf-recorder: bash tools/showcase/build-recorder.sh"
    [ -f "$KEEP/fps" ] || fps > "$KEEP/fps"
    set_fps 60
    # -D: every frame, not only damaged ones, so the file is a constant 60 fps.
    nohup "$RECORDER" -y -D -r 60 -c libx264 -p preset=veryfast -p crf=18 -x yuv420p "$@" -f "$out" \
      > "$RUN/record.log" 2>&1 &
    echo $! > "$RUN/record.pid"
    sleep 0.5
    kill -0 "$(cat "$RUN/record.pid")" 2>/dev/null || { stop_record; die "wf-recorder failed: $RUN/record.log"; } ;;
  stop-record) stop_record ;;
  *) sed -n '4,14s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; exit 2 ;;
esac
