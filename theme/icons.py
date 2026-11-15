#!/usr/bin/env python3
"""Build the icon themes ryce-<id>: Papirus-Dark (Papirus-Light on a paper theme) with
folders in the theme's greys.

Papirus draws every folder with two inline blues (#5294e2 front, #4877b1 back) and
points folder.svg, user-home.svg and the rest at folder-blue*.svg. Each ryce-<id>
ships recoloured copies of exactly those places icons and inherits its Papirus base for
everything else. GTK caches an icon theme by NAME, so a theme switch changes the
name (gsettings icon-theme ryce-<id>); a theme already in use is never rewritten in
place: a changed build lands beside it and replaces it with a rename.

    python3 theme/icons.py                      build into ~/.local/share/icons
    python3 theme/icons.py --dest DIR           build into DIR
    python3 theme/icons.py --check [--dest DIR] build into DIR (default: a temp dir),
                                                then verify it: every folder name of
                                                Papirus present, no Papirus blue left
    --src DIR                                   the Papirus to read for every theme (tests)
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from colormath import over  # noqa: E402
from tokens import ThemeError, load_all, scheme  # noqa: E402

# Light-on-dark symbolic icons for a dark ground, dark-on-light for paper (tokens.scheme).
PAPIRUS = {"dark": Path("/usr/share/icons/Papirus-Dark"), "light": Path("/usr/share/icons/Papirus-Light")}
DEFAULT_DEST = Path.home() / ".local" / "share" / "icons"
STAMP = ".ryce-icons.sha256"
BLUE_FILE = re.compile(r"folder-blue(-[a-z0-9-]+)?\.svg")
PLACES_DIR = re.compile(r"\d+x\d+(@2x)?/places")
# Papirus' folder colours, the paper sheet and the emblem glyph drawn on the front.
FRONT, BACK, PAPER, GLYPH = "#5294e2", "#4877b1", "#e4e4e4", "#1d344f"

Plan = dict[str, tuple[str, bytes]]   # rel path -> ("file", bytes) | ("link", target)


class IconError(Exception):
    pass


def recolour(svg: str, t: dict) -> str:
    d, c = t["desktop"], t["colors"]
    swap = {FRONT: d["folder"], BACK: d["folder_dark"], PAPER: c["fg1"],
            GLYPH: over(d["folder_dark"], 0.5, c["bg0"])}
    return re.sub("|".join(swap), lambda m: swap[m.group(0).lower()], svg, flags=re.I)


def papirus_index(src: Path) -> configparser.ConfigParser:
    ini = configparser.ConfigParser(interpolation=None, strict=False)
    ini.optionxform = str  # type: ignore[assignment,method-assign]
    try:
        ini.read_string((src / "index.theme").read_text(encoding="utf-8"))
    except OSError as e:
        raise IconError(f"cannot read {src}/index.theme ({e.strerror}); install papirus-icon-theme") from None
    if not ini.has_section("Icon Theme"):
        raise IconError(f"{src}/index.theme has no [Icon Theme] section")
    return ini


def places_dirs(ini: configparser.ConfigParser, key: str) -> list[str]:
    return [d for d in ini["Icon Theme"].get(key, "").split(",") if PLACES_DIR.fullmatch(d)]


def plan(t: dict, src: Path) -> Plan:
    """Every file and symlink of ryce-<id>, keyed by path relative to the theme dir."""
    ini = papirus_index(src)
    parent = PAPIRUS[scheme(t)].name
    plain, scaled = places_dirs(ini, "Directories"), places_dirs(ini, "ScaledDirectories")
    out: Plan = {}
    for d in plain + scaled:
        size = d.split("/")[0]
        base = size.removesuffix("@2x")
        if base != size and (src / size).is_symlink() and os.readlink(src / size) == base:
            out[size] = ("link", base.encode())       # 16x16@2x -> 16x16, like Papirus
            continue
        here = src / d
        if not here.is_dir():
            continue
        for f in sorted(here.iterdir()):
            if f.suffix != ".svg":
                continue
            real = f.resolve()
            if real.parent != here.resolve() or not BLUE_FILE.fullmatch(real.name):
                continue
            rel = f"{d}/{f.name}"
            if f.is_symlink():
                out[rel] = ("link", real.name.encode())   # flatten folder_man -> folder-documents -> …
            else:
                out[rel] = ("file", recolour(f.read_text(encoding="utf-8"), t).encode())
    if not any(k == "file" for k, _ in out.values()):
        raise IconError(f"{src}: no folder-blue*.svg under any places dir; is it Papirus-Dark?")
    shipped = {r.rsplit("/", 1)[0] for r in out if "/" in r}
    dirs = [d for d in plain if d in shipped]
    scaled_dirs = [d for d in scaled if d in shipped or d.split("/")[0] in out]
    lines = ["[Icon Theme]", f"Name=Ryce {t['name']}",
             f"Comment={parent} with folders in the {t['name']} greys (ryce-pc theme/icons.py)",
             f"Inherits={parent}", "Example=folder",
             "Directories=" + ",".join(dirs), "ScaledDirectories=" + ",".join(scaled_dirs), ""]
    for d in dirs + scaled_dirs:
        if not ini.has_section(d):
            raise IconError(f"{src}/index.theme lists {d} but has no [{d}] section")
        lines += [f"[{d}]", *(f"{k}={v}" for k, v in ini[d].items()), ""]
    out["index.theme"] = ("file", "\n".join(lines).encode())
    return dict(sorted(out.items()))


def digest(p: Plan) -> str:
    h = hashlib.sha256()
    for rel, (kind, data) in p.items():
        h.update(f"{rel}\0{kind}\0".encode() + data + b"\0")
    return h.hexdigest()


def write_tree(p: Plan, root: Path) -> None:
    for rel, (kind, data) in p.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "link":
            os.symlink(data.decode(), path)
        else:
            path.write_bytes(data)
            path.chmod(0o644)


def install(tid: str, p: Plan, dest: Path) -> bool:
    """Put ryce-<tid> under dest; False when the installed one is already this build."""
    final = dest / f"ryce-{tid}"
    want = digest(p)
    try:
        if (final / STAMP).read_text(encoding="utf-8").strip() == want:
            return False
    except OSError:
        pass
    dest.mkdir(parents=True, exist_ok=True)
    new = Path(tempfile.mkdtemp(prefix=f".ryce-{tid}.", dir=dest))
    try:
        write_tree(p, new)
        if shutil.which("gtk-update-icon-cache"):
            r = subprocess.run(["gtk-update-icon-cache", "-q", "-f", "-t", str(new)],
                               capture_output=True, text=True, timeout=120)
            if r.returncode:
                raise IconError(f"gtk-update-icon-cache {new}: {r.stderr.strip() or r.returncode}")
        (new / STAMP).write_text(want + "\n", encoding="utf-8")
        new.chmod(0o755)
        old = dest / f".ryce-{tid}.old"
        shutil.rmtree(old, ignore_errors=True)
        if final.exists():
            final.rename(old)
        new.rename(final)
        shutil.rmtree(old, ignore_errors=True)
    except BaseException:
        shutil.rmtree(new, ignore_errors=True)
        raise
    return True


def verify(tid: str, p: Plan, dest: Path, src: Path) -> list[str]:
    root, bad = dest / f"ryce-{tid}", []
    for rel, (kind, data) in p.items():
        path = root / rel
        if kind == "link":
            if os.readlink(path) != data.decode():
                bad.append(f"{path}: link points at {os.readlink(path)}, want {data.decode()}")
        elif path.read_bytes() != data:
            bad.append(f"{path}: differs from the build")
        if kind == "file" and rel.endswith(".svg") and re.search(f"{FRONT}|{BACK}", data.decode(), re.I):
            bad.append(f"{path}: a Papirus blue survived the recolour")
        if rel.endswith(".svg") and not path.resolve().is_file():
            bad.append(f"{path}: dangling")
    for d in places_dirs(papirus_index(src), "Directories"):
        here = src / d
        names = {f.name for f in here.iterdir() if BLUE_FILE.fullmatch(f.resolve().name)
                 and f.resolve().parent == here.resolve()} if here.is_dir() else set()
        missing = sorted(n for n in names if f"{d}/{n}" not in p)
        if missing:
            bad.append(f"{root}/{d}: missing {', '.join(missing[:5])}")
    return bad


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dest", type=Path)
    ap.add_argument("--src", type=Path, help="one Papirus for every theme (default: by scheme)")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    try:
        themes = load_all()
        srcs = {tid: a.src or PAPIRUS[scheme(t)] for tid, t in themes.items()}
        plans = {tid: plan(t, srcs[tid]) for tid, t in themes.items()}
        scratch = tempfile.TemporaryDirectory(prefix="ryce-icons.") if a.check and not a.dest else None
        dest = a.dest or (Path(scratch.name) if scratch else DEFAULT_DEST)
        changed = [tid for tid, p in plans.items() if install(tid, p, dest)]
        if a.check:
            bad = [b for tid, p in plans.items() for b in verify(tid, p, dest, srcs[tid])]
            if scratch:
                scratch.cleanup()
            for b in bad:
                print(b)
            if bad:
                return 1
            n = sum(r.endswith(".svg") and k == "file" for r, (k, _) in next(iter(plans.values())).items())
            print(f"icons: ok ({len(plans)} themes x {n} recoloured files in {'a scratch dir' if scratch else dest})")
        elif changed:
            print(f"icons: built {', '.join(f'ryce-{t}' for t in changed)} in {dest}")
    except (IconError, ThemeError) as e:
        print(f"icons: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"icons: {e.filename}: {e.strerror}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
