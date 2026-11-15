#!/usr/bin/env bash
# Give Feishin the rice's look (seed.js says which keys and how): the «Ryce» theme, the
# analyser ringing the full-screen player's cover, and on a fresh profile Spanish and
# the native frame. Merges into existing settings without touching server, login, queue
# or any other choice; backs the profile's localStorage up first, then reads the result
# back from disk in a second process; idempotent. Needs the graphical session (a hidden
# Electron window) and Feishin closed (seed.js checks).
#
#   bash apps/feishin/seed.sh [--dry-run]    --dry-run lists the keys it would change
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
case ${1:-} in
  ''|--dry-run) ;;
  *) echo "uso: seed.sh [--dry-run]" >&2; exit 2 ;;
esac
command -v feishin >/dev/null || { echo "seed.sh: Feishin no está instalado (sudo pacman -S feishin)" >&2; exit 1; }
# The Electron Feishin itself runs on (the package's launcher names it), so the profile
# format is the one Feishin reads.
launcher=$(command -v feishin)
# `|| true`: a launcher that names neither must reach the friendly check below, not
# end the script silently under pipefail.
electron=$(grep -o 'electron[0-9]*' "$launcher" | head -n 1 || true)
asar=$(grep -o '/[^ "]*app\.asar' "$launcher" | head -n 1 || true)
command -v "$electron" >/dev/null || { echo "seed.sh: falta ${electron:-electron}, del que depende Feishin" >&2; exit 1; }
if [ "${1:-}" = --dry-run ]; then
  exec "$electron" "$here/seed.js" ${asar:+"$asar"} --dry-run
fi
"$electron" "$here/seed.js" ${asar:+"$asar"}
# Electron flushes localStorage without saying when it reached the disk: a fresh process
# reads the profile back and must find nothing left to change.
if ! "$electron" "$here/seed.js" ${asar:+"$asar"} --check; then
  echo "seed.sh: los ajustes no quedaron guardados en el perfil de Feishin; la copia previa está en ~/.config/feishin/Local Storage/leveldb.ryce-*" >&2
  exit 1
fi
echo "feishin seed: comprobado en disco"
