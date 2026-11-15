import QtQuick
import Quickshell.Bluetooth

// Quickshell 0.3.2's BluetoothDevice as HeadsetLogic sees it (src/bluetooth/device.cpp):
// connect() and disconnect() set the state at once and do nothing while connected /
// connecting (connect) or not connected (disconnect). The test drives BlueZ's answers.
QtObject {
    property string address: "00:00:00:00:00:01"
    property string name: "Cascos de prueba"
    property string icon: "audio-headset"
    property bool paired: true
    property bool connected: false
    property int state: BluetoothDeviceState.Disconnected
    property bool batteryAvailable: false
    property real battery: 0
    property int connects: 0
    property int disconnects: 0

    function connect() {
        if (connected || state === BluetoothDeviceState.Connecting) return;
        connects++;
        state = BluetoothDeviceState.Connecting;
    }
    function disconnect() {
        if (!connected) return;
        disconnects++;
        state = BluetoothDeviceState.Disconnecting;
    }

    // BlueZ's answers. device.cpp:288-292 updates `connected`'s value, then notifies the
    // state, then `connected`: a QML property cannot hold a new value without notifying, so
    // the scenarios run twice, with `connected` notified after the state (as the signals go)
    // and before it (as a handler reading the value sees it).
    property bool connectedFirst: false
    function linkUp() {
        if (connectedFirst) connected = true;
        state = BluetoothDeviceState.Connected;
        connected = true;
    }
    function linkDown() {
        if (connectedFirst) connected = false;
        state = BluetoothDeviceState.Disconnected;
        connected = false;
    }
    // A refused or failed call: the state falls back to what BlueZ's Connected says.
    function refused() {
        state = connected ? BluetoothDeviceState.Connected : BluetoothDeviceState.Disconnected;
    }
}
