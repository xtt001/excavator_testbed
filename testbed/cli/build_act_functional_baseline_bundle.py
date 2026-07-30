"""Build the functional-only strict-18 ACT bundle after a passing 3x10."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from testbed.eval.act_functional_baseline_bundle import (
    build_functional_baseline_bundle,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-act-functional-baseline-bundle",
        description=(
            "Write a functional_baseline_only bundle. This command does not "
            "freeze ACT and does not unlock effect-model work."
        ),
    )
    parser.add_argument("--validation-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--runtime-config", type=Path, required=True)
    parser.add_argument(
        "--runtime-code",
        type=Path,
        action="append",
        required=True,
    )
    parser.add_argument("--carry-start-envelope", type=Path, required=True)
    parser.add_argument("--unity-build-id", required=True)
    parser.add_argument("--unity-scene-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    validation_paths = sorted(
        args.validation_dir.glob("validation_reset_*.json")
    )
    if len(validation_paths) != 3:
        raise RuntimeError(
            f"exactly_three_validation_records_required:{validation_paths}"
        )
    records = [_read_json(path) for path in validation_paths]
    checkpoints = {
        primitive: (
            args.checkpoint_root / primitive / "policy_best.ckpt"
        )
        for primitive in ("dig", "carry", "dump", "return")
    }
    bundle = build_functional_baseline_bundle(
        primitive_checkpoint_paths=checkpoints,
        validation_records=records,
        runtime_config_path=args.runtime_config,
        runtime_code_paths=args.runtime_code,
        carry_start_envelope_path=args.carry_start_envelope,
        unity_build_id=args.unity_build_id,
        unity_scene_id=args.unity_scene_id,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "schema": bundle["schema"],
                "status": bundle["status"],
                "output": str(args.output.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"validation_record_not_mapping:{path}")
    return value


if __name__ == "__main__":
    main()
