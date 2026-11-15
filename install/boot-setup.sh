#!/usr/bin/env bash
# The boot chain: a short GRUB menu on its own art, the peonza spinning in Plymouth in the
# chosen theme (the LUKS passphrase is asked inside it), and the login after it (ryce's page,
# regreet if it cannot show, tuigreet last; install/boot/ryce-greeter). GRUB and the login look
# the same whatever the desktop theme. Run as root with the user at the machine; every step
# looks before it acts, so a second run changes nothing.
#
#   pkexec bash install/boot-setup.sh --theme ID [--only PART]... [--dry-run]
#   pkexec bash install/boot-setup.sh --only grub|greeter [--dry-run]
#   pkexec bash install/boot-setup.sh --rollback [--dry-run]
#
#   --theme ID   origen, grafito, ola, tinta or papel (themes/ID as rendered by theme/render.py): what
#                Plymouth wears. GRUB and the login ignore it: only plymouth needs it.
#   --only PART  plymouth, grub or greeter; repeatable (default: the three)
#   --dry-run    print every action, change nothing (works without root)
#   --rollback   put back the latest backup set of /var/backups/ryce and rebuild what uses it
#   --root DIR   tests only: prefix every system path with DIR (commands still run: fake them
#                first on PATH, as install/tests/test_boot_setup.py does)
#
# The GRUB menu: four entries (linux, linux-lts, the snapshots, the firmware settings), set in
# /etc/default/grub.d/ryce.cfg, which grub-mkconfig reads after /etc/default/grub; memtest86+
# has no knob, so its script loses the execute bit. The art is theme/boot/grub (built by
# theme/boot/grub.py) plus fonts made here by grub-mkfont.
#
# Safety, in order. (1) The LTS kernel gets its own initramfs, from a copy of today's
# mkinitcpio.conf without plymouth, built BEFORE anything else changes: the linux-lts entry
# always boots the way it did. (2) A snapper snapshot of / before the first change of a run.
# (3) Every file or folder replaced (or file mode changed) is recorded first in
# /var/backups/ryce/<time>/ with a manifest; --rollback restores the latest set exactly.
# (4) A failed initramfs or grub.cfg rebuild puts the previous config back and rebuilds before
# exiting with an error. By hand, at the GRUB menu: `e` on the entry, add plymouth.enable=0 at
# the end of the `linux` line, Ctrl+X; or boot the linux-lts entry.
# greetd is never restarted here (that would end the running session): the greeter changes
# show at the next logout or boot.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)   # physical: stage.py wants it
REPO=$(dirname "$HERE")
EDIT=(python3 -I "$HERE/boot/edit.py")
STAGE=(python3 -I "$HERE/boot/stage.py" "$REPO")
IMAGES=(python3 -I "$HERE/boot/images.py")
MANAGED="# Managed by ryce-pc (install/boot-setup.sh): change it in the repo and re-run."
FRAMES=72   # contracts/constants.json peonza_assets.plymouth_frames

LTS_CONF=/etc/mkinitcpio-lts.conf
LTS_PRESET=/etc/mkinitcpio.d/linux-lts.preset
PLY_DIR=/usr/share/plymouth/themes/ryce
FONT_DIR=/usr/local/share/fonts/ryce
GRUB_DIR=/boot/grub/themes/ryce
GRUB_CFG=/boot/grub/grub.cfg
GRUB_DROPIN=/etc/default/grub.d/ryce.cfg
MEMTEST=/etc/grub.d/60_memtest86+-efi
GRUB_ART=$REPO/theme/boot/grub
# The menu's face: Martian Mono, the peonza brand's typeface (static, so its hinting holds up
# in GRUB's one-bit glyphs). theme.txt names the sizes it uses as "Ryce Regular N".
GRUB_FACE=$REPO/assets/fonts/MartianMono-Regular.ttf
# The login: the wrapper, the page with its background (quickshell/greeter and
# theme/boot/greeter, built by theme/boot/greeter.py), regreet's background and config
# (install/boot/greeter) and the mask that hides the uwsm session. install/system-setup.sh
# installs the same files. An old theme spool in /var/lib/ryce/greeter (greeter-sync, retired
# 2026-11-14) is no longer read and is left alone.
GREETER_BIN=/usr/local/bin/ryce-greeter
GREETER_QML=/usr/local/share/ryce/greeter
GREETER_SHARE=/usr/share/ryce/greeter
GREETER_ART=$REPO/theme/boot/greeter/background.jpg
GREETER_ETC=$HERE/boot/greeter
UWSM_MASK=/usr/local/share/wayland-sessions/hyprland-uwsm.desktop
# The peonza cursor (theme/cursor/build.py), XCursor half only: cage, regreet and the page read
# it as the greeter user, who cannot read ~/.local/share/icons; libXcursor looks in
# /usr/share/icons, not /usr/local. Every alias is a plain copy (stage.py refuses links).
CURSOR_SRC=assets/cursors/ryce-peonza
CURSOR_DIR=/usr/share/icons/ryce-peonza
# Everything this script may replace; --rollback refuses a manifest naming anything else.
TARGETS=(/etc/mkinitcpio.conf "$LTS_CONF" "$LTS_PRESET" /etc/plymouth/plymouthd.conf "$PLY_DIR"
  "$FONT_DIR" /etc/default/grub "$GRUB_DROPIN" "$MEMTEST" "$GRUB_DIR" "$GREETER_BIN" "$GREETER_QML"
  "$GREETER_SHARE" "$CURSOR_DIR" /etc/greetd/regreet.toml /etc/greetd/regreet.css /etc/greetd/config.toml
  "$UWSM_MASK")
# What goes into the main initramfs (the plymouth hook copies the theme and its font).
INITRAMFS_INPUTS=(/etc/mkinitcpio.conf /etc/plymouth/plymouthd.conf "$PLY_DIR" "$FONT_DIR")
# The glyphs the GRUB fonts carry: Latin-1 and Latin Extended-A (Spanish), punctuation, arrows.
GRUB_RANGE=0x20-0x7E,0xA0-0x17F,0x2000-0x206F,0x2190-0x21FF

ARGS=("$@")
THEME='' DRY=0 ROLLBACK=0 ROOT=''
PARTS=()
CHANGES=0
WARNINGS=()
SET=''        # this run's backup set, opened at the first change
GRUB_DIRTY=0
FONTS_DONE=0 FONTS_CHANGED=0

die()  { printf '\nboot-setup.sh: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }
ok()   { printf '    ✓ %s\n' "$*"; }
warn() { WARNINGS+=("$*"); printf '    ! %s\n' "$*"; }
change() {
  CHANGES=$((CHANGES + 1))
  if [ "$DRY" = 1 ]; then printf '    + [simulación] %s\n' "$*"; else printf '    + %s\n' "$*"; fi
}
usage() { sed -n '2,18s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; }
want() { [[ " ${PARTS[*]} " == *" $1 "* ]]; }

while [ $# -gt 0 ]; do
  case $1 in
    --theme) [ $# -ge 2 ] || die "--theme necesita un nombre (origen, grafito, ola, tinta o papel)"; THEME=$2; shift ;;
    --only)
      [ $# -ge 2 ] || die "--only necesita plymouth, grub o greeter"
      case $2 in plymouth|grub|greeter) PARTS+=("$2") ;; *) die "--only $2: usa plymouth, grub o greeter" ;; esac
      shift ;;
    --dry-run) DRY=1 ;;
    --rollback) ROLLBACK=1 ;;
    --root) [ $# -ge 2 ] || die "--root necesita una carpeta"; ROOT=${2%/}; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "opción desconocida: $1 (usa --help)" ;;
  esac
  shift
done
if [ "$ROLLBACK" = 1 ]; then
  [ -z "$THEME" ] && [ ${#PARTS[@]} = 0 ] \
    || die "--rollback no admite --theme ni --only: restaura el último juego de copias completo"
else
  [ ${#PARTS[@]} -gt 0 ] || PARTS=(plymouth grub greeter)
  if [ -n "$THEME" ]; then
    [[ $THEME =~ ^[a-z][a-z0-9-]*$ ]] && [ -f "$REPO/themes/$THEME/theme.json" ] \
      || die "no conozco el tema '$THEME': mira themes/ (y ejecuta python3 theme/render.py)"
  elif want plymouth; then
    die "falta --theme (origen, grafito, ola, tinta o papel) para Plymouth; sin tema: --only grub o --only greeter"
  fi
fi

# Only the main checkout, whose folders the agents' sandbox cannot write (docs/seguridad.md §1):
# a git worktree under .worktrees/ is writable from the sandbox, and this script runs as root.
# A --root dry tree (the tests) may come from anywhere. Decided without running git as root
# (git refuses a repo owned by another user and would fail open): the main checkout has a
# .git folder, a worktree a .git file.
if [ -z "$ROOT" ] && { [ ! -d "$REPO/.git" ] || [ -L "$REPO/.git" ]; }; then
  die "$REPO no es el checkout principal de git (¿un worktree?): ejecútalo desde la carpeta que creó git clone"
fi

TMP=$(mktemp -d "${TMPDIR:-/tmp}/ryce-boot.XXXXXX")
trap 'rm -rf "$TMP"' EXIT

# Who owns what this script installs: root (a --root test tree: whoever runs the tests).
# Nothing it puts outside /boot may belong to the user or be writable by others: a wrapper
# the user could rewrite would see the next login's password.
if [ -n "$ROOT" ]; then ME=$(id -u):$(id -g); else ME=0:0; fi

# Root copies files out of the user's repo, parts of which the agents' sandbox can write: a
# link planted there (to /etc/shadow, /root…), even swapped in mid-copy, would be read and
# published. Every repo input reaches root's $TMP through install/boot/stage.py (no link on
# the way, regular files with one name, read with the repo owner's rights); only that copy is
# installed, and install_path checks it once more.
from_repo() {  # from_repo DEST SPEC...: see install/boot/stage.py
  "${STAGE[@]}" "$@" || die "no copio nada del repo (mensaje arriba): nada se ha tocado por ello"
}
no_links() {  # no_links PATH...: only plain files and folders (no links, FIFOs, sockets)
  local found
  found=$(find "$@" ! -type f ! -type d -print -quit 2>/dev/null) || true
  [ -z "$found" ] || die "$found no es un fichero normal (¿un enlace?): como root no lo copio (quítalo y repite)"
}

# --- copies and backups ---------------------------------------------------------------------
# /boot is vfat: modes and owners cannot be set there, so copies into it carry content only.
copy() {  # copy SRC DST REL
  case $3 in
    /boot/*) cp -R "$1" "$2" ;;
    *) cp -a "$1" "$2" ;;
  esac
}

same() { [ -e "$2" ] && if [ -d "$1" ]; then diff -rq "$1" "$2" >/dev/null 2>&1; else cmp -s "$1" "$2"; fi; }

# owned PATH MODE: PATH (and everything under it) belongs to $ME and no one else may write it;
# a file must also have exactly MODE (0755…). MODE "-" (vfat /boot): owners do not exist there.
owned() {
  [ "$2" = - ] && return 0
  find "$1" -exec stat -c '%u:%g %a %n' {} + 2>/dev/null | awk -v me="$ME" -v want="${2#0}" -v file="$([ -d "$1" ] || echo 1)" '
    { g = substr($2, length($2) - 1, 1); o = substr($2, length($2), 1) }
    $1 != me || g ~ /[2367]/ || o ~ /[2367]/ || (file && $2 != want) { bad = 1 }
    END { exit bad || NR == 0 }'
}

snapshot() {
  if ! command -v snapper >/dev/null || [ ! -f "$ROOT/etc/snapper/configs/root" ]; then
    warn "sin snapper (o sin su configuración root): no hay instantánea previa, solo las copias"
  elif snapper -c root create -d 'antes de ryce boot'; then
    ok "instantánea de snapper «antes de ryce boot»"
  else
    warn "snapper no pudo hacer la instantánea; sigo con las copias de /var/backups/ryce"
  fi
}

open_set() {
  [ -z "$SET" ] || return 0
  local base=$ROOT/var/backups/ryce stamp n=1
  stamp=$(date +%Y%m%d-%H%M%S)
  SET=$base/$stamp
  while [ -e "$SET" ] || [ -e "$SET.restored" ]; do n=$((n + 1)); SET=$base/$stamp-$n; done
  mkdir -p "$SET/files"
  chmod 700 "$base" "$SET"
  printf '# ryce boot-setup %s: tema %s, partes %s\n' "$stamp" "${THEME:--}" "${PARTS[*]}" > "$SET/manifest"
  ok "copias de esta pasada en ${SET#"$ROOT"}"
  snapshot
}

in_set() { awk -F'\t' -v r="$1" '$2 == r { f = 1 } END { exit !f }' "$2/manifest"; }

backup() {  # backup REL: once per run, before REL is first replaced
  local rel=$1
  open_set
  in_set "$rel" "$SET" && return 0
  # Every step checked by hand: callers run this under `install_path … || dirty=1`, where
  # bash switches errexit off, and a backup that silently failed would let the live file
  # be replaced (and a later rollback delete it).
  if [ -e "$ROOT$rel" ]; then
    mkdir -p "$SET/files$(dirname "$rel")" || die "no pude preparar la copia de $rel: no toco nada"
    cp -a "$ROOT$rel" "$SET/files$rel" || die "no pude copiar $rel a la copia de seguridad: no toco nada"
    printf 'saved\t%s\n' "$rel" >> "$SET/manifest" || die "no pude escribir el manifiesto de la copia: no toco nada"
  else
    printf 'absent\t%s\n' "$rel" >> "$SET/manifest"
  fi
}

backup_mode() {  # backup_mode REL: REL's permission bits, once per run, before its first chmod
  local rel=$1 mode
  open_set
  in_set "$rel" "$SET" && return 0
  mode=$(stat -c %a "$ROOT$rel") || die "no pude leer el modo de $rel: no toco nada"
  printf 'mode\t%s\t%s\n' "$rel" "$mode" >> "$SET/manifest" || die "no pude escribir el manifiesto de la copia: no toco nada"
}

restore() {  # restore REL SET: put REL back as SET found it; 1 if SET never touched it
  local rel=$1 set=$2 kind mode
  kind=$(awk -F'\t' -v r="$rel" '$2 == r { print $1 "\t" $3; exit }' "$set/manifest")
  mode=${kind#*$'\t'} kind=${kind%%$'\t'*}
  case $kind in
    mode)
      # Only the bits were changed: a file that went since (its package removed) stays gone.
      [ ! -e "$ROOT$rel" ] || chmod "$mode" "$ROOT$rel" || die "no pude devolver el modo $mode a $rel: hazlo a mano (chmod $mode $rel)"
      ;;
    saved)
      # Never delete the live file unless its copy is really there.
      [ -e "$set/files$rel" ] || { warn "falta la copia de $rel en ${set#"$ROOT"}: lo dejo como está"; return 2; }
      rm -rf "$ROOT$rel"; mkdir -p "$(dirname "$ROOT$rel")"
      copy "$set/files$rel" "$ROOT$rel" "$rel" || die "no pude restaurar $rel desde ${set#"$ROOT"}/files: hazlo a mano"
      # The copy keeps the content and mode it had; its owner is root's again whatever it was.
      case $rel in /boot/*) ;; *) chown -R "$ME" "$ROOT$rel" || die "no pude devolver $rel a root (chown -R root:root $rel)" ;; esac
      ;;
    absent) rm -rf "$ROOT$rel" ;;
    *) return 1 ;;
  esac
}

# install_path REL SRC MODE: SRC (a file or a folder) becomes REL unless they are identical;
# REL is backed up first. MODE: the file mode; folders get u=rwX,go=rX (the greeter user reads
# them); "-" sets nothing (vfat /boot). Returns 1 when it changed something (also in a dry
# run), so `install_path … || dirty=1`, as system-setup.sh's put_file.
install_path() {
  local rel=$1 src=$2 mode=$3 path=$ROOT$1
  no_links "$src"
  if ! same "$src" "$path"; then
    if [ -e "$path" ]; then change "$rel"; else change "$rel (nuevo)"; fi
  elif owned "$path" "$mode"; then
    ok "$rel"; return 0
  else
    change "$rel: de root y con su modo (el contenido ya estaba)"
  fi
  [ "$DRY" = 1 ] && return 1
  backup "$rel"
  mkdir -p "$(dirname "$path")"
  rm -rf "$path.ryce-new"
  copy "$src" "$path.ryce-new" "$rel" || die "no pude preparar $rel: el original sigue intacto"
  if [ "$mode" != - ]; then
    if [ -d "$src" ]; then chmod -R u=rwX,go=rX "$path.ryce-new"; else chmod "$mode" "$path.ryce-new"; fi
    chown -R "$ME" "$path.ryce-new" || die "no pude hacer root el dueño de $rel: el original sigue intacto"
  fi
  rm -rf "$path"
  mv "$path.ryce-new" "$path" || die "no pude colocar $rel (la copia está en la copia de seguridad): ejecuta --rollback"
  return 1
}

edit() {  # edit OUT VERB FILE ARGS...: edit.py into OUT, or stop with its message
  local out=$1; shift
  "${EDIT[@]}" "$@" > "$out" || die "no pude editar ${2#"$ROOT"} (mensaje arriba): no se ha tocado"
}

# --- initramfs and grub.cfg -----------------------------------------------------------------
listing() { lsinitcpio "$1" > "$TMP/listing" 2>/dev/null; }   # a file, not a pipe: pipefail + grep -q

rebuild() {  # rebuild PRESET: mkinitcpio, keeping the previous image in the set until it passes
  local img=/boot/initramfs-$1.img
  mkdir -p "$SET/scratch"
  [ ! -f "$ROOT$img" ] || cp "$ROOT$img" "$SET/scratch/"
  mkinitcpio -p "$1"
}

# undo_initramfs PRESET WHY PATHS...: put PATHS back from this run's set, rebuild, and stop.
undo_initramfs() {
  local preset=$1 why=$2 img=/boot/initramfs-$1.img rel; shift 2
  printf '\n    ! %s: deshago los cambios del initramfs de %s\n' "$why" "$preset" >&2
  for rel in "$@"; do restore "$rel" "$SET" || true; done
  if ! mkinitcpio -p "$preset"; then
    [ ! -f "$SET/scratch/${img##*/}" ] || cp "$SET/scratch/${img##*/}" "$ROOT$img"
    die "$why, y la reconstrucción con la configuración anterior también falló: he vuelto a poner la imagen anterior ($img). Copias en ${SET#"$ROOT"}"
  fi
  die "$why. Configuración anterior restaurada y $img reconstruido; GRUB y greetd no se han tocado. Copias en ${SET#"$ROOT"}"
}

regen_grub() {  # grub.cfg from /etc/default/grub{,.d}; on failure the previous config and grub.cfg
  local lang rel
  change "${GRUB_CFG} (grub-mkconfig)"
  [ "$DRY" = 1 ] && return 0
  open_set
  mkdir -p "$SET/scratch"
  [ ! -f "$ROOT$GRUB_CFG" ] || cp "$ROOT$GRUB_CFG" "$SET/scratch/grub.cfg"
  # The menu's own words («Opciones avanzadas…») follow LANG; pkexec may not pass it on.
  lang=$(sed -n 's/^LANG=//p' "$ROOT/etc/locale.conf" 2>/dev/null | tr -d '"' | head -n 1 || true)
  if env ${lang:+LANG="$lang"} grub-mkconfig -o "$ROOT$GRUB_CFG" && grub-script-check "$ROOT$GRUB_CFG"; then
    rm -f "$SET/scratch/grub.cfg"
    return 0
  fi
  [ "$ROLLBACK" = 1 ] && die "grub-mkconfig falló tras restaurar las copias: revisa la salida de arriba antes de reiniciar"
  printf '\n    ! grub-mkconfig o grub-script-check fallaron: vuelvo a la configuración de GRUB anterior\n' >&2
  for rel in /etc/default/grub "$GRUB_DROPIN" "$MEMTEST" "$GRUB_DIR"; do restore "$rel" "$SET" || true; done
  if ! { grub-mkconfig -o "$ROOT$GRUB_CFG" && grub-script-check "$ROOT$GRUB_CFG"; }; then
    [ ! -f "$SET/scratch/grub.cfg" ] || cp "$SET/scratch/grub.cfg" "$ROOT$GRUB_CFG"
  fi
  die "no se pudo generar grub.cfg con el tema; el menú de arranque es el de antes. Copias en ${SET#"$ROOT"}"
}

# --- fonts ----------------------------------------------------------------------------------
# The vendored fonts go system-wide: neither the greeter user nor mkinitcpio (Plymouth's Font=,
# resolved with fc-match as root) can see ~/.local/share/fonts.
install_fonts() {
  [ "$FONTS_DONE" = 0 ] || return 0
  FONTS_DONE=1
  local stage=$TMP/fonts
  from_repo "$stage" 'assets/fonts/*.ttf' 'assets/fonts/*.otf' assets/fonts/licenses/
  if ! install_path "$FONT_DIR" "$stage" u=rwX; then
    FONTS_CHANGED=1
    if [ "$DRY" = 0 ] && command -v fc-cache >/dev/null; then
      fc-cache -f "$ROOT$FONT_DIR" || warn "fc-cache falló: las fuentes se verán tras el siguiente arranque"
    fi
  fi
}

# font_face FAMILY: "FILE<TAB>INDEX" of the family's Regular face, from the repo's fonts first
# and then the system's; nothing when the family is nowhere.
font_face() {
  local fam=$1 found
  local files=("$REPO"/assets/fonts/*.ttf "$REPO"/assets/fonts/*.otf)
  found=$(for f in "${files[@]}"; do [ ! -f "$f" ] || fc-scan -f '%{file}\t%{family}\t%{style}\t%{index}\n' "$f"; done \
    | awk -F'\t' -v fam="$fam" '
        { n = split($2, names, ","); hit = 0; for (i = 1; i <= n; i++) if (names[i] == fam) hit = 1 }
        hit && $3 == "Regular" { print $1 "\t" $4; done = 1; exit }
        hit && first == "" { first = $1 "\t" $4 }
        END { if (!done && first != "") print first }')
  if [ -z "$found" ]; then
    found=$(fc-match -f '%{family}\t%{file}\t%{index}\n' "$fam:style=Regular" 2>/dev/null \
      | awk -F'\t' -v fam="$fam" '{ n = split($1, names, ","); for (i = 1; i <= n; i++) if (names[i] == fam) print $2 "\t" $3 }')
  fi
  printf '%s' "$found"
}

# --- preconditions --------------------------------------------------------------------------
if [ -z "$ROOT" ] && [ "$DRY" = 0 ] && [ "$(id -u)" -ne 0 ]; then
  die "necesito root: pkexec bash $REPO/install/boot-setup.sh ${ARGS[*]} (o prueba antes con --dry-run)"
fi

missing=()
need_cmd()  { command -v "$1" >/dev/null || missing+=("la orden '$1' (pacman -S ${2:-$1})"); }
need_file() { [ -e "$1" ] || missing+=("${1#"$ROOT"}${2:+ ($2)}"); }
TDIR=$REPO/themes/$THEME
if [ "$ROLLBACK" = 0 ]; then
  if want plymouth || want grub; then
    need_file "$ROOT/etc/default/grub" "¿se instaló con GRUB?"
  fi
  if want plymouth; then
    need_cmd python3 python
    python3 -I -c 'import PIL' 2>/dev/null || missing+=("el módulo Pillow de Python (pacman -S python-pillow)")
    for c in fc-scan fc-match; do need_cmd "$c" fontconfig; done
    need_cmd mkinitcpio; need_cmd lsinitcpio mkinitcpio; need_cmd plymouth
    need_file "$ROOT/usr/lib/plymouth/script.so" "pacman -S plymouth"
    need_file "$ROOT/etc/mkinitcpio.conf"
    need_file "$ROOT$LTS_PRESET" "sin linux-lts no hay arranque de rescate: pacman -S linux-lts"
    for f in ryce.plymouth ryce.script; do need_file "$TDIR/boot/plymouth/$f" "python3 theme/render.py"; done
    for ((i = 0; i < FRAMES; i++)); do need_file "$(printf '%s/peonza/plymouth-%02d.png' "$TDIR" "$i")"; done
  fi
  if want grub; then
    for c in grub-mkconfig grub-script-check grub-mkfont; do need_cmd "$c" grub; done
    for f in theme.txt background.png select_c.png; do need_file "$GRUB_ART/$f" "python3 theme/boot/grub.py"; done
    need_file "$GRUB_FACE"
    # /boot (vfat, dmask=0077) is unreadable without root: a dry run there just assumes changes.
    if [ "$DRY" = 0 ] || [ -r "$ROOT/boot" ]; then need_file "$ROOT/boot/grub" "¿GRUB está en /boot/grub?"; fi
  fi
  if want greeter; then
    need_file "$ROOT/etc/greetd/config.toml" "ejecuta antes install/system-setup.sh"
    need_file "$REPO/quickshell/greeter/shell.qml"
    need_file "$GREETER_ART" "python3 theme/boot/greeter.py"
    for f in regreet.toml regreet.css hyprland-uwsm.desktop; do need_file "$GREETER_ETC/$f"; done
    need_file "$REPO/$CURSOR_SRC/index.theme" "python3 theme/cursor/build.py"
  fi
  if { want plymouth || want grub; } && [ "$DRY" = 0 ] && [ ! -w "$ROOT/boot" ]; then
    missing+=("/boot con permiso de escritura (¿montada de solo lectura? mira 'findmnt /boot')")
  fi
fi
if [ ${#missing[@]} -gt 0 ]; then
  printf '\nboot-setup.sh: falta:\n' >&2
  printf '  - %s\n' "${missing[@]}" >&2
  exit 1
fi

if [ "$DRY" = 0 ]; then
  mkdir -p "$ROOT/var/backups/ryce"
  exec 9> "$ROOT/var/backups/ryce/.lock"
  flock -n 9 || die "ya hay otro boot-setup.sh en marcha"
fi

if [ "$ROLLBACK" = 1 ]; then
  printf 'ryce-pc · deshacer el arranque con tema%s\n' "$([ "$DRY" = 1 ] && echo ' (simulación: no se cambia nada)')"
else
  printf 'ryce-pc · arranque%s (%s)%s\n' "${THEME:+ con el tema $THEME}" "${PARTS[*]}" \
    "$([ "$DRY" = 1 ] && echo ', simulación: no se cambia nada')"
fi

# --- rollback -------------------------------------------------------------------------------
if [ "$ROLLBACK" = 1 ]; then
  step "Deshacer: el último juego de copias"
  base=$ROOT/var/backups/ryce
  latest=$(find "$base" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended \
    -regex '.*/[0-9]{8}-[0-9]{6}(-[0-9]+)?' 2>/dev/null | sort | tail -n 1)
  [ -n "$latest" ] && [ -f "$latest/manifest" ] || die "no hay copias en /var/backups/ryce: no hay nada que deshacer"
  ok "juego ${latest#"$ROOT"}"
  entries=()
  while IFS=$'\t' read -r kind rel extra; do
    case $kind in
      '#'*|'') continue ;;
      saved|absent) [ -z "$extra" ] || kind=bad ;;
      mode) [[ $extra =~ ^[0-7]{3,4}$ ]] || kind=bad ;;
      *) kind=bad ;;
    esac
    [ "$kind" != bad ] || die "manifiesto ilegible: ${latest#"$ROOT"}/manifest"
    [[ " ${TARGETS[*]} " == *" $rel "* ]] || die "el manifiesto nombra $rel, que este script no gestiona: no restauro nada"
    entries+=("$kind"$'\t'"$rel"$'\t'"$extra")
  done < "$latest/manifest"
  initramfs=0
  for e in "${entries[@]}"; do
    IFS=$'\t' read -r kind rel extra <<< "$e"
    case $kind in
      saved) change "restaurar $rel" ;;
      absent) change "quitar $rel (lo creó este script)" ;;
      mode) change "devolver a $rel el modo $extra" ;;
    esac
    [ "$DRY" = 1 ] || restore "$rel" "$latest"
    case $rel in
      /etc/mkinitcpio.conf|"$LTS_CONF"|"$LTS_PRESET"|/etc/plymouth/plymouthd.conf|"$PLY_DIR"|"$FONT_DIR") initramfs=1 ;;
      /etc/default/grub|"$GRUB_DROPIN"|"$MEMTEST"|"$GRUB_DIR") GRUB_DIRTY=1 ;;
    esac
  done
  SET=$latest
  # system-setup.sh also points greetd at the wrapper: never leave greetd without its greeter.
  if [ "$DRY" = 0 ] && [ ! -e "$ROOT$GREETER_BIN" ] && grep -qF "$GREETER_BIN" "$ROOT/etc/greetd/config.toml" 2>/dev/null; then
    from_repo "$TMP/rescue" install/boot/ryce-greeter
    install -m 0755 "$TMP/rescue/ryce-greeter" "$ROOT$GREETER_BIN"
    warn "greetd sigue usando $GREETER_BIN: lo dejo instalado"
  fi
  if [ "$initramfs" = 1 ]; then
    change "initramfs de todos los núcleos (mkinitcpio -P)"
    [ "$DRY" = 1 ] || mkinitcpio -P || die "mkinitcpio -P falló tras restaurar las copias: no reinicies hasta revisar la salida de arriba"
  fi
  [ "$GRUB_DIRTY" = 0 ] || regen_grub
  if [ "$DRY" = 0 ]; then mv "$latest" "$latest.restored"; ok "juego marcado como restaurado (${latest#"$ROOT"}.restored)"; fi
  older=$(find "$base" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended \
    -regex '.*/[0-9]{8}-[0-9]{6}(-[0-9]+)?' 2>/dev/null | wc -l)
  if [ "$older" -gt 0 ]; then
    warn "quedan $older juegos de copias más antiguos: cada --rollback deshace uno; repítelo para volver al estado anterior a ryce"
  fi
  printf '\n==> Resumen: %d cambios%s, %d avisos\n' "$CHANGES" "$([ "$DRY" = 1 ] && echo ' (simulados)')" "${#WARNINGS[@]}"
  exit 0
fi

# --- 1. rescue: linux-lts boots without plymouth, whatever happens next ----------------------
if want plymouth; then
  step "Rescate: linux-lts arranca siempre sin Plymouth"
  lts_dirty=0
  # Regenerated on every run from the CURRENT mkinitcpio.conf minus plymouth, so a later
  # change there (modules, hooks, a keyfile) reaches the rescue initramfs too; install_path
  # leaves an identical file alone.
  edit "$TMP/lts.conf" hooks "$ROOT/etc/mkinitcpio.conf" drop
  printf '%s\n# linux-lts: the rescue boot, a copy of mkinitcpio.conf without plymouth.\n' "$MANAGED" \
    | cat - "$TMP/lts.conf" > "$TMP/lts.conf.new"
  install_path "$LTS_CONF" "$TMP/lts.conf.new" 0644 || lts_dirty=1
  edit "$TMP/lts.preset" preset "$ROOT$LTS_PRESET" "$LTS_CONF"
  install_path "$LTS_PRESET" "$TMP/lts.preset" 0644 || lts_dirty=1
  if ! listing "$ROOT/boot/initramfs-linux-lts.img" || grep -q plymouth "$TMP/listing"; then lts_dirty=1; fi
  if [ "$lts_dirty" = 0 ]; then
    ok "initramfs-linux-lts.img no lleva plymouth"
  else
    change "initramfs de linux-lts (mkinitcpio -p linux-lts)"
    if [ "$DRY" = 0 ]; then
      open_set
      rebuild linux-lts || undo_initramfs linux-lts "mkinitcpio -p linux-lts falló" "$LTS_CONF" "$LTS_PRESET"
      if ! listing "$ROOT/boot/initramfs-linux-lts.img" || grep -q plymouth "$TMP/listing"; then
        undo_initramfs linux-lts "la imagen de linux-lts no es legible o lleva plymouth" "$LTS_CONF" "$LTS_PRESET"
      fi
      rm -rf "$SET/scratch"
    fi
  fi
fi

# --- 2. plymouth ----------------------------------------------------------------------------
if want plymouth; then
  step "Plymouth: la peonza girando, la contraseña del disco dentro"
  dirty=0
  install_fonts
  [ "$FONTS_CHANGED" = 0 ] || dirty=1
  stage=$TMP/plymouth
  frames=()
  for ((i = 0; i < FRAMES; i++)); do frames+=("$(printf '%s/peonza/plymouth-%02d.png' "$TDIR" "$i")"); done
  from_repo "$stage" "$TDIR/boot/plymouth/ryce.plymouth" "$TDIR/boot/plymouth/ryce.script" "${frames[@]}"
  "${IMAGES[@]}" dot "$TDIR" "$stage/dot.png" || die "no pude dibujar el punto de la contraseña (images.py)"
  # «Contraseña del disco» as a picture in the theme's face: plymouth cannot draw the ñ itself.
  family=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["fonts"]["ui"])' "$TDIR/theme.json")
  face=$(font_face "$family")
  if [ -z "$face" ]; then
    warn "no encuentro la fuente '$family': el aviso de la contraseña irá en Martian Mono"
    face=$GRUB_FACE$'\t'0
  fi
  "${IMAGES[@]}" prompt "$TDIR" "${face%%$'\t'*}" "${face#*$'\t'}" "$stage/prompt.png" \
    || die "no pude dibujar el aviso de la contraseña con ${face%%$'\t'*} (images.py, mensaje arriba)"
  install_path "$PLY_DIR" "$stage" u=rwX || dirty=1
  printf '%s\n[Daemon]\nTheme=ryce\nShowDelay=0\nDeviceTimeout=8\n' "$MANAGED" > "$TMP/plymouthd.conf"
  install_path /etc/plymouth/plymouthd.conf "$TMP/plymouthd.conf" 0644 || dirty=1
  edit "$TMP/mkinitcpio.conf" hooks "$ROOT/etc/mkinitcpio.conf" add
  install_path /etc/mkinitcpio.conf "$TMP/mkinitcpio.conf" 0644 || dirty=1
  theme_file=usr/share/plymouth/themes/ryce/ryce.script
  if ! listing "$ROOT/boot/initramfs-linux.img" || ! grep -q "$theme_file" "$TMP/listing"; then dirty=1; fi
  if [ "$dirty" = 0 ]; then
    ok "initramfs-linux.img ya lleva plymouth con este tema"
  else
    change "initramfs de linux con plymouth (mkinitcpio -p linux)"
    if [ "$DRY" = 0 ]; then
      open_set
      rebuild linux || undo_initramfs linux "mkinitcpio -p linux falló" "${INITRAMFS_INPUTS[@]}"
      if ! listing "$ROOT/boot/initramfs-linux.img" || ! grep -q "$theme_file" "$TMP/listing"; then
        undo_initramfs linux "lsinitcpio no encuentra el tema ryce dentro de initramfs-linux.img" "${INITRAMFS_INPUTS[@]}"
      fi
      rm -rf "$SET/scratch"
    fi
  fi
  edit "$TMP/grub.default" word "$ROOT/etc/default/grub" GRUB_CMDLINE_LINUX_DEFAULT splash
  install_path /etc/default/grub "$TMP/grub.default" 0644 || GRUB_DIRTY=1
fi

# --- 3. grub --------------------------------------------------------------------------------
if want grub; then
  step "GRUB: cuatro entradas sobre un fondo propio"
  stage=$TMP/grub
  from_repo "$stage" "$GRUB_ART/*"
  from_repo "$TMP/grub-face" "$GRUB_FACE"
  sizes=$(grep -o '"Ryce Regular [0-9]*"' "$stage/theme.txt" | tr -dc '0-9\n' | sort -nu)
  for size in $sizes; do
    grub-mkfont -n Ryce -s "$size" -r "$GRUB_RANGE" -o "$stage/ryce-$size.pf2" "$TMP/grub-face/${GRUB_FACE##*/}" 2> "$TMP/mkfont.err" \
      || { cat "$TMP/mkfont.err" >&2; die "grub-mkfont falló con $GRUB_FACE"; }
    grep -aq "Ryce Regular $size" "$stage/ryce-$size.pf2" \
      || warn "la fuente de GRUB no se llama «Ryce Regular $size»: el menú usará la de GRUB"
  done
  install_path "$GRUB_DIR" "$stage" - || GRUB_DIRTY=1
  cat > "$TMP/ryce.cfg" <<EOF
$MANAGED
# grub-mkconfig reads this after /etc/default/grub: these lines win over it.
# ryce's own menu (theme/boot/grub), drawn for 1920x1080.
GRUB_THEME="$GRUB_DIR/theme.txt"
GRUB_GFXMODE=1920x1080,auto
# Four entries. Each kernel at the top level, no «Opciones avanzadas» submenu: linux first
# (GRUB_TOP_LEVEL in /etc/default/grub), then linux-lts, the rescue boot. Then the snapshots
# and the firmware settings. No «… (EFI BootNext)» entries copied from the firmware's boot
# list (new in grub 2.16; here, only a stale Windows Boot Manager).
GRUB_DISABLE_SUBMENU=true
GRUB_DISABLE_BOOTNEXT=true
EOF
  install_path "$GRUB_DROPIN" "$TMP/ryce.cfg" 0644 || GRUB_DIRTY=1
  # memtest86+ has no knob: its script loses the execute bit (the manifest keeps the mode, so
  # --rollback gives it back). An upgrade of memtest86+-efi restores the bit: re-run then.
  if [ -x "$ROOT$MEMTEST" ]; then
    change "$MEMTEST sin permiso de ejecución: el test de memoria sale del menú"
    if [ "$DRY" = 0 ]; then
      backup_mode "$MEMTEST"
      chmod a-x "$ROOT$MEMTEST" || die "no pude quitar el test de memoria del menú (chmod a-x $MEMTEST)"
    fi
    GRUB_DIRTY=1
  elif [ -e "$ROOT$MEMTEST" ]; then
    ok "el test de memoria no sale en el menú"
  fi
  if grep -Eq '^[[:space:]]*GRUB_TERMINAL_OUTPUT=["]?console' "$ROOT/etc/default/grub"; then
    warn "GRUB_TERMINAL_OUTPUT=console en /etc/default/grub: así GRUB no dibuja el tema; coméntalo"
  fi
fi

if want plymouth || want grub; then
  if [ "$GRUB_DIRTY" = 1 ]; then regen_grub; else ok "$GRUB_CFG al día"; fi
fi

# --- 4. greeter -----------------------------------------------------------------------------
if want greeter; then
  step "Pantalla de acceso: la de ryce; regreet y tuigreet de reserva"
  from_repo "$TMP/greeter-etc" install/boot/ryce-greeter "$GREETER_ETC/regreet.toml" \
    "$GREETER_ETC/regreet.css" "$GREETER_ETC/hyprland-uwsm.desktop"
  from_repo "$TMP/cursor" "$CURSOR_SRC/index.theme" "$CURSOR_SRC/cursors/"
  install_path "$GREETER_BIN" "$TMP/greeter-etc/ryce-greeter" 0755 || true
  install_fonts
  stage=$TMP/page
  from_repo "$stage" 'quickshell/greeter/*.qml' "$GREETER_ART"
  install_path "$GREETER_QML" "$stage" u=rwX || true
  # regreet, the first fallback: the same background as the page.
  stage=$TMP/regreet
  from_repo "$stage" "$GREETER_ART"
  install_path "$GREETER_SHARE" "$stage" u=rwX || true
  install_path /etc/greetd/regreet.toml "$TMP/greeter-etc/regreet.toml" 0644 || true
  install_path /etc/greetd/regreet.css "$TMP/greeter-etc/regreet.css" 0644 || true
  # «Hyprland (uwsm-managed)» out of both greeters' session lists (ryce-greeter reads
  # /usr/local/share first).
  install_path "$UWSM_MASK" "$TMP/greeter-etc/hyprland-uwsm.desktop" 0644 || true
  # The cursor the wrapper names (XCURSOR_THEME) and regreet.toml's cursor_theme_name.
  install_path "$CURSOR_DIR" "$TMP/cursor" u=rwX || true
  # The greeter command, and no [initial_session]: the login page shows after the LUKS
  # passphrase (an autologin would skip it). --rollback brings the old file back.
  edit "$TMP/config.toml" greeter "$ROOT/etc/greetd/config.toml" "$GREETER_BIN"
  install_path /etc/greetd/config.toml "$TMP/config.toml" 0644 || true
  for c in cage regreet; do command -v "$c" >/dev/null || warn "falta $c: el acceso será tuigreet (pacman -S ${c/regreet/greetd-regreet})"; done
  command -v qs >/dev/null || warn "falta quickshell: el acceso será regreet (pacman -S quickshell)"
  command -v tuigreet >/dev/null || warn "falta tuigreet, el acceso de reserva: pacman -S greetd-tuigreet"
  if [ -f "$ROOT/usr/lib/tmpfiles.d/regreet.conf" ]; then
    ok "regreet guarda su estado en /var/lib/regreet (lo crea systemd-tmpfiles en cada arranque)"
  else
    warn "no está /usr/lib/tmpfiles.d/regreet.conf: regreet no recordará el último usuario"
  fi
  ok "greetd no se reinicia ahora: lo verás al cerrar sesión o en el próximo arranque"
fi

# --- summary --------------------------------------------------------------------------------
printf '\n==> Resumen: %d cambios%s, %d avisos\n' "$CHANGES" \
  "$([ "$DRY" = 1 ] && echo ' (simulados)')" "${#WARNINGS[@]}"
for w in "${WARNINGS[@]}"; do printf '    ! %s\n' "$w"; done
if [ "$DRY" = 1 ]; then
  apply=()
  for a in "${ARGS[@]}"; do [ "$a" = --dry-run ] || apply+=("$a"); done
  echo "    Para aplicarlo: pkexec bash $REPO/install/boot-setup.sh ${apply[*]}"
elif [ "$CHANGES" -gt 0 ]; then
  echo "    Reinicia para verlo. Si el arranque falla: en GRUB, la entrada de linux-lts;"
  echo "    después, pkexec bash $REPO/install/boot-setup.sh --rollback"
fi
