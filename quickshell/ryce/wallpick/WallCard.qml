import QtQuick
import Quickshell.Widgets
import qs
import qs as Ryce

// One picture in the wallpaper picker: its thumbnail, its number and name, and «en uso»
// on the one that shows. The theme selector's card (drawers/ThemeCard.qml) in the
// current theme's own colours: they all belong to it.
Item {
    id: card
    required property int number           // 0 the main picture, n its alt-n
    required property string name
    required property string thumb          // a file:// URL
    required property int order
    property bool focused: false
    property bool current: false
    signal hovered()
    signal picked()

    // Enters one beat after the card before it; then only the focused card lifts.
    property real enter: 0
    readonly property real lift: focused ? 6 : 0
    property real liftNow: lift
    Behavior on liftNow {
        NumberAnimation {
            duration: Math.round(Ryce.Palette.motionMs * 0.7)
            easing.type: Easing.BezierSpline
            easing.bezierCurve: Ryce.Palette.motionCurve
        }
    }
    SequentialAnimation {
        running: true
        PauseAnimation { duration: Math.round(Ryce.Palette.motionMs * 0.3) + card.order * Math.round(Ryce.Palette.motionMs / 6) }
        NumberAnimation {
            target: card
            property: "enter"
            to: 1
            duration: Ryce.Palette.motionMs
            easing.type: Easing.BezierSpline
            easing.bezierCurve: Ryce.Palette.motionCurve
        }
    }

    implicitWidth: 248
    implicitHeight: face.height
    opacity: Math.min(1, enter)
    transform: Translate { y: Math.round((1 - card.enter) * 14 - card.liftNow) }
    Accessible.role: Accessible.Button
    Accessible.name: card.name + (card.current ? ", en uso" : "")

    Rectangle {
        id: face
        width: parent.width
        height: caption.y + caption.height + 12
        radius: Ryce.Palette.rounding
        color: Ryce.Palette.bg1
        border.width: 1
        border.color: card.focused ? Ryce.Palette.fg2 : Ryce.Palette.line
        Behavior on border.color { ColorAnimation { duration: 140 } }

        ClippingRectangle {
            id: thumb
            x: 7
            y: 7
            width: parent.width - 14
            height: Math.round(width * 9 / 16)
            radius: Math.max(0, Ryce.Palette.rounding - 4)
            color: Ryce.Palette.bg0

            Image {
                anchors.fill: parent
                source: card.thumb
                sourceSize.width: 480
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                smooth: true
            }
        }

        Item {
            id: caption
            x: 15
            y: thumb.y + thumb.height + 12
            width: parent.width - 30
            height: Math.max(nameLabel.implicitHeight, 16)

            Label {
                id: numberLabel
                anchors.verticalCenter: parent.verticalCenter
                text: String(card.number + 1)
                color: Ryce.Palette.fg2
                font.pixelSize: Ui.meta
            }
            Label {
                id: nameLabel
                anchors.left: numberLabel.right
                anchors.leftMargin: 8
                anchors.right: usage.visible ? usage.left : parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: card.name
                color: Ryce.Palette.fg0
                font.pixelSize: Ui.body
                elide: Text.ElideRight
            }
            Label {
                id: usage
                visible: card.current
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: "en uso"
                color: Ryce.Palette.fg2
                font.pixelSize: Ui.meta
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onEntered: card.hovered()
        onClicked: card.picked()
    }
}
