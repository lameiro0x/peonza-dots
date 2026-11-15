import QtQuick
import Quickshell.Hyprland
import Quickshell.Io
import qs as Ryce

// The active keyboard layout as its code («US», «ES»). Super+Space switches every
// keyboard at once (`hyprctl switchxkblayout all next`), but a per-device toggle can
// switch one alone, and about ten devices are attached. The `activelayout` event names
// the keyboard that switched and its keymap («KEYBOARD,Spanish»), not the code, so each
// event asks Hyprland for THAT keyboard's layout list and index (the main keyboard
// until an event has named one): one `hyprctl` per burst of events.
Module {
    id: kb
    property bool hyprland: false
    property string code: ""
    property string board: ""          // the keyboard named by the last event

    shown: hyprland && code !== ""
    Accessible.name: "Teclado " + code

    function parse(text) {
        try {
            const boards = JSON.parse(text).keyboards ?? [];
            const k = boards.find(b => b.name === board) ?? boards.find(b => b.main) ?? boards[0];
            const layouts = String(k?.layout ?? "").split(",");
            code = (layouts[k?.active_layout_index ?? 0] ?? "").trim().slice(0, 3).toUpperCase();
        } catch (e) {
            code = "";
        }
    }

    // A switch that lands while a query runs asks again once it ends: two quick switches
    // (or one switch of every keyboard, an event each) must not leave the first answer.
    property bool again: false
    function refresh() {
        if (query.running) again = true;
        else query.running = true;
    }
    Component.onCompleted: if (hyprland) refresh()

    Process {
        id: query
        command: ["hyprctl", "-j", "devices"]
        stdout: StdioCollector {
            onStreamFinished: kb.parse(text)
        }
        onExited: if (kb.again) { kb.again = false; running = true; }
    }
    Connections {
        target: kb.hyprland ? Hyprland : null
        function onRawEvent(event) {
            if (event.name !== "activelayout") return;
            // A keyboard's name never holds a comma; the keymap's name after it may.
            const comma = event.data.indexOf(",");
            kb.board = comma > 0 ? event.data.slice(0, comma) : "";
            kb.refresh();
        }
    }

    BarText {
        text: String.fromCodePoint(0xf030c)      // md-keyboard
        ink: text
        visible: BarUi.skin !== "box"
        color: Ryce.Palette.fg2
        font.family: Ryce.Palette.fontIcon
        font.pixelSize: BarUi.iconPx
        font.weight: Font.Normal
    }
    BarText {
        text: kb.code
        color: Ryce.Palette.fg1
    }
}
