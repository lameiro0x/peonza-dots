import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import qs as Ryce

// Hito, the user's task manager, in the shell: a card on each desk (shown while the
// monitor's workspace is empty, like the desk clock; today's tasks unless the user picks
// another filter on it) and a drawer out of the left rim with the list (today, overdue,
// the next 7 days and the undated, to tick off and add) or the month. Filters and view
// are kept in hito.json.
//   qs -c ryce ipc call hito toggle|open|close     the drawer (SUPER+H)
//   qs -c ryce ipc call hito desk                  the desk card on/off (kept in hito.json)
//   qs -c ryce ipc call hito refresh               fetch now
Scope {
    id: root

    readonly property string statePath: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state") + "/ryce/hito.json"
    property bool drawerOpen: false
    property bool drawerSettled: false       // open and done moving: the fetches may land
    Binding { target: Ryce.Ui; property: "hitoOpen"; value: root.drawerOpen }
    property string drawerScreen: ""
    property real toggledAt: 0               // Date.now() of the last open or close (perf probe)
    property bool resting: true              // closed and still: the drawers may be rebuilt
    readonly property bool deskSeen: desks.instances.some(d => d.live)     // a card on screen now

    function focusedScreen() {
        const monitor = Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE") ? Hyprland.focusedMonitor : null;
        const name = monitor?.name ?? "";
        return Quickshell.screens.some(s => s.name === name) ? name : (Quickshell.screens[0]?.name ?? "");
    }
    function closeDrawer() {
        if (!drawerOpen) return;
        toggledAt = Date.now();
        resting = false;
        drawerOpen = false;
        drawerSettled = false;
    }
    function openDrawer() {
        toggledAt = Date.now();
        drawerScreen = focusedScreen();
        resting = false;
        if (!drawers.active) drawers.active = true;     // mid-rebuild: finish it now
        drawerOpen = true;
    }
    // Opening always fetches, once the drawer is out: a reply mid-slide rebuilds the list
    // under the motion. `wanted` turning on may have started that fetch already.
    function settleDrawer() {
        drawerSettled = true;
        if (!client.busy) client.refresh(true);
    }

    Hito {
        id: client
        wanted: root.drawerSettled || root.deskSeen
        calendarOn: root.drawerSettled && saved.listView === "calendario"
    }

    IpcHandler {
        target: "hito"

        function toggle(): void { root.drawerOpen ? root.closeDrawer() : root.openDrawer(); }
        function open(): void { root.openDrawer(); }
        function close(): void { root.closeDrawer(); }
        function desk(): void { saved.desk = !saved.desk; }
        function refresh(): void { client.refresh(true); }
    }

    FileView {
        path: root.statePath
        // Read before the first frame, so a card the user turned off never flashes in.
        blockLoading: true
        printErrors: false
        atomicWrites: true
        onAdapterUpdated: writeAdapter()
        onSaveFailed: err => console.warn(`ryce hito: could not save ${root.statePath}: ${err}`)

        // What the desk card and the drawer show, as the user last left them.
        JsonAdapter {
            id: saved
            property bool desk: true
            property string deskFilter: "hoy"           // hoy | atrasadas | todas | proyecto
            property string deskProject: ""             // a Hito.projectKey
            property string listFilter: "todas"
            property string listProject: ""
            property string listView: "lista"           // lista | calendario
            property string calProject: ""              // "" = every project
        }
    }

    Variants {
        id: desks
        model: Quickshell.screens

        HitoDesk {
            required property var modelData
            screen: modelData
            on: saved.desk
            hito: client
            prefs: saved
        }
    }

    // A theme switch leaves the text of a long-lived window a shade off what a new window
    // draws: after one, once the cross-fade is over and the drawer is closed, it is built
    // again in spare frame time (as AriaRoot does).
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
    // close it, and the desks would stay covered and the list polled.
    function lost() {
        drawerOpen = false;
        drawerSettled = false;
        resting = true;
        Qt.callLater(renew);                    // not while Variants is mid-update
    }
    function renew() {
        if (!stale || drawerOpen || !resting) return;
        stale = false;
        drawers.active = false;
        drawers.activeAsync = true;
    }

    // One drawer per screen, built once and kept mapped (HitoDrawer says why).
    LazyLoader {
        id: drawers
        activeAsync: true

        Variants {
            model: Quickshell.screens

            HitoDrawer {
                required property var modelData
                screen: modelData
                shown: root.drawerOpen && root.drawerScreen === modelData.name
                hito: client
                prefs: saved
                toggledAt: root.toggledAt
                onCloseRequested: root.closeDrawer()
                onEntered: root.settleDrawer()
                onRested: {
                    root.resting = true;
                    root.renew();
                }
                Component.onDestruction: if (shown || moving) root.lost()
            }
        }
    }
}
