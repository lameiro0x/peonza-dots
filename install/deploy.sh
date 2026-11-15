#!/usr/bin/env bash
# Link the repo into your home following install/links.tsv. No root. Run it again after any
# pull: a second run changes nothing.
#
#   bash install/deploy.sh [--dry-run] [--check] [--home DIR]
#   bash install/deploy.sh --uninstall | --restore [STAMP]  [--dry-run] [--home DIR]
#
#   --dry-run    print what would change, change nothing
#   --check      change nothing; exit 1 if any link is missing or wrong
#   --home DIR   deploy into DIR instead of $HOME (the systemd/fc-cache steps are skipped)
#   --uninstall  remove what deploy made (links into this repo, rendered files as written,
#                folders it created once empty) and move back what it first set aside
#   --restore    move back what one run set aside (STAMP, a backup folder; default the latest
#                one that still holds something to give back)
#
# links.tsv: `file` = one symlink for that path; `render` = a real file, the repo file with
# every @HOME@ replaced by the home's path (for configs read with no ~ or $HOME expansion,
# chromium-flags.conf); `tree` = one symlink per file under the repo
# folder (folders are created, never linked, so files apps write never land in the repo;
# tests/, __pycache__/, *.pyc and README.md are skipped; links left pointing at a file the
# repo no longer has are reported by --check and moved to the backup by a real run); `theme` =
# one symlink to ~/.local/state/ryce/theme/current/<repo path>, so the file comes from the theme
# in use and `ryce-theme set` moves every app at once (the path must exist in EVERY themes/<id>/).
# The first `theme` row seeds that state folder from contracts/constants.json: one link per
# theme into the repo's themes/<id>/ and `current -> <default_theme>` (relative) unless
# `current` already names a theme. Whatever is in the way is moved to
# ~/.local/state/ryce/backup/<timestamp>-<4 chars>/ (a new folder per run), never deleted.
# The repo itself is never written. A folder on the way that is a link is followed when it
# leads to a real folder of yours outside the repo (a stow setup), moved aside when it leads
# into the repo, and refused otherwise. Every real run records what it made in
# ~/.local/state/ryce/deploy-manifest.tsv, one `kind<TAB>home path<TAB>extra` per line: link,
# render (extra: the repo file, a TAB, the sha256 of what it wrote), dir (a folder it
# created), backup (extra: the stamp) and old (a render of ours, unedited, set aside: never
# put back). --uninstall and --restore act on those lines only; --uninstall keeps the backup
# lines it could not put back.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
LINKS=$REPO/install/links.tsv
MODE=apply TARGET=$HOME UNDO='' STAMP=''

die() { printf 'deploy.sh: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case $1 in
    --dry-run) MODE=dry ;;
    --check) MODE=check ;;
    --home) [ $# -ge 2 ] || die "--home necesita una carpeta"; TARGET=$2; shift ;;
    --uninstall) UNDO=uninstall ;;
    --restore)
      UNDO=restore
      if [ $# -ge 2 ] && [ "${2#-}" = "$2" ]; then STAMP=$2; shift; fi
      ;;
    -h|--help) sed -n '2,13s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "opción desconocida: $1 (usa --help)" ;;
  esac
  shift
done

[ -z "$UNDO" ] || [ "$MODE" != check ] || die "--check no se combina con --uninstall ni --restore"
[ "$(id -u)" -ne 0 ] || [ "$TARGET" != "$HOME" ] || die "no lo ejecutes con sudo: es para tu usuario"
[ -f "$LINKS" ] || die "no encuentro $LINKS"
[ -d "$TARGET" ] || die "no existe la carpeta $TARGET"
TARGET=$(cd "$TARGET" && pwd -P)
case $TARGET/ in "$REPO"/*) die "la carpeta destino $TARGET está dentro del repo" ;; esac
REAL_HOME=0
[ "$TARGET" = "$(cd "$HOME" && pwd -P)" ] && REAL_HOME=1

STATE_DIR=$TARGET/.local/state/ryce
MANIFEST=$STATE_DIR/deploy-manifest.tsv
BACKUP_ROOT=$STATE_DIR/backup
# Made by the first stash of a real run (mktemp: two runs in one second never share it);
# older manifests carry stamps without the suffix.
BACKUP=$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)-XXXX
STAMP_RE='^[0-9]{8}-[0-9]{6}(-[A-Za-z0-9]{4})?$'
FINE=0 CHANGED=0 DRIFT=0 BACKED=0
ERRORS=() REFUSED=()
# RENDER_SUMS: the sha256 of every render the manifest records per path (what we wrote there).
declare -A SEEN=() RENDER_SUMS=() RENDERED=() FREED=()

act() {
  CHANGED=$((CHANGED + 1))
  if [ "$MODE" = dry ]; then printf '  + [simulación] %s\n' "$*"; else printf '  + %s\n' "$*"; fi
}

record() {  # record KIND REL [EXTRA [SUM]]: one manifest line, real runs only
  [ "$MODE" = apply ] || return 0
  printf '%s\t%s\t%s%s\n' "$1" "$2" "${3:-}" "${4:+$'\t'$4}" >> "$MANIFEST"
}

file_sum() { local s; s=$(sha256sum < "$1"); printf '%s' "${s%% *}"; }

# Move whatever sits at a home path into this run's backup folder (a file, a folder, a stray
# link). mv -n: a copy already there is never overwritten.
stash() {  # stash REL [backup|old]
  local rel=$1
  BACKED=$((BACKED + 1))
  if [ "$MODE" = apply ] && [ "${BACKUP: -5}" = -XXXX ]; then
    mkdir -p "$BACKUP_ROOT"
    BACKUP=$(mktemp -d "$BACKUP")
  fi
  act "$TARGET/$rel apartado en $BACKUP/$rel"
  record "${2:-backup}" "$rel" "${BACKUP##*/}"
  [ "$MODE" = dry ] && return 0
  mkdir -p "$(dirname "$BACKUP/$rel")"
  mv -nT -- "$TARGET/$rel" "$BACKUP/$rel" || true
  if [ -e "$TARGET/$rel" ] || [ -L "$TARGET/$rel" ]; then
    die "no pude apartar $TARGET/$rel en $BACKUP/$rel (¿ya existe, o sin permiso?): lo dejo donde estaba"
  fi
}

# A link we may write through: it leads to a real folder of this user, outside the repo.
own_dir() {  # own_dir ABS
  local real
  real=$(realpath -e -- "$1" 2>/dev/null) && [ -d "$real" ] || return 1
  [ "$(stat -c %u -- "$real")" = "$(id -u)" ] || return 1
  case $real/ in "$REPO"/*) return 1 ;; esac
}

# Every folder above a link must be the user's own. A symlinked one is followed when it leads
# to a real folder of theirs (a stow setup: moving it would cut every other app off its files),
# moved aside when it leads into the repo (writing through it would write the repo), and
# refused otherwise (another user's folder, a file, a dangling link): the row is skipped and
# the run fails at the end. Sets PARENT_NEW=1 when some folder above is (or, in a dry run,
# would be) freshly created, PARENT_NEW=refused when the row must be skipped.
ensure_parents() {
  local rel=$1 cur='' part
  PARENT_NEW=0
  local IFS=/
  for part in $(dirname "$rel"); do
    [ "$part" = . ] && continue
    cur=${cur:+$cur/}$part
    if [ -n "${SEEN[$cur]:-}" ]; then
      case ${SEEN[$cur]} in old) ;; refused) PARENT_NEW=refused; return 0 ;; *) PARENT_NEW=1 ;; esac
      continue
    fi
    if [ "$PARENT_NEW" = 0 ] && [ -d "$TARGET/$cur" ] && [ ! -L "$TARGET/$cur" ]; then
      SEEN[$cur]=old; continue
    fi
    if [ "$PARENT_NEW" = 0 ] && [ -L "$TARGET/$cur" ] && ! repo_link "$TARGET/$cur"; then
      if own_dir "$TARGET/$cur"; then
        printf '  · %s es un enlace a %s: lo sigo y escribo dentro\n' "$TARGET/$cur" "$(realpath -- "$TARGET/$cur")"
        SEEN[$cur]=old; continue
      fi
      SEEN[$cur]=refused PARENT_NEW=refused
      REFUSED+=("$TARGET/$cur es un enlace a $(readlink -- "$TARGET/$cur"), que no es una carpeta tuya: ni escribo a través de él ni lo aparto")
      return 0
    fi
    [ "$PARENT_NEW" = 1 ] || { [ ! -L "$TARGET/$cur" ] && [ ! -e "$TARGET/$cur" ]; } || stash "$cur"
    SEEN[$cur]=new PARENT_NEW=1
    [ "$MODE" = dry ] || mkdir "$TARGET/$cur"
    record dir "$cur"
  done
}

link_one() {  # link_one SRC_ABS REL_IN_HOME
  local src=$1 rel=$2 dst=$TARGET/$2
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then FINE=$((FINE + 1)); record link "$rel"; return 0; fi
  if [ "$MODE" = check ]; then
    DRIFT=$((DRIFT + 1))
    if [ -L "$dst" ]; then printf '  ✗ %s apunta a %s\n' "$dst" "$(readlink "$dst")"
    elif [ -e "$dst" ]; then printf '  ✗ %s es un fichero propio, no un enlace al repo\n' "$dst"
    else printf '  ✗ %s no existe\n' "$dst"; fi
    return 0
  fi
  ensure_parents "$rel"
  [ "$PARENT_NEW" != refused ] || return 0
  if [ "$PARENT_NEW" = 0 ] && { [ -L "$dst" ] || [ -e "$dst" ]; }; then stash "$rel"; fi
  act "$dst → ${src#"$REPO"/}"
  [ "$MODE" = dry ] || ln -s "$src" "$dst"
  record link "$rel"
}

render_text() { local body; body=$(<"$1"); printf '%s\n' "${body//@HOME@/"$TARGET"}"; }

render_one() {  # render_one SRC_ABS REL_IN_HOME SRC_REL
  local src=$1 rel=$2 dst=$TARGET/$2 want sum
  want=$(render_text "$src")
  sum=$(printf '%s\n' "$want" | sha256sum) sum=${sum%% *}
  if [ -f "$dst" ] && [ ! -L "$dst" ] && [ "$(<"$dst")" = "$want" ]; then
    FINE=$((FINE + 1)); record render "$rel" "$3" "$sum"; return 0
  fi
  if [ "$MODE" = check ]; then
    DRIFT=$((DRIFT + 1))
    if [ -L "$dst" ]; then printf '  ✗ %s es un enlace, no el fichero generado de %s\n' "$dst" "$3"
    elif [ -e "$dst" ]; then printf '  ✗ %s no coincide con %s (con tu home dentro)\n' "$dst" "$3"
    else printf '  ✗ %s no existe\n' "$dst"; fi
    return 0
  fi
  ensure_parents "$rel"
  [ "$PARENT_NEW" != refused ] || return 0
  if [ "$PARENT_NEW" = 0 ] && { [ -L "$dst" ] || [ -e "$dst" ]; }; then
    # Exactly what an earlier run wrote is kept, but it is not the user's original; anything
    # else there (theirs, or a render they edited) is.
    if [ -f "$dst" ] && [ ! -L "$dst" ] && [[ " ${RENDER_SUMS[$rel]:-} " == *" $(file_sum "$dst") "* ]]; then
      stash "$rel" old
    else
      stash "$rel"
    fi
  fi
  act "$dst → $3 (con tu home dentro)"
  if [ "$MODE" = apply ]; then
    printf '%s\n' "$want" > "$dst.ryce-tmp"
    mv -f "$dst.ryce-tmp" "$dst"
  fi
  record render "$rel" "$3" "$sum"
}

# Links under a managed tree that point into its repo folder at a file that no longer exists
# (renamed or deleted in the repo): --check reports them, a real run moves them to the backup.
prune_orphans() {  # prune_orphans SRC_ABS REL_IN_HOME
  local src=$1 dir=$TARGET/$2 l t
  [ -d "$dir" ] && { [ ! -L "$dir" ] || own_dir "$dir"; } || return 0
  while IFS= read -r -d '' l; do
    t=$(readlink "$l")
    case $t in "$src"/*) ;; *) continue ;; esac
    [ ! -e "$t" ] || continue
    if [ "$MODE" = check ]; then
      DRIFT=$((DRIFT + 1))
      printf '  ✗ %s apunta a %s, que ya no existe en el repo\n' "$l" "${t#"$REPO"/}"
    else
      printf '  · enlace huérfano: %s ya no existe en el repo\n' "${t#"$REPO"/}"
      stash "${l#"$TARGET"/}"
    fi
  done < <(find "$dir/" -type l -print0 | sort -z)
}

THEME_STATE='' DEFAULT_THEME=''
THEMES=()

theme_known() {  # theme_known ID: listed in constants.json and present in the repo
  local id
  for id in "${THEMES[@]}"; do [ "$id" = "$1" ] && [ -d "$REPO/themes/$1" ] && return 0; done
  return 1
}

# Once, on the first `theme` row: read the theme list and seed ~/<theme_state>/. A `current`
# that names a theme is the user's choice (ryce-theme moves it) and is never touched.
seed_theme_state() {
  [ -z "$THEME_STATE" ] || return 0
  local conf id cur dst lines
  conf=$(python3 - "$REPO/contracts/constants.json" 2>/dev/null <<'PY'
import json, re, sys
c = json.load(open(sys.argv[1], encoding="utf-8"))
ids = c["themes"]
assert ids and all(re.fullmatch(r"[a-z][a-z0-9-]*", i) for i in ids) and c["default_theme"] in ids
print(c["theme_state"], c["default_theme"], *ids, sep="\n")
PY
  ) || die "contracts/constants.json no define los temas (themes, default_theme, theme_state): sin eso no hay filas theme"
  mapfile -t lines <<<"$conf"
  THEME_STATE=${lines[0]} DEFAULT_THEME=${lines[1]} THEMES=("${lines[@]:2}")
  valid_rel "$THEME_STATE" || die "constants.json: theme_state debe ser una ruta relativa a tu home: $THEME_STATE"
  for id in "${THEMES[@]}"; do
    if [ -d "$REPO/themes/$id" ]; then link_one "$REPO/themes/$id" "$THEME_STATE/$id"
    else ERRORS+=("falta en el repo: themes/$id/ (tema de contracts/constants.json)"); fi
  done
  dst=$TARGET/$THEME_STATE/current
  cur=$(readlink "$dst" 2>/dev/null || true)
  if theme_known "$cur"; then FINE=$((FINE + 1)); record link "$THEME_STATE/current"; return 0; fi
  if [ "$MODE" = check ]; then
    DRIFT=$((DRIFT + 1))
    printf '  ✗ %s no apunta a ningún tema%s\n' "$dst" "${cur:+ (apunta a $cur)}"
    return 0
  fi
  ensure_parents "$THEME_STATE/current"
  [ "$PARENT_NEW" != refused ] || return 0
  if [ "$PARENT_NEW" = 0 ] && { [ -L "$dst" ] || [ -e "$dst" ]; }; then stash "$THEME_STATE/current"; fi
  act "$dst → $DEFAULT_THEME"
  [ "$MODE" = dry ] || ln -s "$DEFAULT_THEME" "$dst"
  record link "$THEME_STATE/current"
}

valid_rel() {  # a relative path that stays inside its root
  case /$1/ in */../*|*/./*|//*) return 1 ;; esac
  [ -n "$1" ] && [ "${1#/}" = "$1" ]
}

UNDONE=0 KEPT=0

repo_link() {  # repo_link PATH: a link that resolves (through the theme state too) into the repo
  [ -L "$1" ] || return 1
  case $(realpath -m -- "$1") in "$REPO"/*) return 0 ;; esac
  return 1
}

# Still ours: a link into this repo, or a file exactly as some run rendered it (manifests
# older than the sums: as the repo file renders today).
ours() {
  local dst=$TARGET/$1 src=${RENDERED[$1]:-}
  if [ -L "$dst" ]; then repo_link "$dst"; return; fi
  [ -n "$src" ] && [ -f "$dst" ] || return 1
  [[ " ${RENDER_SUMS[$1]:-} " == *" $(file_sum "$dst") "* ]] && return 0
  [ -f "$REPO/$src" ] && [ "$(<"$dst")" = "$(render_text "$REPO/$src")" ]
}

drop() {  # remove a home path judged ours beforehand
  UNDONE=$((UNDONE + 1)) FREED[$1]=1
  act "quito $TARGET/$1"
  [ "$MODE" = dry ] || rm -f -- "$TARGET/$1"
}

# put_back REL STAMP: the copy in that backup set goes home, unless something new stands
# there (in a dry run, what this run would have removed by then counts as gone).
put_back() {
  local rel=$1 bak=$BACKUP_ROOT/$2/$1 dst=$TARGET/$1
  if { [ -e "$dst" ] || [ -L "$dst" ]; } && { [ "$MODE" != dry ] || [ -z "${FREED[$rel]:-}" ]; }; then
    KEPT=$((KEPT + 1))
    printf '  ! %s ya existe y no es de ryce: tu copia sigue en %s\n' "$dst" "$bak"
    return 1
  fi
  act "$dst devuelto (copia del $2)"
  [ "$MODE" = dry ] && return 0
  mkdir -p "$(dirname "$dst")"
  mv -nT -- "$bak" "$dst" || true
  [ -e "$bak" ] || [ -L "$bak" ] || return 0
  KEPT=$((KEPT + 1))
  printf '  ! %s no se pudo devolver: tu copia sigue en %s\n' "$dst" "$bak"
  return 1
}

# The copy a backup line points at, unless it is gone or is itself a link of ours set aside.
restorable() { [ -e "$1" ] || [ -L "$1" ] && ! repo_link "$1"; }

# --uninstall and --restore: only what the manifest names, and only while it is still ours.
undo() {
  [ -f "$MANIFEST" ] || die "no hay manifiesto en $MANIFEST: nada que deshacer (lo escribe cada deploy.sh real; si instalaste antes de que existiera, ejecuta deploy.sh una vez y repite)"
  [ "$MODE" = dry ] || lock_state
  local kind rel extra sum n=0 r s done=0
  local -a links=() dirs=() backups=() gone=() back=()
  local -A first=() kept=()
  while IFS=$'\t' read -r kind rel extra sum; do
    n=$((n + 1))
    valid_rel "$rel" || die "$MANIFEST:$n: ruta no válida: $rel"
    case $kind in
      link) links+=("$rel") ;;
      render)
        valid_rel "$extra" || die "$MANIFEST:$n: ruta del repo no válida: $extra"
        RENDERED[$rel]=$extra RENDER_SUMS[$rel]+=" $sum" links+=("$rel") ;;
      dir) dirs+=("$rel") ;;
      backup|old)
        [[ $extra =~ $STAMP_RE ]] || die "$MANIFEST:$n: sello no válido: $extra"
        [ "$kind" = old ] || backups+=("$extra"$'\t'"$rel") ;;
      *) die "$MANIFEST:$n: tipo desconocido: $kind" ;;
    esac
  done < "$MANIFEST"
  # Oldest set first: the stamp's time part sorts as time; within one second (and one run)
  # the manifest order, which is the order things happened, is kept.
  [ ${#backups[@]} -eq 0 ] || mapfile -t backups < <(printf '%s\n' "${backups[@]}" | sort -s -t $'\t' -k1.1,1.15)

  if [ "$UNDO" = restore ]; then
    [ ${#backups[@]} -gt 0 ] || die "nada que devolver: el manifiesto no anota nada apartado"
    if [ -z "$STAMP" ]; then   # the latest set that still holds something of the user's
      for ((n = ${#backups[@]} - 1; n >= 0; n--)); do
        r=${backups[n]}
        restorable "$BACKUP_ROOT/${r%%$'\t'*}/${r#*$'\t'}" && { STAMP=${r%%$'\t'*}; break; }
      done
      [ -n "$STAMP" ] || die "nada que devolver: lo que anota el manifiesto ya no está en $BACKUP_ROOT (o son enlaces al repo)"
    fi
    [[ $STAMP =~ $STAMP_RE ]] || die "--restore espera un sello AAAAMMDD-HHMMSS[-XXXX] (una carpeta de $BACKUP_ROOT), no $STAMP"
    for r in "${backups[@]}"; do
      rel=${r#*$'\t'}
      [ "${r%%$'\t'*}" = "$STAMP" ] && restorable "$BACKUP_ROOT/$STAMP/$rel" && back+=("$rel")
    done
    [ ${#back[@]} -gt 0 ] || die "nada que devolver del $STAMP"
    for rel in "${back[@]}"; do ! ours "$rel" || gone+=("$rel"); done
    for rel in "${gone[@]}"; do drop "$rel"; done
    for rel in "${back[@]}"; do
      put_back "$rel" "$STAMP" || continue
      done=$((done + 1))
      [ "$MODE" = apply ] || continue
      # Its backup line goes, and so do its render lines: what stands there now is the user's.
      R=$rel S=$STAMP awk -F'\t' '!($2 == ENVIRON["R"] && ($1 == "render" || ($1 == "backup" && $3 == ENVIRON["S"])))' \
        "$MANIFEST" > "$MANIFEST.tmp"
      mv -f "$MANIFEST.tmp" "$MANIFEST"
    done
    printf 'deploy --restore %s%s: %d devueltos · %d siguen en la copia\n' "$STAMP" \
      "$([ "$MODE" = dry ] && echo ' (simulación)')" "$done" "$KEPT"
    return 0
  fi

  # Decide everything before removing anything: theme links resolve through
  # ~/.local/state/ryce/theme/current, itself one of the links.
  for rel in "${links[@]}"; do
    [ -z "${first[$rel]:-}" ] || continue
    first[$rel]=seen
    if ours "$rel"; then gone+=("$rel")
    elif [ -e "$TARGET/$rel" ] || [ -L "$TARGET/$rel" ]; then
      KEPT=$((KEPT + 1))
      printf '  · %s ya no es de ryce: se queda\n' "$TARGET/$rel"
    fi
  done
  first=()
  for r in "${backups[@]}"; do
    s=${r%%$'\t'*} rel=${r#*$'\t'}
    [ -z "${first[$rel]:-}" ] && restorable "$BACKUP_ROOT/$s/$rel" || continue
    first[$rel]=$s
    back+=("$rel")
  done
  if [ "$MODE" = apply ] && [ "$REAL_HOME" = 1 ] && command -v systemctl >/dev/null \
     && [ "$(systemctl --user is-enabled agentd.service 2>/dev/null || true)" = enabled ]; then
    systemctl --user disable agentd.service >/dev/null 2>&1 && echo "  - agentd.service desactivado" || true
  fi
  for rel in "${gone[@]}"; do drop "$rel"; done
  # The folders it created, deepest first, once empty (a dry run assumes they will be).
  while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    if [ "$MODE" = dry ] || rmdir -- "$TARGET/$rel" 2>/dev/null; then FREED[$rel]=1; fi
  done < <(printf '%s\n' "${dirs[@]}" | sort -ru)
  for rel in "${back[@]}"; do put_back "$rel" "${first[$rel]}" && done=$((done + 1)); done
  # Outside the links: the VS Code themes deploy installed are cheap to take back; what
  # `ryce-theme apply` set in the running desktop is not recorded, so it is said instead.
  if [ "$REAL_HOME" = 1 ] && [ -f "$STATE_DIR/vscode-vsix.sha256" ] && command -v code >/dev/null; then
    act "quito los temas de VS Code (code --uninstall-extension ryce.ryce-themes)"
    if [ "$MODE" = apply ]; then
      code --uninstall-extension ryce.ryce-themes >/dev/null 2>&1 && rm -f -- "$STATE_DIR/vscode-vsix.sha256" \
        || echo "  ! VS Code no quitó sus temas: code --uninstall-extension ryce.ryce-themes"
    fi
  fi
  if [ "$REAL_HOME" = 1 ]; then
    echo "  · no se deshace lo que ryce-theme aplicó en tu sesión: iconos, cursor y fuente de GTK (gsettings), la variable universal ryce_theme de fish y el tema de color de VS Code"
    [ ! -f "$TARGET/.config/Code/User/settings.json.ryce-bak" ] \
      || echo "  · tu settings.json de VS Code de antes de ryce está en $TARGET/.config/Code/User/settings.json.ryce-bak"
  fi
  if [ "$MODE" = apply ]; then
    # What is still set aside keeps its line (a later --restore can give it back) and its
    # folder; only the empty folders around it go.
    : > "$MANIFEST.tmp"
    for r in "${backups[@]}"; do
      s=${r%%$'\t'*} rel=${r#*$'\t'}
      restorable "$BACKUP_ROOT/$s/$rel" || continue
      printf 'backup\t%s\t%s\n' "$rel" "$s" >> "$MANIFEST.tmp"
      kept[$BACKUP_ROOT/$s/$rel]=1
    done
    if [ -s "$MANIFEST.tmp" ]; then mv -f "$MANIFEST.tmp" "$MANIFEST"; else rm -f -- "$MANIFEST.tmp" "$MANIFEST"; fi
    if [ -d "$BACKUP_ROOT" ]; then
      while IFS= read -r -d '' r; do
        [ -n "${kept[$r]:-}" ] || rmdir -- "$r" 2>/dev/null || true
      done < <(find "$BACKUP_ROOT" -mindepth 1 -depth -type d -print0)
    fi
    rmdir -- "$BACKUP_ROOT" 2>/dev/null || true
    rmdir -- "$STATE_DIR" 2>/dev/null || true
    if [ "$REAL_HOME" = 1 ] && command -v systemctl >/dev/null; then systemctl --user daemon-reload 2>/dev/null || true; fi
  fi
  printf 'deploy --uninstall%s: %d quitados · %d devueltos · %d dejados en su sitio\n' \
    "$([ "$MODE" = dry ] && echo ' (simulación)')" "$UNDONE" "$done" "$KEPT"
  [ "$MODE" = dry ] || [ ! -f "$MANIFEST" ] \
    || echo "  · lo que no se pudo devolver sigue en $BACKUP_ROOT y en el manifiesto: deploy.sh --restore lo devuelve cuando quede libre su sitio"
}

# One run at a time on a state folder: the lock is on the folder itself, so --uninstall can
# still remove it.
lock_state() {
  command -v flock >/dev/null || die "falta flock (util-linux)"
  exec 9<"$STATE_DIR"
  flock -n 9 || die "otro deploy.sh está trabajando en $STATE_DIR: espera a que acabe y repite"
}

if [ -n "$UNDO" ]; then undo; exit 0; fi

# The state folder is written before any row: the same rule as ensure_parents, but checked
# up front, since mkdir -p would otherwise go through whatever link stands on the way.
if [ "$MODE" != check ]; then
  cur=''
  for part in .local state ryce; do
    cur=${cur:+$cur/}$part
    if [ -L "$TARGET/$cur" ]; then
      own_dir "$TARGET/$cur" || die "$TARGET/$cur es un enlace a $(readlink -- "$TARGET/$cur"), que no es una carpeta tuya fuera del repo: ahí va el manifiesto de deploy. Cámbialo por una carpeta real y repite"
    elif [ -e "$TARGET/$cur" ] && [ ! -d "$TARGET/$cur" ]; then
      die "$TARGET/$cur no es una carpeta: ahí va el manifiesto de deploy. Apártalo y repite"
    fi
  done
fi
if [ "$MODE" = apply ]; then
  mkdir -p "$STATE_DIR"
  lock_state
  if [ -f "$MANIFEST" ]; then
    while IFS=$'\t' read -r kind rel _ sum; do [ "$kind" != render ] || RENDER_SUMS[$rel]+=" $sum"; done < "$MANIFEST"
  fi
fi

lineno=0
while IFS= read -r line || [ -n "$line" ]; do
  lineno=$((lineno + 1))
  case $line in ''|'#'*) continue ;; esac
  IFS=$'\t' read -r src rel kind extra <<<"$line"
  if [ -z "${kind:-}" ] || [ -n "${extra:-}" ] || ! valid_rel "$src" || ! valid_rel "$rel"; then
    die "links.tsv:$lineno: se esperaban tres columnas separadas por tabulador (repo, home, file|tree|theme|render): $line"
  fi
  case $kind in
    file)
      if [ -f "$REPO/$src" ]; then link_one "$REPO/$src" "$rel"
      else ERRORS+=("links.tsv:$lineno: falta en el repo: $src"); fi
      ;;
    render)
      if [ -f "$REPO/$src" ]; then render_one "$REPO/$src" "$rel" "$src"
      else ERRORS+=("links.tsv:$lineno: falta en el repo: $src"); fi
      ;;
    tree)
      if [ ! -d "$REPO/$src" ]; then ERRORS+=("links.tsv:$lineno: falta en el repo: $src/"); continue; fi
      while IFS= read -r -d '' f; do
        link_one "$f" "$rel/${f#"$REPO/$src"/}"
      done < <(find "$REPO/$src" -type d \( -name tests -o -name __pycache__ \) -prune -o \
                 \( -type f -o -type l \) ! -name '*.pyc' ! -name README.md ! -name .DS_Store \
                 -print0 | sort -z)
      prune_orphans "$REPO/$src" "$rel"
      ;;
    theme)
      seed_theme_state
      for id in "${THEMES[@]}"; do
        [ -d "$REPO/themes/$id" ] && [ ! -e "$REPO/themes/$id/$src" ] || continue
        ERRORS+=("links.tsv:$lineno: falta themes/$id/$src (genera los temas: python3 tools/tokens.py; python3 theme/render.py)")
      done
      link_one "$TARGET/$THEME_STATE/current/$src" "$rel"
      ;;
    *) die "links.tsv:$lineno: modo '$kind' desconocido (file, tree, theme o render)" ;;
  esac
done < "$LINKS"

if [ "$MODE" = apply ]; then   # one line per thing, in first-seen order
  awk '!seen[$0]++' "$MANIFEST" > "$MANIFEST.tmp" && mv -f "$MANIFEST.tmp" "$MANIFEST"
fi

for e in "${ERRORS[@]}" "${REFUSED[@]}"; do printf '  ✗ %s\n' "$e" >&2; done

if [ "$MODE" = check ]; then
  printf 'deploy --check: %d enlaces correctos · %d con deriva\n' "$FINE" "$DRIFT"
  [ "$DRIFT" -eq 0 ] && [ ${#ERRORS[@]} -eq 0 ] || exit 1
  exit 0
fi

printf 'deploy%s: %d ya correctos · %d cambios' "$([ "$MODE" = dry ] && echo ' (simulación)')" "$FINE" "$CHANGED"
[ "$BACKED" -eq 0 ] || printf ' · %d apartados en %s' "$BACKED" "$BACKUP"
printf '\n'
[ ${#ERRORS[@]} -eq 0 ] || die "el repo está incompleto (${#ERRORS[@]} rutas de links.tsv no existen): 'git pull' o vuelve a clonarlo"
[ ${#REFUSED[@]} -eq 0 ] || die "lo que va bajo ${#REFUSED[@]} carpetas enlazadas no se ha instalado (arriba): cambia cada enlace por una carpeta tuya (o monta el disco al que apunta) y repite"

[ "$MODE" = apply ] && [ "$REAL_HOME" = 1 ] || exit 0

if command -v fc-cache >/dev/null; then
  fc-cache -f >/dev/null && echo "  ✓ caché de fuentes al día" || echo "  ! fc-cache falló: ejecútalo a mano (fc-cache -fv)"
fi
if command -v systemctl >/dev/null && systemctl --user show-environment >/dev/null 2>&1; then
  systemctl --user daemon-reload
  if [ -f "$TARGET/.config/systemd/user/agentd.service" ]; then
    if [ "$(systemctl --user is-enabled agentd.service 2>/dev/null || true)" = enabled ]; then
      echo "  ✓ agentd.service activado"
    else
      systemctl --user enable agentd.service && echo "  + agentd.service activado (arranca con tu sesión)"
    fi
  fi
else
  echo "  ! no hay gestor systemd de usuario en esta sesión: entra en una TTY con tu usuario y repite"
fi
# Theme assets that live outside the links: the recoloured folder icons (one icon
# theme per desktop theme; idempotent, a matching stamp does nothing) and the VS Code
# colour themes (the VSIX is reinstalled only when its bytes changed).
if command -v python3 >/dev/null && [ -d /usr/share/icons/Papirus-Dark ]; then
  python3 "$REPO/theme/icons.py" >/dev/null && echo "  ✓ carpetas de cada tema" || echo "  ! no se pudieron generar las carpetas (python3 theme/icons.py)"
fi
if command -v code >/dev/null && [ -f "$REPO/themes/ryce-vscode.vsix" ]; then
  vsix_sum=$(sha256sum "$REPO/themes/ryce-vscode.vsix" | cut -d' ' -f1)
  stamp=$TARGET/.local/state/ryce/vscode-vsix.sha256
  if [ "$(cat "$stamp" 2>/dev/null || true)" != "$vsix_sum" ]; then
    if code --install-extension "$REPO/themes/ryce-vscode.vsix" --force >/dev/null 2>&1; then
      mkdir -p "$(dirname "$stamp")" && printf '%s\n' "$vsix_sum" > "$stamp"
      echo "  + temas de VS Code instalados"
    else
      echo "  ! VS Code no instaló sus temas: code --install-extension themes/ryce-vscode.vsix --force"
    fi
  fi
fi
# Live only inside Hyprland: from another desktop `apply` would rewrite its GTK settings,
# fish variables and VS Code theme, none of which --uninstall can put back.
if [ -x "$TARGET/.local/bin/ryce-theme" ] && [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
  "$TARGET/.local/bin/ryce-theme" apply >/dev/null 2>&1 && echo "  ✓ tema aplicado: $("$TARGET/.local/bin/ryce-theme" get 2>/dev/null)" \
    || echo "  ! el tema no se aplicó del todo: ryce-theme apply"
fi
shell=$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f7 || true)
case $shell in
  */fish) ;;
  *) echo "  · fish como shell de inicio (opcional): chsh -s /usr/bin/fish" ;;
esac
echo "  Siguiente: reinicia (sudo reboot) y, ya dentro de Hyprland, bash install/verify.sh"
