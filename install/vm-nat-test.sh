#!/usr/bin/env bash
# Pretend to be a libvirt NAT guest: a network namespace plugged into virbr0 (192.168.122.0/24),
# then reach the internet through the host's forward chain and libvirt's masquerade.
# Needs root. Leaves nothing behind (namespace, veth and /etc/netns entry are removed on exit).
set -uo pipefail   # no -e: every check runs and reports, the trap cleans up
ns=ryce-vmtest host=ryce-vt0
[ "$(id -u)" = 0 ] || { echo "run it as root: pkexec /usr/bin/bash $0"; exit 2; }
for b in ip ping getent curl; do
  command -v "$b" >/dev/null || { echo "missing $b"; exit 2; }
done
ip link show virbr0 >/dev/null 2>&1 || { echo "virbr0 missing: libvirt's default network is not up"; exit 1; }
cleanup() { ip netns del "$ns" 2>/dev/null; ip link del "$host" 2>/dev/null; rm -rf "/etc/netns/$ns"; }
trap cleanup EXIT
cleanup
ip netns add "$ns"
ip link add "$host" type veth peer name eth0 netns "$ns"
ip link set "$host" master virbr0 up
ip -n "$ns" link set lo up
ip -n "$ns" link set eth0 up
ip -n "$ns" addr add 192.168.122.250/24 dev eth0
ip -n "$ns" route add default via 192.168.122.1
mkdir -p "/etc/netns/$ns" && echo 'nameserver 192.168.122.1' > "/etc/netns/$ns/resolv.conf"
# libvirt's virbr0 runs STP (forward_delay 2 s): a new port spends ~4 s in listening and
# learning, dropping everything. Wait until it forwards (brport state 3) instead of guessing.
for _ in $(seq 40); do
  [ "$(cat "/sys/class/net/$host/brport/state" 2>/dev/null)" = 3 ] && break
  sleep 0.5
done
[ "$(cat "/sys/class/net/$host/brport/state" 2>/dev/null)" = 3 ] || echo "WARN bridge port still not forwarding after 20 s"
r=0
ip netns exec "$ns" ping -c 2 -W 3 1.1.1.1 >/dev/null 2>&1 && echo "OK  ping 1.1.1.1 (forward + NAT)" || { echo "FAIL ping 1.1.1.1"; r=1; }
ip netns exec "$ns" getent hosts archlinux.org >/dev/null 2>&1 && echo "OK  DNS via libvirt dnsmasq" || { echo "FAIL DNS via 192.168.122.1"; r=1; }
code=$(ip netns exec "$ns" curl -4 -sS -m 10 -o /dev/null -w '%{http_code}' https://archlinux.org 2>&1)
[ "$code" = 200 ] && echo "OK  https://archlinux.org → 200" || { echo "FAIL https → $code"; r=1; }
exit $r
