-- Window and layer rules. Rules are applied top to bottom and the LAST match
-- wins, so the `agentwait` rule stays at the very end of this file — and
-- local.lua, which loads after it, must not add window rules.

-- look.lua loads first and registers the palette, or its fallback, as this
-- module.
local P = require("palette")

-----------------
---- WINDOWS ----
-----------------

hl.window_rule({
    name           = "suppress-maximize",
    match          = { class = ".*" },
    suppress_event = "maximize",
})

hl.window_rule({
    name  = "fix-xwayland-drags",
    match = {
        class      = "^$",
        title      = "^$",
        xwayland   = true,
        float      = true,
        fullscreen = false,
        pin        = false,
    },
    no_focus = true,
})

-- File dialogs tile beside the window that opened them instead of floating
-- over it (the user's choice, 2026-11-09). Tiled is the default, so a title
-- that matches by accident costs nothing. Placed before the floating rules
-- below so those still win for their own windows.
-- The portal's file chooser (every GTK/Qt/Electron app that goes through
-- xdg-desktop-portal); its title is whatever the calling app asked for.
hl.window_rule({
    name  = "file-dialogs-portal",
    match = { class = "^xdg-desktop-portal-gtk$" },
    tile  = true,
})

-- In-process choosers, Spanish and English: «Abrir archivo», «Guardar como»,
-- «Seleccionar carpeta», «Subir archivo», «Open Files», «Save As»…
hl.window_rule({
    name  = "file-dialogs-title",
    match = { title = "^(Abrir|Guardar|Seleccionar|Elegir|Subir archivos?|Open|Save|Select an? (File|Folder)|Choose Files?|File Upload)( .*)?$" },
    tile  = true,
})

-- Any other modal dialog: beside its parent, never on top of it.
hl.window_rule({
    name  = "modal-dialogs",
    match = { modal = true },
    tile  = true,
})

hl.window_rule({
    name   = "pavucontrol",
    match  = { class = "^org\\.pulseaudio\\.pavucontrol$" },
    float  = true,
    size   = { 880, 560 },
    center = true,
})

-- Firefox and Chromium name the window before it maps; static rules see that
-- initial title.
hl.window_rule({
    name              = "picture-in-picture",
    match             = { title = "^Picture[- ]in[- ][Pp]icture$" },
    float             = true,
    pin               = true,
    keep_aspect_ratio = true,
    size              = { 480, 270 },
    move              = { "monitor_w - window_w - 24", "monitor_h - window_h - 24" },
})

hl.window_rule({
    name       = "polkit",
    match      = { class = "^hyprpolkitagent$" },
    float      = true,
    center     = true,
    dim_around = true,
})

-- Feishin, the music player (apps/feishin): glass at the panels' alpha, since
-- Electron cannot make its window translucent by itself. The whole window takes
-- it, text and covers too, hence the panels' value and not the terminal's:
-- Grafito stays opaque (its panels are), Papel barely turns. The blur behind is
-- the decoration's, as for any translucent window. look.lua's fallback palette
-- has no alpha block: opaque then.
local feishin_alpha = (P.alpha and P.alpha.panel) or 1
hl.window_rule({
    name    = "feishin-glass",
    match   = { class = "^feishin$" },
    opacity = string.format("%.2f %.2f", feishin_alpha, feishin_alpha),
})

-- agentd adds the static tag `agentwait` (hl.dsp.window.tag) to a window whose
-- AI session waits for you, and removes it when it stops waiting. Dynamic
-- effects are re-evaluated on the tag change. The theme's signal colour, solid:
-- the one place a window border speaks it. Keep this rule LAST.
hl.window_rule({
    name         = "agentwait",
    match        = { tag = "agentwait" },
    border_color = P.signal,
})

----------------
---- LAYERS ----
----------------

-- Quickshell slides its own drawers out of the frame: Hyprland animating the
-- same surface on top would double the motion.
hl.layer_rule({ name = "qs-no-anim", match = { namespace = "^qs-" }, no_anim = true })

-- Hyprland animates the rest, in the theme's layersIn/layersOut timing.
hl.layer_rule({ name = "anim-waybar", match = { namespace = "^waybar$" },        animation = "slide top" })
-- The launcher enters the way the theme's layers do (Origen pops, Grafito and Ola
-- drop from the top, Tinta fades).
hl.layer_rule({ name = "anim-rofi",   match = { namespace = "^rofi$" },
                animation = (P.motion.leaves.layersIn and P.motion.leaves.layersIn.style) or "popin 92%" })
-- mako's layer namespace is "notifications".
hl.layer_rule({ name = "anim-mako",   match = { namespace = "^notifications$" }, animation = "slide right" })

-- Translucent surfaces get the (xray) blur when the theme has blur at all.
-- ignore_alpha keeps it off fully transparent pixels: rounded corners, shadows,
-- gaps. Not the frame: blur behind a screen-wide layer is a pass every frame.
-- Never a bar (qs-bar, nor the Waybar fallback): it floats as plates over the
-- sharp wallpaper, and a blur under them would bring back the veiled band it
-- replaced. SwayOSD's
-- namespace is "swayosd" (osd_window.rs, v0.3.2). A theme with blur.desk = false (Tinta)
-- keeps its desk cards on the sharp picture: its glass shows the sheet through the black.
if P.blur.enabled then
    for _, r in ipairs({
        { "blur-quickshell", P.blur.desk == false and "^qs-osd$" or "^qs-(osd|desk)$" },
        { "blur-rofi",       "^rofi$" },
        { "blur-mako",       "^notifications$" },
        { "blur-swayosd",    "^swayosd$" },
    }) do
        hl.layer_rule({ name = r[1], match = { namespace = r[2] }, blur = true, ignore_alpha = 0.2 })
    end
end
