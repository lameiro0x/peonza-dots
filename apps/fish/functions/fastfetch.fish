# The logo is the theme's peonza spinning: an animated WebP sent with the kitty protocol
# (theme/fetch/fetch.py), which fastfetch decodes with ImageMagick 7 and kitty plays.
# Without ImageMagick a local kitty still draws the still PNG itself (kitty-direct).
# Anywhere else (the TTY, ssh, tmux) those escapes would print as text: the half-block
# peonza instead, and in the TTY no Nerd Font icons and a bar the console font has.
#
# The config fits 88 columns with the logo beside the text (half a 1920 px kitty). Below
# that the logo goes above the text, smaller; below 52 the keys shrink to their icons,
# and the half-block peonza, which cannot shrink, is left out below 34. A line that still
# does not fit is cut at the edge (disableLinewrap), never wrapped under the logo.
function fastfetch --wraps fastfetch --description 'fastfetch with the peonza logo'
    set -l state ~/.local/state/ryce/theme
    set -q RYCE_THEME_STATE; and set state $RYCE_THEME_STATE
    set -l here $state/current
    # The theme's own config, as the logo: both follow RYCE_THEME_STATE (the stage's).
    set -l fit --config $here/fastfetch/config.jsonc
    if test $COLUMNS -lt 88
        set -a fit --logo-position top --logo-padding-top 1 --logo-padding-left 0
        test $COLUMNS -lt 52; and set -a fit --key-type icon --key-width 4
    end
    if test "$TERM" = xterm-kitty; and not set -q SSH_TTY; and not set -q TMUX
        # Square boxes at kitty's 10 x 26 px cell, like the config's 31 x 12.
        if test $COLUMNS -lt 52
            set -a fit --logo-width 16 --logo-height 6
        else if test $COLUMNS -lt 88
            set -a fit --logo-width 20 --logo-height 8
        end
        if command -q magick
            command fastfetch $fit --logo $here/fastfetch/peonza.webp $argv
        else
            command fastfetch $fit --logo-type kitty-direct --logo $here/peonza/logo.png $argv
        end
        return
    end
    set -l logo --logo-type file --logo $here/fastfetch/peonza.txt
    test $COLUMNS -lt 34; and set logo --logo-type none
    if test "$TERM" = linux
        command fastfetch $fit $logo \
            --key-type string --bar-char-elapsed █ --bar-char-total ░ $argv
    else
        command fastfetch $fit $logo $argv
    end
end
