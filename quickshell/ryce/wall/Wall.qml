import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs as Ryce

// The live-wallpaper experiment: the theme's own static wallpaper through a calm
// per-theme shader (Origen film grain and a slow breathing of the key light; Grafito a
// wave travelling through the dot sizes; the photo themes borrow Origen's grain). Full screen, no input, on
// the Background layer over the static wallpaper (awww maps first, at login): a layer
// stacks by creation, and this loads later than the desk widgets, so on Bottom it would
// cover them. Its owner loads it only while it is wanted and seen, so unloaded it costs
// nothing and the static wallpaper shows through.
// It paints the picture `ryce-theme wall` chose for the theme (wallpapers.json in the
// theme state: {theme: n}, none = the main picture, n = wallpaper/alt-n/).
// Without the theme's wallpaper file it maps nothing.
PanelWindow {
    id: wall
    readonly property int fps: 24
    // Seconds on a 1000 s cycle: every shader's motion has a period that divides 1000,
    // so the wrap is seamless and float precision stays fine.
    property real time: (Date.now() / 1000) % 1000

    visible: base.status === Image.Ready
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    mask: Region {}

    WlrLayershell.namespace: "qs-wall"
    WlrLayershell.layer: WlrLayer.Background
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    // Which of the theme's pictures is on: 0 the main one, n its alt-n. A binding, so a
    // theme switch picks that theme's remembered picture without a file change.
    property var picks: ({})
    readonly property int choice: {
        const n = picks[Ryce.Palette.themeId];
        return Number.isInteger(n) && n > 0 && !(missing[Ryce.Palette.themeId] === n) ? n : 0;
    }
    // A remembered alternate whose files are gone (stale or hand-edited wallpapers.json)
    // falls back to the main picture, as `ryce-theme wallpaper` does.
    property var missing: ({})
    FileView {
        // Palette.stateDir, spelled from the environment (qmlcheck: paths from env/literals).
        path: (Quickshell.env("RYCE_THEME_STATE") || (Quickshell.env("HOME") + "/.local/state/ryce/theme")) + "/wallpapers.json"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            try {
                const m = JSON.parse(text());
                wall.picks = m && typeof m === "object" ? m : {};
            } catch (e) {
                wall.picks = {};
            }
        }
        onLoadFailed: wall.picks = {}
    }

    Timer {
        running: wall.visible
        interval: Math.round(1000 / wall.fps)
        repeat: true
        onTriggered: wall.time = (Date.now() / 1000) % 1000
    }

    Image {
        id: base
        visible: false
        // Sized from the screen, not the window: the window maps only once this is ready.
        source: Ryce.Palette.themeDir + "/wallpaper/" + (wall.choice > 0 ? "alt-" + wall.choice + "/" : "")
                + (wall.screen.height > 1080 ? "2560x1440" : "1920x1080") + ".jpg"
        sourceSize: Qt.size(wall.screen.width, wall.screen.height)
        asynchronous: true
        cache: false
        onStatusChanged: if (status === Image.Error && wall.choice > 0) {
            const m = Object.assign({}, wall.missing);
            m[Ryce.Palette.themeId] = wall.choice;
            wall.missing = m;
        }
    }

    ShaderEffect {
        id: fx
        anchors.fill: parent
        property var source: base
        property real time: wall.time
        property point resolution: Qt.point(width, height)
        property color fog: Ryce.Palette.fg2
        // Only Origen (grain, breathing light) and Grafito (a wave through the dots) have
        // their own; the others borrow Origen's grain, Papel (the light theme) as Ola does.
        fragmentShader: Qt.resolvedUrl((({ grafito: "grafito", ola: "origen", papel: "origen" })[Ryce.Palette.themeId] ?? "origen") + ".frag.qsb")
        // Fade in over the static wallpaper, so loading never jumps.
        opacity: base.status === Image.Ready ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Ryce.Palette.motionMs * 2 } }
    }
}
