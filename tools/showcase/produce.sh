#!/usr/bin/env bash
# The README's media from a clean stage: bring the showcase up in Tinta, shoot every scene
# (tools/showcase/scenes/record.sh), take the stage down again, also when a scene fails,
# then cut and draw (tools/showcase/post/*.py).
#
#   bash tools/showcase/produce.sh [OUT]        everything (OUT defaults to out/showcase)
#   bash tools/showcase/produce.sh post [OUT]   only the post-production, from OUT/raw
#
# OUT/raw keeps the raw clips and shots, OUT/media gets the README's files: demo.mp4,
# hero.webp + hero.jpg, theme-<t>.jpg, desk-<t>.jpg, the close-ups, bars.png,
# greeter.webp, boot.webp, newtab.jpg, despiece.png, social.png and contact.jpg (every
# still, for review). Shooting needs the real Hyprland session, outside Claude Code's
# sandbox; post needs ffmpeg (libx264, libwebp) and Pillow.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
HERE=$ROOT/tools/showcase
die() { printf 'produce.sh: %s\n' "$*" >&2; exit 1; }

post() {
  local out=$1 c
  for c in ffmpeg fc-match python3; do command -v "$c" >/dev/null || die "falta $c"; done
  python3 -c 'import PIL' 2>/dev/null || die "falta Pillow (python-pillow)"
  [ -d "$out/raw" ] || die "no raw material in $out/raw (bash $0 $out)"
  mkdir -p "$out/media"
  python3 -I "$HERE/post/stills.py" "$out/raw" "$out/media"
  python3 -I "$HERE/post/despiece.py" "$out/raw" "$out/media"
  python3 -I "$HERE/post/video.py" "$out/raw" "$out/media"
  python3 -I "$HERE/post/stills.py" contact "$out/media"
  ls -l "$out/media"
}

shoot() {
  local out=$1
  mkdir -p "$out/raw"
  bash "$HERE/stage.sh" up tinta
  trap 'bash "$HERE/stage.sh" down' EXIT
  sleep 3                       # the shell's first data (Hito, Aria, the roster) lands
  bash "$HERE/scenes/record.sh" "$out/raw"
  trap - EXIT
  bash "$HERE/stage.sh" down
}

if [ "${1:-}" = post ]; then
  post "${2:-$ROOT/out/showcase}"
else
  out=${1:-$ROOT/out/showcase}
  shoot "$out"
  post "$out"
fi
