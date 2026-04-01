"""tb-experiment-record — write a comparable experiment record for one run."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-experiment-record",
        description="Summarise one train+eval round into JSON/Markdown plus a registry CSV row.",
    )
    parser.add_argument(
        "--train-ckpt-dir",
        type=Path,
        required=True,
        help="Training checkpoint directory containing run_metadata.json.",
    )
    parser.add_argument(
        "--eval-results-dir",
        type=Path,
        required=True,
        help="Evaluation results directory containing metrics.json and rollout_manifest.json.",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Optional explicit dataset directory. Defaults to the train metadata dataset_dir.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="",
        help="Optional experiment name used for the record directory.",
    )
    parser.add_argument(
        "--hypothesis",
        type=str,
        default="",
        help="What scientific question or hypothesis this experiment is testing.",
    )
    parser.add_argument(
        "--notes",
        type=str,
        default="",
        help="Free-form notes about the outcome or observations of this run.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runs/experiments"),
        help="Root directory where experiment records and registry CSV are written.",
    )
    args = parser.parse_args()

    from testbed.runtime.experiment_record import (
        append_experiment_registry,
        build_experiment_record,
        write_experiment_record,
    )

    record = build_experiment_record(
        train_ckpt_dir=args.train_ckpt_dir,
        eval_results_dir=args.eval_results_dir,
        dataset_dir=args.dataset_dir,
        experiment_name=args.name,
        hypothesis=args.hypothesis,
        notes=args.notes,
    )
    json_path, md_path = write_experiment_record(
        record=record,
        output_root=args.output_root,
    )
    registry_path = append_experiment_registry(
        record,
        args.output_root / "experiment_registry.csv",
    )

    print(f"Experiment record JSON: {json_path}")
    print(f"Experiment record Markdown: {md_path}")
    print(f"Experiment registry CSV: {registry_path}")


if __name__ == "__main__":
    main()
