import QtQuick
import qs

// The sheet's small print: Martian Mono in capitals, tracked out.
Text {
    property int px: 11

    color: Look.fg2
    font.family: Look.fontLabel
    font.pixelSize: px
    font.letterSpacing: Look.track(px)
    font.capitalization: Font.AllUppercase
    textFormat: Text.PlainText
}
