import QtQuick
import qs
import qs as Ryce

// PC stats on the desk, from a Sampler that runs only while `live` (shown and not
// covered by a window), each kept as a short history for its sparkline.
Column {
    id: stats
    property bool shown
    property bool live
    readonly property int history: 48       // samples per sparkline: 96 s

    property var cpuHist: []
    property var memHist: []
    property var gpuHist: []
    property var tempHist: []
    property var rxHist: []

    function keep(list, v) {
        const out = list.concat([v]);
        return out.length > history ? out.slice(out.length - history) : out;
    }

    spacing: 9

    Sampler {
        id: pc
        live: stats.live
        onSampled: {
            if (pc.fresh) {
                stats.cpuHist = stats.keep(stats.cpuHist, pc.cpu);
                if (pc.gpuBusy >= 0) stats.gpuHist = stats.keep(stats.gpuHist, pc.gpuBusy);
                stats.rxHist = stats.keep(stats.rxHist, pc.rx);
            }
            if (pc.memTotal > 0) stats.memHist = stats.keep(stats.memHist, pc.memUsed);
            if (pc.temp >= 0) stats.tempHist = stats.keep(stats.tempHist, pc.temp);
        }
    }

    StatRow {
        on: stats.shown
        order: 0
        label: "procesador"
        value: pc.cpu < 0 ? "…" : Math.round(pc.cpu) + DeskUi.unit + "%"
        trailing: Sparkline { values: stats.cpuHist; capacity: stats.history }
    }
    StatRow {
        on: stats.shown
        order: 1
        label: "memoria"
        value: pc.memTotal > 0 ? pc.gb(pc.memUsed) + " de " + Math.round(pc.memTotal) + DeskUi.unit + "GB" : "…"
        trailing: Sparkline { values: stats.memHist; hi: pc.memTotal; capacity: stats.history }
    }
    StatRow {
        on: stats.shown
        order: 2
        label: "gráfica"
        available: pc.prev === null || pc.prev.gpu !== undefined
        value: pc.gpuBusy < 0 ? "…"
            : Math.round(pc.gpuBusy) + DeskUi.unit + "% ocupada" + (pc.gpuMhz > 0 ? "  ·  " + pc.gpuMhz + DeskUi.unit + "MHz" : "")
        trailing: Sparkline { values: stats.gpuHist; capacity: stats.history }
    }
    StatRow {
        on: stats.shown
        order: 3
        label: "temperatura"
        available: pc.prev === null || pc.prev.temp !== undefined
        value: pc.temp < 0 ? "…" : Math.round(pc.temp) + DeskUi.unit + "°C"
        trailing: Sparkline { values: stats.tempHist; lo: 30; hi: 100; capacity: stats.history }
    }
    StatRow {
        on: stats.shown
        order: 4
        label: "disco"
        value: pc.diskTotal > 0 ? pc.gb(pc.diskUsed) + " de " + Math.round(pc.diskTotal) + DeskUi.unit + "GB" : "…"

        // Usage of /, a bar rather than a line: it moves too slowly to draw a history.
        trailing: Item {
            implicitWidth: 120
            implicitHeight: 20

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 3
                radius: 1.5
                color: Ryce.Palette.line
            }
            Rectangle {
                anchors.bottom: parent.bottom
                width: pc.diskTotal > 0 ? Math.round(parent.width * pc.diskUsed / pc.diskTotal) : 0
                height: 3
                radius: 1.5
                color: Ryce.Palette.tint
            }
        }
    }
    StatRow {
        on: stats.shown
        order: 5
        label: "red"
        value: "↓ " + pc.rate(pc.rx) + "  ↑ " + pc.rate(pc.tx)
        trailing: Sparkline { values: stats.rxHist; hi: Math.max(64e3, ...stats.rxHist); capacity: stats.history }
    }
    StatRow {
        on: stats.shown
        order: 6
        label: "encendido"
        value: pc.since(pc.uptime)
    }
}
