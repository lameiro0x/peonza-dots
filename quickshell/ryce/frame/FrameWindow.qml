import QtQuick
import QtQuick.Shapes
import Quickshell
import Quickshell.Wayland
import qs as Ryce

// What is left of the frame on one screen: its four corners, rounded concave to the
// theme's frame radius in opaque bg0, so the screen itself reads rounded. No rim and no
// band any more: the bar floats on plates (bar/BarWindow) and the windows keep the
// theme's gaps_out from the sides. A theme without a radius (Tinta) has no frame at
// all. Static: nothing here changes unless the theme does. Click-through (empty input
// mask).
PanelWindow {
    id: win
    readonly property int r: Ryce.Palette.frameRadius

    visible: r > 0
    anchors { top: true; left: true; right: true; bottom: true }
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"
    mask: Region {}

    WlrLayershell.namespace: "qs-frame"
    WlrLayershell.layer: WlrLayer.Top
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: Ryce.Palette.bg0
            fillRule: ShapePath.OddEvenFill
            strokeWidth: -1

            PathRectangle { x: 0; y: 0; width: win.width; height: win.height }
            PathRectangle { x: 0; y: 0; width: win.width; height: win.height; radius: win.r }
        }
    }
}
