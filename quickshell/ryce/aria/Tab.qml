import QtQuick
import QtQuick.Shapes
import qs
import qs as Ryce
import qs.bar

// A word you can press: the drawer's tabs, the album order and its buttons, in the
// bar's module skin (BarUi.skin). `on` wears the bar's active mark. Origen: chips.
// Grafito: bare words, the active one in fg0 behind a dot. Ola: airy capsules. Tinta:
// 1 px boxes on the glass.
Item {
    id: tab
    property string text
    property bool on: false
    property bool small: false
    signal clicked()

    readonly property string skin: BarUi.skin
    readonly property bool grounded: skin === "chip" || skin === "capsule"

    implicitWidth: label.implicitWidth + 2 * (skin === "capsule" ? 16 : skin === "bare" ? 8 : 12)
    implicitHeight: small ? 26 : 30
    opacity: enabled ? 1 : 0.4
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.checked: on

    Rectangle {
        visible: tab.grounded
        anchors.fill: parent
        radius: tab.skin === "capsule" ? height / 2 : Math.min(Ryce.Palette.pillRadius, height / 2)
        color: tab.on ? Ryce.Palette.pill : mouse.containsMouse ? Ryce.Palette.bg3 : Ryce.Palette.bg2
        Behavior on color { ColorAnimation { duration: 140 } }
    }
    // A stroke-only Shape, never a bordered transparent Rectangle (QTBUG-137166).
    Shape {
        visible: tab.skin === "box"
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: tab.on ? Ryce.Palette.bg3 : "transparent"
            strokeColor: tab.on || mouse.containsMouse ? Ryce.Palette.fg2 : Ryce.Palette.line
            strokeWidth: 1
            PathRectangle {
                x: 0.5
                y: 0.5
                width: tab.width - 1
                height: tab.height - 1
                radius: Math.max(0, Ryce.Palette.pillRadius - 0.5)
            }
        }
    }
    Rectangle {
        visible: tab.skin === "bare" && tab.on
        x: 1
        anchors.verticalCenter: parent.verticalCenter
        width: 3
        height: 3
        radius: 1.5
        color: Ryce.Palette.fg0
    }
    Label {
        id: label
        anchors.centerIn: parent
        text: tab.text
        color: tab.grounded && tab.on ? Ryce.Palette.inkOnPill
            : tab.on || mouse.containsMouse ? Ryce.Palette.fg0 : tab.grounded ? Ryce.Palette.fg1 : Ryce.Palette.fg2
        font.pixelSize: tab.small ? Ui.meta : Ui.meta + 1
        font.letterSpacing: tab.skin === "bare" ? 0.6 : 0
        elide: Text.ElideNone
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: tab.clicked()
    }
}
