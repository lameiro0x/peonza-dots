pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io

// The bar's machine readouts, sampled every 3 s for every screen at once: CPU load and
// a minute of its history, memory in use, CPU package temperature, network rates.
// One long-lived `sh` answers each newline on its stdin with one line of raw counters,
// using builtins only, so a sample costs no fork. It finds the coretemp/k10temp hwmon
// once at start (the hwmon indexes move between boots, never within one). If the shell
// dies, the next tick starts it again and the rates start over.
Singleton {
    id: stats
    readonly property int history: 20          // samples kept: one minute

    property real cpu: -1                       // percent, -1 until two samples exist
    property var cpuHist: []
    property real mem: -1                       // percent of MemTotal in use
    property real temp: -1                      // °C, -1 without a sensor
    property real rx: -1                        // bytes per second
    property real tx: -1
    property var prev: null

    // Fields: idle total memTotal memAvailable rx tx tempMilli uptime
    readonly property string script: `
t=
for h in /sys/class/hwmon/hwmon*; do
  read -r n < "$h/name" 2>/dev/null || continue
  case $n in coretemp|k10temp|zenpower) t=$h/temp1_input; break ;; esac
done
while read -r _; do
  read -r _ u n s i w q sq st _ < /proc/stat
  while read -r k v _; do
    case $k in MemTotal:) mt=$v ;; MemAvailable:) ma=$v; break ;; esac
  done < /proc/meminfo
  rx=0 tx=0
  while IFS=' :' read -r f r _ _ _ _ _ _ _ x _; do
    case $f in Inter-*|face|lo|docker*|veth*|br-*|virbr*|tailscale*|wg*|tun*) ;;
      *) rx=$((rx + r)) tx=$((tx + x)) ;; esac
  done < /proc/net/dev
  c=-1; [ -n "$t" ] && { read -r c < "$t" || c=-1; }
  read -r up _ < /proc/uptime
  echo "$((i + w)) $((u + n + s + i + w + q + sq + st)) $mt $ma $rx $tx $c $up"
done`

    function ingest(line) {
        const f = line.trim().split(/\s+/).map(Number);
        if (f.length !== 8 || f.some(isNaN)) return;
        const [idle, total, memTotal, memAvail, inBytes, outBytes, milli, up] = f;
        const p = prev;
        const dt = p ? up - p.up : 0;
        if (dt > 0 && total > p.total) {
            cpu = Math.max(0, Math.min(100, 100 * (1 - (idle - p.idle) / (total - p.total))));
            const h = cpuHist.concat([cpu]);
            cpuHist = h.length > history ? h.slice(h.length - history) : h;
            // Counters reset when an interface goes away: never report a negative rate.
            rx = Math.max(0, (inBytes - p.rx) / dt);
            tx = Math.max(0, (outBytes - p.tx) / dt);
        }
        mem = memTotal > 0 ? 100 * (memTotal - memAvail) / memTotal : -1;
        temp = milli > 0 ? milli / 1000 : -1;
        prev = { idle: idle, total: total, rx: inBytes, tx: outBytes, up: up };
    }

    Process {
        id: shell
        running: true
        stdinEnabled: true
        command: ["sh", "-c", stats.script]
        stdout: SplitParser {
            onRead: line => stats.ingest(line)
        }
        onExited: stats.prev = null
    }
    Timer {
        running: true
        interval: 3000
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            if (!shell.running) shell.running = true;
            else shell.write("\n");
        }
    }
}
