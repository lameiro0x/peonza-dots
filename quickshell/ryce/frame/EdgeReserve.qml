import QtQuick
import Quickshell
import Quickshell.Wayland

// An invisible strip that only reserves space, so tiled windows sit under the bar. The
// frame and the bar ignore exclusive zones (the frame covers the screen, the bar's
// surface reaches past its zone for the plates' shadows); this carries it instead.
// FrameRoot reserves the top edge only.
PanelWindow {
    id: reserve
    required property string edge      // "top" | "left" | "right" | "bottom"
    required property int size

    anchors {
        top: reserve.edge !== "bottom"
        bottom: reserve.edge !== "top"
        left: reserve.edge !== "right"
        right: reserve.edge !== "left"
    }
    implicitWidth: 1
    implicitHeight: 1
    exclusionMode: ExclusionMode.Normal
    exclusiveZone: size
    color: "transparent"
    mask: Region {}

    WlrLayershell.namespace: "qs-edge"
    WlrLayershell.layer: WlrLayer.Bottom
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
}
