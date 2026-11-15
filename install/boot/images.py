#!/usr/bin/env python3
"""The Plymouth images that depend on the theme, built at install time by install/boot-setup.sh
from themes/<id>/theme.json. Deterministic: the same theme and font give the same bytes, so a
second run changes nothing. (The GRUB menu has its own art: theme/boot/grub.py.)

    images.py dot THEME_DIR OUT.png                  the passphrase dot, in fg1
    images.py prompt THEME_DIR FONT INDEX OUT.png    «Contraseña del disco» in fg1, set in FONT
                                                     (face INDEX, as fc-scan numbers it)

The prompt is a picture, not Image.Text: plymouth's label-freetype decodes text with mbrtowc()
in the initramfs's C locale, where any non-ASCII byte (the ñ) comes out as a garbage glyph.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

SS = 8  # supersampling for anti-aliased edges
PROMPT = "Contraseña del disco"
# The label it replaces was Image.Text(..., FONT + " 12"): 12 pt at plymouth's 96 dpi.
PROMPT_PX = 16
PAD = 2  # transparent margin, so no anti-aliased edge touches the border


class Refused(Exception):
    pass


def rgb(hexcolor: str) -> tuple[int, int, int]:
    return tuple(int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))


def fg1(theme_dir: Path) -> tuple[int, int, int]:
    return rgb(json.loads((theme_dir / "theme.json").read_text())["colors"]["fg1"])


def dot(theme_dir: Path, out: Path) -> None:
    ink, d = fg1(theme_dir), 8
    big = Image.new("RGBA", (d * SS, d * SS), ink + (0,))
    ImageDraw.Draw(big).ellipse((0, 0, d * SS - 1, d * SS - 1), fill=ink + (255,))
    big.resize((d, d), Image.Resampling.BOX).save(out)


def has_glyph(font: ImageFont.FreeTypeFont, ch: str) -> bool:
    """False when FONT draws CH as its missing-glyph box (the same mask as a noncharacter)."""
    missing = font.getmask("\U0010fffe")
    mask = font.getmask(ch)
    if mask.size != missing.size:
        return True
    a = Image.frombytes("L", mask.size, bytes(mask)) if mask.size[0] and mask.size[1] else None
    b = Image.frombytes("L", missing.size, bytes(missing)) if missing.size[0] and missing.size[1] else None
    return a is not None and (b is None or ImageChops.difference(a, b).getbbox() is not None)


def prompt(theme_dir: Path, font_file: str, index: str, out: Path) -> None:
    # Drawn SS times larger and scaled down: at 16 px every advance would otherwise be
    # rounded to a whole pixel, which opens gaps such as «de l disco».
    font = ImageFont.truetype(font_file, PROMPT_PX * SS, index=int(index))
    # A variable face renders its default instance, which for Space Grotesk is Light (300):
    # thin, uneven strokes at 16 px. Ask for its Regular weight when it has one.
    try:
        axes = font.get_variation_axes()
    except OSError:      # not a variable font
        axes = []
    if axes:
        weights = [400 if a.get("name") in (b"Weight", "Weight") else a["default"] for a in axes]
        font.set_variation_by_axes([min(max(w, a["minimum"]), a["maximum"]) for w, a in zip(weights, axes)])
    missing = [ch for ch in sorted(set(PROMPT) - {" "}) if not has_glyph(font, ch)]
    if missing:
        raise Refused(f"{font_file} no tiene {' '.join(missing)}: el aviso de la contraseña saldría mal")
    ascent, descent = font.getmetrics()
    width = font.getlength(PROMPT)
    size = (round(width / SS) + 2 * PAD, round((ascent + descent) / SS) + 2 * PAD)
    # Coverage drawn alone and used as the alpha of a flat fg1 card: the edges keep the
    # theme's colour instead of blending towards a black that is not there.
    big = Image.new("L", (size[0] * SS, size[1] * SS), 0)
    ImageDraw.Draw(big).text((PAD * SS, PAD * SS + ascent), PROMPT, font=font, fill=255, anchor="ls")
    alpha = big.resize(size, Image.Resampling.BOX)
    card = Image.new("RGBA", alpha.size, fg1(theme_dir) + (255,))
    card.putalpha(alpha)
    card.save(out)


def main(argv: list[str]) -> int:
    verbs = {"dot": (dot, 3), "prompt": (prompt, 5)}
    if not argv or argv[0] not in verbs or len(argv) != verbs[argv[0]][1]:
        sys.exit(__doc__)
    f, _ = verbs[argv[0]]
    paths = [Path(argv[1])] + argv[2:-1] + [Path(argv[-1])]
    try:
        f(*paths)
    except (OSError, Refused) as e:
        print(f"images.py {argv[0]}: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
