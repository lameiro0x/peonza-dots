import QtQuick
import qs as Ryce

// One module on the bar: its floating plate (Plate, skinned by BarUi.skin; Grafito's
// readouts share their group's plate instead), the module's own content in a row, and,
// when `interactive`, a hover ground that fades in and a short press. The gap before it
// is part of its width, so a module that appears or leaves (`shown`) slides its
// neighbours over smoothly instead of snapping a spacing at the end; its plate narrows
// with it and the content is clipped, so the plate's shadow is never cut.
// The module's own MouseArea lies under its content, so a button inside (Media's skip
// buttons) takes its own clicks; `hovered` comes from a HoverHandler on the face, which
// still sees the pointer over such a button. `lit` defaults to hover on an interactive
// module; one with buttons inside can keep the ground off while a button is hovered.
Item {
    id: mod
    default property alias content: body.data
    property bool shown: true
    property bool interactive: false
    property alias spacing: body.spacing
    readonly property bool hovered: hover.hovered
    property bool lit: interactive && hovered
    signal clicked(var mouse)
    signal wheeled(var wheel)

    readonly property real full: Math.ceil(body.implicitWidth) + 2 * BarUi.padX

    // The width it is heading to: neighbours budget against this, not the animated one.
    readonly property real target: shown ? full + BarUi.gap : 0

    implicitWidth: target
    implicitHeight: BarUi.band
    visible: width > 0
    opacity: shown ? 1 : 0
    Behavior on implicitWidth { NumberAnimation { duration: Ryce.Palette.motionMs; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
    Behavior on opacity { NumberAnimation { duration: Ryce.Palette.motionMs * 0.6; easing.type: Easing.OutCubic } }

    // Grafito's instrument panel: a dot in the gap between two readouts. The first of a
    // row has none: it would sit on its plate's edge.
    Rectangle {
        visible: BarUi.skin === "bare" && mod.x > 0
        x: Math.round(BarUi.gap / 2) - 1
        anchors.verticalCenter: parent.verticalCenter
        width: 2
        height: 2
        radius: 1
        color: Ryce.Palette.fg2
    }
    MouseArea {
        id: mouse
        anchors.fill: face
        enabled: mod.interactive && mod.shown
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        cursorShape: Qt.PointingHandCursor
        onClicked: m => mod.clicked(m)
        onWheel: w => mod.wheeled(w)
    }
    Item {
        id: face
        x: BarUi.gap
        width: Math.max(0, mod.width - BarUi.gap)
        height: BarUi.chipHeight
        anchors.verticalCenter: parent.verticalCenter
        scale: mouse.pressed ? 0.96 : 1
        Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }

        HoverHandler {
            id: hover
            enabled: mod.interactive && mod.shown
        }
        Plate {
            anchors.fill: parent
            ground: BarUi.skin !== "bare"
            lit: mod.lit
        }
        Item {
            anchors.fill: parent
            clip: true

            Row {
                id: body
                x: BarUi.padX
                height: parent.height
                spacing: BarUi.inner
            }
        }
    }
}
