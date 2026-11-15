# neofetch (AUR, 7.1.0: upstream is archived) in the theme's colours, with the peonza
# beside the same groups as fastfetch: theme/templates/neofetch/config.conf, rendered per
# theme. The config picks the peonza that fits the window (a picture in kitty, sextants
# elsewhere, none when narrow) and centres it on the text.
# Any argument goes after the theme's config and wins: `neofetch --off`.
function neofetch --wraps neofetch --description 'neofetch in the theme colours, with the peonza'
    if not command -q neofetch
        echo 'neofetch: no está instalado (paquete del AUR «neofetch»: install/packages/apps.txt)' >&2
        return 127
    end
    set -l state ~/.local/state/ryce/theme
    set -q RYCE_THEME_STATE; and set state $RYCE_THEME_STATE
    set -l conf $state/current/neofetch/config.conf
    if not test -r $conf
        echo "neofetch: falta la configuración del tema ($conf); ejecuta install/deploy.sh" >&2
        return 1
    end
    command neofetch --config $conf $argv
end
