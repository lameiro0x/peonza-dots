#!/usr/bin/env python3
"""Generate the Spanish cheat sheets from keys/keymap.tsv.

    python3 tools/atajos.py           write docs/atajos.md and quickshell/ryce/keys/atajos.json
    python3 tools/atajos.py --check   exit 1 if either is stale

docs/atajos.md is the full guide; atajos.json feeds the SUPER+F1 overlay
(quickshell/ryce/keys/), grouped for a glance and with series such as
CTRL + 1..0 folded into one row.

The TSV is the single source of truth for keybindings (keys/gen.py turns it into
hypr/binds.lua). Generating the cheat sheet from the same file means the guide
can never describe a key that does not exist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "keys"))
import gen  # noqa: E402  (keys/gen.py: parse())

SRC = ROOT / "keys" / "keymap.tsv"
OUT = ROOT / "docs" / "atajos.md"
JSON_OUT = ROOT / "quickshell" / "ryce" / "keys" / "atajos.json"

MODS = {"CTRL": "Ctrl", "SHIFT": "Mayús", "SUPER": "Super", "ALT": "Alt"}
KEYS = {
    "Return": "Enter", "space": "Espacio", "Left": "←", "Right": "→", "Up": "↑", "Down": "↓",
    "apostrophe": "'", "Tab": "Tab", "Escape": "Esc", "Print": "ImprPant", "grave": "º",
    "mouse:272": "clic izquierdo (arrastrar)", "mouse:273": "clic derecho (arrastrar)",
    "XF86AudioRaiseVolume": "Subir volumen", "XF86AudioLowerVolume": "Bajar volumen",
    "XF86AudioMute": "Silenciar", "XF86AudioMicMute": "Silenciar micro",
    "XF86AudioPlay": "Play", "XF86AudioPause": "Pausa", "XF86AudioNext": "Siguiente",
    "XF86AudioPrev": "Anterior",
}
DIR = {"l": "a la izquierda", "r": "a la derecha", "u": "hacia arriba", "d": "hacia abajo",
       "left": "a la izquierda", "right": "a la derecha", "up": "hacia arriba", "down": "hacia abajo"}
# Monitor actions' argument: a side, or the next / previous one (two screens: the other).
SCREEN = {"l": "a la pantalla de la izquierda", "r": "a la pantalla de la derecha",
          "+1": "a la otra pantalla", "-1": "a la otra pantalla"}
CALLS = {"ryce.despejar": "Despejar el escritorio"}   # `call` binds, by function
TITLES = [  # keyword in the TSV's English section header -> Spanish title
    ("WM utilities", "Ventanas y sesión"), ("Terminal", "Terminal, cerrar y lanzador"),
    ("Focus", "Mover el foco"), ("Monitors", "Pantallas"), ("Move/swap", "Mover ventanas"),
    ("Resize", "Redimensionar"), ("Previous/next", "Workspace anterior / siguiente"),
    ("Go to workspace", "Ir a un workspace"), ("Move window to workspace", "Mandar una ventana a otro workspace"),
    ("Screenshots", "Capturas de pantalla (en ~/Pictures/Screenshots)"), ("Mouse", "Ratón"),
    ("Volume", "Volumen"), ("Music", "Música"), ("ryce extras", "Extras de este PC"),
]


def keys_of(mods: tuple[str, ...], key: str) -> str:
    parts = [MODS.get(m, m) for m in mods]
    parts.append(KEYS.get(key, key.upper() if len(key) == 1 else key))
    return " + ".join(f"`{p}`" for p in parts)


def what(action: str, arg: str) -> str:
    a = arg.strip()
    if action == "exec":
        low = a.lower()
        for needle, text in (
            ("systemctl hibernate", "Hibernar el PC (las sesiones siguen al volver)"),
            ("ryce-term", "Abrir una terminal"),
            ("sidebar", "Abrir o cerrar el panel lateral (agentes, música, controles)"),
            ("selector", "Elegir el tema (Origen, Grafito, Ola, Tinta o Papel)"),
            ("ryce-theme next", "Pasar al tema siguiente"),
            ("desk toggle clock", "Mostrar u ocultar el reloj del escritorio"),
            ("desk toggle stats", "Mostrar u ocultar los datos del PC en el escritorio"),
            ("desk toggle wall", "Encender o apagar el fondo animado"),
            ("call hito", "Abrir o cerrar tus tareas de Hito"),
            ("call keys", "Ver esta chuleta de atajos"),
            ("call aria", "Abrir o cerrar Aria, tu música"),
            ("call headset", "Conectar los cascos Bluetooth, o reconectarlos si ya están conectados"),
            ("call wallpick", "Elegir fondo"),
            ("wall", "Cambiar el fondo de pantalla"),
            ("switchxkblayout", "Cambiar teclado inglés/español"),
            ("hyprlock", "Bloquear la pantalla"),
            ("rofi -show drun", "Lanzador de aplicaciones"),
            ("clipboard", "Historial del portapapeles"),
            ("screenshot", "Captura de pantalla"),
            ("wpctl set-volume", "Volumen"),
            ("wpctl set-mute", "Silenciar"),
            ("playerctl", "Control de la música"),
            ("kitty", "Abrir una terminal"),
        ):
            if needle in low:
                if needle == "screenshot":
                    if "area-copy" in low or "copy" in low:
                        return "Captura de una zona al portapapeles"
                    if "edit" in low or "swappy" in low:
                        return "Captura de una zona para anotarla (swappy)"
                    if "area" in low:
                        return "Captura de una zona"
                    return "Captura de toda la pantalla"
                if needle == "playerctl":
                    for verb, t in (("play-pause", "Pausar o seguir la música"), ("next", "Canción siguiente"),
                                    ("previous", "Canción anterior")):
                        if verb in low:
                            return t
                if needle == "wpctl set-volume":
                    return "Subir volumen" if "+" in a else "Bajar volumen"
                return text
        return f"Ejecutar `{a}`"
    if action == "call":
        return CALLS.get(a, f"Ejecutar `{a}`")
    if action == "close":
        return "Cerrar la ventana"
    if action == "focus":
        return f"Mover el foco {DIR.get(a, a)}"
    if action == "move":
        return f"Mover la ventana {DIR.get(a, a)}"
    if action == "resize":
        dx, _, dy = a.partition(" ")
        if dx.lstrip("-") not in ("", "0"):
            return "Hacer la ventana más ancha" if not dx.startswith("-") else "Hacer la ventana más estrecha"
        return "Hacer la ventana más alta" if not dy.startswith("-") else "Hacer la ventana más baja"
    if action == "workspace":
        return f"Ir al workspace {a}"
    if action == "wsstep":
        if a.startswith("-"):
            return "Workspace anterior, aunque esté vacío (del 6 pasa al 5 de la otra pantalla; en el 1 se para)"
        return "Workspace siguiente, aunque esté vacío (del 5 pasa al 6 de la otra pantalla; en el 10 se para)"
    if action == "movetoworkspace":
        return f"Mandar la ventana al workspace {a} (y seguirla)"
    if action == "focusmonitor":
        return f"Foco {SCREEN.get(a, a)}"
    if action == "movetomonitor":
        return f"Mover la ventana {SCREEN.get(a, a)}"
    if action == "fullscreen":
        return "Pantalla completa"
    if action == "float":
        return "Ventana flotante / en mosaico"
    if action == "pseudo":
        return "Pseudo-mosaico"
    if action == "togglesplit":
        return "Cambiar la división (horizontal / vertical)"
    if action == "exit":
        return "Salir de Hyprland"
    if action == "drag":
        return "Mover la ventana con el ratón"
    if action == "dragresize":
        return "Redimensionar con el ratón"
    return f"{action} {a}".strip()


def sections(text: str) -> list[tuple[str, list[str]]]:
    """Split the TSV into (section title, raw bind lines) using its `# --` headers."""
    out: list[tuple[str, list[str]]] = []
    title = "General"
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# --"):
            raw = s[4:].strip()
            title = next((es for kw, es in TITLES if raw.startswith(kw)), raw.split("(")[0].strip())
            out.append((title, []))
            continue
        if not s or s.startswith("#"):
            continue
        if not out:
            out.append((title, []))
        out[-1][1].append(line)
    return [(t, ls) for t, ls in out if ls]


def render() -> str:
    text = SRC.read_text(encoding="utf-8")
    lines = [
        "# Atajos de teclado",
        "",
        "> GENERADO por `tools/atajos.py` desde `keys/keymap.tsv` — no lo edites a mano.",
        "> Son los atajos de tu Arch (`dotsArch`) más unos pocos extra. **Ctrl** es la tecla",
        "> principal y **Bloq Mayús funciona como otro Ctrl**.",
        "> Hay 10 workspaces. Con dos pantallas cada una tiene siempre los suyos: del 1 al 5",
        "> la principal y del 6 al 10 la segunda. Ir a uno con `Ctrl` + número te lleva también",
        "> a su pantalla, con el foco y el ratón. `Ctrl` + `←` / `→` va al anterior o al",
        "> siguiente por número: en el borde pasa a la otra pantalla (del 5 al 6 y del 6 al 5)",
        "> y se para en el 1 y en el 10. Con una sola pantalla, los 10 están en ella.",
        "",
    ]
    for title, raw in sections(text):
        binds = gen.parse("\n".join(raw), source="keymap.tsv")
        lines += [f"## {title}", "", "| Teclas | Qué hace |", "|---|---|"]
        for b in binds:
            lines.append(f"| {keys_of(b.mods, b.key)} | {what(b.action, b.arg)} |")
        lines.append("")
    return "\n".join(lines)


# The overlay's groups, in reading order, and how a bind finds its group.
GROUPS = ("Ventanas", "Workspaces", "Pantallas", "Apps", "Capturas", "Sonido", "ryce")
# Keycaps: KEYS spells keys for prose, these must fit a small cap.
CAPS = {
    **KEYS,
    "mouse:272": "Clic izq.", "mouse:273": "Clic der.",
    "XF86AudioRaiseVolume": "Vol +", "XF86AudioLowerVolume": "Vol −", "XF86AudioMute": "Silencio",
    "XF86AudioMicMute": "Micro", "XF86AudioNext": "Sig.", "XF86AudioPrev": "Ant.",
}
# Consecutive binds with the same mods and one of these actions fold into one row.
SERIES = {
    "focus": "Mover el foco",
    "move": "Mover la ventana",
    "resize": "Cambiar el tamaño de la ventana",
    "wsstep": "Workspace anterior / siguiente; en el borde pasa a la otra pantalla",
    "workspace": "Ir a un workspace (1–10)",
    "movetoworkspace": "Mandar la ventana a un workspace",
    "focusmonitor": "Foco a la pantalla de la izquierda / derecha",
    "movetomonitor": "Mover la ventana a la otra pantalla",
}


def group_of(b: gen.Bind) -> str:
    if b.action in gen.MONITOR_ACTIONS:
        return "Pantallas"
    if b.action in ("workspace", "movetoworkspace", "wsstep"):
        return "Workspaces"
    if b.action != "exec":
        return "Ventanas"
    low = b.arg.lower()
    if "screenshot" in low:
        return "Capturas"
    if "wpctl" in low or "playerctl" in low or "call headset" in low:
        return "Sonido"
    if "hyprlock" in low or "systemctl hibernate" in low:
        return "Ventanas"
    if "ipc call" in low or "ryce-theme" in low or "wall" in low or "switchxkblayout" in low:
        return "ryce"
    return "Apps"


def cap(key: str) -> str:
    return CAPS.get(key, key.upper() if len(key) == 1 else key)


def cheatsheet(text: str) -> dict:
    """The overlay's data: groups of rows, each row its keycaps and what it does."""
    runs: list[list[gen.Bind]] = []
    for b in gen.parse(text, source="keymap.tsv"):
        last = runs[-1][-1] if runs else None
        if last and b.action in SERIES and (last.action, last.mods) == (b.action, b.mods):
            runs[-1].append(b)
        else:
            runs.append([b])
    groups: dict[str, list[dict]] = {g: [] for g in GROUPS}
    for run in runs:
        first = run[0]
        mods = [MODS.get(m, m) for m in first.mods]
        if len(run) == 1:
            row = {"keys": [*mods, cap(first.key)], "what": what(first.action, first.arg)}
        else:
            caps = [cap(b.key) for b in run]
            joined = " ".join(caps) if len(caps) <= 4 else f"{caps[0]} … {caps[-1]}"
            row = {"keys": [*mods, joined], "what": SERIES[first.action]}
        rows = groups[group_of(first)]
        # Two lone keys doing the same thing (the Play and Pause media keys) read as one
        # row with both caps, not as a duplicated line.
        prev = rows[-1] if rows else None
        if prev and prev["what"] == row["what"] and len(prev["keys"]) == len(row["keys"]) == 1:
            prev["keys"] = [f"{prev['keys'][0]} / {row['keys'][0]}"]
            continue
        rows.append(row)
    return {
        "generated_by": "tools/atajos.py from keys/keymap.tsv; do not edit",
        "groups": [{"title": g, "rows": rows} for g, rows in groups.items() if rows],
    }


def render_json() -> str:
    data = cheatsheet(SRC.read_text(encoding="utf-8"))
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str]) -> int:
    outputs = {OUT: render(), JSON_OUT: render_json()}
    if "--check" in argv:
        stale = [p for p, text in outputs.items()
                 if (p.read_text(encoding="utf-8") if p.exists() else "") != text]
        for p in stale:
            print(f"stale: {p.relative_to(ROOT) if p.is_relative_to(ROOT) else p} (run python3 tools/atajos.py)")
        if not stale:
            print("atajos: ok")
        return 1 if stale else 0
    for p, text in outputs.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"wrote {p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
