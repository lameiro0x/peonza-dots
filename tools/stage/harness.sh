#!/bin/sh
# Build (idempotently) a rootless prefix of OFFICIAL Arch packages on a Linux box
# that is NOT the target PC (today: the user's Arch laptop, `ssh arch`), so that
# we can check this repo against the exact versions the new PC will install:
#
#   Hyprland 0.57.1 `--verify-config`        (config gate; Lua only since 0.57)
#   sway (headless, pixman) + Waybar 0.16    (visual stage, invisible)
#   Quickshell 0.3.2 + Qt 6.12               (widgets on the same stage)
#
# Nothing is installed system-wide and nothing appears on the laptop's screen:
# everything lives in ~/.cache/ryce-verify and runs in its own XDG_RUNTIME_DIR.
# Headless *Hyprland* does not work this way (needs a seat for DRM, and nested
# in a headless wlroots it dies with "no allocator available") — measured
# 2026-11-09 — so runtime IPC checks of Hyprland happen on the real PC.
set -eu
D="${RYCE_VERIFY:-$HOME/.cache/ryce-verify}"
M="${RYCE_MIRROR:-https://geo.mirror.pkgbuild.com}"
mkdir -p "$D/pkgs" "$D/root"
exec 8>"$D/.harness.lock"
flock -w 600 8 || { echo "harness busy" >&2; exit 3; }
cd "$D/pkgs"

PKGS="hyprland hyprutils aquamarine hyprgraphics hyprwire hyprlang hyprcursor hyprland-guiutils hyprtoolkit lua
sway wlroots0.20 libliftoff swaybg waybar
hyprlock hypridle sdbus-cpp
python-gobject gobject-introspection-runtime python-cairo
quickshell qt6-base qt6-declarative qt6-wayland qt6-svg qt6-shadertools cpptrace libdwarf"

for repo in extra core; do
  [ -s "index-$repo.html" ] && [ -z "$(find "index-$repo.html" -mmin +720 2>/dev/null)" ] || \
    curl -fsSL --max-time 60 "$M/$repo/os/x86_64/" -o "index-$repo.html"
done

for p in $PKGS; do
  f=""
  for repo in extra core; do
    f=$(grep -oE "href=\"$p-[0-9][^\"]*-x86_64\.pkg\.tar\.zst\"" "index-$repo.html" \
        | sed 's/href="//;s/"$//' | sort -V | tail -1)
    [ -n "$f" ] && break
  done
  [ -n "$f" ] || { echo "MISSING $p" >&2; continue; }
  # A colon in the file name (epoch) makes tar think it is a remote host.
  local_name=$(printf %s "$f" | sed 's/%3A/-/; s/:/-/')
  if [ ! -f "$local_name" ]; then
    curl -fsSL --max-time 300 "$M/$repo/os/x86_64/$f" -o "$local_name.part" && mv "$local_name.part" "$local_name"
    tar --zstd -xf "$local_name" -C "$D/root" \
      --exclude=.PKGINFO --exclude=.BUILDINFO --exclude=.MTREE --exclude=.INSTALL
    echo "extracted $local_name"
  fi
done

export LD_LIBRARY_PATH="$D/root/usr/lib"
for b in Hyprland sway waybar quickshell hyprlock; do
  if ldd "$D/root/usr/bin/$b" | grep -q 'not found'; then
    echo "LIBS MISSING for $b:" >&2; ldd "$D/root/usr/bin/$b" | grep 'not found' >&2; exit 1
  fi
done
"$D/root/usr/bin/Hyprland" --version | head -1
"$D/root/usr/bin/waybar" --version
"$D/root/usr/bin/quickshell" --version
echo "harness: ok ($D)"
