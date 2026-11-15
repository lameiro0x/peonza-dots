#!/usr/bin/env bash
# peonza-dots: an Arch Linux desktop on Hyprland 0.57 (Lua config) and Quickshell.
#
#   git clone --depth 1 https://github.com/lameiro0x/peonza-dots ~/peonza-dots
#   cd ~/peonza-dots && ./install.sh
#
#   --dry-run          show the plan and what would change, change nothing
#   --yes              ask nothing, take the plan as shown (pacman gets --noconfirm)
#   --configs-only     links and theme only: no pacman, no sudo
#   --packages SET     core (default: desktop and base tools), apps (core + daily apps and
#                      VMs) or dev (apps + development tools); official repos only, no AUR
#   --theme ID         origen, grafito, ola, tinta or papel (default: the current one)
#   --system           also the XDG user folders and, if no other display manager is
#                      active, the greetd login page (asked one by one)
#   --boot             also theme GRUB and Plymouth (install/boot-setup.sh, as root)
#   --restore [STAMP]  put back the files one run moved aside (default: the latest)
#   --uninstall        remove the links and put your own files back
#   -h, --help         this help
#
# Nothing outside your home changes without --system or --boot. Files in the way are moved to
# ~/.local/state/ryce/backup/<stamp>/, never deleted, and a second run changes nothing.
set -euo pipefail

REPO=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd -P)
DEPLOY=(bash "$REPO/install/deploy.sh")
BOOT=$REPO/install/boot-setup.sh
TESTED_HYPR=0.57

DRY=0 YES=0 CONFIGS_ONLY=0 SET='' THEME='' SYSTEM=0 BOOT_STEP=0 UNDO='' STAMP=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  B=$'\e[1m' D=$'\e[2m' R=$'\e[31m' G=$'\e[32m' Y=$'\e[33m' C=$'\e[36m' N=$'\e[0m'
else
  B='' D='' R='' G='' Y='' C='' N=''
fi
STEP=0
SUMMARY=()

die()  { printf '\n%sinstall.sh:%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
step() { STEP=$((STEP + 1)); printf '\n%s%d%s  %s%s%s\n' "$C" "$STEP" "$N" "$B" "$*" "$N"; }
say()  { printf '   %s\n' "$*"; }
ok()   { printf '   %s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '   %s!%s %s\n' "$Y" "$N" "$*"; }
row()  { printf '   %s%-10s%s %s\n' "$D" "$1" "$N" "$2"; }
note() { SUMMARY+=("$1"$'\t'"$2"); }
tilde() { sed "s|^$HOME/|~/|"; }

ask() {  # ask QUESTION: yes only on y/yes; --yes says yes
  [ "$YES" = 0 ] || return 0
  [ -t 0 ] || die "no terminal to answer «$1»: run it in a terminal, or add --yes"
  local a
  printf '\n   %s%s%s [y/N] ' "$B" "$1" "$N"
  read -r a || a=
  case $a in [yY] | [yY][eE][sS]) return 0 ;; *) return 1 ;; esac
}

while [ $# -gt 0 ]; do
  case $1 in
    --dry-run) DRY=1 ;;
    --yes) YES=1 ;;
    --configs-only) CONFIGS_ONLY=1 ;;
    --packages) [ $# -ge 2 ] || die "--packages needs core, apps or dev"; SET=$2; shift ;;
    --theme) [ $# -ge 2 ] || die "--theme needs a theme id"; THEME=$2; shift ;;
    --system) SYSTEM=1 ;;
    --boot) BOOT_STEP=1 ;;
    --uninstall) UNDO=uninstall ;;
    --restore)
      UNDO=restore
      if [ $# -ge 2 ] && [ "${2#-}" = "$2" ]; then STAMP=$2; shift; fi
      ;;
    -h | --help) sed -n '2,19s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown option: $1 (see ./install.sh --help)" ;;
  esac
  shift
done
case ${SET:-core} in core | apps | dev) ;; *) die "--packages takes core, apps or dev, not '$SET'" ;; esac
[ "$CONFIGS_ONLY" = 0 ] || [ -z "$SET" ] || die "--configs-only installs no packages: drop --packages"
[ "$CONFIGS_ONLY" = 0 ] || [ $((SYSTEM + BOOT_STEP)) = 0 ] || die "--configs-only uses no root: drop --system and --boot"
if [ -n "$UNDO" ] && [ -n "$SET$THEME" ]; then die "--$UNDO takes only --dry-run and --yes"; fi
if [ -n "$UNDO" ] && [ $((SYSTEM + BOOT_STEP + CONFIGS_ONLY)) -gt 0 ]; then die "--$UNDO takes only --dry-run and --yes"; fi
SET=${SET:-core}
[ -d "${HOME:-}" ] || die "HOME is not set or is not a folder (HOME='${HOME:-}'): log in as your user and run it again"
CURRENT=$(readlink "$HOME/.local/state/ryce/theme/current" 2>/dev/null || true)

# The peonza in the chosen theme, in kitty only (graphics protocol; it leaves the cursor put).
banner() {
  local art=$REPO/themes/$1/greet/peonza.kitty sub="Arch · Hyprland $TESTED_HYPR · Quickshell"
  if [ -t 1 ] && [ "${TERM:-}" = xterm-kitty ] && [ -n "${KITTY_WINDOW_ID:-}" ] && [ -r "$art" ]; then
    printf '\n\n\n\n\e[4A'
    cat "$art"
    printf '\e[B\e[14G%s%s%s\e[B\e[14G%s%s%s\e[B\n' "$B" "peonza-dots" "$N" "$D" "$sub" "$N"
  else
    printf '\n%speonza-dots%s  %s%s%s\n' "$B" "$N" "$D" "$sub" "$N"
  fi
}

# ---- this machine and the plan: read-only -------------------------------------------------
[ "$(id -u)" -ne 0 ] || die "run it as your user, not root: it asks for sudo when it needs it"
[ -f "$REPO/install/links.tsv" ] || die "$REPO is not a full checkout: git clone it again"

# --uninstall and --restore: install/deploy.sh does the work from its manifest; shown first.
if [ -n "$UNDO" ]; then
  banner "${CURRENT:-origen}"
  step "${UNDO^}: your home only"
  args=(--"$UNDO")
  [ -z "$STAMP" ] || args+=("$STAMP")
  plan=$("${DEPLOY[@]}" "${args[@]}" --dry-run 2>&1) || die "$(printf '%s' "$plan" | tail -n 2)"
  printf '%s\n' "$plan" | sed -n 's/^  + \[simulación\] \(.*\) devuelto (copia del \(.*\))$/\1  (copy of \2)/p' \
    | tilde | sed 's/^/   ← /'
  printf '%s\n' "$plan" | grep -E '^  [!·] ' | tilde | sed 's/^  /   /' || true
  say "$(printf '%s\n' "$plan" | grep -c '\[simulación\] quito' || true) links into this repo to remove; your files above come back"
  if [ "$DRY" = 1 ]; then printf '\n   %sdry run: nothing changed.%s\n' "$D" "$N"; exit 0; fi
  ask "Go ahead?" || { say "Nothing changed."; exit 0; }
  out=$("${DEPLOY[@]}" "${args[@]}" 2>&1) || { printf '%s\n' "$out" | tail -n 5; die "install/deploy.sh --$UNDO failed (above)"; }
  printf '%s\n' "$out" | grep -E '^  [!·] ' | tilde | sed 's/^  /   /' || true
  ok "$(printf '%s\n' "$out" | sed -n \
    -e 's/^deploy --uninstall: \([0-9]*\) quitados · \([0-9]*\) devueltos · \([0-9]*\) .*/\1 links removed · \2 files back · \3 left in place/p' \
    -e 's/^deploy --restore \([0-9A-Za-z-]*\):\([0-9]*\) devueltos · \([0-9]*\) .*/\2 files back from \1 · \3 still in the backup/p')"
  if [ "$UNDO" = uninstall ]; then
    say "Left as they were: the packages (sudo pacman -Rns what you do not want), the files"
    say "in ~/.local/share/ryce and the icon themes generated in ~/.local/share/icons."
    if [ -d /var/backups/ryce ]; then
      say "If --boot or the login page ran: pkexec bash ${BOOT#"$PWD"/} --rollback"
      say "and, to log in as before, sudo systemctl disable greetd and enable your old login manager."
    fi
  fi
  exit 0
fi

[ -f /etc/arch-release ] || die "this is for Arch Linux (no /etc/arch-release here)"
for cmd in pacman python3; do command -v "$cmd" >/dev/null || die "'$cmd' is missing: is this an Arch install?"; done
[ "$CONFIGS_ONLY" = 1 ] || command -v sudo >/dev/null || die "sudo is missing (pacman -S sudo as root), or use --configs-only"
[ -e "$REPO/.git" ] || die "run it from a git clone (git clone --depth 1 https://github.com/lameiro0x/peonza-dots)"
if [ $((SYSTEM + BOOT_STEP)) -gt 0 ] && { [ ! -d "$REPO/.git" ] || [ -L "$REPO/.git" ]; }; then
  die "--system and --boot run as root and only from the main clone, not from a git worktree"
fi

mapfile -t CONF < <(python3 -I - "$REPO/contracts/constants.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1], encoding="utf-8"))
print(c["default_theme"], *c["themes"], sep="\n")
PY
) || die "contracts/constants.json is unreadable: git clone the repo again"
THEMES=("${CONF[@]:1}")
if [ -n "$THEME" ]; then
  case " ${THEMES[*]} " in *" $THEME "*) ;; *) die "no theme '$THEME': pick one of ${THEMES[*]}" ;; esac
fi
SHOWN=${THEME:-${CURRENT:-${CONF[0]}}}
banner "$SHOWN"

step "This machine"
DM=$(readlink /etc/systemd/system/display-manager.service 2>/dev/null || true)
DM=${DM##*/}
if [ -n "$DM" ]; then say "login manager: $DM"; else say "login manager: none (you log in on a TTY)"; fi
for dev in /sys/bus/pci/devices/*; do
  [ "$(cat "$dev/vendor" 2>/dev/null)" = 0x10de ] || continue
  case $(cat "$dev/class" 2>/dev/null) in 0x03*)
    warn "NVIDIA GPU: no driver is set up here; read the Hyprland wiki's NVIDIA page first"; break ;;
  esac
done
have=$(pacman -Q hyprland 2>/dev/null | awk '{print $2}' || true)
repo=$(LC_ALL=C pacman -Si hyprland 2>/dev/null | awk '$1 == "Version" {print $3; exit}' || true)
where=installed
[ -n "$have" ] || where="in the repos"
case ${have:-$repo} in
  "$TESTED_HYPR".*) ok "Hyprland ${have:-$repo} $where (tested: $TESTED_HYPR.x)" ;;
  '') warn "cannot tell which Hyprland the repos ship (sudo pacman -Sy updates the list)" ;;
  *) warn "Hyprland ${have:-$repo}: this config is written for $TESTED_HYPR.x and may need fixes" ;;
esac
say "Hyprland upgrades break configs every few months: holding them back (IgnorePkg) is up to you"

case $SET in
  core) LISTS=(base desktop) ;;
  apps) LISTS=(base desktop apps) ;;
  dev) LISTS=(base desktop apps dev) ;;
esac
FILES=()
for l in "${LISTS[@]}"; do FILES+=("$REPO/install/packages/$l.txt"); done
mapfile -t PKGS < <(sed 's/#.*//' "${FILES[@]}" | awk 'NF && !seen[$1]++ {print $1}')
# The lists were written for an Intel machine with snapper on btrfs: those parts only go where
# they fit (snap-pac's pacman hooks fail on every transaction without a snapper config).
SKIP=()
lspci 2>/dev/null | grep -qiE '(vga|display|3d)[^:]*: intel' ||
  SKIP+=(intel-media-driver vulkan-intel intel-gpu-tools intel-npu-driver linux-firmware-intel)
[ -e /etc/snapper/configs/root ] || SKIP+=(snap-pac)
if [ ${#SKIP[@]} -gt 0 ]; then
  mapfile -t PKGS < <(printf '%s\n' "${PKGS[@]}" | grep -vxF -f <(printf '%s\n' "${SKIP[@]}"))
fi
MISSING=()
if [ "$CONFIGS_ONLY" = 0 ]; then
  rc=0
  out=$(pacman -T -- "${PKGS[@]}") || rc=$?
  case $rc in
    0) ;;
    127) mapfile -t MISSING <<<"$out" ;;
    *) die "pacman -T failed (code $rc): is another pacman running?" ;;
  esac
fi

plan=$("${DEPLOY[@]}" --dry-run 2>&1) || die "the links cannot be planned:
$(printf '%s' "$plan" | grep -E '✗|deploy\.sh:' | head -n 5)"
CHANGES=$(printf '%s\n' "$plan" | grep -c '\[simulación\]' || true)
mapfile -t ASIDE < <(printf '%s\n' "$plan" | sed -n 's/^  + \[simulación\] \(.*\) apartado en .*/\1/p' | tilde)

step "The plan"
if [ "$CONFIGS_ONLY" = 1 ]; then row Packages "none (--configs-only)"
elif [ ${#MISSING[@]} -eq 0 ]; then row Packages "$SET: all ${#PKGS[@]} installed already"
else row Packages "$SET: ${#MISSING[@]} of ${#PKGS[@]} to install with sudo pacman -S --needed (no -Syu)"
fi
if [ "$CHANGES" = 0 ]; then row Configs "every link already in place"
else row Configs "$((CHANGES - ${#ASIDE[@]})) links into this repo; ${#ASIDE[@]} of your files moved aside, never deleted"
fi
for a in "${ASIDE[@]:0:8}"; do row "" "  → backup: $a"; done
[ ${#ASIDE[@]} -le 8 ] || row "" "  … and $((${#ASIDE[@]} - 8)) more"
printf '%s\n' "$plan" | sed -n 's/^  · \(.*\) es un enlace a \(.*\): lo sigo .*/\1 → \2 (a link of yours: written into, not moved)/p' \
  | tilde | while IFS= read -r a; do row "" "  $a"; done
row Theme "${THEME:-${CURRENT:-${CONF[0]} (default)}}"
if [ "$SYSTEM" = 1 ]; then row System "XDG folders; greetd login page$([ -z "$DM" ] || [ "$DM" = greetd.service ] || echo " (skipped: $DM is active)")"
else row System "untouched (--system adds XDG folders and the login page)"
fi
if [ "$BOOT_STEP" = 1 ]; then row Boot "GRUB and Plymouth themed as root, with a backup and --rollback"
else row Boot "untouched (--boot themes GRUB and Plymouth)"
fi
if [ ${#MISSING[@]} -gt 0 ]; then
  printf '\n'
  printf '%s\n' "${MISSING[*]}" | fold -s -w 84 | sed "s/^/   $D/; s/\$/$N/"
fi
# Packages already installed that one in the plan conflicts with: --noconfirm would answer
# «no» to pacman's «remove it?» and stop the whole install, so pacman asks for those.
CONFLICTS=(pipewire-pulse:pulseaudio) REPLACES=()
for pair in "${CONFLICTS[@]}"; do
  case " ${MISSING[*]} " in *" ${pair%%:*} "*) ;; *) continue ;; esac
  pacman -Q "${pair#*:}" >/dev/null 2>&1 || continue
  REPLACES+=("${pair#*:}")
  warn "${pair%%:*} replaces ${pair#*:}: pacman asks to remove ${pair#*:} (answer y). If it then"
  say "  names a package that needs ${pair#*:}, remove that first (sudo pacman -Rs PACKAGE)"
done

if [ "$DRY" = 1 ]; then
  printf '\n   %sdry run: nothing changed.%s Run it without --dry-run to apply.\n' "$D" "$N"
  exit 0
fi
ask "Go ahead?" || { say "Nothing changed."; exit 0; }

# ---- packages: official repos only (install/check-packages.py), never an implicit -Syu -----
if [ ${#MISSING[@]} -gt 0 ]; then
  step "Packages"
  flags=(-S --needed)
  [ "$YES" = 0 ] || [ ${#REPLACES[@]} -gt 0 ] || flags+=(--noconfirm)
  sudo pacman "${flags[@]}" -- "${MISSING[@]}" \
    || die "pacman failed (above), nothing of this step was installed. If it said «not found» or 404, the package list is old: sudo pacman -Syu. If it named a conflict, remove or replace that package as it says. Then ./install.sh again (safe to repeat)"
  note Packages "${#MISSING[@]} installed ($SET)"
else
  note Packages "$([ "$CONFIGS_ONLY" = 1 ] && echo "skipped (--configs-only)" || echo "nothing missing ($SET)")"
fi

# ---- links: deploy.sh moves what is in the way aside and records it for --uninstall --------
step "Configs"
out=$("${DEPLOY[@]}" 2>&1) || { printf '%s\n' "$out" | tail -n 15 | sed 's/^/   /'; die "install/deploy.sh failed (above)"; }
made=$(printf '%s\n' "$out" | grep -c ' → ' || true)
ok "$made links made, ${#ASIDE[@]} of your files moved aside"
printf '%s\n' "$out" | grep -E '^  ! ' | sed 's/^  /   /' || true
stamp=$(printf '%s\n' "$out" | sed -n 's|.* apartados en .*/backup/\([0-9A-Za-z-]*\)$|\1|p')
note Configs "$made links${stamp:+, your old files in ~/.local/state/ryce/backup/$stamp}"

# ---- theme ---------------------------------------------------------------------------------
if [ -n "$THEME" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
  # Outside Hyprland only the choice is saved (ryce-theme set would retheme this desktop's
  # GTK, fish and VS Code, which --uninstall cannot put back); Hyprland applies it at login.
  step "Theme"
  st=$HOME/.local/state/ryce/theme
  if ln -sfn "$THEME" "$st/current.tmp" && mv -fT "$st/current.tmp" "$st/current"; then
    ok "$THEME (applied when you log into Hyprland)"
  else
    warn "could not choose $THEME: ryce-theme set $THEME from Hyprland"
  fi
elif [ -n "$THEME" ]; then
  step "Theme"
  rc=0
  "$REPO/bin/ryce-theme" set "$THEME" >/dev/null 2>&1 || rc=$?
  case $rc in
    0) ok "$THEME" ;;
    3) ok "$THEME (the apps that are not running pick it up when they start)" ;;
    *) warn "ryce-theme set $THEME failed (code $rc): run it again from Hyprland" ;;
  esac
fi
note Theme "$(readlink "$HOME/.local/state/ryce/theme/current" 2>/dev/null || echo "$SHOWN")"

# ---- system, opt-in (the rest of install/system-setup.sh fits the author's PC: not offered) -
GREETER=0 SYS_DONE=() BOOT_NOTE=''
if [ "$SYSTEM" = 1 ]; then
  step "System"
  if [ -f "$HOME/.config/user-dirs.dirs" ]; then ok "XDG folders already set"
  elif ! command -v xdg-user-dirs-update >/dev/null; then warn "xdg-user-dirs-update is missing (pacman -S xdg-user-dirs)"
  elif ask "Create Desktop, Downloads, Pictures… in your home (English names)?"; then
    LC_ALL=C.UTF-8 xdg-user-dirs-update && SYS_DONE+=("XDG folders")
  fi
  if [ -n "$DM" ] && [ "$DM" != greetd.service ]; then
    say "$DM is your login manager: greetd left alone"
  elif [ ! -f /etc/greetd/config.toml ]; then
    warn "greetd is not installed (it is in the core packages): login page skipped"
  elif ask "Use greetd with the peonza login page (root: /etc/greetd, enabled for the next boot)?"; then
    GREETER=1
  fi
fi

# ---- boot and login as root, opt-in (boot-setup.sh keeps a backup set, has --rollback) -----
if [ "$BOOT_STEP" = 1 ] || [ "$GREETER" = 1 ]; then
  step "Boot and login (as root)"
  args=()
  if [ "$BOOT_STEP" = 1 ]; then
    args+=(--theme "$(readlink "$HOME/.local/state/ryce/theme/current" 2>/dev/null || echo "$SHOWN")")
    [ "$GREETER" = 1 ] || args+=(--only plymouth --only grub)
  else
    args+=(--only greeter)
  fi
  say "First what it would change (pkexec asks for your password):"
  pkexec bash "$BOOT" "${args[@]}" --dry-run || die "install/boot-setup.sh refused (above): nothing changed"
  if ask "Apply these boot and login changes?"; then
    pkexec bash "$BOOT" "${args[@]}" || die "install/boot-setup.sh failed (above). Undo: pkexec bash $BOOT --rollback"
    if [ "$GREETER" = 1 ]; then
      sudo systemctl enable greetd.service || die "greetd is set up but not enabled: sudo systemctl enable greetd.service"
      SYS_DONE+=("greetd login page from the next boot")
    fi
    BOOT_NOTE="$([ "$BOOT_STEP" = 0 ] || echo "GRUB and Plymouth, ")$([ "$GREETER" = 0 ] || echo "login page, ")undo: pkexec bash ${BOOT#"$PWD"/} --rollback"
  else
    BOOT_NOTE="skipped"
  fi
fi
if [ "$SYSTEM" = 1 ]; then
  if [ ${#SYS_DONE[@]} -eq 0 ]; then note System "nothing changed"; else note System "$(IFS=,; echo "${SYS_DONE[*]}" | sed 's/,/, /g')"; fi
fi
[ -z "$BOOT_NOTE" ] || note "As root" "$BOOT_NOTE"

# ---- summary -------------------------------------------------------------------------------
step "Done"
for s in "${SUMMARY[@]}"; do row "${s%%$'\t'*}" "${s#*$'\t'}"; done
printf '\n'
row Undo "./install.sh --uninstall   (links out, your own files back)"
row Next "log into Hyprland, then: bash install/verify.sh"
row Optional "Hito (Supabase), Aria (Navidrome) and agentd (Claude Code sessions) need their"
row "" "own setup; without it they stay quiet. The ryce-* commands live in ~/.local/bin."
