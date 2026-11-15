import QtQuick
import qs as Ryce

// A minute of history in a module: a line over a faint fill (desk/Sparkline at bar
// scale, in the module's hue), or, with `bars`, a column per sample as in a terminal
// monitor. Repainted only when a sample arrives or the colours move.
Canvas {
    id: trace
    property var values: []
    property real hi: 100
    property int capacity: 20
    property bool bars: false
    property color color: Ryce.Palette.fg1

    implicitWidth: bars ? capacity * 3 - 1 : 44
    implicitHeight: Math.round(BarUi.chipHeight * 0.5)
    onValuesChanged: requestPaint()
    onColorChanged: requestPaint()
    onBarsChanged: requestPaint()

    Connections {
        target: Ryce.Palette
        function onLineChanged() { trace.requestPaint(); }
    }

    onPaint: {
        const ctx = getContext("2d");
        ctx.reset();
        const n = Math.min(values.length, capacity);
        const vals = values.slice(-n);
        const level = v => Math.min(1, Math.max(0, v / Math.max(hi, 1e-9)));
        if (bars) {
            // Newest at the right; an empty slot is a 1 px stub in `line`.
            for (let i = 0; i < capacity; i++) {
                const v = i - (capacity - n) >= 0 ? vals[i - (capacity - n)] : -1;
                const h = v < 0 ? 1 : Math.max(1, Math.round(level(v) * height));
                ctx.fillStyle = v < 0 ? Ryce.Palette.line : color;
                ctx.fillRect(i * 3, height - h, 2, h);
            }
            return;
        }
        // The floor is a dotted axis, never a solid rule: a solid rule under an idle,
        // flat trace read as an empty input field («______»). An idle minute (under 4 %
        // of the scale throughout) draws the axis alone.
        ctx.fillStyle = Ryce.Palette.rgba(Ryce.Palette.fg2, 0.8);
        for (let dx = width - 2; dx >= 0; dx -= 4) ctx.fillRect(dx, height - 1, 1, 1);
        const peak = vals.reduce((m, v) => Math.max(m, level(v)), 0);
        if (n < 2 || peak < 0.04) return;
        const step = (width - 3) / (capacity - 1);
        const x = i => width - 2 - (n - 1 - i) * step;
        const y = v => 1.5 + (height - 4) * (1 - level(v));

        ctx.beginPath();
        ctx.moveTo(x(0), height - 1);
        for (let i = 0; i < n; i++) ctx.lineTo(x(i), y(vals[i]));
        ctx.lineTo(x(n - 1), height - 1);
        ctx.closePath();
        // Denser as the load climbs: a pinned trace with a faint fill read as an empty box.
        ctx.fillStyle = Ryce.Palette.rgba(color, 0.16 + 0.2 * peak * peak);
        ctx.fill();

        ctx.beginPath();
        for (let i = 0; i < n; i++) i ? ctx.lineTo(x(i), y(vals[i])) : ctx.moveTo(x(i), y(vals[i]));
        ctx.lineWidth = 1.25;
        ctx.lineJoin = "round";
        ctx.strokeStyle = color;
        ctx.stroke();
    }
}
