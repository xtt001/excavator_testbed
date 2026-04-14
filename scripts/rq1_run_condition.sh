#!/usr/bin/env bash
# rq1_run_condition.sh — Run one complete RQ1 condition:
#   inject delay → record teleop → analyze latency → train ACT
#
# Usage:
#   ./scripts/rq1_run_condition.sh c0_baseline    0
#   ./scripts/rq1_run_condition.sh c100ms_delay 100
#   ./scripts/rq1_run_condition.sh c200ms_delay 200
#
# After all conditions are done, run rq1_compare.py for comparison plots.

set -euo pipefail

COND=${1:?"Usage: $0 <condition_name> <delay_ms>"}
DELAY=${2:?"Usage: $0 <condition_name> <delay_ms>"}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$REPO_DIR/testbed/configs/rq1_experiment"

echo "============================================================"
echo " RQ1 Condition: $COND  (injected delay: ${DELAY}ms)"
echo "============================================================"

# 1. Inject delay
echo ""
echo "--- Step 1: Inject delay ---"
if [[ "$DELAY" -gt 0 ]]; then
    sudo bash "$SCRIPT_DIR/inject_delay.sh" "$DELAY" 10
    bash "$SCRIPT_DIR/verify_latency.sh" "$DELAY"
else
    sudo bash "$SCRIPT_DIR/inject_delay.sh" 0
    echo "[rq1] No delay injected (baseline condition)"
fi

# 2. Record teleop (requires Unity running on port 5057)
echo ""
echo "--- Step 2: Record teleop demos ---"
echo "[rq1] Unity must be running on 127.0.0.1:5057"
echo "[rq1] Press ENTER to start recording, or Ctrl+C to abort."
read -r

conda run -n aloha tb-record-teleop \
    --config "$CONFIG_DIR/teleop_${COND}.yaml"

# 3. Analyze latency trace (auto-run by latency module on close)
echo ""
echo "--- Step 3: Latency analysis ---"
TRACE_DIR="$REPO_DIR/outputs/rq1/$COND"
if [[ -d "$TRACE_DIR" ]]; then
    conda run -n aloha python -m testbed.latency_module.analysis.export_summary \
        --run-dir "$TRACE_DIR"
else
    # Also extract from HDF5 as backup
    conda run -n aloha python -m testbed.latency_module.analysis.hdf5_bridge \
        --dataset "$REPO_DIR/data/rq1/$COND" \
        --label   "$COND" \
        --out     "$REPO_DIR/outputs/rq1" \
        --delay-inject-ms "$DELAY"
fi

# 4. Train ACT (offline, no Unity needed)
echo ""
echo "--- Step 4: Train ACT ---"
conda run -n aloha tb-train --config "$CONFIG_DIR/train_${COND}.yaml"

echo ""
echo "============================================================"
echo " Condition $COND complete."
echo " Data:    data/rq1/$COND/"
echo " Latency: outputs/rq1/$COND/summary.json"
echo " Model:   runs/ckpts/rq1/$COND/policy_best.ckpt"
echo "============================================================"
echo ""
echo "Next: Run tb-eval when Unity is available:"
echo "  tb-eval --config testbed/configs/rq1_experiment/eval_${COND}.yaml"
