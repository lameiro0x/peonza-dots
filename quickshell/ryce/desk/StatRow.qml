import QtQuick
import qs
import qs as Ryce

// One desk stat: a quiet label, the value in tabular mono, and a trailing mark
// (sparkline or bar) passed as the child.
// Papel sets the stats as a table of contents instead: the label in italic, a dot
// leader, the value flush right in the card's ink (one ink for every figure, as a page
// prints them) with old-style figures, and no mark. Its leader dots sit on one grid for
// every row, as a printed contents page lines them up.
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
        font: DeskUi.folio ? entry.font : val.font
        text: "100 % ocupada  ·  2850 MHz"
    }

    // Only the theme's own layout takes room (childrenRect counts hidden items too).
    Row {
        visible: !DeskUi.folio
        width: visible ? implicitWidth : 0
        height: visible ? implicitHeight : 0

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

    Item {
        id: contents
        readonly property real step: 7      // one leader dot every `step` px
        visible: DeskUi.folio
        width: visible ? 112 + Math.ceil(widest.advanceWidth) + 40 : 0
        height: visible ? entry.height : 0

        Label {
            id: title
            anchors.baseline: entry.baseline
            text: row.label
            color: DeskUi.soft
            font.family: Ryce.Palette.fontUi
            font.italic: true
            font.pixelSize: 14
            elide: Text.ElideNone
        }
        Label {
            id: entry
            anchors.right: parent.right
            text: row.value
            color: DeskUi.ink
            font.family: Ryce.Palette.fontUi
            font.pixelSize: 14
            font.features: { "onum": 1 }        // proportional: Literata has no tabular old-style
            elide: Text.ElideNone
        }
        // The leader, from a grid point past the label to one before the value.
        Label {
            readonly property real from: Math.ceil((title.width + 8) / contents.step) * contents.step
            readonly property real to: entry.x - 8
            x: from
            anchors.baseline: entry.baseline
            text: ".".repeat(Math.max(0, Math.floor((to - from) / contents.step)))
            color: DeskUi.dim
            font.family: Ryce.Palette.fontUi
            font.pixelSize: 14
            // Every dot advances one step: the dot's own width plus the space after it.
            font.letterSpacing: contents.step - dot.advanceWidth
            elide: Text.ElideNone

            TextMetrics {
                id: dot
                font.family: Ryce.Palette.fontUi
                font.pixelSize: 14
                text: "."
            }
        }
    }
}
