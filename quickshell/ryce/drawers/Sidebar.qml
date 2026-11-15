import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import qs
import qs as Ryce
import qs.agents
import qs.desk

// The sidebar (SUPER+a): a drawer that slides out of the screen's right edge, in the
// frame's opaque bg0, under the bar's zone and gaps_out from the top and the bottom like a
// tiled window. Where it meets the edge it flares into it with the frame's concave corner
// (the volume OSD's language), its free corners round convex to the same radius; Tinta's
// 0 radius makes it a plain slab. No exclusive zone (it never moves a window); Escape or
// a click anywhere else closes it.
// Built once per screen and never unmapped, for the reasons AriaWindow gives: closed, it
// sits on the Bottom layer with no input and the drawer hidden. DrawerMotion moves it on
// the render thread; the data (the board's clock, player, cava, controls, /proc) wakes
// only once it is in (`live`), so nothing forks or parses mid-slide.
PanelWindow {
    id: win
    property bool shown: false
    property real toggledAt: 0
    signal closeRequested()
    signal rested()                         // closed and still again
    readonly property bool moving: reveal.running
    property bool live: false
    property bool breathing: false          // from in to still again: AgentBoard.animate

    readonly property int fillet: Ryce.Palette.frameRadius
    readonly property int gap: Ryce.Palette.gapsOut
    readonly property int reach: Ui.panelWidth
    readonly property int slack: 24        // room for a curve that overshoots (Ola)

    anchors { top: true; right: true; bottom: true }
    margins.top: Ryce.Palette.frameTop
    implicitWidth: slack + reach
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    mask: shown ? null : noInput
    Region { id: noInput }

    WlrLayershell.namespace: "qs-sidebar"
    // On Overlay from the opening until the drawer is hidden again: bound to `shown`, a
    // close would drop it to Bottom for a beat before the leave starts.
    WlrLayershell.layer: drawer.visible ? WlrLayer.Overlay : WlrLayer.Bottom
    WlrLayershell.keyboardFocus: shown ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    onShownChanged: shown ? open() : close()
    Component.onCompleted: if (shown) closeRequested()     // never opens itself (AriaWindow)
    function open() {
        drawer.visible = true;
        drawer.forceActiveFocus();
        reveal.show();
    }
    function close() {
        live = false;
        reveal.hide();
    }

    DrawerMotion {
        id: reveal
        panel: drawer
        content: content
        tiers: [clock, board, music, controls, system]
        home: win.slack
        away: win.slack + win.reach
        contentHome: Ui.pad
        onEntered: if (win.shown) {
            win.live = true;
            win.breathing = true;
        }
        // Hiding the drawer also renders the frame that commits the move to Bottom.
        onRested: if (!win.shown) {
            drawer.visible = false;
            win.breathing = false;
            win.rested();
        }
    }

    // Armed once the drawer is in: the move to Overlay and the keyboard only reach the
    // compositor with the next frame, and a grab that comes first is cleared at once.
    HyprlandFocusGrab {
        active: win.shown && !reveal.arriving
        windows: [win]
        onCleared: win.closeRequested()
    }

    Item {
        id: drawer
        visible: false                      // open() and the leave own it
        width: win.width
        height: win.height
        Keys.onEscapePressed: win.closeRequested()

        FrameProbe {
            name: "sidebar"
            busy: reveal.running
            opening: win.shown
            since: win.toggledAt
        }

        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer

            // Flare, convex corner, side, convex corner, flare; then back along the
            // screen's edge, past it by `slack` for an overshooting curve.
            ShapePath {
                id: edge
                readonly property real f: win.fillet
                readonly property real e: win.reach                     // the screen's edge, open
                readonly property real t: win.gap                       // where the top flare starts
                readonly property real b: drawer.height - win.gap       // where the bottom flare ends

                fillColor: Ryce.Palette.bg0
                strokeWidth: -1
                startX: edge.e
                startY: edge.t
                PathArc { x: edge.e - edge.f; y: edge.t + edge.f; radiusX: edge.f; radiusY: edge.f }
                PathLine { x: edge.f; y: edge.t + edge.f }
                PathArc { x: 0; y: edge.t + 2 * edge.f; radiusX: edge.f; radiusY: edge.f; direction: PathArc.Counterclockwise }
                PathLine { x: 0; y: edge.b - 2 * edge.f }
                PathArc { x: edge.f; y: edge.b - edge.f; radiusX: edge.f; radiusY: edge.f; direction: PathArc.Counterclockwise }
                PathLine { x: edge.e - edge.f; y: edge.b - edge.f }
                PathArc { x: edge.e; y: edge.b; radiusX: edge.f; radiusY: edge.f }
                PathLine { x: edge.e + win.slack; y: edge.b }
                PathLine { x: edge.e + win.slack; y: edge.t }
            }
        }

        // DrawerMotion owns x and every tier's opacity.
        ColumnLayout {
            id: content
            y: win.gap + win.fillet + 18
            width: win.reach - 2 * Ui.pad
            height: win.height - win.gap - win.fillet - y - Ui.pad
            spacing: 0

            Clock {
                id: clock
                Layout.fillWidth: true
            }
            AgentBoard {
                id: board
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.topMargin: 26
                active: win.live
                animate: win.breathing
                onFocusRequested: win.closeRequested()
            }
            // No player: the section is one quiet line. Cover and spectrum need a player;
            // cava runs only while something plays and the drawer is in.
            ColumnLayout {
                id: music
                Layout.fillWidth: true
                Layout.topMargin: 18
                spacing: 0

                SectionRule {
                    Layout.fillWidth: true
                    label: "música"
                    meta: player.player === null ? "nada sonando" : ""
                    metaColor: Ryce.Palette.fg2
                }
                Player {
                    id: player
                    Layout.fillWidth: true
                    Layout.topMargin: 14
                    visible: player.player !== null
                    active: win.live
                }
                // Its room follows the player, not `live`: closing must not reflow the
                // content while it fades.
                Cava {
                    readonly property bool playing: player.player !== null && player.player.isPlaying
                    Layout.fillWidth: true
                    Layout.topMargin: 12
                    visible: playing
                    active: win.live && playing
                }
            }
            ColumnLayout {
                id: controls
                Layout.fillWidth: true
                Layout.topMargin: 22
                spacing: 0

                SectionRule {
                    Layout.fillWidth: true
                    label: "controles"
                }
                Controls {
                    Layout.fillWidth: true
                    Layout.topMargin: 14
                    active: win.live
                }
            }
            SystemLine {
                id: system
                Layout.fillWidth: true
                Layout.topMargin: 18
                active: win.live
            }
        }
    }
}
