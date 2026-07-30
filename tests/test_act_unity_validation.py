from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_DIG_AREA_CELL_AREA_IDX,
    ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_INITIAL_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_REMAINING_MASS_FRACTION_IDX,
    ENV_STATE_DIG_AREA_REMAINING_MASS_VALID_MASK_IDX,
    ENV_STATE_DIG_AREA_REMAINING_SOIL_VOLUME_START_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.act_unity_validation import (
    ActUnityValidationContractError,
    build_act_unity_validation_record,
    build_act_unity_validation_records,
)
from testbed.eval.policy_inference_timing import timed_policy_predict


def _env(
    *,
    volume: float,
    payload: float,
    current_mass: float,
    initial_mass: float = 1000.0,
    wall_sessions: int = 0,
    bottom_sessions: int = 0,
) -> list[float]:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[ENV_STATE_MASS_IN_BUCKET_IDX] = payload
    env[ENV_STATE_DIG_AREA_CELL_AREA_IDX] = 1.0
    env[
        ENV_STATE_DIG_AREA_REMAINING_SOIL_VOLUME_START_IDX :
        ENV_STATE_DIG_AREA_REMAINING_SOIL_VOLUME_START_IDX + 6
    ] = volume
    env[ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX] = current_mass
    env[ENV_STATE_DIG_AREA_INITIAL_REMAINING_MASS_IDX] = initial_mass
    env[ENV_STATE_DIG_AREA_REMAINING_MASS_FRACTION_IDX] = (
        current_mass / initial_mass
    )
    env[ENV_STATE_DIG_AREA_REMAINING_MASS_VALID_MASK_IDX] = 1.0
    env[ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX] = wall_sessions
    env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX] = (
        bottom_sessions
    )
    return env.tolist()


def _row(
    *,
    t: int,
    cycle: int,
    skill: str,
    volume: float,
    payload: float,
    current_mass: float,
    checkpoint: bool = True,
) -> dict[str, object]:
    return {
        "t": t,
        "step_id": t,
        "primitive_cycle_index": cycle,
        "skill_name": skill,
        "primitive_checkpoint_path": f"/ckpts/{skill}.ckpt" if checkpoint else "",
        "policy_inference_latency_ms": 12.0 + t * 0.01,
        "transition_timeout": False,
        "pre_dig_align_timeout_count": 0,
        "box_safety_reason": "",
        "box_safety_awaiting_neutral_ack": False,
        "env_state": _env(
            volume=volume,
            payload=payload,
            current_mass=current_mass,
        ),
    }


def _two_cycle_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    def append(
        cycle: int,
        skill: str,
        count: int,
        volume: float,
        payload: float,
        mass: float,
        *,
        checkpoint: bool = True,
    ) -> None:
        for _ in range(count):
            rows.append(
                _row(
                    t=len(rows),
                    cycle=cycle,
                    skill=skill,
                    volume=volume,
                    payload=payload,
                    current_mass=mass,
                    checkpoint=checkpoint,
                )
            )

    append(0, "bootstrap", 10, 1.0, 0.0, 1000.0, checkpoint=False)
    append(0, "dig", 4, 1.0, 20.0, 1000.0)
    append(0, "carry", 2, 0.99, 20.0, 900.0)
    append(0, "dump", 2, 0.99, 20.0, 900.0)
    append(0, "return", 10, 0.99, 0.0, 900.0)
    append(1, "dig", 4, 0.99, 25.0, 900.0)
    append(1, "carry", 2, 0.98, 25.0, 700.0)
    append(1, "dump", 2, 0.98, 25.0, 700.0)
    append(1, "return", 2, 0.98, 0.0, 700.0)
    return rows


def _write_artifact(
    path: Path,
    *,
    contract: str = "agx_env_state_v2_4_107",
    recorder_layout: bool = False,
) -> None:
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata") if recorder_layout else handle
        metadata.attrs["env_state_contract_version"] = contract
        metadata.attrs["runtime_build_id"] = (
            "editor:2022.3.62f3:0.1.0:agx_env_state_v2_4_107"
        )
        metadata.attrs["unity_scene_id"] = (
            "Assets/AGXUnity_Excavator/AGXUnity_Excavator.unity"
            "@sha256:97b01deb"
        )
        metadata.attrs["unity_source_sha256"] = "fb50869b"


def test_build_validation_record_derives_real_gate_facts(tmp_path: Path) -> None:
    artifact = tmp_path / "episode_0.hdf5"
    _write_artifact(artifact)

    record = build_act_unity_validation_record(
        rows=_two_cycle_rows(),
        artifact_path=artifact,
        reset_id="seed_1000",
        stable_window_steps=10,
    )

    assert record["schema"] == "act_unity_closed_loop_validation_v1"
    assert record["cycle_count"] == 2
    assert record["completed_full_cycle_count"] == 1
    assert record["effective_move_cycle_count"] == 1
    assert record["initial_remaining_mass_kg"] == pytest.approx(1000.0)
    assert record["final_remaining_mass_kg"] == pytest.approx(700.0)
    assert record["wall_contact_count"] == 0
    assert record["bottom_contact_count"] == 0
    assert record["stuck_count"] == 0
    assert record["timeout_count"] == 0
    assert len(record["four_camera_inference_latency_ms"]) > 0
    assert record["scene_id"].endswith("@sha256:97b01deb")
    assert record["unity_source_sha256"] == "fb50869b"


def test_validation_rejects_non_107d_runtime_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "episode_0.hdf5"
    _write_artifact(artifact, contract="agx_env_state_v2_3_89")

    with pytest.raises(
        ActUnityValidationContractError,
        match="env_state_contract_version_mismatch",
    ):
        build_act_unity_validation_record(
            rows=_two_cycle_rows(),
            artifact_path=artifact,
            reset_id="seed_1000",
        )


def test_validation_reads_runtime_provenance_from_recorder_metadata_group(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "episode_0.hdf5"
    _write_artifact(artifact, recorder_layout=True)

    record = build_act_unity_validation_record(
        rows=_two_cycle_rows(),
        artifact_path=artifact,
        reset_id="seed_1000",
    )

    assert record["env_state_contract_version"] == "agx_env_state_v2_4_107"
    assert record["unity_build_id"].endswith("agx_env_state_v2_4_107")
    assert record["unity_source_sha256"] == "fb50869b"


def test_validation_counts_final_dump_only_cycle_without_losing_prior_return(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "episode_0.hdf5"
    _write_artifact(artifact)
    rows = [
        row
        for row in _two_cycle_rows()
        if not (
            int(row["primitive_cycle_index"]) == 1
            and str(row["skill_name"]) == "return"
        )
    ]

    record = build_act_unity_validation_record(
        rows=rows,
        artifact_path=artifact,
        reset_id="seed_1000",
    )

    assert record["cycle_count"] == 2
    assert record["completed_full_cycle_count"] == 1
    assert record["effective_move_cycle_count"] == 1


def test_validation_records_are_no_overwrite_and_seeded_by_rollout_id(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results"
    rollouts = results / "rollouts"
    hdf5_dir = results / "hdf5_rollouts"
    rollouts.mkdir(parents=True)
    hdf5_dir.mkdir(parents=True)
    for rollout_id in range(2):
        (rollouts / f"rollout_{rollout_id:03d}.jsonl").write_text(
            "\n".join(json.dumps(row) for row in _two_cycle_rows()) + "\n",
            encoding="utf-8",
        )
        _write_artifact(hdf5_dir / f"episode_{rollout_id}.hdf5")

    output = tmp_path / "validation"
    records = build_act_unity_validation_records(
        results_dir=results,
        output_dir=output,
        expected_rollout_count=2,
        seed_base=1000,
    )

    assert [item["reset_id"] for item in records] == ["seed_1000", "seed_1001"]
    assert (output / "validation_manifest.json").is_file()
    with pytest.raises(FileExistsError):
        build_act_unity_validation_records(
            results_dir=results,
            output_dir=output,
            expected_rollout_count=2,
            seed_base=1000,
        )


def test_timed_policy_predict_uses_injected_monotonic_clock() -> None:
    class Policy:
        def predict(self, obs: dict[str, object]) -> np.ndarray:
            assert obs["ok"] is True
            return np.asarray([1.0, 2.0], dtype=np.float32)

    clock = iter((10.0, 10.0125))
    action, latency_ms = timed_policy_predict(
        Policy(),
        {"ok": True},
        monotonic=lambda: next(clock),
    )

    np.testing.assert_array_equal(action, [1.0, 2.0])
    assert latency_ms == pytest.approx(12.5)
