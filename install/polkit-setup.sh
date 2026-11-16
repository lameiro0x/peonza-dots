#!/usr/bin/env bash
# The password once, then a 30-minute window: what sudo's timestamp does, for every process.
# polkit remembers an authorization per process, and pkexec's subject is the process that
# runs it, so an agent (one new shell per command) was asked for the password on every
# command, and a loop on every turn (2026-11-16: 72 dialogs in an hour, libvirt and pkexec).
#
#   pkexec bash install/polkit-setup.sh [--dry-run]      set it up (a second run changes nothing)
#   pkexec bash install/polkit-setup.sh --check          is every piece in place? the window's state
#   pkexec bash install/polkit-setup.sh --rollback [--dry-run]
#   --root DIR   tests only: prefix every system path with DIR (commands are faked on PATH)
#
# How it works, each piece in a file of its own carrying the marker below:
#   - /etc/pam.d/polkit-1 replaces polkit's own /usr/lib/pam.d/polkit-1 with the same four
#     lines plus two: after a password is accepted (account) and when pkexec is about to run
#     a command (session), pam_exec runs /usr/local/lib/ryce/polkit-stamp, which touches
#     /run/ryce-polkit/<user>. Only root writes there (tmpfiles.d makes it at boot; polkit's
#     agent helper, which runs in a read-only /run, gets that one folder writable)
#   - 49-ryce-admin-window.rules lets an admin (wheel) of the active local session in, for any
#     action and without asking, while that stamp is under 30 minutes old; every pkexec that
#     runs extends it, but never past 8 hours since the password was last typed (the account
#     stage also touches <user>.auth): a periodic job cannot keep it open for days. Outside the
#     window the usual rules ask, and the same pkexec command that was refused (or is still
#     waiting) is not asked again for 2 minutes: a loop cannot flood the screen. SSH and
#     inactive sessions never get the window. Hygiene, not a wall: whatever is root inside the
#     window can stamp, as it could install its own rule
#
# Order is safety: the stamp folder and the helper's permission first, then the stamp program,
# then PAM (from then on stamps are written, but nothing reads them), the rule last. Rollback
# removes the rule first. The PAM file is written only when polkit's own is still the stack
# below; if a polkit update changes it, this refuses instead of shadowing the new one.
set -euo pipefail

MANAGED="Managed by ryce-pc (install/polkit-setup.sh): change it in the repo and re-run."
ARGS=("$@")
ROOT=""
DRY=0
MODE=apply
CHANGES=0
FAILS=0
WINDOW_MIN=30
CAP_H=8

RULE=etc/polkit-1/rules.d/49-ryce-admin-window.rules
PAM=etc/pam.d/polkit-1
VENDOR_PAM=usr/lib/pam.d/polkit-1
STAMP_BIN=usr/local/lib/ryce/polkit-stamp
TMPFILES=etc/tmpfiles.d/ryce-polkit.conf
DROPIN=etc/systemd/system/polkit-agent-helper@.service.d/ryce-polkit.conf
STAMPS=run/ryce-polkit
OURS=("$RULE" "$PAM" "$STAMP_BIN" "$TMPFILES" "$DROPIN")

die()  { printf '\npolkit-setup.sh: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }
ok()   { printf '    ✓ %s\n' "$*"; }
bad()  { printf '    ✗ %s\n' "$*"; FAILS=$((FAILS + 1)); }
change() {
  CHANGES=$((CHANGES + 1))
  if [ "$DRY" = 1 ]; then printf '    + [simulación] %s\n' "$*"; else printf '    + %s\n' "$*"; fi
}
run() {  # run CMD...: the command, or its echo under --dry-run
  if [ "$DRY" = 1 ]; then printf '      (simulado) %s\n' "$*"; return 0; fi
  "$@"
}

while [ $# -gt 0 ]; do
  case $1 in
    --dry-run) DRY=1 ;;
    --rollback) MODE=rollback ;;
    --check) MODE=check ;;
    --root) [ $# -gt 1 ] || die "--root necesita una carpeta"; ROOT=${2%/}; shift ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "opción desconocida: $1 (mira --help)" ;;
  esac
  shift
done
[ "$MODE" != check ] || [ "$DRY" = 0 ] || die "--dry-run no va con --check"

if [ -z "$ROOT" ] && [ "$(id -u)" -ne 0 ] && ! { [ "$DRY" = 1 ] && [ "$MODE" != check ]; }; then
  die "necesito root: pkexec bash $0 ${ARGS[*]} (o prueba antes con --dry-run)"
fi
for c in systemctl systemd-tmpfiles stat install mktemp; do
  command -v "$c" >/dev/null || die "falta la orden $c"
done

# --- the fixed texts ---------------------------------------------------------------------------

rule_text() {
  cat <<EOF
// $MANAGED
// The password once, then a window (sudo's timestamp, for every process at once). polkit keeps
// an authorization per process and pkexec's subject is the process that runs it, so an agent
// (a new shell per command) was asked on every command. An admin (wheel) of the active local
// session who typed the password, or ran pkexec, in the last $WINDOW_MIN minutes is let in
// without asking, for at most $CAP_H hours since the password was last typed:
// /usr/local/lib/ryce/polkit-stamp marks those moments from PAM (/etc/pam.d/polkit-1) in
// /run/ryce-polkit/<user> (last use) and <user>.auth (last password), which only root writes.
// Outside the window the usual rules ask; the same pkexec command refused or still waiting is
// not asked again for two minutes. To close it now: pkexec rm -f /run/ryce-polkit/\$USER*

var RYCE_WINDOW_S = $((WINDOW_MIN * 60));
var RYCE_CAP_S = $((CAP_H * 3600));
var RYCE_REPEAT_MS = 120000;
var RYCE_RECHECK_MS = 5000;
var ryceSeen = {};
var ryceAsked = {};

function ryceRecent(stamp, now, limit) {
    var age = now / 1000 - stamp;
    return stamp > 0 && age > -60 && age < limit;
}

function ryceFresh(user) {
    var now = Date.now();
    var seen = ryceSeen[user];
    if (!seen || now - seen.checked >= RYCE_RECHECK_MS || now < seen.checked) {
        var use = 0, auth = 0;
        try {
            var dir = "/run/ryce-polkit/";
            var out = String(polkit.spawn(["/usr/bin/stat", "-c", "%Y", dir + user, dir + user + ".auth"])).split("\n");
            use = parseInt(out[0], 10) || 0;
            auth = parseInt(out[1], 10) || 0;
        } catch (e) {
            use = 0;
            auth = 0;
        }
        seen = ryceSeen[user] = {use: use, auth: auth, checked: now};
    }
    return ryceRecent(seen.use, now, RYCE_WINDOW_S) && ryceRecent(seen.auth, now, RYCE_CAP_S);
}

polkit.addRule(function (action, subject) {
    if (!subject.local || !subject.active || !subject.isInGroup("wheel")) {
        return polkit.Result.NOT_HANDLED;
    }
    if (ryceFresh(subject.user)) {
        return polkit.Result.YES;
    }
    if (action.id != "org.freedesktop.policykit.exec") {
        return polkit.Result.NOT_HANDLED;
    }
    var now = Date.now();
    var command = String(action.lookup("command_line"));
    var key = subject.user + "\\n" + command;
    for (var k in ryceAsked) {
        if (now - ryceAsked[k] >= RYCE_REPEAT_MS || now < ryceAsked[k]) {
            delete ryceAsked[k];
        }
    }
    if (key in ryceAsked) {
        polkit.log("ryce-polkit: " + subject.user + " pidió otra vez «" + command +
                   "» antes de 2 minutos, sin contraseña de por medio: denegado sin preguntar");
        return polkit.Result.NO;
    }
    ryceAsked[key] = now;
    return polkit.Result.NOT_HANDLED;
});
EOF
}

stamp_text() {
  cat <<EOF
#!/bin/sh
# $MANAGED
# Run by pam_exec from /etc/pam.d/polkit-1 once polkit let an admin in: «account» after the
# agent accepted a password, «open_session» when pkexec is about to run a command. Touches
# /run/ryce-polkit/<user> (last use) and, after a password, <user>.auth too; the rule
# 49-ryce-admin-window.rules lets that user in while the first is under $WINDOW_MIN minutes old
# and the second under $CAP_H hours. Optional in PAM: whatever happens here, it exits 0.
PATH=/usr/bin
export PATH
dir=/run/ryce-polkit
case \${PAM_TYPE-} in
  account) user=\${PAM_USER-} auth=1 ;;
  open_session)
    # pkexec opens the session for the target (root); the caller is pkexec's real uid.
    uid=\$(awk '\$1 == "Uid:" { print \$2; exit }' "/proc/\$PPID/status" 2>/dev/null) || exit 0
    user=\$(id -nu "\$uid" 2>/dev/null) || exit 0
    auth=0 ;;
  *) exit 0 ;;
esac
case \$user in '' | -* | *[!a-z0-9_-]*) exit 0 ;; esac
if [ ! -d "\$dir" ] || [ -L "\$dir" ]; then exit 0; fi
touch -- "\$dir/\$user" 2>/dev/null || exit 0
if [ "\$auth" = 1 ]; then touch -- "\$dir/\$user.auth" 2>/dev/null || exit 0; fi
logger -t ryce-polkit -- "ventana de administración de \$user abierta o alargada ($WINDOW_MIN min, \$PAM_TYPE)" 2>/dev/null
exit 0
EOF
}

# polkit's own stack, as /usr/lib/pam.d/polkit-1 ships it (comments and blank lines aside).
VENDOR_LINES=$'auth include system-auth\naccount include system-auth\npassword include system-auth\nsession include system-auth'
pam_text() {
  cat <<EOF
#%PAM-1.0
# $MANAGED
# polkit's own stack (/usr/lib/pam.d/polkit-1, which this file shadows) plus the two pam_exec
# lines that open the admin window of 49-ryce-admin-window.rules: account runs only after the
# password was accepted, session only when pkexec was authorized and is about to run.

auth       include      system-auth
account    include      system-auth
account    optional     pam_exec.so quiet seteuid /$STAMP_BIN
password   include      system-auth
session    include      system-auth
session    optional     pam_exec.so quiet seteuid /$STAMP_BIN
EOF
}

tmpfiles_text() {
  cat <<EOF
# $MANAGED
# The stamps of the admin window (49-ryce-admin-window.rules): written by root alone.
d /$STAMPS 0755 root root -
EOF
}

dropin_text() {
  cat <<EOF
# $MANAGED
# polkit's agent helper checks the password with /run read-only (ProtectSystem=strict); the
# stamp folder of the admin window is the one place its PAM stack may write.
[Service]
ReadWritePaths=-/$STAMPS
EOF
}

# --- files ---------------------------------------------------------------------------------------

check_target() {  # REL: absent, or a plain file carrying the marker, in a folder that is no link
  local p="$ROOT/$1" d
  d=$(dirname "$p")
  [ ! -L "$d" ] || die "$(dirname "/$1") es un enlace simbólico: no lo toco"
  [ ! -L "$p" ] || die "/$1 es un enlace simbólico: no lo toco"
  [ ! -e "$p" ] || [ -f "$p" ] || die "/$1 existe y no es un fichero normal: no lo toco"
  if [ -f "$p" ] && ! grep -qF "$MANAGED" "$p"; then
    die "/$1 ya existe y no es de ryce-pc: revísalo a mano (no he cambiado nada)"
  fi
}
ours() { [ -f "$ROOT/$1" ] && [ ! -L "$ROOT/$1" ] && grep -qF "$MANAGED" "$ROOT/$1"; }
same() {  # same REL TEXTFN MODE: REL holds exactly that text with that mode
  [ -f "$ROOT/$1" ] && [ ! -L "$ROOT/$1" ] && [ "$(cat "$ROOT/$1")" = "$("$2")" ] \
    && [ "$(stat -c %a "$ROOT/$1")" = "${3#0}" ]
}
put() {  # put REL TEXTFN [MODE]: write REL unless it already holds exactly that; 0 when it changed
  local rel=$1 fn=$2 mode=${3:-0644} p="$ROOT/$1" tmpf
  if same "$rel" "$fn" "$mode"; then ok "/$rel"; return 1; fi
  change "/$rel"
  [ "$DRY" = 1 ] && return 0
  install -d -m 0755 "$(dirname "$p")"
  tmpf=$(mktemp "$(dirname "$p")/.ryce-polkit.XXXXXX")
  if ! { "$fn" > "$tmpf" && chmod "$mode" "$tmpf" && mv -f "$tmpf" "$p"; }; then
    rm -f "$tmpf"; die "no pude escribir /$rel"
  fi
}
drop() {  # drop REL: remove REL when it is ours; 0 when removed
  local rel=$1
  [ -e "$ROOT/$rel" ] || [ -L "$ROOT/$rel" ] || { ok "/$rel (no estaba)"; return 1; }
  ours "$rel" || { printf '    ! /%s no es de ryce-pc: lo dejo\n' "$rel"; return 1; }
  change "quitar /$rel"
  run rm -f "$ROOT/$rel"
}
vendor_lines() {  # polkit's PAM stack without comments, blank lines or column padding
  sed -e 's/#.*//' -e 's/[[:space:]]\{1,\}/ /g' -e 's/^ //' -e 's/ $//' "$ROOT/$VENDOR_PAM" | grep -v '^$'
}
stamps_dir_sound() {  # /run/ryce-polkit: a real folder of root's, 0755
  local d="$ROOT/$STAMPS"
  [ -d "$d" ] && [ ! -L "$d" ] && { [ -n "$ROOT" ] || [ "$(stat -c '%u %a' "$d")" = "0 755" ]; }
}
invoker() {  # the user who ran this through pkexec or sudo, if any
  local uid=${PKEXEC_UID:-${SUDO_UID:-}}
  [ -n "$uid" ] && [ "$uid" != 0 ] && id -nu "$uid" 2>/dev/null
}

# --- modes -------------------------------------------------------------------------------------

apply() {
  local rel dirty=0
  for rel in "${OURS[@]}"; do check_target "$rel"; done
  [ -f "$ROOT/$VENDOR_PAM" ] || die "falta /$VENDOR_PAM (¿polkit sin instalar?): no cambio nada"
  if [ "$(vendor_lines)" != "$VENDOR_LINES" ]; then
    die "/$VENDOR_PAM ya no es la pila que conozco (¿polkit actualizado?): revisa pam_text() en este script; no cambio nada"
  fi

  step "La carpeta de las marcas: solo root escribe en ella"
  put "$TMPFILES" tmpfiles_text || true
  if stamps_dir_sound; then ok "/$STAMPS"
  else
    change "/$STAMPS"
    if [ -n "$ROOT" ]; then run install -d -m 0755 "$ROOT/$STAMPS"
    else run systemd-tmpfiles --create "/$TMPFILES"; fi
  fi
  if put "$DROPIN" dropin_text; then dirty=1; fi
  if [ "$dirty" = 1 ]; then change "systemd relee el ayudante de polkit"; run systemctl daemon-reload; fi

  step "El programa que pone la marca, y PAM que lo llama"
  put "$STAMP_BIN" stamp_text 0755 || true
  put "$PAM" pam_text || true

  step "La regla de polkit (la última: es la que deja pasar)"
  put "$RULE" rule_text || true

  local who
  if who=$(invoker) && [ "$DRY" = 0 ]; then
    step "Ventana abierta para $who"
    touch -- "$ROOT/$STAMPS/$who" "$ROOT/$STAMPS/$who.auth" \
      && ok "$WINDOW_MIN minutos desde ahora; cada pkexec la alarga, como mucho $CAP_H horas"
  fi
  printf '\n==> %d cambios%s\n' "$CHANGES" "$([ "$DRY" = 1 ] && echo ' (simulados)')"
}

check() {
  local rel
  step "Piezas"
  same "$TMPFILES" tmpfiles_text 0644 && ok "/$TMPFILES" || bad "/$TMPFILES falta o cambió"
  stamps_dir_sound && ok "/$STAMPS" || bad "/$STAMPS falta o no es de root con 0755"
  same "$DROPIN" dropin_text 0644 && ok "/$DROPIN" || bad "/$DROPIN falta o cambió"
  same "$STAMP_BIN" stamp_text 0755 && ok "/$STAMP_BIN" || bad "/$STAMP_BIN falta o cambió"
  same "$PAM" pam_text 0644 && ok "/$PAM" || bad "/$PAM falta o cambió"
  same "$RULE" rule_text 0644 && ok "/$RULE" || bad "/$RULE falta o cambió"
  if [ -f "$ROOT/$VENDOR_PAM" ] && [ "$(vendor_lines)" = "$VENDOR_LINES" ]; then
    ok "/$VENDOR_PAM sigue siendo la pila de debajo"
  else
    bad "/$VENDOR_PAM cambió (¿polkit actualizado?): /$PAM ya no la copia; vuelve a ejecutar sin --check"
  fi

  step "La ventana"
  local f now use auth left
  now=$(date +%s)
  for f in "$ROOT/$STAMPS"/*; do
    [ -f "$f" ] || continue
    case $f in *.auth) continue ;; esac
    use=$(( now - $(stat -c %Y "$f") ))
    auth=$(( CAP_H * 3600 ))
    [ ! -f "$f.auth" ] || auth=$(( now - $(stat -c %Y "$f.auth") ))
    if [ "$use" -lt $((WINDOW_MIN * 60)) ] && [ "$auth" -lt $((CAP_H * 3600)) ]; then
      left=$(( WINDOW_MIN * 60 - use ))
      [ $(( CAP_H * 3600 - auth )) -ge "$left" ] || left=$(( CAP_H * 3600 - auth ))
      ok "$(basename "$f"): abierta, se cierra en $(( (left + 59) / 60 )) min si nada la usa (la contraseña se escribió hace $((auth / 60)) min)"
    else
      ok "$(basename "$f"): cerrada"
    fi
  done
  if [ "$FAILS" -eq 0 ]; then printf '\n==> todo en su sitio\n'; return 0; fi
  printf '\n==> %d problemas: pkexec bash %s\n' "$FAILS" "$0"
  return 1
}

rollback() {
  step "La regla primero: nadie entra ya sin contraseña"
  drop "$RULE" || true
  step "PAM vuelve a la pila de polkit, y fuera el programa de las marcas"
  drop "$PAM" || true
  drop "$STAMP_BIN" || true
  step "La carpeta de las marcas"
  if drop "$DROPIN"; then change "systemd relee el ayudante de polkit"; run systemctl daemon-reload; fi
  drop "$TMPFILES" || true
  if [ -d "$ROOT/$STAMPS" ] && [ ! -L "$ROOT/$STAMPS" ]; then
    change "quitar /$STAMPS"; run rm -rf --one-file-system "$ROOT/$STAMPS"
  fi
  printf '\n==> %d cambios%s\n' "$CHANGES" "$([ "$DRY" = 1 ] && echo ' (simulados)')"
}

case $MODE in
  apply) apply ;;
  check) check ;;
  rollback) rollback ;;
esac
