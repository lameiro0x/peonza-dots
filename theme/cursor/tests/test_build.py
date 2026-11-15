"""theme/cursor/build.py and the committed assets/cursors/ryce-peonza: names, hotspots,
visibility on every ground, and the real libraries (libXcursor, libhyprcursor) loading it."""
import ctypes
import ctypes.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build  # noqa: E402

THEME = build.OUT
CURSORS = THEME / "cursors"
BRAND = Path(os.environ.get("PEONZA_BRAND", Path.home() / "Repos" / "logo-peonza" / "brand" / "mark")).parents[1]
CAPITAINE = Path("/usr/share/icons/capitaine-cursors/cursors")
# cursor-shape-v1 (wayland-protocols staging/cursor-shape), as compositors name them: CSS names.
SHAPE_V1 = """default context-menu help pointer progress wait cell crosshair text vertical-text alias copy
move no-drop not-allowed grab grabbing e-resize n-resize ne-resize nw-resize s-resize se-resize
sw-resize w-resize ew-resize ns-resize nesw-resize nwse-resize col-resize row-resize all-scroll
zoom-in zoom-out dnd-ask all-resize""".split()
# capitaine names drawn by nobody here: index.theme's Inherits=Adwaita answers them.
INHERITED = {"color-picker", "pencil", "draft", "pirate", "up-arrow", "down-arrow", "left-arrow", "right-arrow"}
GROUNDS = [g for _, g in build.GROUNDS]


def luminance(rgb):
    c = np.asarray(rgb, np.float64) / 255
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c @ [0.2126, 0.7152, 0.0722]


def over(pm, ground):
    """A premultiplied RGBA array composited over a flat ground."""
    a = pm[..., 3:4].astype(np.float64) / 255
    return pm[..., :3] + np.array(ground, np.float64) * (1 - a)


class Committed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {n: build.read_xcursor((CURSORS / n).read_bytes()) for n in build.SHAPES}

    def test_every_wayland_shape_resolves(self):
        overrides = {a for names in build.ALIASES.values() for a in names}
        for name in SHAPE_V1:
            self.assertTrue((CURSORS / name).is_file(), f"cursors/{name}")
            self.assertTrue(name in build.SHAPES or name in overrides, name)

    def test_aliases_are_copies_of_drawn_files(self):
        seen = set()
        for base, names in build.ALIASES.items():
            self.assertIn(base, build.SHAPES)
            for a in names:
                self.assertNotIn(a, build.SHAPES)
                self.assertNotIn(a, seen, f"{a} aliased twice")
                seen.add(a)
                self.assertFalse((CURSORS / a).is_symlink(), a)
                self.assertEqual((CURSORS / a).read_bytes(), (CURSORS / base).read_bytes(), a)

    @unittest.skipUnless(CAPITAINE.is_dir(), "capitaine-cursors not installed")
    def test_capitaine_names_are_covered(self):
        ours = set(build.SHAPES) | {a for names in build.ALIASES.values() for a in names}
        self.assertEqual(sorted({p.name for p in CAPITAINE.iterdir()} - ours - INHERITED), [])

    def test_sizes_frames_and_hotspots(self):
        for name, images in self.files.items():
            frames = len(build.SHAPES[name][0])
            self.assertEqual([i[0] for i in images], [s for s in build.SIZES for _ in range(frames)], name)
            for nominal, px, xhot, yhot, delay in images:
                self.assertEqual(px.shape, (nominal, nominal, 4))
                self.assertEqual((xhot, yhot), build.hotspot(name, nominal), name)
                self.assertEqual(delay, build.DELAY if frames > 1 else 0)
                hx, hy = build.SHAPES[name][1]
                self.assertEqual((hx * 8 % 1, hy * 8 % 1), (0, 0), f"{name}: hotspot off the 1/8 grid")

    def test_animations_move(self):
        for name in ("progress", "wait"):
            frames = [px for s, px, *_ in self.files[name] if s == 32]
            self.assertGreater(len(frames), 8)
            changed = sum(int(np.abs(a.astype(int) - b).max() > 40) for a, b in zip(frames, frames[1:]))
            self.assertEqual(changed, len(frames) - 1, f"{name}: a frame repeats the previous one")

    def test_the_pointer_tip_is_the_hotspot(self):
        """The top points up-left: the film-black pixel furthest up-left (least x + y) is the
        hotspot and no other, nothing drawn leads it but the tip's own outline, and the body
        lies down and to the right of it (the user saw it upside down when the tall grip
        trailed as a second, longer point)."""
        for name in ("default", "progress", "help", "copy", "alias", "no-drop", "context-menu"):
            for nominal, px, xhot, yhot, _ in self.files[name]:
                at = (name, nominal)
                ink = px[..., 3] >= 128            # the drawing, not its shadow
                fill = ink & (px[..., :3].max(axis=-1) < 100)
                fy, fx = np.nonzero(fill)
                lead = fx + fy == (fx + fy).min()
                self.assertEqual(list(zip(fx[lead], fy[lead])), [(xhot, yhot)], at)
                ys, xs = np.nonzero(ink)
                ahead = xs + ys < xhot + yhot
                outline = build.OUTLINE * nominal
                self.assertLessEqual(np.hypot(xs[ahead] - xhot, ys[ahead] - yhot).max(), outline + 1, at)
                self.assertGreater(xs.mean() - xhot, nominal / 8, at)
                self.assertGreater(ys.mean() - yhot, nominal / 8, at)

    def test_nothing_is_cut_by_the_canvas(self):
        for name, images in self.files.items():
            for nominal, px, *_ in images:
                a = px[..., 3]
                edge = max(a[0].max(), a[-1].max(), a[:, 0].max(), a[:, -1].max())
                self.assertLess(edge, 128, (name, nominal))

    def test_visible_on_every_ground(self):
        """On every ground, the fill or the outline meets WCAG 1.4.11's 3:1 for non-text UI
        over a fifth of the cursor at least, the pointer over 30 % (capitaine-cursors-light,
        the cursor the user lost on Ola's sage, covers 23 % there at 24 px)."""
        for name, images in self.files.items():
            for nominal, px, *_ in images:
                ink = px[..., 3] >= 200            # the drawing, not its shadow
                floor = 0.3 if name == "default" else 0.2
                for g in GROUNDS:
                    lum, ground = luminance(over(px, g)), luminance(g)
                    ratio = (np.maximum(lum, ground) + 0.05) / (np.minimum(lum, ground) + 0.05)
                    self.assertGreater((ratio[ink] >= 3).mean(), floor, (name, nominal, g))

    def test_index_and_manifest_name_the_theme(self):
        self.assertIn("Name=ryce-peonza\n", (THEME / "index.theme").read_text())
        self.assertIn("name = ryce-peonza\n", (THEME / "manifest.hl").read_text())
        self.assertEqual(sorted(p.stem for p in (THEME / "hyprcursors").glob("*.hlc")), sorted(build.SHAPES))


class Generator(unittest.TestCase):
    def test_committed_theme_is_fresh(self):
        self.assertEqual(build.check(build.build_all()), [])

    def test_check_names_a_stale_and_a_stray_file(self):
        drawn = {n: build.frames_of(n) for n in ("default", "wait")}
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        out = tmp / "ryce-peonza"
        shutil.copytree(THEME, out)
        old = build.OUT, build.SHAPES, build.ALIASES, build.ROOT
        self.addCleanup(lambda: [setattr(build, k, v) for k, v in zip(("OUT", "SHAPES", "ALIASES", "ROOT"), old)])
        build.OUT, build.ROOT = out, tmp
        build.SHAPES = {n: old[1][n] for n in drawn}
        build.ALIASES = {n: old[2].get(n, ()) for n in drawn}
        for p in (out / "cursors").iterdir():
            if p.name not in drawn and p.name not in build.ALIASES["default"] + build.ALIASES["wait"]:
                p.unlink()
        for p in (out / "hyprcursors").iterdir():
            if p.stem not in drawn:
                p.unlink()
        self.assertEqual(build.check(drawn), [])
        data = bytearray((out / "cursors" / "default").read_bytes())
        data[-200] ^= 0xFF
        (out / "cursors" / "default").write_bytes(bytes(data))
        (out / "cursors" / "extra").write_bytes(b"")
        bad = build.check(drawn)
        self.assertIn("stale: ryce-peonza/cursors/default", bad)
        self.assertIn("stray: ryce-peonza/cursors/extra", bad)
        (out / "cursors" / "left_ptr").unlink()
        (out / "cursors" / "left_ptr").symlink_to("default")
        self.assertIn("stale: ryce-peonza/cursors/left_ptr is a link, should be a file", build.check(drawn))

    def test_the_pointer_leads_with_its_tip_not_its_grip(self):
        """Along the axis, the tip stands further off the disc than the grip and its knob:
        the one long, sharp end is the leading one (the measured top, turned over, trailed
        a grip longer than its tip and read as pointing down-right)."""
        top = build.Top(build.HOT, build.REACH, build.TILT, build.LOOK, point=build.POINT, grip=build.GRIP)
        tip_out = top.lift(build.PROFILE["rimBot"])
        grip_out = top.lift(1) - top.lift(build.PROFILE["rimTop"]) + build.KNOB
        self.assertGreater(tip_out, 2 * grip_out)

    def test_xcursor_round_trip(self):
        img = build.render(build.SHAPES["default"][0][0], 24)
        (nominal, px, xhot, yhot, delay), = build.read_xcursor(build.xcursor([(24, img, 3, 3, 0)]))
        self.assertEqual((nominal, xhot, yhot, delay), (24, 3, 3, 0))
        a = np.asarray(img, np.int32)
        self.assertTrue(np.array_equal(px[..., 3], a[..., 3]))
        self.assertLessEqual(np.abs(px[..., :3] - (a[..., :3] * a[..., 3:] + 127) // 255).max(), 0)

    @unittest.skipUnless((BRAND / "src" / "geometry.mjs").exists(), "logo-peonza not here (PEONZA_BRAND)")
    def test_profile_is_the_brand_profile(self):
        text = (BRAND / "src" / "geometry.mjs").read_text()
        block = re.search(r"export const PROFILE = \{(.*?)\};", text, re.S).group(1)
        brand = {}
        for key, val in re.findall(r"(\w+):\s*(\[[^\]]*\]|[\d.]+)", block):
            nums = [float(v) for v in re.findall(r"[\d.]+", val)]
            brand[key] = tuple(nums) if val.startswith("[") else nums[0]
        self.assertEqual(brand, {k: (tuple(v) if isinstance(v, tuple) else v) for k, v in build.PROFILE.items()})


class RealLibraries(unittest.TestCase):
    """The theme as the readers on this machine see it."""

    @unittest.skipUnless(ctypes.util.find_library("Xcursor"), "libXcursor missing")
    def test_libxcursor_resolves_every_name(self):
        class Image(ctypes.Structure):
            _fields_ = [("version", ctypes.c_uint), ("size", ctypes.c_uint), ("width", ctypes.c_uint),
                        ("height", ctypes.c_uint), ("xhot", ctypes.c_uint), ("yhot", ctypes.c_uint),
                        ("delay", ctypes.c_uint), ("pixels", ctypes.c_void_p)]

        class Images(ctypes.Structure):
            _fields_ = [("nimage", ctypes.c_int), ("images", ctypes.POINTER(ctypes.POINTER(Image))),
                        ("name", ctypes.c_char_p)]

        lib = ctypes.CDLL(ctypes.util.find_library("Xcursor"))
        lib.XcursorLibraryLoadImages.restype = ctypes.POINTER(Images)
        lib.XcursorLibraryLoadImages.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        lib.XcursorImagesDestroy.argtypes = [ctypes.POINTER(Images)]
        old = os.environ.get("XCURSOR_PATH")
        os.environ["XCURSOR_PATH"] = str(THEME.parent)
        self.addCleanup(lambda: os.environ.__setitem__("XCURSOR_PATH", old) if old is not None
                        else os.environ.pop("XCURSOR_PATH", None))
        base_of = {a: b for b, names in build.ALIASES.items() for a in names}
        for name in SHAPE_V1 + ["left_ptr", "xterm", "hand2", "watch", "sb_h_double_arrow"]:
            imgs = lib.XcursorLibraryLoadImages(name.encode(), b"ryce-peonza", 32)
            self.assertTrue(imgs, name)
            base = base_of.get(name, name)
            self.assertEqual(imgs.contents.nimage, len(build.SHAPES[base][0]), name)
            first = imgs.contents.images[0].contents
            self.assertEqual((first.size, first.xhot, first.yhot), (32, *build.hotspot(base, 32)), name)
            lib.XcursorImagesDestroy(imgs)

    @unittest.skipUnless(ctypes.util.find_library("hyprcursor"), "libhyprcursor missing")
    def test_libhyprcursor_loads_a_deployed_copy(self):
        # Deployed the way install/links.tsv does it: real folders, one link per file.
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        dest = tmp / "icons" / "ryce-peonza"
        for p in THEME.rglob("*"):
            if p.is_dir():
                continue
            (dest / p.relative_to(THEME)).parent.mkdir(parents=True, exist_ok=True)
            (dest / p.relative_to(THEME)).symlink_to(p)
        probe = Path(__file__).with_name("hyprcursor_probe.py")
        r = subprocess.run([sys.executable, str(probe), "32", "default", "left_ptr", "progress", "wait", "hand2",
                            "sb_h_double_arrow", "nesw-resize", "text"],
                           env={**os.environ, "XDG_DATA_HOME": str(tmp), "XDG_DATA_DIRS": str(tmp)},
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        base_of = {a: b for b, names in build.ALIASES.items() for a in names}
        got = dict(line.split(" ", 1) for line in r.stdout.splitlines())
        for name, value in got.items():
            base = base_of.get(name, name)
            n, hx, hy = map(int, value.split())
            self.assertEqual((n, hx, hy), (len(build.SHAPES[base][0]), *build.hotspot(base, 32)), name)
        self.assertEqual(len(got), 8, r.stdout)


if __name__ == "__main__":
    unittest.main()
