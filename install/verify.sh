#!/usr/bin/env bash
# Day-one checks. Run as your user, from a terminal inside Hyprland, after the first login:
#
#   bash install/verify.sh [--no-probe]
#
# Read-only, with one exception: the probe tags the focused window `agentwait` for 4 s so you
# can see its waiting border, then removes the tag (--no-probe skips it). Exit 1 if any ❌.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROBE=1
case ${1:-} in
  '') ;;
  --no-probe) PROBE=0 ;;
  -h|--help) sed -n '2,7s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; exit 0 ;;
  *) echo "verify.sh: opción desconocida: $1 (usa --help)" >&2; exit 2 ;;
esac

PASS=0 FAIL=0 WARN=0
ok()   { PASS=$((PASS + 1)); printf '✅ %s\n' "$1"; }
bad()  { FAIL=$((FAIL + 1)); printf '❌ %s\n' "$1"; [ -z "${2:-}" ] || printf '   → %s\n' "$2"; }
note() { WARN=$((WARN + 1)); printf '⚠️  %s\n' "$1"; [ -z "${2:-}" ] || printf '   → %s\n' "$2"; }
have() { command -v "$1" >/dev/null 2>&1; }
enabled() { [ "$(systemctl is-enabled "$1" 2>/dev/null || true)" = enabled ]; }
in_hyprland() { [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && have hyprctl; }
json() {  # json PYTHON_EXPR < document: evaluate EXPR with the parsed document bound to d
  python3 -c 'import json, sys; d = json.load(sys.stdin); exec(sys.argv[1])' "$1"
}
section() { printf '\n%s\n' "$1"; }

# --- hardware -------------------------------------------------------------------------------
section "Hardware"
kernel=$(uname -r)
IFS=. read -r kmaj kmin _ <<<"$kernel"
kmin=${kmin%%[!0-9]*}
if [ "${kmaj:-0}" -gt 6 ] || { [ "${kmaj:-0}" -eq 6 ] && [ "${kmin:-0}" -ge 12 ]; }; then
  ok "kernel $kernel (≥ 6.12)"
else
  bad "kernel $kernel: Arrow Lake necesita 6.12 o más" "elige 'Arch Linux' (no un kernel antiguo) en GRUB y actualiza con ryce-update"
fi

if have lspci; then
  # First display-class device (VGA 0300, 3D 0302, display 0380) and its driver.
  gpu=$(lspci -nnk 2>/dev/null | awk -F'\t' '
    /^[^ \t]/ { if (name != "") exit; if ($0 ~ /\[03(00|02|80)\]/) name = $0; next }
    name != "" && /Kernel driver in use:/ { sub(/.*in use: /, ""); drv = $0 }
    END { if (name != "") print name "\t" drv }' || true)
  IFS=$'\t' read -r gpu_name gpu_drv <<<"$gpu" || true
  case ${gpu_drv:-} in
    i915) ok "GPU integrada con i915: ${gpu_name#* }" ;;
    xe) note "GPU integrada con xe (forzado a mano)" "en Arrow Lake lo probado es i915: quita xe.force_probe de GRUB" ;;
    *) bad "la GPU no tiene driver (${gpu_drv:-ninguno})" "mira 'lspci -nnk' y 'journalctl -k -b | grep -i i915'" ;;
  esac
  wifi=$(lspci -nn -d ::0280 2>/dev/null | head -n 1 || true)
  if [ -z "$wifi" ]; then ok "sin tarjeta Wi-Fi (Ethernet)"
  elif grep -qi intel <<<"$wifi"; then ok "Wi-Fi Intel: ${wifi#* }"
  else note "Wi-Fi: ${wifi#* }" "si es la TP-Link TL-WN881ND: solo 2,4 GHz y sin Bluetooth. Usa Ethernet, o cambia a una Intel AX210"; fi
else
  bad "falta lspci" "sudo pacman -S pciutils"
fi

if have vainfo && vainfo --display drm 2>&1 | grep -q 'iHD'; then
  ok "vídeo por hardware: VA-API con el driver iHD"
else
  bad "VA-API no usa iHD" "sudo pacman -S intel-media-driver libva-utils; luego 'vainfo --display drm'"
fi

vk=$(vulkaninfo --summary 2>/dev/null | sed -n 's/^[[:space:]]*deviceName[[:space:]]*=[[:space:]]*//p' | head -n 1 || true)
case $vk in
  *Intel*) ok "Vulkan: $vk" ;;
  *) bad "Vulkan no ve la GPU Intel (${vk:-nada})" "sudo pacman -S vulkan-intel vulkan-tools; luego 'vulkaninfo --summary'" ;;
esac

if [ -r /dev/accel/accel0 ] && [ -w /dev/accel/accel0 ]; then
  ok "NPU: /dev/accel/accel0 accesible"
elif [ -e /dev/accel/accel0 ]; then
  bad "NPU presente pero sin permiso" "cierra sesión y vuelve a entrar (grupo render)"
else
  bad "no hay NPU (/dev/accel/accel0)" "mira 'journalctl -k -b | grep -i vpu' y que intel-npu-driver esté instalado"
fi

if ls /sys/class/nvme/nvme0 >/dev/null 2>&1; then
  ok "NVMe: $(tr -s ' ' < /sys/class/nvme/nvme0/model 2>/dev/null || echo nvme0)"
else
  bad "no veo el disco NVMe" "en la BIOS (Supr al arrancar): Advanced → PCH Storage Configuration → VMD Disabled"
fi

links=$(nmcli -t -f TYPE,STATE device 2>/dev/null || true)
if grep -q '^ethernet:connected' <<<"$links"; then
  ok "Ethernet conectada"
elif grep -q '^wifi:connected' <<<"$links"; then
  note "conectado solo por Wi-Fi" "la tarjeta de serie es de 2,4 GHz y lenta: en cuanto puedas, cable o una Intel AX210"
else
  bad "sin red (ni Ethernet ni Wi-Fi)" "comprueba el cable y 'nmcli device'; para Wi-Fi: nmcli device wifi connect NOMBRE --ask"
fi

# --- system ---------------------------------------------------------------------------------
section "Sistema"
want=(docker kvm libvirt render video)
read -r -a mine <<<"$(id -nG)"
missing=()
for g in "${want[@]}"; do
  case " ${mine[*]} " in *" $g "*) ;; *) missing+=("$g") ;; esac
done
if [ ${#missing[@]} -eq 0 ]; then ok "estás en los grupos ${want[*]}"
else bad "te faltan los grupos: ${missing[*]}" "sudo bash install/system-setup.sh y luego cierra sesión y vuelve a entrar"; fi

if swapon --show=NAME --noheadings 2>/dev/null | grep -q zram0; then
  size=$(swapon --show=NAME,SIZE --noheadings 2>/dev/null | awk '/zram0/ {print $2}' || true)
  ok "zram activo ($size)"
else
  bad "zram no está activo" "reinicia; si sigue igual, 'systemctl status systemd-zram-setup@zram0'"
fi
if [ "$(cat /sys/module/zswap/parameters/enabled 2>/dev/null || echo N)" = Y ]; then
  note "zswap activo: zram apenas se usará" "añade zswap.enabled=0 en /etc/default/grub y 'sudo grub-mkconfig -o /boot/grub/grub.cfg'"
fi
if [ "$(sysctl -n vm.swappiness 2>/dev/null || true)" = 180 ]; then ok "ajustes de memoria (swappiness 180)"
else bad "vm.swappiness no es 180" "sudo bash install/system-setup.sh"; fi
if systemctl is-active --quiet systemd-oomd 2>/dev/null && [ -f /etc/systemd/system/user@.service.d/90-ryce-oomd.conf ]; then
  ok "systemd-oomd vigila tu sesión"
else
  bad "systemd-oomd no está activo o falta su ajuste" "sudo bash install/system-setup.sh"
fi

snap_missing=()
for f in /etc/snapper/configs/root /etc/snapper/configs/home \
         /usr/share/libalpm/hooks/05-snap-pac-pre.hook /etc/pacman.d/hooks/55-bootbackup_pre.hook; do
  [ -e "$f" ] || snap_missing+=("$f")
done
for u in snapper-timeline.timer snapper-cleanup.timer grub-btrfsd.service; do
  enabled "$u" || snap_missing+=("$u")
done
if [ ${#snap_missing[@]} -eq 0 ]; then ok "instantáneas: snapper root+home, snap-pac, copia de /boot, GRUB"
else bad "instantáneas incompletas: ${snap_missing[*]}" "sudo bash install/system-setup.sh (y GUIA.md, paso de archinstall)"; fi

if have pacman-conf; then
  mapfile -t ignored < <(pacman-conf IgnorePkg 2>/dev/null || true)
  mapfile -t pin < <(sed -n '/^HYPR_PIN=(/,/^)/p' "$HERE/system-setup.sh" | sed '1d;$d;s/#.*//' | tr -s ' \t' '\n' | sed '/^$/d')
  unpinned=()
  for p in "${pin[@]}"; do
    case " ${ignored[*]} " in *" $p "*) ;; *) unpinned+=("$p") ;; esac
  done
  if [ ${#pin[@]} -gt 0 ] && [ ${#unpinned[@]} -eq 0 ]; then ok "familia Hyprland fijada (${#pin[@]} paquetes en IgnorePkg)"
  else bad "sin fijar en IgnorePkg: ${unpinned[*]:-la lista HYPR_PIN}" "sudo bash install/system-setup.sh"; fi
  read -r -a retired <<<"$(sed -n 's/^RETIRED_PIN=(\(.*\))/\1/p' "$HERE/system-setup.sh")"
  stale=()
  for p in "${retired[@]}"; do
    case " ${ignored[*]} " in *" $p "*) stale+=("$p") ;; esac
  done
  [ ${#stale[@]} -eq 0 ] || bad "siguen fijados y ya no deben: ${stale[*]}" "sudo bash install/system-setup.sh"
else
  bad "falta pacman-conf" "¿es esto Arch?"
fi

if have pacman && pacman -Q thermald >/dev/null 2>&1; then
  bad "thermald instalado (en Arrow Lake de sobremesa puede frenar la memoria)" "sudo pacman -Rns thermald"
else
  ok "thermald no está"
fi

if enabled nftables.service && grep -q 'ryce-pc' /etc/nftables.conf 2>/dev/null \
   && grep -q '"127.0.0.1"' /etc/docker/daemon.json 2>/dev/null; then
  ok "cortafuegos activo y Docker publica solo en localhost"
else
  bad "falta el cortafuegos (nftables) o la configuración de Docker" "sudo bash install/system-setup.sh"
fi

svc_off=()
for u in greetd.service NetworkManager.service docker.service libvirtd.service fstrim.timer paccache.timer reflector.timer; do
  enabled "$u" || svc_off+=("$u")
done
if [ ${#svc_off[@]} -eq 0 ]; then ok "servicios del sistema activados"
else bad "sin activar: ${svc_off[*]}" "sudo bash install/system-setup.sh"; fi

src=$(findmnt -no SOURCE / 2>/dev/null || true)
if lsblk -nso TYPE "${src%%\[*}" 2>/dev/null | grep -qx crypt; then crypt=1; else crypt=0; fi
if [ ! -r /etc/greetd/config.toml ]; then
  note "no puedo leer /etc/greetd/config.toml"
elif grep -q '^\[initial_session\]' /etc/greetd/config.toml; then
  if [ "$crypt" = 1 ]; then ok "greetd: entrada automática (el disco cifrado es el inicio de sesión)"
  else bad "greetd entra solo y el disco NO está cifrado: cualquiera que encienda el PC entra" "sudo bash install/system-setup.sh (quita la entrada automática)"; fi
else
  if [ "$crypt" = 1 ]; then note "greetd pide usuario aunque el disco está cifrado" "sudo bash install/system-setup.sh activa la entrada automática"
  else ok "greetd: tuigreet pide usuario y contraseña"; fi
fi

# --- session --------------------------------------------------------------------------------
section "Sesión"
user_off=()
for u in agentd mako ryce-wallpaper hypridle; do
  systemctl --user is-active --quiet "$u.service" 2>/dev/null || user_off+=("$u")
done
if [ ${#user_off[@]} -eq 0 ]; then ok "servicios de usuario en marcha: agentd mako ryce-wallpaper hypridle"
else bad "parados: ${user_off[*]}" "systemctl --user status ${user_off[0]}.service; journalctl --user -u ${user_off[0]} -b"; fi

# The bar: Quickshell, or Waybar when Quickshell could not stay up (OnFailure=).
if systemctl --user is-active --quiet quickshell.service 2>/dev/null; then
  ok "barra: Quickshell (el marco)"
elif systemctl --user is-active --quiet waybar.service 2>/dev/null; then
  note "barra de reserva: Waybar, porque Quickshell no consiguió arrancar" \
    "journalctl --user -u quickshell -b | tail; cuando esté arreglado: systemctl --user reset-failed quickshell && systemctl --user start quickshell"
else
  bad "no hay barra: ni Quickshell ni Waybar están en marcha" "systemctl --user start waybar (la de reserva); luego journalctl --user -u quickshell -b"
fi

if in_hyprland; then
  hz=$(hyprctl -j monitors 2>/dev/null | json '
ms = [(m["name"], m["width"], m["height"], m["refreshRate"]) for m in d]
print(max((r for *_, r in ms), default=0))
print(", ".join(f"{n} {w}x{h}@{r:.0f}" for n, w, h, r in ms))' 2>/dev/null || true)
  best=$(head -n 1 <<<"$hz"); shown=$(sed -n 2p <<<"$hz")
  if [ -n "$best" ] && python3 -c 'import sys; sys.exit(float(sys.argv[1]) < 143)' "$best"; then
    ok "monitor a ≥ 143 Hz: $shown"
  else
    bad "ningún monitor a 144 Hz (${shown:-sin datos})" "revisa el cable (DisplayPort) y la línea de monitor en ~/.config/hypr; 'hyprctl monitors all' lista los modos"
  fi
  errs=$(hyprctl -j configerrors 2>/dev/null | json '
print("\n".join(e for e in (d if isinstance(d, list) else [d]) if isinstance(e, str) and e.strip()))' 2>/dev/null) \
    || errs="hyprctl configerrors no responde"
  if [ -z "$errs" ]; then ok "config de Hyprland sin errores"
  else bad "errores en la config de Hyprland:" "$(head -n 5 <<<"$errs" | tr '\n' ' ')"; fi
else
  bad "no estás dentro de Hyprland (o falta hyprctl)" "ejecuta esto desde una terminal de la sesión gráfica"
fi

roster=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/agentd/roster.json
if ! have claude; then
  note "Claude Code no está instalado: no comparo el roster de agentd"
elif [ ! -f "$roster" ]; then
  bad "agentd no ha escrito $roster" "systemctl --user status agentd"
else
  compare() {
    timeout 15 claude agents --json 2>/dev/null | python3 -c '
import json, os, sys
raw = json.load(sys.stdin)
if isinstance(raw, dict):
    raw = next((v for v in raw.values() if isinstance(v, list)), [])
live = {a["sessionId"] for a in raw if a.get("sessionId") and a.get("pid") and os.path.exists("/proc/" + str(a["pid"]))}
with open(sys.argv[1]) as f:
    mine = {s["sessionId"] for s in json.load(f)["sessions"]}
miss, extra = sorted(live - mine), sorted(mine - live)
if miss or extra:
    print("faltan " + (" ".join(s[:8] for s in miss) or "0") + " · sobran " + (" ".join(s[:8] for s in extra) or "0"))
    sys.exit(1)
print(len(live))' "$roster"
  }
  if n=$(compare) || { sleep 2; n=$(compare); }; then ok "agentd ve las mismas $n sesiones que 'claude agents'"
  else bad "agentd y 'claude agents' no coinciden: ${n:-sin respuesta}" "journalctl --user -u agentd -b | tail"; fi
fi

# --- the signature move ---------------------------------------------------------------------
if [ "$PROBE" = 1 ] && [ -t 0 ] && in_hyprland; then
  section "Prueba del borde de espera"
  addr=$(hyprctl -j activewindow 2>/dev/null | json 'print(d.get("address", "") if isinstance(d, dict) else "")' 2>/dev/null || true)
  if [[ $addr =~ ^0x[0-9a-f]+$ ]]; then
    tag() { hyprctl dispatch "hl.dsp.window.tag({ tag = \"$1agentwait\", window = \"address:$addr\" })" 2>&1 || true; }
    trap 'tag - >/dev/null' EXIT INT TERM
    echo "Mira esta ventana: durante 4 segundos su borde debería cambiar al color de aviso del tema, liso y sin brillo."
    reply=$(tag +)
    # agentd removes tags no session asked for, so keep re-applying it while you look.
    for _ in 1 2 3; do sleep 1; tag + >/dev/null; done
    sleep 1
    tag - >/dev/null
    trap - EXIT INT TERM
    if [ "$reply" != ok ]; then
      bad "Hyprland rechazó el dispatcher de etiquetas: $reply" "revisa la versión de Hyprland (0.57+, config Lua)"
    else
      read -r -p "¿Has visto el borde de aviso? [s/n] " seen
      case $seen in
        s|S|si|sí) ok "la ventana que espera lleva el borde de aviso" ;;
        *) bad "sin borde de aviso" "revisa la regla de ventana del tag agentwait en ~/.config/hypr/rules.lua" ;;
      esac
    fi
  else
    note "no hay ventana enfocada: prueba del borde omitida"
  fi
elif [ "$PROBE" = 1 ]; then
  note "prueba del borde de espera omitida (hace falta una terminal dentro de Hyprland)"
fi

printf '\nResultado: %d ✅ · %d ❌ · %d ⚠️\n' "$PASS" "$FAIL" "$WARN"
[ "$FAIL" -eq 0 ]
