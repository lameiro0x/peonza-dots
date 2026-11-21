import QtQuick
import Quickshell
import qs
import qs as Ryce
import "../prose.js" as Prose

// The desk clock. Each theme sets its own type: Origen a film timecode in Martian Mono
// (the seconds run, small, like a counter), Grafito Doto dot-matrix numerals, Ola a
// large, airy Instrument Serif, Tinta a bold terminal readout with its seconds counter
// (a HUD line, like the rest of its desk). Under it the Spanish date and a quiet line:
// theme and ISO week. It sits on a Card: its inks are DeskUi's.
// Papel writes the hour in words instead (Written, prose.js), and sets the rest as a
// book would: the part of the day and the date in words in the text italic (the digits
// are the bar's), then a small-capitals line under a gilt fleuron with the week in roman
// numerals.
Column {
    id: clock
    property bool shown
    property bool live          // shown and not covered: only then does the clock tick
    readonly property var es: Qt.locale("es_ES")
    readonly property bool folio: DeskUi.folio
    readonly property var stance: ({
        origen: { size: 88, weight: Font.Normal, spacing: -1, seconds: true, inset: 5 },
        grafito: { size: 116, weight: Font.Bold, spacing: 4, seconds: false, inset: 0 },
        ola: { size: 136, weight: Font.Normal, spacing: -2, seconds: false, inset: 6 },
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
        visible: !clock.folio
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
        visible: !clock.folio
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
        visible: !clock.folio
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

    // Papel. Loaded only there: the other themes never pay for its fonts' metrics.
    Reveal {
        visible: clock.folio
        on: clock.shown
        order: 0

        Loader {
            active: clock.folio

            sourceComponent: Written {
                text: Prose.hour(sys.date.getHours(), sys.date.getMinutes())
                live: clock.live
                px: 72
            }
        }
    }
    // «de la noche · jueves, diecinueve de noviembre»
    Reveal {
        visible: clock.folio
        on: clock.shown
        order: 1

        Label {
            readonly property string part: Prose.partOfDay(sys.date.getHours(), sys.date.getMinutes())
            text: (part !== "" ? part + "  ·  " : "") + clock.es.toString(sys.date, "dddd") + ", "
                + Prose.number(sys.date.getDate(), false) + " de " + clock.es.toString(sys.date, "MMMM")
            color: DeskUi.soft
            font.family: Ryce.Palette.fontUi
            font.italic: true
            font.pixelSize: 17
            elide: Text.ElideNone
        }
    }
    // «❦ PAPEL · SEMANA XLVII» in small capitals.
    Reveal {
        visible: clock.folio
        on: clock.shown
        order: 2

        Row {
            spacing: 8

            Label {
                anchors.baseline: week.baseline
                text: "❦"
                color: Ryce.Palette.tint
                font.family: "EB Garamond"         // the fleuron is Garamond's: Literata has none
                font.pixelSize: 20
                elide: Text.ElideNone
            }
            Label {
                id: week
                text: Ryce.Palette.themeName.toLowerCase() + "  ·  semana " + Prose.roman(clock.isoWeek(sys.date))
                color: DeskUi.dim
                font.family: Ryce.Palette.fontUi
                font.pixelSize: 13
                font.features: { "smcp": 1 }
                font.letterSpacing: 0.8
                elide: Text.ElideNone
            }
        }
    }
}
