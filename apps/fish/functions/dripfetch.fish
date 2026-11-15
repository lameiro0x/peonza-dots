# dripfetch (AUR) in the theme's colours with the peonza: theme/fetch/fetch.py renders one
# config per theme. It runs a throwaway copy, because dripfetch writes a moved box's
# position back into the file it runs and the theme's file is generated in the repo (so a
# moved box lasts one run). Any argument goes straight to dripfetch: `dripfetch -c 3`,
# `dripfetch --list-logos`.
function dripfetch --wraps dripfetch --description 'dripfetch in the theme colours, with the peonza'
    if not command -q dripfetch
        echo 'dripfetch: no está instalado (paquete del AUR «dripfetch»)' >&2
        return 127
    end
    if set -q argv[1]
        command dripfetch $argv
        return
    end
    set -l state ~/.local/state/ryce/theme
    set -q RYCE_THEME_STATE; and set state $RYCE_THEME_STATE
    set -l src $state/current/dripfetch/config.yaml
    if not test -r $src
        echo "dripfetch: falta la configuración del tema ($src); ejecuta install/deploy.sh" >&2
        return 1
    end
    set -l run (mktemp --suffix=.yaml -t ryce-dripfetch.XXXXXX); or return 1
    cp -- $src $run; and command dripfetch -c $run
    set -l code $status
    rm -f -- $run
    return $code
end
