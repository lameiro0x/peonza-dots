pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io

// agentd's roster (contracts/roster.v1.schema.json), read-only. agentd replaces the file
// atomically (tmp + rename), which drops a FileView watch: poll instead, every 500 ms,
// and parse only when the text changed. A parse error or an unknown schema keeps the
// last good model.
Singleton {
    id: roster

    // $RYCE_AGENTD_DIR (tools/stage/nested.sh) or $RYCE_RUNTIME (tools/stage/scene.sh)
    // override the runtime dir, else $XDG_RUNTIME_DIR/agentd.
    readonly property string runtimeDir: Quickshell.env("RYCE_AGENTD_DIR") || Quickshell.env("RYCE_RUNTIME") || (Quickshell.env("XDG_RUNTIME_DIR") ? Quickshell.env("XDG_RUNTIME_DIR") + "/agentd" : "")
    readonly property string path: runtimeDir ? runtimeDir + "/roster.json" : ""
    readonly property int maxWorkspace: 11      // contracts/constants.json max_ws

    property bool present: false       // roster.json exists and parsed at least once
    // Normalised, waiting first. Each: sessionId, project, title, name, state, waitingFor,
    // since, workspace, window, plus the story of the session: doing (what it does, one
    // line), did (the last thing it reported done, one line; "" from an agentd that
    // does not write it yet), asked (the first sentence of the user's last prompt),
    // waiting_on ("shell", "agent", "monitor" while busy only because of its own
    // background work, else "") and subagents [{ id, type, description, live }], live first.
    property var sessions: []
    // Every session, for the sidebar: by workspace (no window last), and inside one the
    // waiting first, then the working, then the ones whose turn is over.
    property var all: []
    // The sessions worth a look: working (background work included) or waiting for the
    // user, by workspace (no window last), waiting first inside one workspace.
    property var board: []
    readonly property int resting: sessions.length - board.length
    // sessionId → session, so a delegate kept by a ScriptModel reads the newest values.
    property var bySession: ({})
    property var counts: ({ waiting: 0, busy: 0, idle: 0 })
    property var focusedWorkspace: null
    // Index 0 is workspace 1. Workspaces agentd did not list are empty.
    property var workspaces: emptyWorkspaces()
    property string lastText: ""

    readonly property var states: ["waiting", "busy", "shell", "idle", "unknown"]
    readonly property var icons: ["claude", "term", "nvim", "code", "files", "browser", "window"]
    readonly property var waitingOn: ["shell", "agent", "monitor"]

    // The session a bar slot or a desk widget shows for workspace `id` (agentd's `lead`:
    // waiting > busy > the rest), or null.
    function sessionAt(id) {
        const slot = workspaceId(id) !== null && id <= maxWorkspace ? workspaces[id - 1] : null;
        return slot && slot.lead !== "" ? (bySession[slot.lead] ?? null) : null;
    }

    function str(v) { return typeof v === "string" ? v : ""; }
    function workspaceId(v) { return Number.isInteger(v) && v > 0 ? v : null; }
    // Window addresses compare without the 0x prefix: Quickshell's HyprlandToplevel.address may omit it.
    function address(v) { return typeof v === "string" && /^(0x)?[0-9a-f]+$/i.test(v) ? v.toLowerCase().replace(/^0x/, "") : ""; }
    function emptyWorkspaces() {
        const list = [];
        for (let i = 1; i <= maxWorkspace; i++)
            list.push({ id: i, occupied: false, active: false, label: "", icon: "window", state: "", lead: "" });
        return list;
    }

    function load(text) {
        if (text === lastText) return;
        let data;
        try {
            data = JSON.parse(text);
        } catch (e) {
            return;    // half-read or corrupt: keep the last good model
        }
        if (!data || data.schema !== "agentd.roster/1" || !Array.isArray(data.sessions)) return;
        lastText = text;

        // shortcut: at most 50 rows, a roster that large is a bug upstream.
        const list = data.sessions.filter(raw => raw !== null && typeof raw === "object" && str(raw.sessionId) !== "").slice(0, 50).map(raw => ({
            sessionId: str(raw.sessionId),
            project: str(raw.project),
            title: str(raw.title),
            name: str(raw.name),
            state: states.includes(raw.state) ? raw.state : "unknown",
            waitingFor: str(raw.waitingFor),
            since: typeof raw.since === "number" ? raw.since : null,
            // A stale agentd writes the old shapes (doing an object, subagents a count):
            // they read as empty.
            doing: str(raw.doing),
            did: str(raw.did),
            asked: str(raw.asked),
            waiting_on: waitingOn.includes(raw.waiting_on) ? raw.waiting_on : "",
            subagents: Array.isArray(raw.subagents) ? raw.subagents.filter(a => a !== null && typeof a === "object").slice(0, 8).map(a => ({
                id: str(a.id),
                type: str(a.type),
                description: str(a.description),
                live: a.live === true
            })) : [],
            workspace: workspaceId(raw.workspace),
            window: address(raw.window)
        }));
        // Waiting first whatever the file says; agentd's order is kept inside each group.
        sessions = list.filter(s => s.state === "waiting").concat(list.filter(s => s.state !== "waiting"));
        const index = {};
        for (const s of list) index[s.sessionId] = s;
        bySession = index;
        const slotOf = s => s.workspace ?? maxWorkspace + 1;
        board = sessions.filter(s => s.state === "waiting" || s.state === "busy")
            .sort((a, b) => slotOf(a) - slotOf(b) || (a.state === "waiting" ? 0 : 1) - (b.state === "waiting" ? 0 : 1));
        const rank = s => s.state === "waiting" ? 0 : s.state === "busy" || s.state === "shell" ? 1 : 2;
        // agentd's order breaks ties: the index, as V4's sort need not be stable.
        const order = new Map(sessions.map((s, i) => [s, i]));
        all = sessions.slice().sort((a, b) => slotOf(a) - slotOf(b) || rank(a) - rank(b) || order.get(a) - order.get(b));
        counts = {
            waiting: list.filter(s => s.state === "waiting").length,
            busy: list.filter(s => s.state === "busy").length,
            idle: list.filter(s => s.state !== "waiting" && s.state !== "busy").length
        };
        const slots = emptyWorkspaces();
        for (const raw of Array.isArray(data.workspaces) ? data.workspaces : []) {
            const id = workspaceId(raw?.id);
            // Each output lists slots 1..always_shown, empty ones included: the output that
            // really holds the workspace (occupied) wins over another output's empty slot.
            if (id === null || id > maxWorkspace || (slots[id - 1].occupied && raw.occupied !== true)) continue;
            slots[id - 1] = {
                id: id,
                occupied: raw.occupied === true,
                active: raw.active === true,
                label: str(raw.label),
                icon: icons.includes(raw.icon) ? raw.icon : "window",
                state: ["busy", "waiting", "idle"].includes(raw.state) ? raw.state : "",
                lead: str(raw.lead)
            };
        }
        workspaces = slots;
        focusedWorkspace = workspaceId(data.hypr?.focusedWorkspace);
        present = true;
    }

    function clear() {
        present = false;
        lastText = "";
        sessions = [];
        all = [];
        board = [];
        bySession = {};
        counts = { waiting: 0, busy: 0, idle: 0 };
        workspaces = emptyWorkspaces();
        focusedWorkspace = null;
    }

    FileView {
        id: file
        path: roster.path
        printErrors: false       // a missing roster (agentd stopped) is a normal state
        onLoaded: roster.load(text())
        onLoadFailed: error => {
            if (error === FileViewError.FileNotFound) roster.clear();
        }
    }
    Timer {
        running: roster.path !== ""
        interval: 500
        repeat: true
        onTriggered: file.reload()
    }
}
