pragma Singleton

import QtQuick
import Quickshell
import qs as Ryce

// Sizes and the module skin of the bar, all derived from the height of the bar's zone
// (Palette.frameTop), so a taller theme scales the whole bar. Colours stay in Palette.
Singleton {
    // How a module sits on its plate. Origen: soft chips. Grafito: an instrument, bare
    // readouts between dot separators on three black plates. Ola: airy capsules. Tinta:
    // small smoked boxes drawn in a 1 px line. A theme not listed here gets chips.
    // Papel is a book's running head (`folio`): the chips' geometry, but square plates
    // ruled in a 1 px line, words in small capitals where the others show icons, every
    // figure in one ink and old-style, roman workspace numerals in italic and the clock in
    // its display italic. A flag, not a sixth skin: every drawer and key cap that reads
    // the skin (aria/, keys/) already draws chips the way a page wants them.
    readonly property string skin: ({ origen: "chip", grafito: "bare", ola: "capsule", tinta: "box", papel: "chip" })[Ryce.Palette.themeId] ?? "chip"
    readonly property bool folio: Ryce.Palette.themeId === "papel"
    // The figures a bar string sets (BarText): tabular ones for a value that changes, and
    // in Papel a book's old-style ones throughout, proportional: Literata has no tabular
    // old-style figures, and `tnum` on top of `onum` turns them back into lining ones.
    function figures(tabular) { return folio ? { "onum": 1 } : tabular ? { "tnum": 1 } : ({}); }
    // Between a figure and its unit: a book's narrow no-break space in Papel («7 %»; Literata
    // has none, so it comes from the fallback face, 2.7 px at 14), a plain space elsewhere.
    // The bar's other themes set a percent tight («7%»).
    readonly property string unit: folio ? "\u202f" : " "
    // Grey themes keep app and tray icons grey too. Read from the static catalog, not the
    // live colours, which cross-fade for a while after a switch.
    readonly property bool mono: {
        const h = Ryce.Palette.catalog[Ryce.Palette.themeId]?.hues;
        return !!h && h.cpu === h.mem && h.mem === h.net && h.net === h.vol;
    }
    // A dot-matrix display face (Grafito's Doto) sets every word on the bar, the clock's
    // smaller siblings in its heaviest cut: the Black dots at 18 px are as big as the
    // clock's Bold ones at 26, and lighter cuts fall apart into specks. Icons stay icons.
    readonly property bool dots: Ryce.Palette.fontDisplayMinPx > 0
    readonly property string face: dots ? Ryce.Palette.fontDisplay : Ryce.Palette.fontUi
    readonly property int weight: dots ? Font.Black : Font.Normal

    readonly property int band: Ryce.Palette.frameTop
    readonly property int textPx: dots ? 18 : Math.round(band * 0.3)     // 46 -> 14, 52 -> 16
    readonly property int smallPx: Math.round(band * 0.23)      // the date under a stacked clock
    readonly property int iconPx: Math.round(band * 0.38)       // 46 -> 17, 52 -> 20
    readonly property int chipHeight: Math.round(band * (skin === "box" ? 0.6 : 0.66))
    readonly property int peonzaPx: chipHeight - 6               // on its own plate
    readonly property int radius: folio ? 0 : Math.min(Ryce.Palette.pillRadius, chipHeight / 2)
    readonly property int padX: skin === "bare" ? 6 : skin === "capsule" ? 14 : 10
    readonly property int gap: skin === "capsule" ? 10 : skin === "bare" ? 12 : 6     // between modules
    readonly property int inner: 7                                                    // glyph to text
    readonly property int inset: 3              // a plate's rim around what rides on it (the workspace pill)
    readonly property int groupPad: 6           // Grafito's group plates past their first and last readout

    // The plates float: their top sits as far below the screen's edge as their bottom
    // sits above the tiled windows (which start gaps_out under the zone), so the bar's
    // centre line drops `lift` px below the zone's. The outer plates line up with the
    // windows' sides. `lift` may be fractional: it lands an odd plate's top on a pixel.
    readonly property int plateTop: Math.round((band + Ryce.Palette.gapsOut - chipHeight) / 2)
    readonly property real lift: plateTop - (band - chipHeight) / 2
    readonly property int edge: Ryce.Palette.gapsOut
    readonly property color plate: Ryce.Palette.rgba(Ryce.Palette.bg0, Ryce.Palette.alphaBar)
}
