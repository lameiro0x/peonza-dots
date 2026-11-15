#!/usr/bin/env bash
# The raw material of the README's media, shot on a running showcase stage
# (tools/showcase/stage.sh up tinta): the video's beats as separate 60 fps clips, the
# hero's theme cycle, the greeter, the close-ups and every theme's stills.
#
#   bash tools/showcase/scenes/record.sh RAW_DIR [video|hero|parts|stills|greeter]...
#
# With no part named it shoots them all, in that order. Everything goes through stage.sh,
# keys included: the picker gets real arrow and Return presses (Hyprland's send_shortcut
# into the stage), so the theme switches are the picker's own. Terminals carry a kitty
# class per scene, so a scene closes only its own. Must run outside Claude Code's sandbox.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)
S=(bash "$ROOT/tools/showcase/stage.sh")
RAW=${1:?usage: record.sh RAW_DIR [video|hero|parts|stills|greeter]...}; shift
STAGE=${XDG_RUNTIME_DIR:?}/ryce-stage-showcase
STATE=$STAGE/state
# The picker's card order (SelectorWindow.qml), for the arrow presses.
ORDER=(origen grafito ola tinta papel)
mkdir -p "$RAW"

say() { printf '· %s\n' "$*" >&2; }
key() { "${S[@]}" run hyprctl dispatch "hl.dsp.send_shortcut({ mods = \"\", key = \"$1\" })" >/dev/null; }
ws() { "${S[@]}" run hyprctl dispatch "hl.dsp.focus({ workspace = $1 })" >/dev/null; }
left() { "${S[@]}" run hyprctl dispatch 'hl.dsp.focus({ direction = "left" })' >/dev/null; sleep 0.3; }
ipc() { "${S[@]}" ipc "$@" >/dev/null; }
term() { "${S[@]}" term "$@"; }
shot() { "${S[@]}" shot "$RAW/$1.png" >/dev/null; }
rec() { "${S[@]}" record "$RAW/$1.mp4"; sleep 0.4; }
stop() { sleep 0.3; "${S[@]}" stop-record; }
current() { readlink "$STATE/current"; }
# Kitties of one scene: their class is in their command line (peonza-term passes it on).
close_class() { pkill -f -- "kitty --class $1" 2>/dev/null || true; sleep 0.6; }
volume() { pactl set-sink-volume ryce-showcase "$1"; }
idx() { local i; for i in "${!ORDER[@]}"; do [ "${ORDER[$i]}" != "$1" ] || echo "$i"; done; }

# pick THEME: open the picker, walk to THEME with the arrows, apply it, let it land.
pick() {
  local from to n k
  from=$(idx "$(current)"); to=$(idx "$1")
  ipc selector open; sleep 0.7
  if [ "$to" -gt "$from" ]; then k=Right; n=$((to - from)); else k=Left; n=$((from - to)); fi
  for _ in $(seq 1 "$n"); do key "$k"; sleep 0.3; done
  sleep 0.35; key Return
  sleep 2.2
  overrides
}

# The stage's compositor settings for the camera. A theme switch reloads the config and
# drops them, so they go back after every switch. invisible alone still lets a resize
# shape show on a split: the pointer also leaves for the far corner. force_split 2: a new
# window always goes right of or below the focused one, so every take tiles the same way.
overrides() {
  "${S[@]}" run hyprctl eval 'hl.config({ cursor = { invisible = true }, dwindle = { force_split = 2 } })' >/dev/null
  "${S[@]}" run hyprctl dispatch 'hl.dsp.cursor.move({ x = 1919, y = 1079 })' >/dev/null
}

# What the stage leaves to its user, set before any frame: the camera's settings,
# fastfetch's title reads peonza@dots instead of the owner's login and host (a fastfetch first on the
# terminals' PATH that rewrites the theme's title format), and nvim does not wrap.
prepare() {
  [ -d "$STAGE/bin" ] || { echo "record.sh: no showcase stage (stage.sh up tinta)" >&2; exit 1; }
  overrides
  cat > "$STAGE/bin/fastfetch" <<EOF
#!/usr/bin/env bash
# The showcase's fastfetch (tools/showcase/scenes/record.sh): an invented login and host.
args=(); prev=
for a in "\$@"; do
  if [ "\$prev" = --config ]; then
    sed 's/{user-name}/peonza/g; s/{host-name}/dots/g' "\$a" > "$STAGE/fetch.jsonc"; a=$STAGE/fetch.jsonc
  fi
  args+=("\$a"); prev=\$a
done
exec $(command -v fastfetch) "\${args[@]}"
EOF
  # A fetch that prints once the tiling has settled (a resize afterwards cuts the card),
  # without the greeter above it.
  printf '#!/bin/sh\nsleep 1.6\nryce_greet=off exec fish -C fastfetch\n' > "$STAGE/bin/fetch-later"
  chmod +x "$STAGE/bin/fastfetch" "$STAGE/bin/fetch-later"
  # nvim in the stills: no wrapping, and code (greet.py's first functions) at the top.
  printf 'set nowrap\ncall cursor(106, 1)\nnormal! zt\n' > "$STAGE/still.vim"
}

# The bar names a workspace after its session only while the workspace holds a window:
# one quiet terminal each on the demo roster's workspaces (1, 2, 4), kept open while the
# hero and the stills are shot.
sessions() { for w in 1 2 4; do term "$w" --class sess; done; sleep 1.5; }

# Straight to THEME without the picker (stills): wait until everything has repainted.
theme() { [ "$(current)" = "$1" ] || { "${S[@]}" theme "$1" >/dev/null; sleep 3; overrides; }; }

video() {
  close_class vid
  theme tinta
  ws 6; ipc sidebar close; sleep 1
  # Terminals that the beats walk through: ws 1 the greeter, a fetch and cava; ws 2 btop.
  say "a · bare desk"
  rec a-desk; sleep 6; stop

  say "b · terminals"
  term 2 --class vid btop
  rec b-terms
  ws 1; sleep 0.8
  # The greeter on the left, the fetch full height on the right, cava under the greeter.
  term 1 --class vid; sleep 2.2
  term 1 --class vid fetch-later; sleep 2.9
  left
  term 1 --class vid cava; sleep 2.6
  ws 2; sleep 2.6
  ws 1; sleep 0.8
  stop

  say "c · audio"
  rec c-audio
  ipc sidebar open; sleep 3.4
  volume 48%; sleep 0.5; volume 56%; sleep 0.5; volume 72%; sleep 1.2
  ipc sidebar close; sleep 0.9
  ipc aria open; sleep 2.8
  ipc aria next; sleep 3.0
  ipc aria close; sleep 0.8
  volume 64%
  stop

  say "d · themes through the picker"
  rec d-themes
  # Over the terminals (they recolour live), then on the bare desk where the whole
  # picture's transition shows, then back over the terminals.
  sleep 0.6
  pick origen; ws 6; sleep 0.6
  pick ola; ws 6
  pick grafito; ws 1; sleep 0.6
  pick papel; ws 1
  pick tinta; ws 1
  sleep 0.6
  stop

  say "e · cheat sheet and workspaces"
  rec e-keys
  ipc keys open; sleep 3.4
  ipc keys close; sleep 0.9
  for w in 2 3 4 5 6; do ws "$w"; sleep 0.6; done
  stop

  say "f · bare desk"
  rec f-desk; sleep 5; stop
  close_class vid
}

# The hero: one framing (the bare desk, the sessions named in the bar), the five themes in
# turn and back to the first. It opens on Origen's colour; Tinta comes last, just before the
# README's drawing of it.
hero() {
  sessions
  theme origen; ws 6; sleep 1.5
  say "hero"
  rec hero
  sleep 2
  for t in ola grafito papel tinta origen; do "${S[@]}" theme "$t" >/dev/null; ws 6; overrides; sleep 2.3; done
  stop
  close_class sess
}

# The parts list's close-ups, in Tinta, on the bare desk.
parts() {
  theme tinta; ws 6; sleep 1
  ipc sidebar open; sleep 2.2; shot part-sidebar; ipc sidebar close; sleep 1
  ipc hito open; sleep 2.2; shot part-hito; ipc hito close; sleep 1
  ipc aria open; sleep 2.6; shot part-aria; ipc aria close; sleep 1
  ipc keys open; sleep 2.2; shot part-keys; ipc keys close; sleep 1
  ipc selector open; sleep 2.2; shot part-selector; ipc selector close; sleep 1
  # The despiece's base: the bare desk while the sessions' workspaces hold windows, so the
  # bar names them.
  for w in 1 2 4; do term "$w" --class part; done
  sleep 2.5; shot part-despiece
  close_class part
}

# Every theme twice, same framing: a working layout (ws 7) and the bare desk (ws 8).
# The terminals are opened anew per theme, so fastfetch prints in that theme's colours.
stills() {
  local t
  sessions
  for t in "${ORDER[@]}"; do
    say "stills · $t"
    theme "$t"
    close_class still
    # The fetch full height on the left; nvim over cava on the right.
    term 7 --class still fetch-later; sleep 1.8
    term 7 --class still nvim -S "$STAGE/still.vim" theme/greet/greet.py; sleep 1.8
    term 7 --class still cava; sleep 0.4
    ws 7; sleep 3.6
    shot "theme-$t"
    ws 8; sleep 1.8
    shot "desk-$t"
    # The volume OSD is a thin rule on the right edge: Papel's plain paper shows it best.
    if [ "$t" = papel ]; then volume 52%; sleep 0.45; shot part-osd; volume 64%; sleep 1.5; fi
  done
  close_class still
  close_class sess
  theme tinta
}

# The kitty greeter, alone on an empty workspace, in Origen (the colour peonza).
greeter() {
  theme origen; ws 9; sleep 1
  say greeter
  rec greeter
  term 9 --class greet; sleep 3.4
  stop
  close_class greet
  theme tinta
}

[ $# -gt 0 ] || set -- video hero parts stills greeter
prepare
for part in "$@"; do
  case $part in
    video|hero|parts|stills|greeter) "$part" ;;
    *) echo "record.sh: unknown part $part" >&2; exit 2 ;;
  esac
done
