import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import qs
import qs as Ryce

// The theme selector: a drawer that rises out of the screen's bottom edge, centred, in
// the frame's own bg0. Its free top corners take the frame's radius; where its sides
// meet the edge they flare into it with the frame's concave corner. A header that carries the keys
// (or the news of the last switch), three cards, one per theme, each in its own stance,
// and two quiet switches. Arrows
// or Tab move, Enter applies, Escape (or a click elsewhere) closes. DrawersRoot loads it
// on demand, runs ryce-theme, and drops the window on `gone()`.
PanelWindow {
    id: win
    property bool shown: false
    property string current: Ryce.Palette.themeId
    property bool boot: false
    property string note: ""
    property string noteKind: ""            // "warn" | "err" | ""
    property int deskEpoch: 0               // DrawersRoot bumps it after toggling the wall
    signal closeRequested()
    signal gone()
    signal applyRequested(string themeId)
    signal bootToggled()
    signal wallToggleRequested()

    readonly property var ids: Ryce.Palette.themeIds
    readonly property int fillet: Ryce.Palette.frameRadius
    readonly property int corner: Ryce.Palette.frameRadius
    readonly property int slack: 24         // room above for a curve that overshoots (Niebla)
    readonly property int pad: 24
    readonly property int bodyWidth: cards.implicitWidth + 2 * pad
    readonly property int bodyHeight: content.implicitHeight + pad + 16
    // 0 = under the screen's edge, 1 = open. Enters on the theme's curve, leaves faster.
    property real p: 0

    // Focus: 0..n-1 the cards, n the boot switch, n+1 the wallpaper switch.
    property int focusIndex: Math.max(0, ids.indexOf(current))
    function move(step) {
        const n = ids.length + 2;
        focusIndex = (focusIndex + step + n) % n;
    }
    function activate() {
        if (focusIndex < ids.length) win.applyRequested(ids[focusIndex]);
        else if (focusIndex === ids.length) win.bootToggled();
        else win.wallToggleRequested();
    }

    // The wallpaper switch shows the desk's real state (desk/AmbientRoot.qml writes it);
    // read-only here, the toggle itself goes through the desk's IPC.
    readonly property string deskState: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state") + "/ryce/desk.json"
    property bool wallOn: false
    onDeskEpochChanged: desk.reload()
    FileView {
        id: desk
        path: win.deskState
        printErrors: false
        onLoaded: {
            try {
                win.wallOn = JSON.parse(text()).wall === true;
            } catch (e) {
                win.wallOn = false;
            }
        }
        onLoadFailed: win.wallOn = false
    }

    visible: shown || p > 0
    anchors.bottom: true
    implicitWidth: bodyWidth + 2 * fillet
    implicitHeight: slack + bodyHeight
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    WlrLayershell.namespace: "qs-selector"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: shown ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    onShownChanged: shown ? open() : close()
    Component.onCompleted: if (shown) open()
    function open() {
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
        Keys.onUpPressed: if (win.focusIndex >= win.ids.length) win.focusIndex = Math.max(0, win.ids.indexOf(win.current))
        Keys.onDownPressed: if (win.focusIndex < win.ids.length) win.focusIndex = win.ids.length
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
            width: cards.implicitWidth
            spacing: 16

            // The header carries the keys, or the news of the last switch in its place.
            SectionRule {
                Layout.fillWidth: true
                label: "tema"
                metaMax: cards.implicitWidth - 120
                meta: win.note !== "" ? win.note : "flechas para elegir \u00b7 Intro aplica \u00b7 Esc cierra"
                metaColor: win.noteKind === "err" ? Ryce.Palette.err : win.noteKind === "warn" ? Ryce.Palette.warn : Ryce.Palette.fg2
            }

            Row {
                id: cards
                spacing: 16

                Repeater {
                    model: win.ids

                    ThemeCard {
                        required property string modelData
                        required property int index
                        themeId: modelData
                        order: index
                        focused: win.focusIndex === index
                        current: win.current === modelData
                        onHovered: win.focusIndex = index
                        onPicked: {
                            win.focusIndex = index;
                            win.applyRequested(modelData);
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: -8          // the switches' ground hangs out; their boxes align with the cards
                spacing: 6

                Check {
                    label: "Aplicar también al arranque (pide tu contraseña)"
                    on: win.boot
                    focused: win.focusIndex === win.ids.length
                    onToggled: {
                        win.focusIndex = win.ids.length;
                        win.bootToggled();
                    }
                }
                Check {
                    label: "Fondo animado (experimental)"
                    on: win.wallOn
                    focused: win.focusIndex === win.ids.length + 1
                    onToggled: {
                        win.focusIndex = win.ids.length + 1;
                        win.wallToggleRequested();
                    }
                }
                Item { Layout.fillWidth: true }
            }
        }
    }
}
