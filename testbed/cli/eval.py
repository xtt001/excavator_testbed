"""
tb-eval  — Evaluate a trained policy under fixed conditions.

Usage
-----
    tb-eval --config testbed/configs/eval_v0.yaml --ckpt ckpts/run1/policy_best.ckpt
    tb-eval --config testbed/configs/eval_v0.yaml --no-video
    python -m testbed.cli.eval --config testbed/configs/eval_v0.yaml
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-eval",
        description="Evaluate a policy with fixed seed evaluation suite.",
    )
    parser.add_argument(
        "--config", "-c",
        type=Path,
        required=True,
        help="Eval YAML config (e.g. testbed/configs/eval_v0.yaml).",
    )
    parser.add_argument(
        "--task-config",
        type=Path,
        default=None,
        help="Optional task YAML (merged, task.*  keys used).",
    )
    parser.add_argument(
        "--ckpt",
        type=Path,
        default=None,
        help="Override eval.ckpt_path.",
    )
    parser.add_argument(
        "--num-rollouts", "-n",
        type=int,
        default=None,
        help="Override eval.num_rollouts.",
    )
    parser.add_argument(
        "--no-video",
        action="store_true",
        help="Disable video saving (overrides eval.save_video).",
    )
    parser.add_argument(
        "--temporal-agg",
        action="store_true",
        default=None,
        help="Enable temporal action aggregation (ACT only).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Override eval results/video root and keep rollout/HDF5 logs "
            "under that results directory."
        ),
    )
    parser.add_argument(
        "--target-cycle-gate",
        type=int,
        default=None,
        help="Override eval.target_cycle_gate for multi-cycle smoke/probe runs.",
    )
    args = parser.parse_args()

    config: dict = {}
    if args.task_config:
        with open(args.task_config) as f:
            config.update(yaml.safe_load(f) or {})
    with open(args.config) as f:
        config.update(yaml.safe_load(f) or {})

    # CLI overrides
    eval_cfg = config.setdefault("eval", {})
    if args.ckpt:
        eval_cfg["ckpt_path"] = str(args.ckpt)
    if args.num_rollouts is not None:
        eval_cfg["num_rollouts"] = args.num_rollouts
    if args.no_video:
        eval_cfg["save_video"] = False
    if args.temporal_agg:
        eval_cfg["temporal_agg"] = True
    if args.target_cycle_gate is not None:
        eval_cfg["target_cycle_gate"] = int(args.target_cycle_gate)
    if args.output_dir:
        results_dir = args.output_dir / "results"
        eval_cfg["results_dir"] = str(results_dir)
        eval_cfg["video_dir"] = str(args.output_dir / "videos")
        eval_cfg["rollout_log_dir"] = str(results_dir / "rollouts")
        eval_cfg["hdf5_dir"] = str(results_dir / "hdf5_rollouts")

    from testbed.runtime.runner import Runner
    Runner(config).eval()


if __name__ == "__main__":
    main()
