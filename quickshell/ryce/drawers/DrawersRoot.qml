import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import qs
import qs as Ryce

// The drawers that come out of the frame: the sidebar (right rim, SUPER+a, the bar's
// agent counter) and the theme selector (bottom rim, SUPER+t). One open at a time, on
// one screen. The sidebar is opened often: one per screen, built once and kept mapped
// (Sidebar.qml); the selector is loaded on demand and dropped once closed.
//   qs -c ryce ipc call sidebar toggle|open|close
//   qs -c ryce ipc call selector toggle|open|close
// The selector's choice runs ryce-theme here, outside the drawer, so the switch outlives
// the drawer closing while the desktop cross-fades.
Scope {
    id: root

    property bool sidebarOpen: false
    Binding { target: Ryce.Ui; property: "sidebarOpen"; value: root.sidebarOpen }
    property string sidebarScreen: ""
    property real sidebarDismissedAt: 0
    property real sidebarToggledAt: 0       // Date.now() of the last open or close (perf probe)
    property bool sidebarResting: true      // closed and still: the sidebars may be rebuilt
    property bool selectorOpen: false
    property string selectorScreen: ""
    property bool boot: false              // the selector's «al arranque» switch, for this session
    property string note: ""               // the selector's last news, shown on its next opening
    property string noteKind: ""
    property int deskEpoch: 0

    function focusedScreen() {
        const monitor = Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE") ? Hyprland.focusedMonitor : null;
        return monitor ? monitor.name : (Quickshell.screens[0]?.name ?? "");
    }
    function screenFor(name) {
        return Quickshell.screens.find(s => s.name === name) ?? Quickshell.screens[0] ?? null;
    }

    function openSidebar(screenName) {
        closeSelector();
        sidebarToggledAt = Date.now();
        // A name no screen has would open nothing and leave the desks covered.
        sidebarScreen = screenFor(screenName)?.name ?? "";
        sidebarResting = false;
        if (!sidebars.active) sidebars.active = true;   // mid-rebuild: finish it now
        sidebarOpen = true;
    }
    function closeSidebar() {
        if (!sidebarOpen) return;
        sidebarToggledAt = Date.now();
        sidebarOpen = false;
        sidebarDismissedAt = Date.now();
    }
    // The open sidebar's screen went away (an output unplugged): nothing else would close it.
    function sidebarLost() {
        sidebarOpen = false;
        sidebarResting = true;
        Qt.callLater(renewSidebars);            // not while Variants is mid-update
    }
    // A theme switch leaves the text of a long-lived window a shade off what a new window
    // draws: after one, once the cross-fade is over and the sidebar is closed, they are
    // built again in spare frame time (as AriaRoot does).
    property bool sidebarsStale: false
    Connections {
        target: Ryce.Palette
        function onSwitched() {
            root.sidebarsStale = true;
            renewal.restart();
        }
    }
    Timer {
        id: renewal
        interval: Ryce.Palette.motionMs + 200
        onTriggered: root.renewSidebars()
    }
    function renewSidebars() {
        if (!sidebarsStale || sidebarOpen || !sidebarResting) return;
        sidebarsStale = false;
        sidebars.active = false;
        sidebars.activeAsync = true;
    }
    // The bar's agent counter, in-process. A click there while the drawer is open first
    // clears the focus grab (closing it) and then lands here: that click closed it, so
    // it must not open it again.
    function toggleSidebar(screenName) {
        if (sidebarOpen && sidebarScreen === screenName) closeSidebar();
        else if (!sidebarOpen && sidebarScreen === screenName && Date.now() - sidebarDismissedAt < 300) return;
        else openSidebar(screenName);
    }

    function openSelector(screenName) {
        closeSidebar();
        selectorScreen = screenName;
        selectorOpen = true;
        selectorLoader.active = true;
    }
    function closeSelector() {
        if (!selectorOpen) return;
        selectorOpen = false;
        if (!apply.running) note = "";
    }

    function applyTheme(themeId) {
        if (apply.running) {
            note = "El cambio de tema anterior sigue en marcha";
            noteKind = "warn";
            return;
        }
        if (themeId === Ryce.Palette.themeId && !boot) {
            closeSelector();
            return;
        }
        note = "";
        apply.screenName = selectorScreen;
        apply.startedAt = Date.now();
        apply.command = ["sh", "-c",
            // PATH first (the stage puts a stub there), then the deployed copy.
            "b=$(command -v ryce-theme) || b=\"$HOME/.local/bin/ryce-theme\"; [ -x \"$b\" ] || exit 127; exec \"$b\" set \"$@\"",
            "sh", themeId].concat(boot ? ["--boot"] : []);
        apply.running = true;
        // Close now: the desktop cross-fades behind it, and --boot's password prompt
        // (polkit) needs the keyboard this drawer holds.
        closeSelector();
    }
    function applied(code, stderr) {
        const reason = stderr.trim().split("\n").filter(l => l.trim() !== "").pop()?.replace(/^ryce-theme:\s*/, "") ?? "";
        if (code === 0) {
            note = "";
            return;
        }
        noteKind = code === 3 ? "warn" : "err";
        note = code === 3 ? "Tema aplicado; algún programa no se pudo avisar"
            : code === 2 ? "Sin cambios: " + (reason !== "" ? reason : "ryce-theme no aceptó el tema")
            : code === 127 ? "No encuentro ryce-theme: ejecuta install/deploy.sh"
            : "ryce-theme falló (código " + code + ")";
        // A quick failure is news about what was just asked: show it. A late one (a
        // password prompt left open) must not grab the keyboard out of nowhere.
        if (Date.now() - apply.startedAt < 5000) openSelector(apply.screenName);
    }

    IpcHandler {
        target: "sidebar"

        function toggle(): void { root.sidebarOpen ? root.closeSidebar() : root.openSidebar(root.focusedScreen()); }
        function open(): void { root.openSidebar(root.focusedScreen()); }
        function close(): void { root.closeSidebar(); }
    }
    IpcHandler {
        target: "selector"

        function toggle(): void { root.selectorOpen ? root.closeSelector() : root.openSelector(root.focusedScreen()); }
        function open(): void { root.openSelector(root.focusedScreen()); }
        function close(): void { root.closeSelector(); }
    }

    Process {
        id: apply
        property string screenName: ""
        property real startedAt: 0
        stderr: StdioCollector { id: applyErr }
        onExited: code => root.applied(code, applyErr.text)
    }
    Process {
        id: wall
        // This shell's own instance, whatever config name it was started under.
        command: ["qs", "-p", Quickshell.shellDir, "ipc", "call", "desk", "toggle", "wall"]
        onExited: code => {
            root.deskEpoch++;
            if (code !== 0) {
                root.note = "No se pudo cambiar el fondo animado";
                root.noteKind = "err";
            }
        }
    }

    LazyLoader {
        id: sidebars
        activeAsync: true

        Variants {
            model: Quickshell.screens

            Sidebar {
                required property var modelData
                screen: modelData
                shown: root.sidebarOpen && root.sidebarScreen === modelData.name
                toggledAt: root.sidebarToggledAt
                onCloseRequested: root.closeSidebar()
                onRested: {
                    root.sidebarResting = true;
                    root.renewSidebars();
                }
                Component.onDestruction: if (shown || moving) root.sidebarLost()
            }
        }
    }
    LazyLoader {
        id: selectorLoader

        SelectorWindow {
            screen: root.screenFor(root.selectorScreen)
            shown: root.selectorOpen
            boot: root.boot
            note: root.note
            noteKind: root.noteKind
            deskEpoch: root.deskEpoch
            onCloseRequested: root.closeSelector()
            onGone: if (!root.selectorOpen) selectorLoader.active = false
            onApplyRequested: themeId => root.applyTheme(themeId)
            onBootToggled: root.boot = !root.boot
            onWallToggleRequested: if (!wall.running) wall.running = true
        }
    }
}
