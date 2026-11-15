#!/usr/bin/env python3
"""Measure what a desktop feature costs, without root.

    python3 tools/perf_probe.py [--seconds 60] [--label NAME] [--json OUT]

Samples, over the window:
  * CPU of the compositor and the desktop's own processes (Hyprland, quickshell,
    awww-daemon, waybar, agentd), from /proc/<pid>/stat utime+stime, as % of ONE core;
  * GPU (i915): RC6 residency (time the render GT slept, higher is better) from
    /sys/class/drm/card*/gt/gt0/rc6_residency_ms, and the mean actual frequency
    from gt_act_freq_mhz sampled every 250 ms (0 while in RC6).

Package power (RAPL) and intel_gpu_top need root on this machine (energy_uj is 0400),
so they are left out on purpose: RC6 + frequency + compositor CPU are the proxies.
Run the same scene twice (feature off / on) and compare; tools/perf_probe.py prints
one line per run and appends it to --json when given.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path

WATCH = ("Hyprland", "quickshell", "qs", "awww-daemon", "waybar", "python3")
TICK = os.sysconf("SC_CLK_TCK")


def gpu_paths() -> tuple[Path | None, Path | None]:
    for card in sorted(glob.glob("/sys/class/drm/card*/gt/gt0/rc6_residency_ms")):
        base = Path(card).parents[2]
        return Path(card), base / "gt_act_freq_mhz"
    return None, None


def procs() -> dict[int, str]:
    out = {}
    for d in glob.glob("/proc/[0-9]*"):
        try:
            comm = Path(d, "comm").read_text().strip()
        except OSError:
            continue
        if comm in WATCH:
            if comm == "python3":
                try:
                    cmd = Path(d, "cmdline").read_bytes()
                except OSError:
                    continue
                if b"agentd" not in cmd:
                    continue
                comm = "agentd"
            out[int(Path(d).name)] = comm
    return out


def cpu_ticks(pid: int) -> int | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except OSError:
        return None
    return int(fields[11]) + int(fields[12])   # utime, stime (fields 14, 15)


def read_int(p: Path | None) -> int | None:
    if p is None:
        return None
    try:
        return int(p.read_text().strip())
    except (OSError, ValueError):
        return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--label", default="run")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)

    rc6_p, freq_p = gpu_paths()
    names = procs()
    t0 = {pid: cpu_ticks(pid) for pid in names}
    rc6_0 = read_int(rc6_p)
    start = time.monotonic()
    freqs = []
    while time.monotonic() - start < a.seconds:
        f = read_int(freq_p)
        if f is not None:
            freqs.append(f)
        time.sleep(0.25)
    wall = time.monotonic() - start
    rc6_1 = read_int(rc6_p)

    cpu: dict[str, float] = {}
    for pid, name in names.items():
        t1, before = cpu_ticks(pid), t0.get(pid)
        if before is None or t1 is None:
            continue
        cpu[name] = cpu.get(name, 0.0) + 100.0 * (t1 - before) / TICK / wall

    res = {
        "label": a.label,
        "seconds": round(wall, 1),
        "cpu_pct_one_core": {k: round(v, 2) for k, v in sorted(cpu.items())},
        "cpu_total": round(sum(cpu.values()), 2),
        "gpu_rc6_pct": None if rc6_0 is None or rc6_1 is None else round(100.0 * (rc6_1 - rc6_0) / (wall * 1000), 1),
        "gpu_mean_mhz": round(sum(freqs) / len(freqs), 1) if freqs else None,
        "gpu_busy_samples_pct": round(100.0 * sum(1 for f in freqs if f > 0) / len(freqs), 1) if freqs else None,
    }
    print(json.dumps(res, ensure_ascii=False))
    if a.json:
        prev = json.loads(a.json.read_text()) if a.json.exists() else []
        prev.append(res)
        a.json.write_text(json.dumps(prev, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
