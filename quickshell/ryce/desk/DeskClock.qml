import QtQuick
import Quickshell
import qs
import qs as Ryce

// The desk clock. Each theme sets its own type: Origen a film timecode in Martian Mono
// (the seconds run, small, like a counter), Grafito Doto dot-matrix numerals, Ola a
// large, airy Instrument Serif, Tinta a bold terminal readout with its seconds counter
// (a HUD line, like the rest of its desk). Under it the Spanish date and a quiet line:
// theme and ISO week. It sits on a Card: its inks are DeskUi's.
Column {
    id: clock
    property bool shown
    property bool live          // shown and not covered: only then does the clock tick
    readonly property var es: Qt.locale("es_ES")
    readonly property var stance: ({
        origen: { size: 88, weight: Font.Normal, spacing: -1, seconds: true, inset: 5 },
        grafito: { size: 116, weight: Font.Bold, spacing: 4, seconds: false, inset: 0 },
        ola: { size: 136, weight: Font.Normal, spacing: -2, seconds: false, inset: 6 },
        papel: { size: 120, weight: Font.Bold, spacing: 0, seconds: false, inset: 6 },    // Space Mono Bold, as on the cover
        tinta: { size: 72, weight: Font.Bold, spacing: 0, seconds: true, inset: 4 }
    })[Ryce.Palette.themeId] ?? { size: 96, weight: Font.Normal, spacing: 0, seconds: false, inset: 0 }
    readonly property int timeSize: Math.max(stance.size, Ryce.Palette.fontDisplayMinPx)

    // ISO 8601 week: the Thursday of this week decides the year it belongs to.
    function isoWeek(d) {
        const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
        t.setUTCDate(t.getUTCDate() + 3 - (t.getUTCDay() + 6) % 7);
        const jan4 = new Date(Date.UTC(t.getUTCFullYear(), 0, 4));
        return 1 + Math.round(((t - jan4) / 86400000 - 3 + (jan4.getUTCDay() + 6) % 7) / 7);
    }

    spacing: 6

    SystemClock {
        id: sys
        enabled: clock.live
        precision: clock.stance.seconds ? SystemClock.Seconds : SystemClock.Minutes
    }

    Reveal {
        on: clock.shown
        order: 0

        Row {
            // Pull the big digits left by their side bearing, so they line up with the date.
            x: -clock.stance.inset
            spacing: Math.round(clock.timeSize * 0.12)

            Label {
                id: time
                // Doto (Grafito) draws its colon as a dotted dagger: use its middle dot.
                text: Qt.formatTime(sys.date, Ryce.Palette.fontDisplay === "Doto" ? "HH'\u00b7'mm" : "HH:mm")
                color: DeskUi.ink
                font.family: Ryce.Palette.fontDisplay
                font.pixelSize: clock.timeSize
                font.weight: clock.stance.weight
                font.letterSpacing: clock.stance.spacing
                font.features: { "tnum": 1 }
                elide: Text.ElideNone
            }
            // Origen's timecode seconds: a small, dim counter on the time's baseline.
            Label {
                visible: clock.stance.seconds
                anchors.baseline: time.baseline
                text: Qt.formatTime(sys.date, "ss")
                color: DeskUi.dim
                font.family: Ryce.Palette.fontDisplay
                font.pixelSize: Math.round(clock.timeSize * 0.3)
                font.features: { "tnum": 1 }
                elide: Text.ElideNone
            }
        }
    }
    Reveal {
        on: clock.shown
        order: 1

        Label {
            text: clock.es.toString(sys.date, "dddd d 'de' MMMM")
            color: DeskUi.soft
            font.family: Ryce.Palette.fontUi
            font.pixelSize: 17
            elide: Text.ElideNone
        }
    }
    Reveal {
        on: clock.shown
        order: 2

        Label {
            text: Ryce.Palette.themeName.toLowerCase() + "  ·  semana " + clock.isoWeek(sys.date)
            color: DeskUi.dim
            font.family: Ryce.Palette.fontUi
            font.pixelSize: 12
            font.letterSpacing: 0.6
            elide: Text.ElideNone
        }
    }
}
