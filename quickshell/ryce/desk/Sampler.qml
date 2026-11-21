import QtQuick
import Quickshell
import Quickshell.Io

// The PC, sampled every 2 s while `live`; nothing runs otherwise. One short `sh` per
// sample reads /proc and /sys with builtins only (`df` joins every 30 s): the GPU card
// and the hwmon sensors are found by name each time, since their indexes move between
// boots. Rates need two samples, so they read -1 until the second one; a pause starts
// them over instead of spanning it. `sampled()` fires after every sample; `fresh` says
// whether it carried new rates.
Scope {
    id: sampler
    property bool live
    readonly property var es: Qt.locale("es_ES")

    property var prev: null                 // previous raw counters, for the rates
    property int tick: 0
    property real cpu: -1
    property real memUsed: 0
    property real memTotal: 0
    property real gpuBusy: -1
    property int gpuMhz: 0
    property real temp: -1                  // CPU package (coretemp, k10temp, zenpower)
    property real gpuTemp: -1               // only a GPU with a hwmon (amdgpu, discrete Intel)
    property real ssdTemp: -1               // first NVMe drive
    property real diskUsed: 0
    property real diskTotal: 0
    property real rx: -1
    property real tx: -1
    property real uptime: -1
    property bool fresh: false              // this sample carried new rates (cpu, gpu, net)
    signal sampled()

    readonly property string script: `
read -r l < /proc/stat; echo "$l"
while read -r k v _; do
  case $k in MemTotal:) mt=$v ;; MemAvailable:) echo "mem $mt $v"; break ;; esac
done < /proc/meminfo
rx=0 tx=0
while IFS=' :' read -r i r _ _ _ _ _ _ _ t _; do
  case $i in Inter-*|face|lo|docker*|veth*|br-*|virbr*|tailscale*|wg*|tun*) ;;
    *) rx=$((rx + r)) tx=$((tx + t)) ;; esac
done < /proc/net/dev
echo "net $rx $tx"
read -r u _ < /proc/uptime; echo "up $u"
for c in /sys/class/drm/card*/gt/gt0/rc6_residency_ms; do
  [ -r "$c" ] || continue
  read -r rc6 < "$c"; read -r f < "\${c%/gt/gt0/rc6_residency_ms}/gt_act_freq_mhz"
  echo "gpu $f $rc6"; break
done
cpu= gpu= ssd=
for h in /sys/class/hwmon/hwmon*; do
  read -r n < "$h/name" || continue
  case $n in
    coretemp|k10temp|zenpower) [ -n "$cpu" ] || { read -r cpu < "$h/temp1_input" && echo "temp $cpu"; } ;;
    amdgpu|i915|xe) [ -n "$gpu" ] || { read -r gpu < "$h/temp1_input" && echo "gputemp $gpu"; } ;;
    nvme) [ -n "$ssd" ] || { read -r ssd < "$h/temp1_input" && echo "ssdtemp $ssd"; } ;;
  esac
done 2>/dev/null
if [ "$1" = 1 ]; then df -kP / | { read -r _; read -r _ s used _; echo "disk $s $used"; }; fi
exit 0`

    function ingest(text) {
        const now = {};
        for (const line of text.split("\n")) {
            const f = line.trim().split(/\s+/);
            if (f.length > 1) now[f[0]] = f.slice(1).map(Number);
        }
        const p = prev, up = now.up?.[0];
        const dt = p && up > p.up ? up - p.up : 0;

        if (now.cpu?.length >= 5) {
            const idle = now.cpu[3] + now.cpu[4], total = now.cpu.reduce((a, b) => a + b, 0);
            if (dt > 0 && total > p.cpuTotal)
                cpu = 100 * (1 - (idle - p.cpuIdle) / (total - p.cpuTotal));
            now.cpuIdle = idle;
            now.cpuTotal = total;
        }
        if (now.mem?.length === 2 && now.mem[0] > 0) {
            memTotal = now.mem[0] / 1048576;
            memUsed = (now.mem[0] - now.mem[1]) / 1048576;
        }
        if (now.gpu?.length === 2) {
            gpuMhz = now.gpu[0];
            // RC6 is the time the render engine slept: the rest of the interval it worked.
            if (dt > 0 && p.gpu)
                gpuBusy = Math.max(0, Math.min(100, 100 - (now.gpu[1] - p.gpu[1]) / (10 * dt)));
        }
        if (now.temp?.length === 1) temp = now.temp[0] / 1000;
        if (now.gputemp?.length === 1) gpuTemp = now.gputemp[0] / 1000;
        if (now.ssdtemp?.length === 1) ssdTemp = now.ssdtemp[0] / 1000;
        if (now.net?.length === 2 && dt > 0 && p.net) {
            rx = Math.max(0, (now.net[0] - p.net[0]) / dt);
            tx = Math.max(0, (now.net[1] - p.net[1]) / dt);
        }
        if (now.disk?.length === 2 && now.disk[0] > 0) {
            diskTotal = now.disk[0] / 1048576;
            diskUsed = now.disk[1] / 1048576;
        }
        if (up > 0) uptime = up;
        now.up = up;
        prev = now;
        fresh = dt > 0;
        sampled();
    }

    function rate(bps) {
        if (bps < 0) return "…";
        if (bps < 1e6) return Math.round(bps / 1e3) + DeskUi.unit + "kB/s";
        return (bps / 1e6).toLocaleString(es, "f", bps < 1e8 ? 1 : 0) + DeskUi.unit + "MB/s";
    }
    function since(s) {
        if (s < 0) return "…";
        const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
        const u = DeskUi.unit;
        return d > 0 ? `${d}${u}d ${h}${u}h` : h > 0 ? `${h}${u}h ${m}${u}min` : `${m}${u}min`;
    }
    function gb(v) { return v.toLocaleString(es, "f", v < 100 ? 1 : 0); }

    onLiveChanged: if (!live) { prev = null; tick = 0; }

    Timer {
        running: sampler.live
        interval: 2000
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            if (proc.running) return;
            proc.command = ["sh", "-c", sampler.script, "sh", sampler.tick % 15 === 0 ? "1" : "0"];
            proc.running = true;
            sampler.tick++;
        }
    }
    Process {
        id: proc
        stdout: StdioCollector {
            onStreamFinished: sampler.ingest(text)
        }
    }
}
