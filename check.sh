#!/usr/bin/env bash
# The per-loop check suite (python3 + bash; the build-time generators also need
# python-numpy, python-pillow, python-fonttools, potrace and rsvg-convert).
# Live checks on the real session (verify-config, stage screenshots): tools/stage/nested.sh.
#   bash check.sh          run everything, exit 1 if any step fails
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 2
fail=0
step() {
  local name="$1"; shift
  printf '\n== %s\n' "$name"
  if "$@"; then echo "-- ok: $name"; else echo "-- FAIL: $name"; fail=1; fi
}
skip_unless() { [ -e "$1" ] || { printf '\n== %s\n-- SKIP (missing %s)\n' "$2" "$1"; return 1; }; }

step "theme contracts, palettes and theme files" python3 tools/tokens.py --check
step "repo lint (signal budget, Lua dispatch, secrets)" python3 tools/lint.py
step "roster sample matches contract" python3 contracts/check_roster.py contracts/roster.sample.json

if skip_unless agentd/tests "agentd"; then
  step "agentd unit tests" env PYTHONPATH=agentd python3 -m unittest discover -s agentd/tests
  step "agentd golden roster matches contract" python3 contracts/check_roster.py agentd/tests/golden/roster.json
fi
if skip_unless keys/gen.py "keys"; then
  step "binds.lua generated from keymap.tsv" python3 keys/gen.py --check
  step "keys tests (parity with dotsArch)" python3 -m unittest discover -s keys
  step "cheat sheet generated from keymap" python3 tools/atajos.py --check
  step "cheat sheet tests" python3 -m unittest discover -s tools -p 'test_atajos.py'
  step "chromium tests" python3 -m unittest discover -s tools -p 'test_chromium_*.py'
fi
if skip_unless hypr/tests "hypr"; then step "hypr tests" python3 -m unittest discover -s hypr/tests; fi
if skip_unless theme/render.py "theme"; then
  step "app themes rendered for every theme" python3 theme/render.py --check
  if skip_unless theme/wallpaper/scenes.py "wallpapers"; then
    step "wallpapers generated" python3 theme/wallpaper/scenes.py --check
  fi
  if skip_unless theme/wallpaper/ink.py "peonza ink wallpaper"; then
    step "peonza ink wallpaper (Tinta alternate)" python3 theme/wallpaper/ink.py --check
  fi
  if skip_unless theme/wallpaper/paper.py "papel covers"; then
    step "Papel's Tractatus covers" python3 theme/wallpaper/paper.py --check
  fi
  if skip_unless theme/wallpaper/dots.py "dot plates"; then
    step "Grafito dot plates" python3 theme/wallpaper/dots.py --check
    step "Chromium new tab pictures" python3 theme/wallpaper/newtab.py --check
  fi
  if skip_unless theme/boot/grub.py "GRUB art"; then
    step "GRUB menu art" python3 theme/boot/grub.py --check
  fi
  if skip_unless theme/boot/greeter.py "login art"; then
    step "login page art" python3 theme/boot/greeter.py --check
  fi
  if skip_unless theme/peonza/glyph.py "peonza glyph"; then
    step "peonza glyph font" python3 theme/peonza/glyph.py --check
  fi
  for gen in theme/peonza/gen.py theme/peonza/gen.mjs; do
    [ -e "$gen" ] || continue
    if skip_unless "$HOME/Repos/logo-peonza/src/pose.mjs" "peonza sprites (brand repo)"; then
      case $gen in *.py) step "peonza sprites" python3 "$gen" --check ;; *) step "peonza sprites" node "$gen" --check ;; esac
    fi
  done
  if skip_unless theme/fetch/fetch.py "fetch peonza"; then
    if skip_unless "$HOME/Repos/logo-peonza/src/pose.mjs" "fetch peonza (brand repo)"; then
      step "fetch peonza (fastfetch/dripfetch)" python3 theme/fetch/fetch.py --check
    fi
    step "fetch tests" python3 -m unittest discover -s theme/fetch
  fi
  if skip_unless theme/greet/greet.py "terminal greeting"; then
    if skip_unless "$HOME/Repos/logo-peonza/src/pose.mjs" "terminal greeting (brand repo)"; then
      step "terminal greeting peonza" python3 theme/greet/greet.py --check
    fi
    step "terminal greeting tests" python3 -B -m unittest discover -s theme/greet
  fi
  if skip_unless theme/cursor/build.py "cursor"; then
    step "peonza cursor theme (XCursor + hyprcursor)" python3 theme/cursor/build.py --check
    step "cursor tests" python3 -m unittest discover -s theme/cursor/tests
  fi
  if skip_unless theme/vscode/build.py "vscode"; then step "VS Code themes (vsix)" python3 theme/vscode/build.py --check; fi
  if skip_unless theme/icons.py "icons"; then
    icons_tmp=$(mktemp -d)
    step "folder icons per theme" python3 theme/icons.py --check --dest "$icons_tmp"
    rm -rf "$icons_tmp"
  fi
  step "theme tests" python3 -m unittest discover -s theme/tests
fi
if [ -e bin/ryce-theme ]; then step "ryce-theme compiles" python3 -m py_compile bin/ryce-theme; fi
if [ -e bin/ryce-chromium-theme ]; then step "ryce-chromium-theme compiles" python3 -m py_compile bin/ryce-chromium-theme; fi
if [ -d apps/zotero/tests ]; then step "zotero setup tests" python3 -B -m unittest discover -s apps/zotero/tests; fi
if skip_unless waybar/tests "waybar"; then step "waybar tests" python3 -m unittest discover -s waybar/tests; fi
if skip_unless systemd/tests "systemd"; then step "systemd unit tests" python3 -m unittest discover -s systemd/tests; fi
if skip_unless quickshell/tests/qmlcheck.py "quickshell"; then
  step "qml structural check" python3 quickshell/tests/qmlcheck.py quickshell/ryce contracts/roster.v1.schema.json
  step "qml structural check (login page)" python3 quickshell/tests/qmlcheck.py quickshell/greeter contracts/roster.v1.schema.json
  step "qmlcheck tests" python3 -m unittest discover -s quickshell/tests
fi
if skip_unless install/tests "install"; then
  step "install tests" python3 -m unittest discover -s install/tests
  shopt -s nullglob
  sh_files=(install/*.sh hypr/scripts/*.sh tools/stage/*.sh tools/*.sh check-arch.sh)
  # bin/ mixes shell and Python (ryce-theme): only shell scripts go to bash -n/shellcheck.
  for f in bin/*; do head -n1 "$f" | grep -qE '^#!.*(ba)?sh' && sh_files+=("$f"); done
  step "bash -n" bash -c 'for f in "$@"; do bash -n "$f" || exit 1; done' _ "${sh_files[@]}"
  if command -v shellcheck >/dev/null; then step "shellcheck" shellcheck -S warning -x "${sh_files[@]}"; fi
  tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
  mkdir -p "$tmp/home"
  step "deploy dry-run" bash install/deploy.sh --dry-run --home "$tmp/home"
fi

echo
if [ "$fail" = 0 ]; then echo "check.sh: ALL GREEN"; else echo "check.sh: FAILURES"; fi
exit "$fail"
