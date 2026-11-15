#!/usr/bin/env python3
"""Point VS Code at a Ryce colour theme by editing one value in settings.json.

settings.json is JSONC (comments, trailing commas), so it is never parsed and
re-serialised: that would drop the user's comments. A small tokenizer finds the
top-level "workbench.colorTheme" member outside strings and comments and replaces
only its value; when the key is missing it is added before the closing brace.
VS Code watches the file and applies the theme live.

    python3 theme/vscode/settings_edit.py "Ryce Ola" [settings.json]

bin/ryce-theme imports write_color_theme(); the name is build.label(theme).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

KEY = "workbench.colorTheme"
DEFAULT = Path.home() / ".config" / "Code" / "User" / "settings.json"
TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<str>"(?:[^"\\\n]|\\.)*")
  | (?P<punct>[{}\[\]:,])
  | (?P<lit>[^\s{}\[\]:,"/]+)
""", re.S | re.X)


class SettingsError(ValueError):
    pass


def _tokens(text: str) -> list[tuple[str, int, int]]:
    """Significant tokens (kind, start, end); whitespace and comments dropped."""
    out, pos = [], 0
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m:
            line = text.count("\n", 0, pos) + 1
            raise SettingsError(f"settings.json line {line}: cannot read {text[pos:pos + 20]!r} "
                                "(unterminated string or comment?); fix it in VS Code first")
        if m.lastgroup not in ("ws", "comment"):
            out.append((m.lastgroup, m.start(), m.end()))
        pos = m.end()
    return out


def set_color_theme(text: str, name: str) -> str:
    """`text` with the top-level "workbench.colorTheme" set to `name`, nothing else touched."""
    value = json.dumps(name, ensure_ascii=False)
    toks = _tokens(text)
    if not toks:
        return "{\n    " + f'"{KEY}": {value}' + "\n}\n"
    if text[toks[0][1]] != "{":
        raise SettingsError("settings.json: the top level is not an object")
    depth, spans, close, indent = 0, [], None, None
    for i, (kind, a, b) in enumerate(toks):
        ch = text[a]
        if kind == "punct" and ch in "{[":
            depth += 1
        elif kind == "punct" and ch in "}]":
            depth -= 1
            if depth == 0:
                close = i
                break
        elif kind == "str" and depth == 1 and text[toks[i - 1][1]] in "{,":
            if indent is None:
                indent = text[text.rfind("\n", 0, a) + 1:a]
            if json.loads(text[a:b]) == KEY and i + 2 < len(toks) and text[toks[i + 1][1]] == ":":
                spans.append(toks[i + 2])
    if close is None:
        raise SettingsError("settings.json: the top-level object is never closed")
    for kind, a, b in reversed(spans):           # VS Code reads the last one; set them all
        if kind not in ("str", "lit"):
            raise SettingsError(f'settings.json: "{KEY}" holds an object or a list, not a name')
        text = text[:a] + value + text[b:]
    if spans:
        return text
    _, last_a, last_b = toks[close - 1]
    brace = toks[close][1]
    member = f'"{KEY}": {value}'
    comma = "" if text[last_a] in "{," else ","
    line_start = text.rfind("\n", 0, brace) + 1
    if text[line_start:brace].strip() == "" and line_start > last_b:
        pad = indent if indent and not indent.strip() else "    "
        text = text[:line_start] + f"{pad}{member}\n" + text[line_start:]
    else:
        text = text[:brace] + f" {member} " + text[brace:]
    return text[:last_b] + comma + text[last_b:]


def write_color_theme(path: Path, name: str) -> bool:
    """Set the theme in the file at `path` atomically; False when it already was."""
    real = Path(os.path.realpath(path))             # a linked settings.json stays a link
    try:
        text = real.read_text(encoding="utf-8")
        mode = real.stat().st_mode & 0o7777
    except FileNotFoundError:
        text, mode = "", 0o644
    new = set_color_theme(text, name)
    if new == text:
        return False
    real.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".settings.", suffix=".json", dir=real.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, real)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return True


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2):
        print("usage: settings_edit.py NAME [settings.json]", file=sys.stderr)
        return 2
    path = Path(argv[1]) if len(argv) == 2 else DEFAULT
    try:
        write_color_theme(path, argv[0])
    except SettingsError as e:
        print(f"settings_edit: {path}: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"settings_edit: {e.filename}: {e.strerror}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
