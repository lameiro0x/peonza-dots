# fish: starship prompt, zoxide jumps, lsd/bat instead of ls/cat.
set -g fish_greeting

fish_add_path ~/.local/bin

# bat follows the terminal's 16 ANSI colours (the palette in kitty.conf).
set -gx BAT_THEME ansi

if status is-interactive
    starship init fish | source
    # Once a command runs, its two-line frame collapses to "<time> <peonza>  command"
    # (fish >= 4.1's transient prompt): scrollback reads as a log, and no
    # $COLUMNS-wide rule is left for kitty to rewrap into stray lines when Hyprland
    # resizes the window. The blank line keeps starship's add_newline gap.
    function starship_transient_prompt_func
        echo
        starship module time $argv
        echo -n ' '
        # Always the success colour: at this point the peonza would carry the PREVIOUS
        # command's status, and a red top beside a command that worked reads as its failure.
        starship module character --status=0
    end
    enable_transience
    zoxide init fish | source

    alias cat 'bat'
    alias ls 'lsd'
    alias ll 'lsd -la'
    alias la 'lsd -a'
    alias l 'lsd'
end
