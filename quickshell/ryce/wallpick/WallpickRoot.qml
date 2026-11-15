import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

// The wallpaper picker (SUPER+SHIFT+W): the current theme's pictures, on the focused
// screen, loaded only while open.
//   qs -c ryce ipc call wallpick toggle|open|close
// The choice runs `ryce-theme wall <n>` here, outside the drawer, so it outlives the
// drawer closing while the picture cross-fades; ryce-theme stays the only writer of
// wallpapers.json. Nothing here ever changes the picture on its own.
Scope {
    id: root

    property bool open: false
    property string screenName: ""
    property string note: ""               // the last choice's news, shown on the next opening
    property string noteKind: ""

    function focusedScreen() {
        const monitor = Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE") ? Hyprland.focusedMonitor : null;
        return monitor ? monitor.name : (Quickshell.screens[0]?.name ?? "");
    }
    function show(name) {
        screenName = name;
        open = true;
        loader.active = true;
    }
    function hide() {
        if (!open) return;
        open = false;
        if (!pick.running) note = "";
    }

    function choose(n) {
        if (pick.running) {
            note = "El cambio de fondo anterior sigue en marcha";
            noteKind = "warn";
            return;
        }
        note = "";
        pick.screenName = screenName;
        pick.startedAt = Date.now();
        pick.command = ["sh", "-c",
            // PATH first (the stage puts a stub there), then the deployed copy.
            "b=$(command -v ryce-theme) || b=\"$HOME/.local/bin/ryce-theme\"; [ -x \"$b\" ] || exit 127; exec \"$b\" wall \"$1\"",
            "sh", String(n)];
        pick.running = true;
        hide();
    }
    function chosen(code, stderr) {
        if (code === 0) return;
        const reason = stderr.trim().split("\n").filter(l => l.trim() !== "").pop()?.replace(/^ryce-theme:\s*/, "") ?? "";
        noteKind = code === 3 ? "warn" : "err";
        note = code === 3 ? "Fondo elegido; no se pudo pintar: " + reason
            : code === 2 ? "Sin cambios: " + (reason !== "" ? reason : "ryce-theme no aceptó el fondo")
            : code === 127 ? "No encuentro ryce-theme: ejecuta install/deploy.sh"
            : "ryce-theme falló (código " + code + ")";
        // A quick failure is news about what was just asked; a late one must not grab
        // the keyboard out of nowhere.
        if (Date.now() - pick.startedAt < 5000) show(pick.screenName);
    }

    IpcHandler {
        target: "wallpick"

        function toggle(): void { root.open ? root.hide() : root.show(root.focusedScreen()); }
        function open(): void { root.show(root.focusedScreen()); }
        function close(): void { root.hide(); }
    }

    Process {
        id: pick
        property string screenName: ""
        property real startedAt: 0
        stderr: StdioCollector { id: pickErr }
        onExited: code => root.chosen(code, pickErr.text)
    }

    LazyLoader {
        id: loader

        WallpickWindow {
            screen: Quickshell.screens.find(s => s.name === root.screenName) ?? Quickshell.screens[0] ?? null
            shown: root.open
            note: root.note
            noteKind: root.noteKind
            onCloseRequested: root.hide()
            onGone: if (!root.open) loader.active = false
            onPicked: n => root.choose(n)
        }
    }
}
