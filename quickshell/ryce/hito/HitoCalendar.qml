import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qs
import qs as Ryce

// The drawer's month: Spanish, Monday first, each day carrying a bar per pending task in
// its project's theme hue (three at most, and «+N» beside them for the rest), so
// busy weeks and each project's share read at a glance. Above, the projects on show,
// which double as the filter. Today wears the pill; the chosen day sits on a ground that
// slides from day to day, and its tasks list under the grid, rising in. A month comes in
// from the side it was paged from. Overdue days put their number in the warn colour.
// Chevrons, the wheel, PageUp/PageDown page months; the arrows move the day; Home, or a
// click on the month's name, comes back to today. Repeating tasks show where Hito has
// put their next turn, read-only as in the list (no rule is expanded here).
ColumnLayout {
    id: cal
    property Hito hito
    property string project: ""             // "" = every project
    signal projectPicked(string key)

    readonly property var es: Qt.locale("es_ES")
    readonly property int cell: Math.floor(width / 7)
    readonly property int cellHeight: 46
    readonly property int bars: 3
    readonly property var parts: hito.month.split("-").map(Number)
    property string chosen: hito.today      // the selected day, ISO
    // The month's tasks once they are in (none while another month's are), the project
    // filter applied, by day.
    readonly property var shown: hito.monthOf !== hito.month ? []
        : project === "" ? hito.monthTasks : hito.ofProject(hito.monthTasks, project)
    readonly property var byDay: {
        const out = {};
        for (const t of shown) (out[t.date] = out[t.date] ?? []).push(t);
        return out;
    }
    readonly property var dayTasks: byDay[chosen] ?? []

    function key(d) { return hito.day(d).slice(0, 7); }
    // Pages `n` months, sliding the new one in from that side; the chosen day becomes
    // today when the new month holds it, else its first.
    function page(n, day) {
        const d = new Date(parts[0], parts[1] - 1 + n, 1);
        slide.from = n > 0 ? 36 : -36;
        hito.month = key(d);
        chosen = day ?? (key(d) === hito.today.slice(0, 7) ? hito.today : hito.day(d));
        slide.restart();
    }
    function pick(iso) {
        const n = (Number(iso.slice(0, 4)) - parts[0]) * 12 + Number(iso.slice(5, 7)) - parts[1];
        if (n !== 0) page(n, iso);
        else chosen = iso;
    }
    function home() {
        const n = (Number(hito.today.slice(0, 4)) - parts[0]) * 12 + Number(hito.today.slice(5, 7)) - parts[1];
        if (n !== 0) page(n, hito.today);
        else chosen = hito.today;
    }
    // A fresh month on every opening (HitoDrawer calls it), as the bar's calendar does.
    function reset() {
        hito.month = hito.today.slice(0, 7);
        chosen = hito.today;
    }

    spacing: 0
    Keys.onLeftPressed: pick(hito.shift(chosen, -1))
    Keys.onRightPressed: pick(hito.shift(chosen, 1))
    Keys.onUpPressed: pick(hito.shift(chosen, -7))
    Keys.onDownPressed: pick(hito.shift(chosen, 7))
    Keys.onPressed: e => {
        if (e.key === Qt.Key_PageUp || e.key === Qt.Key_PageDown) page(e.key === Qt.Key_PageUp ? -1 : 1);
        else if (e.key === Qt.Key_Home) home();
        else return;
        e.accepted = true;
    }

    // The month's name, and the chevrons.
    Item {
        Layout.fillWidth: true
        implicitHeight: 30

        Label {
            id: title
            anchors.verticalCenter: parent.verticalCenter
            readonly property bool away: cal.hito.month !== cal.hito.today.slice(0, 7)
            text: cal.es.standaloneMonthName(cal.parts[1] - 1, Locale.LongFormat) + " " + cal.parts[0]
            color: Ryce.Palette.fg0
            font.family: Ryce.Palette.fontDisplay
            font.pixelSize: Math.max(18, Ryce.Palette.fontDisplayMinPx)
            elide: Text.ElideNone

            MouseArea {
                anchors.fill: parent
                enabled: title.away
                cursorShape: Qt.PointingHandCursor
                onClicked: cal.home()
            }
        }
        Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            Ryce.IconButton {
                size: 26
                glyph: String.fromCodePoint(0xf0141)     // md-chevron_left
                Accessible.name: "Mes anterior"
                onClicked: cal.page(-1)
            }
            Ryce.IconButton {
                size: 26
                glyph: Ui.chevron
                Accessible.name: "Mes siguiente"
                onClicked: cal.page(1)
            }
        }
    }

    // The projects this month touches: a legend in their hues, and the filter.
    Choices {
        Layout.fillWidth: true
        Layout.topMargin: 10
        options: [{ key: "", label: "todos" }].concat(
            cal.hito.projectsIn(cal.hito.monthOf === cal.hito.month ? cal.hito.monthTasks : [], cal.project)
                .map(p => ({ key: p.key, label: p.name, hue: p.hue })))
        current: cal.project
        square: Ryce.Palette.pillRadius < 4
        hito: cal.hito
        onPicked: key => cal.projectPicked(key)
    }

    DayOfWeekRow {
        Layout.topMargin: 12
        Layout.preferredWidth: 7 * cal.cell
        implicitHeight: 20
        padding: 0
        spacing: 0
        locale: cal.es

        delegate: Item {
            required property string narrowName
            implicitWidth: cal.cell
            implicitHeight: 20

            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                text: parent.narrowName.toUpperCase()
                color: Ryce.Palette.fg2
                font.pixelSize: Ui.meta
                elide: Text.ElideNone
            }
        }
    }

    Item {
        id: sheet
        Layout.preferredWidth: 7 * cal.cell
        implicitHeight: 6 * cal.cellHeight
        clip: true

        // A notch per month, touchpads adding up to one first.
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.NoButton
            property int acc: 0
            onWheel: wheel => {
                acc += wheel.angleDelta.y;
                while (Math.abs(acc) >= 120) {
                    cal.page(acc > 0 ? -1 : 1);
                    acc -= acc > 0 ? 120 : -120;
                }
            }
        }

        Item {
            id: leaf
            width: parent.width
            height: parent.height

            // The chosen day's ground, gliding from day to day.
            Rectangle {
                id: ground
                readonly property int at: Math.round((cal.hito.date(cal.chosen) - cal.hito.date(cal.hito.gridStart(cal.hito.month))) / 86400000)
                visible: at >= 0 && at < 42
                x: (at % 7) * cal.cell + 2
                y: Math.floor(at / 7) * cal.cellHeight + 2
                width: cal.cell - 4
                height: cal.cellHeight - 4
                radius: Math.min(Ryce.Palette.rounding, 10)
                color: Ryce.Palette.bg2
                border.width: 1
                border.color: Ryce.Palette.line
                Behavior on x { NumberAnimation { duration: Math.round(Ryce.Palette.motionMs * 0.5); easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
                Behavior on y { NumberAnimation { duration: Math.round(Ryce.Palette.motionMs * 0.5); easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
            }

            MonthGrid {
                id: grid
                width: parent.width
                height: parent.height
                padding: 0
                spacing: 0
                locale: cal.es
                month: cal.parts[1] - 1
                year: cal.parts[0]

                delegate: Item {
                    id: day
                    required property var model
                    readonly property string iso: cal.hito.day(model.date)
                    readonly property var tasks: cal.byDay[iso] ?? []
                    readonly property bool inMonth: model.month === grid.month
                    readonly property bool isToday: iso === cal.hito.today
                    readonly property bool late: iso < cal.hito.today && tasks.length > 0
                    readonly property bool weekend: model.date.getDay() === 0 || model.date.getDay() === 6
                    implicitWidth: cal.cell
                    implicitHeight: cal.cellHeight
                    opacity: inMonth || isToday ? 1 : Ryce.Palette.light ? 0.75 : 0.5
                    Accessible.role: Accessible.Button
                    Accessible.name: cal.es.toString(model.date, "dddd d 'de' MMMM") + (isToday ? ", hoy" : "")
                        + (tasks.length > 0 ? ", " + tasks.length + (tasks.length === 1 ? " tarea" : " tareas") : "")

                    Rectangle {
                        visible: day.isToday
                        anchors.horizontalCenter: number.horizontalCenter
                        y: number.y - 1
                        width: Math.max(24, number.implicitWidth + 12)
                        height: number.implicitHeight + 2
                        radius: Math.min(Ryce.Palette.pillRadius, height / 2)
                        color: Ryce.Palette.pill
                    }
                    Label {
                        id: number
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 6
                        text: day.model.day
                        color: day.isToday ? Ryce.Palette.inkOnPill
                            : day.late ? Ryce.Palette.warn
                            : !day.inMonth ? Ryce.Palette.fg2
                            : day.weekend ? Ryce.Palette.fg1 : Ryce.Palette.fg0
                        font.pixelSize: Ui.body
                        font.features: { "tnum": 1 }
                        elide: Text.ElideNone
                    }
                    Column {
                        id: stack
                        readonly property int more: day.tasks.length - cal.bars
                        x: 8
                        y: 27
                        spacing: 2

                        Repeater {
                            model: day.tasks.slice(0, cal.bars)

                            Rectangle {
                                required property var modelData
                                // Room at the end for the «+N» of a fuller day.
                                width: cal.cell - 16 - (stack.more > 0 ? 14 : 0)
                                height: 3
                                radius: Math.min(1.5, Ryce.Palette.pillRadius)
                                color: cal.hito.dotColor(modelData.hue, Ryce.Palette.fg2)
                            }
                        }
                    }
                    Label {
                        visible: stack.more > 0
                        x: cal.cell - 8 - implicitWidth
                        y: stack.y + Math.round((stack.height - implicitHeight) / 2)
                        text: "+" + stack.more
                        color: Ryce.Palette.fg2
                        font.pixelSize: 9
                        font.features: { "tnum": 1 }
                        elide: Text.ElideNone
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            cal.forceActiveFocus();
                            cal.pick(day.iso);
                        }
                    }
                }
            }
        }

        // A new month slides in from where it was paged from.
        ParallelAnimation {
            id: slide
            property real from: 36
            XAnimator {
                target: leaf
                from: slide.from
                to: 0
                duration: Math.round(Ryce.Palette.motionMs * 0.6)
                easing.type: Easing.BezierSpline
                easing.bezierCurve: Ryce.Palette.motionCurve
            }
            OpacityAnimator {
                target: leaf
                from: 0
                to: 1
                duration: Math.round(Ryce.Palette.motionMs * 0.45)
                easing.type: Easing.OutQuad
            }
        }
    }

    SectionRule {
        Layout.fillWidth: true
        Layout.topMargin: 14
        label: cal.chosen === cal.hito.today ? "hoy" : cal.es.toString(cal.hito.date(cal.chosen), "dddd d 'de' MMMM")
        meta: cal.hito.monthOf !== cal.hito.month ? "…"
            : cal.dayTasks.length === 0 ? "nada" : String(cal.dayTasks.length)
        metaColor: Ryce.Palette.fg2
    }

    // The chosen day's tasks, rising in each time the day changes.
    ListView {
        id: list
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.topMargin: 8
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: cal.dayTasks
        spacing: 2
        transform: Translate { id: rise }

        delegate: TaskRow {
            required property var modelData
            width: ListView.view.width
            task: modelData
            hito: cal.hito
            note: [modelData.time, cal.project === "" ? modelData.project : ""].filter(s => s !== "").join(" · ")
            noteColor: modelData.date < cal.hito.today ? Ryce.Palette.warn : Ryce.Palette.fg2
            mark: cal.hito.completing[modelData.id] === undefined ? ""
                : cal.hito.completing[modelData.id] === "busy" ? "busy" : "done"
            onCompleteRequested: cal.hito.complete(modelData)
        }
    }
    onChosenChanged: {
        list.positionViewAtBeginning();
        enter.restart();
    }
    ParallelAnimation {
        id: enter
        NumberAnimation { target: list; property: "opacity"; from: 0; to: 1; duration: Math.round(Ryce.Palette.motionMs * 0.5); easing.type: Easing.OutQuad }
        NumberAnimation { target: rise; property: "y"; from: 8; to: 0; duration: Math.round(Ryce.Palette.motionMs * 0.6); easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve }
    }
}
