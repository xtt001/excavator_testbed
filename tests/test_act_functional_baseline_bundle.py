from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from testbed.eval.act_functional_baseline_bundle import (
    FunctionalBaselineBundleError,
    build_functional_baseline_bundle,
)


def _write(path: Path, value: str = "artifact") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validation_records(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for reset_index in range(3):
        rollout = _write(
            root / f"rollout_{reset_index:03d}.jsonl",
            f"reset-{reset_index}",
        )
        records.append(
            {
                "schema": "act_functional_10cycle_validation_v1",
                "status": "passed",
                "reset_id": f"reset-{reset_index}",
                "completed_cycle_count": 10,
                "cycles": [
                    {"cycle_index": cycle_index}
                    for cycle_index in range(10)
                ],
                "terminal_return_ready_step": 1000,
                "terminal_neutral_ack_step": 1001,
                "wall_contact_count": 0,
                "stuck_count": 0,
                "timeout_count": 0,
                "hard_bottom_event_count": 0,
                "hard_bottom_events": [],
                "source_artifact_path": str(rollout),
                "source_artifact_sha256": _sha256(rollout),
                "diagnostics": {
                    "remaining_mass_drop_fraction": 0.08,
                    "inference_p95_ms": 37.0,
                },
            }
        )
    return records


def test_functional_bundle_locks_code_config_envelope_and_three_rollouts(
    tmp_path: Path,
) -> None:
    checkpoints = {
        primitive: _write(tmp_path / f"ckpts/{primitive}/policy_best.ckpt")
        for primitive in ("dig", "carry", "dump", "return")
    }
    runtime_config = _write(tmp_path / "functional-a0.yaml")
    runtime_code = [
        _write(tmp_path / "runtime/safety_interlock.py"),
        _write(tmp_path / "runtime/functional_cycle_gate.py"),
    ]
    envelope = _write(
        tmp_path / "carry_start_envelope_v1.json",
        json.dumps({"schema": "carry_start_envelope_v1"}),
    )
    output = tmp_path / "functional_baseline_only.json"

    bundle = build_functional_baseline_bundle(
        primitive_checkpoint_paths=checkpoints,
        validation_records=_validation_records(tmp_path / "rollouts"),
        runtime_config_path=runtime_config,
        runtime_code_paths=runtime_code,
        carry_start_envelope_path=envelope,
        unity_build_id="unity-build-sha",
        unity_scene_id="yulong-hard-bottom-box",
        output_path=output,
    )

    assert bundle["schema"] == "act_functional_baseline_bundle_v1"
    assert bundle["status"] == "functional_baseline_only"
    assert bundle["gate"]["passed_reset_count"] == 3
    assert bundle["release_scope"] == {
        "formal_act_freeze": False,
        "effect_model_unlocked": False,
        "planned_cut_calibration_unlocked": False,
    }
    assert set(bundle["checkpoints"]) == {"dig", "carry", "dump", "return"}
    assert len(bundle["runtime_code"]) == 2
    assert len(bundle["validation_rollouts"]) == 3
    assert output.is_file()


def test_functional_bundle_rejects_tampered_rollout_and_overwrite(
    tmp_path: Path,
) -> None:
    checkpoints = {
        primitive: _write(tmp_path / f"ckpts/{primitive}/policy_best.ckpt")
        for primitive in ("dig", "carry", "dump", "return")
    }
    records = _validation_records(tmp_path / "rollouts")
    Path(str(records[1]["source_artifact_path"])).write_text(
        "tampered",
        encoding="utf-8",
    )
    kwargs = {
        "primitive_checkpoint_paths": checkpoints,
        "validation_records": records,
        "runtime_config_path": _write(tmp_path / "functional-a0.yaml"),
        "runtime_code_paths": [_write(tmp_path / "runtime.py")],
        "carry_start_envelope_path": _write(tmp_path / "envelope.json"),
        "unity_build_id": "unity-build-sha",
        "unity_scene_id": "scene",
        "output_path": tmp_path / "bundle.json",
    }

    with pytest.raises(
        FunctionalBaselineBundleError,
        match="source_artifact_sha256_mismatch",
    ):
        build_functional_baseline_bundle(**kwargs)

    _write(tmp_path / "existing.json")
    kwargs["validation_records"] = _validation_records(
        tmp_path / "fresh-rollouts"
    )
    kwargs["output_path"] = tmp_path / "existing.json"
    with pytest.raises(FileExistsError, match="already exists"):
        build_functional_baseline_bundle(**kwargs)
