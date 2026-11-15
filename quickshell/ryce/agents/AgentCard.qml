import QtQuick
import QtQuick.Layouts
import qs
import qs as Ryce

// One session, whatever it is doing. Three short lines: the project; its state (waiting
// for you: what it asks, in the signal, its dot breathing; working: «trabajando» or what
// its background work waits on; its turn over: «esperando la siguiente acción») with how
// long; and one sentence: what it does, else what it just did, else what it was asked.
// Unfolded it adds the user's last ask and its subagents. Every string here comes from a
// transcript: Label renders plain text only. The theme's signal marks a waiting session,
// small: the dot and its state words. Nothing else is coloured.
// The rows come grouped by workspace (Roster.all): the first of a group (`leads`) wears
// the workspace numeral and a hairline above; the others hang under it.
//
// Pointer: the row goes to the session's workspace; the chevron at its right end unfolds
// it. Keyboard (Tab or Up/Down between rows): Space or Enter unfolds; Enter on a row with
// nothing more to show goes to the workspace.
Item {
    id: card
    required property var session
    property real now
    property var focusedWorkspace: null
    property bool first: false
    property bool leads: true
    property bool expanded: false
    property int beat                       // AgentBoard's: each tick, a waiting dot breathes once
    signal activated()
    signal toggled()

    readonly property bool waiting: session.state === "waiting"
    onBeatChanged: if (waiting && !pulse.running) pulse.start()
    readonly property bool background: session.waiting_on !== ""
    readonly property bool working: !waiting && (background || session.state === "busy" || session.state === "shell")
    readonly property bool reachable: session.workspace !== null
    readonly property bool here: reachable && session.workspace === focusedWorkspace
    readonly property bool lit: (mouse.containsMouse && reachable) || activeFocus
    readonly property int badge: 22
    readonly property int textX: badge + 14
    readonly property int keyWidth: 48          // the «Pidió» column when unfolded
    readonly property bool hasSubagents: session.subagents.length > 0
    readonly property int live: session.subagents.filter(a => a.live).length
    // `did` is optional: an agentd older than the field leaves it out.
    readonly property string did: session.did ?? ""
    readonly property string named: session.title || session.name || ""

    // A turn that ended with its own work still out is working: say what it waits on.
    readonly property var backgroundText: ({ shell: "espera un comando", agent: "espera un subagente", monitor: "vigila un proceso" })
    // Same words as the bar (contracts/constants.json words_es); never raw English.
    readonly property string stateText: waiting
        ? (Ryce.Words.waitingFor[session.waitingFor] ?? Ryce.Words.waitingFallback)
        : background ? backgroundText[session.waiting_on]
        : working ? (Ryce.Words.state[session.state] ?? Ryce.Words.state.busy)
        : "esperando la siguiente acción"
    // The sentence: what it does (its turn open), else what it just did; else what it was
    // asked, else its name.
    readonly property string told: waiting || working ? session.doing || did : did
    readonly property bool fromAsk: told === "" && session.asked !== ""
    readonly property string line: told || session.asked || named
    readonly property string sinceText: {
        if (session.since === null) return "";
        const m = Math.floor(Math.max(0, now - session.since) / 60);
        return m < 1 ? "ahora" : m < 60 ? m + " min" : m < 1440 ? Math.floor(m / 60) + " h " + (m % 60) + " min" : Math.floor(m / 1440) + " d";
    }
    readonly property bool showsAsk: session.asked !== "" && !fromAsk
    readonly property bool expandable: showsAsk || hasSubagents

    implicitHeight: body.implicitHeight + (leads ? 24 : 14)
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: (session.project || "sin proyecto") + ", " + stateText
    Accessible.description: line + (showsAsk ? ". Pidió: " + session.asked : "")

    Keys.onSpacePressed: if (expandable) card.toggled()
    Keys.onReturnPressed: expandable ? card.toggled() : (reachable && card.activated())
    Keys.onEnterPressed: expandable ? card.toggled() : (reachable && card.activated())
    Keys.onDownPressed: nextItemInFocusChain(true).forceActiveFocus(Qt.TabFocusReason)
    Keys.onUpPressed: nextItemInFocusChain(false).forceActiveFocus(Qt.BacktabFocusReason)

    // Between workspaces only: the rows of one workspace read as one group.
    Rectangle {
        visible: card.leads && !card.first
        width: parent.width
        height: 1
        color: Ryce.Palette.line
    }
    // Under the pointer or the keyboard: the drawer's next step up; a hairline for focus.
    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: -8
        anchors.rightMargin: -8
        anchors.topMargin: card.leads ? 4 : 0
        radius: Ryce.Palette.rounding
        color: Ryce.Palette.bg1
        border.width: card.activeFocus ? 1 : 0
        border.color: Ryce.Palette.line
        opacity: card.lit ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }

    // The workspace numeral, on the group's first row; the focused one wears the bar's
    // active pill. A session without a window shows the terminal glyph instead.
    Rectangle {
        visible: card.leads
        x: 0
        y: 12
        width: card.badge
        height: card.badge
        radius: Math.min(Ryce.Palette.pillRadius, width / 2)
        color: card.here ? Ryce.Palette.pill : "transparent"

        Label {
            anchors.centerIn: parent
            text: card.reachable ? String(card.session.workspace) : Ui.terminal
            color: card.here ? Ryce.Palette.inkOnPill : card.reachable ? Ryce.Palette.fg1 : Ryce.Palette.fg2
            font.family: card.reachable ? Ryce.Palette.fontUi : Ryce.Palette.fontIcon
            font.pixelSize: Ui.meta + 1
            font.features: { "tnum": 1 }
            elide: Text.ElideNone
        }
    }

    ColumnLayout {
        id: body
        z: 1        // above the row's area: the chevron takes its own clicks
        anchors { left: parent.left; right: parent.right; top: parent.top }
        anchors { leftMargin: card.textX; topMargin: card.leads ? 12 : 2 }
        spacing: 2

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: card.badge
            spacing: 8

            Label {
                text: card.session.project || "sin proyecto"
                color: card.waiting || card.working ? Ryce.Palette.fg0 : Ryce.Palette.fg1
                font.pixelSize: Ui.project
                font.weight: Font.Medium
                Layout.maximumWidth: body.width - 70
            }
            // Working: a filled dot in the theme's busy ink. Working on its own in the
            // background: the same ink as a ring. Waiting for you: the signal, breathing
            // while the drawer is in. Its turn over: a ring in the quiet ink.
            Item {
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: 7
                implicitHeight: 7

                Rectangle {
                    id: halo
                    visible: card.waiting
                    anchors.fill: parent
                    radius: width / 2
                    color: Ryce.Palette.signal
                    opacity: 0
                }
                Rectangle {
                    anchors.fill: parent
                    radius: width / 2
                    color: card.waiting ? Ryce.Palette.signal : card.working && !card.background ? Ryce.Palette.busy : "transparent"
                    border.width: card.waiting || (card.working && !card.background) ? 0 : 1.5
                    border.color: card.working ? Ryce.Palette.busy : Ryce.Palette.fg2
                }
                // A ring that swells and fades on the board's beat; Animators, so it costs
                // the GUI thread nothing. Never stopped: it ends by itself (stopping one
                // mid-slide froze the drawer's own Animators), and between beats nothing
                // moves, so the drawer renders no frames for it.
                ParallelAnimation {
                    id: pulse
                    ScaleAnimator { target: halo; from: 1; to: 2.8; duration: 1100; easing.type: Easing.OutCubic }
                    OpacityAnimator { target: halo; from: 0.55; to: 0; duration: 1100; easing.type: Easing.OutCubic }
                }
            }
            Item { Layout.fillWidth: true }
            // The disclosure: how many subagents are live, and a chevron that turns down.
            Item {
                visible: card.expandable
                implicitWidth: discloseRow.implicitWidth + 8
                implicitHeight: card.badge
                Accessible.role: Accessible.Button
                Accessible.name: card.expanded ? "Plegar" : "Desplegar"

                Rectangle {
                    anchors.fill: parent
                    radius: Math.min(Ryce.Palette.pillRadius, height / 2)
                    color: Ryce.Palette.bg2
                    opacity: discloseMouse.containsMouse ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 120 } }
                }
                Row {
                    id: discloseRow
                    anchors.centerIn: parent
                    spacing: 2

                    Label {
                        visible: card.hasSubagents
                        anchors.verticalCenter: parent.verticalCenter
                        text: card.live > 0 ? String(card.live) : String(card.session.subagents.length)
                        color: card.live > 0 ? Ryce.Palette.fg1 : Ryce.Palette.fg2
                        font.pixelSize: Ui.meta
                        font.features: { "tnum": 1 }
                    }
                    Label {
                        anchors.verticalCenter: parent.verticalCenter
                        text: Ui.chevron
                        color: Ryce.Palette.fg2
                        font.family: Ryce.Palette.fontIcon
                        font.pixelSize: Ui.meta + 3
                        rotation: card.expanded ? 90 : 0
                        Behavior on rotation { NumberAnimation { duration: Ryce.Palette.motionMs * 0.4; easing.type: Easing.OutCubic } }
                    }
                }
                MouseArea {
                    id: discloseMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: card.toggled()
                }
            }
        }

        // The state, and for how long.
        Label {
            Layout.fillWidth: true
            text: card.stateText + (card.sinceText !== "" ? " · " + card.sinceText : "")
            color: card.waiting ? Ryce.Palette.signal : card.working ? Ryce.Palette.busy : Ryce.Palette.fg2
            font.pixelSize: Ui.meta
        }
        // The one sentence about the session; an ask reads as one.
        Label {
            visible: card.line !== ""
            Layout.fillWidth: true
            text: card.fromAsk ? "«" + card.line + "»" : card.line
            color: card.fromAsk ? Ryce.Palette.fg2 : Ryce.Palette.fg1
            font.pixelSize: Ui.meta + 1
        }

        // Unfolded: what was asked and the subagents. Height and opacity follow the
        // theme's curve, so it unfolds rather than jumps.
        Item {
            id: fold
            Layout.fillWidth: true
            Layout.preferredHeight: card.expanded ? more.implicitHeight + 6 : 0
            visible: Layout.preferredHeight > 0
            clip: true
            opacity: card.expanded ? 1 : 0
            Behavior on Layout.preferredHeight {
                NumberAnimation { duration: Ryce.Palette.motionMs * 0.5; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve }
            }
            Behavior on opacity { NumberAnimation { duration: Ryce.Palette.motionMs * 0.4; easing.type: Easing.OutCubic } }

            ColumnLayout {
                id: more
                y: 6
                width: parent.width
                spacing: 4

                RowLayout {
                    visible: card.showsAsk
                    Layout.fillWidth: true
                    spacing: 0

                    Label {
                        text: "Pidió"
                        color: Ryce.Palette.fg2
                        font.pixelSize: Ui.meta
                        Layout.preferredWidth: card.keyWidth
                        Layout.alignment: Qt.AlignTop
                        topPadding: 1
                    }
                    Label {
                        text: card.session.asked
                        color: Ryce.Palette.fg1
                        font.pixelSize: Ui.meta + 1
                        // 60 characters: two lines at most, even in a wide face.
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        Layout.fillWidth: true
                    }
                }
                // The subagents: type and what it was sent to do; a finished one is
                // ticked and dimmed.
                Repeater {
                    model: card.session.subagents

                    RowLayout {
                        id: sub
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 0

                        Item {
                            Layout.preferredWidth: card.keyWidth
                            implicitHeight: subText.implicitHeight
                            Rectangle {
                                visible: sub.modelData.live
                                anchors.verticalCenter: parent.verticalCenter
                                width: 5
                                height: 5
                                radius: 2.5
                                color: Ryce.Palette.busy
                            }
                            Label {
                                visible: !sub.modelData.live
                                anchors.verticalCenter: parent.verticalCenter
                                text: Ui.check
                                color: Ryce.Palette.fg2
                                font.family: Ryce.Palette.fontIcon
                                font.pixelSize: Ui.meta
                            }
                        }
                        Label {
                            id: subText
                            Layout.fillWidth: true
                            text: sub.modelData.type + (sub.modelData.description !== "" ? " · " + sub.modelData.description : "")
                            color: sub.modelData.live ? Ryce.Palette.fg1 : Ryce.Palette.fg2
                            font.pixelSize: Ui.meta
                        }
                    }
                }
            }
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: card.reachable ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (card.reachable) card.activated()
    }
}
