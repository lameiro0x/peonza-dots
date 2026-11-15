import QtQml.Models
import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import qs
import qs as Ryce
import qs.desk

// Hito's drawer: the frame's left rim thickening into a drawer, the sidebar's mirror (the
// same shape, flipped, with the frame's concave corners where its free edge meets the bar
// band and the bottom rim). A field to add a task for today, then the list or the month
// (HitoCalendar). The list: «Hoy», «Atrasadas», «Próximos 7 días» and «Sin fecha», each
// task with its project's colour, narrowed to hoy, atrasadas or one proyecto if the user
// picks so; view and filter are kept in hito.json. Overlay layer while shown; keyboard
// only then; Escape or a click anywhere else closes it.
// Built once per screen and kept mapped, closed on the Bottom layer with no input and the
// drawer hidden, for the reasons AriaWindow gives; the slide runs on the render thread and
// HitoRoot fetches on `entered`, once it is over.
PanelWindow {
    id: win
    property bool shown: false
    property Hito hito
    property var prefs                      // HitoRoot's JsonAdapter
    property real toggledAt
    signal closeRequested()
    signal entered()
    signal rested()                         // closed and still again
    readonly property bool moving: enter.running || leave.running

    readonly property int rim: Ryce.Palette.frameRim
    readonly property int fillet: Ryce.Palette.frameRadius
    readonly property int reach: Ui.panelWidth
    readonly property int slack: 24         // room for a curve that overshoots
    readonly property int undatedMax: 50
    readonly property int leaveMs: Math.round(Ryce.Palette.motionMs * 0.6)
    property bool adding: false
    readonly property bool monthly: prefs.listView === "calendario"
    // A hand-edited hito.json with a word it does not know falls back to «todas».
    readonly property string filter: ["hoy", "atrasadas", "todas", "proyecto"].includes(prefs.listFilter) ? prefs.listFilter : "todas"
    readonly property bool choosing: filter === "proyecto" && prefs.listProject === ""
    function only(list) { return filter === "proyecto" ? hito.ofProject(list, prefs.listProject) : list; }

    // The list as one flat model: each section's rule, its tasks and its «y N más»; empty
    // sections drop out, except the one the filter is about («hoy» in the whole list),
    // which says so. Colours go as tones, resolved by the rows: a theme's cross-fade must
    // not rebuild the list on every frame.
    readonly property var rows: {
        const out = [];
        if (choosing) return out;
        const fresh = hito.fetchedAt > 0;
        const section = (label, tasks, total, empty, tone, noteOf, noteTone) => {
            if (total === 0 && empty === "") return;
            out.push({ kind: "rule", label: label, meta: total > 0 ? String(total) : fresh ? empty : "…",
                       tone: total > 0 ? tone : "", gap: out.length > 0 ? 22 : 0 });
            for (const t of tasks) out.push({ kind: "task", task: t, note: noteOf(t), tone: noteTone });
            if (total > tasks.length) out.push({ kind: "more", text: "y " + (total - tasks.length) + " más en Hito" });
        };
        const mine = filter === "proyecto";
        if (filter !== "atrasadas") {
            const today = only(hito.dueToday);
            section("hoy", today, today.length, "nada para hoy", "", t => note([t.time, mine ? "" : t.project]), "");
        }
        if (filter !== "hoy") {
            const late = only(hito.overdue);
            section("atrasadas", late, late.length, filter === "atrasadas" ? "nada atrasado" : "", "warn",
                    t => hito.lateBy(t.date), "warn");
        }
        if (filter === "todas" || mine) {
            const soon = only(hito.upcoming);
            section("próximos 7 días", soon, soon.length, "", "", t => note([hito.weekday(t.date), t.time]), "");
            // The undated pile is long: grouped by project (Hito sorts it), the first fifty.
            const undated = only(hito.undated);
            section("sin fecha", undated.slice(0, undatedMax), undated.length, "", "", t => mine ? "" : t.project, "");
        }
        return out;
    }
    function ink(tone) { return tone === "warn" ? Ryce.Palette.warn : Ryce.Palette.fg2; }
    function note(parts) { return parts.filter(s => s !== "").join(" · "); }
    function add() {
        if (adding || field.text.trim() === "") return;
        adding = true;
        hito.add(field.text, ok => {
            adding = false;
            if (ok) field.text = "";
        });
    }

    anchors { top: true; left: true; bottom: true }
    margins.top: Ryce.Palette.frameTop
    implicitWidth: slack + fillet + reach + rim
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    mask: shown ? null : noInput
    Region { id: noInput }

    WlrLayershell.namespace: "qs-hito"
    WlrLayershell.layer: shown || leave.running ? WlrLayer.Overlay : WlrLayer.Bottom
    WlrLayershell.keyboardFocus: shown ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    onShownChanged: shown ? open() : close()
    Component.onCompleted: if (shown) closeRequested()     // never opens itself (AriaWindow)
    function open() {
        drawer.visible = true;
        if (!leave.running) {
            scroller.positionViewAtBeginning();
            month.reset();
        }
        leave.stop();
        enter.start();
        field.forceActiveFocus();
    }
    function close() {
        enter.stop();
        leave.start();
    }
    // Animators: x and opacity are the render thread's until done, so nothing binds to
    // them. The drawer enters on the theme's curve and its content fades in as it comes
    // out; leaving is faster, the content going just before the drawer is in.
    ParallelAnimation {
        id: enter
        XAnimator {
            target: drawer
            to: -win.slack
            duration: Ryce.Palette.motionMs
            easing.type: Easing.BezierSpline
            easing.bezierCurve: Ryce.Palette.motionCurve
        }
        OpacityAnimator {
            target: content
            to: 1
            duration: Math.round(Ryce.Palette.motionMs * 0.3)
            easing.type: Easing.InQuad
        }
        onFinished: if (win.shown) win.entered()
    }
    ParallelAnimation {
        id: leave
        XAnimator {
            target: drawer
            to: -win.slack - win.reach
            duration: win.leaveMs
            easing.type: Easing.InCubic
        }
        OpacityAnimator {
            target: content
            to: 0
            duration: Math.round(win.leaveMs * 0.85)
            easing.type: Easing.InCubic
        }
        // Hiding the drawer also renders the frame that commits the move to Bottom.
        // Closed: an unsent draft goes, as it did when the drawer was built per opening.
        onFinished: if (!win.shown) {
            drawer.visible = false;
            if (!win.adding) field.text = "";
            win.rested();
        }
    }

    // Armed once the drawer is in: the move to Overlay and the keyboard only reach the
    // compositor with the next frame, and a grab that comes first is cleared at once.
    HyprlandFocusGrab {
        active: win.shown && !enter.running
        windows: [win]
        onCleared: win.closeRequested()
    }

    Item {
        id: drawer
        visible: false                      // open() and the leave own it
        x: -win.slack - win.reach
        width: win.width
        height: win.height
        Keys.onEscapePressed: win.closeRequested()

        FrameProbe {
            name: "hito"
            busy: enter.running || leave.running
            opening: win.shown
            since: win.toggledAt
        }

        // The sidebar's outline (drawers/Sidebar.qml), mirrored: its free edge is on the right here.
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            transform: Scale { xScale: -1; origin.x: drawer.width / 2 }

            ShapePath {
                id: edge
                readonly property real f: win.fillet
                readonly property real h: drawer.height - win.rim
                readonly property real w: drawer.width + win.slack

                fillColor: Ryce.Palette.bg0
                strokeWidth: -1
                startX: 0
                startY: 0
                PathArc { x: edge.f; y: edge.f; radiusX: edge.f; radiusY: edge.f }
                PathLine { x: edge.f; y: edge.h - edge.f }
                PathArc { x: 0; y: edge.h; radiusX: edge.f; radiusY: edge.f }
                PathLine { x: 0; y: drawer.height }
                PathLine { x: edge.w; y: drawer.height }
                PathLine { x: edge.w; y: 0 }
            }
        }

        // The content rides with the drawer.
        ColumnLayout {
            id: content
            x: win.slack + win.rim + Ui.pad
            y: 18
            width: win.reach - 2 * Ui.pad
            height: win.height - win.rim - y - Ui.pad
            opacity: 0
            spacing: 0

            SectionRule {
                Layout.fillWidth: true
                label: "hito"
                metaMax: 280
                meta: win.hito.config !== "ready" ? ""
                    : win.hito.problem !== "" ? win.hito.problem
                    : win.hito.busy ? "actualizando…"
                    : win.hito.fetchedAt > 0 ? "al día  ·  " + Qt.formatTime(new Date(win.hito.fetchedAt), "HH:mm")
                    : ""
                metaColor: win.hito.problem !== "" ? Ryce.Palette.warn : Ryce.Palette.fg2
            }

            // Quick add: Enter files it for today, with no project (as the web's quick add).
            Rectangle {
                Layout.fillWidth: true
                Layout.topMargin: 16
                visible: win.hito.config === "ready"
                implicitHeight: 38
                radius: Math.min(Ryce.Palette.pillRadius, height / 2)
                color: Ryce.Palette.bg1
                border.width: 1
                border.color: field.activeFocus ? Ryce.Palette.line : Ryce.Palette.bg1

                Label {
                    x: 14
                    anchors.verticalCenter: parent.verticalCenter
                    visible: field.text === ""
                    text: win.adding ? "Guardando…" : "Nueva tarea…"
                    color: Ryce.Palette.fg2
                }
                TextInput {
                    id: field
                    x: 14
                    width: parent.width - 28
                    anchors.verticalCenter: parent.verticalCenter
                    readOnly: win.adding
                    maximumLength: 500
                    clip: true
                    color: Ryce.Palette.fg0
                    selectionColor: Ryce.Palette.bg3
                    selectedTextColor: Ryce.Palette.fg0
                    font.family: Ryce.Palette.fontUi
                    font.pixelSize: Ui.body
                    Keys.onReturnPressed: win.add()
                    Keys.onEnterPressed: win.add()
                    Keys.onEscapePressed: win.closeRequested()
                }
            }

            // Not configured: a calm hint where the list would be.
            Label {
                Layout.fillWidth: true
                Layout.topMargin: 22
                visible: win.hito.config === "missing" || win.hito.config === "incomplete"
                wrapMode: Text.Wrap
                text: "Hito no está configurado en este ordenador"
                color: Ryce.Palette.fg1
            }
            Label {
                Layout.fillWidth: true
                Layout.topMargin: 6
                visible: win.hito.config === "missing" || win.hito.config === "incomplete"
                wrapMode: Text.Wrap
                text: win.hito.config === "incomplete"
                    ? "Su .env está incompleto: necesita VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, VITE_APP_EMAIL y VITE_APP_PASSWORD."
                    : "Se lee ~/.config/ryce-private/hito.env, o el fichero que indique RYCE_HITO_ENV."
                color: Ryce.Palette.fg2
                font.pixelSize: Ui.meta
            }
            // The view, then what the list holds.
            Choices {
                Layout.fillWidth: true
                Layout.topMargin: 18
                visible: win.hito.config === "ready"
                options: [{ key: "lista", label: "lista" }, { key: "calendario", label: "calendario" }]
                current: win.monthly ? "calendario" : "lista"
                size: Ui.body
                onPicked: key => win.prefs.listView = key
            }
            Choices {
                Layout.fillWidth: true
                Layout.topMargin: 12
                visible: win.hito.config === "ready" && !win.monthly
                options: [{ key: "hoy", label: "hoy" }, { key: "atrasadas", label: "atrasadas" },
                          { key: "todas", label: "todas" }, { key: "proyecto", label: "proyecto" }]
                current: win.filter
                onPicked: key => win.prefs.listFilter = key
            }
            Choices {
                Layout.fillWidth: true
                Layout.topMargin: 8
                visible: win.hito.config === "ready" && !win.monthly && win.filter === "proyecto"
                options: win.hito.projectsIn(win.hito.everything, win.prefs.listProject)
                    .map(p => ({ key: p.key, label: p.name, hue: p.hue }))
                current: win.prefs.listProject
                square: Ryce.Palette.pillRadius < 4
                hito: win.hito
                onPicked: key => win.prefs.listProject = key
            }
            Label {
                Layout.topMargin: 22
                visible: win.hito.config === "ready" && !win.monthly && win.choosing
                text: "Elige un proyecto"
                color: Ryce.Palette.fg2
            }

            // Keeps the hint at the top when neither the list nor the month is there.
            Item {
                Layout.fillHeight: true
                visible: !scroller.visible && !month.visible
            }

            HitoCalendar {
                id: month
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.topMargin: 20
                visible: win.hito.config === "ready" && win.monthly
                hito: win.hito
                project: win.prefs.calProject
                onProjectPicked: key => win.prefs.calProject = key
            }

            // Only the rows in sight exist, and a fetch reuses them instead of building
            // the whole list again.
            ListView {
                id: scroller
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.topMargin: 22
                visible: win.hito.config === "ready" && !win.monthly && !win.choosing
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                reuseItems: true
                model: win.rows

                // Heights carry the old column's spacing: 2 between a section's lines,
                // 6 under its rule, 22 between sections.
                delegate: DelegateChooser {
                    role: "kind"

                    DelegateChoice {
                        roleValue: "rule"

                        Item {
                            required property var modelData
                            width: ListView.view.width
                            implicitHeight: modelData.gap + rule.implicitHeight + 8

                            SectionRule {
                                id: rule
                                y: parent.modelData.gap
                                width: parent.width
                                label: parent.modelData.label
                                meta: parent.modelData.meta
                                metaColor: win.ink(parent.modelData.tone)
                            }
                        }
                    }
                    DelegateChoice {
                        roleValue: "task"

                        Item {
                            id: line
                            required property var modelData
                            width: ListView.view.width
                            implicitHeight: 32

                            TaskRow {
                                y: 2
                                width: parent.width
                                task: line.modelData.task
                                hito: win.hito
                                note: line.modelData.note
                                noteColor: win.ink(line.modelData.tone)
                                mark: win.hito.completing[line.modelData.task.id] === undefined ? ""
                                    : win.hito.completing[line.modelData.task.id] === "busy" ? "busy" : "done"
                                onCompleteRequested: win.hito.complete(line.modelData.task)
                            }
                        }
                    }
                    DelegateChoice {
                        roleValue: "more"

                        Label {
                            required property var modelData
                            topPadding: 6
                            text: modelData.text
                            color: Ryce.Palette.fg2
                            font.pixelSize: Ui.meta
                        }
                    }
                }
            }
        }
    }
}
