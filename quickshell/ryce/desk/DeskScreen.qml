import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Services.Mpris
import qs as Ryce
import qs.osd
import qs.wall

// Everything ambient on one monitor. The desk is `bare` while the monitor's active
// workspace holds no window: only then is it seen, so only then does anything sample,
// tick or animate. The wall sits on the Background layer, the widgets on Bottom over it.
// A theme's own always-on widgets (its `desktop.ambient` list: hud, binclock, edgeviz)
// exist only while the theme lists them; the HUD is its theme's stats, so it replaces
// the desk stats there (they would share the bottom-left corner with the binary clock).
// Every widget with something to read sits on a Card; EdgeViz is an edge ornament, bare.
Scope {
    id: desk
    property ShellScreen screen
    property bool clockOn
    property bool statsOn
    property bool wallOn

    readonly property HyprlandMonitor monitor: Hyprland.monitorFor(screen)
    readonly property HyprlandWorkspace workspace: monitor?.activeWorkspace ?? null
    // Outside Hyprland nothing says what covers the desk: take it as seen.
    readonly property bool bare: !workspace || workspace.toplevels.values.length === 0
    // Clear of the screen's rounded corners; the top margins below clear the bar's zone.
    readonly property int left: 52
    readonly property int bottom: 44
    readonly property var wants: Ryce.Palette.ambient      // the theme's always-on widgets
    // Every theme keeps the same corners: the clock top left under the bar, the stats bottom
    // left, the Hito card top right (HitoDesk). Ola too since 2026-11-15, the user's choice:
    // its cards are solid, so the cartouche behind the clock costs nothing.
    readonly property bool clockRight: false
    readonly property bool playing: Mpris.players.values.some(p => p.isPlaying)

    function showOsd() { osd.flash(); }

    LazyLoader {
        // A window over the desk (fullscreen included) unloads it: zero cost, the static
        // wallpaper below shows.
        active: desk.wallOn && desk.bare

        Wall { screen: desk.screen }
    }

    DeskWindow {
        id: clockWin
        screen: desk.screen
        shown: desk.clockOn
        covered: Ryce.Ui.deskCovered
        lines: 3
        anchors { top: true; left: !desk.clockRight; right: desk.clockRight }
        margins { top: Ryce.Palette.frameTop + 40; left: desk.left; right: desk.left }

        content: Card {
            on: clockWin.shown

            DeskClock {
                shown: clockWin.shown
                live: desk.clockOn && desk.bare && !Ryce.Ui.deskCovered
            }
        }
    }

    DeskWindow {
        id: statsWin
        screen: desk.screen
        shown: desk.statsOn && !desk.wants.includes("hud")
        covered: Ryce.Ui.deskCovered
        lines: 7
        anchors { bottom: true; left: true }
        margins { bottom: desk.bottom; left: desk.left }

        content: Card {
            on: statsWin.shown

            DeskStats {
                shown: statsWin.shown
                live: shown && desk.bare && !Ryce.Ui.deskCovered
            }
        }
    }

    LazyLoader {
        active: desk.wants.includes("hud")

        // Bottom right, facing the binary clock: the top right is the Hito card's. Its
        // layer box (the card and its shadow pad) ends 24 px above the wallpaper's title
        // block (Plano's cajetín, from y 942 of 1080 down, theme/wallpaper/ink.py TB and
        // DESK), scaled with the screen like the sheet.
        DeskWindow {
            id: hudWin
            screen: desk.screen
            shown: true
            covered: Ryce.Ui.deskCovered
            anchors { bottom: true; right: true }
            margins {
                bottom: Math.round((desk.screen?.height ?? 1080) * (1080 - 942 + 24) / 1080)
                right: DeskUi.rightMargin(desk.screen?.width ?? 1920, hudWin.pad)
            }

            content: Card {
                on: hudWin.shown

                Hud { live: desk.bare && !Ryce.Ui.deskCovered }
            }
        }
    }

    LazyLoader {
        active: desk.wants.includes("binclock")

        DeskWindow {
            id: binWin
            screen: desk.screen
            shown: true
            covered: Ryce.Ui.deskCovered
            anchors { bottom: true; left: true }
            margins { bottom: desk.bottom; left: desk.left }

            // Pinned as it stood at e398d3b, the user's pick: that day's plate (bg0 at the
            // bar's 0.82, the line at full strength), whatever the desk's alpha, rounding or
            // hairline become since; only its corners changed, square since 2026-11-15.
            content: Card {
                on: binWin.shown
                ground: Ryce.Palette.rgba(Ryce.Palette.bg0, 0.82)
                radius: 0
                outlined: true
                hairline: Ryce.Palette.line
                pad: 22

                BinClock { live: desk.bare && !Ryce.Ui.deskCovered }
            }
        }
    }

    LazyLoader {
        active: desk.wants.includes("edgeviz")

        // On the screen edge itself, between the desk clock and the binary clock;
        // mapped only while something plays.
        DeskWindow {
            id: edge
            screen: desk.screen
            shown: desk.playing && desk.bare
            anchors.left: true

            // Over the window's padding: the lines start at the edge.
            content: EdgeViz { x: -edge.pad; active: edge.shown }
        }
    }

    VolumeOsd {
        id: osd
        screen: desk.screen
        armed: !Hyprland.focusedMonitor || Hyprland.focusedMonitor === desk.monitor
    }
}
