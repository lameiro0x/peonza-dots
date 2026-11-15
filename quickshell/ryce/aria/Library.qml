import QtQuick
import Quickshell

// What Aria's drawers browse, shared by every screen's drawer: the playlists with their
// real sizes, the songs of each one, and every song on the server.
// Navidrome's getPlaylists counts lie both ways (0.61, measured on the user's server): an
// m3u-imported list whose files are gone says 15 songs and getPlaylist brings none; a
// smart list says 0 until it is next evaluated. So each list is opened once in the
// background (one request at a time, after the list of lists) and shows the size its
// songs give; an empty one says so instead of opening onto nothing. The songs are kept,
// so opening a list afterwards is instant. A list whose `changed` stamp moves is asked
// again; a smart one (it carries `validUntil`) is re-evaluated by the server on every
// read, so it is asked again after `fresh`.
// Every song: search3 with an empty query, which Navidrome documents for clients that
// sync the whole library, in pages of `page` until a short one.
Scope {
    id: lib
    required property var api

    readonly property int page: 500
    readonly property int most: 20000       // shortcut: a library past this is cut, warn if it ever matters
    readonly property real fresh: 30 * 60 * 1000

    property var playlists: null             // [{ id, name, songCount, duration, … }] as the server lists them
    property var known: ({})                 // id -> { stamp, at, songs } once opened
    property var all: null                   // every song, trimmed; null until asked
    property bool allLoading: false
    property real allAt: 0
    property string allFailed: ""

    // Only what the drawer and mpv read: a full Subsonic child is ~40 fields.
    function trim(s) {
        return { id: String(s.id ?? ""), title: s.title ?? "", artist: s.artist ?? "", album: s.album ?? "",
                 duration: Number(s.duration) || 0, track: s.track ?? null, coverArt: s.coverArt ?? "" };
    }
    function stampOf(p) { return p.validUntil !== undefined ? "smart" : String(p.changed ?? ""); }
    function stale(p) {
        const k = known[p.id];
        return !k || k.stamp !== stampOf(p) || (k.stamp === "smart" && Date.now() - k.at > fresh);
    }
    // The size to show: the songs once known, the server's count until then.
    function sizeOf(p) {
        const k = known[p.id];
        return k ? k.songs.length : (p.songCount ?? 0);
    }
    function checked(p) { return known[p.id] !== undefined; }

    function keep(p, songs) {
        const next = Object.assign({}, known);
        next[p.id] = { stamp: stampOf(p), at: Date.now(), songs: songs };
        known = next;
    }

    function loadPlaylists(ok, fail) {
        api.call("getPlaylists", null, r => {
            const next = r.playlists?.playlist ?? [];
            if (JSON.stringify(next) !== JSON.stringify(playlists)) playlists = next;
            ok?.();
            verify();
        }, fail);
    }
    // Background check, one list at a time; a list opened meanwhile is not asked twice.
    property bool verifying: false
    function verify() {
        if (verifying || playlists === null) return;
        const p = playlists.find(stale);
        if (!p) return;
        verifying = true;
        api.call("getPlaylist", { id: p.id }, r => {
            verifying = false;
            keep(p, (r.playlist?.entry ?? []).map(trim));
            Qt.callLater(verify);
        }, () => { verifying = false; });       // the next listing tries again
    }
    // ok(songs) or fail(text); from memory when the list has not changed.
    function songsOf(p, ok, fail) {
        if (!stale(p)) return ok(known[p.id].songs);
        api.call("getPlaylist", { id: p.id }, r => {
            const songs = (r.playlist?.entry ?? []).map(trim);
            keep(p, songs);
            ok(songs);
        }, fail);
    }

    // Every song, then done() (every caller that asked while it loaded). A page that fails
    // keeps what was there before and says why in `allFailed`.
    property var waiters: []
    function loadAll(done) {
        if (all !== null && !allLoading && Date.now() - allAt < fresh) return done?.();
        if (done) waiters.push(done);
        if (allLoading) return;
        allLoading = true;
        allFailed = "";
        const got = [];
        const finish = () => {
            allLoading = false;
            const calls = waiters;
            waiters = [];
            for (const f of calls) f();
        };
        const next = offset => api.call("search3", { query: "", songCount: page, songOffset: offset, albumCount: 0, artistCount: 0 }, r => {
            const songs = r.searchResult3?.song ?? [];
            for (const s of songs) got.push(trim(s));
            if (songs.length === page && got.length < most) return next(offset + page);
            all = got;
            allAt = Date.now();
            finish();
        }, text => {
            allFailed = text;
            finish();
        });
        next(0);
    }

    // A shuffled copy (Fisher–Yates); 20 000 songs take a few milliseconds.
    function shuffled(list) {
        const out = list.slice();
        for (let i = out.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            const t = out[i];
            out[i] = out[j];
            out[j] = t;
        }
        return out;
    }

    // Another server or user: nothing known holds.
    Connections {
        target: lib.api
        function onAuthChanged() {
            lib.playlists = null;
            lib.known = {};
            lib.all = null;
            lib.allAt = 0;
        }
    }
}
