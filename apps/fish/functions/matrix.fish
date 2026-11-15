# cmatrix in the theme's own green slot (a named ANSI colour, so kitty's palette
# decides: gruvbox olive, Grafito's mint, kanagawa's spring green, Tinta's whisper).
function matrix --description 'lluvia de cmatrix con los colores del tema'
    if not command -q cmatrix
        echo "matrix: falta cmatrix (pkexec pacman -S cmatrix)" >&2
        return 127
    end
    command cmatrix -ab -u 5 -C green $argv
end
