import QtQuick
import QtQuick.Shapes
import Quickshell
import Quickshell.Hyprland
import qs as Ryce
import qs.agents
import "../prose.js" as Prose

// The ten workspace slots, centred in the bar, each labelled with its number. Fixed slots
// 1..10, never a Repeater over Hyprland's workspace objects (Quickshell 0.3.2 can keep
// stale ids on them): occupancy comes from the toplevels. Every bar shows every slot,
// grouped by the screen that keeps it (Desks: live state united with the rules; 1-5 |
// 6-10 on the PC), screens left to right with a rule between groups; one screen, all
// ten and no rule. Each group shows all of its slots, empty ones included: they are
// exactly the workspaces that screen keeps. The pill sits on the FOCUSED screen's
// workspace and glides across the rule when the focus changes screen; every other
// screen's workspace wears a faint ground in the pill's colour, so each group says what
// its screen shows and the pill says where you are. `activeId` and `cleared` stay THIS
// bar's screen's (the focus line beside it reads them).
// Every slot's place is computed from the model, so the slots and the pill animate
// to the same target and never chase each other. The slots share one plate, the pill
// riding inside it `BarUi.inset` from its rim; the plate follows the row's width on the
// slots' own curve.
Item {
    id: row
    property var screen
    property bool hyprland: false

    readonly property int count: 10     // constants workspace_keys: CTRL + 1..9, 0

    // Slot 10's numeral takes two digits: its slot has its own, wider metrics. Papel numbers
    // its workspaces as a book numbers its front matter, lowercase roman in italic, from a
    // narrow «i» to a wide «viii»: each slot fits its own numeral. It shows no app icons
    // (SlotFace), so an app slot keeps the empty one's width: opening a window, or moving
    // the focus, never moves a numeral.
    readonly property var metrics: {
        void numeralFont.font;                      // re-measure when the theme changes the font
        return shape("0");
    }
    readonly property var metricsById: {
        void numeralFont.font;
        const out = [];
        for (let id = 1; id <= count; id++)
            out.push(BarUi.folio ? shape(numeral(id)) : id >= 10 ? shape("00") : metrics);
        return out;
    }
    function metricsFor(id) {
        return metricsById[id - 1] ?? metrics;
    }
    function numeral(id) {
        return BarUi.folio ? Prose.roman(id) : String(id);
    }
    function shape(widest) {
        const padX = 12, numeralWidth = Math.ceil(numeralFont.advanceWidth(widest)), gap = 9, glyphWidth = BarUi.iconPx, iconGap = 4;
        const contentX = padX + numeralWidth + gap;
        return {
            textPx: BarUi.textPx,
            pillHeight: BarUi.chipHeight - 2 * BarUi.inset,     // rides inside the row's plate
            padX: padX,
            numeralWidth: numeralWidth,
            contentX: contentX,
            glyphWidth: glyphWidth,
            iconGap: iconGap,
            maxApps: 3,             // icons per slot; more windows share the last one
            labelMax: 140,          // longer project names elide
            dot: 6,
            dotGap: 8,
            spacing: 4,
            sepWidth: 26,           // between two screens' groups, the rule centred in it
            // An app slot grows by one icon per distinct app (up to maxApps): it changes
            // when windows open or close, never on focus.
            widths: { empty: padX * 2 + numeralWidth, app: n => contentX + n * glyphWidth + (n - 1) * iconGap + padX },
            // Material Design glyphs (nf-md-*) by code point.
            glyphs: {
                term: String.fromCodePoint(0xf018d),       // md-console
                nvim: String.fromCodePoint(0xf0169),       // md-code_braces
                code: String.fromCodePoint(0xf0169),       // md-code_braces
                files: String.fromCodePoint(0xf0256),      // md-folder_outline
                browser: String.fromCodePoint(0xf059f),    // md-web
                claude: String.fromCodePoint(0xf018d),     // md-console: a session agentd could not name
                window: String.fromCodePoint(0xf0614)      // md-application_outline
            }
        };
    }
    // Project slots fit their label (up to labelMax), so the ring hugs the name. The width
    // changes only when the workspace's project does, and then it animates.
    FontMetrics {
        id: labelFont
        font.family: BarUi.face
        font.pixelSize: BarUi.textPx
        font.weight: BarUi.weight
    }
    // The numerals as SlotFace sets them in Papel (italic, its figures); every other theme
    // measures its digits in the labels' font, as it always has.
    FontMetrics {
        id: numeralFont
        font.family: BarUi.face
        font.pixelSize: BarUi.textPx
        font.weight: BarUi.weight
        font.italic: BarUi.folio
        font.features: BarUi.folio ? BarUi.figures(true) : ({})
    }
    function labelWidth(label) {
        return Math.min(metrics.labelMax, Math.ceil(labelFont.advanceWidth(label)));
    }
    // An app id to an icon URL, "" when the theme has none (the slot falls back to the glyph).
    function iconFor(appId) {
        const entry = DesktopEntries.heuristicLookup(appId);
        return Quickshell.iconPath(entry?.icon || appId, true);
    }

    // Workspace id -> the distinct app ids of its windows, in Hyprland's order. Reading
    // each toplevel's workspace makes the binding follow windows that move, not only the
    // list; a window with no app id yet still occupies its workspace.
    readonly property var apps: {
        const map = {};
        if (!hyprland) return map;
        for (const t of Hyprland.toplevels.values) {
            const id = t.workspace?.id ?? 0;
            if (id <= 0) continue;
            const list = map[id] ?? (map[id] = []);
            const app = t.wayland?.appId || t.lastIpcObject?.class || "";
            if (app !== "" && !list.includes(app)) list.push(app);
        }
        return map;
    }
    // Workspaces with at least one window.
    readonly property var occupied: hyprland
        ? Object.keys(apps).map(Number)
        : Roster.workspaces.filter(w => w.occupied).map(w => w.id)
    // Every screen, left to right, with the workspace it shows. «Despejar» (SUPER+e, hypr)
    // swaps a monitor's workspace N for the empty named workspace `despejado-N` and back:
    // that screen stays on N, its mark only outlined (still on N, the desk cleared).
    // Without Hyprland, agentd's focused workspace on one screen.
    readonly property var screens: {
        if (!hyprland) return [{ name: "", active: Roster.focusedWorkspace ?? 0, cleared: false, focused: true }];
        const focused = Hyprland.focusedMonitor;
        return Desks.monitors.map(m => {
            const ws = m.activeWorkspace;
            const from = /^despejado-(\d+)$/.exec(ws?.name ?? "");
            return { name: m.name, active: from ? Number(from[1]) : (ws?.id ?? 0), cleared: from !== null, focused: m === focused };
        });
    }
    readonly property var here: (hyprland ? screens.find(s => s.name === Hyprland.monitorFor(screen)?.name) : null) ?? screens[0] ?? null
    readonly property var focusedScreen: screens.find(s => s.focused) ?? here
    readonly property bool cleared: here?.cleared ?? false
    readonly property int activeId: here?.active ?? 0
    readonly property int pillId: focusedScreen?.active ?? 0
    readonly property bool pillCleared: focusedScreen?.cleared ?? false

    // Slots by id (index id - 1), laid out group by group; `seps` holds where each rule
    // between two groups starts. A group with no slot to show takes no room and no rule.
    readonly property var layout: {
        void labelFont.font;                        // re-measure when the theme changes the font
        void DesktopEntries.applications.values;    // and look icons up again once entries load
        const n = count;
        const names = screens.map(s => s.name);
        // A slot whose owner is no listed screen (none plugged yet) joins the first group.
        const groupOf = id => Math.max(0, hyprland ? names.indexOf(Desks.owners[id] ?? "") : 0);
        const list = new Array(n);
        for (let id = 1; id <= n; id++) {
            const r = Roster.workspaces[id - 1];
            const has = occupied.includes(id);
            // The roster's Claude session on this workspace, also when agentd's slot names
            // another window (a plain terminal opened first): the slot follows the session
            // the moment it appears and drops it the moment it ends.
            const s = r.icon === "claude" ? null : (Roster.sessions.find(x => x.workspace === id) ?? null);
            const project = has && (r.icon === "claude" ? r.label !== "" : s !== null && s.project !== "");
            const kind = !has ? "empty" : project ? "project" : "app";
            const label = !project ? "" : r.icon === "claude" ? r.label : s.project;
            const state = !has ? "" : s === null ? r.state : ["waiting", "busy"].includes(s.state) ? s.state : "idle";
            const showing = screens.find(d => d.active === id) ?? null;
            const m = metricsFor(id);
            const labelWidth = label === "" ? 0 : row.labelWidth(label);
            // App slots: one icon per distinct app; no window reported yet keeps one glyph.
            const icons = kind !== "app" || BarUi.folio ? [] : (apps[id] ?? []).slice(0, m.maxApps).map(a => row.iconFor(a));
            const full = kind === "empty" || kind === "app" && BarUi.folio ? m.widths.empty
                : kind === "app" ? m.widths.app(Math.max(1, icons.length))
                : m.contentX + labelWidth + (state === "waiting" ? m.dotGap + m.dot : 0) + m.padX;
            // `key` is what SlotFace prints: the workspace's number, never the key's name.
            list[id - 1] = { id: id, key: row.numeral(id), occupied: has, kind: kind, label: label, labelWidth: labelWidth,
                             icon: r.icon, icons: icons, state: state, shown: true, width: full, full: full,
                             group: groupOf(id),
                             // Shown on a screen that does not have the focus: the faint ground.
                             elsewhere: showing !== null && !showing.focused, elsewhereCleared: showing !== null && !showing.focused && showing.cleared };
        }
        const seps = [];
        let x = 0, end = 0;
        for (let g = 0; g < Math.max(1, screens.length); g++) {
            const group = list.filter(s => s.group === g);
            if (group.length > 0 && end > 0) {
                seps.push(end);
                x = end + metrics.sepWidth;
            }
            for (const s of group) {
                s.x = x;
                end = x + s.width;
                x = end + metrics.spacing;
            }
        }
        return { slots: list, seps: seps, width: end };
    }
    readonly property var slots: layout.slots
    readonly property real contentWidth: layout.width
    readonly property real start: Math.round((width - contentWidth) / 2)

    // The pill rides the slots themselves: each edge travels from where it started to the
    // LIVE edge of the target slot item (progress 0 -> 1). When the row re-centres around
    // a slot that appears, or agentd names the project a beat later and the slot grows,
    // the pill moves with the slot on the slot's own curve instead of being re-aimed on a
    // curve of its own; the ink clipped to it (Slot.qml) reads the same edges, so pill and
    // label never part. The leading edge runs ahead and the trailing one follows 1.5x
    // slower, so a jump stretches and settles. A switch mid-flight freezes the pill where
    // it is and leaves from there, so fast switching never piles animations up.
    property Item toSlot: null
    property Item fromSlot: null      // null: leave from the frozen edges below
    property real fromLeft: 0
    property real fromRight: 0
    property real leftP: 1
    property real rightP: 1
    readonly property real pillLeft: toSlot === null ? 0
        : (fromSlot !== null ? fromSlot.x : fromLeft) * (1 - leftP) + toSlot.x * leftP
    readonly property real pillRight: toSlot === null ? 0
        : (fromSlot !== null ? fromSlot.x + fromSlot.width : fromRight) * (1 - rightP) + (toSlot.x + toSlot.width) * rightP
    onPillIdChanged: place()

    function place() {
        const target = pillId >= 1 && pillId <= count ? slotItems.itemAt(pillId - 1) : null;
        if (target === toSlot) return;
        leftEdge.stop();
        rightEdge.stop();
        // First placement, or a workspace past the slots: no journey to show.
        if (toSlot === null || target === null) {
            fromSlot = target;
            toSlot = target;
            leftP = 1;
            rightP = 1;
            return;
        }
        const right = target.x > pillLeft;
        if (leftP === 1 && rightP === 1) {
            fromSlot = toSlot;
        } else {
            fromLeft = pillLeft;
            fromRight = pillRight;
            fromSlot = null;
        }
        toSlot = target;
        leftP = 0;
        rightP = 0;
        const lead = Ryce.Palette.motionMs * 0.75, trail = lead * 1.5;
        leftEdge.duration = right ? trail : lead;
        rightEdge.duration = right ? lead : trail;
        leftEdge.start();
        rightEdge.start();
    }
    NumberAnimation {
        id: leftEdge
        target: row
        property: "leftP"
        from: 0
        to: 1
        easing.type: Easing.BezierSpline
        easing.bezierCurve: Ryce.Palette.motionCurve
    }
    NumberAnimation {
        id: rightEdge
        target: row
        property: "rightP"
        from: 0
        to: 1
        easing.type: Easing.BezierSpline
        easing.bezierCurve: Ryce.Palette.motionCurve
    }

    // The hover ground of the slot under the pointer, drawn UNDER the pill: the slot just
    // clicked is still hovered while the pill arrives, and a ground over the pill hid it
    // behind a block of the wrong colour. It fades as the pill takes the slot over.
    property Item hoverSlot: null
    property bool hovering: false

    Plate {
        x: row.start - BarUi.inset
        width: row.contentWidth + 2 * BarUi.inset
        height: BarUi.chipHeight
        anchors.verticalCenter: parent.verticalCenter
        Behavior on x { NumberAnimation { duration: Ryce.Palette.motionMs; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
        Behavior on width { NumberAnimation { duration: Ryce.Palette.motionMs; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
    }
    // The rule between two screens' groups: as tall as the pill, so it reads as a wall
    // and not as one more gap. Counted, not modelled, so a moving rule slides.
    Repeater {
        model: row.layout.seps.length

        Rectangle {
            required property int index
            x: row.start + (row.layout.seps[index] ?? 0) + Math.round((row.metrics.sepWidth - width) / 2)
            width: 2
            height: row.metrics.pillHeight
            anchors.verticalCenter: parent.verticalCenter
            radius: 1
            color: Ryce.Palette.fg2
            Behavior on x { NumberAnimation { duration: Ryce.Palette.motionMs; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
        }
    }
    // What every other screen shows: a faint ground in the pill's colour (an outline when
    // that screen's desk is cleared), under the pill, so the pill crossing over it on a
    // change of screen is never tinted. It moves on the slots' own curve.
    Repeater {
        model: row.count

        Item {
            id: ground
            required property int index
            readonly property var info: row.slots[index]
            x: row.start + info.x
            width: info.width
            height: row.metrics.pillHeight
            anchors.verticalCenter: parent.verticalCenter
            opacity: info.elsewhere ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Ryce.Palette.motionMs; easing.type: Easing.OutCubic } }
            Behavior on x { NumberAnimation { duration: Ryce.Palette.motionMs; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
            Behavior on width { NumberAnimation { duration: Ryce.Palette.motionMs; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }

            Rectangle {
                visible: !ground.info.elsewhereCleared
                anchors.fill: parent
                radius: Math.min(Ryce.Palette.pillRadius, height / 2)
                color: Ryce.Palette.pill
                opacity: 0.22
            }
            Shape {
                visible: ground.info.elsewhereCleared
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer

                ShapePath {
                    fillColor: "transparent"
                    strokeColor: Ryce.Palette.rgba(Ryce.Palette.pill, 0.5)
                    strokeWidth: 1
                    PathRectangle {
                        x: 0.5
                        y: 0.5
                        width: Math.max(0, ground.width - 1)
                        height: ground.height - 1
                        radius: Math.max(0, Math.min(Ryce.Palette.pillRadius, ground.height / 2) - 0.5)
                    }
                }
            }
        }
    }
    Rectangle {
        x: row.hoverSlot?.x ?? 0
        width: row.hoverSlot?.width ?? 0
        height: row.metrics.pillHeight
        anchors.verticalCenter: parent.verticalCenter
        radius: Math.min(Ryce.Palette.pillRadius, height / 2)
        color: Ryce.Palette.bg2
        opacity: row.hyprland && row.hovering && row.hoverSlot !== row.toSlot ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
    }
    // The slots draw their ink in the pill's colours only where a solid pill lies.
    readonly property bool solid: toSlot !== null && !pillCleared
    Rectangle {
        visible: row.solid
        x: row.pillLeft
        width: Math.max(0, row.pillRight - row.pillLeft)
        height: row.metrics.pillHeight
        anchors.verticalCenter: parent.verticalCenter
        radius: Math.min(Ryce.Palette.pillRadius, height / 2)
        color: Ryce.Palette.pill
    }
    // Desk cleared: the pill as a 1 px outline. A Shape, not a bordered transparent
    // Rectangle (QTBUG-137166).
    Shape {
        visible: row.toSlot !== null && row.pillCleared
        x: row.pillLeft
        width: Math.max(0, row.pillRight - row.pillLeft)
        height: row.metrics.pillHeight
        anchors.verticalCenter: parent.verticalCenter
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: "transparent"
            strokeColor: Ryce.Palette.pill
            strokeWidth: 1
            PathRectangle {
                x: 0.5
                y: 0.5
                width: Math.max(0, row.pillRight - row.pillLeft - 1)
                height: row.metrics.pillHeight - 1
                radius: Math.max(0, Math.min(Ryce.Palette.pillRadius, row.metrics.pillHeight / 2) - 0.5)
            }
        }
    }

    Repeater {
        id: slotItems
        model: row.count
        onItemAdded: (index, item) => { if (index === row.pillId - 1) row.place(); }

        Slot {
            id: slot
            required property int index
            info: row.slots[index]
            metrics: row.metricsFor(info.id)
            x: row.start + info.x
            width: info.width
            height: row.height
            pillLeft: row.solid ? row.pillLeft - x : 0
            pillRight: row.solid ? row.pillRight - x : 0
            clickable: row.hyprland
            onActivated: Hyprland.dispatch("hl.dsp.focus({ workspace = " + info.id + " })")
            onHoveredChanged: {
                if (hovered) row.hoverSlot = slot;
                if (row.hoverSlot === slot) row.hovering = hovered;
            }

            Behavior on x { NumberAnimation { duration: Ryce.Palette.motionMs; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
            Behavior on width { NumberAnimation { duration: Ryce.Palette.motionMs; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
        }
    }

    // Wheel over a group: the previous / next slot of THAT screen, from the workspace that
    // screen shows (not the focused one: rolling over the other screen's group must not
    // eat its first step), one step per notch (touchpad deltas add up to a notch first).
    // Like CTRL + arrows (ryce.ws_step) it steps by number, stopping at 1 and 10 and
    // crossing to the other screen past a group's edge; focusing a workspace moves the
    // focus to its screen.
    MouseArea {
        x: row.start
        width: row.contentWidth
        height: parent.height
        z: -1
        enabled: row.hyprland
        acceptedButtons: Qt.NoButton
        property int acc: 0
        onWheel: wheel => {
            acc += wheel.angleDelta.y;
            const steps = Math.trunc(acc / 120);
            if (steps === 0) return;
            acc -= steps * 120;
            // The group under the pointer: the slot nearest to it.
            const px = wheel.x;
            const g = row.slots.reduce((a, b) => Math.abs(b.x + b.width / 2 - px) < Math.abs(a.x + a.width / 2 - px) ? b : a).group;
            const at = row.screens[g]?.active ?? 0;
            if (at < 1) return;
            const next = Math.max(1, Math.min(row.count, at - steps));
            if (next !== at)
                Hyprland.dispatch("hl.dsp.focus({ workspace = " + next + " })");
        }
    }
}
