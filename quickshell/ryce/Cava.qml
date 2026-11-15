import QtQuick
import Quickshell
import Quickshell.Io
import qs
import qs as Ryce

// Spectrum under the player. cava runs only while the sidebar is shown and something
// plays; no cava or silence leaves a calm 1 px baseline in `line`.
Item {
    id: root
    property bool active
    readonly property int bars: 32           // cava.conf [general] bars
    readonly property int gap: 3
    readonly property int barWidth: Math.floor((width - (bars - 1) * gap) / bars)
    property var levels: []

    implicitHeight: 36
    onActiveChanged: if (!active) { levels = []; parser.last = ""; }

    Process {
        // Missing cava is a normal state (optional package): exit quietly, keep the baseline.
        running: root.active
        command: ["sh", "-c", "command -v cava >/dev/null 2>&1 || exit 0; exec cava -p \"$1\"",
                  "sh", Quickshell.shellDir + "/cava.conf"]
        stdout: SplitParser {
            id: parser
            property string last: ""
            onRead: frame => {
                if (frame === last) return;   // identical frames: no repaint
                last = frame;
                root.levels = frame.split(";").slice(0, root.bars).map(Number);
            }
        }
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        height: parent.height
        spacing: root.gap

        Repeater {
            model: root.bars

            Rectangle {
                required property int index
                readonly property real level: Math.min(1, (root.levels[index] || 0) / 100)

                width: root.barWidth
                height: Math.max(1, Math.round(level * root.height))
                y: root.height - height
                radius: Math.min(1, Ryce.Palette.pillRadius)
                color: level > 0 ? Ryce.Palette.fg2 : Ryce.Palette.line
            }
        }
    }
}
