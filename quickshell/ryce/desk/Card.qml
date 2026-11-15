import QtQuick
import QtQuick.Effects
import QtQuick.Shapes

// One desk widget on its own ground (DeskUi: fill, alpha, hairline, shadow) with room
// around the text, so no widget blends into the wallpaper or into its neighbour. Drawn
// like the bar's plates: a RectangularShadow (a distance shader, no blur pass) and a
// stroke-only Shape, never a bordered transparent Rectangle (QTBUG-137166). The ground
// fades and rises with the widget's first line (`on`), and leaves with it. A card that
// must not follow the theme's desk (Tinta's binary clock) sets its own look.
Item {
    id: card
    property bool on
    property color ground: DeskUi.ground
    property int radius: DeskUi.radius
    property bool outlined: DeskUi.outlined
    property color hairline: DeskUi.hairline
    property int pad: DeskUi.pad
    property bool plain: false              // no ground, shadow or hairline: content only
    default property alias body: inner.data

    implicitWidth: inner.width + 2 * pad
    implicitHeight: inner.height + 2 * pad

    Reveal {
        visible: !card.plain
        anchors.fill: parent
        on: card.on

        RectangularShadow {
            anchors.fill: parent
            offset.y: 2
            blur: 10
            radius: card.radius
            color: DeskUi.shadow
        }
        Rectangle {
            anchors.fill: parent
            radius: card.radius
            color: card.ground
        }
        Shape {
            visible: card.outlined
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer

            ShapePath {
                fillColor: "transparent"
                strokeColor: card.hairline
                strokeWidth: 1
                PathRectangle {
                    x: 0.5
                    y: 0.5
                    width: Math.max(0, card.width - 1)
                    height: Math.max(0, card.height - 1)
                    radius: Math.max(0, card.radius - 0.5)
                }
            }
        }
    }
    Item {
        id: inner
        x: card.pad
        y: card.pad
        width: childrenRect.width
        height: childrenRect.height
    }
}
