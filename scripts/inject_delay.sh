#!/usr/bin/env bash
# inject_delay.sh — Configure tc netem on loopback to inject one-way delay.
#
# Usage:
#   sudo ./scripts/inject_delay.sh 100          # inject 100ms one-way delay
#   sudo ./scripts/inject_delay.sh 100 10       # 100ms delay + 10ms jitter
#   sudo ./scripts/inject_delay.sh 0            # clear all netem rules
#
# Effect:
#   Adds symmetric delay on lo (loopback). Since Unity and Python both run on
#   the same machine, this affects both directions of the step-ack socket,
#   making the total RTT increase by approximately 2x the injected one-way delay.
#   e.g. inject 100ms → RTT increases by ~200ms
#
# Requires: sudo, iproute2 (tc)

set -euo pipefail

DELAY_MS=${1:-0}
JITTER_MS=${2:-0}
IFACE="lo"

if [[ "$DELAY_MS" -eq 0 ]]; then
    echo "[inject_delay] Clearing tc netem rules on $IFACE..."
    sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true
    echo "[inject_delay] Done. Current qdisc:"
    tc qdisc show dev "$IFACE"
    exit 0
fi

echo "[inject_delay] Injecting ${DELAY_MS}ms delay (jitter=${JITTER_MS}ms) on $IFACE..."

# Remove existing rule first (ignore error if none)
sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true

if [[ "$JITTER_MS" -gt 0 ]]; then
    sudo tc qdisc add dev "$IFACE" root netem \
        delay "${DELAY_MS}ms" "${JITTER_MS}ms" distribution normal
    echo "[inject_delay] Set: delay=${DELAY_MS}ms jitter=${JITTER_MS}ms (normal dist)"
else
    sudo tc qdisc add dev "$IFACE" root netem delay "${DELAY_MS}ms"
    echo "[inject_delay] Set: delay=${DELAY_MS}ms (fixed)"
fi

echo "[inject_delay] Current qdisc:"
tc qdisc show dev "$IFACE"
echo ""
echo "[inject_delay] Verify with a quick RTT ping:"
ping -c 3 -i 0.2 127.0.0.1 | tail -3
