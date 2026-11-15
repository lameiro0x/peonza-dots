import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import qs
import qs as Ryce

// The wallpaper picker: the theme selector's drawer (it rises out of the screen's bottom
// edge, in the frame's bg0, its free corners at the frame's radius, flaring into the edge)
// holding the current theme's pictures: the main one and its alternates, four to a row.
// Arrows or Tab move, Enter puts the picture, Escape (or a click elsewhere) closes. The
// one that shows says «en uso». WallpickRoot loads it on demand, runs ryce-theme, and
// drops the window on `gone()`.
PanelWindow {
    id: win
    property bool shown: false
    property string note: ""
    property string noteKind: ""            // "warn" | "err" | ""
    signal closeRequested()
    signal gone()
    signal picked(int number)

    // The remembered choices, in the theme state (Palette.stateDir, spelled from the
    // environment for qmlcheck); the theme's own theme.json is read through
    // Palette.themeDir, never `current/` (tools/lint.py), each time the drawer opens.
    readonly property string stateDir: Quickshell.env("RYCE_THEME_STATE") || (Quickshell.env("HOME") + "/.local/state/ryce/theme")
    readonly property string picksFile: stateDir + "/wallpapers.json"

    property string themeId: ""
    property string themeName: ""
    property var pictures: []               // [{number, name, thumb}]
    property var picks: ({})
    readonly property int active: {
        const n = picks[themeId];
        return Number.isInteger(n) && n > 0 && n < pictures.length ? n : 0;
    }

    // «assets/wallpapers/tinta-plano.jpg» -> «Plano»: the file's name without the theme.
    function nameOf(path, tid) {
        const stem = String(path).split("/").pop().replace(/\.[^.]*$/, "").replace(new RegExp("^" + tid + "-"), "");
        const words = stem.replace(/[-_]+/g, " ").trim();
        return words === "" ? "Sin nombre" : words.charAt(0).toUpperCase() + words.slice(1);
    }
    function load(text) {
        let t = null;
        try {
            t = JSON.parse(text);
        } catch (e) {
            t = null;
        }
        // The id names a folder: only what ryce-theme itself would accept.
        if (!t || typeof t.id !== "string" || !/^[a-z0-9-]+$/.test(t.id)) {
            win.pictures = [];
            return;
        }
        const alts = Array.isArray(t.wallpaper?.alternates) ? t.wallpaper.alternates : [];
        const base = "file://" + win.stateDir + "/" + t.id + "/wallpaper/";
        win.themeId = t.id;
        win.themeName = typeof t.name === "string" ? t.name : t.id;
        win.pictures = [{ number: 0, name: "Principal", thumb: base + "thumb.png" }].concat(
            alts.map((p, i) => ({ number: i + 1, name: win.nameOf(p, t.id), thumb: base + "alt-" + (i + 1) + "/thumb.png" })));
        win.focusIndex = win.active;
    }

    Process {
        id: info
        function reload() {
            running = false;
            command = ["cat", "--", Ryce.Palette.themeDir + "/theme.json"];
            running = true;
        }
        stdout: StdioCollector { id: infoText }
        onExited: code => {
            if (code === 0) win.load(infoText.text);
            else win.pictures = [];
        }
    }
    FileView {
        id: memory
        path: win.picksFile
        printErrors: false
        onLoaded: {
            try {
                const m = JSON.parse(text());
                win.picks = m && typeof m === "object" ? m : {};
            } catch (e) {
                win.picks = {};
            }
            win.focusIndex = win.active;
        }
        onLoadFailed: win.picks = {}
    }
    // A theme switch while open: follow the palette, which ryce-theme tells.
    Connections {
        target: Ryce.Palette
        function onThemeIdChanged() { info.reload(); }
    }

    readonly property int columns: Math.max(1, Math.min(4, pictures.length))
    readonly property int fillet: Ryce.Palette.frameRadius
    readonly property int corner: Ryce.Palette.frameRadius
    readonly property int slack: 24         // room above for a curve that overshoots
    readonly property int pad: 24
    readonly property int bodyWidth: Math.max(grid.implicitWidth, 520) + 2 * pad
    readonly property int bodyHeight: content.implicitHeight + pad + 16
    property real p: 0                      // 0 = under the screen's edge, 1 = open

    property int focusIndex: 0
    function move(step) {
        const n = pictures.length;
        if (n > 0) focusIndex = (focusIndex + step + n) % n;
    }
    function moveRow(step) {
        const to = focusIndex + step * columns;
        if (to >= 0 && to < pictures.length) focusIndex = to;
    }
    function activate() {
        if (focusIndex < 0 || focusIndex >= pictures.length) return;
        if (focusIndex === active) win.closeRequested();
        else win.picked(focusIndex);
    }

    visible: shown || p > 0
    anchors.bottom: true
    implicitWidth: bodyWidth + 2 * fillet
    implicitHeight: slack + bodyHeight
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    WlrLayershell.namespace: "qs-wallpick"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: shown ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    onShownChanged: shown ? open() : close()
    Component.onCompleted: if (shown) open()
    function open() {
        info.reload();
        memory.reload();
        leave.stop();
        enter.duration = Ryce.Palette.motionMs;
        enter.start();
    }
    function close() {
        enter.stop();
        leave.duration = Math.round(Ryce.Palette.motionMs * 0.6);
        leave.start();
    }
    NumberAnimation {
        id: enter
        target: win
        property: "p"
        to: 1
        easing.type: Easing.BezierSpline
        easing.bezierCurve: Ryce.Palette.motionCurve
    }
    NumberAnimation {
        id: leave
        target: win
        property: "p"
        to: 0
        easing.type: Easing.InCubic
        onFinished: win.gone()
    }

    HyprlandFocusGrab {
        active: win.shown
        windows: [win]
        onCleared: win.closeRequested()
    }

    Item {
        id: drawer
        y: win.slack + Math.round((1 - win.p) * win.bodyHeight)
        width: win.width
        height: win.bodyHeight + win.slack
        focus: true

        Keys.onEscapePressed: win.closeRequested()
        Keys.onLeftPressed: win.move(-1)
        Keys.onRightPressed: win.move(1)
        Keys.onTabPressed: win.move(1)
        Keys.onBacktabPressed: win.move(-1)
        Keys.onUpPressed: win.moveRow(-1)
        Keys.onDownPressed: win.moveRow(1)
        Keys.onReturnPressed: win.activate()
        Keys.onEnterPressed: win.activate()
        Keys.onSpacePressed: win.activate()

        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer

            ShapePath {
                id: edge
                readonly property real f: win.fillet
                readonly property real r: win.corner
                readonly property real w: drawer.width
                readonly property real b: win.bodyHeight                // the screen's bottom edge

                fillColor: Ryce.Palette.bg0
                strokeWidth: -1
                startX: 0
                startY: edge.b
                PathArc { x: edge.f; y: edge.b - edge.f; radiusX: edge.f; radiusY: edge.f; direction: PathArc.Counterclockwise }
                PathLine { x: edge.f; y: edge.r }
                PathArc { x: edge.f + edge.r; y: 0; radiusX: edge.r; radiusY: edge.r }
                PathLine { x: edge.w - edge.f - edge.r; y: 0 }
                PathArc { x: edge.w - edge.f; y: edge.r; radiusX: edge.r; radiusY: edge.r }
                PathLine { x: edge.w - edge.f; y: edge.b - edge.f }
                PathArc { x: edge.w; y: edge.b; radiusX: edge.f; radiusY: edge.f; direction: PathArc.Counterclockwise }
                PathLine { x: edge.w; y: drawer.height }
                PathLine { x: 0; y: drawer.height }
            }
        }

        ColumnLayout {
            id: content
            x: win.fillet + win.pad
            y: win.pad - 4
            width: win.bodyWidth - 2 * win.pad
            spacing: 16

            // The header carries the keys, or the news of the last choice in its place.
            SectionRule {
                Layout.fillWidth: true
                label: win.themeName !== "" ? "fondo · " + win.themeName.toLowerCase() : "fondo"
                metaMax: content.width - 160
                meta: win.note !== "" ? win.note : "flechas para elegir · Intro lo pone · Esc cierra"
                metaColor: win.noteKind === "err" ? Ryce.Palette.err : win.noteKind === "warn" ? Ryce.Palette.warn : Ryce.Palette.fg2
            }

            Grid {
                id: grid
                visible: win.pictures.length > 0
                columns: win.columns
                spacing: 16

                Repeater {
                    model: win.pictures

                    WallCard {
                        required property var modelData
                        required property int index
                        number: modelData.number
                        name: modelData.name
                        thumb: modelData.thumb
                        order: index
                        focused: win.focusIndex === index
                        current: win.active === index
                        onHovered: win.focusIndex = index
                        onPicked: {
                            win.focusIndex = index;
                            win.activate();
                        }
                    }
                }
            }

            Label {
                visible: win.pictures.length === 0
                text: "No encuentro los fondos del tema: ejecuta install/deploy.sh"
                color: Ryce.Palette.fg1
                font.pixelSize: Ui.body
            }
        }
    }
}
