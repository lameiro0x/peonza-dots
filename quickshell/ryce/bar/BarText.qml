import QtQuick
import qs as Ryce

// A bar string centred optically: the ink of `ink` (digits by default, which share the
// cap height; a glyph passes itself) lands on `centre`, not the line box. The line box
// carries each face's ascent, descent and gap, so anchoring it put Doto's 26 px
// numerals visibly high in the band. `reserve` holds the width of the widest value a
// readout can take, so a changing number never moves its neighbours; the value hugs
// its icon and the slack trails it. Words come in the bar's face (BarUi.face), so a
// glyph in the icon font sets its weight back to normal too.
Text {
    id: t
    property string ink: "0"
    property string reserve: ""
    // Tabular figures for values that change. Never for names: Inter's tnum also sets
    // punctuation tabular, which widens a «-» past the measured label width.
    property bool tabular: reserve !== ""
    property real centre: parent ? parent.height / 2 : 0
    readonly property real inkHeight: inkBox.tightBoundingRect.height

    y: Math.round(centre - (inkBox.tightBoundingRect.y + inkBox.tightBoundingRect.height / 2) - baselineOffset)
    width: reserve === "" ? implicitWidth : Math.max(implicitWidth, Math.ceil(reserveBox.advanceWidth))
    textFormat: Text.PlainText
    color: Ryce.Palette.fg0
    font.family: BarUi.face
    font.pixelSize: BarUi.textPx
    font.weight: BarUi.weight
    font.features: tabular ? { "tnum": 1 } : ({})

    TextMetrics {
        id: inkBox
        font: t.font
        text: t.ink
    }
    TextMetrics {
        id: reserveBox
        font: t.font
        text: t.reserve
    }
}
