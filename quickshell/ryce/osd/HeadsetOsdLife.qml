import QtQuick
import Quickshell

// When the headset OSD (HeadsetOsd.qml) is on screen, kept apart from the window so that it
// runs against stand-ins in quickshell/tests/headset. A press shows it on the focused
// screen while nothing else is saying it, keeps it while the press is in flight and lets
// it go a moment after the outcome (longer for a failure).
Scope {
    id: life
    property bool armed: false              // this screen is the focused one
    property bool sidebarOpen: false        // the open sidebar's pill already says it
    property bool busy: false
    property bool failed: false
    property bool yielding: false           // the volume OSD is out at the same spot: the newest wins
    property int holdMs: 1600
    property int failHoldMs: 2600
    property bool shown: false

    // A keyboard press (or a peek). Every screen hears it: the focused one shows it, the
    // others let go of one left from an earlier press (focus moved in between).
    function announce() {
        if (!armed || sidebarOpen) {
            letGo();
            return;
        }
        shown = true;
        if (busy) hide.stop();
        else holdThenHide();
    }
    function letGo() {
        hide.stop();
        shown = false;
    }
    function holdThenHide() {
        hide.interval = failed ? failHoldMs : holdMs;
        hide.restart();
    }

    onBusyChanged: {
        if (!shown) return;
        if (busy) hide.stop();
        else holdThenHide();
    }
    // The sidebar opened over it: the pill takes over, the OSD would sit on top of it.
    onSidebarOpenChanged: if (sidebarOpen) letGo()
    // The volume OSD came out where this one is: it is the newer news.
    onYieldingChanged: if (yielding) letGo()

    Timer {
        id: hide
        onTriggered: life.shown = false
    }
}
