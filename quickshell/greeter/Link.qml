import QtQuick
import qs

// A word that acts (REINICIAR, APAGAR, CAMBIAR): grey until the pointer or the focus is on
// it, then white with the sheet's square in front. Enter or Space runs it, as a click does.
Item {
    id: link

    required property string label
    readonly property bool lit: mouse.containsMouse || activeFocus
    signal activated()

    implicitWidth: word.implicitWidth
    implicitHeight: word.implicitHeight
    activeFocusOnTab: true

    Accessible.role: Accessible.Button
    Accessible.name: label
    Accessible.onPressAction: link.activated()
    Keys.onReturnPressed: link.activated()
    Keys.onEnterPressed: link.activated()
    Keys.onSpacePressed: link.activated()

    Rectangle {
        x: -12
        anchors.verticalCenter: word.verticalCenter
        width: 5
        height: 5
        color: Look.fg0
        visible: link.activeFocus
    }

    Caps {
        id: word
        text: link.label
        color: link.lit ? Look.fg0 : Look.fg2
        Behavior on color { ColorAnimation { duration: 120 } }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        anchors.margins: -8
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: link.activated()
    }
}
