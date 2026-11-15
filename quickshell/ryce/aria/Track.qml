import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import Quickshell.Widgets
import qs
import qs as Ryce
import qs.bar

// One row of a list: a song, a playlist or an album. A lead (the track number, a glyph,
// or a small cover), a title over a quiet line, a trailing note and, when given, one
// glyph button at the end (`action`: the lists' «aleatorio»). The one playing wears the
// media hue; the pointer lifts a quiet ground (Tinta: a 1 px box). `muted` dims a row
// that leads nowhere (a list with no songs left).
Item {
    id: row
    property string lead
    property bool glyph: false             // the lead is a Nerd Font glyph
    property string cover
    property string title
    property string sub
    property string trail
    property bool current: false
    property bool muted: false
    property string action                  // a glyph; "" for none
    property string actionName
    signal clicked()
    signal actionClicked()

    readonly property string skin: BarUi.skin

    implicitHeight: cover !== "" ? 50 : 42
    Accessible.role: Accessible.ListItem
    Accessible.name: title + (sub !== "" ? ", " + sub : "")

    Rectangle {
        visible: row.skin !== "box"
        anchors.fill: parent
        radius: row.skin === "capsule" ? height / 2 : Math.min(Ryce.Palette.pillRadius, 8)
        color: Ryce.Palette.bg2
        opacity: mouse.containsMouse ? 1 : row.current ? 0.55 : 0
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }
    Shape {
        visible: row.skin === "box" && (mouse.containsMouse || row.current)
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: "transparent"
            strokeColor: mouse.containsMouse ? Ryce.Palette.fg2 : Ryce.Palette.line
            strokeWidth: 1
            PathRectangle {
                x: 0.5
                y: 0.5
                width: row.width - 1
                height: row.height - 1
                radius: Math.max(0, Ryce.Palette.pillRadius - 0.5)
            }
        }
    }

    RowLayout {
        z: 1        // above the row's area: the action takes its own clicks
        anchors.fill: parent
        opacity: row.muted ? 0.55 : 1
        anchors.leftMargin: row.skin === "capsule" ? 14 : 8
        anchors.rightMargin: anchors.leftMargin
        spacing: 12

        ClippingRectangle {
            visible: row.cover !== ""
            implicitWidth: 36
            implicitHeight: 36
            radius: Math.min(Ryce.Palette.rounding, 8)
            color: Ryce.Palette.bg2

            Image {
                anchors.fill: parent
                source: row.cover
                sourceSize: Qt.size(72, 72)
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
            }
        }
        Label {
            visible: row.cover === ""
            Layout.preferredWidth: 22
            horizontalAlignment: Text.AlignRight
            text: row.current ? Ui.volHigh : row.lead
            color: row.current ? Ryce.Palette.hueMedia : Ryce.Palette.fg2
            font.family: row.current || row.glyph ? Ryce.Palette.fontIcon : Ryce.Palette.fontUi
            font.pixelSize: row.current || row.glyph ? 15 : Ui.meta
            font.features: { "tnum": 1 }
            elide: Text.ElideNone
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1

            Label {
                Layout.fillWidth: true
                text: row.title
                color: row.current ? Ryce.Palette.hueMedia : Ryce.Palette.fg0
            }
            Label {
                visible: row.sub !== ""
                Layout.fillWidth: true
                text: row.sub
                color: Ryce.Palette.fg2
                font.pixelSize: Ui.meta
            }
        }
        Label {
            visible: row.trail !== ""
            text: row.trail
            color: Ryce.Palette.fg2
            font.pixelSize: Ui.meta
            font.features: { "tnum": 1 }
            elide: Text.ElideNone
        }
        IconButton {
            visible: row.action !== ""
            Layout.rightMargin: -4
            size: 28
            glyph: row.action
            Accessible.name: row.actionName
            onClicked: row.actionClicked()
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: row.clicked()
    }
}
