import QtQuick
import QtQuick.Shapes
import Quickshell
import Quickshell.Wayland
import Quickshell.Services.Pipewire
import qs
import qs as Ryce

// The volume drawer: when the default sink's volume or mute changes, a small pill slides
// out of the screen's right edge at mid-height, its corners meeting the edge in concave
// fillets like the frame's own, and goes back after 1.2 s. Overlay layer, no input, no
// keyboard. `armed` (the focused monitor) decides which screen shows it.
PanelWindow {
    id: osd
    property bool armed
    property bool shown: false
    property real p: shown ? 1 : 0

    readonly property PwNode sink: Pipewire.defaultAudioSink
    readonly property real volume: sink?.audio?.volume ?? 0
    readonly property bool muted: sink?.audio?.muted ?? false
    // Ignore the burst of changes while a sink appears (startup, a new default device).
    property bool settled: false

    readonly property int fillet: Math.max(4, Ryce.Palette.frameRadius)
    readonly property int bodyWidth: 46
    readonly property int bodyHeight: 188

    function flash() {
        if (!armed) return;
        shown = true;
        hide.restart();
    }

    visible: shown || p > 0
    anchors.right: true
    implicitWidth: bodyWidth
    implicitHeight: bodyHeight + 2 * fillet
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    mask: Region {}

    WlrLayershell.namespace: "qs-osd"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    Behavior on p {
        NumberAnimation {
            duration: Ryce.Palette.motionMs
            easing.type: Easing.BezierSpline
            easing.bezierCurve: Ryce.Palette.motionCurve
        }
    }

    onSinkChanged: { settled = false; settle.restart(); }
    PwObjectTracker { objects: [osd.sink] }
    Connections {
        target: osd.sink?.audio ?? null
        function onVolumeChanged() { if (osd.settled) osd.flash(); }
        function onMutedChanged() { if (osd.settled) osd.flash(); }
    }
    Timer {
        id: settle
        interval: 1500
        running: true
        onTriggered: osd.settled = true
    }
    Timer {
        id: hide
        interval: 1200
        onTriggered: osd.shown = false
    }

    Shape {
        id: drawer
        width: osd.width
        height: osd.height
        x: Math.round((1 - osd.p) * osd.width)
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            id: edge
            readonly property real w: osd.width
            readonly property real h: osd.height
            readonly property real f: osd.fillet
            readonly property real r: Ryce.Palette.frameRadius

            fillColor: Ryce.Palette.bg0     // the frame's own fill: the drawer reads as the edge extruding
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

        // The pill's face, centred in the body.
        Column {
            x: Math.round((osd.bodyWidth - width) / 2)
            anchors.verticalCenter: parent.verticalCenter
            spacing: 12

            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                text: osd.muted || osd.volume <= 0 ? Ui.volOff : osd.volume < 0.34 ? Ui.volLow : osd.volume < 0.67 ? Ui.volMid : Ui.volHigh
                color: osd.muted ? Ryce.Palette.fg2 : Ryce.Palette.fg1
                font.family: Ryce.Palette.fontIcon
                font.pixelSize: 16
                elide: Text.ElideNone
            }
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 4
                height: 104
                radius: 2
                // The track in `line`: bg1 next to the frame's bg0 does not read at all.
                color: Ryce.Palette.line

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: Math.round(parent.height * Math.min(1, osd.volume))
                    radius: 2
                    color: osd.muted ? Ryce.Palette.fg2 : Ryce.Palette.fg0
                    Behavior on height { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
                }
            }
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                text: Math.round(osd.volume * 100)
                color: osd.muted ? Ryce.Palette.fg2 : Ryce.Palette.fg0
                font.pixelSize: 12
                font.features: { "tnum": 1 }
                elide: Text.ElideNone
            }
        }
    }
}
