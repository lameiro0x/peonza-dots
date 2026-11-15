import QtQuick
import Quickshell.Networking
import qs as Ryce

// The machine at a glance, left of the focus line: CPU (a minute of history, load,
// package temperature), memory in use, and the network link with its rates. Each icon
// wears its module's hue; Tinta trades the icons for terminal labels and draws the CPU
// history as columns.
Row {
    id: stats
    readonly property var es: Qt.locale("es_ES")
    readonly property bool terminal: BarUi.skin === "box"

    // Wired beats wifi; bridges and virtual devices are type None and never count.
    readonly property int link: {
        const up = Networking.devices.values.filter(d => d.connected);
        return up.some(d => d.type === DeviceType.Wired) ? DeviceType.Wired : up.some(d => d.type === DeviceType.Wifi) ? DeviceType.Wifi : DeviceType.None;
    }

    function rate(bps) {
        if (bps < 0) return "…";
        if (bps < 1e3) return Math.round(bps) + " B";
        if (bps < 1e6) return Math.round(bps / 1e3) + " kB";
        return (bps / 1e6).toLocaleString(es, "f", bps < 1e8 ? 1 : 0) + " MB";
    }
    function percent(v) { return v < 0 ? "…" : Math.round(v) + "%"; }

    Module {
        Accessible.name: "Procesador " + stats.percent(SysStats.cpu) + (SysStats.temp > 0 ? ", " + Math.round(SysStats.temp) + " grados" : "")

        Head { glyph: Ryce.Ui.cpu; word: "cpu"; hue: Ryce.Palette.hueCpu; terminal: stats.terminal }
        Trace {
            anchors.verticalCenter: parent.verticalCenter
            values: SysStats.cpuHist
            // Scaled to the minute's peak (25 % at least): an idle desktop still draws a
            // shape, and the figure beside it gives the absolute load.
            hi: Math.max(25, ...SysStats.cpuHist)
            capacity: SysStats.history
            bars: stats.terminal
            color: stats.terminal ? Ryce.Palette.fg1 : Ryce.Palette.hueCpu
        }
        BarText {
            text: stats.percent(SysStats.cpu)
            reserve: "00%"         // two digits: a full 100 % is rare enough to nudge
        }
        BarText {
            visible: SysStats.temp > 0
            text: Math.round(SysStats.temp) + "°"
            reserve: "00°"
            color: SysStats.temp >= 90 ? Ryce.Palette.warn : Ryce.Palette.fg1
        }
    }
    Module {
        Accessible.name: "Memoria " + stats.percent(SysStats.mem)

        Head { glyph: Ryce.Ui.memory; word: "ram"; hue: Ryce.Palette.hueMem; terminal: stats.terminal }
        BarText {
            text: stats.percent(SysStats.mem)
            reserve: "00%"
        }
    }
    Module {
        Accessible.name: (stats.link === DeviceType.Wired ? "Red por cable" : stats.link === DeviceType.Wifi ? "Wifi" : "Sin red")
            + ", baja " + stats.rate(SysStats.rx) + " por segundo, sube " + stats.rate(SysStats.tx)

        Head {
            glyph: String.fromCodePoint(stats.link === DeviceType.Wired ? 0xf0317     // md-lan
                : stats.link === DeviceType.Wifi ? 0xf05a9                              // md-wifi
                : 0xf0319)                                                               // md-lan_disconnect
            word: "net"
            hue: stats.link === DeviceType.None ? Ryce.Palette.fg2 : Ryce.Palette.hueNet
            terminal: stats.terminal
        }
        Head { glyph: String.fromCodePoint(0xf0045); word: "↓"; hue: Ryce.Palette.fg2; terminal: stats.terminal; small: true }     // md-arrow_down
        BarText {
            text: stats.rate(SysStats.rx)
            reserve: "999 kB"
        }
        Head { glyph: String.fromCodePoint(0xf005d); word: "↑"; hue: Ryce.Palette.fg2; terminal: stats.terminal; small: true }     // md-arrow_up
        BarText {
            text: stats.rate(SysStats.tx)
            reserve: "999 kB"
        }
    }
}
