import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Hyprland
import qs
import qs as Ryce

// The agent board: every live session from agentd's roster, grouped by workspace (the
// ones waiting for you first inside each, then the working, then those whose turn is
// over). The roster polls by itself (the bar needs it always); this only reads it.
ColumnLayout {
    id: board
    property bool active
    // The waiting dots may breathe, all on one beat (every 2.4 s, from the drawer in until
    // it is still again).
    property bool animate
    property int beat: 0
    property real now: Date.now() / 1000
    // sessionId → true for rows whose subagents are open. Kept here, not in the row:
    // a roster update must never fold one back.
    property var expanded: ({})
    signal focusRequested()       // a row sent Hyprland to its workspace

    // Hyprland 0.57 evaluates dispatch arguments as Lua, so only a validated integer from
    // the roster is formatted into the call (contracts/constants.json dispatch_focus_ws).
    function focusWorkspace(ws) {
        if (!Number.isInteger(ws) || ws < 1) return;
        Hyprland.dispatch(`hl.dsp.focus({ workspace = ${ws} })`);
        board.focusRequested();
    }
    function toggle(sid) {
        const next = Object.assign({}, expanded);
        next[sid] = !next[sid];
        expanded = next;
    }

    spacing: 6

    Timer {
        running: board.active
        interval: 15000
        repeat: true
        triggeredOnStart: true
        onTriggered: board.now = Date.now() / 1000
    }

    Timer {
        running: board.animate && Roster.counts.waiting > 0
        interval: 2400
        repeat: true
        triggeredOnStart: true
        onTriggered: board.beat++
    }

    SectionRule {
        Layout.fillWidth: true
        label: "agentes"
        meta: Roster.counts.waiting === 1 ? "1 te espera"
            : Roster.counts.waiting > 1 ? Roster.counts.waiting + " te esperan"
            : Roster.counts.busy > 0 ? Roster.counts.busy + " " + Ryce.Words.state.busy
            : Roster.all.length === 1 ? "1 sesión" : Roster.all.length > 1 ? Roster.all.length + " sesiones" : ""
        metaColor: Roster.counts.waiting > 0 ? Ryce.Palette.signal : Ryce.Palette.fg2
    }

    // As tall as its rows, up to the room there is.
    Item {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.preferredHeight: list.contentHeight
        Layout.maximumHeight: list.contentHeight
        visible: Roster.all.length > 0

        ListView {
            id: list
            anchors.fill: parent
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            // Keyed by session: a roster update keeps the rows (their focus, the scroll)
            // and each row reads its newest values through Roster.bySession.
            model: ScriptModel {
                values: Roster.all
                objectProp: "sessionId"
            }

            delegate: AgentCard {
                required property var modelData
                required property int index
                width: ListView.view.width
                session: Roster.bySession[modelData.sessionId] ?? modelData
                now: board.now
                focusedWorkspace: Roster.focusedWorkspace
                first: index === 0
                leads: index === 0 || Roster.all[index - 1]?.workspace !== session.workspace
                beat: board.beat
                expanded: board.expanded[modelData.sessionId] === true
                onActivated: board.focusWorkspace(session.workspace)
                onToggled: board.toggle(modelData.sessionId)
                onActiveFocusChanged: if (activeFocus) list.positionViewAtIndex(index, ListView.Contain)
            }
        }
        // More rows below: the last 32 px fade into the drawer instead of a scrollbar.
        Rectangle {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: 32
            visible: !list.atYEnd
            gradient: Gradient {
                GradientStop { position: 0; color: Ryce.Palette.rgba(Ryce.Palette.bg0, 0) }
                GradientStop { position: 1; color: Ryce.Palette.bg0 }
            }
        }
    }
    Item {
        visible: Roster.all.length > 0
        Layout.fillHeight: true
    }

    ColumnLayout {
        visible: Roster.all.length === 0
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.topMargin: 10
        spacing: 4

        Label {
            text: "Sin sesiones de IA"
            color: Ryce.Palette.fg1
        }
        Label {
            Layout.fillWidth: true
            text: Roster.present ? "Abre Claude Code en una terminal y aparecerá aquí."
                : "agentd todavía no ha escrito el roster."
            color: Ryce.Palette.fg2
            wrapMode: Text.WordWrap
            font.pixelSize: Ui.meta
        }
        Item { Layout.fillHeight: true }
    }
}
