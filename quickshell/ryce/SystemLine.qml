import QtQuick
import QtQuick.Layouts
import Quickshell.Io
import qs
import qs as Ryce

// CPU and memory from /proc, sampled every 2 s only while the sidebar is shown.
// Glyphs in fg2, figures in fg1: a footnote, not a dashboard.
RowLayout {
    id: root
    property bool active
    property var lastCpu: null      // [idle, total] jiffies of the previous sample
    property real cpu: -1
    property real memUsedGiB: 0
    property real memTotalGiB: 0
    readonly property var es: Qt.locale("es_ES")

    function sampleCpu(text) {
        const f = text.slice(0, text.indexOf("\n")).trim().split(" ").filter(x => x !== "").slice(1).map(Number);
        if (f.length < 5) return;
        const idle = f[3] + f[4];
        const total = f.reduce((a, b) => a + b, 0);
        if (lastCpu !== null && total > lastCpu[1])
            cpu = 100 * (1 - (idle - lastCpu[0]) / (total - lastCpu[1]));
        lastCpu = [idle, total];
    }
    function sampleMem(text) {
        const kib = key => {
            const at = text.indexOf(key + ":");
            return at < 0 ? NaN : parseInt(text.slice(at + key.length + 1), 10);
        };
        const total = kib("MemTotal"), avail = kib("MemAvailable");
        if (!(total > 0) || isNaN(avail)) return;
        memTotalGiB = total / 1048576;
        memUsedGiB = (total - avail) / 1048576;
    }

    spacing: 8
    onActiveChanged: if (!active) { lastCpu = null; cpu = -1; }

    FileView {
        id: stat
        path: "/proc/stat"
        printErrors: false
        onLoaded: root.sampleCpu(text())
    }
    FileView {
        id: meminfo
        path: "/proc/meminfo"
        printErrors: false
        onLoaded: root.sampleMem(text())
    }
    Timer {
        running: root.active
        interval: 2000
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            stat.reload();
            meminfo.reload();
        }
    }

    Label { text: Ui.cpu; color: Ryce.Palette.fg2; font.family: Ryce.Palette.fontIcon; font.pixelSize: Ui.body }
    Label {
        text: root.cpu < 0 ? "cpu" : "cpu " + Math.round(root.cpu) + " %"
        font.pixelSize: Ui.meta
        font.features: { "tnum": 1 }
    }
    Item { implicitWidth: 12 }
    Label { text: Ui.memory; color: Ryce.Palette.fg2; font.family: Ryce.Palette.fontIcon; font.pixelSize: Ui.body }
    Label {
        Layout.fillWidth: true
        text: root.memTotalGiB > 0
            ? "ram " + root.memUsedGiB.toLocaleString(root.es, "f", 1) + " de " + Math.round(root.memTotalGiB) + " GB"
            : "ram"
        font.pixelSize: Ui.meta
        font.features: { "tnum": 1 }
    }
}
