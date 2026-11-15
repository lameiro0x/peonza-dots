import QtQuick
import qs
import qs as Ryce

// A quiet checkbox line for the selector: a small box, the bar's pill colour when on.
Item {
    id: check
    property string label
    property bool on: false
    property bool focused: false
    signal toggled()

    implicitWidth: row.implicitWidth + 16
    implicitHeight: 30
    Accessible.role: Accessible.CheckBox
    Accessible.name: label
    Accessible.checked: on

    Rectangle {
        anchors.fill: parent
        radius: Math.min(Ryce.Palette.pillRadius, height / 2)
        color: Ryce.Palette.bg1
        opacity: check.focused || mouse.containsMouse ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }
    Row {
        id: row
        x: 8
        anchors.verticalCenter: parent.verticalCenter
        spacing: 9

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: 14
            height: 14
            radius: Math.min(Ryce.Palette.pillRadius, 4)
            color: check.on ? Ryce.Palette.pill : Ryce.Palette.bg0
            border.width: check.on ? 0 : 1
            border.color: Ryce.Palette.fg2
            Behavior on color { ColorAnimation { duration: 120 } }

            Label {
                anchors.centerIn: parent
                visible: check.on
                text: Ui.check
                color: Ryce.Palette.inkOnPill
                font.family: Ryce.Palette.fontIcon
                font.pixelSize: 11
                elide: Text.ElideNone
            }
        }
        Label {
            anchors.verticalCenter: parent.verticalCenter
            text: check.label
            color: check.focused || mouse.containsMouse ? Ryce.Palette.fg0 : Ryce.Palette.fg1
            font.pixelSize: 12
            elide: Text.ElideNone
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: check.toggled()
    }
}
