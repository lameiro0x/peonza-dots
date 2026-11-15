import QtQuick
import qs
import qs as Ryce
import qs.desk

// The desk's Hito card. On top, which tasks it shows: hoy, atrasadas, todas, or one
// proyecto (picked from the projects with something pending). Then how many, large in
// the theme's display face like the desk clock, then up to six of them, each with its
// project's colour and its time, day or lateness, and a quiet last line. «Hoy» leaves the
// overdue out but counts them under the headline. Ticking happens in the drawer
// (SUPER+H). It sits on a desk Card: its inks are DeskUi's.
Column {
    id: card
    property bool shown
    property Hito hito
    property string filter: "hoy"           // hoy | atrasadas | todas | proyecto
    property string project: ""             // Hito.projectKey of the chosen project
    signal filterPicked(string key)
    signal projectPicked(string key)

    // The project picker takes about two rows' room: the card keeps its height, so the
    // desk widgets around it (DeskScreen's `under` in Ola) can count on it.
    readonly property int maxRows: filter === "proyecto" ? 4 : 6
    readonly property bool ready: hito.config === "ready"
    readonly property bool fresh: hito.fetchedAt > 0
    readonly property bool choosing: filter === "proyecto" && project === ""
    readonly property var list: !ready ? []
        : filter === "atrasadas" ? hito.overdue
        : filter === "todas" ? hito.everything
        : filter === "proyecto" ? (choosing ? [] : hito.ofProject(hito.everything, project))
        : hito.dueToday
    // `width`: the monospace faces (Origen's wide Martian Mono, Tinta's) need more room
    // for a task's title; Ola's card fits the sky between the crest and the clock.
    readonly property var stance: ({
        origen: { size: 56, weight: Font.Normal, caps: false, square: false, width: 480 },
        grafito: { size: 60, weight: Font.Bold, caps: false, square: true, width: 400 },
        ola: { size: 76, weight: Font.Normal, caps: false, square: false, width: 400 },
        papel: { size: 60, weight: Font.Bold, caps: false, square: true, width: 440 },
        tinta: { size: 44, weight: Font.Bold, caps: true, square: true, width: 460 }
    })[Ryce.Palette.themeId] ?? { size: 56, weight: Font.Normal, caps: false, square: false, width: 400 }
    readonly property color ink: DeskUi.ink
    readonly property color dim: DeskUi.dim
    readonly property color late: DeskUi.legible(Ryce.Palette.warn)

    function word(s) { return stance.caps ? s.toUpperCase() : s; }
    function plural(n, one, many) { return n === 1 ? one : many; }
    // What the list holds, and what it says when it holds nothing.
    readonly property string what: filter === "atrasadas" ? plural(list.length, "atrasada", "atrasadas")
        : filter === "todas" ? plural(list.length, "pendiente", "pendientes")
        : filter === "proyecto" ? "en " + hito.projectName(project)
        : plural(list.length, "tarea", "tareas") + " para hoy"
    readonly property string none: filter === "atrasadas" ? "nada atrasado"
        : filter === "todas" ? "nada pendiente"
        : filter === "proyecto" ? (choosing ? "elige un proyecto" : "nada pendiente en " + hito.projectName(project))
        : "nada para hoy"
    readonly property string headline: hito.config === "loading" ? "…"
        : !ready ? "Hito sin configurar  ·  " + (hito.config === "incomplete" ? "su .env está incompleto" : "falta su .env")
        : !fresh ? (hito.problem !== "" ? hito.problem : "…")
        : list.length === 0 ? none
        : what
    readonly property string subline: !ready || !fresh || filter !== "hoy" || hito.overdue.length === 0 ? ""
        : hito.overdue.length + plural(hito.overdue.length, " atrasada", " atrasadas")
    readonly property string footer: {
        if (!ready) return "";                // the headline already says it all
        const parts = ["hito"];
        if (list.length > maxRows) parts.push((list.length - maxRows) + " más");
        if (fresh && hito.problem !== "") parts.push(hito.problem.toLowerCase());
        parts.push("super+h abre la lista");
        return word(parts.join("  ·  "));
    }
    // The note at a task's end: how late, when, or that it has no date. «hoy» is said
    // only where the list mixes days.
    function meta(t) {
        if (t.date === "") return "sin fecha";
        if (t.date < hito.today) return hito.lateBy(t.date);
        const when = t.date === hito.today ? (filter === "hoy" ? "" : "hoy") : hito.weekday(t.date);
        const parts = [when, t.time].filter(s => s !== "");
        return parts.length > 0 ? parts.join(" ") : t.recurring ? "se repite" : "";
    }

    width: stance.width
    spacing: 8

    component Ink: Label {
        color: card.ink
        font.family: Ryce.Palette.fontUi
    }

    Reveal {
        visible: card.ready
        on: card.shown
        order: 0

        Choices {
            width: card.width
            options: [{ key: "hoy", label: "hoy" }, { key: "atrasadas", label: "atrasadas" },
                      { key: "todas", label: "todas" }, { key: "proyecto", label: "proyecto" }]
            current: card.filter
            ink: card.ink
            dim: card.dim
            hover: DeskUi.soft
            size: 12
            caps: card.stance.caps
            onPicked: key => card.filterPicked(key)
        }
    }
    // The projects to pick from, while «proyecto» is chosen.
    Reveal {
        visible: card.ready && card.filter === "proyecto"
        on: card.shown
        order: 0

        Choices {
            width: card.width
            options: card.hito.projectsIn(card.hito.everything, card.project)
                .map(p => ({ key: p.key, label: p.name, hue: p.hue }))
            current: card.project
            ink: card.ink
            dim: card.dim
            hover: DeskUi.soft
            size: 12
            caps: card.stance.caps
            square: card.stance.square
            hito: card.hito
            onPicked: key => card.projectPicked(key)
        }
    }

    Reveal {
        on: card.shown
        order: 1

        Row {
            spacing: 14

            Ink {
                id: count
                visible: card.ready && card.fresh && !card.choosing
                text: String(card.list.length)
                font.family: Ryce.Palette.fontDisplay
                font.pixelSize: Math.max(card.stance.size, Ryce.Palette.fontDisplayMinPx)
                font.weight: card.stance.weight
                font.features: { "tnum": 1 }
                elide: Text.ElideNone
            }
            // Sits on the count's baseline, or on its own line when there is no count.
            Column {
                y: count.visible ? count.baselineOffset - height : 0
                width: card.width - (count.visible ? count.width + 14 : 0)
                spacing: 2

                Ink {
                    width: parent.width
                    text: card.word(card.headline)
                    font.pixelSize: 15
                }
                Ink {
                    visible: text !== ""
                    width: parent.width
                    text: card.word(card.subline)
                    color: card.ready ? card.late : card.dim
                    font.pixelSize: 12
                }
            }
        }
    }

    Repeater {
        model: card.list.slice(0, card.maxRows)

        Reveal {
            id: line
            required property var modelData
            required property int index
            readonly property bool overdue: modelData.date !== "" && modelData.date < card.hito.today
            on: card.shown
            order: index + 2

            Item {
                width: card.width
                height: title.implicitHeight + 2

                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 7
                    height: 7
                    radius: card.stance.square ? 1 : 3.5
                    color: card.hito.dotColor(line.modelData.hue, card.dim)
                }
                Ink {
                    id: title
                    x: 17
                    width: meta.x - x - 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: line.modelData.title
                    font.pixelSize: 14
                }
                Ink {
                    id: meta
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: card.word(card.meta(line.modelData))
                    color: line.overdue ? card.late : card.dim
                    font.pixelSize: 12
                    font.features: { "tnum": 1 }
                    elide: Text.ElideNone
                }
            }
        }
    }

    Reveal {
        visible: card.footer !== ""
        on: card.shown
        order: card.maxRows + 2

        Ink {
            text: card.footer
            color: card.dim
            font.pixelSize: 11
            font.letterSpacing: 0.6
            elide: Text.ElideNone
        }
    }
}
