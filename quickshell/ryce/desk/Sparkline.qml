import QtQuick
import qs as Ryce

// A tiny history line, newest sample at the right edge, in the theme's tint over a
// one-pixel baseline. Until `capacity` samples are in, the ones there spread over the
// whole width, so a fresh desk shows a line, not a hairline with a stub at its end. A
// series that does not move at this height (under 2 % of the scale) is drawn as a dotted
// mid line in a fainter tint: steady, not an empty field. Repainted only when a sample
// arrives (or the tint moves).
Canvas {
    id: spark
    property var values: []
    property real lo: 0
    property real hi: 100
    property int capacity: 48

    implicitWidth: 120
    implicitHeight: 20
    onValuesChanged: requestPaint()

    Connections {
        target: Ryce.Palette
        function onTintChanged() { spark.requestPaint(); }
        function onLineChanged() { spark.requestPaint(); }
    }

    onPaint: {
        const ctx = getContext("2d");
        ctx.reset();
        ctx.fillStyle = Ryce.Palette.line;
        ctx.fillRect(0, height - 1, width, 1);
        const n = Math.min(values.length, capacity);
        if (n < 2) return;
        const step = (width - 3) / (n < capacity ? n - 1 : capacity - 1);
        const span = Math.max(hi - lo, 1e-9);
        const x = i => width - 2 - (n - 1 - i) * step;
        const y = v => 1.5 + (height - 4) * (1 - Math.min(1, Math.max(0, (v - lo) / span)));
        const vals = values.slice(-n);

        if (Math.max(...vals) - Math.min(...vals) < 0.02 * span) {
            const mid = Math.round(height / 2);
            ctx.fillStyle = Ryce.Palette.rgba(Ryce.Palette.tint, 0.5);
            for (let px = x(0); px < x(n - 1) - 3; px += 4) ctx.fillRect(Math.round(px), mid, 2, 1);
            ctx.beginPath();
            ctx.arc(x(n - 1), mid + 0.5, 1.75, 0, 2 * Math.PI);
            ctx.fillStyle = Ryce.Palette.tint;
            ctx.fill();
            return;
        }

        ctx.beginPath();
        ctx.moveTo(x(0), height - 1);
        for (let i = 0; i < n; i++) ctx.lineTo(x(i), y(vals[i]));
        ctx.lineTo(x(n - 1), height - 1);
        ctx.closePath();
        ctx.fillStyle = Ryce.Palette.rgba(Ryce.Palette.tint, 0.10);
        ctx.fill();

        ctx.beginPath();
        for (let i = 0; i < n; i++) i ? ctx.lineTo(x(i), y(vals[i])) : ctx.moveTo(x(i), y(vals[i]));
        ctx.lineWidth = 1.25;
        ctx.lineJoin = "round";
        ctx.strokeStyle = Ryce.Palette.tint;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(x(n - 1), y(vals[n - 1]), 1.75, 0, 2 * Math.PI);
        ctx.fillStyle = Ryce.Palette.tint;
        ctx.fill();
    }
}
