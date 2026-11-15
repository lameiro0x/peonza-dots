import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

// The keybinding cheat sheet (SUPER+F1), on the focused screen, loaded only while open.
//   qs -c ryce ipc call keys toggle|open|close
Scope {
    id: root

    property bool open: false
    property string screenName: ""

    function focusedScreen() {
        const monitor = Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE") ? Hyprland.focusedMonitor : null;
        return monitor ? monitor.name : (Quickshell.screens[0]?.name ?? "");
    }
    function show() {
        screenName = focusedScreen();
        open = true;
        loader.active = true;
    }

    IpcHandler {
        target: "keys"

        function toggle(): void { root.open ? root.open = false : root.show(); }
        function open(): void { root.show(); }
        function close(): void { root.open = false; }
    }

    LazyLoader {
        id: loader

        CheatsheetWindow {
            screen: Quickshell.screens.find(s => s.name === root.screenName) ?? Quickshell.screens[0] ?? null
            shown: root.open
            onCloseRequested: root.open = false
            onGone: if (!root.open) loader.active = false
        }
    }
}
