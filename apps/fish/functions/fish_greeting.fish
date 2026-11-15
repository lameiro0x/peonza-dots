# Every new kitty shell opens on the theme's peonza, four lines tall: it spins down for
# 1.3 s while a ring closes round it, then holds still beside «buenas tardes» and the
# date. The picture is a ready-made stream of kitty graphics escapes per theme
# (theme/greet/greet.py): fish only prints it, and kitty plays it once and stops, so
# nothing keeps running afterwards. `fastfetch` still shows the full card on demand.
#
# Only where kitty itself reads the escapes: TERM and KITTY_WINDOW_ID together (another
# terminal started from kitty inherits the id, not the TERM), not over ssh, not inside
# tmux, not when the output is not a terminal, and not in a window under 40 columns or
# 12 lines (a split, a quick panel). 40 columns hold the picture's 11, two blank and the
# longest date, «miércoles 30 de septiembre». Anywhere else the shell starts silent.
#
# Off: `set -U ryce_greet off` (every shell, kept), or `set -gx ryce_greet off` before
# starting one (that shell and its children). `set -e ryce_greet` brings it back.
function fish_greeting --description 'the peonza spins once beside a short hello'
    test "$ryce_greet" = off; and return
    test "$TERM" = xterm-kitty; and set -q KITTY_WINDOW_ID; or return
    set -q SSH_TTY; or set -q SSH_CONNECTION; or set -q TMUX; and return
    isatty stdout; and test $COLUMNS -ge 40 -a $LINES -ge 12; or return
    set -l state ~/.local/state/ryce/theme
    set -q RYCE_THEME_STATE; and set state $RYCE_THEME_STATE
    set -l art $state/current/greet/peonza.kitty
    test -r $art; or return

    # One fork for the clock: hour, weekday (1 = lunes), day, month.
    set -l now (date '+%-H %u %-d %-m' | string split ' ')
    set -l hello 'buenas noches'
    if test $now[1] -ge 6 -a $now[1] -lt 14
        set hello 'buenos días'
    else if test $now[1] -ge 14 -a $now[1] -lt 21
        set hello 'buenas tardes'
    end
    set -l days lunes martes miércoles jueves viernes sábado domingo
    set -l months enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre
    set -l date "$days[$now[2]] $now[3] de $months[$now[4]]"

    # The date in the theme's fg2, which its colors.fish gives the autosuggestions.
    set -l dim brblack
    set -q fish_color_autosuggestion[1]; and set dim $fish_color_autosuggestion

    # Four newlines make room even at the bottom of the screen; back up to the first of
    # them and place the picture there, under the prompt's left edge. It leaves the
    # cursor where it was (C=1), the text goes on the middle two lines from column 14,
    # and the prompt starts below.
    printf '\n\n\n\n\e[4A'
    command cat $art
    printf '\e[B\e[14G%s\e[B\e[14G%s%s%s\e[B\n' $hello (set_color $dim) $date (set_color normal)
end
