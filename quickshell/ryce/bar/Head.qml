import QtQuick
import qs as Ryce

// What a module is: its icon in the module's hue, or a word in fg2. In Tinta's terminal
// skin a short lowercase word, as a system monitor labels its columns; in Papel a book's
// abbreviation in small capitals («proc.», `page`), never a computer's icon.
BarText {
    property string glyph
    property string word
    property string page: word
    property color hue: Ryce.Palette.fg1
    property bool terminal: false
    property bool small: false
    readonly property bool worded: terminal || BarUi.folio

    text: BarUi.folio ? page : terminal ? word : glyph
    ink: worded ? "0" : glyph          // a word shares the readout's baseline
    color: worded ? Ryce.Palette.fg2 : hue
    font.family: worded ? BarUi.face : Ryce.Palette.fontIcon
    font.pixelSize: worded || small ? BarUi.textPx : BarUi.iconPx
    font.weight: worded ? BarUi.weight : Font.Normal
    font.features: BarUi.folio ? { "smcp": 1 } : ({})
    font.letterSpacing: BarUi.folio ? 0.6 : 0       // small capitals want air
}
