import QtQuick
import Quickshell
import Quickshell.Wayland
import qs as Ryce

// A desk widget's surface: Bottom layer (over the wallpaper, under every window), no
// keyboard, sized to its content; no pointer either unless `interactive` (Hito's card
// and its filters), and never while covered. Mapped while shown and while its lines are
// still leaving; `lines` is how many Reveal steps the content staggers through.
// `covered` (a drawer over the desk) fades it out of the way and back, still mapped and
// hidden meanwhile (a ticking clock renders nothing): unmapping would rebuild every
// widget's window on every screen each time a drawer closes.
PanelWindow {
    id: win
    property bool shown
    property bool covered
    property int lines: 1
    property alias content: holder.data
    property bool interactive: false
    readonly property int pad: 12           // room for the rise, so it is never clipped

    visible: shown || leaving.running
    onShownChanged: if (!shown) leaving.restart()
    onCoveredChanged: {
        fade.stop();
        fade.from = holder.opacity;         // from wherever a fade caught midway left it
        fade.to = covered ? 0 : 1;
        fade.duration = Math.round(Ryce.Palette.motionMs * (covered ? 0.6 : 1));
        fade.start();
    }
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    mask: interactive && !covered ? null : noInput
    Region { id: noInput }
    implicitWidth: holder.childrenRect.width + 2 * pad
    implicitHeight: holder.childrenRect.height + 2 * pad

    WlrLayershell.namespace: "qs-desk"
    WlrLayershell.layer: WlrLayer.Bottom
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    Timer {
        id: leaving
        interval: Ryce.Palette.motionMs * 1.25 + win.lines * Math.round(Ryce.Palette.motionMs / 5)
    }

    Item {
        id: holder
        x: win.pad
        y: win.pad
        visible: !win.covered || fade.running
    }
    Component.onCompleted: holder.opacity = covered ? 0 : 1
    OpacityAnimator {
        id: fade
        target: holder
        easing.type: Easing.BezierSpline
        easing.bezierCurve: Ryce.Palette.motionCurve
    }
}
