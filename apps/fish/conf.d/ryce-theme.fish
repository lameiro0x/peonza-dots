# Syntax colours follow the desktop theme. bin/ryce-theme swaps the theme state
# link, then sets the universal `ryce_theme`: every running fish gets the change
# event, re-reads the colours and repaints its prompt, which starship then draws from
# the new theme's config (its 24-bit colours would otherwise wait for the next
# command); a new fish reads them here.
status is-interactive; or return

function _ryce_theme_apply --on-variable ryce_theme
    set -l state $HOME/.local/state/ryce/theme
    set -q RYCE_THEME_STATE; and set state $RYCE_THEME_STATE
    set -l colors $state/current/fish/colors.fish
    test -r $colors; and source $colors
    # Only from the event (argv: VARIABLE SET ryce_theme): at startup no prompt exists yet.
    set -q argv[1]; and commandline -f repaint
end

_ryce_theme_apply
