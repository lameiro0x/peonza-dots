import QtQuick
import Quickshell
import qs
import qs as Ryce

// A BCD binary clock: six columns (H H M M S S), four rows (bits 8 4 2 1, top down),
// a lit circle bright, an unlit one a dim grey. Every bit of the grid is drawn, even
// those a tens digit never reaches, so it reads as one block. Ticks once a second, and
// only while `live`; changes are instant, a terminal readout has no easing. Over it a
// one-word key in the HUD's voice, so the block reads as a clock. Pinned as it was at
// e398d3b (the user's pick, 2026-11-15) like its card in DeskScreen: the key keeps the
// ink DeskUi gave fg2 then (6 twentieths toward fg0, 4.55:1 on that card), whatever the
// desk's alpha does since.
Column {
    id: bin
    property bool live
    readonly property int dot: 34
    readonly property string digits: Qt.formatTime(sys.date, "HHmmss")

    spacing: 12

    SystemClock {
        id: sys
        enabled: bin.live
        precision: SystemClock.Seconds
    }

    Label {
        text: "HORA_BIN"
        color: DeskUi.mix(Ryce.Palette.fg2, Ryce.Palette.fg0, 0.3)
        font.family: Ryce.Palette.fontMono
        font.pixelSize: 11
        font.bold: true
        font.letterSpacing: 1.2
    }
    Grid {
        columns: 6
        spacing: 8

        Repeater {
            model: 24

            Rectangle {
                required property int index
                // Grid fills row by row: index 0..5 is the 8s row.
                readonly property bool lit: (Number(bin.digits[index % 6]) >> (3 - Math.floor(index / 6))) & 1

                width: bin.dot
                height: bin.dot
                radius: bin.dot / 2
                color: lit ? Ryce.Palette.rgba(Ryce.Palette.fg0, 0.9) : Ryce.Palette.rgba(Ryce.Palette.fg1, 0.26)
            }
        }
    }
}
