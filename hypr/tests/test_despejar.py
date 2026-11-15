#!/usr/bin/env python3
"""ryce.despejar (hypr/despejar.lua, SUPER+e): clear every monitor, then bring
each one back as it was.

    python3 -m unittest discover -s hypr/tests -v

Runs the module in a stock Lua against a small fake of Hyprland's query API:
monitors show workspaces, workspaces hold windows. What it holds is the
contract, not the dispatch spelling (tools/stage/verify-config.sh and the nested
stage prove that): which workspace each monitor shows after a press, where every
window ends up, which window has the focus. Skipped when no `lua` is on PATH.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HYPR = Path(__file__).resolve().parent.parent
LUA = shutil.which("lua") or shutil.which("lua5.4") or shutil.which("luajit")

# The fake world. Workspaces are keyed by name (a numbered one is named "3",
# like Hyprland's own), windows by address; a monitor shows one workspace.
WORLD = r"""
W = { mons = {}, wss = {}, wins = {}, focus = nil }

local function ws_obj(name)
    local s = W.wss[name]
    if not s then return nil end
    local n = 0
    for _, w in pairs(W.wins) do if w.ws == name then n = n + 1 end end
    local visible = false
    for _, m in pairs(W.mons) do if m.active == name then visible = true end end
    -- A named workspace: Lua says nil on 0.57.2, older Hyprland a negative id.
    return { name = name, id = tonumber(name) or W.named_id, windows = n, visible = visible,
             special = false, __sel = name }
end

local function resolve(sel)
    if type(sel) == "table" then return sel.__sel end
    sel = tostring(sel)
    return sel:match("^name:(.+)$") or sel
end

local function win_obj(addr)
    local w = W.wins[addr]
    if not w then return nil end
    return { address = addr, workspace = ws_obj(w.ws) }
end

local function mon_obj(m)
    return {
        name = m.name, is_mirror = false, active_workspace = ws_obj(m.active),
        set_workspace = function(_, sel)
            local name = resolve(sel)
            W.wss[name] = W.wss[name] or {}
            for _, o in pairs(W.mons) do
                assert(o == m or o.active ~= name, "set_workspace stole a visible workspace")
            end
            m.active = name
            if m.focused then
                W.focus = nil
                for a, w in pairs(W.wins) do if w.ws == name and w.last then W.focus = a end end
            end
        end,
    }
end

hl = {
    get_monitors = function()
        local out = {}
        for _, m in ipairs(W.mons) do out[#out + 1] = mon_obj(m) end
        return out
    end,
    get_workspaces = function()
        local out = {}
        for name in pairs(W.wss) do out[#out + 1] = ws_obj(name) end
        return out
    end,
    get_workspace_windows = function(sel)
        local name, out = resolve(sel), {}
        for a, w in pairs(W.wins) do if w.ws == name then out[#out + 1] = win_obj(a) end end
        return out
    end,
    get_active_window = function() return W.focus and win_obj(W.focus) or nil end,
    get_window = function(sel) return win_obj(resolve(sel):match("^address:(.+)$")) end,
    dispatch = function(d) d() end,
    dsp = {
        window = {
            move = function(t)
                return function()
                    assert(t.follow == false, "a carried window must not pull the focus")
                    local addr = resolve(t.window):match("^address:(.+)$")
                    local name = resolve(t.workspace)
                    W.wss[name] = W.wss[name] or {}
                    W.wins[addr].ws = name
                end
            end,
        },
        focus = function(t)
            return function()
                local addr = resolve(t.window):match("^address:(.+)$")
                assert(W.wins[addr], "focus on a dead window")
                W.focus = addr
            end
        end,
    },
}

-- A world: monitors in order, the first one focused.
function world(mons, wins, focus)
    W.mons, W.wss, W.wins, W.focus = {}, {}, {}, focus
    for i, m in ipairs(mons) do
        W.mons[i] = { name = m[1], active = m[2], focused = i == 1 }
        W.wss[m[2]] = {}
    end
    for addr, ws in pairs(wins) do
        W.wss[ws] = W.wss[ws] or {}
        W.wins[addr] = { ws = ws, last = addr == focus }
    end
end

function load() dofile(HYPR .. "/despejar.lua") end
function press() ryce.despejar() end
function shows(name, want)
    for _, m in ipairs(W.mons) do
        if m.name == name then
            assert(m.active == want, name .. " shows " .. m.active .. ", want " .. want)
            return
        end
    end
    error("no monitor " .. name)
end
function on(addr, want)
    assert(W.wins[addr].ws == want, addr .. " is on " .. W.wins[addr].ws .. ", want " .. want)
end
function focused(want)
    assert(W.focus == want, "focus is " .. tostring(W.focus) .. ", want " .. tostring(want))
end
"""

SCENARIOS = {
    "clears_every_monitor_and_brings_each_back": """
        world({ { "DP-1", "1" }, { "HDMI-A-1", "9" } }, { a = "1", b = "1", c = "9" }, "b")
        load(); press()
        shows("DP-1", "despejado-1"); shows("HDMI-A-1", "despejado-9")
        on("a", "1"); on("b", "1"); on("c", "9")
        focused(nil)
        press()
        shows("DP-1", "1"); shows("HDMI-A-1", "9")
        on("a", "1"); on("b", "1"); on("c", "9")
        focused("b")
    """,
    "an_empty_monitor_is_left_alone": """
        world({ { "DP-1", "2" }, { "HDMI-A-1", "10" } }, { a = "2" }, "a")
        load(); press()
        shows("DP-1", "despejado-2"); shows("HDMI-A-1", "10")
        press()
        shows("DP-1", "2"); shows("HDMI-A-1", "10")
    """,
    "nothing_to_clear_is_a_no_op": """
        world({ { "DP-1", "4" } }, {}, nil)
        load(); press()
        shows("DP-1", "4")
    """,
    "a_window_opened_meanwhile_comes_back_with_the_rest": """
        world({ { "DP-1", "1" } }, { a = "1" }, "a")
        load(); press()
        W.wins.n = { ws = "despejado-1" }; W.focus = "n"
        press()
        shows("DP-1", "1"); on("a", "1"); on("n", "1")
        focused("n")
    """,
    "a_window_focused_on_another_monitor_keeps_the_focus": """
        world({ { "DP-1", "1" }, { "HDMI-A-1", "9" } }, { a = "1", c = "9" }, "a")
        load(); press()
        W.mons[1].active = "3"; W.wss["3"] = {}; W.wins.m = { ws = "3" }; W.focus = "m"
        W.mons[1].focused, W.mons[2].focused = false, false
        press()
        shows("HDMI-A-1", "9"); focused("m")
    """,
    "a_monitor_switched_away_meanwhile_keeps_its_new_workspace": """
        world({ { "DP-1", "1" }, { "HDMI-A-1", "9" } }, { a = "1", c = "9" }, "a")
        load(); press()
        W.mons[1].active = "3"; W.wss["3"] = {}
        press()
        shows("DP-1", "3"); shows("HDMI-A-1", "9")
    """,
    "a_window_left_on_a_hidden_despejado_workspace_is_carried_home": """
        world({ { "DP-1", "1" } }, { a = "1" }, "a")
        load(); press()
        W.wins.n = { ws = "despejado-1" }
        W.mons[1].active = "3"; W.wss["3"] = {}; W.wins.m = { ws = "3" }
        press()
        shows("DP-1", "despejado-3")
        on("n", "1"); on("m", "3")
    """,
    "the_way_back_survives_a_config_reload": """
        world({ { "DP-1", "5" } }, { a = "5" }, "a")
        load(); press()
        ryce = nil; load()
        press()
        shows("DP-1", "5"); on("a", "5")
    """,
    "a_named_workspace_round_trips": """
        world({ { "DP-1", "notas" } }, { a = "notas" }, "a")
        load(); press()
        shows("DP-1", "despejado-notas")
        press()
        shows("DP-1", "notas")
    """,
    "a_named_workspace_with_a_negative_id_round_trips": """
        world({ { "DP-1", "notas" } }, { a = "notas" }, "a")
        W.named_id = -1337
        load(); press()
        shows("DP-1", "despejado-notas")
        press()
        shows("DP-1", "notas"); on("a", "notas")
    """,
    "a_focused_window_closed_meanwhile_is_not_refocused": """
        world({ { "DP-1", "1" } }, { a = "1", b = "1" }, "b")
        load(); press()
        W.wins.b = nil
        press()
        shows("DP-1", "1"); focused(nil)
    """,
}


@unittest.skipUnless(LUA, "no lua interpreter on PATH")
class Despejar(unittest.TestCase):
    def run_lua(self, body: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "run.lua"
            script.write_text(f"HYPR = {str(HYPR)!r}\n{WORLD}\n{body}\nprint('ok')\n", encoding="utf-8")
            return subprocess.run([LUA, str(script)], capture_output=True, text=True, timeout=20)

    def test_scenarios(self):
        for name, body in SCENARIOS.items():
            with self.subTest(scenario=name):
                proc = self.run_lua(body)
                self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "ok"), proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
