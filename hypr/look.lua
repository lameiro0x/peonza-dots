-- Marco: quiet frames on near-monochrome greys. Everything that makes a theme
-- (colours, gaps, radii, blur, motion) comes from palette.lua, generated per
-- theme by tools/tokens.py from contracts/themes/<id>.json; nothing is typed
-- here. No glow anywhere: an AI session that waits for you is told by a solid
-- border (rules.lua, `agentwait`), never by a halo.
--
-- palette.lua is a link through ~/.local/state/ryce/theme/current. A missing
-- link must not cost the session its look, so this falls back to Origen's file
-- in the theme state, then to a built-in grey table, and registers whatever it
-- found as the `palette` module for rules.lua.

local function builtin()
    local B = {
        hex      = { bg0 = "0a0a0a", line = "2a2a2a", fg0 = "e6e6e6", fg1 = "a8a8a8" },
        geometry = { gaps_in = 5, gaps_out = 10, border = 1, rounding = 2, rounding_power = 2 },
        blur     = { enabled = false, size = 4, passes = 1, brightness = 1 },
        motion   = { curves = {}, leaves = {} },
    }
    -- No theme's signal colour here: the waiting border falls back to plain white.
    B.hex.signal = B.hex.fg0
    for k, v in pairs(B.hex) do B[k] = "rgb(" .. v .. ")" end
    function B.rgba(name, a)
        return string.format("rgba(%s%02x)", B.hex[name], math.floor(a * 255 + 0.5))
    end
    return B
end

local function load_palette()
    local ok, P = pcall(require, "palette")
    if ok then return P end
    local state = os.getenv("RYCE_THEME_STATE") or ((os.getenv("HOME") or "") .. "/.local/state/ryce/theme")
    ok, P = pcall(dofile, state .. "/origen/hypr/palette.lua")
    if ok and type(P) == "table" then return P end
    return builtin()
end

local P = load_palette()
package.loaded["palette"] = P
local G = P.geometry

hl.config({
    general = {
        gaps_in     = G.gaps_in,
        gaps_out    = G.gaps_out,
        border_size = G.border,
        col = {
            -- Barely there (the user, 2026-11-15): a faint hairline on the focused
            -- window, the theme's line at a fifth on the rest, which the gap
            -- already separates. The one loud border is `agentwait` (rules.lua).
            active_border   = P.rgba("fg1", 0.22),
            inactive_border = P.rgba("line", 0.2),
        },
        layout           = "dwindle",
        resize_on_border = true,
    },

    decoration = {
        rounding       = G.rounding,
        rounding_power = G.rounding_power,   -- 2 = circle; Ola's 3 squares its few px off

        -- Opaque windows: an inactive_opacity below 1 would put blur behind
        -- every unfocused window, a pass per frame the iGPU does not need.
        active_opacity   = 1.0,
        inactive_opacity = 1.0,
        -- File dialogs tile beside their parent (rules.lua): dimming the parent
        -- would grey out the very window the dialog belongs to.
        dim_modal = false,

        shadow = {
            enabled      = true,
            range        = 8,
            render_power = 2,
            -- In bg0 a shadow vanishes on a paper theme: ink there (P.scheme, tokens.py).
            color        = P.scheme == "light" and P.rgba("fg0", 0.14) or P.rgba("bg0", 0.4),
        },

        -- Blur sits behind every translucent surface: kitty's glass and the
        -- layers enabled in rules.lua. xray blurs only the wallpaper under them
        -- instead of re-blurring windows each frame: cheap on Xe graphics.
        -- Small and few passes, so the picture still reads through the glass
        -- (7 x 3 had turned it into a flat haze); brightness smokes it, the
        -- darkening the terminal's text floor is measured under
        -- (theme/tests/test_terminal.py). vibrancy 0 keeps the greys grey. No
        -- window rule may set no_blur.
        blur = {
            enabled           = P.blur.enabled,
            size              = P.blur.size,
            passes            = P.blur.passes,
            brightness        = P.blur.brightness,
            xray              = true,
            vibrancy          = 0,
            new_optimizations = true,
        },
    },

    animations = {
        -- No workspace_wraparound: ryce.ws_step stops at a screen's first and
        -- last workspace, so every step slides the plain way, by number.
        enabled = true,
    },

    dwindle = {
        preserve_split = true,
    },

    misc = {
        force_default_wallpaper  = 0,
        disable_hyprland_logo    = true,
        disable_splash_rendering = true,
        -- What shows before the wallpaper paints, and behind it on a switch.
        background_color         = P.bg0,
    },

    input = {
        -- US English; a second layout goes in the gitignored hypr/local.lua, e.g.
        -- hl.config({ input = { kb_layout = "us,es" } }) (Alt+Shift switches)
        kb_layout    = "us",
        kb_options   = "ctrl:nocaps,grp:alt_shift_toggle",
        follow_mouse = 1,
        sensitivity  = 0,
    },
})

-- Motion is the theme's personality: Origen decelerates like film, Grafito
-- snaps, Ola springs. Sorted so the config reads the same on every load.
local function sorted_keys(t)
    local keys = {}
    for k in pairs(t) do keys[#keys + 1] = k end
    table.sort(keys)
    return keys
end

local curves = P.motion.curves
for _, name in ipairs(sorted_keys(curves)) do
    hl.curve(name, curves[name])
end

for _, leaf in ipairs(sorted_keys(P.motion.leaves)) do
    local l = P.motion.leaves[leaf]
    local spec = { leaf = leaf, enabled = true, speed = l.speed, style = l.style }
    -- Springs and beziers are referenced by different keys.
    local kind = curves[l.curve] and curves[l.curve].type == "spring" and "spring" or "bezier"
    spec[kind] = l.curve
    hl.animation(spec)
end
