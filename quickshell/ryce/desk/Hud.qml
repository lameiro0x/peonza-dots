import QtQuick
import Quickshell
import Quickshell.Io
import qs
import qs as Ryce
import qs.agents

// The YoRHa-style readout (Tinta's desk): two columns of CAPS_SNAKE monospace on a desk
// Card, our own data in its voice. The AI link comes from agentd's roster, the PC from a
// Sampler (every 2 s, only while `live`), host and kernel are read once. Under the
// meters, the sessions worth a look, like the sidebar's board (SUPER+A): working (a
// background task included) or waiting for you, in workspace order, each with its
// state and one short line of what it is doing. The bracket line turns into an
// inverted block while an AI waits.
Column {
    id: hud
    property bool live
    readonly property int px: 13
    readonly property real cw: probe.implicitWidth / 10 // one monospace cell
    readonly property int keyWidth: 11
    readonly property int rightAt: 37                   // the right column, in cells
    readonly property int rightCells: 34
    readonly property int slots: 12                     // cells in a meter
    readonly property int cells: rightAt + rightCells   // the whole width
    readonly property int maxRows: 4                    // sessions listed

    property string host: ""
    property string kernel: ""
    property int spin: 0
    // The same board as the sidebar (agents/Roster.qml): working or waiting, by workspace.
    readonly property var board: Roster.board ?? []
    readonly property int working: board.filter(s => s.state !== "waiting").length
    readonly property string spinner: working > 0 ? "|/-\\"[spin % 4] : "-"
    readonly property bool waiting: Roster.counts.waiting > 0

    // Roster text comes from transcripts: one line, no control characters, upper case.
    function clean(s) { return s.replace(/[\u0000-\u001f\u007f]+/g, " ").trim().toUpperCase(); }
    // No String.trimEnd in Qt's JS engine.
    function clip(s, n) { return s.length > n ? s.slice(0, n - 1).replace(/\s+$/, "") + "…" : s; }
    function stateWord(s) {
        if (s.state === "waiting") return Words.waitingFor[s.waitingFor] ?? Words.waitingFallback;
        const on = typeof s.waiting_on === "string" ? s.waiting_on : "";
        if (on === "shell") return "espera un comando";
        if (on === "agent") return "espera un subagente";
        if (on === "monitor") return "vigila un proceso";
        return Words.state[s.state] ?? Words.state.busy;
    }
    // One short line: what it is doing, else what it was last asked, else its title.
    function doing(s) {
        const str = v => typeof v === "string" ? v : "";
        return clip(clean(str(s.doing)) || clean(str(s.asked)) || clean(str(s.title)), 60);
    }
    function label(s) { return clean(s.project) || clean(s.name) || clean(s.title) || "SESIÓN"; }
    function key(k) { return k.padEnd(keyWidth) + ": "; }
    function pct(v) { return v < 0 ? " --%" : String(Math.round(v)).padStart(3) + "%"; }
    function meter(v) {
        const n = v < 0 ? 0 : Math.max(v > 0 ? 1 : 0, Math.min(slots, Math.round(v / 100 * slots)));
        return "[" + "|".repeat(n) + ".".repeat(slots - n) + "]  " + pct(v);
    }
    function temp(v) { return v < 0 ? "-- °C" : Math.round(v) + " °C"; }

    width: (rightAt + rightCells) * cw
    spacing: 3

    Sampler {
        id: pc
        live: hud.live
        onSampled: if (hud.working > 0) hud.spin++
    }
    FileView {
        path: "/proc/sys/kernel/hostname"
        printErrors: false
        onLoaded: hud.host = text().trim().toUpperCase()
    }
    FileView {
        path: "/proc/sys/kernel/osrelease"
        printErrors: false
        onLoaded: hud.kernel = text().trim().toUpperCase()
    }

    // One readout cell: monospace, one line, elided at its column.
    component Cell: Label {
        property int cells: hud.rightAt - 3
        width: cells * hud.cw
        color: DeskUi.soft
        font.family: Ryce.Palette.fontMono
        font.pixelSize: hud.px
        font.features: { "tnum": 1 }
    }
    // Two cells on one line; the right one may split its key (dim) from its value.
    component Line: Item {
        id: line
        property alias first: l.text
        property alias firstColor: l.color
        property bool bold
        property string key
        property string value
        property color keyColor: DeskUi.soft
        property color valueColor: DeskUi.soft

        implicitWidth: hud.width
        implicitHeight: l.implicitHeight

        Cell { id: l; font.bold: line.bold }
        Row {
            x: hud.rightAt * hud.cw
            Cell {
                width: implicitWidth
                text: line.key
                color: line.keyColor
            }
            Cell {
                cells: hud.rightCells - line.key.length
                text: line.value
                color: line.valueColor
            }
        }
    }
    // A temperature with its small caption, centred on each other.
    component Temp: Column {
        id: t
        property real value
        property string caption
        spacing: 2

        Cell {
            anchors.horizontalCenter: t.horizontalCenter
            width: implicitWidth
            text: hud.temp(t.value)
            color: DeskUi.ink
        }
        Label {
            anchors.horizontalCenter: t.horizontalCenter
            text: t.caption
            color: DeskUi.dim
            font.family: Ryce.Palette.fontMono
            font.pixelSize: 10
        }
    }
    component Gap: Item { implicitWidth: 1; implicitHeight: hud.px }

    // Measures the cell, and follows the theme's face (a Column skips it: invisible).
    Cell {
        id: probe
        visible: false
        width: implicitWidth
        text: "MMMMMMMMMM"
    }

    Line {
        bold: true
        first: hud.key("ENLACE_IA") + (Roster.present
            ? Roster.sessions.length + (Roster.sessions.length === 1 ? " SESIÓN" : " SESIONES") + " [ " + hud.spinner + " ]"
            : "SIN ENLACE [ - ]")
        firstColor: DeskUi.ink
        key: hud.key("UNIDAD")
        keyColor: DeskUi.ink
        value: hud.host || "…"
        valueColor: DeskUi.ink
    }
    Line {
        first: hud.key(Words.state.busy.toUpperCase()) + hud.working
        key: hud.key("NÚCLEO")
        value: hud.kernel || "…"
    }
    Line {
        first: hud.key(Words.state.waiting.toUpperCase()) + Roster.counts.waiting
        firstColor: DeskUi.dim
        key: hud.key("ACTIVO")
        keyColor: DeskUi.dim
        value: pc.since(pc.uptime).toUpperCase()
        valueColor: DeskUi.dim
    }
    Gap {}
    Line {
        first: hud.key("CPU_CARGA") + hud.meter(pc.cpu)
        firstColor: DeskUi.ink
        key: hud.key("GPU_CARGA")
        keyColor: DeskUi.ink
        value: hud.meter(pc.gpuBusy)
        valueColor: DeskUi.ink
    }
    Line {
        first: hud.key("RAM_USO") + hud.meter(pc.memTotal > 0 ? 100 * pc.memUsed / pc.memTotal : -1)
        firstColor: DeskUi.ink
        key: hud.key("DISCO_USO")
        keyColor: DeskUi.ink
        value: hud.meter(pc.diskTotal > 0 ? 100 * pc.diskUsed / pc.diskTotal : -1)
        valueColor: DeskUi.ink
    }
    Line {
        first: hud.key("RED_BAJADA") + pc.rate(pc.rx).toUpperCase()
        firstColor: DeskUi.dim
        key: hud.key("RED_SUBIDA")
        keyColor: DeskUi.dim
        value: pc.rate(pc.tx).toUpperCase()
    }
    Gap {}

    // The board: «> WS LABEL ... STATE», the label elided at its column, then its line
    // hung under the label on a «└» (a child line, never read as a wrap), only when it
    // says more than the label. A waiting one is marked «!» and inked bright. Nothing to
    // list says why.
    Cell {
        visible: hud.board.length === 0
        cells: hud.cells
        text: !Roster.present ? "> AGENTD SIN RESPUESTA" : "> SIN SESIONES ACTIVAS"
        color: DeskUi.dim
    }
    Repeater {
        model: hud.board.slice(0, hud.maxRows)

        Column {
            id: row
            required property var modelData
            readonly property bool waits: modelData.state === "waiting"
            spacing: 1

            Line {
                bold: row.waits
                first: (row.waits ? "! " : "> ") + (row.modelData.workspace ?? "·") + "  " + hud.label(row.modelData)
                firstColor: row.waits ? DeskUi.ink : DeskUi.soft
                value: hud.stateWord(row.modelData).toUpperCase()
                valueColor: row.waits ? DeskUi.ink : DeskUi.soft
            }
            Cell {
                readonly property string line: hud.doing(row.modelData)
                visible: line !== "" && line !== hud.label(row.modelData)
                cells: hud.cells
                text: "   └ " + line
                color: DeskUi.dim
            }
        }
    }
    Cell {
        visible: hud.board.length > hud.maxRows
        cells: hud.cells
        text: "  + " + (hud.board.length - hud.maxRows) + " MÁS EN SUPER+A"
        color: DeskUi.dim
    }
    Gap {}

    // The bracket line: centred under both columns; an amber block (the signal: an AI
    // waits for you) while one waits.
    Item {
        width: hud.width
        height: bracket.implicitHeight + 4

        Rectangle {
            anchors.centerIn: parent
            width: bracket.implicitWidth + 2 * hud.cw
            height: parent.height
            color: Ryce.Palette.signal
            visible: hud.waiting
        }
        Cell {
            id: bracket
            anchors.centerIn: parent
            width: implicitWidth
            text: hud.waiting ? "[ ATENCIÓN REQUERIDA ]" : "[ SISTEMA NOMINAL ]"
            color: hud.waiting ? Ryce.Palette.inkOnPill : DeskUi.ink
            font.bold: true
        }
    }
    Gap {}

    // Two temperatures under the bracket: the CPU, then the GPU if it has a sensor,
    // else the NVMe drive.
    Row {
        x: (hud.width - width) / 2
        spacing: 9 * hud.cw

        Temp { value: pc.temp; caption: "Temperatura CPU" }
        Temp {
            value: pc.gpuTemp >= 0 ? pc.gpuTemp : pc.ssdTemp
            caption: pc.gpuTemp >= 0 ? "Temperatura GPU" : "Temperatura NVMe"
        }
    }
}
