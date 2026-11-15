import QtQuick
import Quickshell
import Quickshell.Io
import qs as Ryce

// The left-edge visualiser: one dotted line per spectrum band, growing from the screen
// edge, low frequencies at the top. Its own cava (edgeviz.conf) runs only while `active`
// (a player plays and the desk is seen); a level of N is N dots, so a frame only moves
// widths. Each line is one tiled image of a single dot, not a row of items.
Item {
    id: viz
    property bool active
    readonly property int bars: 72          // edgeviz.conf [general] bars
    readonly property int maxDots: 72       // edgeviz.conf ascii_max_range
    readonly property int pitch: 4          // one dot and its gap, along a line
    readonly property int row: 7            // one line and its gap
    property var levels: []
    // One 2 px dot in its 4 px cell, in the theme's ink (# escaped for the URL). The ink
    // comes from the static catalog, not the cross-fading fg0: a theme switch decodes
    // the dot once instead of on every frame of the fade.
    readonly property string ink: Ryce.Palette.catalog[Ryce.Palette.themeId]?.colors.fg0 ?? Ryce.Palette.fg0
    readonly property string dot: "data:image/svg+xml;utf8," + encodeURIComponent(
        `<svg xmlns="http://www.w3.org/2000/svg" width="${pitch}" height="2"><rect width="2" height="2" fill="${ink}"/></svg>`)

    implicitWidth: maxDots * pitch
    implicitHeight: bars * row
    onActiveChanged: if (!active) { levels = []; parser.last = ""; }

    Process {
        // Missing cava is a normal state (optional package): exit quietly, draw nothing.
        running: viz.active
        command: ["sh", "-c", "command -v cava >/dev/null 2>&1 || exit 0; exec cava -p \"$1\"",
                  "sh", Quickshell.shellDir + "/desk/edgeviz.conf"]
        stdout: SplitParser {
            id: parser
            property string last: ""
            onRead: frame => {
                if (frame === last) return;   // identical frames: no repaint
                last = frame;
                viz.levels = frame.split(";").slice(0, viz.bars).map(Number);
            }
        }
    }

    Repeater {
        model: viz.bars

        Image {
            required property int index
            y: index * viz.row
            width: Math.min(viz.maxDots, Math.max(0, viz.levels[index] || 0)) * viz.pitch
            height: 2
            source: viz.dot
            fillMode: Image.Tile
            horizontalAlignment: Image.AlignLeft
            verticalAlignment: Image.AlignTop
            smooth: false
            opacity: 0.85
        }
    }
}
