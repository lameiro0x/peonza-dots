#!/usr/bin/env bash
# The system layer of ryce-pc, run as root once archinstall 4.5 has finished (default btrfs
# layout + Snapper + GRUB, see GUIA.md). Every step looks before it acts, so running it again
# is always safe and a second run reports 0 changes.
#
#   sudo bash install/system-setup.sh [--dry-run] [--yes] [--user NAME]
#
#   --dry-run   print what would change, change nothing (works without root)
#   --yes       pass --noconfirm to pacman
#   --user      the desktop user (default: the one who ran sudo)
#
# RYCE_ROOT (tests only) prefixes every system path this script reads or writes. Commands
# still run, so the tests put fakes first on PATH; the user's home comes from `getent passwd`.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)   # physical: install/boot/stage.py wants it
REPO=$(dirname "$HERE")
ROOT=${RYCE_ROOT:-}

# The hypr family moves as one unit: a minor release breaks the config about every three
# months and the libraries change soname together. -Syu skips these; ryce-update explains the
# deliberate upgrade. install/check-packages.py parses this array and fails if any official
# package in our install closure links libhypr*/libaquamarine and is missing here.
HYPR_PIN=(
  hyprland aquamarine hyprutils hyprlang hyprcursor hyprgraphics hyprwire
  hyprland-guiutils hyprtoolkit xdg-desktop-portal-hyprland
  hyprlock hypridle hyprsunset hyprpolkitagent hyprland-qt-support hyprpicker
)
# Pinned by an earlier version of this script and released since; removed from IgnorePkg.
# quickshell uses Qt's private API and Arch rebuilds it with every Qt minor release: pinned
# while Qt floats, a Qt update would leave a quickshell built for the old Qt.
RETIRED_PIN=(quickshell)
PIN_MARKER="# ryce-pc: the hypr family moves as one unit; ryce-update explains how to upgrade it"
MANAGED="# Managed by ryce-pc (install/system-setup.sh): change it in the repo and re-run."
# docker and libvirt are root without a password (the summary says so). libvirt is granted
# since 2026-11-16: without it polkit asks for the password once per virsh process, so an
# agent that polls a VM (`until virsh …; do sleep 5; done`) raised the dialog every 5 s.
# Arch's /usr/share/polkit-1/rules.d/50-libvirt.rules lets the group in. kvm only opens /dev/kvm.
USER_GROUPS=(docker kvm libvirt render video)

DRY=0 YES=0 TARGET_USER=
CHANGES=0
WARNINGS=()

die()  { printf '\nsystem-setup.sh: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }
ok()   { printf '    ✓ %s\n' "$*"; }
warn() { WARNINGS+=("$*"); printf '    ! %s\n' "$*"; }
change() {
  CHANGES=$((CHANGES + 1))
  if [ "$DRY" = 1 ]; then printf '    + [simulación] %s\n' "$*"; else printf '    + %s\n' "$*"; fi
}
run() { [ "$DRY" = 1 ] || "$@"; }

usage() { sed -n '2,10s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; }

while [ $# -gt 0 ]; do
  case $1 in
    --dry-run) DRY=1 ;;
    --yes) YES=1 ;;
    --user) [ $# -ge 2 ] || die "--user necesita un nombre"; TARGET_USER=$2; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "opción desconocida: $1 (usa --help)" ;;
  esac
  shift
done

TMP=$(mktemp -d "${TMPDIR:-/tmp}/ryce-setup.XXXXXX")
trap 'rm -rf "$TMP"' EXIT

# Who owns what this script writes: root (a RYCE_ROOT test tree: whoever runs the tests).
# Nothing it writes may belong to the user or be writable by others: a greeter wrapper the
# user could rewrite would see the next login's password.
if [ -n "$ROOT" ]; then ME=$(id -u):$(id -g); else ME=0:0; fi

# owned PATH MODE: PATH (and everything under it) belongs to $ME and no one else may write it;
# a file must also have exactly MODE (0644…); a folder, MODE "-".
owned() {
  find "$1" -exec stat -c '%u:%g %a %n' {} + 2>/dev/null | awk -v me="$ME" -v want="${2#0}" '
    { g = substr($2, length($2) - 1, 1); o = substr($2, length($2), 1) }
    $1 != me || g ~ /[2367]/ || o ~ /[2367]/ || (want != "-" && $2 != want) { bad = 1 }
    END { exit bad || NR == 0 }'
}

# Root copies files out of the user's repo, parts of which the agents' sandbox can write: a
# link planted there (to a root-only folder, to ~/.ssh), even swapped in mid-copy, would be
# read and published. from_repo NAME SPEC...: root's own copies in $TMP/NAME through
# install/boot/stage.py (no link on the way, regular files with one name, read with the repo
# owner's rights; SPEC as stage.py takes it), the only copies installed.
from_repo() {
  python3 -I "$HERE/boot/stage.py" "$REPO" "$TMP/$1" "${@:2}" \
    || die "no copio nada del repo (mensaje arriba): nada se ha tocado por ello"
}

# put_file PATH MODE < content: write only when the content, owner or mode differs (never
# empty content: rendered files go through a temp file whose producer was checked); the first
# time an existing file is replaced, the original is kept next to it as PATH.ryce-orig.
# Returns 1 when it wrote the file, so `put_file … || reload` reloads only on change (and
# every call site needs that `||`: set -e).
put_file() {
  local rel=$1 mode=$2 path=$ROOT$1 new=$TMP/new same=0
  cat > "$new"
  [ -s "$new" ] || die "no hay nada que escribir en $rel (fallo al generarlo): no se ha tocado"
  [ -f "$path" ] && cmp -s "$new" "$path" && same=1
  if [ "$same" = 1 ] && owned "$path" "$mode"; then ok "$rel"; return 0; fi
  if [ "$same" = 1 ]; then
    change "$rel: de root y con su modo (el contenido ya estaba)"
  elif [ -f "$path" ] && [ ! -e "$path.ryce-orig" ]; then
    change "$rel (original guardado en $rel.ryce-orig)"
  elif [ -f "$path" ]; then
    change "$rel"
  else
    change "$rel (nuevo)"
  fi
  [ "$DRY" = 1 ] && return 0
  mkdir -p "$(dirname "$path")"
  # The original keeps its mode and dates, never its owner: the copy is root's.
  [ "$same" = 1 ] || [ ! -f "$path" ] || [ -e "$path.ryce-orig" ] || cp --preserve=mode,timestamps "$path" "$path.ryce-orig"
  cp "$new" "$path.ryce-tmp"
  chmod "$mode" "$path.ryce-tmp"
  chown "$ME" "$path.ryce-tmp"
  mv -f "$path.ryce-tmp" "$path"
  return 1   # "changed": callers use it to reload what depends on the file
}

# render_pacman_conf FILE PINS RETIRED: FILE with Color, VerbosePkgLists and
# ParallelDownloads = 10 set in [options]; with PINS non-empty, IgnorePkg becomes the union of
# what the user already ignores and PINS, minus RETIRED, on one line under PIN_MARKER. Commented defaults are uncommented in place,
# missing keys go at the end of [options], every other line is kept byte for byte.
render_pacman_conf() {
  awk -v pin="$2" -v retired="$3" -v marker="$PIN_MARKER" '
    function section(line,   s) { s = line; gsub(/^[ \t]*\[|\][ \t]*$/, "", s); return s }
    function key_of(line, commented,   s) {
      s = line
      if (commented) { if (s !~ /^[ \t]*#/) return ""; sub(/^[ \t]*#[ \t]*/, "", s) }
      else if (s ~ /^[ \t]*#/) return ""
      sub(/^[ \t]+/, "", s); sub(/[ \t]*(=.*)?$/, "", s)
      return s
    }
    function add_ign(list,   n, a, i) {
      n = split(list, a, /[ \t]+/)
      for (i = 1; i <= n; i++) if (a[i] != "" && !(a[i] in have) && !(a[i] in gone)) { have[a[i]] = 1; ign[++n_ign] = a[i] }
    }
    function emit(k,   i, line) {
      if (k == "IgnorePkg") {
        line = "IgnorePkg   ="
        for (i = 1; i <= n_ign; i++) line = line " " ign[i]
        print marker; print line
      } else print val[k]
      emitted[k] = 1
    }
    function flush(   i) { for (i = 1; i <= nk; i++) if ((keys[i] in val) && !(keys[i] in emitted)) emit(keys[i]) }
    BEGIN {
      val["Color"] = "Color"; val["VerbosePkgLists"] = "VerbosePkgLists"
      val["ParallelDownloads"] = "ParallelDownloads = 10"
      if (pin != "") val["IgnorePkg"] = ""
      n = split(retired, r, " "); for (i = 1; i <= n; i++) gone[r[i]] = 1
      nk = split("Color VerbosePkgLists ParallelDownloads IgnorePkg", keys, " ")
    }
    NR == FNR {
      if ($0 ~ /^[ \t]*\[.*\][ \t]*$/) { sec = section($0); next }
      if (sec == "options") {
        k = key_of($0, 0)
        if (k in val) active[k] = 1
        if (k == "IgnorePkg") { v = $0; sub(/^[^=]*=/, "", v); add_ign(v) }
      }
      next
    }
    FNR == 1 { if (pin != "") add_ign(pin); sec = "" }
    /^[ \t]*\[.*\][ \t]*$/ { if (sec == "options") flush(); sec = section($0); print; next }
    sec == "options" && pin != "" && $0 == marker { next }
    sec == "options" {
      k = key_of($0, 0)
      if (k in val) { if (!(k in emitted)) emit(k); next }
      k = key_of($0, 1)
      if ((k in val) && !(k in active) && !(k in emitted)) { emit(k); next }
    }
    { print }
    END { if (sec == "options") flush() }
  ' "$1" "$1"
}

pacman_conf() {  # pacman_conf "PINS" "RETIRED" (PINS empty: leave IgnorePkg alone)
  local conf=$ROOT/etc/pacman.conf
  [ -s "$conf" ] || die "no encuentro /etc/pacman.conf: ¿es esto un Arch recién instalado?"
  grep -q '^[[:space:]]*\[options\]' "$conf" || die "/etc/pacman.conf no tiene sección [options]: revísalo a mano"
  render_pacman_conf "$conf" "$1" "${2:-}" > "$TMP/render" \
    || die "no pude generar /etc/pacman.conf: no se ha tocado"
  grep -q '^\[options\]' "$TMP/render" || die "el /etc/pacman.conf generado no tiene [options]: no se ha tocado"
  put_file /etc/pacman.conf 0644 < "$TMP/render" || true
}

# render_kv FILE KEY=VALUE...: shell-style config (snapper) with each KEY set to "VALUE";
# missing keys are appended.
render_kv() {
  local file=$1; shift
  awk -v kv="$*" '
    BEGIN { n = split(kv, a, " "); for (i = 1; i <= n; i++) { split(a[i], p, "="); want[p[1]] = p[2]; order[i] = p[1] } }
    {
      for (i = 1; i <= n; i++) if (index($0, order[i] "=") == 1) {
        if (!(order[i] in seen)) print order[i] "=\"" want[order[i]] "\""
        seen[order[i]] = 1; next
      }
      print
    }
    END { for (i = 1; i <= n; i++) if (!(order[i] in seen)) print order[i] "=\"" want[order[i]] "\"" }
  ' "$file"
}

unit_enabled() { [ "$(systemctl is-enabled "$1" 2>/dev/null || true)" = enabled ]; }

enable_unit() {  # enable_unit [--now] UNIT
  local now=0
  if [ "$1" = --now ]; then now=1; shift; fi
  if unit_enabled "$1"; then
    ok "$1 activado"
  else
    change "activar $1"
    run systemctl enable --quiet "$1" || { warn "no pude activar $1: mira 'systemctl status $1'"; return 0; }
  fi
  if [ "$now" = 1 ] && ! systemctl is-active --quiet "$1" 2>/dev/null; then
    change "arrancar $1"
    run systemctl start "$1" || warn "$1 no arranca: mira 'journalctl -u $1 -b'"
  fi
}

# nocow_subvol PATH OWNER MODE: PATH becomes its own btrfs subvolume with CoW off, so it stays
# out of every snapshot of its parent and VM disks/caches do not fragment. Only a missing or
# empty PATH is converted; data is never moved.
nocow_subvol() {
  local path=$1 owner=$2 mode=$3 parent fstype
  parent=$(dirname "$path")
  if [ ! -d "$parent" ]; then
    if [ "$DRY" = 1 ]; then change "$path: subvolumen sin CoW (cuando exista $parent)"
    else warn "$path: no existe $parent (¿falló la instalación de paquetes?)"; fi
    return 0
  fi
  fstype=$(findmnt -no FSTYPE -T "$parent" 2>/dev/null || true)
  if [ "$fstype" != btrfs ]; then
    warn "$path está en '${fstype:-?}', no en btrfs: se deja como está"; return 0
  fi
  if btrfs subvolume show "$path" >/dev/null 2>&1; then ok "$path es un subvolumen aparte"; return 0; fi
  if [ -L "$path" ] || { [ -e "$path" ] && [ ! -d "$path" ]; }; then
    warn "$path no es una carpeta: se deja como está"; return 0
  fi
  if [ -d "$path" ] && [ -n "$(ls -A "$path")" ]; then
    warn "$path ya tiene datos y entra en las instantáneas. Para sacarlo: para lo que lo usa, 'mv $path $path.old', vuelve a ejecutar este script y copia de vuelta con 'cp -a --reflink=never $path.old/. $path/'"
    return 0
  fi
  if [ -d "$path" ]; then change "$path: carpeta vacía → subvolumen sin CoW, fuera de las instantáneas"
  else change "$path: subvolumen nuevo sin CoW, fuera de las instantáneas"; fi
  [ "$DRY" = 1 ] && return 0
  [ ! -d "$path" ] || rmdir "$path"
  btrfs subvolume create "$path" >/dev/null
  chattr +C "$path"
  chown "$owner" "$path"
  chmod "$mode" "$path"
}

# render_docker_daemon FILE: FILE's JSON (or {}) with our keys set, as stable JSON. Fails on
# invalid JSON so put_file never sees half a file.
#   ip / host_binding_ipv4 = 127.0.0.1: `-p 8080:80` publishes on localhost only, for the
#     default bridge and for every user-defined network (compose). Docker docs, port publishing.
#   ip-forward-no-drop: Docker would otherwise set the iptables FORWARD policy to drop when it
#     enables forwarding, which also drops libvirt's NAT (the Kali VM). Forwarding is filtered
#     by our nftables forward chain instead. Docker docs, packet filtering, "Docker on a router".
render_docker_daemon() {
  python3 - "$1" <<'PY'
import json, os, sys

path = sys.argv[1]
conf = {}
if os.path.exists(path):
    with open(path) as f:
        text = f.read()
    conf = json.loads(text) if text.strip() else {}
if not isinstance(conf, dict):
    sys.exit(f"{path}: not a JSON object")
conf["ip"] = "127.0.0.1"
conf["ip-forward-no-drop"] = True
conf.setdefault("default-network-opts", {}).setdefault("bridge", {})[
    "com.docker.network.bridge.host_binding_ipv4"] = "127.0.0.1"
print(json.dumps(conf, indent=2, sort_keys=True))
PY
}

# install_tree DST FILE...: DST holds exactly these files (by name, mode 0644, root's), each
# written only when it differs, by a copy renamed into place; a file of DST no longer among
# them is removed. FILEs are stage()d copies. Vendored files, so no .ryce-orig copies (a stray
# font copy would load twice). Returns 1 when it changed something, like put_file.
install_tree() {
  local dst=$1 f name changed=0
  shift
  local -A want=()
  # A folder the user owns (or others may write) is put right before anything goes into it.
  if [ -d "$ROOT$dst" ] && ! owned "$ROOT$dst" -; then
    changed=1
    change "$dst: de root y sin escritura para otros"
    run chown -R "$ME" "$ROOT$dst"
    run chmod -R go-w "$ROOT$dst"
  fi
  for f in "$@"; do
    name=${f##*/}
    want[$name]=1
    cmp -s "$f" "$ROOT$dst/$name" && continue
    changed=1
    if [ -e "$ROOT$dst/$name" ]; then change "$dst/$name"; else change "$dst/$name (nuevo)"; fi
    [ "$DRY" = 1 ] && continue
    mkdir -p "$ROOT$dst"
    cp "$f" "$ROOT$dst/.$name.ryce-tmp"
    chmod 0644 "$ROOT$dst/.$name.ryce-tmp"
    chown "$ME" "$ROOT$dst/.$name.ryce-tmp"
    mv -f "$ROOT$dst/.$name.ryce-tmp" "$ROOT$dst/$name"
  done
  for f in "$ROOT$dst"/*; do
    [ -f "$f" ] && [ -z "${want[${f##*/}]:-}" ] || continue
    changed=1
    change "quitar $dst/${f##*/} (ya no está en el repo)"
    run rm -f "$f"
  done
  [ "$changed" = 0 ] || return 1
  ok "$dst ($# ficheros)"
}

# --- preflight -----------------------------------------------------------------------------
if [ "$DRY" = 0 ] && [ -z "$ROOT" ] && [ "$(id -u)" -ne 0 ]; then
  die "necesito root: ejecútalo como 'sudo bash install/system-setup.sh' (o prueba antes con --dry-run)"
fi
[ -f "$ROOT/etc/arch-release" ] || die "esto no parece Arch Linux (falta /etc/arch-release)"
# Only the main checkout, whose folders the agents' sandbox cannot write (docs/seguridad.md §1):
# from a git worktree under .worktrees/ an agent could plant the login page that sees the
# password. Decided without running git as root, as install/boot-setup.sh does: the main
# checkout has a .git folder, a worktree a .git file. A RYCE_ROOT test tree may come from anywhere.
if [ -z "$ROOT" ] && { [ ! -d "$REPO/.git" ] || [ -L "$REPO/.git" ]; }; then
  die "$REPO no es el checkout principal de git (¿un worktree?): ejecútalo desde la carpeta que creó git clone"
fi
for cmd in pacman systemctl findmnt getent awk; do
  command -v "$cmd" >/dev/null || die "falta la orden '$cmd': ¿es un Arch recién instalado con archinstall?"
done
if [ -z "$TARGET_USER" ]; then
  TARGET_USER=${SUDO_USER:-}
  [ -n "$TARGET_USER" ] || [ "$(id -u)" -eq 0 ] || TARGET_USER=$(id -un)
fi
[ -n "$TARGET_USER" ] && [ "$TARGET_USER" != root ] \
  || die "no sé cuál es tu usuario: lánzalo con sudo desde tu usuario o añade --user TU_USUARIO"
PASSWD=$(getent passwd "$TARGET_USER" || true)
[ -n "$PASSWD" ] || die "el usuario '$TARGET_USER' no existe (¿lo creaste en archinstall?)"
USER_HOME=$(cut -d: -f6 <<<"$PASSWD")
[ -d "$USER_HOME" ] || die "la carpeta personal $USER_HOME de $TARGET_USER no existe"

shopt -s nullglob
LISTS=("$HERE"/packages/*.txt)
shopt -u nullglob
[ ${#LISTS[@]} -gt 0 ] || die "no hay listas en install/packages/: ¿clonaste el repo completo?"
[ -f "$REPO/theme/boot/greeter/background.jpg" ] \
  || die "falta theme/boot/greeter/background.jpg, el fondo de la pantalla de acceso: python3 theme/boot/greeter.py"
# The login's files and the fonts, copied out of the repo before anything changes.
command -v python3 >/dev/null || die "falta python3 (pacman -S python; GUIA.md lo pide en archinstall)"
from_repo greeter install/boot/ryce-greeter install/boot/greeter/regreet.toml install/boot/greeter/regreet.css \
  install/boot/greeter/hyprland-uwsm.desktop theme/boot/greeter/background.jpg
from_repo page 'quickshell/greeter/*.qml' theme/boot/greeter/background.jpg
from_repo fonts 'assets/fonts/*.ttf' 'assets/fonts/*.otf'
from_repo licenses 'assets/fonts/licenses/*'
from_repo cursor assets/cursors/ryce-peonza/index.theme assets/cursors/ryce-peonza/cursors/
mapfile -t PKGS < <(sed 's/#.*//' "${LISTS[@]}" | awk 'NF && !seen[$1]++ {print $1}')

printf 'ryce-pc · configuración del sistema para %s%s\n' "$TARGET_USER" \
  "$([ "$DRY" = 1 ] && echo ' (simulación: no se cambia nada)')"
if [ "$DRY" = 1 ] && [ -z "$ROOT" ] && [ "$(id -u)" -ne 0 ]; then
  echo "    (sin root algunas comprobaciones, como los subvolúmenes, pueden anunciar cambios que ya están hechos)"
fi

# --- pacman --------------------------------------------------------------------------------
step "pacman: color, 10 descargas en paralelo, lista detallada"
pacman_conf ""

step "Paquetes (${#PKGS[@]} de install/packages, solo repos oficiales)"
rc=0
missing_out=$(pacman -T -- "${PKGS[@]}") || rc=$?
case $rc in
  0) ok "todos instalados" ;;
  127)
    mapfile -t MISSING <<<"$missing_out"
    change "instalar ${#MISSING[@]} paquetes que faltan:"
    printf '%s\n' "${MISSING[*]}" | fold -s -w 86 | sed 's/^/        /'
    if [ "$DRY" = 0 ]; then
      # Once the pin exists a full -Syu could die on a soname bump the pinned family is still
      # waiting for: re-runs only add what is missing; ryce-update does the upgrades.
      if grep -Eq '^[[:space:]]*IgnorePkg[[:space:]]*=(.*[[:space:]])?hyprland([[:space:]]|$)' "$ROOT/etc/pacman.conf"; then
        flags=(-S --needed)
      else
        flags=(-Syu --needed)
      fi
      [ "$YES" = 1 ] && flags+=(--noconfirm)
      [ "$YES" = 1 ] || echo "    pacman te preguntará; Intro acepta la opción por defecto."
      pacman "${flags[@]}" -- "${MISSING[@]}" \
        || die "pacman falló (el error está justo encima). Si dice «not found» o 404, actualiza antes con ryce-update. Luego vuelve a ejecutar este script: es seguro repetirlo."
    fi
    ;;
  *) die "pacman -T falló (código $rc): ¿base de datos de pacman bloqueada? Prueba 'sudo rm /var/lib/pacman/db.lck' solo si no hay otro pacman en marcha." ;;
esac

step "Fijar la familia Hyprland (IgnorePkg)"
pacman_conf "${HYPR_PIN[*]}" "${RETIRED_PIN[*]}"

# --- memory --------------------------------------------------------------------------------
step "Memoria: zram, swappiness, systemd-oomd, journal"
put_file /etc/systemd/zram-generator.conf 0644 <<EOF || echo "      (el nuevo tamaño de zram se aplica al reiniciar)"
$MANAGED
# zram swap of half the RAM, zstd. archinstall already passes zswap.enabled=0 when it sets up
# zram: zswap in front of zram would leave zram nearly unused (ArchWiki, Zram).
[zram0]
zram-size = ram / 2
compression-algorithm = zstd
swap-priority = 100
EOF

put_file /etc/sysctl.d/99-ryce.conf 0644 <<EOF || run sysctl --system >/dev/null
$MANAGED
# In-memory swap (zram) is far cheaper than dropping page cache: ArchWiki Zram values.
vm.swappiness = 180
vm.watermark_boost_factor = 0
vm.watermark_scale_factor = 125
vm.page-cluster = 0
# Many watchers at once (vite, tsc, editors, several Claude Code sessions).
fs.inotify.max_user_watches = 1048576
fs.inotify.max_user_instances = 1024
EOF

reload=0
put_file /etc/systemd/system/user@.service.d/90-ryce-oomd.conf 0644 <<EOF || reload=1
$MANAGED
# systemd-oomd only acts on units that opt in. Under sustained memory pressure it kills the
# worst cgroup inside the user session (one browser scope, one agent terminal), not a random
# process. Same values as Fedora's systemd-oomd-defaults.
[Service]
ManagedOOMMemoryPressure=kill
ManagedOOMMemoryPressureLimit=50%
EOF
[ "$reload" = 0 ] || run systemctl daemon-reload
enable_unit --now systemd-oomd.service

put_file /etc/systemd/journald.conf.d/90-ryce.conf 0644 <<EOF || run systemctl restart systemd-journald
$MANAGED
[Journal]
SystemMaxUse=1G
EOF

# --- boot: mainline kernel first ----------------------------------------------------------
# Arch kernel file names carry no version, so grub-mkconfig sorts vmlinuz-linux-lts above
# vmlinuz-linux and the LTS fallback became the DEFAULT entry (seen on the real PC, 2026-11-09:
# first boot came up on 6.18-lts). GRUB_TOP_LEVEL pins the mainline kernel on top; LTS stays
# one entry down, under "Advanced options".
step "Arranque: el núcleo principal primero, el LTS de reserva"
if [ -f "$ROOT/etc/default/grub" ]; then
  if grep -q '^GRUB_TOP_LEVEL="/boot/vmlinuz-linux"$' "$ROOT/etc/default/grub"; then
    ok "GRUB arranca por defecto el núcleo principal"
  else
    change "GRUB_TOP_LEVEL=/boot/vmlinuz-linux"
    run sed -i '/^GRUB_TOP_LEVEL=/d' "$ROOT/etc/default/grub"
    run sh -c "printf '%s\n' 'GRUB_TOP_LEVEL=\"/boot/vmlinuz-linux\"' >> '$ROOT/etc/default/grub'"
    [ -z "$ROOT" ] && run grub-mkconfig -o /boot/grub/grub.cfg
  fi
else
  warn "no hay /etc/default/grub: ¿se instaló con GRUB?"
fi

# --- snapshots -----------------------------------------------------------------------------
step "Instantáneas: snapper, snap-pac y copia de /boot"
snapper_changed=0
for cfg in root home; do
  file=/etc/snapper/configs/$cfg
  if [ ! -f "$ROOT$file" ]; then
    warn "no existe la configuración '$cfg' de snapper: en archinstall elige btrfs con instantáneas Snapper (GUIA.md, paso de discos)"
    continue
  fi
  if [ "$cfg" = root ]; then
    limits="TIMELINE_LIMIT_HOURLY=5 TIMELINE_LIMIT_DAILY=7 TIMELINE_LIMIT_WEEKLY=0 TIMELINE_LIMIT_MONTHLY=0 TIMELINE_LIMIT_YEARLY=0"
  else  # home: daily is enough; the caches below live outside its snapshots
    limits="TIMELINE_LIMIT_HOURLY=0 TIMELINE_LIMIT_DAILY=7 TIMELINE_LIMIT_WEEKLY=4 TIMELINE_LIMIT_MONTHLY=0 TIMELINE_LIMIT_YEARLY=0"
  fi
  # shellcheck disable=SC2086  # limits is a list of KEY=VALUE words
  render_kv "$ROOT$file" $limits > "$TMP/render" || die "no pude generar $file: no se ha tocado"
  put_file "$file" 0644 < "$TMP/render" || snapper_changed=1
done
# snapperd caches configs: restart it only if it is running.
[ "$snapper_changed" = 0 ] || run systemctl try-restart snapperd.service

if [ -f "$ROOT/usr/share/libalpm/hooks/05-snap-pac-pre.hook" ] || [ "$DRY" = 1 ]; then
  ok "snap-pac hace una instantánea antes y después de cada pacman"
else
  warn "snap-pac no está instalado: 'sudo pacman -S snap-pac'"
fi
if unit_enabled grub-btrfsd.service; then ok "grub-btrfsd añade las instantáneas al menú de GRUB"
else warn "grub-btrfsd.service no está activo: sin él no puedes arrancar una instantánea desde GRUB ('sudo systemctl enable --now grub-btrfsd')"; fi

# The ESP (/boot) is vfat, outside btrfs, so snapshots of / hold modules without the kernel
# that matches them. These are the hooks from ArchWiki "System backup#Snapshots and /boot
# partition" (linked from the Snapper page) with fixed folders instead of one timestamped
# folder per run: history lives in the snapshots, so the live copy never grows. snap-pac's
# 05-pre snapshot sees the copy left by the previous transaction; its zz-post sees this one's.
for when in pre post; do
  if [ "$when" = pre ]; then name=55-bootbackup_pre; at=PreTransaction
  else name=95-bootbackup_post; at=PostTransaction; fi
  put_file "/etc/pacman.d/hooks/$name.hook" 0644 <<EOF || true
$MANAGED
# ArchWiki: System backup#Snapshots and /boot partition. Copy of /boot in /.bootbackup/$when.
[Trigger]
Operation = Upgrade
Operation = Install
Operation = Remove
Type = Path
Target = usr/lib/modules/*/vmlinuz
Target = boot/*

[Action]
Depends = rsync
Description = Copying /boot into /.bootbackup/$when (ryce-pc)...
When = $at
Exec = /usr/bin/rsync -a --mkpath --delete /boot/ /.bootbackup/$when/
EOF
done

step "Subvolúmenes sin CoW (cachés y discos de VM fuera de las instantáneas)"
nocow_subvol "$ROOT/var/lib/docker" root:root 0710
nocow_subvol "$ROOT/var/lib/libvirt/images" root:root 0711
nocow_subvol "$USER_HOME/.cache" "$TARGET_USER:" 0700

# --- login ---------------------------------------------------------------------------------
step "Inicio de sesión: greetd con la pantalla de acceso de ryce"
# No [initial_session]: after the LUKS passphrase the login page asks for the user's password
# (two passwords, the user's choice on 2026-11-09). The greeter is install/boot/ryce-greeter:
# ryce's Quickshell page in cage, regreet if that cannot show, tuigreet if neither can. One
# look whatever the desktop theme; install/boot-setup.sh --only greeter installs the same
# files with backups and --rollback.
put_file /usr/local/bin/ryce-greeter 0755 < "$TMP/greeter/ryce-greeter" || true
put_file /etc/greetd/config.toml 0644 <<EOF || true
$MANAGED
# The LUKS passphrase opens the disk; this greeter then asks for the user's password.
[terminal]
vt = 1

[default_session]
command = "/usr/local/bin/ryce-greeter"
user = "greeter"
EOF
dm=$(readlink "$ROOT/etc/systemd/system/display-manager.service" 2>/dev/null || true)
if [ -n "$dm" ] && [ "${dm##*/}" != greetd.service ]; then
  warn "ya hay otro gestor de inicio activo (${dm##*/}): 'sudo systemctl disable ${dm##*/}' y vuelve a ejecutar este script"
else
  enable_unit greetd.service   # starts on the next boot, never under the TTY you are using now
fi

# The greeter user cannot read ~: the page and its background, regreet's files and the
# vendored fonts live in system paths. The fonts are the same set install/boot-setup.sh puts
# there for Plymouth. An old theme spool in /var/lib/ryce/greeter (greeter-sync, retired
# 2026-11-14) is no longer read and is left alone.
install_tree /usr/local/share/ryce/greeter "$TMP"/page/* || true
install_tree /usr/share/ryce/greeter "$TMP/greeter/background.jpg" || true
put_file /etc/greetd/regreet.toml 0644 < "$TMP/greeter/regreet.toml" || true
put_file /etc/greetd/regreet.css 0644 < "$TMP/greeter/regreet.css" || true
# «Hyprland (uwsm-managed)» out of the greeters' session lists (ryce-greeter reads
# /usr/local/share first; uwsm is not installed).
put_file /usr/local/share/wayland-sessions/hyprland-uwsm.desktop 0644 < "$TMP/greeter/hyprland-uwsm.desktop" || true
# The peonza cursor's XCursor half, for cage, regreet and the page (the wrapper's XCURSOR_THEME,
# regreet.toml's cursor_theme_name); libXcursor looks in /usr/share/icons, not /usr/local.
install_tree /usr/share/icons/ryce-peonza "$TMP/cursor/index.theme" || true
install_tree /usr/share/icons/ryce-peonza/cursors "$TMP"/cursor/cursors/* || true
fonts=0
install_tree /usr/local/share/fonts/ryce "$TMP"/fonts/* || fonts=1
install_tree /usr/local/share/fonts/ryce/licenses "$TMP"/licenses/* || fonts=1
if [ "$fonts" = 1 ] && [ -z "$ROOT" ]; then
  run fc-cache -f /usr/local/share/fonts/ryce || warn "fc-cache falló: la pantalla de acceso usará otras letras hasta el próximo arranque"
fi

# --- firewall -------------------------------------------------------------------------------
step "Cortafuegos (nftables) y Docker solo en localhost"
# sshd's LAN: the on-link IPv4 network of the default route's interface, read at each run and
# never written in this (published) file. Only a private range counts: with no network yet, or
# a public address on the link, sshd answers the tailnet alone until a run with the LAN up.
lan_cidr() {
  local dev net
  dev=$(ip -4 route show default 2>/dev/null | awk '{ for (i = 1; i < NF; i++) if ($i == "dev") { print $(i + 1); exit } }')
  [ -n "$dev" ] || return 0
  net=$(ip -4 route show dev "$dev" scope link proto kernel 2>/dev/null | awk '{ print $1; exit }')
  [[ $net =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$ ]] || return 0
  case $net in
    10.* | 192.168.* | 172.1[6-9].* | 172.2[0-9].* | 172.3[01].*) printf '%s\n' "$net" ;;
  esac
}
LAN=$(lan_cidr)
if [ -n "$LAN" ]; then
  SSH_LAN="ip saddr $LAN tcp dport ssh accept comment \"sshd: the home LAN only\""
else
  SSH_LAN="# sshd: no private LAN was up at install time, so the tailnet only (re-run with it up)"
  warn "no veo la red local (¿sin red?): sshd solo por la tailnet hasta que lo vuelvas a ejecutar con red"
fi

fw=0
put_file /etc/nftables.conf 0644 <<EOF || fw=1
#!/usr/bin/nft -f
$MANAGED
# Arch's default ruleset (nftables package) plus what a box with Docker and libvirt needs.
# Input: nothing from the LAN reaches the agents' dev servers, Docker or libvirt; only replies,
# loopback, ICMP, DHCPv6 replies, the VMs' DHCP/DNS, sshd from the home LAN and the tailnet
# only (never the global IPv6 address the ISP hands this PC), and Torre's
# remote port from the tailnet interface alone (it binds the 100.x address and nothing else).
# Forward: this PC routes only for its own containers and VMs (their bridges), never the LAN.
# "destroy table" replaces only this table: Docker's and libvirt's tables stay, so reloading
# (sudo nft -f /etc/nftables.conf) is always safe.

destroy table inet filter
table inet filter {
  chain input {
    type filter hook input priority filter
    policy drop

    ct state invalid drop comment "early drop of invalid connections"
    ct state {established, related} accept comment "allow tracked connections"
    iif lo accept comment "allow from loopback"
    meta l4proto { icmp, icmpv6 } accept comment "allow icmp"
    ip6 saddr fe80::/10 udp sport 547 udp dport 546 accept comment "allow DHCPv6 replies"
    iifname "virbr*" udp dport { 53, 67 } accept comment "libvirt VMs: DHCP and DNS"
    iifname "virbr*" tcp dport 53 accept comment "libvirt VMs: DNS over TCP"
    $SSH_LAN
    iifname "tailscale0" tcp dport ssh accept comment "sshd: the tailnet"
    iifname "tailscale0" tcp dport 47714 accept comment "Torre: its peers and the phone, over the tailnet only"
    pkttype host limit rate 5/second counter reject with icmpx type admin-prohibited
    counter
  }
  chain forward {
    type filter hook forward priority filter
    policy drop

    ct state {established, related} accept comment "replies to containers and VMs"
    iifname "docker0" accept comment "the default Docker bridge reaches out"
    iifname "br-*" accept comment "compose networks reach out"
    iifname "virbr*" accept comment "libvirt VMs reach out (NAT)"
  }
}
EOF
enable_unit nftables.service   # oneshot: loads the file at boot, then shows as inactive
if [ "$fw" = 0 ] && nft list table inet filter >/dev/null 2>&1; then
  ok "cortafuegos cargado"
else
  change "cargar el cortafuegos ahora"
  if [ "$DRY" = 0 ]; then
    if nft -c -f "$ROOT/etc/nftables.conf"; then nft -f "$ROOT/etc/nftables.conf"
    else warn "nftables rechaza /etc/nftables.conf ('sudo nft -c -f /etc/nftables.conf' dice por qué): sin cortafuegos hasta arreglarlo"; fi
  fi
fi

dk=0
if command -v python3 >/dev/null; then
  render_docker_daemon "$ROOT/etc/docker/daemon.json" > "$TMP/render" \
    || die "/etc/docker/daemon.json no es JSON válido: corrígelo (o bórralo) y vuelve a ejecutar"
  put_file /etc/docker/daemon.json 0644 < "$TMP/render" || dk=1
else
  change "/etc/docker/daemon.json: puertos de Docker solo en localhost (tras instalar python)"
fi
put_file /etc/systemd/system/docker.service.d/90-ryce-nftables.conf 0644 <<EOF || { dk=1; run systemctl daemon-reload; }
$MANAGED
# Docker adds its own tables after the firewall exists, never before it.
[Unit]
After=nftables.service
EOF
docker_was_active=0
if systemctl is-active --quiet docker.service 2>/dev/null; then docker_was_active=1; fi
enable_unit --now docker.service
if [ "$dk" = 1 ] && [ "$docker_was_active" = 1 ]; then
  change "reiniciar docker para aplicar su configuración (los contenedores en marcha se reinician)"
  run systemctl restart docker.service || warn "docker no rearranca: 'journalctl -u docker -b'"
fi

# --- services ------------------------------------------------------------------------------
step "Servicios"
put_file /etc/xdg/reflector/reflector.conf 0644 <<EOF || true
$MANAGED
# Weekly by reflector.timer: the 10 fastest HTTPS mirrors synced in the last 12 h, nearby first.
--save /etc/pacman.d/mirrorlist
--protocol https
--country ES,FR,PT,DE,NL
--age 12
--latest 20
--sort rate
--number 10
EOF
enable_unit --now NetworkManager.service
enable_unit --now libvirtd.service
enable_unit --now fstrim.timer
enable_unit --now paccache.timer
enable_unit --now reflector.timer
# The PC turned out to have Intel CNVi Wi-Fi + Bluetooth (8087:0026), not the 2.4 GHz card the
# shop page listed: bluez is in packages/apps.txt, so the adapter works for headphones.
enable_unit --now bluetooth.service

if [ -e "$ROOT/etc/libvirt/qemu/networks/autostart/default.xml" ]; then
  ok "la red 'default' de libvirt arranca sola"
else
  change "red 'default' de libvirt: arranque automático (NAT para las VMs)"
  run virsh -c qemu:///system net-autostart default >/dev/null \
    || warn "no pude marcar la red 'default' de libvirt: 'sudo virsh net-autostart default'"
fi

# --- the user ------------------------------------------------------------------------------
step "Tu usuario: grupos y carpetas"
add=()
for g in "${USER_GROUPS[@]}"; do
  line=$(getent group "$g" || true)
  if [ -z "$line" ]; then
    if [ "$DRY" = 1 ]; then add+=("$g"); else warn "el grupo '$g' no existe (¿falta su paquete?)"; fi
    continue
  fi
  case ",${line##*:}," in *",$TARGET_USER,"*) ;; *) add+=("$g") ;; esac
done
if [ ${#add[@]} -eq 0 ]; then
  ok "$TARGET_USER está en ${USER_GROUPS[*]}"
else
  change "añadir $TARGET_USER a: ${add[*]} (efectivo en tu próximo inicio de sesión)"
  run usermod -aG "$(IFS=,; echo "${add[*]}")" "$TARGET_USER"
fi
put_file /etc/profile.d/ryce-localbin.sh 0644 <<EOF || true
$MANAGED
# ~/.local/bin holds claude (native installer), ryce-update and ryce-term. Every login shell
# reads /etc/profile (greetd too, before starting Hyprland); fish adds the folder by itself.
case ":\$PATH:" in
  *":\$HOME/.local/bin:"*) ;;
  *) PATH="\$HOME/.local/bin:\$PATH"; export PATH ;;
esac
EOF
if [ -f "$USER_HOME/.config/user-dirs.dirs" ]; then
  ok "carpetas XDG creadas"
else
  # English names on purpose: links.tsv and the wallpaper service use ~/Pictures.
  change "carpetas XDG (Desktop, Downloads, Pictures…) en $USER_HOME"
  run runuser -u "$TARGET_USER" -- env HOME="$USER_HOME" XDG_CONFIG_HOME="$USER_HOME/.config" \
    LC_ALL=C.UTF-8 xdg-user-dirs-update || warn "xdg-user-dirs-update falló: ejecútalo tú sin sudo"
fi

# --- checks that only warn -----------------------------------------------------------------
step "Comprobaciones"
if pacman -Q thermald >/dev/null 2>&1; then
  warn "thermald está instalado: en Arrow Lake de sobremesa puede activar intel_powerclamp y frenar la memoria. Quítalo: 'sudo pacman -Rns thermald'"
else
  ok "thermald no está (a propósito, ver GUIA)"
fi
if [ -r "$ROOT/proc/cmdline" ] && ! grep -qw 'zswap.enabled=0' "$ROOT/proc/cmdline"; then
  warn "zswap sigue activo y le quita trabajo a zram: añade zswap.enabled=0 a GRUB_CMDLINE_LINUX_DEFAULT en /etc/default/grub y ejecuta 'sudo grub-mkconfig -o /boot/grub/grub.cfg'"
else
  ok "zswap desactivado en el arranque"
fi
lang=$(sed -n 's/^LANG=//p' "$ROOT/etc/locale.conf" 2>/dev/null | tr -d '"' | head -n 1 || true)
keymap=$(sed -n 's/^KEYMAP=//p' "$ROOT/etc/vconsole.conf" 2>/dev/null | tr -d '"' | head -n 1 || true)
if [ -n "$lang" ]; then ok "idioma del sistema: $lang"
else warn "/etc/locale.conf no define LANG: 'sudo localectl set-locale LANG=es_ES.UTF-8'"; fi
case $keymap in
  es*) ok "teclado de consola: $keymap" ;;
  *) warn "teclado de consola '${keymap:-sin definir}', no español: 'sudo localectl set-keymap es'" ;;
esac

# --- summary -------------------------------------------------------------------------------
printf '\n==> Resumen: %d cambios%s, %d avisos\n' "$CHANGES" \
  "$([ "$DRY" = 1 ] && echo ' (simulados)')" "${#WARNINGS[@]}"
for w in "${WARNINGS[@]}"; do printf '    ! %s\n' "$w"; done
echo "    · Grupos docker y libvirt = root sin contraseña: cualquier proceso tuyo (también un"
echo "      agente) puede hacerse root a través de Docker o de una VM. Lo explica docs/seguridad.md."
if [ "$DRY" = 1 ]; then
  echo "    Para aplicarlo: sudo bash install/system-setup.sh"
else
  echo "    Siguiente paso, SIN sudo: bash install/deploy.sh"
fi
