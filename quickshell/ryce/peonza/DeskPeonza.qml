import QtQuick
import Quickshell
import QtQuick.Shapes
import Quickshell.Hyprland
import qs as Ryce
import qs.desk

// The spinning peonza on one monitor's desk: a DeskWindow (Bottom layer, no input) with
// the brand's `think` state, 72 frames of 96 px in one strip (themes/<id>/peonza/desk.png,
// theme/peonza/gen.py), standing on the picture itself over a thin floor ellipse in the
// theme's shadow ink, no tile; on Ola's pale print a light peonza vanishes, so there it
// stands on Ola's own card. It spins for as long as the desk is seen (no window, or the
// empty `despejado-N` of Super+E) and rests the moment a tiled window, a window over it,
// the scratchpad, a drawer or the switch hides it. It turns as the boot peonza does, 60
// frames a second, one turn in 1.2 s: a FrameAnimation runs with the monitor's own frames
// and the frame shown comes from the time gone by, so the 144 Hz and the 72 Hz screens
// turn at the same speed and no frame waits on a timer out of step with the display. A
// step only moves the clipped strip (no decode, no texture upload).
// RYCE_PERF_PROBE=1 logs the spin's frames every 10 s: ticks, steps, mean and worst.
// Where: the corner the theme's desk leaves free. Bottom right in Origen, Grafito and
// Ola (their stats are bottom left); Papel's bottom right is the cover's caption, so
// there it hangs mid-height on the right edge, between the Hito card and the corner.
// Tinta's corners are the binary clock's and the HUD's: there it stands bottom centre,
// in the layer box (890,896)–(1030,1036) at 1920×1080 the sheet's drawings keep clear of
// (theme/wallpaper/ink.py). Every theme's layer box is that 140 px square.
Scope {
    id: desk
    property ShellScreen screen
    property bool on

    readonly property bool hyprland: !!Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE")
    readonly property HyprlandMonitor monitor: hyprland ? Hyprland.monitorFor(screen) : null
    readonly property HyprlandWorkspace workspace: monitor?.activeWorkspace ?? null
    // The scratchpad (a special workspace) shown over this monitor's desk.
    property bool special: !!monitor?.lastIpcObject?.specialWorkspace?.name
    // Seen: no tiled window and no floating one over the peonza. A window Hyprland has
    // not described yet counts as tiled. Outside Hyprland nothing says: take it as seen.
    readonly property bool bare: !workspace || !special && !workspace.toplevels.values.some(t => {
        const o = t.lastIpcObject;
        if (!o || !o.floating) return true;
        const box = win.box();
        return o.at[0] < box.x1 && o.at[0] + o.size[0] > box.x0 && o.at[1] < box.y1 && o.at[1] + o.size[1] > box.y0;
    })
    readonly property bool live: on && bare && !Ryce.Ui.deskCovered
    readonly property string spot: ({ papel: "edge", tinta: "centre" })[Ryce.Palette.themeId] ?? "corner"

    Connections {
        target: desk.hyprland ? Hyprland : null
        function onRawEvent(event) {
            const n = event.name;
            // activespecial: "<workspace name>,<monitor>", the name empty when it hides.
            if (n === "activespecial") {
                const at = event.data.lastIndexOf(",");
                if (event.data.slice(at + 1) === desk.monitor?.name) desk.special = event.data.slice(0, at) !== "";
            }
            // Floating state and geometry live in lastIpcObject: ask again when they move.
            if (["openwindow", "changefloatingmode", "movewindowv2", "windowtitlev2", "closewindow"].includes(n))
                Hyprland.refreshToplevels();
        }
    }

    readonly property bool tile: Ryce.Palette.themeId === "ola"
    readonly property bool probe: Quickshell.env("RYCE_PERF_PROBE") === "1"

    FrameAnimation {
        property real t                     // seconds into the current turn
        property int ticks
        property int steps
        property real worst
        property real since

        running: desk.live && strip.status === Image.Ready
        onTriggered: {
            t = (t + frameTime) % (top.frames / 60);
            const f = Math.floor(t * 60) % top.frames;
            if (f !== top.frame) {
                top.frame = f;
                steps++;
            }
            if (!desk.probe) return;
            ticks++;
            worst = Math.max(worst, frameTime);
            since += frameTime;
            if (since < 10) return;
            console.info(`ryce perf peonza ${desk.screen?.name}: ${ticks} ticks, ${steps} steps in ${since.toFixed(1)} s,`
                + ` mean ${(1000 * since / ticks).toFixed(1)} ms, worst ${(1000 * worst).toFixed(1)} ms`);
            ticks = 0;
            steps = 0;
            worst = 0;
            since = 0;
        }
    }

    DeskWindow {
        id: win
        screen: desk.screen
        shown: desk.on
        covered: Ryce.Ui.deskCovered
        lines: 1
        // Papel: only `right`, the layer shell centres it vertically; Tinta: only
        // `bottom`, centred horizontally.
        anchors { right: desk.spot !== "centre"; bottom: desk.spot !== "edge" }
        margins { right: 52; bottom: 44 }

        // The layer box in the monitor's layout coordinates, as Hyprland reports windows.
        function box() {
            const m = desk.monitor, w = m?.width ?? 0, h = m?.height ?? 0, s = implicitWidth;
            const x = desk.spot === "centre" ? (w - s) / 2 : w - margins.right - s;
            const y = desk.spot === "edge" ? (h - s) / 2 : h - margins.bottom - s;
            return { x0: (m?.x ?? 0) + x, y0: (m?.y ?? 0) + y, x1: (m?.x ?? 0) + x + s, y1: (m?.y ?? 0) + y + s };
        }

        content: Card {
            on: win.shown
            plain: !desk.tile
            pad: 0

            Reveal {
                on: win.shown
                order: desk.tile ? 1 : 0

                Item {
                    width: 116
                    height: 116

                    // The floor it spins on: under the tip (x 43.5, y 86 of the frame).
                    Shape {
                        anchors.fill: parent
                        preferredRendererType: Shape.CurveRenderer

                        ShapePath {
                            fillColor: Ryce.Palette.rgba(Ryce.Palette.light ? Ryce.Palette.fg0 : Ryce.Palette.bg0, 0.32)
                            strokeWidth: -1
                            PathAngleArc {
                                centerX: top.x + 43.5
                                centerY: top.y + 87
                                radiusX: 21
                                radiusY: 2.5
                                sweepAngle: 360
                            }
                        }
                    }
                    Item {
                        id: top
                        readonly property int size: 96
                        readonly property int frames: 72
                        property int frame: 0

                        // The tip on the box's centre line.
                        x: Math.round(58 - 43.5)
                        y: 4
                        width: size
                        height: size
                        clip: true

                        Image {
                            id: strip
                            x: -top.frame * top.size
                            source: "file://" + Ryce.Palette.themeDir + "/peonza/desk.png"
                            sourceSize.height: top.size
                            smooth: false           // drawn at this size: 1:1, no filtering
                            asynchronous: true
                            onStatusChanged: if (status === Image.Error) console.warn(`ryce peonza: no ${source}`)
                        }
                    }
                }
            }
        }
    }
}
