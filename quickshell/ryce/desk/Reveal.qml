import QtQuick
import qs as Ryce

// One line of a desk widget: fades in and rises a few pixels, `order` steps after the
// first, with the theme's own duration and curve. Leaving runs the same way back.
Item {
    id: reveal
    property bool on
    property int order
    readonly property int stagger: Math.round(Ryce.Palette.motionMs / 5)
    property real p: on ? 1 : 0

    implicitWidth: childrenRect.width
    implicitHeight: childrenRect.height
    opacity: p
    transform: Translate { y: Math.round((1 - reveal.p) * 8) }

    Behavior on p {
        SequentialAnimation {
            PauseAnimation { duration: reveal.order * reveal.stagger }
            NumberAnimation {
                duration: Ryce.Palette.motionMs
                easing.type: Easing.BezierSpline
                easing.bezierCurve: Ryce.Palette.motionCurve
            }
        }
    }
}
