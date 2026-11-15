import QtQuick
import Quickshell

// RYCE_PERF_PROBE=1 (unset: nothing runs): one log line per drawer open or close, so a
// change to its motion is judged by numbers, not by eye.
//   first   ms from the toggle to the window's first synced frame (window creation
//           included when the open builds one)
//   frames  GUI-thread ticks while `busy`; worst is the longest after the first, slow
//           counts those over 1.5 refresh periods (RYCE_PERF_HZ, default 60). Motion run
//           by Animators does not wait for these ticks: then they show GUI stalls only.
// The render thread's own frames: --log-rules "qt.scenegraph.time.renderloop=true".
Item {
    id: probe
    property string name
    property bool busy                      // the open or close is in flight
    property bool opening
    property real since                     // Date.now() of the toggle
    readonly property bool on: Quickshell.env("RYCE_PERF_PROBE") === "1"
    readonly property real budget: 1.5 / (Number(Quickshell.env("RYCE_PERF_HZ")) || 60)
    property bool awaiting: on
    property real first: -1

    onSinceChanged: if (on) { first = -1; awaiting = true; }

    Connections {
        target: probe.awaiting ? probe.Window.window : null
        function onAfterAnimating() {
            probe.first = Date.now() - probe.since;
            probe.awaiting = false;
        }
    }

    FrameAnimation {
        property int n
        property int slow
        property real worst
        property real t0

        running: probe.on && probe.busy
        onRunningChanged: {
            if (running) {
                n = 0;
                slow = 0;
                worst = 0;
                t0 = Date.now();
                return;
            }
            console.info(`ryce perf ${probe.name} ${probe.opening ? "open" : "close"}: first=${probe.first}ms frames=${n}`
                + ` worst=${(worst * 1000).toFixed(1)}ms slow=${slow} wall=${Date.now() - t0}ms`);
        }
        onTriggered: {
            // The first tick measures from before the run: `first` covers it.
            if (++n === 1) return;
            worst = Math.max(worst, frameTime);
            if (frameTime > probe.budget) slow++;
        }
    }
}
