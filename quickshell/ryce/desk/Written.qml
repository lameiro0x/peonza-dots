import QtQuick
import qs
import qs as Ryce
import "../prose.js" as Prose

// Papel's hour, written rather than displayed («Las diez y cuarto»): the display italic
// with one swash capital, the initial in the lamp's gilt and the rest in the card's ink.
// The capital is a Text of its own: `swsh` on the whole line would turn every capital
// into a swash, and a line holds only plain text (Label). It is written in from left to
// right at a pen's pace when the desk comes into view (`live` rises) and, when the
// wording changes, from the first word that changed: a clip that widens over the line,
// its leading edge feathered into the card's ground so the letters arrive, not appear.
// A clip and one NumberAnimation for under a second: nothing runs while it rests, and
// nothing at all while the desk is covered (the clock stops, so the words never change).
// The rest of the line starts at the swash capital's advance, as one shaped line would set
// it: a Text's implicitWidth adds its last glyph's overhang, and the swash L's tail runs
// 12 px past its advance at 72 px, under the next letter (measured: TextMetrics and
// FontMetrics carry `swsh`, advance 35.9 against the plain L's 42.0; the Label reports 47.9).
// The width is the current phrase's ink, so the card fits what it says: it changes only
// when the wording does, once, as the new words start to be written; at rest it never moves.
Item {
    id: written
    property string text
    property bool live
    property int px: 72
    property color initialInk: Ryce.Palette.tint
    property color ink: DeskUi.ink
    property color ground: DeskUi.ground

    readonly property int bleed: Math.round(px * 0.3)  // swash strokes that reach past the line box
    readonly property int feather: Math.round(px * 0.6)
    // A method call binds to its arguments only: name the font, or the first measure (taken
    // before `font: initial.font` lands) would stick.
    readonly property real advance: {
        void initialFont.font;
        return initialFont.advanceWidth(text.charAt(0));
    }
    // The line's end, the rest's overhang included (its implicitWidth carries it).
    readonly property real lineWidth: advance + rest.implicitWidth
    // How much of the line is written, in pixels from its start; all of it at rest.
    property real reach: 1e6
    property string previous: ""

    // Measured from the string, never read back from the Labels: a change handler may run
    // before their bindings have taken the new text.
    function span(t, n) {
        return n <= 0 ? 0 : initialFont.advanceWidth(t.charAt(0)) + restFont.advanceWidth(t.slice(1, n));
    }
    // Where the old and the new wording part, snapped back to the start of that word.
    function cut(before, after) {
        let i = 0;
        while (i < before.length && i < after.length && before[i] === after[i]) i++;
        if (i < after.length) i = after.lastIndexOf(" ", i) + 1;
        return span(after, i);
    }
    // From `from` px to the line's end; a whole line starts with the feather before it.
    function write(from) {
        pen.stop();
        const end = span(text, text.length);
        const start = Math.min(from <= 0 ? -(feather + bleed) : from, reach, end);
        if (Ryce.Palette.motionMs <= 0 || start >= end) {
            reach = 1e6;
            return;
        }
        pen.from = start;
        pen.to = end;
        // One pace for every phrase: the widest (about eleven ems) takes 0.9 s, a changed
        // last word a beat.
        pen.duration = Math.round(Math.max(240, 900 * (end - start) / (11 * px + feather)));
        pen.start();
    }
    onLiveChanged: if (live) { reach = 0; write(0); }
    onTextChanged: {
        if (live) write(cut(previous, text));
        else reach = 1e6;
        previous = text;
    }
    Component.onCompleted: {
        previous = text;
        if (live) { reach = 0; write(0); }
    }

    // The swash's own ink can reach past a short rest (never in Spanish, but cheap to keep).
    implicitWidth: Math.ceil(Math.max(lineWidth, initial.implicitWidth))
    implicitHeight: initial.implicitHeight

    NumberAnimation {
        id: pen
        target: written
        property: "reach"
        easing.type: Easing.InOutSine
        onFinished: written.reach = 1e6
    }
    FontMetrics {
        id: initialFont
        font: initial.font
    }
    FontMetrics {
        id: restFont
        font: rest.font
    }

    // Written up to `reach`, fading out over the `feather` past it; all of it at rest.
    Item {
        readonly property bool writing: written.reach < written.lineWidth
        x: -written.bleed
        y: -written.bleed
        width: writing ? Math.max(0, written.bleed + written.reach + written.feather) : written.lineWidth + 2 * written.bleed
        height: written.height + 2 * written.bleed
        clip: true

        Item {
            x: written.bleed
            y: written.bleed

            Label {
                id: initial
                text: written.text.charAt(0)
                color: written.initialInk
                font.family: Ryce.Palette.fontDisplay
                font.italic: true
                font.pixelSize: written.px
                font.features: { "swsh": 1 }
                renderType: Text.CurveRendering
                elide: Text.ElideNone
            }
            Label {
                id: rest
                x: written.advance
                text: written.text.slice(1)
                color: written.ink
                font.family: Ryce.Palette.fontDisplay
                font.italic: true
                font.pixelSize: written.px
                renderType: Text.CurveRendering
                elide: Text.ElideNone
            }
        }
        // The pen's edge: the last letters fade in from the card's own ground.
        Rectangle {
            visible: parent.writing
            x: written.bleed + written.reach
            width: written.feather
            height: parent.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Ryce.Palette.rgba(written.ground, 0) }
                GradientStop { position: 1; color: written.ground }
            }
        }
    }
}
