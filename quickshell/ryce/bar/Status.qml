import QtQuick
import Quickshell.Services.Pipewire
import qs as Ryce
import qs.agents

// The right end of the bar: what plays, the tray, AI sessions (who waits, else how
// many work), keyboard layout, volume, clock. Quiet by default; only a waiting
// session takes the signal colour. `room` is the width the bar leaves between the
// workspaces and the edge; the playing title takes what the rest does not.
Row {
    id: status
    property real room: 600
    property bool hyprland: false
    property bool calendarOpen: false
    signal agentsClicked()
    signal clockClicked()

    readonly property int waiting: Roster.counts.waiting
    readonly property int busy: Roster.counts.busy

    readonly property PwNode sink: Pipewire.defaultAudioSink
    readonly property bool hasSink: sink !== null && sink.audio !== null
    readonly property bool muted: hasSink && sink.audio.muted
    readonly property int volume: hasSink ? Math.round(sink.audio.volume * 100) : 0

    PwObjectTracker { objects: [status.sink] }

    Media {
        id: media
        maxText: Math.min(260, status.room - media.chrome
            - tray.target - agents.target - keyboard.target - volume.target - clock.target)
    }
    Tray {
        id: tray
    }
    Module {
        id: agents
        shown: status.waiting > 0 || status.busy > 0
        interactive: true
        spacing: 8
        Accessible.role: Accessible.Button
        Accessible.name: count.text
        onClicked: status.agentsClicked()

        Item {
            visible: status.waiting > 0
            width: 6
            height: parent.height

            Rectangle {
                anchors.centerIn: parent
                width: 6
                height: 6
                radius: 3
                color: Ryce.Palette.signal
            }
        }
        BarText {
            id: count
            text: status.waiting > 0
                ? status.waiting + " " + (status.waiting === 1 ? Ryce.Words.state.waiting : "te esperan")
                : status.busy + " " + Ryce.Words.state.busy
            color: status.waiting > 0 ? Ryce.Palette.fg0 : Ryce.Palette.fg1
        }
    }
    Keyboard {
        id: keyboard
        hyprland: status.hyprland
    }
    // Click mutes; the wheel moves 5 % per notch, touchpad deltas adding up first.
    Module {
        id: volume
        shown: status.hasSink
        interactive: true
        Accessible.role: Accessible.Slider
        Accessible.name: status.muted ? "Volumen silenciado" : "Volumen " + status.volume + " %"
        property int acc: 0
        onClicked: if (status.hasSink) status.sink.audio.muted = !status.sink.audio.muted
        onWheeled: wheel => {
            acc += wheel.angleDelta.y;
            const steps = Math.trunc(acc / 120);
            if (steps === 0 || !status.hasSink) return;
            acc -= steps * 120;
            status.sink.audio.volume = Math.max(0, Math.min(1, status.sink.audio.volume + steps * 0.05));
        }

        Head {
            glyph: status.muted || status.volume === 0 ? Ryce.Ui.volOff : status.volume < 34 ? Ryce.Ui.volLow : status.volume < 67 ? Ryce.Ui.volMid : Ryce.Ui.volHigh
            word: "vol"
            page: "vol."
            hue: status.muted ? Ryce.Palette.fg2 : Ryce.Palette.hueVol
            terminal: BarUi.skin === "box"
        }
        BarText {
            text: String(status.volume)
            reserve: "00"
            color: status.muted ? Ryce.Palette.fg2 : Ryce.Palette.fg0
        }
    }
    BarClock {
        id: clock
        open: status.calendarOpen
        onClicked: status.clockClicked()
    }
}
