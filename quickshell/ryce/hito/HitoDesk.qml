import QtQuick
import Quickshell
import Quickshell.Hyprland
import qs as Ryce
import qs.desk

// Hito's card on one monitor's desk: a DeskWindow (Bottom layer, taking the pointer for
// its filters) seen only while the monitor's active workspace holds no window, and live
// (fetching) only then. Its filter and project are the user's, kept in hito.json.
// Each theme puts it where its wallpaper and its own desk widgets leave room: the top
// right, under the bar, clear of the clock (top left) and the stats or binary clock
// (bottom left); in Tinta its right edge is the title block's, like the HUD under it
// (DeskUi.rightMargin); elsewhere its right edge is the desk peonza's.
Scope {
    id: desk
    property ShellScreen screen
    property bool on
    property Hito hito
    property var prefs                      // HitoRoot's JsonAdapter
    readonly property var filters: ["hoy", "atrasadas", "todas", "proyecto"]

    readonly property HyprlandMonitor monitor: Hyprland.monitorFor(screen)
    readonly property HyprlandWorkspace workspace: monitor?.activeWorkspace ?? null
    // Outside Hyprland nothing says what covers the desk: take it as seen.
    readonly property bool bare: !workspace || workspace.toplevels.values.length === 0
    readonly property bool live: on && bare

    onLiveChanged: if (live) hito.touch()

    DeskWindow {
        id: win
        screen: desk.screen
        shown: desk.on
        covered: Ryce.Ui.deskCovered
        interactive: true
        lines: 10
        anchors { top: true; right: true }
        margins {
            top: Ryce.Palette.frameTop + 40
            right: DeskUi.rightMargin(desk.screen?.width ?? 1920, win.pad)
        }

        content: Card {
            on: win.shown

            HitoCard {
                shown: win.shown
                hito: desk.hito
                // A hand-edited hito.json with a word it does not know falls back to «hoy».
                filter: desk.filters.includes(desk.prefs.deskFilter) ? desk.prefs.deskFilter : "hoy"
                project: desk.prefs.deskProject
                onFilterPicked: key => desk.prefs.deskFilter = key
                onProjectPicked: key => desk.prefs.deskProject = key
            }
        }
    }
}
