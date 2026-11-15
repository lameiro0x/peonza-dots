import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import qs as Ryce

// Aria, the user's Navidrome, as a drawer under the bar's right end (SUPER+m): what
// plays, its queue, the playlists, the albums and a search. Playback is the mpv of
// ryce-aria.service (Mpv.qml), so it outlives the drawer, and with mpv-mpris it is also
// the bar's media module and the media keys. One drawer per screen, built once and kept
// mapped: it opens on the focused monitor. The player and the library live here because
// the keys and the scrobbles need them.
//   qs -c ryce ipc call aria toggle|open|close|playpause|next|prev
Scope {
    id: root

    property bool open: false
    Binding { target: Ryce.Ui; property: "ariaOpen"; value: root.open }
    property string screenName: ""
    property real toggledAt: 0               // Date.now() of the last open or close (perf probe)
    property bool resting: true              // closed and still: the drawers may be rebuilt

    readonly property alias api: subsonic
    readonly property alias library: library
    readonly property alias player: player

    function focusedScreen() {
        const monitor = Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE") ? Hyprland.focusedMonitor : null;
        const name = monitor?.name ?? "";
        return Quickshell.screens.some(s => s.name === name) ? name : (Quickshell.screens[0]?.name ?? "");
    }
    function show() {
        toggledAt = Date.now();
        screenName = focusedScreen();
        resting = false;
        if (!drawers.active) drawers.active = true;     // mid-rebuild: finish it now
        open = true;
    }
    // The drawer is in place: now the socket and the network, which would land mid-slide.
    function arrived() {
        player.ensure();
        if (subsonic.status === "offline") subsonic.ping();
    }
    function hide() {
        if (!open) return;
        toggledAt = Date.now();
        resting = false;
        open = false;
    }

    function play(list, index) {
        if (!list || list.length === 0) return;
        player.playList(list, Math.max(0, Math.min(index, list.length - 1)), id => subsonic.streamUrl(id));
    }

    Subsonic { id: subsonic }
    Library {
        id: library
        api: subsonic
    }
    Mpv {
        id: player
        tracking: root.open
    }

    // Scrobble the way Last.fm counts a listen: once a track has played for half its
    // length or 4 minutes, whichever comes first, paused time not counted. One single-shot
    // timer per track; nothing runs while paused.
    // shortcut: a seek counts as listening time; read mpv's playback-time if that matters.
    property string scrobbleId: ""
    property real heardMs: 0
    property real since: 0
    // The song whose «now playing» went out; the same id again is not a new listen. mpv's
    // playlist-shuffle/move/unshuffle point the current entry at another song for one event
    // before settling back, so a change only counts once it has held for `settle`.
    property string trackedId: ""
    Timer {
        id: settle
        interval: 150
        onTriggered: if (player.currentId !== root.trackedId) root.track(player.currentId)
    }
    function track(id) {
        hold();
        trackedId = id;
        scrobbleId = id;
        heardMs = 0;
        if (id === "" || !subsonic.usable) return;
        subsonic.call("scrobble", { id: id, submission: "false" }, null, null);
        const seconds = player.songs[id]?.duration ?? 0;
        countdown.interval = Math.max(1000, Math.min(240000, seconds > 0 ? seconds * 500 : 240000));
        resume();
    }
    function resume() {
        if (scrobbleId === "" || !player.playing || countdown.running) return;
        since = Date.now();
        countdown.interval = Math.max(1, countdown.interval - heardMs);
        heardMs = 0;
        countdown.start();
    }
    function hold() {
        if (!countdown.running) return;
        heardMs = Date.now() - since;
        countdown.stop();
    }
    Timer {
        id: countdown
        onTriggered: {
            subsonic.call("scrobble", { id: root.scrobbleId, submission: "true" }, null, null);
            root.scrobbleId = "";
        }
    }
    Connections {
        target: player
        function onCurrentIdChanged() { settle.restart(); }
        function onPlayingChanged() { player.playing ? root.resume() : root.hold(); }
    }

    IpcHandler {
        target: "aria"

        function toggle(): void { root.open ? root.hide() : root.show(); }
        function open(): void { root.show(); }
        function close(): void { root.hide(); }
        function playpause(): void { player.toggle(); }
        function next(): void { player.next(); }
        function prev(): void { player.prev(); }
    }

    // A theme switch leaves the text of a long-lived window a shade off what a new window
    // draws, and the drawer used to be new on every opening: after a switch, once the
    // cross-fade is over and the drawer is closed, it is built again in spare frame time.
    property bool stale: false
    Connections {
        target: Ryce.Palette
        function onSwitched() {
            root.stale = true;
            renewal.restart();
        }
    }
    Timer {
        id: renewal
        interval: Ryce.Palette.motionMs + 200
        onTriggered: root.renew()
    }
    // The open drawer's screen went away (an output unplugged): nothing else would ever
    // close it, and the desks would stay covered.
    function lost() {
        open = false;
        resting = true;
        Qt.callLater(renew);                    // not while Variants is mid-update
    }
    function renew() {
        if (!stale || open || !resting) return;
        stale = false;
        drawers.active = false;
        drawers.activeAsync = true;
    }

    LazyLoader {
        id: drawers
        activeAsync: true

        Variants {
            model: Quickshell.screens

            AriaWindow {
                required property var modelData
                screen: modelData
                shown: root.open && root.screenName === modelData.name
                aria: root
                onCloseRequested: root.hide()
                onEntered: root.arrived()
                onRested: {
                    root.resting = true;
                    root.renew();
                }
                Component.onDestruction: if (shown || moving) root.lost()
            }
        }
    }
}
