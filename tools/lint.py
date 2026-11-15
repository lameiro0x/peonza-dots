#!/usr/bin/env python3
"""Repo-wide invariants that no single slice can see.

    python3 tools/lint.py        exit 1 on any violation, one line each

1. SIGNAL BUDGET. Each theme's `signal` (ember in Origen, red in Grafito, pale
   seal red in Ola, amber in Tinta) means exactly one thing: an AI session is waiting for you.
   Only the files in SIGNAL_ALLOW may reference it (by any theme's hex or by
   token name). Everything else — kitty, rofi, fastfetch, the wallpaper, the
   clock — stays in the theme's neutrals. A stray use dilutes the one meaning.
2. LUA-MODE DISPATCH. Hyprland >= 0.57 has no hyprlang: `hyprctl dispatch X`
   evaluates X as Lua. A bare dispatcher word (`hyprctl dispatch workspace 3`)
   silently does nothing — the trap the VM hit with Waybar clicks. Every
   dispatch must start with `hl.`.
3. NO hyprland.conf. 0.57 removed it; a stray one is dead config that someone
   will edit expecting a change.
4. NO SECRETS-SHAPED STRINGS in tracked text (tokens, keys) — the repo may be
   pushed.
5. QML DISPATCH. Quickshell's Hyprland.dispatch() sends its string raw, so on 0.57
   it must be Lua too: `Hyprland.dispatch("hl.dsp.focus({ workspace = 3 })")`.
6. NO `current/` IN QML (except the generated Palette.qml, which reloads it on
   IPC): images and files go through `Palette.themeDir`, the theme's own path, or
   Qt's image cache and file watches keep the previous theme.
"""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", "inspiracion", "__pycache__", ".claude", "out", ".cache", ".worktrees", "node_modules"}
TEXT_EXT = {".py", ".lua", ".qml", ".js", ".css", ".jsonc", ".json", ".conf", ".sh", ".toml",
            ".rasi", ".ini", ".tsv", ".service", ".target", ".fish", ".md", ".txt", ".kdl", ""}

# Who may speak the signal.
SIGNAL_ALLOW = [
    "contracts/*",                  # the source of the token
    "tools/*",                      # this file, the generator, the colour maths
    "themes/*/theme.json", "themes/*/hypr/palette.lua", "themes/*/waybar/palette.css",  # generated
    "quickshell/ryce/Palette.qml",  # generated
    "themes/*/hypr/hyprlock.conf", "theme/templates/hypr/hyprlock.conf",  # "N agentes te esperan"
    "theme/templates/@*/hypr/hyprlock.conf",                             # a theme's own lock layout
    "hypr/rules.lua",               # border_color of the tagged (waiting) window
    "waybar/style.css",             # fallback bar: .waiting ring and the agents counter
    "quickshell/ryce/agents/*",     # the waiting agent card
    "quickshell/ryce/bar/*",        # the waiting slot dot and the peonza's wobble
    "quickshell/ryce/desk/Hud.qml", # Tinta's HUD: «[ ATENCIÓN REQUERIDA ]» while an AI waits
    "theme/peonza/*",               # bakes the wobble sprite in the signal colour
    "agentd/*",                     # agentd/tests and render may name the state
    "*/tests/*", "*/test_*.py",     # tests assert the budget
    "docs/*", "GUIA.md", "README.md",
    "theme/render.py",              # the app-theme generator refuses it
]


def _signal_re() -> re.Pattern[str]:
    import json
    hexes = set()
    for f in (ROOT / "contracts" / "themes").glob("*.json"):
        c = json.loads(f.read_text(encoding="utf-8"))["colors"]
        hexes |= {c[k][1:] for k in ("signal", "signal_dim", "signal_on_pill")}
    names = (r"@signal\b|\bsignal_dim\b|\bsignal_on_pill\b|signalOnPill|signalDim|Palette\.signal"
             r"|\bP\.signal|P\.hex\.signal|colors\[\"signal|rgba\(\s*\"signal|\{\{\s*signal")
    return re.compile(r"(?i)(?<![0-9a-f])(" + "|".join(sorted(hexes)) + r")(?:[0-9a-f]{2})?(?![0-9a-f])|" + names)


SIGNAL_RE = _signal_re()

DISPATCH_RE = re.compile(r"hyprctl\s+(?:-[a-zA-Z]+\s+)*dispatch\s+(?!['\"]?hl\.)(\S+)")
DISPATCH_SKIP = ["docs/*", "GUIA.md", "README.md", "tools/lint.py"]

QML_DISPATCH_RE = re.compile(r"Hyprland\.dispatch\(\s*[\"'`](?!hl\.)")
QML_CURRENT_RE = re.compile(r"/current/")
QML_CURRENT_ALLOW = ["quickshell/ryce/Palette.qml"]

SECRET_RE = re.compile(
    r"(sk-ant-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


def tracked_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.suffix not in TEXT_EXT:
            continue
        if p.stat().st_size > 2_000_000:
            continue
        out.append(p)
    return out


def allowed(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


def main() -> int:
    errs: list[str] = []
    for p in tracked_files():
        rel = p.relative_to(ROOT).as_posix()
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if SIGNAL_RE.search(line) and not allowed(rel, SIGNAL_ALLOW):
                errs.append(f"{rel}:{n}: signal colour outside its allowlist: {line.strip()[:100]}")
            m = DISPATCH_RE.search(line)
            if m and not allowed(rel, DISPATCH_SKIP):
                errs.append(f"{rel}:{n}: Lua-mode Hyprland needs `hyprctl dispatch 'hl.…'`, got `{m.group(1)}`")
            if p.suffix == ".qml" and QML_DISPATCH_RE.search(line):
                errs.append(f"{rel}:{n}: Hyprland.dispatch() sends its text raw: it must be Lua (`hl.dsp.…`)")
            if p.suffix == ".qml" and QML_CURRENT_RE.search(line) and not allowed(rel, QML_CURRENT_ALLOW):
                errs.append(f"{rel}:{n}: no `current/` paths in QML; use Palette.themeDir")
            if SECRET_RE.search(line):
                errs.append(f"{rel}:{n}: secret-shaped string")
        if p.name == "hyprland.conf":
            errs.append(f"{rel}: hyprland.conf is dead since Hyprland 0.57 (Lua only)")
    for e in errs:
        print(e)
    if not errs:
        print("lint: ok")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
