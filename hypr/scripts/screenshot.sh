#!/usr/bin/env bash
# Screenshots (grim + slurp), bound in keys/keymap.tsv:
#   screenshot.sh full        whole screen to a file                  Print
#   screenshot.sh area        selected area to a file                 SHIFT+Print
#   screenshot.sh area-copy   selected area to a file + clipboard     CTRL+SHIFT+s
#   screenshot.sh edit        selected area into swappy to annotate   SUPER+SHIFT+s
# Files land in ~/Pictures/Screenshots. Cancelling a selection is not an error.
set -euo pipefail

mode=${1:-}
case "$mode" in
    full | area | area-copy | edit) ;;
    *) echo "usage: ${0##*/} full|area|area-copy|edit" >&2; exit 2 ;;
esac

for bin in grim slurp; do
    command -v "$bin" >/dev/null || { echo "${0##*/}: $bin is not installed" >&2; exit 1; }
done

if [ "$mode" != full ]; then
    # slurp exits non-zero when the selection is cancelled (Escape).
    region=$(slurp 2>/dev/null) || exit 0
fi

if [ "$mode" = edit ]; then
    command -v swappy >/dev/null || { echo "${0##*/}: swappy is not installed" >&2; exit 1; }
    # swappy saves into its own save_dir (default ~/Pictures) on demand.
    grim -g "$region" - | swappy -f -
    exit 0
fi

dir="$HOME/Pictures/Screenshots"
mkdir -p "$dir"
file="$dir/screenshot-$(date +%Y-%m-%d_%H-%M-%S).png"

if [ "$mode" = full ]; then
    grim "$file"
else
    grim -g "$region" "$file"
fi
if [ "$mode" = area-copy ]; then
    wl-copy --type image/png <"$file"
fi
