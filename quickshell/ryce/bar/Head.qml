import QtQuick
import qs as Ryce

// What a module is: its icon in the module's hue, or, in Tinta's terminal skin, a
// short lowercase word in fg2, as a system monitor labels its columns.
BarText {
    property string glyph
    property string word
    property color hue: Ryce.Palette.fg1
    property bool terminal: false
    property bool small: false

    text: terminal ? word : glyph
    ink: terminal ? "0" : glyph        // a word shares the readout's baseline
    color: terminal ? Ryce.Palette.fg2 : hue
    font.family: terminal ? BarUi.face : Ryce.Palette.fontIcon
    font.pixelSize: terminal ? BarUi.textPx : small ? BarUi.textPx : BarUi.iconPx
    font.weight: terminal ? BarUi.weight : Font.Normal
}
