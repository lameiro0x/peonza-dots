#!/usr/bin/env python3
"""Papel's pictures: a reading room at night. A book lies open on green baize under a
brass lamp; its letters are vellum, its ornaments gilt.

    python3 theme/wallpaper/paper.py            write assets/wallpapers/papel.jpg (2560x1440)
                                                and papel-lock.jpg (1920x1080)
    python3 theme/wallpaper/paper.py --check    exit 1 if a committed master is stale or
                                                breaks the budget below
    python3 theme/wallpaper/paper.py --out DIR  render both into DIR (for looking)

The ground is the theme's bg0 as baize: a felt of fine seeded noise (it also dithers the
lamp's gradient against banding) and a warm pool of lamplight, bg0 lifted a little
towards the gilt. On it, only two inks: vellum (fg0) and gilt (tint). The signal colour
never appears; it belongs to «an AI session waits» alone.

  desktop  the opening of Don Quijote (Cervantes, 1605; the 1905 Barcelona edition's text
           on Wikisource, accents modernised) set as a spread in Literata at book size:
           justified, old-style figures, running heads in small capitals with their
           folios, the chapter's head, a peonza (the user's mark) for a fleuron and a
           swash E from EB Garamond Italic dropped four lines for the initial. The
           letters are ghosts, vellum at ~1.5:1 on the baize, a texture and not a read;
           only the initial and the fleuron are gilt at fuller strength. The spread lies
           where the desk's cards are not (SPREAD, clear of CARDS: the clock, the stats, Hito
           and the desk's peonza), under the lamp; the bar's band and the cards' places
           stay bare baize, so a card never cuts a letter in half.
  lock     a title page: a gilt double rule framing the screen, a fleuron breaking it at
           the head, a short rule under the title, the peonza as the printer's device and
           a hairline for the password. hyprlock (@papel/hypr/hyprlock.conf) writes the
           title, the hour in words (bin/ryce-hora), and every other line; LOCK holds the
           rows it is measured against.

Everything is set in 1920x1080 units and drawn at each master's own size (u = w / 1920),
never resized from a bigger render. panels.py (the launcher's ex libris) and newtab.py
(the 1605 title page) draw with the helpers here. Deterministic: seeded noise only, no
wall-clock input; --check compares decoded pixels with scenes.py's tolerance. Reads
~/Repos/logo-peonza (or $PEONZA_BRAND) for the peonza; without it, it skips with a message.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenes import BRAND, ROOT, colormath, differs, fbm, finish, grain, grid, hexrgb, mark, save, tokens  # noqa: E402

OUT = ROOT / "assets" / "wallpapers" / "papel.jpg"
LOCK = ROOT / "assets" / "wallpapers" / "papel-lock.jpg"
FONTS = ROOT / "assets" / "fonts"
LITERATA = FONTS / "Literata-Variable.ttf"
LITERATA_ITALIC = FONTS / "Literata-Italic-Variable.ttf"
GARAMOND_ITALIC = FONTS / "EBGaramond-Italic-Variable.ttf"   # the swash capitals and ❦ ❧ ☙

# The text: chapter one, one string per paragraph, more than the two pages hold.
CHAPTER = ("Capítulo primero", "Que trata de la condición y ejercicio del famoso",
           "hidalgo don Quijote de la Mancha")
QUIJOTE = (
    "En un lugar de la Mancha, de cuyo nombre no quiero acordarme, no ha mucho tiempo que "
    "vivía un hidalgo de los de lanza en astillero, adarga antigua, rocín flaco y galgo "
    "corredor. Una olla de algo más vaca que carnero, salpicón las más noches, duelos y "
    "quebrantos los sábados, lantejas los viernes, algún palomino de añadidura los domingos, "
    "consumían las tres partes de su hacienda. El resto della concluían sayo de velarte, "
    "calzas de velludo para las fiestas, con sus pantuflos de lo mismo, y los días de entre "
    "semana se honraba con su vellorí de lo más fino. Tenía en su casa una ama que pasaba de "
    "los cuarenta, y una sobrina que no llegaba a los veinte, y un mozo de campo y plaza, que "
    "así ensillaba el rocín como tomaba la podadera. Frisaba la edad de nuestro hidalgo con "
    "los cincuenta años: era de complexión recia, seco de carnes, enjuto de rostro, gran "
    "madrugador y amigo de la caza. Quieren decir que tenía el sobrenombre de Quijada o "
    "Quesada (que en esto hay alguna diferencia en los autores que deste caso escriben), "
    "aunque por conjeturas verosímiles se deja entender que se llamaba Quijano. Pero esto "
    "importa poco a nuestro cuento; basta que en la narración dél no se salga un punto de la "
    "verdad.",
    "Es, pues, de saber que este sobredicho hidalgo, los ratos que estaba ocioso (que eran "
    "los más del año), se daba a leer libros de caballerías, con tanta afición y gusto, que "
    "olvidó casi de todo punto el ejercicio de la caza, y aun la administración de su "
    "hacienda; y llegó a tanto su curiosidad y desatino en esto, que vendió muchas hanegas de "
    "tierra de sembradura para comprar libros de caballerías en que leer, y así llevó a su "
    "casa todos cuantos pudo haber dellos; y de todos, ningunos le parecían tan bien como los "
    "que compuso el famoso Feliciano de Silva, porque la claridad de su prosa y aquellas "
    "entricadas razones suyas le parecían de perlas; y más cuando llegaba a leer aquellos "
    "requiebros y cartas de amoríos, donde en muchas partes hallaba escrito: «La razón de la "
    "sinrazón que a mi razón se hace, de tal manera mi razón enflaquece, que con razón me "
    "quejo de la vuestra fermosura». Y también cuando leía: «Los altos cielos, que de vuestra "
    "divinidad divinamente con las estrellas os fortifican, os hacen merecedora del "
    "merecimiento que merece la vuestra grandeza».",
    "Con estas y semejantes razones perdía el pobre caballero el juicio, y desvelábase por "
    "entenderlas y desentrañarles el sentido, que no se lo sacara ni las entendiera el mismo "
    "Aristóteles, si resucitara para solo ello.",
)
HEADS = ("Don Quijote de la Mancha", "Capítulo primero")
FOLIOS = (32, 33)               # a modern edition's: the preliminaries fill the first thirty

# ── layout, in 1920x1080 units ────────────────────────────────────────────────
BAR = 48                        # the bar's band: bare baize
# The desk's cards at their largest, measured on the stage at 1920x1080 (2026-11-19) with
# a little slack: the clock top left (DeskScreen.qml: left 52, top frameTop + 40), the
# stats bottom left (bottom 44), Hito top right (HitoDesk.qml, ten lines) and the desk's
# peonza bottom right (peonza/DeskPeonza.qml: 116 px, right 52, bottom 44). Nothing of
# the book sits under one or within CARD_MARGIN of it, or its edge would cut a letter.
CARDS = {"reloj": (52, 88, 860, 330), "estado": (52, 760, 450, 1036), "hito": (1360, 88, 1880, 560),
         "peonza": (1752, 920, 1868, 1036)}
CARD_MARGIN = 24
# The spread: verso and recto text blocks (x0, x1), the running heads' baseline, the body's
# first baseline, its leading and lines per page. Between the stats and the peonza, under
# Hito's card.
SPREAD = {"verso": (500, 1010), "recto": (1150, 1660), "head": 622, "first": 664, "lead": 25,
          "lines": 15, "size": 16.5}
LAMP = {"desk": (0.56, 0.80, 0.42, 0.50), "lock": (0.50, 0.44, 0.40, 0.46)}  # cx, cy, rx, ry (fractions)
# Lock: the frame's insets, and the rows hyprlock's lines are measured against.
LOCK_FRAME = (48, 58)           # outer rule (2 px) and inner rule (1 px), from every edge
LOCK_ROWS = {"title_rule": 548, "device": (590, 672), "field_rule": 778, "field_width": 360}
# Where the lock's words go: no ink of the picture there (hour, part of day and date).
LOCK_QUIET = (200, 300, 1720, 530)

# Ink strengths: how far towards its colour a fully covered pixel goes.
GHOST = 0.14                  # vellum letters, ~1.5:1 on the lit baize: a texture
GILT = 0.62                     # the initial and the fleuron, the one warm accent
RULE = 0.42                     # the lock's rules: present, never brighter than its words

# What a picture may cost, measured on the render (the 1920 one for the desktop budget).
BUDGET = {
    "ghost_max": 1.6,           # the strongest ghost letter against its own ground
    "lamp_max": "bg3",          # the lamp lights the baize at most to bg3's luminance
    "band_step_max": 0.75,      # a flat 8-bit run may not span most of a step of the light
    "mean_min": 0.85,           # the room stays bg0: its mean luminance between these shares
    "mean_max": 1.5,            # of bg0's (a darker corner, a lamp, never a lit room)
}


# ── type ──────────────────────────────────────────────────────────────────────
def face(path: Path, px: float, wght: int = 400) -> ImageFont.FreeTypeFont:
    """A variable font at px, its optical size set to px (Literata's opsz 7..72)."""
    f = ImageFont.truetype(str(path), px, layout_engine=ImageFont.Layout.RAQM)
    f.set_variation_by_axes([min(max(px, a["minimum"]), a["maximum"]) if b"Optical" in a["name"] else wght
                             for a in f.get_variation_axes()])
    return f


def spaced(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, x: float, base: float,
           track: float, features: list[str], align: str = "centre") -> tuple[float, float]:
    """Letterspaced capitals (small capitals with c2sc) one glyph at a time; x is the line's
    centre, left or right edge by `align`. Returns the line's (left, right)."""
    widths = [font.getlength(ch, features=features) for ch in text]
    total = sum(widths) + track * (len(text) - 1)
    left = {"centre": x - total / 2, "left": x, "right": x - total}[align]
    pos = left
    for ch, wd in zip(text, widths):
        draw.text((pos, base), ch, font=font, fill=255, anchor="ls", features=features)
        pos += wd + track
    return left, left + total


def column(draw: ImageDraw.ImageDraw, words: list[tuple[str, bool]], start: int, x0: float, x1: float,
           base: float, lead: float, lines: int, font: ImageFont.FreeTypeFont,
           indent: dict[int, float] | None = None, caps: int = 0) -> int:
    """Justified lines from words[start:] (word, opens a paragraph), as many as `lines`.
    A paragraph opens with a 1 em indent, its last line ragged; indent maps a line to its
    extra left indent (the dropped initial); the first `caps` words of the column are set
    in small capitals. Returns the index of the first word left over."""
    space = font.getlength(" ")
    i = start
    for n in range(lines):
        if i >= len(words):
            break
        left = x0 + (indent or {}).get(n, 0.0) + (font.size if words[i][1] and n else 0.0)
        line, width = [], 0.0
        while i < len(words):
            word, opens = words[i]
            if line and opens:
                break
            feats = ["onum", "pnum"] + (["smcp"] if i - start < caps else [])
            wd = font.getlength(word, features=feats)
            if line and width + space + wd > x1 - left:
                break
            line.append((word, wd, feats))
            width += (space if len(line) > 1 else 0) + wd
            i += 1
        ragged = i >= len(words) or words[i][1]
        gap = space if ragged or len(line) < 2 else (x1 - left - sum(w for _, w, _ in line)) / (len(line) - 1)
        x = left
        for word, wd, feats in line:
            draw.text((x, base + n * lead), word, font=font, fill=255, anchor="ls", features=feats)
            x += wd + gap
    return i


def tokens_of(paragraphs: tuple[str, ...]) -> list[tuple[str, bool]]:
    return [(w, k == 0) for p in paragraphs for k, w in enumerate(p.split())]


def peonza(height: int) -> np.ndarray:
    """The peonza as a fleuron, height px tall: its silhouette, the engraving's lines
    (peonza.svg's dark strokes) cut out of it so the ground shows through them."""
    sil = mark("peonza-silhouette.svg", height=height)[..., 3]
    full = mark("peonza.svg", height=height)
    return sil * (1 - full[..., 3] * (1 - full[..., :3].mean(axis=-1)))


def stamp(mask: Image.Image, cov: np.ndarray, cx: float, top: float) -> None:
    """Paste a coverage array into an L mask, centred on cx, its top at `top`."""
    h, w = cov.shape
    layer = Image.fromarray(np.round(cov * 255).astype(np.uint8), mode="L")
    x, y = round(cx - w / 2), round(top)
    region = mask.crop((x, y, x + w, y + h))
    mask.paste(Image.fromarray(np.maximum(np.asarray(region), np.asarray(layer))), (x, y))


# ── ground and inks ───────────────────────────────────────────────────────────
def palette(t: dict) -> dict[str, np.ndarray]:
    c = t["colors"]
    return {"bg0": hexrgb(c["bg0"]), "vellum": hexrgb(c["fg0"]), "gilt": hexrgb(c["tint"]),
            "lamp": hexrgb(c["bg0"]) + (hexrgb(c["tint"]) - hexrgb(c["bg0"])) * 0.10}


def baize(w: int, h: int, t: dict, lamp: tuple[float, float, float, float], seed: int = 7,
          felt: bool = True) -> np.ndarray:
    """bg0 as felt under a lamp: a warm pool (bg0 lifted towards the gilt) fading to a
    room a shade darker than bg0 at the corners, a soft mottle and a fine grain (felt=False:
    the light alone, what the banding measure compares against)."""
    pal = palette(t)
    x, y = grid(w, h)
    cx, cy, rx, ry = lamp
    aspect = w / h
    pool = np.exp(-(((x - cx) * aspect / (rx * aspect)) ** 2 + ((y - cy) / ry) ** 2))
    rgb = pal["bg0"] + (pal["lamp"] - pal["bg0"]) * pool[..., None]
    rgb = rgb * (1 - 0.10 * np.clip(1 - pool / 0.12, 0, 1) ** 2)[..., None]   # the room beyond the pool
    if not felt:
        return rgb
    u = w / 1920
    rgb = rgb * (1 + 0.035 * (fbm(w, h, 9 * u, 9 * u, 3, seed) - 0.5))[..., None]
    return rgb + grain(w, h, seed + 1, 1.1 / 255)


def lay(ground: np.ndarray, inks: list[tuple[np.ndarray, float, Image.Image]]) -> np.ndarray:
    """Each ink (colour, strength, L mask) over the ground, in order."""
    rgb = ground
    for col, k, mask in inks:
        a = np.asarray(mask, dtype=np.float64)[..., None] / 255.0 * k
        rgb = rgb + (col - rgb) * a
    return rgb


def blank(w: int, h: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    m = Image.new("L", (w, h), 0)
    return m, ImageDraw.Draw(m)


# ── desktop ───────────────────────────────────────────────────────────────────
def desktop_layers(w: int, h: int, t: dict) -> tuple[np.ndarray, list, tuple]:
    pal = palette(t)
    u = w / 1920
    s = SPREAD
    ghost, gd = blank(w, h)
    gilt, ld = blank(w, h)
    body = face(LITERATA, s["size"] * u)
    lead = s["lead"] * u
    caps = face(LITERATA, 13 * u)
    folio = face(LITERATA, s["size"] * u)
    (v0, v1), (r0, r1) = (np.array(s["verso"]) * u), (np.array(s["recto"]) * u)
    head, first = s["head"] * u, s["first"] * u

    # Running heads in letterspaced small capitals, folios on the outer edges.
    for (x0, x1), text, num, outer in (((v0, v1), HEADS[0], FOLIOS[0], "left"),
                                       ((r0, r1), HEADS[1], FOLIOS[1], "right")):
        spaced(gd, text.upper(), caps, (x0 + x1) / 2, head, 1.6 * u, ["c2sc"])
        gd.text((x0 if outer == "left" else x1, head), str(num), font=folio, fill=255,
                anchor="ls" if outer == "left" else "rs", features=["onum"])

    # The chapter's head on the verso: its number in spaced small capitals, its title in
    # italic, the peonza under them as the fleuron.
    mid = (v0 + v1) / 2
    spaced(gd, CHAPTER[0].upper(), face(LITERATA, 17 * u), mid, first + 6 * u, 2.4 * u, ["c2sc"])
    ital = face(LITERATA_ITALIC, 15 * u)
    for k, line in enumerate(CHAPTER[1:]):
        gd.text((mid, first + (6 + 32 + 21 * k) * u), line, font=ital, fill=255, anchor="ms", features=["onum"])
    stamp(gilt, peonza(round(40 * u)), mid, first + 72 * u)

    # The body: five lines of the verso go to the head, the initial drops four.
    words = tokens_of(QUIJOTE)
    words[0] = (words[0][0][1:], True)               # «En» -> the initial E + «n»
    top = first + 5 * s["lead"] * u
    drop = 4
    big = face(GARAMOND_ITALIC, 100)
    l, tp, r, b = big.getbbox("E", anchor="ls", features=["swsh"])
    # Cap top on the first line's cap height (Literata's H is 0.70 em), foot on line four's baseline.
    span = (drop - 1) * lead + 0.70 * body.size
    initial = face(GARAMOND_ITALIC, 100 * span / -tp)
    l, tp, r, b = initial.getbbox("E", anchor="ls", features=["swsh"])
    ld.text((v0 - l, top + (drop - 1) * lead), "E", font=initial, fill=255, anchor="ls", features=["swsh"])
    # The swash's tail runs under line four's baseline: line five steps aside for it too.
    hang = {n: r - l + 6 * u for n in range(drop + 1)}
    nxt = column(gd, words, 0, v0, v1, top, lead, s["lines"] - 5, body, indent=hang, caps=4)
    column(gd, words, nxt, r0, r1, first, lead, s["lines"], body)
    return baize(w, h, t, LAMP["desk"]), [(pal["vellum"], GHOST, ghost), (pal["gilt"], GILT, gilt)], LAMP["desk"]


def desktop(w: int, h: int, t: dict) -> Image.Image:
    return finish(lay(*desktop_layers(w, h, t)[:2]))


# ── lock ──────────────────────────────────────────────────────────────────────
def lock_layers(w: int, h: int, t: dict) -> tuple[np.ndarray, list, tuple]:
    pal = palette(t)
    u = w / 1920
    rules, rd = blank(w, h)
    gilt, ld = blank(w, h)
    # The frame: a thick-thin double rule, broken at the head by a fleuron.
    o, i = (v * u for v in LOCK_FRAME)
    rd.rectangle((o, o, w - 1 - o, h - 1 - o), outline=255, width=max(1, round(2 * u)))
    rd.rectangle((i, i, w - 1 - i, h - 1 - i), outline=255, width=max(1, round(1 * u)))
    orn = face(GARAMOND_ITALIC, 40 * u)
    cx = w / 2
    gap = 46 * u
    rd.rectangle((cx - gap, 0, cx + gap, i + 4 * u), fill=0)
    ld.text((cx, (o + i) / 2 + 13 * u), "❦", font=orn, fill=255, anchor="ms")
    # The title's rule, the device, the field's hairline.
    rr = LOCK_ROWS
    rd.line((cx - 60 * u, rr["title_rule"] * u, cx + 60 * u, rr["title_rule"] * u), fill=255, width=max(1, round(u)))
    top, bottom = (v * u for v in rr["device"])
    stamp(gilt, peonza(round(bottom - top)), cx, top)
    half = rr["field_width"] / 2 * u
    rd.line((cx - half, rr["field_rule"] * u, cx + half, rr["field_rule"] * u), fill=255, width=max(1, round(u)))
    return baize(w, h, t, LAMP["lock"], seed=11), [(pal["gilt"], RULE, rules), (pal["gilt"], GILT, gilt)], LAMP["lock"]


def lock(w: int, h: int, t: dict) -> Image.Image:
    return finish(lay(*lock_layers(w, h, t)[:2]))


# ── budget and outputs ────────────────────────────────────────────────────────
def luminance(rgb: np.ndarray) -> np.ndarray:
    a = np.clip(rgb, 0, 1)
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def band_step(row8: np.ndarray, light: np.ndarray) -> float:
    """Banding along one row: the most the smooth light underneath (`light`, in 8-bit
    units) changes across one run of a single 8-bit value. A run that spans a whole step
    of the gradient (≥ 1) is a visible band; the grain keeps runs far shorter."""
    edges = np.flatnonzero(np.diff(row8) != 0) + 1
    starts, stops = np.concatenate([[0], edges]), np.concatenate([edges, [len(row8) - 1]])
    return float(np.abs(light[stops] - light[starts]).max())     # from a run's start to the next one's


def measure(layers: tuple, t: dict) -> dict:
    """The numbers the budget reads: the ghost letters' worst contrast against their own
    ground, the lamp's brightest pixel, and the banding across the lamp's gradient (rows
    through the pool, green channel)."""
    ground, inks, lamp = layers
    h, w = ground.shape[:2]
    ground8 = np.clip(np.round(ground * 255), 0, 255)
    lum = luminance(ground8 / 255)
    light = baize(w, h, t, lamp, felt=False) * 255
    out = {"lamp_max": float(lum.max()),
           "lamp_hex": "#%02x%02x%02x" % tuple(int(v) for v in ground8.reshape(-1, 3)[lum.argmax()]),
           "band_step": max(band_step(ground8[y, :, 1], light[y, :, 1])
                            for y in (round(h * f) for f in (0.3, 0.5, 0.8)))}
    vellum = palette(t)["vellum"]
    for col, k, mask in inks:
        if np.array_equal(col, vellum):
            full = np.asarray(mask) >= 250
            ink = luminance((ground8 / 255 + (col - ground8 / 255) * k)[full])
            out["ghost_max"] = float(((ink + 0.05) / (lum[full] + 0.05)).max())
    return out


def over_budget(img: Image.Image, t: dict, layers: tuple | None = None, desk: bool = True) -> list[str]:
    """What breaks the budget: the mean always; with the layers (paper.py's own renders),
    the lamp, the banding, the ghosts and the zones that must stay bare baize."""
    out = []
    lum = luminance(np.asarray(img.convert("RGB"), dtype=np.float64) / 255.0)
    bg0 = colormath.luminance(t["colors"]["bg0"])
    if lum.mean() < BUDGET["mean_min"] * bg0:
        out.append(f"mean luminance {lum.mean():.4f} < {BUDGET['mean_min'] * bg0:.4f}: the room is darker than its baize")
    if lum.mean() > BUDGET["mean_max"] * bg0:
        out.append(f"mean luminance {lum.mean():.4f} > {BUDGET['mean_max'] * bg0:.4f}: no longer a dim room")
    if layers is None:
        return out
    m = measure(layers, t)
    ceiling = colormath.luminance(t["colors"][BUDGET["lamp_max"]])
    if m["lamp_max"] > ceiling:
        out.append(f"the lamp lights the baize to {m['lamp_hex']} ({m['lamp_max']:.4f}), past {BUDGET['lamp_max']}")
    if m["band_step"] >= BUDGET["band_step_max"]:
        out.append(f"banding: one flat run spans {m['band_step']:.2f} of an 8-bit step across the lamp")
    if m.get("ghost_max", 0) > BUDGET["ghost_max"]:
        out.append(f"ghost letters reach {m['ghost_max']:.2f}:1 (> {BUDGET['ghost_max']}): they would read, not rest")
    u = img.width / 1920
    marks = sum(np.asarray(mask, dtype=np.int32) for _, _, mask in layers[1])
    zones = [(0, 0, 1920, BAR), *CARDS.values()] if desk else [LOCK_QUIET]
    pad = CARD_MARGIN if desk else 0
    for x0, y0, x1, y1 in zones:
        part = marks[max(0, round((y0 - pad) * u)):round((y1 + pad) * u), max(0, round((x0 - pad) * u)):round((x1 + pad) * u)]
        if part.any():
            out.append(f"ink inside {(x0, y0, x1, y1)}: the bar, a card or the lock's words would sit on it")
    return out


def outputs() -> list[tuple[Path, int, int, bool]]:
    """(master, width, height, is the desktop)."""
    return [(OUT, 2560, 1440, True), (LOCK, 1920, 1080, False)]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a master is stale or over budget")
    ap.add_argument("--out", type=Path, help="write both pictures into this folder instead")
    a = ap.parse_args(argv)
    if not (BRAND / "peonza-silhouette.svg").exists():
        print(f"paper: skip (no {BRAND / 'peonza-silhouette.svg'}; set PEONZA_BRAND to the brand's mark/ folder)")
        return 0
    # Raw, not tokens.load(): the contract names these masters, so it validates only once they exist.
    t = json.loads((tokens.THEMES_SRC / "papel.json").read_text(encoding="utf-8"))
    bad = []
    for path, w, h, desk in outputs():
        layers = (desktop_layers if desk else lock_layers)(w, h, t)
        img = finish(lay(*layers[:2]))
        m = measure(layers, t)
        print(f"paper: {path.name}: lamp {m['lamp_hex']} ({m['lamp_max']:.4f}), banding {m['band_step']:.2f} step"
              + (f", ghost letters {m['ghost_max']:.2f}:1" if "ghost_max" in m else ""))
        bad += [f"{path.name}: {b}" for b in over_budget(img, t, layers, desk)]
        if a.check:
            why = differs(path, img)
            if why:
                bad.append(f"stale: {path.relative_to(ROOT)}: {why} (run python3 theme/wallpaper/paper.py)")
        else:
            dst = a.out / path.name if a.out else path
            dst.parent.mkdir(parents=True, exist_ok=True)
            save(dst, img)
            print(f"wrote {dst}")
    for b in bad:
        print(f"paper: {b}")
    if a.check and not bad:
        print("paper: ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
