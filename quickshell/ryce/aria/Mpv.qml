import QtQuick
import Quickshell
import Quickshell.Io

// Aria's player: the mpv of ryce-aria.service, driven over its JSON IPC socket. mpv's
// playlist is the queue; each entry is a stream URL whose `id` names the song, and
// `songs` maps those ids to their tags (kept in the runtime dir, so a shell restart
// still knows what mpv is playing). Events only: pause, playlist and duration are
// observed; the position is asked once a second, and only while `tracking` (the drawer
// open) and playing. RYCE_ARIA_RUN points a test shell at its own socket.
Scope {
    id: mpv

    readonly property string runDir: Quickshell.env("RYCE_ARIA_RUN") || Quickshell.env("XDG_RUNTIME_DIR")
    readonly property string socketPath: runDir + "/ryce-aria.sock"
    readonly property string queuePath: runDir + "/ryce-aria-queue.json"

    property bool tracking: false
    property string failure: ""            // Spanish, why there is no player
    property bool starting: false

    property bool paused: true
    property bool idle: true
    property int pos: -1
    property var entries: []               // [{ filename, current }] as mpv reports them
    property real duration: 0
    property real time: 0
    property bool shuffled: false
    property var songs: ({})               // song id -> Subsonic child

    readonly property bool ready: sock.connected
    readonly property bool playing: ready && !paused && !idle
    readonly property var ids: entries.map(e => idOf(e.filename))
    readonly property string currentId: pos >= 0 && pos < ids.length ? ids[pos] : ""
    readonly property var current: currentId !== "" ? (songs[currentId] ?? null) : null

    function idOf(url) {
        const m = /[?&]id=([^&]+)/.exec(String(url ?? ""));
        return m ? decodeURIComponent(m[1]) : "";
    }

    // Commands wait here while the socket comes up; a request's answer goes to its callback.
    property var pending: []
    property var replies: ({})
    property int nextRequest: 100

    function send(cmd, reply) {
        const msg = { command: cmd };
        if (reply) {
            msg.request_id = nextRequest++;
            replies[msg.request_id] = reply;
        }
        sendAll([msg]);
    }
    // Messages in one write: a whole library queued is one flush, not thousands.
    function sendAll(msgs) {
        if (sock.connected) {
            sock.write(msgs.map(m => JSON.stringify(m)).join("\n") + "\n");
            sock.flush();
        } else {
            pending = pending.concat(msgs);
            ensure();
        }
    }
    function get(name, reply) { send(["get_property", name], reply); }

    // Connect; if nobody listens, start the unit once and retry for up to 3 s.
    function attach() {
        if (!sock.connected) sock.connected = true;
    }
    function ensure() {
        if (sock.connected || starting) return;
        failure = "";
        starting = true;
        attempts = 0;
        sock.connected = true;
    }
    property int attempts: 0
    function retry() {
        if (!starting) return;
        attempts++;
        if (attempts === 1) {
            start.running = true;
        } else if (attempts > 16) {
            starting = false;
            pending = [];
            failure = "El reproductor no arranca (systemctl --user status ryce-aria.service)";
        } else {
            again.restart();
        }
    }
    Process {
        id: start
        command: ["systemctl", "--user", "start", "ryce-aria.service"]
        onExited: again.restart()
    }
    Timer {
        id: again
        interval: 200
        onTriggered: sock.connected = true
    }

    Socket {
        id: sock
        path: mpv.socketPath
        parser: SplitParser {
            onRead: line => mpv.receive(line)
        }
        onConnectionStateChanged: {
            if (connected) {
                mpv.starting = false;
                mpv.failure = "";
                for (const [i, name] of ["pause", "playlist-pos", "playlist", "duration", "idle-active"].entries())
                    write(JSON.stringify({ command: ["observe_property", i + 1, name] }) + "\n");
                for (const msg of mpv.pending) write(JSON.stringify(msg) + "\n");
                mpv.pending = [];
                flush();
                if (mpv.tracking) mpv.refreshTime();
            } else {
                mpv.replies = {};
                mpv.paused = true;
                mpv.idle = true;
                mpv.entries = [];
                mpv.pos = -1;
            }
        }
        onError: mpv.retry()
    }

    function receive(line) {
        let msg = null;
        try {
            msg = JSON.parse(line);
        } catch (e) {
            return;
        }
        if (msg.request_id !== undefined) {
            const reply = replies[msg.request_id];
            delete replies[msg.request_id];
            reply?.(msg.error === "success" ? msg["data"] : null);
            return;
        }
        if (msg.event !== "property-change") return;
        const value = msg["data"];
        switch (msg.name) {
        case "pause": paused = value === true; break;
        case "idle-active": idle = value === true; break;
        case "playlist-pos": pos = typeof value === "number" ? value : -1; break;
        case "playlist": entries = Array.isArray(value) ? value : []; break;
        case "duration": duration = typeof value === "number" ? value : 0; break;
        }
    }

    function refreshTime() {
        get("time-pos", v => time = typeof v === "number" ? v : 0);
    }
    onTrackingChanged: if (tracking && ready) refreshTime()
    onPosChanged: time = 0
    Timer {
        interval: 1000
        repeat: true
        running: mpv.tracking && mpv.playing
        onTriggered: mpv.refreshTime()
    }

    // Replace the queue with `list` (Subsonic songs) and play it from `index`. With
    // shuffle on, the rest of the list is shuffled behind the chosen song.
    function playList(list, index, urlOf) {
        const known = {};
        for (const s of list) known[s.id] = s;
        songs = known;
        store.setText(JSON.stringify(known));
        const msgs = [{ command: ["stop"] }];
        for (const s of list) {
            const title = (s.artist ? s.artist + " — " : "") + (s.title ?? "");
            msgs.push({ command: { name: "loadfile", url: urlOf(s.id), flags: "append", options: { "force-media-title": title } } });
        }
        msgs.push({ command: ["playlist-play-index", index] }, { command: ["set_property", "pause", false] });
        sendAll(msgs);
        if (shuffled) shuffleRest();
    }
    function shuffleRest() {
        send(["playlist-shuffle"]);
        get("playlist-pos", p => { if (typeof p === "number" && p > 0) send(["playlist-move", p, 0]); });
    }
    function setShuffle(on) {
        shuffled = on;
        if (entries.length < 2) return;
        if (on) shuffleRest();
        else send(["playlist-unshuffle"]);
    }
    function toggle() { if (!idle || entries.length > 0) send(["cycle", "pause"]); }
    function next() { send(["playlist-next"]); }
    function prev() {
        // Like every player: back to the start first, the previous track within 3 s.
        // Asked, not read from `time`, which is stale while the drawer is closed.
        get("time-pos", t => typeof t === "number" && t > 3 ? seek(0) : send(["playlist-prev"]));
    }
    function seek(seconds) {
        time = seconds;
        send(["seek", seconds, "absolute"]);
    }
    function jump(index) {
        send(["playlist-play-index", index]);
        send(["set_property", "pause", false]);
    }

    FileView {
        id: store
        path: mpv.queuePath
        printErrors: false
        onLoaded: {
            try {
                mpv.songs = JSON.parse(text()) ?? {};
            } catch (e) {
                mpv.songs = {};
            }
        }
    }
    Component.onCompleted: attach()
}
