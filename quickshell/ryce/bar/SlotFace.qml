import QtQuick
import qs as Ryce

// The inside of a workspace slot: key numeral, then the project label (an AI session
// there) or the icons of its apps, then the waiting dot. Same weights on and off the
// pill, so nothing reflows when it passes. `onPill` swaps every colour for the
// pill's ink; Slot.qml draws one of each and clips the second to the pill. An app the
// icon theme does not know shows agentd's glyph for the workspace instead.
// Papel shows no app at all: an occupied page's numeral is in fg0, an empty one's in fg2.
Item {
    id: face
    required property var info
    required property var metrics
    property bool onPill: false
    property bool waiting: false
    property real breath: 1
    readonly property bool project: info.kind === "project"
    width: info.full

    BarText {
        x: face.metrics.padX
        width: face.metrics.numeralWidth
        horizontalAlignment: Text.AlignHCenter
        text: face.info.key
        tabular: true
        color: face.onPill ? Ryce.Palette.inkOnPill : !face.info.occupied ? Ryce.Palette.fg2 : BarUi.folio ? Ryce.Palette.fg0 : Ryce.Palette.fg1
        font.pixelSize: face.metrics.textPx
        font.italic: BarUi.folio        // Papel's roman numerals (Workspaces.numeral)
    }
    // Delegates follow the count, not the array, so a recomputed model rebinds the
    // sources in place instead of recreating every icon.
    Repeater {
        model: face.info.kind === "app" && !BarUi.folio ? Math.max(1, face.info.icons.length) : 0

        Item {
            id: app
            required property int index
            readonly property string source: face.info.icons[index] ?? ""
            x: face.metrics.contentX + index * (face.metrics.glyphWidth + face.metrics.iconGap)
            width: face.metrics.glyphWidth
            height: face.height

            AppIcon {
                visible: app.source !== ""
                anchors.centerIn: parent
                source: app.source
            }
            BarText {
                visible: app.source === ""
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: face.metrics.glyphs[face.info.icon] ?? face.metrics.glyphs.window
                ink: text
                color: face.onPill ? Ryce.Palette.dimOnPill : Ryce.Palette.fg2
                font.family: Ryce.Palette.fontIcon
                font.weight: Font.Normal
                font.pixelSize: face.metrics.glyphWidth - 2
            }
        }
    }
    BarText {
        visible: face.project
        x: face.metrics.contentX
        width: face.info.labelWidth
        text: face.info.label
        elide: Text.ElideRight
        color: face.info.state === "idle"
            ? (face.onPill ? Ryce.Palette.dimOnPill : Ryce.Palette.fg2)
            : (face.onPill ? Ryce.Palette.inkOnPill : Ryce.Palette.fg0)
        font.pixelSize: face.metrics.textPx
    }
    Rectangle {
        visible: face.waiting
        x: face.metrics.contentX + face.info.labelWidth + face.metrics.dotGap
        anchors.verticalCenter: parent.verticalCenter
        width: face.metrics.dot
        height: width
        radius: width / 2
        color: face.onPill ? Ryce.Palette.signalOnPill : Ryce.Palette.signal
        opacity: face.breath
    }
}
