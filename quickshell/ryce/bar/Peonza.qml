import QtQuick
import qs as Ryce

// The peonza where the distro logo used to be. It turns in bursts: one turn every 10 s
// while no AI session works, one every 6 s while one is busy, and while one waits for
// you a nod in the theme's signal colour every 4 s. The sprites are horizontal strips of
// 64 px frames in the theme's own directory (contracts/constants.json peonza_assets); a
// Timer steps a clipped strip and sleeps through the rest, so between bursts nothing
// repaints. Missing sprites fall back to still.png, then to the glyph.
// `flick()` (a click on it) plays a burst now (a turn, or a nod while a session waits);
// one under way gets one more after it, so no click is lost. A burst ends on frame 0,
// where it rests, and the rest starts over: a click resets the idle countdown.
Item {
    id: peonza
    property string mode: "idle"     // "idle" | "busy" | "waiting"
    property int size: 22
    property bool again: false       // a click landed mid-burst: one more burst after this one
    readonly property int frames: mode === "waiting" ? 16 : 24
    readonly property int rest: mode === "waiting" ? 4000 : mode === "busy" ? 6000 : 10000
    readonly property string dir: "file://" + Ryce.Palette.themeDir + "/peonza/"
    readonly property bool animating: strip.status === Image.Ready
    property int frame: 0

    implicitWidth: size
    implicitHeight: size
    // A session that starts working or waiting shows it at once; back to idle, it rests.
    onModeChanged: {
        again = false;
        frame = mode === "idle" ? 0 : 1;
    }
    function flick() {
        if (frame === 0) frame = 1;
        else again = true;
    }

    Image {
        id: still
        anchors.fill: parent
        visible: !peonza.animating && status === Image.Ready
        source: peonza.dir + "still.png"
        sourceSize.height: 64
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
    }
    Item {
        anchors.fill: parent
        clip: true
        visible: peonza.animating

        Image {
            id: strip
            source: peonza.dir + (peonza.mode === "waiting" ? "wobble.png" : "spin.png")
            x: -peonza.frame * peonza.size
            width: peonza.frames * peonza.size
            height: peonza.size
            sourceSize.height: 64
            smooth: true
            mipmap: true
        }
    }
    Text {
        anchors.centerIn: parent
        visible: !peonza.animating && still.status !== Image.Ready
        textFormat: Text.PlainText
        text: String.fromCodePoint(0x100000)     // Ryce Peonza, the 20 px cut
        font.family: "Ryce Peonza"
        font.pixelSize: peonza.size
        color: peonza.mode === "waiting" ? Ryce.Palette.signal : peonza.mode === "busy" ? Ryce.Palette.fg0 : Ryce.Palette.fg1
        Behavior on color { ColorAnimation { duration: Ryce.Palette.motionMs } }
    }

    // A turn in 1.2 s (a nod in 1.1 s), then the rest on frame 0. Bursts, not a loop: with
    // sessions busy all day a continuous 20 fps spin kept the bar and the compositor
    // repainting (measured live 2026-11-09: compositor+shell CPU 1.7 % -> 6.6 % of a core,
    // GPU asleep 84 % -> 61 %). A change of interval restarts the Timer, so a click in the
    // rest starts the burst at once.
    Timer {
        running: peonza.animating
        repeat: true
        interval: peonza.frame === 0 ? peonza.rest : (peonza.mode === "waiting" ? 70 : 50)
        onTriggered: {
            peonza.frame = (peonza.frame + 1) % peonza.frames;
            if (peonza.frame === 0 && peonza.again) {
                peonza.again = false;
                peonza.frame = 1;
            }
        }
    }
}
