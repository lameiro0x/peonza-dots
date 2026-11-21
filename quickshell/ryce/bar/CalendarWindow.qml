import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import qs as Ryce

// The month, dropped under the bar's clock (a click on it) on that bar's screen: one
// more plate of the bar's (Plate, the bar's skin and faces, the windows' rounding),
// right-aligned with the clock's plate. Spanish, Monday first; today wears the
// workspace pill. The chevrons, the wheel and the arrows page through it (left and
// right a month, up and down a year), a click on the month or Home comes back to
// today. Keyboard only while shown; Escape or a click anywhere else closes it.
// BarWindow loads it on demand and drops it on `gone()`.
PanelWindow {
    id: win
    property bool shown: false
    signal closeRequested()
    signal gone()

    readonly property var es: Qt.locale("es_ES")
    readonly property int shade: BarUi.edge     // room for the plate's shadow; the right one lines up with the clock's plate
    readonly property int pad: 14
    readonly property int cell: Math.round(BarUi.textPx * 2.2)
    // Ola's capsules and Papel's running head title the month in their display serif,
    // larger; a theme whose display face is its UI face keeps the readouts' size, or the
    // title crowds the chevrons.
    readonly property bool serif: (BarUi.skin === "capsule" || BarUi.folio) && Ryce.Palette.fontDisplay !== Ryce.Palette.fontUi
    readonly property var today: new Date()     // a fresh window per opening
    property int month: today.getMonth()        // 0-11, as MonthGrid counts
    property int year: today.getFullYear()
    readonly property bool away: month !== today.getMonth() || year !== today.getFullYear()
    // 0 = gone, 1 = open. Drops in on the theme's curve, leaves faster.
    property real p: 0

    function step(months) {
        const m = month + months;
        year += Math.floor(m / 12);
        month = ((m % 12) + 12) % 12;
    }
    function home() {
        month = today.getMonth();
        year = today.getFullYear();
    }

    visible: shown || p > 0
    anchors { top: true; right: true }
    margins.top: BarUi.plateTop + BarUi.chipHeight + 8 - shade
    implicitWidth: card.width + 2 * shade
    implicitHeight: card.height + 2 * shade
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"
    mask: Region { item: card }

    WlrLayershell.namespace: "qs-calendar"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: shown ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    onShownChanged: shown ? open() : close()
    Component.onCompleted: if (shown) open()
    function open() {
        leave.stop();
        enter.duration = Math.round(Ryce.Palette.motionMs * 0.6);
        enter.start();
    }
    function close() {
        enter.stop();
        leave.duration = Math.round(Ryce.Palette.motionMs * 0.4);
        leave.start();
    }
    NumberAnimation {
        id: enter
        target: win
        property: "p"
        to: 1
        easing.type: Easing.BezierSpline
        easing.bezierCurve: Ryce.Palette.motionCurve
    }
    NumberAnimation {
        id: leave
        target: win
        property: "p"
        to: 0
        easing.type: Easing.InCubic
        onFinished: win.gone()
    }

    HyprlandFocusGrab {
        active: win.shown
        windows: [win]
        onCleared: win.closeRequested()
    }

    Item {
        id: card
        x: win.shade
        y: win.shade - Math.round((1 - win.p) * 6)
        width: grid.width + 2 * win.pad
        height: column.height + 2 * win.pad
        opacity: win.p
        focus: true
        Accessible.role: Accessible.Dialog
        Accessible.name: "Calendario, " + title.text

        Keys.onEscapePressed: win.closeRequested()
        Keys.onLeftPressed: win.step(-1)
        Keys.onRightPressed: win.step(1)
        Keys.onUpPressed: win.step(-12)
        Keys.onDownPressed: win.step(12)
        Keys.onPressed: e => {
            if (e.key === Qt.Key_Home) {
                win.home();
                e.accepted = true;
            }
        }

        Plate {
            anchors.fill: parent
            radius: Ryce.Palette.rounding
        }
        // A month per notch; touchpads add their small deltas up to a notch first.
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.NoButton
            property int acc: 0
            onWheel: wheel => {
                acc += wheel.angleDelta.y;
                while (Math.abs(acc) >= 120) {
                    win.step(acc > 0 ? -1 : 1);
                    acc -= acc > 0 ? 120 : -120;
                }
            }
        }

        Column {
            id: column
            x: win.pad
            y: win.pad
            spacing: 4

            Item {
                width: grid.width
                height: win.cell

                Ryce.IconButton {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    size: win.cell - 6
                    glyph: String.fromCodePoint(0xf0141)     // md-chevron_left
                    Accessible.name: "Mes anterior"
                    onClicked: win.step(-1)
                }
                BarText {
                    id: title
                    x: Math.round((parent.width - width) / 2)
                    readonly property string words: win.es.standaloneMonthName(win.month, Locale.LongFormat) + " " + win.year
                    text: BarUi.dots ? words.toUpperCase() : words
                    color: Ryce.Palette.fg0
                    font.family: win.serif ? Ryce.Palette.fontDisplay : BarUi.face
                    font.pixelSize: win.serif ? Math.round(BarUi.textPx * 1.5) : BarUi.textPx
                    font.weight: BarUi.dots ? BarUi.weight : win.serif ? Font.Normal : Font.Medium

                    MouseArea {
                        anchors.fill: parent
                        enabled: win.away
                        cursorShape: Qt.PointingHandCursor
                        onClicked: win.home()
                    }
                }
                Ryce.IconButton {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    size: win.cell - 6
                    glyph: Ryce.Ui.chevron
                    Accessible.name: "Mes siguiente"
                    onClicked: win.step(1)
                }
            }
            DayOfWeekRow {
                width: grid.width
                height: Math.round(win.cell * 0.8)
                padding: 0
                spacing: 0
                locale: win.es

                delegate: Item {
                    required property string narrowName
                    implicitWidth: win.cell
                    implicitHeight: Math.round(win.cell * 0.8)

                    BarText {
                        x: Math.round((parent.width - width) / 2)
                        text: parent.narrowName.toUpperCase()
                        ink: "L"
                        color: Ryce.Palette.fg2
                        font.pixelSize: BarUi.dots ? BarUi.textPx - 2 : BarUi.smallPx     // Doto falls apart smaller
                    }
                }
            }
            MonthGrid {
                id: grid
                width: 7 * win.cell
                height: 6 * win.cell
                padding: 0
                spacing: 0
                locale: win.es
                month: win.month
                year: win.year

                delegate: Item {
                    id: day
                    required property var model
                    readonly property bool inMonth: model.month === grid.month
                    readonly property bool weekend: model.date.getDay() === 0 || model.date.getDay() === 6
                    implicitWidth: win.cell
                    implicitHeight: win.cell
                    Accessible.name: win.es.toString(model.date, "dddd d 'de' MMMM") + (model.today ? ", hoy" : "")

                    Rectangle {
                        visible: day.model.today
                        anchors.centerIn: parent
                        width: parent.width - 4
                        height: parent.height - 4
                        radius: Math.min(Ryce.Palette.pillRadius, height / 2)
                        color: Ryce.Palette.pill
                    }
                    BarText {
                        x: Math.round((parent.width - width) / 2)
                        text: day.model.day
                        tabular: true
                        color: day.model.today ? Ryce.Palette.inkOnPill
                            : !day.inMonth ? Ryce.Palette.fg2
                            : day.weekend ? Ryce.Palette.fg1 : Ryce.Palette.fg0
                        // Quieter than the month, never gone: fg2 at half on cream falls under 2:1.
                        opacity: day.inMonth || day.model.today ? 1 : Ryce.Palette.light ? 0.75 : 0.5
                    }
                }
            }
        }
    }
}
