-- Everything long-lived runs as a systemd --user unit under ryce-session.target
-- (waybar, quickshell, wallpaper, hypridle, hyprpolkitagent, agentd, mako), not
-- as a bare exec: a unit is restarted when it dies, an exec is forgotten.
-- The units need this compositor's WAYLAND_DISPLAY and HYPRLAND_INSTANCE_SIGNATURE
-- (the bar's on-click handlers shell out to hyprctl), so hand them over first.
-- greetd never activates graphical-session.target, hence the own target.

local SESSION_VARS = "WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE XDG_CURRENT_DESKTOP"

hl.on("hyprland.start", function()
    -- Only import-environment gates the start: without it the units would run
    -- against a stale or missing WAYLAND_DISPLAY. The D-Bus activation
    -- environment and the reset of units that hit their start limit in an
    -- earlier session are best effort and never keep the session down.
    hl.exec_cmd("systemctl --user import-environment " .. SESSION_VARS
        .. " && { dbus-update-activation-environment --systemd " .. SESSION_VARS .. " || true; }"
        .. " && { systemctl --user reset-failed || true; }"
        .. " && systemctl --user start ryce-session.target")
    -- GTK on Wayland takes theme, icons, cursor and fonts from GSettings, not
    -- from settings.ini; this mirrors one into the other (needs the session bus).
    hl.exec_cmd("sh ~/.local/lib/ryce/gsettings.sh")
end)

-- On logout, stop the session services rather than leave them restarting
-- against a compositor that is gone (units that are PartOf the target).
hl.on("hyprland.shutdown", function()
    hl.exec_cmd("systemctl --user stop ryce-session.target")
end)
