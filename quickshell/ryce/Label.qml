import QtQuick
import qs as Ryce

// Every visible string goes through here. Plain text only: roster strings come from
// Claude transcripts and must never be parsed as markup. The theme's UI face by
// default, rendered like the bar's text so both read as one surface.
Text {
    textFormat: Text.PlainText
    color: Ryce.Palette.fg1
    font.family: Ryce.Palette.fontUi
    font.pixelSize: Ryce.Ui.body
    elide: Text.ElideRight
}
