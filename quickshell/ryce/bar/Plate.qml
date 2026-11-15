import QtQuick
import QtQuick.Effects
import QtQuick.Shapes
import qs as Ryce

// One floating ground on the bar: bg0 at the theme's plate alpha (alpha.bar, chosen for
// text contrast over the brightest wallpaper pixel) on a soft shadow, the wallpaper
// showing all around it. Tinta's boxes and Grafito's instrument plates carry a 1 px
// outline (on Grafito's black dot plate a black plate alone would vanish). `lit` fades a
// hover ground in.
// The shadow is RectangularShadow, a signed-distance shader with no blur pass, never a
// MultiEffect over live content: resizing a plate only moves its uniforms.
Item {
    id: plate
    property bool ground: true          // false: only the hover ground (Grafito's readouts)
    property bool lit: false
    property real radius: BarUi.radius

    RectangularShadow {
        visible: plate.ground
        anchors.fill: parent
        offset.y: 2
        blur: 10
        radius: plate.radius
        // On paper (a light scheme) a shadow in bg0 is the paper itself: it is cast in
        // the ink instead, faint, so a cream plate still lifts off cream.
        color: Ryce.Palette.light ? Ryce.Palette.rgba(Ryce.Palette.fg0, 0.16) : Ryce.Palette.rgba(Ryce.Palette.bg0, 0.45)
    }
    Rectangle {
        visible: plate.ground
        anchors.fill: parent
        radius: plate.radius
        color: BarUi.plate
    }
    Rectangle {
        anchors.fill: parent
        radius: plate.radius
        color: Ryce.Palette.bg2
        opacity: plate.lit ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Ryce.Palette.motionMs * 0.5; easing.type: Easing.OutCubic } }
    }
    // The outline: a stroke-only Shape, never a bordered transparent Rectangle, which
    // erases what lies beneath it (QTBUG-137166).
    Shape {
        visible: plate.ground && (BarUi.skin === "box" || BarUi.skin === "bare")
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: "transparent"
            strokeColor: plate.lit ? Ryce.Palette.fg2 : Ryce.Palette.line
            strokeWidth: 1
            PathRectangle {
                x: 0.5
                y: 0.5
                width: Math.max(0, plate.width - 1)
                height: Math.max(0, plate.height - 1)
                radius: Math.max(0, plate.radius - 0.5)
            }
        }
    }
}
