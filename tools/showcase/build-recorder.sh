#!/usr/bin/env bash
# Build wf-recorder 0.6.0 for tools/showcase/stage.sh record, without root: Arch's own recipe
# (its PKGBUILD's source and ffmpeg-9.patch, both checked by sha256) with meson and ninja
# from a throwaway venv, into ${XDG_CACHE_HOME:-~/.cache}/ryce-showcase/wf-recorder.
#
#   bash tools/showcase/build-recorder.sh       build (again) → …/wf-recorder/build/wf-recorder
#
# Why not the package: Arch's wf-recorder is not installed here and installing needs root;
# 0.6.0 as released does not compile against FFmpeg 9 (codec->pix_fmts is gone), which
# is what the patch fixes (built and run here 2026-11-15 against ffmpeg n9.0.2). Needs ffmpeg, wayland, wayland-protocols, libpulse, gcc, python.
set -euo pipefail

CACHE=${XDG_CACHE_HOME:-$HOME/.cache}/ryce-showcase/wf-recorder
SRC_URL=https://github.com/ammen99/wf-recorder/archive/v0.6.0.tar.gz
SRC_SHA=52d2c952506d63708f9a8f1aacd4d6ca176287caf3507c8ff2882fa0390cb391
PATCH_URL=https://gitlab.archlinux.org/archlinux/packaging/packages/wf-recorder/-/raw/main/ffmpeg-9.patch
PATCH_SHA=d151f6163ee2839df0edf5bcafd82f41b88832cae66ddb6673ce54d7b8f680c6
die() { printf 'build-recorder.sh: %s\n' "$*" >&2; exit 1; }

for c in curl sha256sum tar patch python3 cc pkg-config; do
  command -v "$c" >/dev/null || die "falta $c"
done
for p in libavcodec libavformat libavfilter libavdevice libswresample wayland-client wayland-protocols libpulse-simple; do
  pkg-config --exists "$p" || die "falta $p (pkg-config): instala ffmpeg, wayland-protocols y libpulse"
done

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fetch() {  # URL SHA256 OUT
  curl -fsSL --max-time 120 -o "$3" "$1" || die "no pude descargar $1"
  printf '%s  %s\n' "$2" "$3" | sha256sum -c --quiet - || die "$1 no es el fichero esperado (sha256)"
}
fetch "$SRC_URL" "$SRC_SHA" "$tmp/src.tar.gz"
fetch "$PATCH_URL" "$PATCH_SHA" "$tmp/ffmpeg-9.patch"

rm -rf "$CACHE"
mkdir -p "$CACHE/src"
tar -xzf "$tmp/src.tar.gz" -C "$CACHE/src" --strip-components=1
patch -d "$CACHE/src" -p1 --quiet < "$tmp/ffmpeg-9.patch"
python3 -m venv "$CACHE/venv"
"$CACHE/venv/bin/pip" install --quiet --disable-pip-version-check meson ninja
PATH=$CACHE/venv/bin:$PATH meson setup "$CACHE/build" "$CACHE/src" -Dpulse=enabled --buildtype=release >/dev/null
PATH=$CACHE/venv/bin:$PATH ninja -C "$CACHE/build" >/dev/null
"$CACHE/build/wf-recorder" --version
echo "$CACHE/build/wf-recorder"
