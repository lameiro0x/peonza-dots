#!/usr/bin/env python3
"""Give imported bookmarks their icons: merge favicons from another Chrome profile.

    python3 tools/chromium_favicons.py --dry-run     counts only, nothing written
    python3 tools/chromium_favicons.py               merge (Chromium must be closed)
        [--profile ~/.config/chromium/Default] [--source ~/mac-archive/browsers/chrome-Default/Favicons]

Bookmarks imported as a bare Bookmarks file arrive without icons; Chromium only fetches
one when the page is visited. The Mac's Chrome Favicons database already holds them.
For every bookmarked page (all roots, folders included) that has no icon here yet:
the icons the source maps to that exact page, else one icon of the same origin (scheme,
host and port), preferring the plain favicon and the one the origin's root page uses.
Bitmaps are copied with last_requested = 0, so Chromium treats them as ordinary icons
and never as on-demand ones its cleanup may drop. An icon URL already stored here is
reused, never duplicated.

Both databases must carry the same schema version (meta table). The merge is one
transaction after a full copy of the database (Favicons.ryce-<time>.bak beside it), and
it refuses to run while Chromium holds the profile (SingletonLock of a live process,
or a database Chromium keeps locked). Output is counts only: never a URL or a title.

Exit: 0 done · 2 bad input, nothing written · 3 Chromium is running, nothing written.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

HOME = Path.home()
PROFILE = HOME / ".config/chromium/Default"
SOURCE = HOME / "mac-archive/browsers/chrome-Default/Favicons"
FAVICON = 1          # favicon_base::IconType::kFavicon (2/4 touch icons, 8 web manifest)


class Refused(Exception):
    def __init__(self, msg: str, code: int) -> None:
        super().__init__(msg)
        self.code = code


def bookmarked(profile: Path) -> list[str]:
    """Every bookmarked URL, once, in tree order."""
    path = profile / "Bookmarks"
    try:
        roots = json.loads(path.read_text(encoding="utf-8"))["roots"]
    except (OSError, ValueError, KeyError) as e:
        raise Refused(f"no se pudo leer {path}: {e}", 2) from None
    seen: dict[str, None] = {}

    def walk(node: dict) -> None:
        if node.get("type") == "url" and node.get("url"):
            seen.setdefault(node["url"])
        for child in node.get("children", ()):
            walk(child)
    for node in roots.values():
        if isinstance(node, dict):
            walk(node)
    return list(seen)


def chromium_holds(user_data: Path) -> bool:
    """SingletonLock is a symlink to «<host>-<pid>» while Chromium runs. A lock from a
    dead process on this host is stale (a crash); one from another host is not ours to judge."""
    lock = user_data / "SingletonLock"
    try:
        target = os.readlink(lock)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    host, _, pid = target.rpartition("-")
    if host != socket.gethostname() or not pid.isdigit():
        return True
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def version(con: sqlite3.Connection, where: Path) -> str:
    try:
        row = con.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
        con.execute("SELECT page_url, icon_id, page_url_type FROM icon_mapping LIMIT 0")
        con.execute("SELECT icon_id, last_updated, image_data, width, height, last_requested"
                    " FROM favicon_bitmaps LIMIT 0")
    except sqlite3.DatabaseError as e:
        raise Refused(f"{where} no es una base de favicons de Chrome: {e}", 2) from None
    if not row:
        raise Refused(f"{where} no tiene versión en su tabla meta", 2)
    return str(row[0])


def origin(url: str) -> str | None:
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError:
        return None
    if not p.scheme or not p.hostname:
        return None
    return f"{p.scheme}://{p.hostname}" + (f":{port}" if port else "")


def plan(pages: list[str], dst: sqlite3.Connection, src: sqlite3.Connection) -> tuple[dict, dict[str, list[int]]]:
    """For each page without an icon here, the source icon ids to map to it."""
    counts = {"marcadores": len(pages), "ya tenían": 0, "exacto": 0, "mismo origen": 0, "sin icono": 0}
    by_origin: dict[str, list[tuple[str, int, int]]] = {}
    for page, icon, kind in src.execute("SELECT m.page_url, f.id, f.icon_type FROM icon_mapping m"
                                        " JOIN favicons f ON f.id = m.icon_id"
                                        " WHERE EXISTS (SELECT 1 FROM favicon_bitmaps b WHERE b.icon_id = f.id)"):
        if (o := origin(page)) is not None:
            by_origin.setdefault(o, []).append((page, icon, kind))
    todo: dict[str, list[int]] = {}
    for page in pages:
        if dst.execute("SELECT 1 FROM icon_mapping WHERE page_url = ? LIMIT 1", (page,)).fetchone():
            counts["ya tenían"] += 1
            continue
        o = origin(page)
        rows = by_origin.get(o, []) if o else []
        exact = sorted({icon for p, icon, _ in rows if p == page})
        if exact:
            todo[page] = exact
            counts["exacto"] += 1
        elif rows:
            uses: dict[int, int] = {}
            for _, icon, _ in rows:
                uses[icon] = uses.get(icon, 0) + 1
            root = {icon for p, icon, _ in rows if p.rstrip("/") == o}
            best = max(rows, key=lambda r: (r[2] == FAVICON, r[1] in root, uses[r[1]], -r[1]))
            todo[page] = [best[1]]
            counts["mismo origen"] += 1
        else:
            counts["sin icono"] += 1
    return counts, todo


def apply(todo: dict[str, list[int]], dst: sqlite3.Connection, src: sqlite3.Connection) -> dict:
    copied: dict[int, int] = {}      # source icon id -> id here
    stats = {"iconos nuevos": 0, "mapas nuevos": 0}
    for page, icons in todo.items():
        for sid in icons:
            if sid not in copied:
                url, kind = src.execute("SELECT url, icon_type FROM favicons WHERE id = ?", (sid,)).fetchone()
                row = dst.execute("SELECT id FROM favicons WHERE url = ? AND icon_type = ?", (url, kind)).fetchone()
                if row and dst.execute("SELECT 1 FROM favicon_bitmaps WHERE icon_id = ?", (row[0],)).fetchone():
                    copied[sid] = row[0]
                else:
                    did = row[0] if row else dst.execute(
                        "INSERT INTO favicons(url, icon_type) VALUES (?, ?)", (url, kind)).lastrowid
                    dst.executemany(
                        "INSERT INTO favicon_bitmaps(icon_id, last_updated, image_data, width, height, last_requested)"
                        " VALUES (?, ?, ?, ?, ?, 0)",
                        [(did, *b) for b in src.execute(
                            "SELECT last_updated, image_data, width, height FROM favicon_bitmaps WHERE icon_id = ?",
                            (sid,))])
                    copied[sid] = did
                    stats["iconos nuevos"] += 1
            dst.execute("INSERT INTO icon_mapping(page_url, icon_id, page_url_type) VALUES (?, ?, 0)",
                        (page, copied[sid]))
            stats["mapas nuevos"] += 1
    return stats


def backup(db: Path) -> Path:
    """A byte copy taken while this process holds the exclusive lock: in rollback-journal
    mode the file is then complete and nobody else can write it (sqlite's backup API would
    wait on our own lock forever)."""
    out = db.with_name(f"{db.name}.ryce-{time.strftime('%Y%m%d-%H%M%S')}.bak")
    if out.exists():
        raise Refused(f"ya existe {out}; espera un segundo y repite", 2)
    shutil.copyfile(db, out)
    os.chmod(out, 0o600)
    return out


def run(profile: Path, source: Path, dry: bool) -> int:
    if not dry and chromium_holds(profile.parent):
        raise Refused("Chromium está abierto con este perfil: ciérralo (todas sus ventanas) y repite", 3)
    db = profile / "Favicons"
    for p in (db, source):
        if not p.is_file():
            raise Refused(f"no existe {p}", 2)
    pages = bookmarked(profile)
    src = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True, timeout=1)
    dst = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True, timeout=1) if dry else \
        sqlite3.connect(db, timeout=1, isolation_level=None)
    try:
        vs, vd = version(src, source), version(dst, db)
        if vs != vd:
            raise Refused(f"esquemas distintos: origen versión {vs}, Chromium versión {vd}", 2)
        if not dry:
            if dst.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal":
                raise Refused(f"{db} está en modo WAL: la copia previa no sería fiable", 2)
            try:
                dst.execute("BEGIN EXCLUSIVE")
            except sqlite3.OperationalError as e:
                raise Refused(f"la base de favicons está bloqueada ({e}): ¿Chromium sigue abierto?", 3) from None
        counts, todo = plan(pages, dst, src)
        for k, v in counts.items():
            print(f"{k}: {v}")
        if dry:
            print("(simulación: no se ha escrito nada)")
            return 0
        if not todo:
            dst.execute("ROLLBACK")
            print("nada que añadir")
            return 0
        try:
            saved = backup(db)
            stats = apply(todo, dst, src)
            dst.execute("COMMIT")
        except BaseException:
            dst.execute("ROLLBACK")
            raise
        for k, v in stats.items():
            print(f"{k}: {v}")
        print(f"copia previa: {saved}")
        return 0
    except sqlite3.DatabaseError as e:
        raise Refused(f"error de SQLite: {e}", 2) from None
    finally:
        src.close()
        dst.close()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--profile", type=Path, default=PROFILE, help="perfil de Chromium (carpeta Default)")
    ap.add_argument("--source", type=Path, default=SOURCE, help="Favicons del Chrome de origen")
    ap.add_argument("--dry-run", action="store_true", help="solo contar")
    a = ap.parse_args(argv)
    try:
        return run(a.profile.expanduser(), a.source.expanduser(), a.dry_run)
    except Refused as e:
        print(f"chromium_favicons: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
