-- Despejar (SUPER+e, keys/keymap.tsv): every monitor that shows windows slides
-- to an empty workspace of its own, so the wallpaper and the desk widgets show;
-- the next press brings each monitor's workspace back.
--
-- Whole workspaces step aside, not the windows: moving windows out and back would
-- rebuild every dwindle tree in a new order and lose split ratios, fullscreen and
-- floating positions. A hidden workspace keeps all of that, and the focus comes
-- back with it.
--
-- The empty workspace is named after the one it hides (`despejado-3`), so the way
-- back lives in Hyprland, not in this Lua state, and survives `hyprctl reload`.
-- Named workspaces have no number: the bar's slots 1..10 and agentd's workspace
-- map never see them, and the windows never leave their own workspace.
--
-- A monitor switched elsewhere meanwhile keeps its new workspace. A window opened
-- on a despejado workspace goes back with the workspace it stands for, also when
-- the user left it behind hidden. Pinned windows stay, as pinned windows do.

ryce = ryce or {}

local PREFIX = "despejado-"

-- The workspace a despejado one stands for, as a selector; nil for any other.
local function origin(name)
    local rest = name and name:sub(1, #PREFIX) == PREFIX and name:sub(#PREFIX + 1) or ""
    if rest == "" then return nil end
    return rest:match("^%d+$") and tonumber(rest) or "name:" .. rest
end

-- The window focused before the last clear. Only the focus depends on it: a
-- reload forgets it and the restored workspace focuses its own last window.
local focus

local function clear(monitors)
    local w = hl.get_active_window()
    focus = w and w.address
    for _, m in ipairs(monitors) do
        local ws = m.active_workspace
        if ws.windows > 0 then
            -- A named workspace has no id on 0.57.2 (a negative one before): use its name.
            m:set_workspace("name:" .. PREFIX .. ((ws.id and ws.id > 0) and ws.id or ws.name))
        end
    end
end

-- Windows on a hidden despejado workspace go home, silently.
local function carry_home()
    for _, ws in ipairs(hl.get_workspaces()) do
        local home = origin(ws.name)
        if home and not ws.visible and ws.windows > 0 then
            for _, w in ipairs(hl.get_workspace_windows(ws)) do
                hl.dispatch(hl.dsp.window.move({ workspace = home, follow = false, window = "address:" .. w.address }))
            end
        end
    end
end

-- A window focused now (one opened on the clear desk, or one on a monitor the
-- user switched elsewhere) keeps the focus; from an empty desk the window
-- focused before the clear gets it back.
local function restore(monitors)
    local now = hl.get_active_window()
    local addr = now and now.address or focus
    focus = nil
    for _, m in ipairs(monitors) do
        m:set_workspace(origin(m.active_workspace.name))
    end
    carry_home()
    local w = addr and hl.get_window("address:" .. addr)
    local active = hl.get_active_window()
    if w and w.workspace and w.workspace.visible and not (active and active.address == addr) then
        hl.dispatch(hl.dsp.focus({ window = "address:" .. addr }))
    end
end

function ryce.despejar()
    local monitors, cleared = {}, {}
    for _, m in ipairs(hl.get_monitors()) do
        if not m.is_mirror and m.active_workspace then
            monitors[#monitors + 1] = m
            if origin(m.active_workspace.name) then cleared[#cleared + 1] = m end
        end
    end
    if #cleared > 0 then
        restore(cleared)
    else
        clear(monitors)
        carry_home()
    end
end
