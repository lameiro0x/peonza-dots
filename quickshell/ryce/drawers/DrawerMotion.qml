import QtQuick
import qs as Ryce

// The drawers' one motion (the sidebar and Aria). In: the panel comes out of its edge on
// the theme's curve (Ola's overshoots, Tinta's snaps), the content trails it by `lag` px
// and settles a beat later, and the content's tiers fade in one after another. Out: the
// content goes first, the panel follows, accelerating, in 60% of the time. A drawer
// caught leaving turns back from where it is, with no second cascade.
// Every value moves on the render thread (Animators): nothing may bind to the panel's or
// the content's offset, nor to a tier's opacity; the drawer only calls show() and hide().
Item {
    id: reveal
    required property Item panel
    required property Item content
    property var tiers: []                  // the content's blocks, in reading order
    property bool vertical: false           // the axis: x (an edge drawer) or y (a card)
    property real home                      // the panel's offset, open
    property real away                      // and closed: past the window's edge
    property real contentHome
    property real lag: 28
    signal entered()
    signal rested()                         // closed and still again

    readonly property bool running: enter.running || back.running || leave.running
    readonly property bool arriving: enter.running || back.running
    readonly property bool leaving: leave.running
    readonly property int ms: Ryce.Palette.motionMs
    readonly property int leaveMs: Math.max(140, Math.round(ms * 0.6))
    // 14 ms apart in Tinta, 32 in Ola: five tiers land within the panel's own motion.
    readonly property int step: Math.round(Math.min(32, Math.max(14, ms * 0.07)))
    readonly property real drift: away > home ? lag : -lag

    // Closed and still: everything where an opening starts from. Only while nothing moves
    // and the panel is hidden; again on each opening from rest, as `away` may have changed
    // with the panel's size.
    function settle() {
        for (const f of fades) f.stop();
        for (const t of tiers) t.opacity = 0;
        content.opacity = 1;
        if (vertical) {
            panel.y = away;
            content.y = contentHome + drift;
        } else {
            panel.x = away;
            content.x = contentHome + drift;
        }
    }
    function show() {
        if (leave.running) {
            leave.stop();
            back.start();
            return;
        }
        if (enter.running || back.running) return;
        settle();
        enter.start();
        for (const f of fades) f.restart();
    }
    function hide() {
        enter.stop();
        back.stop();
        leave.start();
    }
    Component.onCompleted: {
        if (fades.length !== tiers.length) build();
        settle();
    }

    // Whichever axis is not used animates this.
    Item { id: idle }

    ParallelAnimation {
        id: enter
        XAnimator {
            target: reveal.vertical ? idle : reveal.panel
            to: reveal.home
            duration: reveal.ms
            easing.type: Easing.BezierSpline
            easing.bezierCurve: Ryce.Palette.motionCurve
        }
        YAnimator {
            target: reveal.vertical ? reveal.panel : idle
            to: reveal.home
            duration: reveal.ms
            easing.type: Easing.BezierSpline
            easing.bezierCurve: Ryce.Palette.motionCurve
        }
        // The content trails: longer and on a softer tail, so it settles after the panel.
        XAnimator {
            target: reveal.vertical ? idle : reveal.content
            to: reveal.contentHome
            duration: Math.round(reveal.ms * 1.25)
            easing.type: Easing.OutQuint
        }
        YAnimator {
            target: reveal.vertical ? reveal.content : idle
            to: reveal.contentHome
            duration: Math.round(reveal.ms * 1.25)
            easing.type: Easing.OutQuint
        }
        onFinished: reveal.entered()
    }
    // Turned back mid-leave: the panel and the content return from where they are.
    ParallelAnimation {
        id: back
        XAnimator {
            target: reveal.vertical ? idle : reveal.panel
            to: reveal.home
            duration: Math.round(reveal.ms * 0.7)
            easing.type: Easing.OutCubic
        }
        YAnimator {
            target: reveal.vertical ? reveal.panel : idle
            to: reveal.home
            duration: Math.round(reveal.ms * 0.7)
            easing.type: Easing.OutCubic
        }
        XAnimator {
            target: reveal.vertical ? idle : reveal.content
            to: reveal.contentHome
            duration: Math.round(reveal.ms * 0.7)
            easing.type: Easing.OutCubic
        }
        YAnimator {
            target: reveal.vertical ? reveal.content : idle
            to: reveal.contentHome
            duration: Math.round(reveal.ms * 0.7)
            easing.type: Easing.OutCubic
        }
        OpacityAnimator {
            target: reveal.content
            to: 1
            duration: Math.round(reveal.ms * 0.4)
        }
        onFinished: reveal.entered()
    }
    ParallelAnimation {
        id: leave
        // Material's accelerate curve: it starts at once and leaves at speed.
        XAnimator {
            target: reveal.vertical ? idle : reveal.panel
            to: reveal.away
            duration: reveal.leaveMs
            easing.type: Easing.BezierSpline
            easing.bezierCurve: [0.3, 0.0, 0.8, 0.15, 1.0, 1.0]
        }
        YAnimator {
            target: reveal.vertical ? reveal.panel : idle
            to: reveal.away
            duration: reveal.leaveMs
            easing.type: Easing.BezierSpline
            easing.bezierCurve: [0.3, 0.0, 0.8, 0.15, 1.0, 1.0]
        }
        XAnimator {
            target: reveal.vertical ? idle : reveal.content
            to: reveal.contentHome + reveal.drift / 2
            duration: reveal.leaveMs
            easing.type: Easing.InCubic
        }
        YAnimator {
            target: reveal.vertical ? reveal.content : idle
            to: reveal.contentHome + reveal.drift / 2
            duration: reveal.leaveMs
            easing.type: Easing.InCubic
        }
        OpacityAnimator {
            target: reveal.content
            to: 0
            duration: Math.round(reveal.leaveMs * 0.5)
            easing.type: Easing.OutQuad
        }
        onFinished: {
            reveal.settle();
            reveal.rested();
        }
    }

    // One fade per tier, held back by its place in the order. A sequence (a 0-to-0 hold,
    // then the fade) never wrote its value back here, so the hold is the first segment of
    // a two-segment curve, flat at 0, and the fade (an ease-out) is the second: one
    // Animator per tier. Created with this Item as parent, which gives it its window.
    property var fades: []
    function build() {
        for (const f of fades) f.destroy();
        fades = tiers.map((t, i) => fade.createObject(reveal, { tier: t, order: i }));
    }
    onTiersChanged: build()
    Component {
        id: fade

        OpacityAnimator {
            id: one
            property Item tier
            property int order
            readonly property int hold: order * reveal.step + Math.round(reveal.ms * 0.12)
            readonly property int fadeMs: Math.round(reveal.ms * 0.55)
            readonly property real f: hold / (hold + fadeMs)
            target: one.tier
            from: 0
            to: 1
            duration: hold + fadeMs
            easing.type: Easing.BezierSpline
            easing.bezierCurve: [f / 3, 0, 2 * f / 3, 0, f, 0,
                f + 0.33 * (1 - f), 1, f + 0.68 * (1 - f), 1, 1, 1]
        }
    }
}
