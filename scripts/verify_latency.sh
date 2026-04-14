#!/usr/bin/env bash
# verify_latency.sh — Quick sanity check that tc netem is working as expected.
#
# Usage:
#   ./scripts/verify_latency.sh [expected_delay_ms]
#
# Sends 10 ICMP pings to localhost and prints statistics.
# Expected RTT ≈ 2 × injected_one_way_delay.

set -euo pipefail

EXPECTED=${1:-0}
echo "[verify_latency] Pinging 127.0.0.1 (expected RTT ≈ $((EXPECTED * 2))ms)..."
ping -c 10 -i 0.1 127.0.0.1

echo ""
echo "[verify_latency] Current tc qdisc on lo:"
tc qdisc show dev lo
