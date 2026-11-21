import QtQuick
import Quickshell
import qs as Ryce

// Time and date at the right end. Inline in most themes, the date first in a quieter
// ink: Grafito sets the time in its dot-matrix face at its minimum readable size, the
// largest thing on a bar that speaks that face throughout (BarUi.dots), after an
// uppercase date; Ola sets it in its display serif, Papel in its display italic with
// old-style figures, a running head's folio. Tinta stacks a small time over the
// date in numbers, as a terminal status line does. Every line is centred on its ink
// (BarText), so the large display numerals sit level with the smaller readouts. A click
// drops the month under it (CalendarWindow); its ground stays lit while that is open.
Module {
    id: clock
    property bool open: false
    readonly property var es: Qt.locale("es_ES")
    readonly property bool stacked: BarUi.skin === "box"
    readonly property bool dots: BarUi.dots
    readonly property bool serif: BarUi.skin === "capsule" || BarUi.folio
    // Doto's colon is a dotted dagger; its middle dot reads as the separator.
    readonly property string time: Qt.formatTime(sys.date, dots ? "HH'·'mm" : "HH:mm")
    readonly property string date: es.toString(sys.date, "ddd d MMM").replace(/\./g, "")     // «lun 9 nov»

    spacing: dots ? 12 : 9
    interactive: true
    lit: hovered || open
    Accessible.role: Accessible.Button
    Accessible.name: es.toString(sys.date, "dddd d 'de' MMMM, HH:mm")

    SystemClock {
        id: sys
        precision: SystemClock.Minutes
    }

    BarText {
        visible: !clock.stacked
        text: clock.dots ? clock.date.toUpperCase() : clock.date
        color: clock.dots ? Ryce.Palette.fg2 : Ryce.Palette.fg1
        font.pixelSize: clock.dots ? BarUi.textPx - 2 : BarUi.textPx
    }
    BarText {
        visible: !clock.stacked
        text: clock.time
        tabular: true
        color: Ryce.Palette.hueClock
        font.family: clock.serif ? Ryce.Palette.fontDisplay : BarUi.face
        font.pixelSize: clock.dots ? Ryce.Palette.fontDisplayMinPx : clock.serif ? Math.round(BarUi.band * 0.48) : BarUi.textPx
        font.weight: clock.dots ? BarUi.weight : clock.serif ? Font.Normal : Font.Medium     // Doto: the readouts' Black, never its specks
        font.italic: BarUi.folio
    }
    Item {
        visible: clock.stacked
        width: Math.max(top.width, bottom.width)
        height: parent.height
        readonly property int lead: 4         // between the two lines' ink

        BarText {
            id: top
            anchors.right: parent.right
            centre: parent.height / 2 - (parent.lead + bottom.inkHeight) / 2
            text: clock.time
            tabular: true
            color: Ryce.Palette.hueClock
            font.weight: Font.Medium
        }
        BarText {
            id: bottom
            anchors.right: parent.right
            centre: parent.height / 2 + (parent.lead + top.inkHeight) / 2
            text: Qt.formatDate(sys.date, "yyyy.MM.dd")
            tabular: true
            color: Ryce.Palette.fg1
            font.pixelSize: BarUi.smallPx
        }
    }
}
