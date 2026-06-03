#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Train ACT_GRAPH first, then train an ACT baseline on the same dataset.

Usage:
  bash scripts/train_act_graph_vs_act.sh [--config PATH] [--epochs N] [--dry-run]

Options:
  --config PATH   ACT_GRAPH config to use.
                  Default: testbed/configs/act_graph_agx_smoke.yaml
  --epochs N      Override train.num_epochs for both runs.
  --dry-run       Generate/print commands without starting training.

Environment:
  PYTHON          Python executable. Default: python
EOF
}

CONFIG="testbed/configs/act_graph_agx_smoke.yaml"
EPOCHS=""
DRY_RUN=0
PYTHON_BIN="${PYTHON:-python}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      CONFIG="$2"
      shift 2
      ;;
    --epochs)
      EPOCHS="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -f "$CONFIG" ]]; then
  echo "Config not found: $CONFIG" >&2
  exit 1
fi

generated_dir="runs/configs/act_graph_vs_act"
mkdir -p "$generated_dir"
baseline_config="$generated_dir/act_baseline_same_data.yaml"

"$PYTHON_BIN" - "$CONFIG" "$baseline_config" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

import yaml

source = Path(sys.argv[1])
target = Path(sys.argv[2])
with open(source) as f:
    cfg = yaml.safe_load(f) or {}

task = cfg.setdefault("task", {})
policy = cfg.setdefault("policy", {})
train = cfg.setdefault("train", {})
eval_cfg = cfg.setdefault("eval", {})

task["task_name"] = "agx_excavation_act_50_same_data"
policy["class"] = "ACT"
policy.pop("graph_params", None)

train["ckpt_dir"] = "runs/ckpts/agx_excavation_act_50_same_data"
eval_cfg["ckpt_dir"] = "runs/ckpts/agx_excavation_act_50_same_data"
eval_cfg["ckpt_path"] = "runs/ckpts/agx_excavation_act_50_same_data/policy_best.ckpt"
eval_cfg["video_dir"] = "runs/eval/agx_excavation_act_50_same_data/videos"
eval_cfg["results_dir"] = "runs/eval/agx_excavation_act_50_same_data/results"

target.parent.mkdir(parents=True, exist_ok=True)
with open(target, "w") as f:
    yaml.safe_dump(cfg, f, sort_keys=False)
print(target)
PY

train_cmd_graph=("$PYTHON_BIN" -m testbed.cli.train --config "$CONFIG")
train_cmd_act=("$PYTHON_BIN" -m testbed.cli.train --config "$baseline_config")
if [[ -n "$EPOCHS" ]]; then
  train_cmd_graph+=(--epochs "$EPOCHS")
  train_cmd_act+=(--epochs "$EPOCHS")
fi

echo "ACT_GRAPH config: $CONFIG"
echo "ACT baseline config: $baseline_config"
echo
printf 'Step 1 command:'
printf ' %q' "${train_cmd_graph[@]}"
printf '\n'
printf 'Step 2 command:'
printf ' %q' "${train_cmd_act[@]}"
printf '\n'
echo

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run only; no training started."
  exit 0
fi

echo "=== Step 1/2: training ACT_GRAPH ==="
"${train_cmd_graph[@]}"

echo "=== Step 2/2: training ACT baseline on the same dataset ==="
"${train_cmd_act[@]}"

echo "Done."
echo "ACT_GRAPH checkpoints: runs/ckpts/agx_excavation_act_graph_50"
echo "ACT baseline checkpoints: runs/ckpts/agx_excavation_act_50_same_data"
