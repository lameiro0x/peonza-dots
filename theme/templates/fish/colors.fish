# fish 4.9 colours, theme «{{theme.name}}». Sourced by conf.d/ryce-theme.fish at start
# and again whenever the universal `ryce_theme` changes. Global scope, so it shadows
# any universal fish_color_* an old `fish_config` left behind.
#
# Every coloured letter in the terminal follows the theme, and none is the old mid
# blue. The command line takes the palette's hues (each theme's own: gruvbox wood,
# Grafito's soft pastels, kanagawa, Tinta's whisper tints); listings, grep, fzf and
# man pages name ANSI slots, so kitty's palette swap recolours them too; git diffs
# go through delta on the theme's diff grounds.

# Command line: commands in the aqua slot, options gold, strings green, keywords
# and pipes violet. Arguments stay the plain text colour.
set -g fish_color_normal {{fg0.hex}}
set -g fish_color_command {{ansi.14.hex}}
set -g fish_color_keyword {{ansi.5.hex}}
set -g fish_color_param {{fg0.hex}}
set -g fish_color_option {{ansi.3.hex}}
set -g fish_color_quote {{ansi.2.hex}}
set -g fish_color_escape {{ansi.13.hex}}
set -g fish_color_redirection {{ansi.13.hex}}
set -g fish_color_operator {{ansi.11.hex}}
set -g fish_color_end {{ansi.5.hex}}
set -g fish_color_comment {{fg2.hex}} --italics
set -g fish_color_error {{err.hex}}
set -g fish_color_valid_path --underline
set -g fish_color_autosuggestion {{fg2.hex}}
set -g fish_color_selection --background={{term.selection_bg.hex}}
set -g fish_color_search_match --background={{term.selection_bg.hex}}
set -g fish_color_history_current {{fg0.hex}} --bold
set -g fish_color_cancel {{fg2.hex}}

set -g fish_pager_color_progress {{fg2.hex}}
set -g fish_pager_color_prefix {{ansi.14.hex}} --bold
set -g fish_pager_color_completion {{fg0.hex}}
set -g fish_pager_color_description {{ansi.3.hex}}
set -g fish_pager_color_selected_background --background={{term.selection_bg.hex}}
set -g fish_pager_color_selected_prefix {{ansi.14.hex}} --bold
set -g fish_pager_color_selected_completion {{term.selection_fg.hex}}
set -g fish_pager_color_selected_description {{ansi.3.hex}}

# ls and lsd names (lsd reads LS_COLORS too). Directories bold in the gold slot,
# never blue; links aqua, executables green, archives red, images and media
# violet, documents bright aqua, plain text uncoloured, leftovers dim.
# Other-writable and sticky directories keep the gold with an underline instead
# of GNU's blue grounds.
set -gx LS_COLORS (string join : \
    'rs=0' 'di=01;33' 'ln=36' 'mh=00' 'pi=33' 'so=35' 'do=35' 'bd=01;33' 'cd=01;33' \
    'or=01;31' 'mi=01;31' 'su=01;31' 'sg=01;31' 'ca=00' 'tw=01;33;4' 'ow=01;33;4' 'st=01;33;4' \
    'ex=01;32' \
    '*.tar=31' '*.tgz=31' '*.gz=31' '*.xz=31' '*.zst=31' '*.bz2=31' '*.zip=31' '*.7z=31' '*.rar=31' \
    '*.deb=31' '*.rpm=31' '*.pkg.tar.zst=31' '*.iso=31' '*.img=31' '*.qcow2=31' \
    '*.png=35' '*.jpg=35' '*.jpeg=35' '*.gif=35' '*.webp=35' '*.svg=35' '*.avif=35' '*.ico=35' \
    '*.mp4=95' '*.mkv=95' '*.webm=95' '*.mov=95' '*.mp3=95' '*.flac=95' '*.ogg=95' '*.opus=95' '*.wav=95' \
    '*.pdf=96' '*.epub=96' '*.odt=96' '*.docx=96' '*.xlsx=96' \
    '*~=90' '*.bak=90' '*.swp=90' '*.tmp=90' '*.log=90' '*.lock=90' '*.pyc=90')

# grep: matches bold gold, file names violet, line numbers green, separators dim.
set -gx GREP_COLORS 'ms=01;33:mc=01;33:sl=:cx=:fn=35:ln=32:bn=32:se=90'

# fzf: base 16 makes every slot not named here a palette colour, never Dark256's
# blues; the current line sits on the theme's selection ground.
set -gx FZF_DEFAULT_OPTS "--color=16,fg:-1,bg:-1,hl:3,fg+:15,bg+:{{term.selection_bg}},hl+:11,gutter:-1,info:8,border:8,separator:8,scrollbar:8,label:7,prompt:14,query:15,pointer:3,marker:2,spinner:5,header:6"

# man pages: bold (headings, options) in gold, underlined (arguments) aqua. groff
# keeps the old overstrike so less can colour it.
set -gx MANROFFOPT -c
set -gx MANPAGER 'less -R --use-color -Dd+y -Du+c'

# git diff, log -p, show: delta on the theme's diff grounds, syntax in the ANSI
# palette (BAT_THEME=ansi), file names in the gold slot, hunks by line number.
if command -q delta
    set -gx GIT_PAGER "delta --plus-style='syntax {{term.diff_add}}' --minus-style='syntax {{term.diff_del}}' --plus-emph-style='syntax {{term.diff_add_word}}' --minus-emph-style='syntax {{term.diff_del_word}}' --file-style='bold yellow' --file-decoration-style='{{line}} ul' --hunk-header-style='line-number syntax' --hunk-header-decoration-style='{{line}} ul' --hunk-header-line-number-style=green --line-numbers --line-numbers-minus-style=red --line-numbers-plus-style=green --line-numbers-zero-style='{{fg2}}' --line-numbers-left-style='{{line}}' --line-numbers-right-style='{{line}}'"
end
