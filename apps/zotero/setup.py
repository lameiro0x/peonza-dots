#!/usr/bin/env python3
"""Set up Zotero's profile for Ryce: Better BibTeX and the theme plugin, nothing else.

    python3 apps/zotero/setup.py [--dry-run] [--home DIR] [--bbt-xpi FILE]

Zotero keeps its profile (settings, add-ons) in ~/.zotero/zotero/<random>.default/, named
by profiles.ini, and the library elsewhere (~/Zotero by default): this script only ever
writes inside the profile, and creates one, with profiles.ini, when Zotero never ran.

  - <profile>/user.js        a link to apps/zotero/user.js (lets profile add-ons start
                             enabled). A user.js this script did not write stops it.
  - extensions/better-bibtex@iris-advies.com.xpi
                             the release pinned in apps/zotero/better-bibtex.json,
                             downloaded (or --bbt-xpi, offline) and checked against its
                             sha256 before it lands. A newer one, from BBT's own updater,
                             is kept.
  - extensions/ryce@ryce-pc.xpi
                             apps/zotero/plugin, zipped: it follows the current Ryce theme
                             live (see its bootstrap.js), so no theme step is needed.

Idempotent; --dry-run says what it would do and writes nothing. Zotero must be closed: it
reads user.js and scans extensions/ only when it starts.
Exit: 0 done · 1 failed, the profile as it was · 2 bad usage · 3 Zotero is running.
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import io
import json
import os
import re
import secrets
import string
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
USER_JS = HERE / "user.js"
USER_JS_MARK = "// Ryce:"
PLUGIN = HERE / "plugin"
PLUGIN_ID = "ryce@ryce-pc"
PIN = json.loads((HERE / "better-bibtex.json").read_text(encoding="utf-8"))
DOWNLOAD_TIMEOUT = 120


class SetupError(Exception):
    pass


def say(msg: str) -> None:
    print(f"zotero-setup: {msg}")


# --- the profile -------------------------------------------------------------------------

def find_profile(root: Path) -> Path | None:
    """The profile Zotero starts with: the Default=1 one, or the only one."""
    ini = root / "profiles.ini"
    if not ini.is_file():
        return None
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read(ini, encoding="utf-8")
    except configparser.Error as e:
        raise SetupError(f"{ini} no se puede leer ({e}); arréglalo o bórralo con Zotero cerrado") from None
    profiles = [cp[s] for s in cp.sections() if s.lower().startswith("profile") and cp[s].get("path")]
    chosen = [p for p in profiles if p.get("default") == "1"] or (profiles if len(profiles) == 1 else [])
    if not profiles:
        return None
    if len(chosen) != 1:
        names = ", ".join(p["path"] for p in profiles)
        raise SetupError(f"{ini} tiene varios perfiles y ninguno por defecto ({names}); "
                         "elige uno en Zotero (zotero -P) y repite")
    p = chosen[0]
    path = root / p["path"] if p.get("isrelative", "1") == "1" else Path(p["path"])
    if not path.is_dir():
        raise SetupError(f"el perfil por defecto de {ini} no existe ({path}); abre Zotero una vez y repite")
    return path


def new_profile(root: Path) -> Path:
    name = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8)) + ".default"
    return root / name


def create_profile(profile: Path) -> None:
    profile.mkdir(mode=0o700, parents=True)
    write_atomic(profile.parent / "profiles.ini", (
        "[General]\nStartWithLastProfile=1\nVersion=2\n\n"
        f"[Profile0]\nName=default\nIsRelative=1\nPath={profile.name}\nDefault=1\n").encode())


def running_pid(profile: Path) -> int | None:
    """The pid in Gecko's `lock` link (host:+pid) when that process is alive."""
    try:
        m = re.search(r":\+(\d+)$", os.readlink(profile / "lock"))
    except OSError:
        return None
    if not m:
        return None
    try:
        os.kill(int(m.group(1)), 0)
    except ProcessLookupError:
        return None  # stale: Zotero crashed or the machine rebooted
    except PermissionError:
        pass         # alive, another user's
    return int(m.group(1))


# --- files ---------------------------------------------------------------------------------

def write_atomic(dst: Path, data: bytes) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, prefix=f".{dst.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, dst)
    except BaseException:
        os.unlink(tmp)
        raise


def user_js_is_ours(profile: Path) -> bool:
    """True when user.js already links here; False when it is missing or an older Ryce one;
    SetupError when it is someone else's, which is never overwritten."""
    dst = profile / "user.js"
    if dst.is_symlink():
        target = os.readlink(dst)
        if Path(target) == USER_JS:
            return True
        if not target.endswith("apps/zotero/user.js"):  # another Ryce checkout is still ours
            raise SetupError(f"{dst} apunta a {target}, que no es de Ryce; quítalo o fusiónalo con "
                             f"{USER_JS} a mano")
    elif dst.exists():
        if not dst.read_text(encoding="utf-8", errors="replace").startswith(USER_JS_MARK):
            raise SetupError(f"{dst} ya existe y no es de Ryce; fusiónalo con {USER_JS} a mano")
    return False


def link_user_js(profile: Path) -> None:
    tmp = profile / ".user.js.ryce-tmp"
    tmp.unlink(missing_ok=True)
    os.symlink(USER_JS, tmp)
    os.replace(tmp, profile / "user.js")


def xpi_version(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as z:
            return str(json.loads(z.read("manifest.json"))["version"])
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None


def version_key(v: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", v))


def fetch_bbt(local: Path | None) -> bytes:
    if local is not None:
        data = local.read_bytes()
    else:
        say(f"descargando {PIN['url']}")
        try:
            with urllib.request.urlopen(PIN["url"], timeout=DOWNLOAD_TIMEOUT) as r:
                data = r.read()
        except OSError as e:
            raise SetupError(f"no pude descargar Better BibTeX ({e}); ¿hay red? O pásalo con --bbt-xpi") from None
    got = hashlib.sha256(data).hexdigest()
    if got != PIN["sha256"]:
        raise SetupError(f"el xpi de Better BibTeX no es el fijado: sha256 {got}, se esperaba {PIN['sha256']} "
                         "(apps/zotero/better-bibtex.json); no se instala nada")
    return data


def bbt_outdated(profile: Path) -> str | None:
    """The installed BBT version ("—" if none) when the pin is newer; None when it is not."""
    have = xpi_version(profile / "extensions" / f"{PIN['id']}.xpi")
    if have and version_key(have) >= version_key(PIN["version"]):
        return None
    return have or "—"


def plugin_xpi() -> bytes:
    """apps/zotero/plugin zipped with fixed dates and order: same sources, same bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(p for p in PLUGIN.iterdir() if p.is_file()):
            info = zipfile.ZipInfo(f.name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, f.read_bytes())
    return buf.getvalue()


def install_plugin(profile: Path, dry: bool) -> None:
    dst = profile / "extensions" / f"{PLUGIN_ID}.xpi"
    data = plugin_xpi()
    if dst.is_file() and dst.read_bytes() == data:
        return
    say(f"plugin Ryce -> {dst}")
    if not dry:
        write_atomic(dst, data)


# --- main ----------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="setup.py", description="Zotero for Ryce: BBT and the theme plugin.")
    ap.add_argument("--dry-run", action="store_true", help="say what would change, write nothing")
    ap.add_argument("--home", type=Path, default=Path.home(), help="home directory (tests)")
    ap.add_argument("--bbt-xpi", type=Path, help="a downloaded Better BibTeX xpi (still sha256-checked)")
    args = ap.parse_args(argv)
    root = args.home / ".zotero" / "zotero"
    try:
        profile = find_profile(root)
        fresh = profile is None
        if fresh:
            profile = new_profile(root)
            say(f"perfil nuevo {profile} (Zotero no se ha abierto nunca aquí)")
        elif (pid := running_pid(profile)) is not None and not args.dry_run:
            say(f"Zotero está abierto con este perfil (pid {pid}); ciérralo y repite")
            return 3
        old_bbt = bbt_outdated(profile)
        link = not user_js_is_ours(profile)
        if link:
            say(f"user.js -> {USER_JS}")
        if old_bbt is not None:
            say(f"Better BibTeX {old_bbt} -> {PIN['version']}")
        if not args.dry_run:
            # Download and checksum before the first write: a failure leaves no trace.
            bbt = fetch_bbt(args.bbt_xpi) if old_bbt is not None else None
            if fresh:
                create_profile(profile)
            if link:
                link_user_js(profile)
            if bbt is not None:
                write_atomic(profile / "extensions" / f"{PIN['id']}.xpi", bbt)
        install_plugin(profile, args.dry_run)
    except (SetupError, OSError) as e:
        say(f"error: {e}")
        return 1
    say(f"listo: {profile}" + (" (simulado, nada escrito)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
