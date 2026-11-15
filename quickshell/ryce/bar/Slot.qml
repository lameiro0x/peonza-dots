import QtQuick
import QtQuick.Shapes
import qs as Ryce

// One workspace slot. Fixed geometry per kind (Workspaces.qml), so a label that changes
// never moves anything. The face is drawn twice: once in the bar's colours, once in the
// pill's ink clipped to where the pill is right now, so a label recolours exactly as the
// pill slides under it, with no relayout (SlotFace.qml). Its hover ground is drawn by
// Workspaces, under the pill.
Item {
    id: slot
    required property var info         // one entry of Workspaces.slots
    required property var metrics      // Workspaces.metrics
    property real pillLeft: 0          // the pill's edges, in this slot's coordinates
    property real pillRight: 0
    property bool clickable: false
    readonly property bool hovered: mouse.containsMouse
    signal activated()

    readonly property bool project: info.kind === "project"
    readonly property bool waiting: project && info.state === "waiting"
    readonly property bool busy: project && info.state === "busy"
    readonly property real radius: Math.min(Ryce.Palette.pillRadius, metrics.pillHeight / 2)

    // A waiting slot's dot breathes three times when the wait begins, then holds still.
    property real breath: 1
    onWaitingChanged: {
        breathe.stop();
        breath = 1;
        if (waiting) breathe.start();
    }
    Component.onCompleted: if (waiting) breathe.start()
    SequentialAnimation {
        id: breathe
        loops: 3
        NumberAnimation { target: slot; property: "breath"; to: 0.25; duration: Math.max(480, Ryce.Palette.motionMs * 1.4); easing.type: Easing.InOutSine }
        NumberAnimation { target: slot; property: "breath"; to: 1; duration: Math.max(480, Ryce.Palette.motionMs * 1.4); easing.type: Easing.InOutSine }
    }

    clip: true
    opacity: info.shown ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: Ryce.Palette.motionMs * 0.6; easing.type: Easing.OutCubic } }

    Accessible.role: Accessible.Button
    Accessible.name: "Escritorio " + info.id + (info.label !== "" ? ", " + info.label : "")

    // Working: a hairline ring. A Shape, not a bordered transparent Rectangle (QTBUG-137166).
    Shape {
        visible: slot.busy
        anchors.centerIn: parent
        width: parent.width
        height: slot.metrics.pillHeight
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: "transparent"
            strokeColor: Ryce.Palette.fg2
            strokeWidth: 1
            PathRectangle {
                x: 0.5
                y: 0.5
                width: slot.width - 1
                height: slot.metrics.pillHeight - 1
                radius: Math.max(0, slot.radius - 0.5)
            }
        }
    }
    SlotFace {
        info: slot.info
        metrics: slot.metrics
        height: slot.height
        waiting: slot.waiting
        breath: slot.breath
    }
    Item {
        x: Math.max(0, Math.min(slot.width, slot.pillLeft))
        width: Math.max(0, Math.min(slot.width, slot.pillRight) - x)
        height: parent.height
        visible: width > 0
        clip: true

        SlotFace {
            x: -parent.x
            info: slot.info
            metrics: slot.metrics
            height: slot.height
            waiting: slot.waiting
            breath: slot.breath
            onPill: true
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        enabled: slot.info.shown
        hoverEnabled: true
        cursorShape: slot.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (slot.clickable) slot.activated()
    }
}
