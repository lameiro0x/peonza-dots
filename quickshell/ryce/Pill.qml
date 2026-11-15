import QtQuick
import qs
import qs as Ryce

// A quick toggle. Off: a quiet ground. On: the bar's active mark (pill colour and
// radius), so "on" means the same thing everywhere.
Rectangle {
    id: pill
    property string glyph
    property string label
    property bool on: false
    property bool available: true
    signal clicked()

    implicitHeight: 34
    radius: Math.min(Ryce.Palette.pillRadius, height / 2)
    color: on ? Ryce.Palette.pill : mouse.containsMouse && available ? Ryce.Palette.bg2 : Ryce.Palette.bg1
    Accessible.role: Accessible.CheckBox
    Accessible.name: label
    Accessible.checked: on
    Behavior on color { ColorAnimation { duration: 140 } }

    Row {
        anchors.centerIn: parent
        spacing: 8

        Label {
            text: pill.glyph
            color: pill.on ? Ryce.Palette.inkOnPill : pill.available ? Ryce.Palette.fg1 : Ryce.Palette.fg2
            font.family: Ryce.Palette.fontIcon
            font.pixelSize: 15
            anchors.verticalCenter: parent.verticalCenter
        }
        Label {
            text: pill.label
            color: pill.on ? Ryce.Palette.inkOnPill : pill.available ? Ryce.Palette.fg1 : Ryce.Palette.fg2
            font.pixelSize: Ui.meta + 1
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: pill.available ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (pill.available) pill.clicked()
    }
}
