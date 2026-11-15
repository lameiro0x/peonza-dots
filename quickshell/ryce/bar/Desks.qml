pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import qs.agents

// Which screen each workspace slot belongs to, the same answer for every bar. Live state
// first: a workspace that exists sits where Hyprland has it, moved there by hand
// included. One that does not exist yet goes where its workspace rule would open it, if
// that monitor is plugged in (a rule naming an absent monitor is no claim: its
// workspaces would be unreachable). Anything else goes to the leftmost screen, so one
// monitor without rules shows all ten. Screens run left to right, as on the desk.
// The rules come from `hyprctl -j workspacerules` (Quickshell has no API for them), read
// at start and on every config reload.
Singleton {
    id: desks
    readonly property bool hyprland: !!Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE")

    // Hyprland's monitors, left to right (top to bottom on a tie).
    readonly property var monitors: hyprland ? Hyprland.monitors.values.slice().sort((a, b) => a.x - b.x || a.y - b.y) : []
    property var rules: ({})        // workspace id -> the rule's monitor selector ("DP-1", "desc:AOC …")

    // Workspace id (1..Roster.maxWorkspace) -> the name of the monitor it belongs to.
    readonly property var owners: {
        const names = monitors.map(m => m.name);
        const map = {};
        if (!hyprland) return map;
        for (const w of Hyprland.workspaces.values) {
            const name = w.monitor?.name ?? "";
            if (w.id >= 1 && w.id <= Roster.maxWorkspace && names.includes(name)) map[w.id] = name;
        }
        for (let id = 1; id <= Roster.maxWorkspace; id++)
            map[id] = map[id] ?? resolve(rules[id]) ?? names[0] ?? "";
        return map;
    }

    // A rule's monitor selector to a plugged monitor's name, or null. `desc:` matches the
    // start of the description, as Hyprland does.
    function resolve(selector) {
        if (typeof selector !== "string" || selector === "") return null;
        const desc = selector.startsWith("desc:") ? selector.slice(5).trim() : null;
        const m = monitors.find(m => desc !== null ? m.description.startsWith(desc) : m.name === selector);
        return m?.name ?? null;
    }

    function parse(text) {
        try {
            const map = {};
            for (const r of JSON.parse(text)) {
                const ws = String(r?.workspaceString ?? "").trim();
                if (/^\d+$/.test(ws) && typeof r.monitor === "string" && r.monitor !== "") map[Number(ws)] = r.monitor;
            }
            rules = map;
        } catch (e) {
            // Half an answer or none: keep the rules we had.
        }
    }

    Process {
        id: query
        command: ["hyprctl", "-j", "workspacerules"]
        running: desks.hyprland
        stdout: StdioCollector {
            onStreamFinished: desks.parse(text)
        }
    }
    // Quickshell 0.3.2 can keep stale ids and a stale active workspace on its objects:
    // ask Hyprland again whenever a workspace or a monitor comes, goes, moves or takes
    // the focus. Once here, not once per bar.
    Connections {
        target: desks.hyprland ? Hyprland : null
        function onRawEvent(event) {
            const n = event.name;
            if (n === "configreloaded") query.running = true;
            if (["workspacev2", "focusedmonv2", "moveworkspacev2", "renameworkspace", "monitoraddedv2", "monitorremovedv2"].includes(n))
                Hyprland.refreshMonitors();
            if (["moveworkspacev2", "createworkspacev2", "destroyworkspacev2", "renameworkspace", "monitoraddedv2", "monitorremovedv2"].includes(n))
                Hyprland.refreshWorkspaces();
        }
    }
}
