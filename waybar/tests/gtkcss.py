"""Tiny readers for the bar's files, shared by the waybar tests (stdlib only).

Not a CSS engine: enough of GTK3's dialect to list rules, resolve palette colours
(`#hex`, `@name`, `alpha(c, a)`, `transparent`) and composite them for contrast.

style.css imports "palette.css", which on the machine is a link to the current
theme's generated file; here every theme's file is read from themes/<id>/.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

WAYBAR = Path(__file__).resolve().parent.parent
ROOT = WAYBAR.parent
CONSTANTS = json.loads((ROOT / "contracts" / "constants.json").read_text(encoding="utf-8"))
SAMPLES = ROOT / "contracts" / "waybar.sample"
THEMES = CONSTANTS["themes"]


def palette_css(theme: str) -> Path:
    return ROOT / "themes" / theme / "waybar" / "palette.css"


def strip_jsonc(text: str) -> str:
    """Drop // and /* */ comments outside strings (Waybar's dialect)."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\":
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            i = text.find("\n", i)
            if i < 0:
                break
            continue
        elif text.startswith("/*", i):
            i = text.index("*/", i) + 2
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def load_config() -> dict:
    return json.loads(strip_jsonc((WAYBAR / "config.jsonc").read_text(encoding="utf-8")))


def css_text(path: str | Path) -> str:
    """A sheet without its comments; a bare name is a file in waybar/."""
    return re.sub(r"/\*.*?\*/", "", (WAYBAR / path).read_text(encoding="utf-8"), flags=re.S)


def defines(text: str) -> dict[str, str]:
    return dict(re.findall(r"@define-color\s+([\w-]+)\s+([^;]+);", text))


def rules(text: str) -> list[tuple[str, dict[str, str]]]:
    """(selector, declarations) for every rule, @keyframes steps included as
    `@keyframes NAME STEP`. Statements (@import, @define-color) are skipped."""
    text = re.sub(r"@(import|define-color)[^;]*;", "", text)
    found: list[tuple[str, dict[str, str]]] = []
    for m in re.finditer(r"@keyframes\s+([\w-]+)\s*\{((?:[^{}]*\{[^}]*\})*)\s*\}", text):
        for step, body in re.findall(r"([^{}]+)\{([^}]*)\}", m.group(2)):
            found.append((f"@keyframes {m.group(1)} {step.strip()}", _decls(body)))
    text = re.sub(r"@keyframes\s+[\w-]+\s*\{(?:[^{}]*\{[^}]*\})*\s*\}", "", text)
    for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", text):
        found.append((" ".join(sel.split()), _decls(body)))
    return found


def _decls(body: str) -> dict[str, str]:
    out = {}
    for part in body.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = " ".join(v.split())
    return out


RGBA = tuple[float, float, float, float]


class Palette:
    def __init__(self, theme: str) -> None:
        self.theme = theme
        self.names = defines(css_text(palette_css(theme))) | defines(css_text("style.css"))

    def resolve(self, expr: str) -> RGBA:
        expr = expr.strip()
        if expr == "transparent":
            return (0.0, 0.0, 0.0, 0.0)
        if expr.startswith("#"):
            h = expr[1:]
            return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, 1.0)
        if expr.startswith("@"):
            return self.resolve(self.names[expr[1:]])
        m = re.fullmatch(r"alpha\((.+),\s*([\d.]+)\)", expr)
        if m:
            r, g, b, a = self.resolve(m.group(1))
            return (r, g, b, a * float(m.group(2)))
        raise ValueError(f"unsupported colour expression: {expr}")


def over(top: RGBA, bottom: RGBA) -> RGBA:
    """Source-over composite; `bottom` must be opaque."""
    a = top[3]
    return (top[0] * a + bottom[0] * (1 - a), top[1] * a + bottom[1] * (1 - a),
            top[2] * a + bottom[2] * (1 - a), 1.0)


def luminance(c: RGBA) -> float:
    def lin(v: float) -> float:
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def ratio(a: RGBA, b: RGBA) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def hexof(c: RGBA) -> str:
    return "#" + "".join(f"{round(v * 255):02x}" for v in c[:3])
