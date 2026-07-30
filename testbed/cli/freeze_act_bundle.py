"""Freeze the strict-18 four-primitive ACT bundle after the real 3x10 gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from testbed.eval.act_freeze_bundle import build_frozen_act_bundle


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate three real Unity reset records and write one "
            "no-overwrite frozen four-primitive ACT bundle."
        )
    )
    parser.add_argument("--validation-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--data-lineage", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    validation_paths = sorted(
        args.validation_dir.glob("validation_reset_*.json")
    )
    if len(validation_paths) != 3:
        raise RuntimeError(
            f"exactly_three_validation_records_required:{validation_paths}"
        )
    validation_rollouts = [_read_json(path) for path in validation_paths]
    artifacts = {
        primitive: _primitive_artifact(args.checkpoint_root / primitive)
        for primitive in ("dig", "carry", "dump", "return")
    }
    bundle = build_frozen_act_bundle(
        primitive_artifacts=artifacts,
        validation_rollouts=validation_rollouts,
        data_lineage_path=args.data_lineage,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "status": bundle["status"],
                "output": str(args.output.resolve()),
            },
            indent=2,
        )
    )


def _primitive_artifact(root: Path) -> dict[str, str]:
    resolved = root.resolve()
    primitive = root.name
    split = (
        Path(
            "/data/pingfan/excavator_testbed_data/"
            "yulong_strict18_terrain_residual_v0/splits"
        )
        / f"{primitive}_source_split.yaml"
    )
    return {
        "checkpoint_path": str(resolved / "policy_best.ckpt"),
        "run_metadata_path": str(resolved / "run_metadata.json"),
        "stats_path": str(resolved / "dataset_stats.pkl"),
        "resolved_config_path": str(resolved / "resolved_config.yaml"),
        "split_path": str(split),
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"validation_record_not_mapping:{path}")
    return value


if __name__ == "__main__":
    main()
