import QtQuick
import QtQuick.Layouts
import qs
import qs as Ryce

// A section title: a small lowercase word, a hairline that runs to the edge, and an
// optional note at its end. The only divider the drawers use; no boxes.
RowLayout {
    id: rule
    property string label
    property string meta
    property color metaColor: Ryce.Palette.fg1
    property real metaMax: Number.POSITIVE_INFINITY     // a longer note elides

    spacing: 10

    Label {
        text: rule.label
        color: Ryce.Palette.fg2
        font.pixelSize: Ui.meta
        font.letterSpacing: 0.4
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignVCenter
        implicitHeight: 1
        color: Ryce.Palette.line
    }
    Label {
        visible: rule.meta !== ""
        Layout.maximumWidth: rule.metaMax
        text: rule.meta
        color: rule.metaColor
        font.pixelSize: Ui.meta
    }
}
