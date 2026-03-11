"""
tb-record  — Collect scripted demonstration episodes and save to HDF5.

Usage
-----
    tb-record --config testbed/configs/task_v0.yaml
    tb-record --config testbed/configs/task_v0.yaml --num-episodes 10
    python -m testbed.cli.record --config testbed/configs/task_v0.yaml
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-record",
        description="Collect scripted demo episodes → HDF5.",
    )
    parser.add_argument(
        "--config", "-c",
        type=Path,
        required=True,
        help="Path to task YAML config (e.g. testbed/configs/task_v0.yaml).",
    )
    parser.add_argument(
        "--num-episodes", "-n",
        type=int,
        default=None,
        help="Override task.num_episodes from the config.",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="Override task.dataset_dir from the config.",
    )
    parser.add_argument(
        "--equipment-model",
        type=str,
        default=None,
        help="Override task.equipment_model from the config.",
    )
    args = parser.parse_args()

    with open(args.config) as f:
        config: dict = yaml.safe_load(f) or {}

    # apply CLI overrides
    task = config.setdefault("task", {})
    if args.num_episodes is not None:
        task["num_episodes"] = args.num_episodes
    if args.output_dir is not None:
        task["dataset_dir"] = str(args.output_dir)
    if args.equipment_model is not None:
        task["equipment_model"] = args.equipment_model

    from testbed.runtime.runner import Runner
    Runner(config).record()


if __name__ == "__main__":
    main()
