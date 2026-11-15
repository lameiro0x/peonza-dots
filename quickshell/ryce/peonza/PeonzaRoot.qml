import QtQuick
import Quickshell
import Quickshell.Io

// The desk's peonza, one DeskPeonza per monitor: on its own card, it spins for as long
// as the desk is seen. On by default; the switch lives in peonza.json under the XDG
// state dir:
//   qs -c ryce ipc call peonza toggle
Scope {
    id: root

    readonly property string statePath: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state") + "/ryce/peonza.json"

    IpcHandler {
        target: "peonza"

        function toggle(): void { prefs.on = !prefs.on; }
    }

    FileView {
        path: root.statePath
        // Read before the first frame, so a peonza turned off never flashes in.
        blockLoading: true
        printErrors: false
        // Missing or unreadable: on, until the first toggle writes a fresh file.
        atomicWrites: true
        onAdapterUpdated: writeAdapter()
        onSaveFailed: err => console.warn(`ryce peonza: could not save ${root.statePath}: ${err}`)

        JsonAdapter {
            id: prefs
            property bool on: true
        }
    }

    Variants {
        model: Quickshell.screens

        DeskPeonza {
            required property var modelData
            screen: modelData
            on: prefs.on
        }
    }
}
