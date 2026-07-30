from __future__ import annotations

import json
from pathlib import Path

import pytest

from testbed.eval.act_freeze_bundle import (
    ActFreezeGateError,
    build_frozen_act_bundle,
)


def _write(path: Path, value: str = "artifact") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def _model_files(root: Path) -> dict[str, dict[str, str]]:
    result = {}
    for primitive in ("dig", "carry", "dump", "return"):
        primitive_root = root / primitive
        checkpoint = _write(primitive_root / "policy_best.ckpt")
        stats = _write(primitive_root / "dataset_stats.pkl")
        config = _write(primitive_root / "resolved_config.yaml")
        split = _write(primitive_root / "source_split.yaml")
        metadata = primitive_root / "run_metadata.json"
        metadata.write_text(
            json.dumps({"status": "completed", "random_init": True}),
            encoding="utf-8",
        )
        result[primitive] = {
            "checkpoint_path": str(checkpoint),
            "stats_path": str(stats),
            "resolved_config_path": str(config),
            "split_path": str(split),
            "run_metadata_path": str(metadata),
        }
    return result


def _rollout(
    reset_id: str,
    *,
    artifact_root: Path,
    final_mass: float = 650.0,
) -> dict[str, object]:
    artifact_path = _write(artifact_root / f"{reset_id}.json")
    return {
        "schema": "act_unity_closed_loop_validation_v1",
        "reset_id": reset_id,
        "cycle_count": 10,
        "completed_full_cycle_count": 9,
        "effective_move_cycle_count": 8,
        "initial_remaining_mass_kg": 1000.0,
        "final_remaining_mass_kg": final_mass,
        "wall_contact_count": 0,
        "stuck_count": 0,
        "timeout_count": 0,
        "four_camera_inference_latency_ms": [25.0] * 19 + [49.0],
        "unity_build_id": "unity-build-sha",
        "scene_id": "yulong-hard-bottom-box",
        "artifact_path": str(artifact_path),
    }


def test_freeze_bundle_requires_and_hashes_four_completed_best_checkpoints(
    tmp_path: Path,
) -> None:
    output = tmp_path / "frozen_act_bundle.json"
    lineage = _write(tmp_path / "lineage.json")
    bundle = build_frozen_act_bundle(
        primitive_artifacts=_model_files(tmp_path / "models"),
        validation_rollouts=[
            _rollout(f"reset-{index}", artifact_root=tmp_path / "rollouts")
            for index in range(3)
        ],
        data_lineage_path=lineage,
        output_path=output,
    )

    assert bundle["status"] == "frozen"
    assert bundle["gate"]["passed"] is True
    assert set(bundle["primitives"]) == {"dig", "carry", "dump", "return"}
    assert all(
        len(primitive["checkpoint_sha256"]) == 64
        for primitive in bundle["primitives"].values()
    )
    assert bundle["unity"]["build_id"] == "unity-build-sha"
    assert output.is_file()


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda rows: rows[:2], "exactly_three_resets"),
        (
            lambda rows: [{**rows[0], "completed_full_cycle_count": 8}, *rows[1:]],
            "completed_cycles_below_9",
        ),
        (
            lambda rows: [{**rows[0], "effective_move_cycle_count": 7}, *rows[1:]],
            "effective_cycles_below_8",
        ),
        (
            lambda rows: [{**rows[0], "final_remaining_mass_kg": 701.0}, *rows[1:]],
            "remaining_mass_drop_below_30pct",
        ),
        (
            lambda rows: [{**rows[0], "wall_contact_count": 1}, *rows[1:]],
            "wall_contact_present",
        ),
        (
            lambda rows: [
                {**rows[0], "four_camera_inference_latency_ms": [51.0] * 20},
                *rows[1:],
            ],
            "inference_p95_above_50ms",
        ),
    ],
)
def test_freeze_bundle_rejects_failed_real_closed_loop_gate(
    tmp_path: Path,
    mutation,
    reason: str,
) -> None:
    rows = [
        _rollout(f"reset-{index}", artifact_root=tmp_path / "rollouts")
        for index in range(3)
    ]
    with pytest.raises(ActFreezeGateError, match=reason):
        build_frozen_act_bundle(
            primitive_artifacts=_model_files(tmp_path / "models"),
            validation_rollouts=mutation(rows),
            data_lineage_path=_write(tmp_path / "lineage.json"),
            output_path=tmp_path / "bundle.json",
        )


def test_freeze_bundle_is_no_overwrite(tmp_path: Path) -> None:
    output = _write(tmp_path / "bundle.json", "existing")
    with pytest.raises(FileExistsError):
        build_frozen_act_bundle(
            primitive_artifacts=_model_files(tmp_path / "models"),
            validation_rollouts=[
                _rollout(f"reset-{index}", artifact_root=tmp_path / "rollouts")
                for index in range(3)
            ],
            data_lineage_path=_write(tmp_path / "lineage.json"),
            output_path=output,
        )
