import QtQuick
import QtQuick.Layouts
import Quickshell
import qs
import qs as Ryce

// The time large, in the theme's display face, with the Spanish date under it.
ColumnLayout {
    readonly property var es: Qt.locale("es_ES")
    // Grafito's dot-matrix face reads only at or above its minimum size, and only bold;
    // its colon is a dotted dagger, so its middle dot is the separator (as in the bar).
    readonly property bool dotMatrix: Ryce.Palette.fontDisplayMinPx > 0

    spacing: 2

    SystemClock {
        id: sys
        precision: SystemClock.Minutes
    }

    Label {
        text: Qt.formatTime(sys.date, dotMatrix ? "HH'·'mm" : "HH:mm")
        color: Ryce.Palette.fg0
        font.family: Ryce.Palette.fontDisplay
        font.pixelSize: Math.max(Ui.clock, Ryce.Palette.fontDisplayMinPx)
        font.weight: dotMatrix ? Font.Bold : Font.Light
        font.features: { "tnum": 1 }
        elide: Text.ElideNone
    }
    Label {
        Layout.fillWidth: true
        // «lunes, 9 de noviembre»
        text: es.toString(sys.date, "dddd, d 'de' MMMM")
        font.pixelSize: Ui.body
    }
}
