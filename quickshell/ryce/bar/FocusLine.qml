import QtQuick
import QtQuick.Shapes
import Quickshell.Hyprland
import Quickshell.Wayland
import qs as Ryce
import qs.agents

// What the focused window is about. A Claude Code window (the session whose `window` is
// the active toplevel, or a title that starts with Claude Code's own mark) wears
// Claude's spark in the brand's terracotta and says what its session is doing, agentd's
// one line (the project is already on the active workspace slot beside it), or what it
// waits for; any other window, its title. Claude Code titles its terminal «✳ …» (idle)
// or with a braille spinner (working): neither is in the bar's fonts, and ✳ fell back to
// Noto Color Emoji, a green square. The mark is cut from the title and drawn here.
// It takes what the bar leaves between the machine readouts and the workspaces: a line
// that does not fit ends in «…» like the playing title, and with less than `minWidth`
// to spare the line steps aside, a Claude window keeping its spark alone.
// Everything here is transcript or window text: plain text only.
Item {
    id: line
    property bool hyprland: false
    property int workspace: 0          // this screen's active workspace
    property real maxWidth: 400
    readonly property int minWidth: 160

    // Quickshell 0.3.2 learns Hyprland's active window from the next focus event only, so
    // after a shell (re)start it is null until then: the Wayland side knows it already.
    readonly property var active: !hyprland ? null : Hyprland.activeToplevel
        ?? Hyprland.toplevels.values.find(t => t.wayland !== null && t.wayland === ToplevelManager.activeToplevel) ?? null
    // Hyprland can keep the last window active on an empty workspace: only trust it on this one.
    readonly property var toplevel: hyprland
        ? (active?.workspace?.id === workspace ? active : null)
        : ToplevelManager.activeToplevel
    readonly property string address: hyprland && toplevel ? Roster.address(toplevel.address) : ""
    readonly property var session: address === "" ? null : (Roster.sessions.find(s => s.window === address) ?? null)
    // Claude Code's title mark: ✳ (U+2733) or a braille spinner cell, then a space.
    readonly property var marked: /^[\u2733\u2800-\u28ff]+\s*/.exec(String(toplevel?.title ?? ""))
    readonly property string title: String(toplevel?.title ?? "").slice(marked?.[0].length ?? 0)
    readonly property bool claude: session !== null || marked !== null
    // `doing` is one line (agentd's roster, up to 60 characters); empty or missing, the
    // window's title speaks.
    readonly property string text: {
        let s = title;
        if (session !== null) {
            const doing = typeof session.doing === "string" ? session.doing : "";
            s = session.state === "waiting" ? (Ryce.Words.waitingFor[session.waitingFor] ?? Ryce.Words.waitingFallback)
                : doing !== "" ? doing : title;
        }
        return s.replace(/\s+/g, " ").trim();
    }
    // Measured, never read back from the Text: widths it sets would loop.
    readonly property real natural: Math.ceil(metrics.advanceWidth(text))
    readonly property bool fits: text !== "" && maxWidth >= minWidth
    readonly property int markRoom: claude ? spark.width + BarUi.inner : 0
    readonly property bool sparkOnly: claude && !fits && maxWidth >= spark.width

    implicitWidth: fits ? Math.min(maxWidth, markRoom + natural) : sparkOnly ? spark.width : 0
    implicitHeight: BarUi.band
    opacity: fits || sparkOnly ? 1 : 0
    // On the workspaces' own curve: the room it fills follows the row's width.
    Behavior on implicitWidth { NumberAnimation { duration: Ryce.Palette.motionMs; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
    Behavior on opacity { NumberAnimation { duration: Ryce.Palette.motionMs * 0.6; easing.type: Easing.OutCubic } }
    Accessible.role: Accessible.StaticText
    Accessible.name: text

    FontMetrics {
        id: metrics
        font: label.font
    }

    // Claude's spark, Claude Code's own ✳: four strokes through the centre, eight rays.
    // Palette.claude is the brand's #d97757, deepened on paper for contrast.
    Shape {
        id: spark
        readonly property real c: width / 2                 // centre
        readonly property real r: c - 1                     // a ray, kept inside the box
        readonly property real d: r * Math.SQRT1_2          // a diagonal ray's run and rise
        visible: line.claude
        width: Math.round(BarUi.textPx * 0.86)
        height: width
        anchors.verticalCenter: parent.verticalCenter
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: Ryce.Palette.claude ?? Ryce.Palette.fg1
            strokeWidth: Math.max(1.5, spark.width / 8)
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            startX: spark.c - spark.r
            startY: spark.c
            PathLine { x: spark.c + spark.r; y: spark.c }
            PathMove { x: spark.c; y: spark.c - spark.r }
            PathLine { x: spark.c; y: spark.c + spark.r }
            PathMove { x: spark.c - spark.d; y: spark.c - spark.d }
            PathLine { x: spark.c + spark.d; y: spark.c + spark.d }
            PathMove { x: spark.c + spark.d; y: spark.c - spark.d }
            PathLine { x: spark.c - spark.d; y: spark.c + spark.d }
        }
    }
    BarText {
        id: label
        visible: line.fits
        x: line.markRoom
        width: Math.max(0, line.width - line.markRoom)
        text: line.text
        elide: Text.ElideRight
        color: Ryce.Palette.fg1
    }
}
