import QtQuick
import qs
import qs as Ryce

// One desk stat: a quiet label, the value in tabular mono, and a trailing mark
// (sparkline or bar) passed as the child.
Reveal {
    id: row
    property string label
    property string value
    property bool available: true
    property alias trailing: slot.data      // the sparkline or bar

    visible: available

    // The value column fits the widest value in the theme's face (Origen's mono runs
    // wide), the same in every row so the marks line up.
    TextMetrics {
        id: widest
        font: val.font
        text: "100 % ocupada  ·  2850 MHz"
    }

    Row {
        Label {
            width: 128
            anchors.baseline: val.baseline
            text: row.label
            color: DeskUi.dim
            font.family: Ryce.Palette.fontUi
            font.pixelSize: 13
        }
        Label {
            id: val
            width: Math.max(200, Math.ceil(widest.advanceWidth) + 16)
            text: row.value
            color: DeskUi.ink
            font.pixelSize: 14
            font.features: { "tnum": 1 }
        }
        Item {
            id: slot
            implicitWidth: 120
            implicitHeight: 20
        }
    }
}
