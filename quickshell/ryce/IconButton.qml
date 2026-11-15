import QtQuick
import qs
import qs as Ryce

// A glyph button. `primary` wears the bar's active mark (the pill colour, the theme's
// pill radius); the others only show a quiet ground under the pointer. `enabled: false`
// dims it and turns its MouseArea off (Item.enabled reaches the children).
Item {
    id: button
    property string glyph
    property bool primary: false
    property int size: 30
    signal clicked()

    implicitWidth: size
    implicitHeight: size
    opacity: enabled ? 1 : 0.35
    Accessible.role: Accessible.Button

    Rectangle {
        anchors.fill: parent
        radius: Math.min(Ryce.Palette.pillRadius, width / 2)
        color: button.primary ? Ryce.Palette.pill : Ryce.Palette.bg2
        opacity: button.primary ? (mouse.containsMouse ? 0.88 : 1) : (mouse.containsMouse ? 1 : 0)
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }
    Label {
        anchors.centerIn: parent
        text: button.glyph
        color: button.primary ? Ryce.Palette.inkOnPill : Ryce.Palette.fg0
        font.family: Ryce.Palette.fontIcon
        font.pixelSize: Math.round(button.size * 0.55)
        elide: Text.ElideNone
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: button.clicked()
    }
}
