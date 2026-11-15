import QtQuick
import Quickshell
import Quickshell.Io
import qs

// The ambient layer: desk widgets (clock, stats), the volume OSD and the live-wallpaper
// experiment, one DeskScreen per monitor. Toggles live in desk.json under the XDG state
// dir, so they survive a reload and a restart:
//   qs -c ryce ipc call desk toggle clock|stats|wall
//   qs -c ryce ipc call osd flash volume
//   qs -c ryce ipc call headset reconnect|toggle|peek|status
//                                  (SUPER+b reconnects; Headset.qml, osd/HeadsetOsd.qml)
Scope {
    id: ambient

    readonly property string statePath: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state") + "/ryce/desk.json"
    readonly property var names: ["clock", "stats", "wall"]
    signal osdShow()

    IpcHandler {
        target: "desk"

        function toggle(name: string): void {
            if (!ambient.names.includes(name)) {
                console.warn(`ryce desk: unknown widget "${name}" (known: ${ambient.names.join(", ")})`);
                return;
            }
            prefs[name] = !prefs[name];
        }
    }

    IpcHandler {
        target: "osd"

        function flash(kind: string): void {
            if (kind !== "volume") {
                console.warn(`ryce osd: unknown kind "${kind}" (known: volume)`);
                return;
            }
            ambient.osdShow();
        }
    }

    // The headset lives in its singleton; its OSD in each DeskScreen beside the volume's.
    // (No function may be named after a `qs ipc` subcommand — show, call, wait, listen,
    // prop: `qs ipc call headset show` prints the target instead of calling it.)
    IpcHandler {
        target: "headset"

        // SUPER+b: connect; already connected, reconnect, which brings the sound back.
        function reconnect(): void { Headset.reconnect(true); }
        // Connect or disconnect, as the sidebar's pill does.
        function toggle(): void { Headset.toggle(true); }
        // The OSD with what the headset is doing now, without touching it.
        function peek(): void { Headset.announced(); }
        function status(): string { return Headset.status(); }
    }

    FileView {
        path: ambient.statePath
        // Read before the first frame, so a widget the user turned off never flashes in.
        blockLoading: true
        printErrors: false
        // Missing or unreadable file: the defaults below stand until the first toggle,
        // which writes a fresh one (atomically: a crash never leaves half a file).
        atomicWrites: true
        onAdapterUpdated: writeAdapter()
        onSaveFailed: err => console.warn(`ryce desk: could not save ${ambient.statePath}: ${err}`)

        JsonAdapter {
            id: prefs
            property bool clock: true
            property bool stats: true
            property bool wall: false
        }
    }

    Variants {
        model: Quickshell.screens

        DeskScreen {
            id: desk
            required property var modelData
            screen: modelData
            clockOn: prefs.clock
            statsOn: prefs.stats
            wallOn: prefs.wall

            Connections {
                target: ambient
                function onOsdShow() { desk.showOsd(); }
            }
        }
    }
}
