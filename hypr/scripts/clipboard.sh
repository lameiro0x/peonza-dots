#!/usr/bin/env bash
# Clipboard history picker (SUPER+c): pick an entry from cliphist in rofi and
# put it back on the clipboard. Cancelling leaves the clipboard untouched.
# The history is recorded by systemd/user/cliphist.service on tmpfs
# ($XDG_RUNTIME_DIR/cliphist.db, gone at logout); read the same database.
set -euo pipefail

db="${XDG_RUNTIME_DIR:?XDG_RUNTIME_DIR is not set}/cliphist.db"

for bin in cliphist rofi wl-copy; do
    command -v "$bin" >/dev/null || { echo "${0##*/}: $bin is not installed" >&2; exit 1; }
done

# rofi exits non-zero on Escape; an empty pick must not reach wl-copy, which
# would replace the clipboard with nothing.
pick=$(cliphist -db-path "$db" list | rofi -dmenu -p clip -display-columns 2 -theme ~/.config/rofi/style.rasi) || exit 0
[ -n "$pick" ] || exit 0
printf '%s\n' "$pick" | cliphist -db-path "$db" decode | wl-copy
