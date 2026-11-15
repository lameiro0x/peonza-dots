import QtQuick
import Quickshell.Widgets
import qs
import qs as Ryce

// One theme in the selector, shown in its own stance: its wallpaper, its name in its own
// display face, its tagline in its own UI face, its colours, its corner radius. Only the
// focus ring and the lift answer to the current theme's motion. `info` is the theme's
// entry in Palette.catalog (generated from contracts/themes).
Item {
    id: card
    required property string themeId
    required property int order
    property bool focused: false
    property bool current: false
    signal hovered()
    signal picked()

    readonly property var info: (Ryce.Palette.catalog ?? {})[themeId] ?? null
    readonly property int radius: info ? info.rounding : Ryce.Palette.rounding
    readonly property int swatchRadius: Math.min(info ? info.pill_radius : Ryce.Palette.pillRadius, 6)
    readonly property bool dotMatrix: info ? info.fonts.display_min_px > 0 : false
    function c(key, fallback) { return info && info.colors[key] ? info.colors[key] : fallback; }

    // Enters after the drawer is under way, one beat after the card on its left; then
    // only the focused card moves, lifting a few pixels on the theme's own curve.
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
        PauseAnimation { duration: Math.round(Ryce.Palette.motionMs * 0.3) + card.order * Math.round(Ryce.Palette.motionMs / 5) }
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
    Accessible.name: (info ? info.name : themeId) + (current ? ", en uso" : "")

    Rectangle {
        id: face
        width: parent.width
        height: column.y + column.height + 14
        radius: card.radius
        color: card.c("bg1", Ryce.Palette.bg1)
        border.width: 1
        border.color: card.focused ? card.c("fg2", Ryce.Palette.fg2) : card.c("line", Ryce.Palette.line)
        Behavior on border.color { ColorAnimation { duration: 140 } }

        ClippingRectangle {
            id: thumb
            x: 7
            y: 7
            width: parent.width - 14
            height: Math.round(width * 9 / 16)
            radius: Math.max(0, card.radius - 4)
            color: card.c("bg0", Ryce.Palette.bg0)

            Image {
                anchors.fill: parent
                // Through the theme's own folder, never `current/`.
                source: "file://" + Ryce.Palette.stateDir + "/" + card.themeId + "/wallpaper/thumb.png"
                sourceSize.width: 480
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                smooth: true
            }
        }

        Column {
            id: column
            x: 15
            y: thumb.y + thumb.height + 14
            width: parent.width - 30
            spacing: 6

            Label {
                width: parent.width
                text: card.info ? card.info.name : card.themeId
                color: card.c("fg0", Ryce.Palette.fg0)
                font.family: card.info ? card.info.fonts.display : Ryce.Palette.fontDisplay
                font.pixelSize: Math.max(26, card.info ? card.info.fonts.display_min_px : 0)
                font.weight: card.dotMatrix ? Font.Bold : Font.Normal
            }
            Label {
                id: tagline
                width: parent.width
                height: 2 * Math.ceil(taglineMetrics.lineSpacing)      // two lines, so the cards align
                text: card.info ? card.info.tagline : ""
                color: card.c("fg1", Ryce.Palette.fg1)
                font.family: card.info ? card.info.fonts.ui : Ryce.Palette.fontUi
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                verticalAlignment: Text.AlignTop

                FontMetrics {
                    id: taglineMetrics
                    font: tagline.font
                }
            }
            Item {
                width: parent.width
                height: 14

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6

                    Repeater {
                        model: ["bg1", "fg1", "pill", "tint"]

                        Rectangle {
                            required property string modelData
                            width: 14
                            height: 14
                            radius: card.swatchRadius
                            color: card.c(modelData, Ryce.Palette.bg2)
                            border.width: modelData === "bg1" ? 1 : 0
                            border.color: card.c("line", Ryce.Palette.line)
                        }
                    }
                    Item { width: 4; height: 1 }
                    // The theme's signal: as small as it is on the desktop.
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 6
                        height: 6
                        radius: 3
                        color: card.c("signal", Ryce.Palette.fg2)
                    }
                }
                Label {
                    visible: card.current
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: "en uso"
                    color: card.c("fg2", Ryce.Palette.fg2)
                    font.family: card.info ? card.info.fonts.ui : Ryce.Palette.fontUi
                    font.pixelSize: 11
                }
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
