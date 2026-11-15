#!/usr/bin/env python3
"""The terminal's greeting, per theme: the peonza spins down while a ring closes round it.

    python3 theme/greet/greet.py            write the file below for every theme
    python3 theme/greet/greet.py --check    exit 1 if any is stale or missing

    themes/<id>/greet/peonza.kitty   kitty graphics protocol escapes, ready to print: the
                                     animation's frames as PNG, its timing and the order to
                                     play it once. fish_greeting cats it at the cursor
                                     (apps/fish/functions/fish_greeting.fish)

The picture is 11 x 4 cells (110 x 104 px at kitty's 10 x 26 px cell: kitty.conf's 13 pt
JetBrains Mono at 112 % height, measured as 1840 x 1014 px for 184 x 39 cells). The
placement asks for those cells (c=, r=), so at another font size kitty scales it to fit.

The motion, 1.3 s: the brand's `think` state, spinning a little faster than its own
period and slowing to a stop, while an arc in fg1 sweeps once round a track in `line`
from twelve o'clock, its head a dot in fg0. The spin ends where `think` comes nearest the
still pose, and cuts to it: the still logo inside a closed hairline ring in fg2, which
is the frame kitty keeps. The cut is hard, like the brand's film (no fades). Ink is the
theme's fg0 with the grooves in bg0, as every peonza asset; the signal never appears.

Chosen from four drawn for the contact sheet (arc, dotted orbit, dial of ticks, a ring
on the floor round the tip): at 1:1 in 104 px the dots and ticks turned to grain and
the floor ring, 24 px tall, hid how far it had come; the arc is two strokes that read
as loading at a glance and settles into a ring that frames the still mark like a seal.

How kitty plays it (docs/graphics-protocol, «Animation»; kitty/graphics.c 0.49.2):
  a=T,I=…      the first frame, sent and placed at once. `I` (an image number, not an id)
               makes kitty pick a fresh id, so a second greeting in the same window never
               replaces the first one's picture; later commands with the same `I` reach
               the newest image with it
  C=1          the cursor stays put: fish writes the text beside the picture itself
  q=2          no replies: an OK or an error would land in the shell's input as typing
  a=f,c=…,X=1  each later frame starts as a copy of the one before (c) and only the
               rectangles that moved are sent over it, replacing (X=1, at x, y): the top's
               square and the ring's moving end; a second rectangle edits the same
               frame (r=). z is the frame's gap in ms
  a=a,r=1,z=…  the first frame's gap (a=T's z is the z-index, not a gap)
  a=a,s=3,v=2  run, looping v-1 = once: at the end kitty stops on the last frame
               (scan_active_animations: `++current_loop >= max_loops` skips the image),
               and image_is_animatable is false from then on, so no timer stays armed
Data goes in chunks of at most 4096 base64 bytes, the protocol's limit.

Size: every pixel is mapped to one COLOURS-entry palette shared by all frames (PNG-8
with alpha), so a pixel that did not move keeps its exact value and stays out of the
patches. Full RGBA frames came to 630 KiB a theme, RGBA patches to ~190 KiB, palette
patches to ~105 KiB: what a new shell prints. Equal neighbours merge into one gap.

--check replays the file the way kitty builds it (every frame whole, with its gap) and
compares that with a fresh render: placement, playback and gaps exactly, pixels within
QUANT (a different Pillow may cut the palette elsewhere) and QUANT_MEAN on average.
Without the brand repo (or PEONZA_BRAND), node or rsvg-convert it skips with a message
and exits 0, as gen.py does.
"""

from __future__ import annotations

import base64
import io
import math
import re
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "theme" / "peonza"))
sys.path.insert(0, str(ROOT / "tools"))

import gen  # noqa: E402
import tokens  # noqa: E402

COLS, ROWS = 11, 4
CELL = (10, 26)                  # kitty's cell in px on the desktop (see above)
W, H = COLS * CELL[0], ROWS * CELL[1]
PEONZA_PX = 64                   # the mark's square; its ink is ~52 px of it
STEPS = 144                      # think's period sampled every 2.5 deg of spin
THINK_PERIOD = 1200              # ms: logo-peonza src/pose.mjs `think.period`, which frames.mjs samples
GAP = 20                         # ms a frame: 50 a second
DURATION = 1300                  # ms from the first frame to the still
CRUISE = 0.4                     # share of it at full speed before the spin winds down
SPEED = 1.25                     # times think's own rate (one turn in 1.2 s) at the start
SETTLE = 0.27                    # think's phase nearest the still pose (lean 6.3, disc 9.4,
                                 # seams at -33 deg against the still's 8, 10, -32)
RING = 47.0                      # ring radius, px from the centre
TRACK, ARC, HEAD = 1.5, 2.5, 2.6 # stroke widths and the head's radius, px
SS = 4                           # supersampling for the strokes
TOP = ((W - PEONZA_PX) // 2, (H - PEONZA_PX) // 2)
TOP_MASK = np.zeros((H, W), dtype=bool)
TOP_MASK[TOP[1]:TOP[1] + PEONZA_PX, TOP[0]:TOP[0] + PEONZA_PX] = True
COLOURS = 64                     # one palette for every frame (PNG-8 with alpha)
INKS = ("fg0", "fg1", "fg2", "bg0", "line")   # what the picture is drawn in
QUANT = 24                       # --check: a pixel may move this far (one palette step:
                                 # another Pillow can cut the octree elsewhere) ...
QUANT_MEAN = 1.0                 # ... but a picture no further than this on average
NUMBER = 7365                    # the image number (any; kitty maps it to a fresh id)
CHUNK = 4096
OUT = "greet/peonza.kitty"
APC = re.compile(rb"\x1b_G([^;\x1b]*)(?:;([^\x1b]*))?\x1b\\")


def rgba(h: str) -> tuple[int, int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 255


def ease(x: float) -> float:
    return (1 - math.cos(math.pi * min(max(x, 0.0), 1.0))) / 2


def phase(ms: float) -> float:
    """Turns of think's period the spin has covered after `ms`: full speed for CRUISE of
    DURATION, then the rate eases to zero at DURATION (its integral, so never backwards)."""
    rate = SPEED / THINK_PERIOD      # turns a ms at full speed
    cruise = CRUISE * DURATION
    if ms <= cruise:
        return rate * ms
    span = DURATION - cruise
    x = min(ms - cruise, span) / span
    # integral of (1 - ease(x)) dx = x - (x - sin(pi x)/pi)/2
    return rate * (cruise + span * (x - (x - math.sin(math.pi * x) / math.pi) / 2))


def timeline() -> list[tuple[int, float, bool]]:
    """(think step, ring progress 0..1, settled) per GAP, the last one the still. The
    spin is shifted so it stops at SETTLE."""
    total = phase(DURATION)
    out = []
    for k in range(DURATION // GAP):
        ms = k * GAP
        step = round((SETTLE - total + phase(ms)) * STEPS) % STEPS
        out.append((step, ease(ms / DURATION), False))
    out.append((-1, 1.0, True))
    return out


def stroke(d: ImageDraw.ImageDraw, a0: float, a1: float, colour: tuple, width: float) -> None:
    """An arc of the ring from a0 to a1 degrees clockwise from twelve o'clock, round caps.
    Its vertices sit on a fixed 2 deg grid, so a longer arc repeats a shorter one's pixels
    and the next frame only has to carry the new end."""
    cx, cy = W / 2, H / 2
    angles = [a0 + 2 * k for k in range(int((a1 - a0) // 2) + 1)] + [a1]
    pts = [((cx + RING * math.sin(math.radians(a))) * SS, (cy - RING * math.cos(math.radians(a))) * SS) for a in angles]
    d.line(pts, fill=colour, width=round(width * SS), joint="curve")
    for x, y in (pts[0], pts[-1]):
        dot(d, x / SS, y / SS, width / 2, colour)


def dot(d: ImageDraw.ImageDraw, x: float, y: float, r: float, colour: tuple) -> None:
    d.ellipse(((x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS), fill=colour)


def ring(c: dict, p: float, settled: bool) -> Image.Image:
    big = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    if settled:
        stroke(d, 0, 360, rgba(c["fg2"]), TRACK)
    else:
        stroke(d, 0, 360, rgba(c["line"]), TRACK)
        if p > 0.004:
            stroke(d, 0, 360 * p, rgba(c["fg1"]), ARC)
        a = math.radians(360 * p)
        dot(d, W / 2 + RING * math.sin(a), H / 2 - RING * math.cos(a), HEAD, rgba(c["fg0"]))
    return big.resize((W, H), Image.Resampling.LANCZOS)


def pictures(t: dict) -> list[np.ndarray]:
    """Every GAP's picture as an H x W x 4 RGBA array, the last one the still."""
    c = t["colors"]
    ink = {"fg": c["fg0"], "bg": c["bg0"]}
    drawn = gen.svgs([{"key": "spin", "motion": "think", "frames": STEPS, "opsz": PEONZA_PX, "ink": ink},
                      {"key": "still", "motion": "still", "frames": 1, "opsz": PEONZA_PX, "ink": ink}])
    tops: dict[int, Image.Image] = {}
    out = []
    for step, p, settled in timeline():
        if step not in tops:
            tops[step] = gen.raster(drawn["still"][0] if settled else drawn["spin"][step], PEONZA_PX)
        img = ring(c, p, settled)
        img.alpha_composite(tops[step], TOP)
        out.append(np.asarray(img))
    return out


def palette(pics: list[np.ndarray], c: dict) -> np.ndarray:
    """One COLOURS-entry RGBA palette for the whole animation, so a pixel that does not
    change keeps its index from frame to frame and only what moves has to be sent: the
    theme's inks exactly and clear, then Pillow's octree over all frames side by side for
    the edges between them."""
    exact = [rgba(c[k]) for k in INKS] + [(0, 0, 0, 0)]
    sheet = Image.fromarray(np.concatenate(pics, axis=1), "RGBA")
    q = sheet.quantize(COLOURS - len(exact), method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    found = np.asarray(q.getpalette("RGBA"), dtype=np.int32).reshape(-1, 4)[:COLOURS - len(exact)]
    return np.concatenate([np.array(exact, dtype=np.int32), found])


def indexed(pic: np.ndarray, pal: np.ndarray) -> np.ndarray:
    """Each pixel's nearest palette entry, compared premultiplied: under alpha 0 any
    colour is the same transparent pixel."""
    def pre(a: np.ndarray) -> np.ndarray:
        a = a.astype(np.int32)
        return np.concatenate([a[..., :3] * a[..., 3:] // 255, a[..., 3:]], axis=-1)
    d = ((pre(pic)[:, :, None, :] - pre(pal)[None, None, :, :]) ** 2).sum(axis=-1)
    return d.argmin(axis=-1).astype(np.uint8)


def png(idx: np.ndarray, pal: np.ndarray) -> bytes:
    img = Image.fromarray(idx, "P")
    img.putpalette(pal[:, :3].astype(np.uint8).tobytes())
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True, transparency=pal[:, 3].astype(np.uint8).tobytes())
    return buf.getvalue()


def patches(prev: np.ndarray, cur: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Rectangles (x, y, w, h) covering every pixel that changed: the top's square and
    the ring's moving end, or one box round both when they meet."""
    diff = prev != cur
    rects = []
    for part in (diff & TOP_MASK, diff & ~TOP_MASK):
        ys, xs = np.nonzero(part)
        if len(xs):
            rects.append((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    if len(rects) == 2:
        (a0, b0, a1, b1), (c0, d0, c1, d1) = rects
        if a0 < c1 and c0 < a1 and b0 < d1 and d0 < b1:
            rects = [(min(a0, c0), min(b0, d0), max(a1, c1), max(b1, d1))]
    return [(x0, y0, x1 - x0, y1 - y0) for x0, y0, x1, y1 in rects]


def stream(t: dict) -> bytes:
    """The file: the first picture placed, every later one as the patches that turn the
    previous frame into it (a=f on top of c=<previous>, replacing: X=1), then play once."""
    pics = pictures(t)
    pal = palette(pics, t["colors"])
    idx = [indexed(p, pal) for p in pics]
    keep = [(idx[0], GAP)]
    for cur in idx[1:]:
        if np.array_equal(cur, keep[-1][0]):
            keep[-1] = (cur, keep[-1][1] + GAP)
        else:
            keep.append((cur, GAP))
    n = NUMBER
    out = [command(f"a=T,f=100,I={n},c={COLS},r={ROWS},C=1,q=2", png(keep[0][0], pal))]
    for frame, ((prev, _), (cur, gap)) in enumerate(zip(keep, keep[1:]), start=2):
        for k, (x, y, w, h) in enumerate(patches(prev, cur)):
            where = f"c={frame - 1},z={gap}" if k == 0 else f"r={frame}"
            out.append(command(f"a=f,f=100,I={n},{where},x={x},y={y},X=1,q=2", png(cur[y:y + h, x:x + w], pal)))
    out.append(command(f"a=a,I={n},r=1,z={keep[0][1]},q=2"))
    out.append(command(f"a=a,I={n},s=3,v=2,q=2"))
    return b"".join(out)


def command(keys: str, data: bytes = b"") -> bytes:
    """One graphics command; with data, as many chunks as the 4096-byte limit needs."""
    if not data:
        return b"\x1b_G" + keys.encode() + b"\x1b\\"
    b64 = base64.standard_b64encode(data)
    parts = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)]
    out = []
    for i, part in enumerate(parts):
        more = int(i < len(parts) - 1)
        head = f"{keys},m={more}" if i == 0 else f"m={more}"
        out.append(b"\x1b_G" + head.encode() + b";" + part + b"\x1b\\")
    return b"".join(out)


def parse(blob: bytes) -> list[tuple[str, bytes]]:
    """The file back as (keys, decoded data) per command, chunks joined. Raises
    ValueError on anything that is not a chain of graphics commands."""
    out: list[tuple[str, bytes]] = []
    pos, keys, data, open_ = 0, "", b"", False
    for m in APC.finditer(blob):
        if m.start() != pos:
            raise ValueError(f"stray bytes at {pos}")
        pos = m.end()
        head = m.group(1).decode()
        kv = dict(x.split("=", 1) for x in head.split(","))
        payload = base64.standard_b64decode(m.group(2) or b"")
        if open_:
            if set(kv) != {"m"}:
                raise ValueError(f"continuation chunk with keys {head}")
            data += payload
        else:
            keys = ",".join(f"{k}={v}" for k, v in kv.items() if k != "m")
            data = payload
        open_ = kv.get("m") == "1"
        if not open_:
            out.append((keys, data))
    if pos != len(blob) or open_:
        raise ValueError("truncated")
    return out


def keys(text: str) -> dict[str, str]:
    return dict(kv.split("=", 1) for kv in text.split(",")) if text else {}


def decode(data: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(data)) as im:
        return np.array(im.convert("RGBA"))


def replay(blob: bytes) -> tuple[str, list[tuple[np.ndarray, int]], list[str]]:
    """What kitty builds from the file: the placement's keys, every frame as a whole
    RGBA picture with its gap, and the closing animation commands. Raises ValueError
    on a command this file does not use or one that refers to a missing frame."""
    cmds = parse(blob)
    if not cmds or keys(cmds[0][0]).get("a") != "T":
        raise ValueError("does not open with a=T")
    out = [[decode(cmds[0][1]), GAP]]
    tail = []
    for text, data in cmds[1:]:
        k = keys(text)
        if k.get("a") == "a":
            tail.append(text)
            if "r" in k and "z" in k:
                out[int(k["r"]) - 1][1] = int(k["z"])
            continue
        if k.get("a") != "f" or k.get("X") != "1" or not data:
            raise ValueError(f"unexpected command {text}")
        if "c" in k:
            base = int(k["c"])
            if not 1 <= base <= len(out):
                raise ValueError(f"c={base} before that frame exists")
            out.append([out[base - 1][0].copy(), int(k["z"])])
        elif int(k.get("r", 0)) != len(out):
            raise ValueError(f"edits frame {k.get('r')}, not the one being built")
        x, y, patch = int(k["x"]), int(k["y"]), decode(data)
        canvas = out[-1][0]
        if y + patch.shape[0] > canvas.shape[0] or x + patch.shape[1] > canvas.shape[1]:
            raise ValueError(f"patch at {x},{y} runs off the picture")
        canvas[y:y + patch.shape[0], x:x + patch.shape[1]] = patch
    return cmds[0][0], [(f, g) for f, g in out], tail


def differs(path: Path, want: bytes) -> str | None:
    if not path.exists():
        return "missing"
    try:
        got, new = replay(path.read_bytes()), replay(want)
    except (ValueError, OSError) as e:
        return f"not a greeting kitty can play ({e})"
    if (got[0], got[2]) != (new[0], new[2]):
        return "placement or playback differs"
    if [g for _, g in got[1]] != [g for _, g in new[1]]:
        return f"timing: {len(got[1])} frames, expected {len(new[1])}, or their gaps differ"
    for i, ((cur, _), (ref, _)) in enumerate(zip(got[1], new[1])):
        if cur.shape != ref.shape:
            return f"frame {i}: size {cur.shape[1]}x{cur.shape[0]}, expected {ref.shape[1]}x{ref.shape[0]}"
        d = np.abs(cur.astype(np.int16) - ref.astype(np.int16))
        if d.max() > QUANT or d.mean() > QUANT_MEAN:
            return f"frame {i}: pixels differ by up to {d.max()} ({d.mean():.2f} on average)"
    return None


def main(argv: list[str]) -> int:
    check = "--check" in argv
    missing = [what for what, ok in ((f"{gen.REPO}/src/pose.mjs", (gen.REPO / "src" / "pose.mjs").exists()),
                                     ("node", shutil.which("node")),
                                     ("rsvg-convert", shutil.which("rsvg-convert"))) if not ok]
    if missing:
        print(f"greet: skip (no {', '.join(missing)}; set PEONZA_BRAND to logo-peonza's brand/mark/)")
        return 0
    stale = []
    for tid in tokens.theme_ids():
        try:
            want = stream(tokens.load(tid))
        except tokens.ThemeError as e:
            print(f"greet: {e}", file=sys.stderr)
            return 2
        path = gen.THEMES_OUT / tid / OUT
        if check:
            why = differs(path, want)
            if why:
                stale.append(f"{path.relative_to(ROOT)}: {why}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(want)
        print(f"wrote themes/{tid}/{OUT} ({len(want) // 1024} KiB)")
    for line in stale:
        print(f"stale: {line} (run python3 theme/greet/greet.py)")
    if check and not stale:
        print("greet: ok")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
