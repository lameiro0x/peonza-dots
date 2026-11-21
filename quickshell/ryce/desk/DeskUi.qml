pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import qs as Ryce
import qs.bar

// The desk cards' ground and inks. Every theme's card is solid, the bar's plate grown to a
// widget: bg0 in a dark theme, the darker paper (bg2) in a light one, where a bg0 card would
// vanish into the page. Tinta alone is glass, the black of its terminals at their alpha
// (alpha.term) over the same smoked blur Hyprland draws behind them (rules.lua, the qs-desk
// layer rule), never under the floor below. A hairline in `line`, faint, edges every card
// of a light theme and Tinta's boxes and Grafito's plates.
// Text never meets the wallpaper, only the card over it: each ink below is the theme's
// own, nudged toward fg0 just enough to keep 4.5:1 against that card over the worst pixel
// the theme's pictures hold: white at the light end (Grafito's peak 0.6), darkened by the
// blur's brightness while Hyprland draws it, and `darkest` at the dark end.
// The blur that counts is the one Hyprland draws, not the theme's word for it: a
// palette.lua that failed to load leaves look.lua's blur off, and a `hyprctl keyword`
// changes it at runtime. So it is asked of Hyprland, at start and on every config reload
// (0.57 answers {"bool": true} and {"float": 0.4}); until it answers, Tinta's glass holds
// the floor on the sharp picture.
Singleton {
    id: ui
    readonly property real floor: 4.5               // WCAG AA, body text
    readonly property bool light: Ryce.Palette.light
    // Which of the theme's pictures shows (wallpapers.json, written by ryce-theme wall and
    // the picker): Tinta's main photo holds white, but its three sheets (alternates 1-3,
    // theme/wallpaper/ink.py) keep every drawing 20 px or more off the cards (crowded()), so
    // under a card there is only the sheet's ground and grid, at most a 0.25 grey.
    readonly property string picksFile: (Quickshell.env("RYCE_THEME_STATE") || (Quickshell.env("HOME") + "/.local/state/ryce/theme")) + "/wallpapers.json"
    property var picks: ({})
    readonly property int pick: picks[Ryce.Palette.themeId] ?? 0
    // A sheet is any picture ink.py draws: the alternates here, the main one in the public
    // export (peonza-dots ships Tinta on its parts-list sheet).
    readonly property bool sheet: glass && (pick >= 1 || Ryce.Palette.wallpaperSource.indexOf("/tinta-") >= 0)
    readonly property real peak: sheet ? 0.25 : (({ grafito: 0.6 })[Ryce.Palette.themeId] ?? 1)
    property bool blurOn: false
    property real blurBrightness: 1
    // The blur darkens only where the theme blurs its desk (blur.desk; Tinta's glass stands
    // on the sharp picture, so the sheet shows through the black).
    readonly property real brightest: peak * (blurOn && Ryce.Palette.blurDesk ? blurBrightness : 1)
    readonly property real darkest: 0
    readonly property color fill: light ? Ryce.Palette.bg2 : Ryce.Palette.bg0
    readonly property bool glass: Ryce.Palette.themeId === "tinta"
    // Papel's cards are folios: the baize-dark ground edged in one rule, the text set as a
    // book sets it (DeskClock, StatRow, HitoCard), every figure in the card's one ink.
    readonly property bool folio: BarUi.folio
    readonly property string unit: BarUi.unit       // between a figure and its unit («7 %»)
    // Tinta's glass: on a sheet, 0.45 black over the sharp grid (the sheet reads through, the
    // text stays far above 4.5:1); on the photo, the terminal's alpha or the floor over white.
    readonly property real alpha: glass ? (sheet ? Math.max(0.45, seeThrough()) : Math.max(Ryce.Palette.alphaTerm, seeThrough())) : 1
    readonly property color ground: Ryce.Palette.rgba(fill, alpha)
    readonly property bool outlined: light || folio || BarUi.skin === "box" || BarUi.skin === "bare"
    // Faint: it only has to say where a card ends, not frame it. A folio's rule is the
    // page's border: the line itself.
    readonly property color hairline: Ryce.Palette.rgba(Ryce.Palette.line, folio ? 1 : 0.4)
    // A dark theme's own shadow; on paper a bg0 shadow is a cream glow, so it is fg0. Not
    // under glass: the RectangularShadow fills the whole card too, and stacked under a 0.62
    // ground it made Tinta's glass a 0.8 slab (measured on the stage: the sheet showed at 18 %).
    readonly property color shadow: glass ? "transparent"
        : light ? Ryce.Palette.rgba(Ryce.Palette.fg0, 0.14) : Ryce.Palette.rgba(Ryce.Palette.bg0, 0.45)
    readonly property int radius: Ryce.Palette.rounding
    readonly property int pad: 22                   // card edge to its text
    readonly property int gap: 20                   // between two cards

    readonly property color ink: legible(Ryce.Palette.fg0)
    readonly property color soft: legible(Ryce.Palette.fg1)
    readonly property color dim: legible(Ryce.Palette.fg2)

    // One getoption per key; a missing or garbled answer leaves the card at the floor
    // without blur.
    function readBlur() {
        if (!Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE")) return;
        enabledQuery.running = true;
        brightnessQuery.running = true;
    }
    function parsed(text, key) {
        try { return JSON.parse(text)[key]; } catch (e) { return undefined; }
    }
    Component.onCompleted: readBlur()

    FileView {
        path: ui.picksFile
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            try {
                const m = JSON.parse(text());
                ui.picks = m && typeof m === "object" ? m : {};
            } catch (e) {
                ui.picks = {};
            }
        }
        onLoadFailed: ui.picks = {}
    }

    Process {
        id: enabledQuery
        command: ["hyprctl", "-j", "getoption", "decoration:blur:enabled"]
        stdout: StdioCollector {
            onStreamFinished: {
                const v = ui.parsed(text, "bool") ?? ui.parsed(text, "int");
                ui.blurOn = v === true || v === 1;
            }
        }
    }
    Process {
        id: brightnessQuery
        command: ["hyprctl", "-j", "getoption", "decoration:blur:brightness"]
        stdout: StdioCollector {
            onStreamFinished: {
                const b = ui.parsed(text, "float");
                ui.blurBrightness = typeof b === "number" && b > 0 && b <= 1 ? b : 1;
            }
        }
    }
    Connections {
        target: Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE") ? Hyprland : null
        function onRawEvent(event) {
            if (event.name === "configreloaded") ui.readBlur();
        }
    }

    function mix(a, b, t) { return Qt.rgba(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, 1); }
    function lum(c) {
        const f = v => v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
    }
    function ratio(a, b) {
        const x = lum(a), y = lum(b);
        return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
    }
    // The card at alpha `a` composited over a wallpaper pixel of grey `base` (sRGB, like
    // Qt and the compositor).
    function over(a, base) {
        return Qt.rgba(a * fill.r + (1 - a) * base, a * fill.g + (1 - a) * base, a * fill.b + (1 - a) * base, 1);
    }
    // How many twentieths of the way to fg0 `c` must go to pass on both worst cards at
    // alpha `a`; 21 when not even fg0 does.
    function steps(c, a) {
        const worst = [over(a, brightest), over(a, darkest)], to = Ryce.Palette.fg0;
        for (let i = 0; i <= 20; i++) {
            const m = mix(c, to, i / 20);
            if (Math.min(ratio(m, worst[0]), ratio(m, worst[1])) >= floor) return i;
        }
        return 21;
    }
    // A right-hand card's layer margin on a screen `width` wide, for a window with `pad`
    // around its card. Tinta's right column ends where the sheet's title block does (its
    // right edge at x 1895 of 1920, theme/wallpaper/ink.py TB), scaled like the sheet;
    // every other theme keeps the desk's 52.
    function rightMargin(width, pad) {
        return Ryce.Palette.themeId === "tinta" ? width - Math.round(width * 1896 / 1920) - pad : 52;
    }
    // The most see-through ground, in hundredths, that keeps fg0 as it is and fg1 within
    // half its way to fg0: past that, soft and dim lines would all turn into fg0. Not
    // under 0.25: the blur rule ignores pixels under 0.2 alpha, and the card's antialiased
    // edge would lose it.
    function seeThrough() {
        for (let i = 25; i < 100; i++)
            if (steps(Ryce.Palette.fg0, i / 100) === 0 && steps(Ryce.Palette.fg1, i / 100) <= 10) return i / 100;
        return 1;
    }
    // `c` itself when it passes on both worst cards, else the first step toward fg0 that
    // does (fg0 if even that fails).
    function legible(c) {
        return mix(c, Ryce.Palette.fg0, Math.min(steps(c, alpha), 20) / 20);
    }
}
