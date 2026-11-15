import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import qs as Ryce
import qs.agents

// The bar on one screen: no band and no blur, only plates floating over the wallpaper
// (Plate, BarUi.lift). Left: the live peonza, the machine (Stats) and the focused
// window. Centre: the workspaces. Right: media, tray, sessions, layout, volume, clock
// (Status). Every element rides its own plate, except in Grafito's instrument skin,
// whose bare readouts share three: left group, workspaces, right group. The surface
// ignores exclusive zones (frame/EdgeReserve carries the zone) and reaches gaps_out past
// it so the plates' shadows are not cut; input stops at the zone. The clock drops a
// month under it (CalendarWindow), loaded only while it shows.
PanelWindow {
    id: bar
    signal sidebarToggleRequested()

    readonly property bool hyprland: !!Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE")
    readonly property bool grouped: BarUi.skin === "bare"
    readonly property real workspacesEnd: workspaces.start + workspaces.contentWidth + BarUi.inset

    anchors { top: true; left: true; right: true }
    implicitHeight: Ryce.Palette.frameTop + Ryce.Palette.gapsOut
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"
    mask: Region { width: bar.width; height: Ryce.Palette.frameTop }

    WlrLayershell.namespace: "qs-bar"
    WlrLayershell.layer: WlrLayer.Top
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    Item {
        id: zone
        y: BarUi.lift
        width: parent.width
        height: BarUi.band

        // Grafito's group plates; the other skins plate each element on its own.
        Plate {
            visible: bar.grouped
            x: BarUi.edge
            width: (focus.width > 0 ? focus.x + focus.width : stats.x + stats.width) + BarUi.groupPad - x
            height: BarUi.chipHeight
            anchors.verticalCenter: parent.verticalCenter
        }
        Plate {
            visible: bar.grouped
            x: status.x + BarUi.gap - BarUi.groupPad
            width: status.width - BarUi.gap + 2 * BarUi.groupPad
            height: BarUi.chipHeight
            anchors.verticalCenter: parent.verticalCenter
        }

        // The peonza: a click flicks it (one turn, or a nod while a session waits). It
        // takes the whole corner up to the screen's edges, so a pointer flung into the
        // corner lands on it (the plate alone starts gaps_out in).
        Plate {
            x: BarUi.edge
            width: BarUi.chipHeight
            height: BarUi.chipHeight
            anchors.verticalCenter: parent.verticalCenter
            ground: !bar.grouped
            lit: spin.containsMouse
        }
        Peonza {
            id: peonza
            x: BarUi.edge + (BarUi.chipHeight - BarUi.peonzaPx) / 2
            anchors.verticalCenter: parent.verticalCenter
            size: BarUi.peonzaPx
            mode: Roster.counts.waiting > 0 ? "waiting" : Roster.counts.busy > 0 ? "busy" : "idle"
            scale: spin.pressed ? 0.92 : 1
            Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
        }
        MouseArea {
            id: spin
            y: -zone.y
            width: BarUi.edge + BarUi.chipHeight
            height: Ryce.Palette.frameTop
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            Accessible.role: Accessible.Button
            Accessible.name: "Peonza"
            onClicked: peonza.flick()
        }
        Stats {
            id: stats
            x: BarUi.edge + BarUi.chipHeight
            height: parent.height
        }

        // The focused window: its own plate, or, in Grafito, a dot after the network readout.
        Plate {
            visible: !bar.grouped && focus.width > 0
            opacity: focus.opacity
            x: focus.x - BarUi.padX
            width: focus.width + 2 * BarUi.padX
            height: BarUi.chipHeight
            anchors.verticalCenter: parent.verticalCenter
        }
        Rectangle {
            visible: bar.grouped && focus.width > 0
            x: stats.x + stats.width + Math.round((2 * BarUi.gap - BarUi.padX) / 2) - 1
            anchors.verticalCenter: parent.verticalCenter
            width: 2
            height: 2
            radius: 1
            color: Ryce.Palette.fg2
        }
        FocusLine {
            id: focus
            x: stats.x + stats.width + BarUi.gap + (bar.grouped ? BarUi.gap : BarUi.padX)
            width: implicitWidth
            height: parent.height
            hyprland: bar.hyprland
            workspace: workspaces.cleared ? 0 : workspaces.activeId     // a cleared desk has no window in focus
            maxWidth: Math.max(0, workspaces.start - BarUi.inset - x - BarUi.padX - 24)
        }

        Workspaces {
            id: workspaces
            anchors.fill: parent
            screen: bar.screen
            hyprland: bar.hyprland
        }

        Status {
            id: status
            anchors.right: parent.right
            anchors.rightMargin: BarUi.edge + (bar.grouped ? BarUi.groupPad : 0)
            height: parent.height
            room: bar.width - status.anchors.rightMargin - bar.workspacesEnd - 24
            hyprland: bar.hyprland
            calendarOpen: bar.calendarOpen
            onAgentsClicked: bar.sidebarToggleRequested()
            onClockClicked: bar.toggleCalendar()
        }
    }

    // The month under the clock, on this bar's screen. A click on the clock while it is
    // open first clears its focus grab (closing it) and then lands here: that click
    // closed it, so it must not open it again (DrawersRoot's sidebar does the same).
    property bool calendarOpen: false
    property real calendarDismissedAt: 0
    function toggleCalendar() {
        if (calendarOpen) closeCalendar();
        else if (Date.now() - calendarDismissedAt >= 300) {
            calendarOpen = true;
            calendarLoader.active = true;
        }
    }
    function closeCalendar() {
        if (!calendarOpen) return;
        calendarOpen = false;
        calendarDismissedAt = Date.now();
    }
    LazyLoader {
        id: calendarLoader

        CalendarWindow {
            screen: bar.screen
            shown: bar.calendarOpen
            onCloseRequested: bar.closeCalendar()
            onGone: if (!bar.calendarOpen) calendarLoader.active = false
        }
    }
}
