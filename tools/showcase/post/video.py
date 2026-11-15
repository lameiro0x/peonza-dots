#!/usr/bin/env python3
"""The README's moving pictures from the raw clips of tools/showcase/scenes/record.sh.

    python3 -I tools/showcase/post/video.py RAW_DIR MEDIA_DIR [demo|hero|greeter]...

demo.mp4   the beats cut and joined with xfade, a key caption on each, H.264 two-pass
           to a byte budget (1920x1080, 60 fps, yuv420p, faststart, no audio).
hero.webp  the five themes' transitions on the bare desk, 1280x720, a seamless loop
           (it starts and ends on Tinta); hero.jpg its first frame.
greeter.webp  the kitty greeter, cropped to the terminal's corner.

Every in and out point is in seconds of its raw clip, set by watching the clips.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stills import KB, font  # noqa: E402

FPS = 60
XFADE = 0.5
DEMO_BUDGET = int(9.2 * 1024 * KB)       # under GitHub's 10 MB, with room for the mux
# clip, in, out, the transition into the next beat, captions (from, to, text) in clip time.
BEATS = [
    ("a-desk", 0.5, 6.0, "fade", []),
    ("b-terms", 1.5, 13.3, "fade", [(2.0, 5.2, "Ctrl+Enter · terminal")]),
    ("c-audio", 0.6, 13.9, "fade", [(0.9, 6.2, "Super+A · panel"), (7.4, 13.4, "Super+M · Aria")]),
    ("d-themes", 0.8, 22.8, "fade", [(1.0, 4.0, "Super+T · themes")]),
    ("e-keys", 0.3, 8.4, "fadeblack", [(0.6, 4.0, "Super+F1 · keys"), (4.4, 8.1, "Ctrl+1…0 · workspaces")]),
    ("f-desk", 0.4, 4.9, None, []),
]
HERO = ("hero", 1.7, 14.6)               # Tinta, the five transitions, Tinta again
HERO_SPEED = 1.5
GREETER = ("greeter", 1.35, 3.6, (620, 214, 10, 60))   # crop: w, h, x, y of the corner


def run(cmd: list[str], timeout: int = 1800) -> None:
    subprocess.run(cmd, check=True, timeout=timeout)


def clip(raw: Path, name: str) -> Path:
    p = raw / f"{name}.mp4"
    if not p.is_file():
        raise SystemExit(f"video.py: missing {p} (run tools/showcase/scenes/record.sh)")
    return p


def caption(text: str, out: Path) -> None:
    """A quiet lower-third: the key in JetBrains Mono on a neutral smoked plate."""
    f = font(26, 500)
    pad_x, h = 22, 52
    w = int(ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(text, font=f)) + 2 * pad_x
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=6, fill=(12, 12, 12, 214), outline=(90, 90, 90, 200), width=1)
    d.text((pad_x, h // 2 + 1), text, font=f, fill=(240, 240, 240, 255), anchor="lm")
    im.save(out)


def demo(raw: Path, media: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="demo-") as t:
        cut(raw, media, Path(t))


def cut(raw: Path, media: Path, tmp: Path) -> None:
    inputs: list[str] = []
    parts: list[str] = []
    for i, (name, a, b, _, _) in enumerate(BEATS):
        inputs += ["-i", str(clip(raw, name))]
        parts.append(f"[{i}:v]trim={a}:{b},setpts=PTS-STARTPTS,fps={FPS},"
                     f"scale=in_range=pc:out_range=tv:in_color_matrix=bt601:out_color_matrix=bt709,format=yuv420p,settb=1/{FPS}[v{i}]")
    # The xfade chain: each beat starts XFADE before the previous one ends.
    length = BEATS[0][2] - BEATS[0][1]
    starts = [0.0]
    last = "v0"
    for i in range(1, len(BEATS)):
        off = length - XFADE
        starts.append(off)
        parts.append(f"[{last}][v{i}]xfade=transition={BEATS[i - 1][3]}:duration={XFADE}:offset={off:.3f}[x{i}]")
        last = f"x{i}"
        length = off + BEATS[i][2] - BEATS[i][1]
    # Captions, on the final timeline, fading in and out.
    n = len(BEATS)
    for i, (_, a, _, _, caps) in enumerate(BEATS):
        for c0, c1, text in caps:
            png = tmp / f"cap{n}.png"
            caption(text, png)
            t0, t1 = starts[i] + c0 - a, starts[i] + c1 - a
            inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{length:.3f}", "-i", str(png)]
            parts.append(f"[{n}:v]format=rgba,fade=in:st={t0:.3f}:d=0.3:alpha=1,"
                         f"fade=out:st={t1 - 0.3:.3f}:d=0.3:alpha=1[c{n}]")
            parts.append(f"[{last}][c{n}]overlay=x=56:y=H-h-56:eof_action=pass:format=auto[o{n}]")
            last = f"o{n}"
            n += 1
    parts.append(f"[{last}]format=yuv420p[out]")
    graph = ";".join(parts)
    # Two-pass to the budget: the bitrate that fills it over the cut's length.
    rate = int(DEMO_BUDGET * 8 / length * 0.97)
    out = media / "demo.mp4"
    base = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[out]", "-an",
            "-c:v", "libx264", "-preset", "slow", "-tune", "animation", "-profile:v", "high",
            "-b:v", str(rate), "-maxrate", str(rate * 3), "-bufsize", str(rate * 4),
            "-g", str(FPS * 4), "-r", str(FPS), "-pix_fmt", "yuv420p",
            "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-passlogfile", str(tmp / "pass")]
    run(base + ["-pass", "1", "-f", "null", "/dev/null"])
    run(base + ["-pass", "2", "-movflags", "+faststart", str(out)])
    size = out.stat().st_size
    print(f"demo.mp4: {length:.1f} s, {size / 1024 / KB:.2f} MB, {rate // 1000} kb/s")
    if size > int(9.5 * 1024 * KB):
        raise SystemExit("video.py: demo.mp4 is over 9.5 MB")


def webp(src: list[str], vf: str, out: Path, limit: int, fps: int, qualities: tuple[int, ...]) -> None:
    """An animated WebP from SRC through VF, at the best quality under LIMIT bytes."""
    for q in qualities:
        run(["ffmpeg", "-v", "error", "-y", *src, "-vf", f"{vf},fps={fps}", "-an",
             "-c:v", "libwebp_anim", "-lossless", "0", "-quality", str(q), "-compression_level", "6",
             "-loop", "0", str(out)])
        if out.stat().st_size <= limit:
            print(f"{out.name}: q{q} at {fps} fps, {out.stat().st_size // KB} KB")
            return
    raise SystemExit(f"video.py: {out.name} does not fit {limit // KB} KB")


def hero(raw: Path, media: Path) -> None:
    name, a, b = HERO
    src = ["-i", str(clip(raw, name))]
    vf = f"trim={a}:{b},setpts=(PTS-STARTPTS)/{HERO_SPEED},scale=1280:720:flags=lanczos"
    webp(src, vf, media / "hero.webp", 4 * 1024 * KB, 24, (80, 72, 64, 56, 48))
    run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), *src, "-frames:v", "1", "-vf", "scale=1280:720:flags=lanczos",
         "-q:v", "2", str(media / "hero.jpg")])


def greeter(raw: Path, media: Path) -> None:
    name, a, b, (w, h, x, y) = GREETER
    vf = f"trim={a}:{b},setpts=PTS-STARTPTS,crop={w}:{h}:{x}:{y}"
    webp(["-i", str(clip(raw, name))], vf, media / "greeter.webp", 1536 * KB, 30, (85, 78, 70, 60))


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__.strip().splitlines()[2].strip())
    raw, media = Path(sys.argv[1]), Path(sys.argv[2])
    media.mkdir(parents=True, exist_ok=True)
    jobs = {"demo": demo, "hero": hero, "greeter": greeter}
    for job in sys.argv[3:] or list(jobs):
        if job not in jobs:
            raise SystemExit(f"video.py: unknown part {job}")
        jobs[job](raw, media)


if __name__ == "__main__":
    main()
