import QtQuick
import Quickshell.Bluetooth

// Quickshell 0.3.2's BluetoothAdapter as HeadsetLogic sees it (src/bluetooth/adapter.cpp):
// writing `enabled` changes it locally at once and does nothing when the value is the same;
// `state` is BlueZ's answer, driven by the test. `writes` counts real writes.
QtObject {
    property int state: BluetoothAdapterState.Enabled
    property bool enabled: true
    property int writes: 0
    onEnabledChanged: writes++
}
