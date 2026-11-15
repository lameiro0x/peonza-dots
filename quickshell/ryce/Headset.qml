pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Bluetooth
import Quickshell.Io

// The headset: the paired Bluetooth audio device that SUPER+b (re)connects and the sidebar's
// pill connects and disconnects. It picks itself — the audio device that is connected, else
// the one connected last (kept in headset.json under the XDG state dir), else the first
// paired one — so nothing names a device and a second pair of headphones just works.
// The state machine is HeadsetLogic (tested in quickshell/tests/headset); this file only
// feeds it Quickshell.Bluetooth and keeps the last address. Everything follows BlueZ's
// D-Bus signals: nothing polls, nothing forks. Neither the adapter nor a device is ever
// cached: after a hibernation the controller comes back under a new name (hci0 → hci1),
// and every device object with it.
Singleton {
    id: root

    readonly property string statePath: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state") + "/ryce/headset.json"

    readonly property bool present: logic.present
    readonly property bool blocked: logic.blocked
    readonly property var device: logic.device
    readonly property bool connected: logic.connected
    readonly property bool busy: logic.busy
    readonly property bool failed: logic.failed
    readonly property string name: logic.name
    readonly property int batteryLevel: logic.batteryLevel
    readonly property bool low: logic.low
    readonly property string word: logic.word

    // A press from the keyboard (IPC): the OSD says the outcome when no sidebar is open.
    signal announced()

    function toggle(fromKey) {
        logic.toggle();
        if (fromKey) announced();               // after the press: the OSD sees it in flight
    }
    function reconnect(fromKey) {
        logic.reconnect();
        if (fromKey) announced();
    }
    function status() {
        return logic.status();
    }

    // The showcase stage (tools/showcase) records the public README's media on this machine:
    // BlueZ is the system's, so the owner's headphones would show by name. There, none.
    readonly property bool showcase: Quickshell.env("RYCE_STAGE") === "showcase"

    HeadsetLogic {
        id: logic
        adapter: root.showcase ? null : Bluetooth.defaultAdapter
        devices: root.showcase ? [] : Bluetooth.devices.values
        last: prefs.last
        onRemember: address => prefs.last = address
    }

    FileView {
        path: root.statePath
        // Read before the first binding: a press right after start acts on the right device.
        blockLoading: true
        printErrors: false
        atomicWrites: true
        onAdapterUpdated: writeAdapter()

        JsonAdapter {
            id: prefs
            property string last: ""
        }
    }
}
