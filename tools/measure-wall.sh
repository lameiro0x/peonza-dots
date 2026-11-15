#!/usr/bin/env bash
# What the live wallpaper costs, measured before anyone turns it on.
#
#   bash tools/measure-wall.sh [-s SECONDS] [-r RUNS] [-f DESK_JSON] -- IPC_CALL...
#
#   IPC_CALL   the command that reaches the shell's IpcHandlers, up to the target:
#                bash tools/measure-wall.sh -- qs -c ryce ipc call
#              it is run as `IPC_CALL desk toggle wall`.
#   -s         seconds per window (default 60)
#   -r         runs per state (default 3)
#   -f         the desk state file the shell writes (default
#              ${XDG_STATE_HOME:-~/.local/state}/ryce/desk.json): read to know whether the
#              wall is on, since the IPC only toggles.
#
# Protocol: on the focused workspace, which must be empty (with a window on it the wall
# unloads and there is nothing to measure), alternate wall off / wall on RUNS times; each
# window waits 5 s for the switch to settle, then runs tools/perf_probe.py for SECONDS.
# Alternating spreads any drift (thermals, background jobs) over both states. Prints every
# run, the medians and one Spanish verdict line; restores the wall's starting state.
# Rejects when, with the wall on, compositor + shell CPU rises more than 4 points of one
# core, GPU RC6 residency falls more than 15 points, or the mean GPU frequency rises more
# than 150 MHz. Exit 0 accepted, 1 rejected, 2 could not measure.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
SECONDS_PER=60
RUNS=3
SETTLE=5
STATE=${XDG_STATE_HOME:-$HOME/.local/state}/ryce/desk.json

die() { printf 'measure-wall: %s\n' "$*" >&2; exit 2; }
usage() { sed -n '4,13s/^# \{0,1\}//p' "${BASH_SOURCE[0]}" >&2; exit 2; }

while getopts 's:r:f:h' opt; do
  case $opt in
    s) SECONDS_PER=$OPTARG ;;
    r) RUNS=$OPTARG ;;
    f) STATE=$OPTARG ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))
[ "${1:-}" = "--" ] && shift
[ $# -gt 0 ] || usage
IPC=("$@")
case $SECONDS_PER$RUNS in *[!0-9]*) die "-s and -r take whole numbers" ;; esac
[ "$SECONDS_PER" -gt 0 ] && [ "$RUNS" -gt 0 ] || die "-s and -r must be positive"

for bin in python3 hyprctl "${IPC[0]}"; do
  command -v "$bin" >/dev/null 2>&1 || die "$bin not found"
done
[ -f "$HERE/perf_probe.py" ] || die "tools/perf_probe.py is missing next to this script"
[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || die "no Hyprland session in this environment (HYPRLAND_INSTANCE_SIGNATURE)"

tmp=$(mktemp -d)
start_state=""
cleanup() {
  [ -z "$start_state" ] || set_wall "$start_state" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT

# "<id> <windows>" of the focused workspace.
workspace() {
  local json
  json=$(hyprctl -j activeworkspace) || die "hyprctl cannot reach Hyprland"
  python3 -c 'import json, sys; w = json.loads(sys.argv[1]); print(w["id"], w["windows"])' "$json" \
    || die "unexpected answer from hyprctl activeworkspace: $json"
}

# "true" or "false": the wall as the shell last saved it (no file: the default, off).
wall_state() {
  python3 - "$STATE" <<'EOF'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        print("true" if json.load(f).get("wall") is True else "false")
except FileNotFoundError:
    print("false")
except (OSError, ValueError) as e:
    sys.exit(f"measure-wall: cannot read {sys.argv[1]}: {e}")
EOF
}

set_wall() {
  local want=$1
  [ "$(wall_state)" = "$want" ] && return 0
  "${IPC[@]}" desk toggle wall >/dev/null || die "the IPC call failed: ${IPC[*]} desk toggle wall"
  for _ in $(seq 1 30); do
    [ "$(wall_state)" = "$want" ] && return 0
    sleep 0.1
  done
  die "the wall did not switch to $want within 3 s (is $STATE the file this shell writes?)"
}

ws=$(workspace)
read -r ws_id ws_windows <<< "$ws"
[ "$ws_windows" = 0 ] || die "workspace $ws_id has $ws_windows window(s): measure on an empty workspace"
start_state=$(wall_state)
printf 'medir fondo animado: workspace %s, %s s por ventana, %s rondas (unos %s min)\n' \
  "$ws_id" "$SECONDS_PER" "$RUNS" $(( (RUNS * 2 * (SECONDS_PER + SETTLE) + 59) / 60 ))

for run in $(seq 1 "$RUNS"); do
  for state in false true; do
    set_wall "$state"
    sleep "$SETTLE"
    now=$(workspace)
    read -r now_id now_windows <<< "$now"
    [ "$now_id" = "$ws_id" ] && [ "$now_windows" = 0 ] \
      || die "the scene changed (workspace $now_id, $now_windows window(s)): keep workspace $ws_id empty during the run"
    label=$([ "$state" = true ] && echo on || echo off)
    python3 "$HERE/perf_probe.py" --seconds "$SECONDS_PER" --label "$label-$run" --json "$tmp/runs.json"
  done
done

python3 - "$tmp/runs.json" <<'EOF'
import json, statistics, sys

runs = json.load(open(sys.argv[1], encoding="utf-8"))
LIMITS = {"cpu": 4.0, "rc6": 15.0, "mhz": 150.0}


def median(state: str, key: str) -> float | None:
    vals = [r[key] for r in runs if r["label"].startswith(state + "-") and r[key] is not None]
    return statistics.median(vals) if vals else None


def es(v: float) -> str:
    return f"{v:+.1f}".replace(".", ",")


off = {k: median("off", k) for k in ("cpu_total", "gpu_rc6_pct", "gpu_mean_mhz")}
on = {k: median("on", k) for k in ("cpu_total", "gpu_rc6_pct", "gpu_mean_mhz")}
print(f"mediana apagado:   cpu {off['cpu_total']} %  rc6 {off['gpu_rc6_pct']} %  gpu {off['gpu_mean_mhz']} MHz")
print(f"mediana encendido: cpu {on['cpu_total']} %  rc6 {on['gpu_rc6_pct']} %  gpu {on['gpu_mean_mhz']} MHz")

d_cpu = on["cpu_total"] - off["cpu_total"]
fails = []
parts = [f"CPU {es(d_cpu)} puntos de un núcleo (límite +4)"]
if d_cpu > LIMITS["cpu"]:
    fails.append("CPU")
if off["gpu_rc6_pct"] is None or on["gpu_rc6_pct"] is None:
    parts.append("RC6 sin datos (no hay i915)")
else:
    d_rc6 = on["gpu_rc6_pct"] - off["gpu_rc6_pct"]
    parts.append(f"GPU dormida {es(d_rc6)} puntos (límite -15)")
    if -d_rc6 > LIMITS["rc6"]:
        fails.append("RC6")
if off["gpu_mean_mhz"] is None or on["gpu_mean_mhz"] is None:
    parts.append("frecuencia sin datos")
else:
    d_mhz = on["gpu_mean_mhz"] - off["gpu_mean_mhz"]
    parts.append(f"GPU {es(d_mhz)} MHz de media (límite +150)")
    if d_mhz > LIMITS["mhz"]:
        fails.append("MHz")

verdict = "RECHAZAR" if fails else "ACEPTAR"
print(f"veredicto: {verdict} el fondo animado: " + ", ".join(parts) + ("; se pasa en " + ", ".join(fails) if fails else "") + ".")
sys.exit(1 if fails else 0)
EOF
