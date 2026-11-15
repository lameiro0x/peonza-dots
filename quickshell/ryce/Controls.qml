import QtQuick
import QtQuick.Layouts
import Quickshell.Io
import Quickshell.Services.Pipewire
import qs
import qs as Ryce

// Quick toggles (mako do-not-disturb, hyprsunset night light) and the output volume.
// Nothing here polls: the toggles are asked once each time the drawer opens.
ColumnLayout {
    id: root
    property bool active
    readonly property int nightKelvin: 4500

    // mako: known once `makoctl mode` answered (mako running).
    property bool dnd: false
    property bool dndKnown: false
    // hyprsunset: whatever its IPC socket last answered; not running = off. A click asks
    // for the opposite of what is shown, then asks again once hyprsunset has settled.
    property bool night: false
    property bool nightBusy: nightSet.running || nightSettle.running
    property int nightRetries: 0       // a fresh daemon may not answer the first ask

    readonly property PwNode sink: Pipewire.defaultAudioSink
    readonly property bool hasSink: sink !== null && sink.audio !== null
    readonly property real volume: hasSink ? sink.audio.volume : 0
    readonly property bool muted: hasSink && sink.audio.muted

    function setVolume(v) {
        if (hasSink) sink.audio.volume = Math.max(0, Math.min(1, v));
    }
    function refresh() {
        dndQuery.running = true;
        nightQuery.running = true;
    }

    spacing: 12
    onActiveChanged: if (active) refresh()

    PwObjectTracker { objects: [root.sink] }

    Process {
        id: dndQuery
        command: ["sh", "-c", "exec makoctl mode 2>/dev/null"]
        stdout: StdioCollector {
            onStreamFinished: {
                const modes = text.trim().split("\n");
                root.dndKnown = text.trim() !== "";
                root.dnd = modes.includes("do-not-disturb");
            }
        }
    }
    Process {
        id: dndToggle
        command: ["sh", "-c", "exec makoctl mode -t do-not-disturb >/dev/null 2>&1"]
        onExited: dndQuery.running = true
    }
    Process {
        id: nightQuery
        command: ["sh", "-c", "hyprctl hyprsunset identity get 2>/dev/null; hyprctl hyprsunset temperature 2>/dev/null"]
        stdout: StdioCollector {
            onStreamFinished: {
                const [identity, kelvin] = text.trim().split("\n");
                if (identity !== "true" && identity !== "false" && root.nightRetries > 0) {
                    root.nightRetries--;
                    nightSettle.restart();
                    return;
                }
                root.night = identity === "false" && Number(kelvin) < 6000;
            }
        }
    }
    // IPC first; only with no daemon answering is one started (or the stray one killed).
    // A second hyprsunset beside a live one exits at once (the CTM manager is taken), and
    // the click is ignored while one is in flight, so instances never stack.
    Process {
        id: nightSet
        onExited: nightSettle.restart()
    }
    // A fresh hyprsunset needs a Wayland roundtrip before its socket exists.
    Timer {
        id: nightSettle
        interval: 600
        onTriggered: nightQuery.running = true
    }
    function toggleNight() {
        if (nightBusy) return;
        nightSet.command = root.night
            ? ["sh", "-c", "hyprctl hyprsunset identity >/dev/null 2>&1 || pkill -x hyprsunset; exit 0"]
            : ["sh", "-c", "hyprctl hyprsunset temperature \"$1\" >/dev/null 2>&1 && exit 0; pkill -x hyprsunset && sleep 0.3; exec setsid -f hyprsunset -t \"$1\" </dev/null >/dev/null 2>&1",
               "sh", String(root.nightKelvin)];
        nightRetries = root.night ? 0 : 1;
        root.night = !root.night;
        nightSet.running = true;
    }

    // The quick toggles and the headset: one group of pills, one gap.
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Pill {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                glyph: Ui.bellOff
                label: "No molestar"
                on: root.dnd
                available: root.dndKnown
                onClicked: {
                    root.dnd = !root.dnd;
                    dndToggle.running = true;
                }
            }
            Pill {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                glyph: Ui.night
                label: "Luz nocturna"
                on: root.night
                onClicked: root.toggleNight()
            }
        }

        // The headset (Headset.qml), as a row that names it: the press says what it acts
        // on. Connected: its battery on the right; while a press is on its way, or failed,
        // the state. A click connects or disconnects (SUPER+b only connects, or reconnects).
        // Hidden on a machine with no Bluetooth at all.
        Pill {
            readonly property bool saying: Headset.busy || Headset.failed || Headset.device === null || Headset.blocked
            readonly property bool charge: Headset.connected && !saying && Headset.batteryLevel >= 0

            Layout.fillWidth: true
            visible: Headset.present
            row: true
            glyph: Ui.headphones
            label: Headset.device === null ? "Cascos" : Headset.name
            meta: saying ? Headset.word : charge ? Headset.batteryLevel + " %" : ""
            metaGlyph: charge ? Ui.battery(Headset.batteryLevel) : ""
            metaSpoken: charge ? "batería " + meta : meta
            metaColor: Headset.failed ? Ryce.Palette.warn : Headset.connected ? Ryce.Palette.dimOnPill : Ryce.Palette.fg2
            on: Headset.connected
            busy: Headset.busy
            available: Headset.device !== null && !Headset.blocked
            onClicked: Headset.toggle(false)
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10

        IconButton {
            size: 28
            enabled: root.hasSink
            glyph: !root.hasSink || root.muted || root.volume === 0 ? Ui.volOff
                : root.volume < 0.34 ? Ui.volLow : root.volume < 0.67 ? Ui.volMid : Ui.volHigh
            Accessible.name: root.muted ? "Activar sonido" : "Silenciar"
            onClicked: root.sink.audio.muted = !root.muted
        }

        // The track is a hairline in `line`; the level in fg0 (fg2 when muted). The knob
        // shows only under the pointer.
        Item {
            Layout.fillWidth: true
            implicitHeight: 28
            visible: root.hasSink
            Accessible.role: Accessible.Slider
            Accessible.name: "Volumen"

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width
                height: 2
                radius: 1
                color: Ryce.Palette.line
            }
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width * Math.min(1, root.volume)
                height: 2
                radius: 1
                color: root.muted ? Ryce.Palette.fg2 : Ryce.Palette.fg0
            }
            Rectangle {
                x: parent.width * Math.min(1, root.volume) - width / 2
                anchors.verticalCenter: parent.verticalCenter
                width: 10
                height: 10
                radius: Math.min(Ryce.Palette.pillRadius, 5)
                color: root.muted ? Ryce.Palette.fg2 : Ryce.Palette.pill
                opacity: slider.containsMouse || slider.pressed ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }
            }
            MouseArea {
                id: slider
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                property int acc: 0
                onPressed: mouse => root.setVolume(mouse.x / width)
                onPositionChanged: mouse => { if (pressed) root.setVolume(mouse.x / width); }
                // 5 % per notch; touchpad deltas add up to a notch first (as in the bar).
                onWheel: wheel => {
                    acc += wheel.angleDelta.y;
                    const steps = Math.trunc(acc / 120);
                    if (steps === 0) return;
                    acc -= steps * 120;
                    root.setVolume(root.volume + steps * 0.05);
                }
            }
        }
        Label {
            visible: !root.hasSink
            Layout.fillWidth: true
            text: "Sin salida de audio"
            color: Ryce.Palette.fg2
            font.pixelSize: Ui.meta
        }
        Label {
            visible: root.hasSink
            text: root.muted ? "mudo" : Math.round(root.volume * 100) + " %"
            horizontalAlignment: Text.AlignRight
            Layout.preferredWidth: 44
            font.pixelSize: Ui.meta
            font.features: { "tnum": 1 }
        }
    }
}
