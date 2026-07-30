from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pytest
import yaml

from testbed.data.handoff_envelope import (
    STRICT18_TRAIN_SOURCE_EPISODE_IDS,
    STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
)
from testbed.eval.hard_bottom_goal_comparison import (
    EVIDENCE_SCOPE,
    _through_first_bottom_contact,
    build_hard_bottom_goal_comparison,
    build_temporal_state_contract,
    extract_recorded_median_goal,
    load_wall_safe_goal,
    select_strict_train_exemplar,
    validate_independent_temporal_states,
)
from testbed.planner.primitive.token.tokens import DigCutTokenPlanner


def _raw_fields(*, entry_x: float, depth: float) -> dict[str, float | int]:
    return {
        "operator_entry_x_m": entry_x,
        "operator_entry_y_m": -0.04,
        "operator_entry_z_m": 0.30,
        "operator_exit_x_m": entry_x - 0.15,
        "operator_exit_y_m": -0.30,
        "operator_exit_z_m": 0.62,
        "operator_cut_direction_x": -0.39,
        "operator_cut_direction_y": -0.68,
        "operator_cut_direction_z": 0.62,
        "operator_cut_length_m": 0.47,
        "operator_cut_depth_peak_m": depth,
        "operator_cut_payload_gain_kg": 61.0,
        "operator_effective_deposit_delta_kg": 72.0,
        "operator_cut_valid": 1,
    }


def _token(raw_fields: dict[str, float | int]) -> list[float]:
    plan = DigCutTokenPlanner(prior={}).plan_from_raw_fields(
        raw_fields,
        source="test",
    )
    return [float(value) for value in plan.token]


def _write_primitive(
    path: Path,
    *,
    source_episode_id: int,
    raw_fields: dict[str, float | int],
) -> None:
    token = np.asarray(_token(raw_fields), dtype=np.float32)
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.attrs["source_episode_id"] = f"episode_{source_episode_id}"
        observations = handle.create_group("observations")
        env_state = np.zeros((3, 89), dtype=np.float32)
        env_state[:, 28:31] = np.asarray(
            [[1.0, -0.1, 0.3], [0.9, -0.2, 0.5], [0.8, -0.3, 0.62]],
            dtype=np.float32,
        )
        env_state[:, 31] = np.asarray([0.02, 0.20, 0.30], dtype=np.float32)
        observations.create_dataset("env_state", data=env_state)
        handle.create_dataset(
            "action",
            data=np.asarray(
                [[-0.1, -0.2, 0.3, 0.4]] * 3,
                dtype=np.float32,
            ),
        )
        cycle = handle.create_group("v2/cycle")
        for name, value in raw_fields.items():
            if name == "operator_effective_deposit_delta_kg":
                dataset_name = "dig_outcome_effective_deposit_delta_kg"
            else:
                dataset_name = name
            cycle.create_dataset(dataset_name, data=np.asarray([value]))
        step = handle.create_group("v2/step")
        step.create_dataset(
            "dig_cut_tokens",
            data=np.repeat(token[None, :], 3, axis=0),
        )


def _write_split(path: Path, *, source_episode_id: int = 32) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "train_ids": [354],
                "val_ids": [],
                "train_source_episode_ids": list(
                    STRICT18_TRAIN_SOURCE_EPISODE_IDS
                ),
                "val_source_episode_ids": list(
                    STRICT18_VALIDATION_SOURCE_EPISODE_IDS
                ),
                "allowed_source_episode_ids": [
                    *STRICT18_TRAIN_SOURCE_EPISODE_IDS,
                    *STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
                ],
                "source_episode_id_by_primitive_episode_id": {
                    354: source_episode_id
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_exemplars(
    path: Path,
    *,
    best_raw: dict[str, float | int],
) -> None:
    path.write_text(
        json.dumps(
            {
                "distance_contract": {
                    "default_removed_depth_scale_m": 0.12,
                    "default_target_cell_weight": 2.0,
                    "raw_fields_contract": "v2_4_removed_depth_cut_v3",
                    "state_vector": (
                        "env_state removed_depth grid cells 0..5 at dig "
                        "primitive start"
                    ),
                },
                "exemplars": [
                    {
                        "exemplar_id": "episode_354",
                        "source_episode": "episode_354.hdf5",
                        "cell_id": 4,
                        "start_removed_depth_grid_m": [
                            0.0,
                            0.06,
                            0.07,
                            0.17,
                            0.0,
                            0.06,
                        ],
                        "raw_fields": best_raw,
                    },
                    {
                        "exemplar_id": "episode_355",
                        "source_episode": "episode_355.hdf5",
                        "cell_id": 4,
                        "start_removed_depth_grid_m": [0.3] * 6,
                        "raw_fields": _raw_fields(entry_x=0.7, depth=0.4),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_w1(path: Path, raw_fields: dict[str, float | int]) -> str:
    path.write_text(
        json.dumps(
            {
                "schema": "residual_cut_intent_runtime_source_v1",
                "plans": [
                    {
                        "cycle_index": 1,
                        "plan": {
                            "raw_fields": raw_fields,
                            "dig_cut_tokens": _token(raw_fields),
                        },
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_rollout(
    *,
    hdf5_path: Path,
    jsonl_path: Path,
    token: list[float],
) -> None:
    step_ids = np.asarray([100, 101, 102], dtype=np.int64)
    env_state = np.zeros((3, 107), dtype=np.float32)
    env_state[:, 39:45] = np.asarray(
        [0.0, 0.06, 0.07, 0.17, 0.0, 0.06],
        dtype=np.float32,
    )
    with h5py.File(hdf5_path, "w") as handle:
        timestamps = handle.create_group("timestamps")
        timestamps.create_dataset("step_id", data=step_ids)
        observations = handle.create_group("observations")
        observations.create_dataset(
            "qpos",
            data=np.zeros((3, 4), dtype=np.float32),
        )
        observations.create_dataset(
            "qvel",
            data=np.zeros((3, 4), dtype=np.float32),
        )
        observations.create_dataset("env_state", data=env_state)
        handle.create_dataset(
            "action",
            data=np.asarray(
                [[0.0] * 4, [0.1, 0.2, 0.3, 0.4], [0.2, 0.3, 0.4, 0.5]],
                dtype=np.float32,
            ),
        )
    rows = [
        {
            "step_id": step_id,
            "primitive_cycle_index": 5,
            "skill_name": "dig",
            "dig_step_count": index,
            "dig_cut_tokens": token,
            "action": action,
        }
        for index, (step_id, action) in enumerate(
            (
                (101, [0.1, 0.2, 0.3, 0.4]),
                (102, [0.2, 0.3, 0.4, 0.5]),
            )
        )
    ]
    jsonl_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_m0_is_last_planner_goal_matching_recorded_cycle_token(
    tmp_path: Path,
) -> None:
    other = _raw_fields(entry_x=0.4, depth=0.2)
    expected = _raw_fields(entry_x=0.63, depth=0.364648)
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        json.dumps(
            {
                "coverage_decision_trace": [
                    {
                        "event": "wall_safety_final_guard_accepted",
                        "cycle_index": 2,
                        "raw_fields": other,
                    },
                    {
                        "event": "wall_safety_final_guard_accepted",
                        "cycle_index": 4,
                        "raw_fields": expected,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = extract_recorded_median_goal(
        planner_trace_path=trace_path,
        recorded_tokens=[_token(expected), _token(expected)],
    )

    assert result["target_id"] == "M0"
    assert result["planner_trace_cycle_index"] == 4
    assert result["raw_fields"] == expected


def test_e1_selection_enforces_strict_train_lineage_and_real_tuple(
    tmp_path: Path,
) -> None:
    raw_fields = _raw_fields(entry_x=1.037643, depth=0.298849)
    dataset_dir = tmp_path / "dig"
    dataset_dir.mkdir()
    _write_primitive(
        dataset_dir / "episode_354.hdf5",
        source_episode_id=32,
        raw_fields=raw_fields,
    )
    split_path = tmp_path / "dig_source_split.yaml"
    _write_split(split_path)
    exemplar_path = tmp_path / "state_exemplars.json"
    _write_exemplars(exemplar_path, best_raw=raw_fields)

    result = select_strict_train_exemplar(
        exemplar_path=exemplar_path,
        split_path=split_path,
        dataset_dir=dataset_dir,
        current_removed_depth_grid_m=np.asarray(
            [0.0, 0.06, 0.07, 0.17, 0.0, 0.06],
            dtype=np.float32,
        ),
        target_cell_id=4,
        expected_exemplar_id="episode_354",
        expected_source_episode_id=32,
    )

    assert result["target_id"] == "E1"
    assert result["exemplar_id"] == "episode_354"
    assert result["primitive_episode_id"] == 354
    assert result["source_episode_id"] == 32
    assert result["raw_fields"] == raw_fields
    assert result["expert_trajectory"]["step_count"] == 3
    assert result["expert_trajectory"]["peak_local_penetration_m"] == pytest.approx(
        0.30
    )

    _write_split(split_path, source_episode_id=33)
    with pytest.raises(ValueError, match="validation|train"):
        select_strict_train_exemplar(
            exemplar_path=exemplar_path,
            split_path=split_path,
            dataset_dir=dataset_dir,
            current_removed_depth_grid_m=np.zeros(6, dtype=np.float32),
            target_cell_id=4,
        )


def test_e1_rejects_partial_or_salvage_paths(tmp_path: Path) -> None:
    partial = tmp_path / "partial_salvage"
    partial.mkdir()
    exemplar_path = partial / "state_exemplars.json"
    exemplar_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden marker"):
        select_strict_train_exemplar(
            exemplar_path=exemplar_path,
            split_path=tmp_path / "missing.yaml",
            dataset_dir=tmp_path,
            current_removed_depth_grid_m=np.zeros(6, dtype=np.float32),
            target_cell_id=4,
        )


def test_w1_sha_and_cycle_one_plan_are_immutable(tmp_path: Path) -> None:
    raw_fields = _raw_fields(entry_x=0.615094, depth=0.419068)
    path = tmp_path / "w1.json"
    sha = _write_w1(path, raw_fields)

    result = load_wall_safe_goal(
        artifact_path=path,
        expected_sha256=sha,
    )

    assert result["target_id"] == "W1"
    assert result["artifact_sha256"] == sha
    assert result["raw_fields"] == raw_fields
    with pytest.raises(ValueError, match="SHA256"):
        load_wall_safe_goal(
            artifact_path=path,
            expected_sha256="0" * 64,
        )


def test_temporal_state_contract_forbids_shared_buffers() -> None:
    states = build_temporal_state_contract(("M0", "E1", "W1"))
    validated = validate_independent_temporal_states(states)

    assert validated["target_count"] == 3
    assert validated["all_initial_contributor_counts_zero"] is True
    assert len({item["state_id"] for item in states}) == 3

    duplicate = [dict(item) for item in states]
    duplicate[1]["buffer_owner_id"] = duplicate[0]["buffer_owner_id"]
    with pytest.raises(ValueError, match="buffer owner"):
        validate_independent_temporal_states(duplicate)


def test_goal_window_stops_at_first_typed_bottom_contact() -> None:
    frames = [
        {
            "action_step_id": step,
            "post_env_state": [
                *([0.0] * 104),
                mask,
                0.0,
                0.0,
            ],
        }
        for step, mask in ((10, 0.0), (11, 1.0), (12, 1.0))
    ]

    selected, contact_step = _through_first_bottom_contact(frames)

    assert [frame["action_step_id"] for frame in selected] == [10, 11]
    assert contact_step == 11


def test_builder_is_teacher_forced_no_overwrite_and_never_fakes_policy_actions(
    tmp_path: Path,
) -> None:
    m0 = _raw_fields(entry_x=0.635571, depth=0.364648)
    e1 = _raw_fields(entry_x=1.037643, depth=0.298849)
    w1 = _raw_fields(entry_x=0.615094, depth=0.419068)
    hdf5_path = tmp_path / "rollout.hdf5"
    jsonl_path = tmp_path / "rollout.jsonl"
    _write_rollout(
        hdf5_path=hdf5_path,
        jsonl_path=jsonl_path,
        token=_token(m0),
    )
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        json.dumps(
            {
                "coverage_decision_trace": [
                    {
                        "event": "wall_safety_final_guard_accepted",
                        "cycle_index": 4,
                        "raw_fields": m0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    dataset_dir = tmp_path / "dig"
    dataset_dir.mkdir()
    _write_primitive(
        dataset_dir / "episode_354.hdf5",
        source_episode_id=32,
        raw_fields=e1,
    )
    split_path = tmp_path / "dig_source_split.yaml"
    _write_split(split_path)
    exemplar_path = tmp_path / "state_exemplars.json"
    _write_exemplars(exemplar_path, best_raw=e1)
    w1_path = tmp_path / "w1.json"
    w1_sha = _write_w1(w1_path, w1)
    output_dir = tmp_path / "comparison"

    result = build_hard_bottom_goal_comparison(
        rollout_hdf5_path=hdf5_path,
        rollout_jsonl_path=jsonl_path,
        planner_trace_path=trace_path,
        exemplar_path=exemplar_path,
        dig_split_path=split_path,
        dig_dataset_dir=dataset_dir,
        wall_safe_goal_path=w1_path,
        wall_safe_goal_sha256=w1_sha,
        output_dir=output_dir,
        compute_train_support=False,
    )

    assert result["evidence_scope"] == EVIDENCE_SCOPE
    assert result["target_order"] == ["M0", "E1", "W1"]
    assert result["policy_action_evidence"]["status"] == "blocked"
    assert "fresh_action" not in result["targets"]["M0"]
    assert result["train_support_evidence"]["status"] == "blocked_not_requested"
    assert (output_dir / "manifest.json").is_file()
    with pytest.raises(FileExistsError):
        build_hard_bottom_goal_comparison(
            rollout_hdf5_path=hdf5_path,
            rollout_jsonl_path=jsonl_path,
            planner_trace_path=trace_path,
            exemplar_path=exemplar_path,
            dig_split_path=split_path,
            dig_dataset_dir=dataset_dir,
            wall_safe_goal_path=w1_path,
            wall_safe_goal_sha256=w1_sha,
            output_dir=output_dir,
            compute_train_support=False,
        )
