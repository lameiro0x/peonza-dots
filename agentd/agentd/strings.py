"""Text shaping shared by the parsers and the renderer.

Budgets are in terminal cells, not code points: a CJK character is two cells,
a combining mark none, so a Chinese repo name cannot overflow its slot.
"""

from __future__ import annotations

import unicodedata

# Cc control, Cf format, Cs surrogate, Zl/Zp separators. Deliberately NOT Co:
# Nerd Font icons live in the private use area, and dropping that category
# silently erases every glyph in the bar.
_DROP = {"Cc", "Cf", "Cs", "Zl", "Zp"}
_EDGE = " ._-/,;:·—"


def printable(s: str) -> str:
    """One line of printable text: controls become spaces, runs collapse."""
    return " ".join("".join(" " if unicodedata.category(c) in _DROP else c for c in s).split())


def pango(s: str) -> str:
    """Printable and safe inside Pango markup (Waybar text and tooltips)."""
    s = "".join(c for c in s if c == "\n" or unicodedata.category(c) not in _DROP)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def isolate(s: str) -> str:
    """FSI … PDI: a right-to-left label stays inside its own box instead of
    reordering the numeral and icon around it. Apply after pango(), which
    drops format characters."""
    return f"⁨{s}⁩"


def _cells(c: str) -> int:
    if unicodedata.combining(c):
        return 0
    return 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1


def width(s: str) -> int:
    return sum(_cells(c) for c in s)


def _head(s: str, n: int) -> str:
    """The longest prefix of s that fits in n cells."""
    used = 0
    for i, c in enumerate(s):
        used += _cells(c)
        if used > n:
            return s[:i]
    return s


def _tail(s: str, n: int) -> str:
    return _head(s[::-1], n)[::-1]


def clip(s: str, n: int) -> str:
    """Prose clip: keep the head, cut at a word when one is near, end in '…'."""
    s = s.strip()
    if width(s) <= n:
        return s
    cut = _head(s, n - 1)
    if s[len(cut)] != " ":              # the cut lands mid-word: back up to a space
        space = cut.rfind(" ")
        if space > 0 and width(cut[:space]) >= (n - 1) // 2:
            cut = cut[:space]
    return cut.rstrip(_EDGE) + "…"


def clip_middle(s: str, n: int) -> str:
    """Name clip: keep both ends.

    Repo names share prefixes (`peonza`, `peonza-dots`,
    `peonza.github.io`), so cutting the tail throws away the only part that
    tells them apart. Separators next to the cut go too: `github.…` reads as a
    typo, not as a truncation.
    """
    s = s.strip()
    if width(s) <= n:
        return s
    head = (n - 1) // 2 + (n - 1) % 2
    return _head(s, head).rstrip(_EDGE) + "…" + _tail(s, (n - 1) - head).lstrip(_EDGE)
