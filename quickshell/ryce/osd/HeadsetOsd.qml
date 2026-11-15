import QtQuick
import QtQuick.Shapes
import Quickshell
import Quickshell.Wayland
import qs
import qs as Ryce

// SUPER+b's answer: the volume OSD's drawer turned on its side — same right edge, same
// mid-height, same concave fillets and hairline rim — naming the headset and saying what
// it is doing: «conectando…», «reconectando…», then «conectado» with the battery, or
// «no responde». When it shows and for how long is HeadsetOsdLife's (tested in
// quickshell/tests/headset). Overlay layer, no input, no keyboard; the window exists only
// while shown (rare, like the volume OSD). `armed` (the focused monitor) picks the screen.
PanelWindow {
    id: osd
    property bool armed
    property bool yielding                  // the volume OSD is out (DeskScreen)
    readonly property bool shown: life.shown
    property real p: shown ? 1 : 0

    readonly property int fillet: Math.max(4, Ryce.Palette.frameRadius)
    readonly property int bodyHeight: 46
    readonly property int padX: 18
    readonly property int maxWidth: 380
    readonly property bool charge: Headset.connected && !Headset.busy && Headset.batteryLevel >= 0
    // One width per showing: the edge never moves while the drawer is out. A press in
    // flight reserves room for its outcome («conectado» and the battery) up front, and the
    // drawer never shrinks back until it has left.
    readonly property real natural: face.implicitWidth + 2 * padX + Ryce.Palette.frameRadius
    readonly property real tail: word.implicitWidth + (level.visible ? face.spacing + level.implicitWidth : 0)
    readonly property real outcome: Math.max(doneWord.advanceWidth, failWord.advanceWidth) + face.spacing
        + doneGlyph.advanceWidth + level.spacing + doneLevel.advanceWidth
    property real held: 0
    function hold() {
        face.forceLayout();                 // a Row in a window that was hidden is not laid out yet
        held = Math.max(held, natural, Headset.busy ? natural - tail + Math.max(tail, outcome) : 0);
    }
    onShownChanged: if (shown) { held = 0; hold(); }
    onNaturalChanged: if (shown) hold()

    TextMetrics { id: doneWord; font: word.font; text: "conectado" }
    TextMetrics { id: failWord; font: word.font; text: "no responde" }
    TextMetrics { id: doneGlyph; font.family: Ryce.Palette.fontIcon; font.pixelSize: 13; text: Ui.battery(100) }
    TextMetrics { id: doneLevel; font: levelText.font; text: "100 %" }

    visible: shown || p > 0
    anchors.right: true
    implicitWidth: Math.min(maxWidth, Math.max(held, natural))
    implicitHeight: bodyHeight + 2 * fillet
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    mask: Region {}

    WlrLayershell.namespace: "qs-osd-headset"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    Behavior on p {
        NumberAnimation {
            duration: Ryce.Palette.motionMs
            easing.type: Easing.BezierSpline
            easing.bezierCurve: Ryce.Palette.motionCurve
        }
    }

    HeadsetOsdLife {
        id: life
        armed: osd.armed
        sidebarOpen: Ui.sidebarOpen
        busy: Headset.busy
        failed: Headset.failed
        yielding: osd.yielding
    }
    Connections {
        target: Headset
        function onAnnounced() { life.announce(); }
        function onBusyChanged() { if (osd.shown) osd.hold(); }
    }

    Shape {
        width: osd.width
        height: osd.height
        x: Math.round((1 - osd.p) * osd.width)
        preferredRendererType: Shape.CurveRenderer

        // VolumeOsd's outline: the edge flares in at the top and the bottom.
        ShapePath {
            id: edge
            readonly property real w: osd.width
            readonly property real h: osd.height
            readonly property real f: osd.fillet
            readonly property real r: Ryce.Palette.frameRadius

            fillColor: Ryce.Palette.bg0
            strokeWidth: -1
            startX: edge.w
            startY: 0
            PathArc { x: edge.w - edge.f; y: edge.f; radiusX: edge.f; radiusY: edge.f }
            PathLine { x: edge.r; y: edge.f }
            PathArc { x: 0; y: edge.f + edge.r; radiusX: edge.r; radiusY: edge.r; direction: PathArc.Counterclockwise }
            PathLine { x: 0; y: edge.h - edge.f - edge.r }
            PathArc { x: edge.r; y: edge.h - edge.f; radiusX: edge.r; radiusY: edge.r; direction: PathArc.Counterclockwise }
            PathLine { x: edge.w - edge.f; y: edge.h - edge.f }
            PathArc { x: edge.w; y: edge.h; radiusX: edge.f; radiusY: edge.f }
            PathLine { x: edge.w; y: 0 }
        }
        // The rim: a hairline along the free side only (not along the screen's edge), so the
        // drawer reads where the wallpaper is the frame's own colour (Papel, Grafito). Half a
        // pixel inside the fill's outline: a 1 px line on the pixel grid, not two half rows
        // (and not half cut off by the window's left edge).
        ShapePath {
            id: rim
            readonly property real o: 0.5
            fillColor: "transparent"
            strokeColor: Ryce.Palette.line
            strokeWidth: 1
            startX: edge.w
            startY: rim.o
            PathArc { x: edge.w - edge.f; y: edge.f + rim.o; radiusX: edge.f; radiusY: edge.f }
            PathLine { x: edge.r + rim.o; y: edge.f + rim.o }
            PathArc { x: rim.o; y: edge.f + edge.r + rim.o; radiusX: edge.r; radiusY: edge.r; direction: PathArc.Counterclockwise }
            PathLine { x: rim.o; y: edge.h - edge.f - edge.r - rim.o }
            PathArc { x: edge.r + rim.o; y: edge.h - edge.f - rim.o; radiusX: edge.r; radiusY: edge.r; direction: PathArc.Counterclockwise }
            PathLine { x: edge.w - edge.f; y: edge.h - edge.f - rim.o }
            PathArc { x: edge.w; y: edge.h - rim.o; radiusX: edge.f; radiusY: edge.f }
        }

        Row {
            id: face
            x: osd.padX
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10

            Label {
                id: glyph
                anchors.verticalCenter: parent.verticalCenter
                // Here, with no ground colour to say it, the glyph carries the state: crossed
                // out only when nothing is coming (off, failed, nothing paired, blocked).
                text: Headset.connected || Headset.busy ? Ui.headphones : Ui.headphonesOff
                color: Headset.failed ? Ryce.Palette.warn : Headset.connected ? Ryce.Palette.fg1 : Ryce.Palette.fg2
                font.family: Ryce.Palette.fontIcon
                font.pixelSize: 16
                elide: Text.ElideNone

                SequentialAnimation on opacity {
                    running: Headset.busy && osd.visible
                    loops: Animation.Infinite
                    alwaysRunToEnd: true
                    NumberAnimation { to: 0.35; duration: 520; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1; duration: 520; easing.type: Easing.InOutSine }
                }
            }
            Label {
                anchors.verticalCenter: parent.verticalCenter
                text: Headset.device === null ? "Cascos" : Headset.name
                color: Ryce.Palette.fg0
                width: Math.min(implicitWidth, osd.maxWidth - 2 * osd.padX - Ryce.Palette.frameRadius
                                - glyph.implicitWidth - word.implicitWidth
                                - (level.visible ? level.implicitWidth + face.spacing : 0) - 2 * face.spacing)
            }
            Label {
                id: word
                anchors.verticalCenter: parent.verticalCenter
                text: Headset.word
                color: Headset.failed ? Ryce.Palette.warn : Ryce.Palette.fg2
                font.pixelSize: Ui.meta + 1
                elide: Text.ElideNone
            }
            Row {
                id: level
                visible: osd.charge
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4

                Label {
                    anchors.verticalCenter: parent.verticalCenter
                    text: Ui.battery(Headset.batteryLevel)
                    color: Headset.low ? Ryce.Palette.warn : Ryce.Palette.fg2
                    font.family: Ryce.Palette.fontIcon
                    font.pixelSize: 13
                    elide: Text.ElideNone
                }
                Label {
                    id: levelText
                    anchors.verticalCenter: parent.verticalCenter
                    text: Headset.batteryLevel + " %"
                    color: Headset.low ? Ryce.Palette.warn : Ryce.Palette.fg2
                    font.pixelSize: Ui.meta + 1
                    font.features: { "tnum": 1 }
                    elide: Text.ElideNone
                }
            }
        }
    }
}
