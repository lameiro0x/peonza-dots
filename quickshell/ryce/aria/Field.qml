import QtQuick
import QtQuick.Shapes
import qs
import qs as Ryce
import qs.bar

// A one-line text field in the drawer's skin: a quiet ground (Tinta: a 1 px box) that
// lifts while it holds the keyboard, and a placeholder in fg2.
Item {
    id: field
    property alias text: input.text
    property alias input: input
    property string placeholder
    property bool secret: false
    signal accepted()

    readonly property string skin: BarUi.skin

    implicitHeight: 34
    Accessible.role: Accessible.EditableText
    Accessible.name: placeholder

    Rectangle {
        visible: field.skin === "chip" || field.skin === "capsule"
        anchors.fill: parent
        radius: field.skin === "capsule" ? height / 2 : Math.min(Ryce.Palette.pillRadius, height / 2)
        color: input.activeFocus ? Ryce.Palette.bg2 : Ryce.Palette.bg1
    }
    Rectangle {
        visible: field.skin === "bare"
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: input.activeFocus ? Ryce.Palette.fg1 : Ryce.Palette.line
    }
    Shape {
        visible: field.skin === "box"
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: "transparent"
            strokeColor: input.activeFocus ? Ryce.Palette.fg2 : Ryce.Palette.line
            strokeWidth: 1
            PathRectangle {
                x: 0.5
                y: 0.5
                width: field.width - 1
                height: field.height - 1
                radius: Math.max(0, Ryce.Palette.pillRadius - 0.5)
            }
        }
    }
    Label {
        anchors.fill: input
        visible: input.text === "" && !input.inputMethodComposing
        text: field.placeholder
        color: Ryce.Palette.fg2
        verticalAlignment: Text.AlignVCenter
    }
    TextInput {
        id: input
        anchors.fill: parent
        anchors.leftMargin: field.skin === "capsule" ? 16 : 10
        anchors.rightMargin: anchors.leftMargin
        verticalAlignment: TextInput.AlignVCenter
        color: Ryce.Palette.fg0
        selectionColor: Ryce.Palette.fg2
        selectedTextColor: Ryce.Palette.bg0
        font.family: Ryce.Palette.fontUi
        font.pixelSize: Ui.body
        echoMode: field.secret ? TextInput.Password : TextInput.Normal
        clip: true
        selectByMouse: true
        onAccepted: field.accepted()
    }
}
