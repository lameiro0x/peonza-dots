-- ryce-pc · Hyprland 0.57.1. Lua only: 0.57.0 removed hyprland.conf.
--
-- This file only orders the modules next to it. Keybindings come FIRST: if
-- anything after them breaks, the session still has its keys (and Hyprland's
-- emergency mode, which trips only when no bind registered, stays out).
--
-- How a broken module surfaces, and why there are two paths:
--   * an error INSIDE a module (typo, unknown option, nil call) is caught by
--     Hyprland's own require(): it lands in Hyprland's config-error banner and
--     in `Hyprland --verify-config`, and the remaining modules still load;
--   * a MISSING module raises out of require() and would abort this file, so
--     each one loads under pcall and the misses are re-raised at the very end,
--     after everything else registered: same banner, same failed verify.
-- local.lua (gitignored, per-machine: a second monitor) is optional.

local missing = {}

local function use(name, optional)
    local ok, err = pcall(require, name)
    if ok then return end
    -- First line only: the rest is Lua's search-path list, and Hyprland's
    -- error banner shows 15 lines in all.
    local msg = tostring(err):match("^[^\n]*")
    local absent = msg:find("module '" .. name .. "' not found", 1, true) ~= nil
    if not (optional and absent) then
        missing[#missing + 1] = msg
    end
end

use("binds")
use("env")
use("monitors")
use("look")
use("rules")
use("despejar")
use("autostart")
use("local", true)

if #missing > 0 then
    error("ryce: " .. #missing .. " module(s) failed to load:\n" .. table.concat(missing, "\n"), 0)
end
