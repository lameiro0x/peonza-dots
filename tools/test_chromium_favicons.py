#!/usr/bin/env python3
"""Tests for tools/chromium_favicons.py on synthetic profiles (never a real one).

    python3 -m unittest discover -s tools -p 'test_chromium_favicons.py'
"""
from __future__ import annotations

import io
import json
import os
import socket
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chromium_favicons as cf  # noqa: E402

SCHEMA = """
CREATE TABLE meta(key LONGVARCHAR NOT NULL UNIQUE PRIMARY KEY, value LONGVARCHAR);
CREATE TABLE icon_mapping(id INTEGER PRIMARY KEY,page_url LONGVARCHAR NOT NULL,icon_id INTEGER,page_url_type INTEGER DEFAULT 0);
CREATE TABLE favicons(id INTEGER PRIMARY KEY,url LONGVARCHAR NOT NULL,icon_type INTEGER DEFAULT 1);
CREATE TABLE favicon_bitmaps(id INTEGER PRIMARY KEY,icon_id INTEGER NOT NULL,last_updated INTEGER DEFAULT 0,image_data BLOB,width INTEGER DEFAULT 0,height INTEGER DEFAULT 0,last_requested INTEGER DEFAULT 0);
"""


def make_db(path: Path, version: int = 9, icons: list[tuple] = ()) -> None:
    """icons: (page_url, icon_url, icon_type, [(width, data, last_requested)])."""
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO meta VALUES (?, ?)",
                    [("version", str(version)), ("last_compatible_version", str(version))])
    for page, icon, kind, bitmaps in icons:
        row = con.execute("SELECT id FROM favicons WHERE url = ? AND icon_type = ?", (icon, kind)).fetchone()
        if row:
            iid = row[0]
        else:
            iid = con.execute("INSERT INTO favicons(url, icon_type) VALUES (?, ?)", (icon, kind)).lastrowid
            for w, data, req in bitmaps:
                con.execute("INSERT INTO favicon_bitmaps(icon_id, last_updated, image_data, width, height,"
                            " last_requested) VALUES (?, 13300000000000000, ?, ?, ?, ?)", (iid, data, w, w, req))
        con.execute("INSERT INTO icon_mapping(page_url, icon_id) VALUES (?, ?)", (page, iid))
    con.commit()
    con.close()


def bookmarks(urls: list[str], folder: list[str] = ()) -> dict:
    node = lambda u: {"type": "url", "url": u, "name": "x"}  # noqa: E731
    return {"roots": {
        "bookmark_bar": {"type": "folder", "children": [node(u) for u in urls] +
                         [{"type": "folder", "children": [node(u) for u in folder]}]},
        "other": {"type": "folder", "children": []},
        "synced": {"type": "folder", "children": []},
    }, "version": 1}


def icon_of(db: Path, page: str) -> list[tuple]:
    con = sqlite3.connect(db)
    rows = con.execute("SELECT f.url, f.icon_type, b.width, b.image_data, b.last_requested FROM icon_mapping m"
                       " JOIN favicons f ON f.id = m.icon_id JOIN favicon_bitmaps b ON b.icon_id = f.id"
                       " WHERE m.page_url = ? ORDER BY b.width", (page,)).fetchall()
    con.close()
    return rows


class Merge(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ryce-fav-"))
        self.profile = self.tmp / "chromium" / "Default"
        self.profile.mkdir(parents=True)
        self.src = self.tmp / "mac-Favicons"

    def run_tool(self, *extra: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = cf.main(["--profile", str(self.profile), "--source", str(self.src), *extra])
        return code, out.getvalue()

    def setup_case(self, marks: list[str], folder: list[str] = ()) -> None:
        (self.profile / "Bookmarks").write_text(json.dumps(bookmarks(marks, folder)), encoding="utf-8")
        make_db(self.profile / "Favicons", icons=[
            ("https://has.example/", "https://has.example/own.ico", 1, [(16, b"OWN", 0)]),
        ])
        make_db(self.src, icons=[
            ("https://exact.example/a", "https://exact.example/fav.ico", 1, [(16, b"E16", 0), (32, b"E32", 99)]),
            ("https://site.example/", "https://site.example/touch.png", 2, [(180, b"TOUCH", 0)]),
            ("https://site.example/other", "https://site.example/root.png", 1, [(16, b"ROOT", 0)]),
            ("https://multi.example/a", "https://multi.example/a.ico", 1, [(16, b"A", 0)]),
            ("https://multi.example/b", "https://multi.example/a.ico", 1, [(16, b"A", 0)]),
            ("https://multi.example/", "https://multi.example/root.ico", 1, [(16, b"MROOT", 0)]),
            ("https://has.example/", "https://has.example/mac.ico", 1, [(16, b"MAC", 0)]),
            ("http://plain.example/x", "http://plain.example/p.ico", 1, [(16, b"P", 0)]),
        ])

    def test_exact_page_icon_is_copied_with_every_bitmap(self) -> None:
        self.setup_case(["https://exact.example/a"])
        code, _ = self.run_tool()
        self.assertEqual(code, 0)
        rows = icon_of(self.profile / "Favicons", "https://exact.example/a")
        self.assertEqual([(r[0], r[2], r[3]) for r in rows],
                         [("https://exact.example/fav.ico", 16, b"E16"), ("https://exact.example/fav.ico", 32, b"E32")])
        # An on-demand stamp would let Chromium's cleanup drop the icon again.
        self.assertTrue(all(r[4] == 0 for r in rows))

    def test_same_origin_falls_back_to_the_plain_favicon(self) -> None:
        self.setup_case(["https://site.example/deep/page?q=1"], folder=[])
        self.run_tool()
        rows = icon_of(self.profile / "Favicons", "https://site.example/deep/page?q=1")
        self.assertEqual([(r[0], r[1], r[3]) for r in rows], [("https://site.example/root.png", 1, b"ROOT")])

    def test_the_root_pages_favicon_wins_over_the_most_used(self) -> None:
        self.setup_case(["https://multi.example/c"])
        self.run_tool()
        rows = icon_of(self.profile / "Favicons", "https://multi.example/c")
        self.assertEqual([r[3] for r in rows], [b"MROOT"])

    def test_another_scheme_is_not_the_same_origin(self) -> None:
        self.setup_case(["https://plain.example/x"])
        _, out = self.run_tool()
        self.assertEqual(icon_of(self.profile / "Favicons", "https://plain.example/x"), [])
        self.assertIn("sin icono: 1", out)

    def test_a_page_that_already_has_an_icon_keeps_it(self) -> None:
        self.setup_case(["https://has.example/"])
        self.run_tool()
        rows = icon_of(self.profile / "Favicons", "https://has.example/")
        self.assertEqual([r[3] for r in rows], [b"OWN"])

    def test_bookmarks_inside_folders_count_and_duplicates_once(self) -> None:
        self.setup_case(["https://exact.example/a", "https://exact.example/a"], folder=["https://site.example/z"])
        _, out = self.run_tool()
        self.assertIn("marcadores: 2", out)
        self.assertEqual(len(icon_of(self.profile / "Favicons", "https://site.example/z")), 1)

    def test_an_icon_shared_by_two_pages_is_stored_once(self) -> None:
        self.setup_case(["https://site.example/one", "https://site.example/two"])
        self.run_tool()
        con = sqlite3.connect(self.profile / "Favicons")
        n = con.execute("SELECT count(*) FROM favicons WHERE url = 'https://site.example/root.png'").fetchone()[0]
        con.close()
        self.assertEqual(n, 1)

    def test_dry_run_changes_nothing_and_prints_counts_only(self) -> None:
        self.setup_case(["https://exact.example/a", "https://site.example/q", "https://none.example/"])
        before = (self.profile / "Favicons").read_bytes()
        code, out = self.run_tool("--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual((self.profile / "Favicons").read_bytes(), before)
        self.assertFalse(list(self.profile.glob("Favicons.ryce-*")))
        self.assertNotIn("example", out)  # never a URL on screen
        for line in ("marcadores: 3", "exacto: 1", "mismo origen: 1", "sin icono: 1"):
            self.assertIn(line, out)

    def test_a_backup_is_taken_before_writing(self) -> None:
        self.setup_case(["https://exact.example/a"])
        self.run_tool()
        backups = list(self.profile.glob("Favicons.ryce-*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(icon_of(backups[0], "https://exact.example/a"), [])

    def test_refuses_another_schema_version(self) -> None:
        self.setup_case(["https://exact.example/a"])
        self.src.unlink()
        make_db(self.src, version=8)
        code, _ = self.run_tool()
        self.assertEqual(code, 2)

    def test_refuses_while_chromium_holds_the_profile(self) -> None:
        self.setup_case(["https://exact.example/a"])
        os.symlink(f"{socket.gethostname()}-{os.getpid()}", self.profile.parent / "SingletonLock")
        before = (self.profile / "Favicons").read_bytes()
        code, _ = self.run_tool()
        self.assertEqual(code, 3)
        self.assertEqual((self.profile / "Favicons").read_bytes(), before)

    def test_a_stale_lock_from_a_dead_process_does_not_block(self) -> None:
        self.setup_case(["https://exact.example/a"])
        os.symlink(f"{socket.gethostname()}-999999999", self.profile.parent / "SingletonLock")
        code, _ = self.run_tool()
        self.assertEqual(code, 0)

    def test_missing_source_is_a_clear_error(self) -> None:
        self.setup_case(["https://exact.example/a"])
        self.src.unlink()
        code, _ = self.run_tool()
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
