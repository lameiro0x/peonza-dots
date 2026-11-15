import QtQuick
import Quickshell
import Quickshell.Bluetooth

// The headset's state machine, kept apart from where its data comes from so that it runs
// against stand-ins in quickshell/tests/headset: Headset.qml feeds it Quickshell.Bluetooth's
// default adapter and device list. Both are duck-typed. An adapter has `state`
// (BluetoothAdapterState) and a writable `enabled`; a device has address, name, icon,
// paired, connected, state (BluetoothDeviceState), batteryAvailable, battery (0–1),
// connect() and disconnect().
//
// What Quickshell 0.3.2 does underneath (src/bluetooth/device.cpp, adapter.cpp):
// - connect() and disconnect() set Connecting / Disconnecting at once, ignore a press while
//   one is in flight and cannot be cancelled. A failed call only logs a warning and the
//   state falls back to BlueZ's `Connected`: Connecting → Disconnected is the failure.
// - Every change of BlueZ's `Connected` rewrites the state: a headset that connects by
//   itself goes Disconnected → Connected, a refused disconnect Disconnecting → Connected.
// - `enabled` is written locally before BlueZ answers, a write of the value it already
//   holds is dropped, and it can read stale after a resume (quickshell#1372); BlueZ's own
//   answer is the adapter's `state`.
// - When the controller re-registers (after a hibernation: hci0 → hci1) every device object
//   goes away and comes back as a new one with the same address.
Scope {
    id: root

    property var adapter: null
    property var devices: []
    property string last: ""                 // the address connected last (its owner keeps it)
    signal remember(string address)          // a device just connected: keep it as `last`

    property int settleMs: 30000             // past this no answer is coming (QtDBus gives up at 25 s)
    property int forgetMs: 4000              // how long «no responde» is said
    property int powerUpMs: 2000             // a connect straight after power-up tends to fail
    property int againMs: 1000               // between the two halves of a reconnect
    property int retryMs: 2500               // a reconnect's connect half refused: once more after this
    property int powerWaitMs: 6000           // an adapter that never says it is on is stale: go anyway

    readonly property bool present: adapter !== null
    readonly property bool powered: present && adapter.state === BluetoothAdapterState.Enabled
    readonly property bool blocked: present && adapter.state === BluetoothAdapterState.Blocked

    // BlueZ's class icon for anything that plays sound: audio-headset, audio-headphones,
    // audio-card (speakers). The list also holds unpaired devices seen in a scan.
    readonly property var candidates: devices.filter(d => d.paired && String(d.icon).startsWith("audio-"))
    // A press acts on one address until it is answered, whatever object carries it (a
    // re-registered controller brings the device back as a new object) and whatever the
    // choice below would say meanwhile (a second pair of headphones connecting by itself).
    property string target: ""
    readonly property var device: target !== "" ? (candidates.find(d => d.address === target) ?? null)
        : candidates.find(d => d.connected && d.address === last)
            ?? candidates.find(d => d.connected)
            ?? candidates.find(d => d.address === last)
            ?? candidates[0] ?? null

    readonly property int linkState: device?.state ?? BluetoothDeviceState.Disconnected
    readonly property bool connected: device !== null && device.connected

    // A press in flight: "on" connecting, "off" disconnecting, "re" the disconnect half of a
    // reconnect.
    property string pending: ""
    property bool reconnecting: false        // a reconnect, from its press to its outcome
    property bool downSeen: false            // the reconnect's link did go down
    property bool retried: false             // the reconnect's connect half was tried twice
    property bool poweringUp: false          // the press switched the adapter on and waits for it
    property bool failed: false              // a press came back without a link

    readonly property bool busy: pending !== "" || linkState === BluetoothDeviceState.Connecting
        || linkState === BluetoothDeviceState.Disconnecting

    readonly property string name: device?.name ?? ""
    // 0–100 while connected and reported; -1 otherwise.
    readonly property int batteryLevel: connected && device.batteryAvailable ? Math.round(device.battery * 100) : -1
    // Time to charge them: the same threshold for the pill's glyph and the OSD's colour.
    readonly property bool low: batteryLevel >= 0 && batteryLevel <= 15
    // The state in a few words, the same in the sidebar's pill and in the OSD. A press in
    // flight speaks first, also while its device is between two objects.
    readonly property string word: failed ? "no responde"
        : reconnecting ? "reconectando…"
        : pending === "on" ? "conectando…"
        : pending === "off" ? "desconectando…"
        : !present ? "sin Bluetooth"
        : blocked ? "Bluetooth desactivado"
        : device === null ? "sin emparejar"
        : linkState === BluetoothDeviceState.Connecting ? "conectando…"
        : linkState === BluetoothDeviceState.Disconnecting ? "desconectando…"
        : connected ? "conectado"
        : "desconectado"

    // The sidebar's pill: connect, or disconnect when connected.
    function toggle() {
        if (!ready()) return;
        if (device.connected) disconnectNow();
        else connectNow();
    }

    // SUPER+b: connect; when already connected, reconnect — the link can be up with no
    // sound (after a resume), and a fresh connect brings the audio profile back.
    function reconnect() {
        if (!ready()) return;
        if (!device.connected) {
            connectNow();
            return;
        }
        clearFailure();
        target = device.address;
        reconnecting = true;
        downSeen = false;
        retried = false;
        pending = "re";
        device.disconnect();
        settle.restart();
    }

    function status() {
        return JSON.stringify({
            present: present, powered: powered, blocked: blocked, device: name,
            state: BluetoothDeviceState.toString(linkState), connected: connected, busy: busy,
            pending: pending, reconnecting: reconnecting, failed: failed, word: word,
            battery: batteryLevel, low: low, candidates: candidates.length
        });
    }

    function ready() {
        // The device list can outlive its adapter for a moment (a re-registration).
        return present && device !== null && !blocked && !busy;
    }
    function connectNow() {
        if (!present || device === null) return;
        clearFailure();
        target = device.address;
        pending = "on";
        powerOn();
        device.connect();
        settle.restart();
    }
    // Not on for BlueZ: BlueZ refuses the first connect (NotReady) until it is up, and
    // onPoweredChanged tries again. Off: switch it on — a cached `enabled` that still reads
    // true there is stale and a write of true would be dropped, so write it off, then on.
    // Enabling: it is on its way (AutoEnable powering a controller that just came back after
    // a hibernation), so wait the same way. One that never says it is on (stuck, as in
    // quickshell#1372) is gone round after powerWaitMs: the connect is tried as things are,
    // and a refusal then is a failure.
    function powerOn() {
        poweringUp = false;
        powerWait.stop();
        if (powered) return;
        const state = adapter.state;
        if (state === BluetoothAdapterState.Disabled || state === BluetoothAdapterState.Disabling) {
            if (adapter.enabled) adapter.enabled = false;
            adapter.enabled = true;
        } else if (state !== BluetoothAdapterState.Enabling) {
            return;
        }
        poweringUp = true;
        powerWait.restart();
    }
    function disconnectNow() {
        clearFailure();
        target = device.address;
        pending = "off";
        device.disconnect();
        settle.restart();
    }
    function clearFailure() {
        failed = false;
        forget.stop();
    }
    // The press is answered. `failed` is set before `pending` clears: whoever reacts to
    // `busy` going false (the OSD's hold) must already see it.
    function fail() {
        failed = true;
        settled();
        forget.restart();
    }
    function settled() {
        reconnecting = false;
        downSeen = false;
        retried = false;
        poweringUp = false;
        settle.stop();
        again.stop();
        retry.stop();
        powerUp.stop();
        powerWait.stop();
        pending = "";
        // `target` feeds `device` and `linkState`: never written from inside their own
        // change handlers (Qt would call it a binding loop and leave one of them stale).
        Qt.callLater(release);
    }
    function release() {
        if (pending === "") target = "";
    }

    onLinkStateChanged: {
        // The press's device is between two objects: onDeviceChanged carries on.
        if (device === null) return;
        if (linkState === BluetoothDeviceState.Connected) {
            // `last` feeds `device`: told after this handler, like `target` (see settled()).
            if (device.address !== last) {
                const address = device.address;
                Qt.callLater(() => root.remember(address));
            }
            // The disconnect half of a reconnect was refused (Disconnecting → Connected):
            // nothing was reconnected, so the press failed.
            if (pending === "re" && !downSeen) {
                fail();
                return;
            }
            // Any other link that comes up answers the press, a failed one included (BlueZ
            // said InProgress while the headset was connecting by itself, then it connected).
            clearFailure();
            settled();
        } else if (linkState === BluetoothDeviceState.Disconnected) {
            if (pending === "off") {
                settled();
            } else if (pending === "re") {
                downSeen = true;
                again.restart();
            } else if (pending === "on" && !poweringUp) {
                // BlueZ gave up (br-connection-page-timeout, ~5 s: the headset is off or out
                // of range). While the adapter powers up, the refusal is expected: powerUp
                // tries again. A reconnect knows the headset was there a moment ago (it just
                // took it down): one more try before giving up, never left disconnected
                // after a single refusal.
                if (reconnecting && !retried) {
                    retried = true;
                    retry.restart();
                } else {
                    fail();
                }
            }
        }
    }
    onPoweredChanged: if (powered && pending === "on" && poweringUp) {
        powerWait.stop();
        powerUp.restart();
    }
    onPresentChanged: if (present && (pending === "on" || pending === "re")) again.restart()
    // The press's device went away or came back as a new object (the controller
    // re-registered). Gone: wait for it, settle bounds the wait. Back: carry on.
    onDeviceChanged: {
        if (pending === "") return;
        if (device === null) {
            if (pending === "re") downSeen = true;   // its object going away took the link down
            return;
        }
        if (device.connected) {
            if (pending !== "re" || downSeen) {
                clearFailure();
                settled();
            }
        } else if (pending === "off") {
            settled();
        } else {
            downSeen = true;
            again.restart();
        }
    }

    Timer {
        id: settle
        interval: root.settleMs
        onTriggered: {
            if (root.pending === "on" || root.pending === "re") root.fail();
            else root.settled();
        }
    }
    Timer {
        id: forget
        interval: root.forgetMs
        onTriggered: root.failed = false
    }
    Timer {
        id: powerUp
        interval: root.powerUpMs
        onTriggered: {
            if (root.pending !== "on" || root.device === null || root.device.connected) return;
            root.poweringUp = false;
            root.device.connect();
        }
    }
    Timer {
        id: powerWait
        interval: root.powerWaitMs
        onTriggered: {
            if (root.pending !== "on" || !root.poweringUp || root.device === null || root.device.connected) return;
            root.poweringUp = false;
            root.device.connect();
        }
    }
    Timer {
        id: retry
        interval: root.retryMs
        onTriggered: if (root.pending === "on" && root.device !== null && !root.device.connected) root.device.connect()
    }
    // The second half of a reconnect, or a press whose device came back as a new object.
    Timer {
        id: again
        interval: root.againMs
        onTriggered: {
            if (root.pending !== "on" && root.pending !== "re") return;
            if (!root.present || root.device === null) return;      // still away: settle bounds it
            if (root.device.connected) {
                root.clearFailure();
                root.settled();
            } else {
                root.connectNow();
            }
        }
    }
}
