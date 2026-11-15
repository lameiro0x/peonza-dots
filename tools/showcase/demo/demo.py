#!/usr/bin/env python3
"""The showcase stage's invented world: one local server that stands in for Hito's Supabase
REST API and for Aria's Navidrome, and the agentd roster the bar shows.

    python3 demo.py serve PORT_FILE MEDIA_DIR   serve on 127.0.0.1, the chosen port written
                                                to PORT_FILE; MEDIA_DIR holds <song id>.mp3
                                                and <cover id>.jpg (tools/showcase/stage.sh)
    python3 demo.py roster OUT_DIR              write OUT_DIR/roster.json from roster.json
                                                here, times made relative to now
    python3 demo.py media TRACK.wav MEDIA_DIR   one tagged MP3 per song of music.json (the
                                                same track) and its cover: the drawing half
                                                of the theme's own new-tab art (newtab.py)

Everything shown comes from hito.json, music.json and roster.json beside this file: invented
tasks, songs and sessions, nothing read from the owner's accounts. Dates in hito.json are
days from today ("day": -2 is the day before yesterday), so the card always has an overdue
task, today's and the week's. Only what Hito.qml and aria/*.qml call is implemented, with
just enough of PostgREST's filters for their queries; any credentials are accepted.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
USER = "00000000-0000-4000-8000-0000000000de"


def load(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


# --- Hito ------------------------------------------------------------------------------------

class Tasks:
    """hito.json as Supabase rows, edited in memory by the shell (complete, add)."""

    def __init__(self) -> None:
        doc = load("hito.json")
        today = dt.date.today()
        self.projects = [dict(p, user_id=USER) for p in doc["projects"]]
        self.rows = []
        for n, t in enumerate(doc["tasks"], 1):
            day = t.get("day")
            self.rows.append({
                "id": str(n), "user_id": USER, "title": t["title"], "project_id": t.get("project"),
                "priority": t.get("priority", 3), "status": t.get("status", "pending"),
                "scheduled_date": None if day is None else (today + dt.timedelta(days=day)).isoformat(),
                "scheduled_time": t.get("time"), "recurrence_rule": t.get("rrule"),
                "sort_order": n, "created_at": f"2026-01-01T00:00:{n:02d}Z",
            })
        self.lock = threading.Lock()

    @staticmethod
    def keep(row: dict, q: dict[str, str]) -> bool:
        """The filters Hito.qml sends: status=eq., and/or over scheduled_date, id=eq."""
        if "status" in q and row["status"] != q["status"].removeprefix("eq."):
            return False
        if "id" in q and row["id"] != q["id"].removeprefix("eq."):
            return False
        date = row["scheduled_date"]
        if "or" in q:  # (scheduled_date.lte.D,scheduled_date.is.null)
            m = re.search(r"scheduled_date\.lte\.([\d-]+)", q["or"])
            if date is not None and m and date > m[1]:
                return False
        if "and" in q:  # (scheduled_date.gte.A,scheduled_date.lte.B)
            lo = re.search(r"scheduled_date\.gte\.([\d-]+)", q["and"])
            hi = re.search(r"scheduled_date\.lte\.([\d-]+)", q["and"])
            if date is None or (lo and date < lo[1]) or (hi and date > hi[1]):
                return False
        return True

    def select(self, table: str, q: dict[str, str]) -> list[dict]:
        cols = q.get("select", "*").split(",")
        with self.lock:
            if table == "projects":
                rows = list(self.projects)
            else:
                rows = [r for r in self.rows if self.keep(r, q)]
                rows.sort(key=lambda r: (r["scheduled_date"] is None, r["scheduled_date"] or "",
                                         r["scheduled_time"] is None, r["scheduled_time"] or "",
                                         r["priority"], r["sort_order"]))
        return [r if cols == ["*"] else {c: r.get(c) for c in cols} for r in rows]

    def update(self, q: dict[str, str], body: dict) -> None:
        with self.lock:
            for r in self.rows:
                if self.keep(r, {"id": q.get("id", "")}):
                    r.update({k: v for k, v in body.items() if k in ("status", "completed_at")})

    def insert(self, body: dict) -> None:
        with self.lock:
            n = len(self.rows) + 1
            self.rows.append({
                "id": str(n), "user_id": USER, "title": str(body.get("title", ""))[:500],
                "project_id": body.get("project_id"), "priority": body.get("priority", 3),
                "status": "pending", "scheduled_date": body.get("scheduled_date"),
                "scheduled_time": body.get("scheduled_time"), "recurrence_rule": None,
                "sort_order": n, "created_at": dt.datetime.now(dt.UTC).isoformat(),
            })


# --- Subsonic --------------------------------------------------------------------------------

class Music:
    """music.json as a Subsonic library: songs, playlists, covers and streams."""

    def __init__(self, media: Path) -> None:
        doc = load("music.json")
        self.media = media
        self.songs = [dict(s, album=doc["album"], artist=s.get("artist", doc["artist"]), track=n,
                           isDir=False, suffix="mp3", contentType="audio/mpeg")
                      for n, s in enumerate(doc["songs"], 1)]
        self.lists = doc["playlists"]

    def song(self, sid: str) -> dict | None:
        return next((s for s in self.songs if s["id"] == sid), None)

    def playlist(self, p: dict, with_entries: bool) -> dict:
        entries = [s for s in (self.song(i) for i in p["songs"]) if s]
        out = {"id": p["id"], "name": p["name"], "songCount": len(entries),
               "duration": sum(s["duration"] for s in entries), "changed": "2026-11-15T00:00:00Z",
               "owner": "demo", "public": False}
        if with_entries:
            out["entry"] = entries
        return out

    def answer(self, name: str, q: dict[str, str]) -> dict | None:
        if name == "ping":
            return {}
        if name == "getPlaylists":
            return {"playlists": {"playlist": [self.playlist(p, False) for p in self.lists]}}
        if name == "getPlaylist":
            p = next((p for p in self.lists if p["id"] == q.get("id")), None)
            return {"playlist": self.playlist(p, True)} if p else None
        if name == "search3":
            off = int(q.get("songOffset", "0") or 0)
            count = int(q.get("songCount", "20") or 20)
            return {"searchResult3": {"song": self.songs[off:off + count]}}
        if name == "scrobble":
            return {}
        return None


# --- HTTP ------------------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    tasks: Tasks
    music: Music
    server_version = "peonza-demo"

    def log_message(self, fmt: str, *args) -> None:  # quiet: the stage log stays readable
        pass

    def reply(self, status: int, body: bytes = b"", kind: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, status: int, doc) -> None:
        self.reply(status, json.dumps(doc, ensure_ascii=False).encode())

    def query(self) -> tuple[str, dict[str, str]]:
        u = urlsplit(self.path)
        return u.path, {k: v[-1] for k, v in parse_qs(u.query).items()}

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            doc = json.loads(self.rfile.read(n) or b"{}") if 0 < n < 65536 else {}
        except ValueError:
            doc = {}
        return doc if isinstance(doc, dict) else {}

    def do_GET(self) -> None:
        path, q = self.query()
        if m := re.fullmatch(r"/rest/v1/(tasks|projects)", path):
            return self.json(200, self.tasks.select(m[1], q))
        if m := re.fullmatch(r"/rest/(\w+)(?:\.view)?", path):
            return self.subsonic(m[1], q)
        self.json(404, {"message": f"no demo route for {path}"})

    do_HEAD = do_GET

    def do_POST(self) -> None:
        path, q = self.query()
        body = self.body()
        if path == "/auth/v1/token":
            return self.json(200, {"access_token": "demo", "refresh_token": "demo", "expires_in": 86400,
                                   "token_type": "bearer", "user": {"id": USER}})
        if path == "/rest/v1/tasks":
            self.tasks.insert(body)
            return self.reply(201)
        self.json(404, {"message": f"no demo route for {path}"})

    def do_PATCH(self) -> None:
        path, q = self.query()
        if path == "/rest/v1/tasks":
            self.tasks.update(q, self.body())
            return self.reply(204)
        self.json(404, {"message": f"no demo route for {path}"})

    def subsonic(self, name: str, q: dict[str, str]) -> None:
        if name in ("stream", "getCoverArt"):
            sid = re.sub(r"[^\w-]", "", q.get("id", ""))
            f = self.music.media / (f"{sid}.mp3" if name == "stream" else f"{sid}.jpg")
            if not sid or not f.is_file():
                return self.reply(404, b"", "text/plain")
            return self.reply(200, f.read_bytes(), "audio/mpeg" if name == "stream" else "image/jpeg")
        doc = self.music.answer(name, q)
        head = {"status": "ok", "version": "1.16.1", "type": "navidrome", "serverVersion": "demo",
                "openSubsonic": True}
        if doc is None:
            head.update(status="failed", error={"code": 70, "message": f"{name}: nada con ese id"})
            doc = {}
        self.json(200, {"subsonic-response": head | doc})


def serve(port_file: Path, media: Path) -> None:
    Handler.tasks = Tasks()
    Handler.music = Music(media)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    tmp = port_file.with_name(port_file.name + ".tmp")
    tmp.write_text(f"{httpd.server_address[1]}\n")
    tmp.replace(port_file)
    httpd.serve_forever()


def roster(out: Path) -> None:
    """roster.json with `since` and `generatedAt` as seconds before now."""
    doc = load("roster.json")
    now = time.time()
    doc["generatedAt"] = now
    for s in doc["sessions"]:
        s["since"] = now - s.pop("ago", 60)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / ".roster.json.tmp"
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(out / "roster.json")


def media(track: Path, out: Path) -> None:
    """<song id>.mp3 tagged (title, artist, album, number, cover) and <theme>.jpg covers."""
    doc = load("music.json")
    out.mkdir(parents=True, exist_ok=True)
    themes = HERE.parents[2] / "themes"
    for theme in {s["coverArt"] for s in doc["songs"]}:
        art = themes / theme / "chromium" / "newtab"
        # The new tab's column sits on --col-justify's side; the drawing is on the other.
        left = "col-justify: end" in (art / "layout.css").read_text(encoding="utf-8")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(art / "1920x1080.jpg"),
                        "-vf", f"crop=1080:1080:{0 if left else 840}:0,scale=600:600", "-q:v", "3",
                        str(out / f"{theme}.jpg")], check=True, timeout=60)
    for n, s in enumerate(doc["songs"], 1):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(track), "-i", str(out / f"{s['coverArt']}.jpg"),
                        "-map", "0:a", "-map", "1:v", "-c:a", "libmp3lame", "-q:a", "3", "-c:v", "copy",
                        "-id3v2_version", "3", "-disposition:v", "attached_pic",
                        "-metadata", f"title={s['title']}", "-metadata", f"artist={s.get('artist', doc['artist'])}",
                        "-metadata", f"album={doc['album']}", "-metadata", f"track={n}",
                        "-metadata:s:v", "comment=Cover (front)", str(out / f"{s['id']}.mp3")],
                       check=True, timeout=120)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["serve"] and len(args) == 3:
        serve(Path(args[1]), Path(args[2]))
    elif args[:1] == ["roster"] and len(args) == 2:
        roster(Path(args[1]))
    elif args[:1] == ["media"] and len(args) == 3:
        media(Path(args[1]), Path(args[2]))
    else:
        sys.exit(__doc__.split("\n\n")[1])
