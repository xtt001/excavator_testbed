from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pytest
import yaml

from testbed.data.coverage_execution_library import (
    COVERAGE_EXECUTION_LIBRARY_SCHEMA,
    STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT,
    build_coverage_execution_library,
    cut_tuple_consistency_residual_m,
    evaluate_coverage_execution_query,
)
from testbed.data.handoff_envelope import (
    STRICT18_TRAIN_SOURCE_EPISODE_IDS,
    STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
)


def _raw_fields(
    *,
    entry_x_m: float,
    entry_z_m: float,
    depth_m: float,
) -> dict[str, float | int]:
    exit_x_m = entry_x_m - 0.20
    exit_z_m = entry_z_m + 0.10
    length_m = float(np.hypot(exit_x_m - entry_x_m, exit_z_m - entry_z_m))
    return {
        "operator_entry_x_m": float(entry_x_m),
        "operator_entry_y_m": -0.05,
        "operator_entry_z_m": float(entry_z_m),
        "operator_exit_x_m": float(exit_x_m),
        "operator_exit_y_m": -0.25,
        "operator_exit_z_m": float(exit_z_m),
        "operator_cut_direction_x": float((exit_x_m - entry_x_m) / length_m),
        "operator_cut_direction_y": -0.2,
        "operator_cut_direction_z": float((exit_z_m - entry_z_m) / length_m),
        "operator_cut_length_m": length_m,
        "operator_cut_depth_peak_m": float(depth_m),
        "operator_cut_payload_gain_kg": 60.0,
        "operator_effective_deposit_delta_kg": 45.0,
        "operator_cut_valid": 1,
    }


def _token(raw_fields: dict[str, float | int]) -> np.ndarray:
    return np.asarray(
        [
            np.clip(float(raw_fields["operator_entry_x_m"]) / 2.0, -1.0, 1.0),
            np.clip(float(raw_fields["operator_entry_z_m"]) / 2.0, -1.0, 1.0),
            np.clip(float(raw_fields["operator_exit_x_m"]) / 2.0, -1.0, 1.0),
            np.clip(float(raw_fields["operator_exit_z_m"]) / 2.0, -1.0, 1.0),
            float(raw_fields["operator_cut_direction_x"]),
            float(raw_fields["operator_cut_direction_z"]),
            np.clip(float(raw_fields["operator_cut_length_m"]) / 2.0, -1.0, 1.0),
            np.clip(
                float(raw_fields["operator_cut_depth_peak_m"]) / 0.8,
                -1.0,
                1.0,
            ),
            np.clip(
                float(raw_fields["operator_cut_payload_gain_kg"]) / 60.0,
                -1.0,
                1.0,
            ),
            1.0,
        ],
        dtype=np.float32,
    )


def _write_primitive(
    path: Path,
    *,
    primitive_episode_id: int,
    source_episode_id: int,
    effect_outcome_cell_id: int,
    corridor_id: int,
    local_tail_m: float,
    plane_tail_m: float,
) -> None:
    depth_m = 0.10
    raw_fields = _raw_fields(
        entry_x_m=0.20 * corridor_id,
        entry_z_m=0.05 * corridor_id,
        depth_m=depth_m,
    )
    token = _token(raw_fields)
    source_start_step = 1000 + primitive_episode_id * 10
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.attrs["primitive_name"] = "dig"
        metadata.attrs["training_tier"] = "gold"
        metadata.attrs["storage_mode"] = "copy"
        metadata.attrs["composite_evidence_kind"] = "strict_parent_selected_replay"
        metadata.attrs["composite_view_kind"] = "combined_strict_clean_vds"
        metadata.attrs["source_episode_id"] = f"episode_{source_episode_id}"
        metadata.attrs["env_state_contract_version"] = "agx_env_state_v2_3_89"
        metadata.attrs["source_start_step"] = source_start_step
        metadata.attrs["operator_entry_step"] = source_start_step
        metadata.attrs["operator_exit_step"] = source_start_step + 1

        observations = handle.create_group("observations")
        env_state = np.zeros((4, 89), dtype=np.float32)
        env_state[:, 17] = 2.0
        env_state[:, 18] = 3.0
        env_state[:, 19] = 2.0
        env_state[:, 73] = 1.0
        env_state[:, 74] = 1.25
        env_state[:, 8] = np.asarray(
            [0.05, 0.20, 0.20 + plane_tail_m, 0.18],
            dtype=np.float32,
        )
        env_state[:, 31] = np.asarray(
            [0.02, depth_m, depth_m + local_tail_m, 0.09],
            dtype=np.float32,
        )
        removed = np.asarray(
            [
                0.001 * primitive_episode_id,
                0.01 * effect_outcome_cell_id,
                0.02,
                0.03,
                0.04,
                0.05,
            ],
            dtype=np.float32,
        )
        env_state[:, 39:45] = removed
        observations.create_dataset("env_state", data=env_state)
        handle.create_dataset("action", data=np.zeros((4, 4), dtype=np.float32))

        cycle = handle.create_group("v2/cycle")
        for name, value in raw_fields.items():
            dataset_name = (
                "cycle_effective_deposit_delta_kg"
                if name == "operator_effective_deposit_delta_kg"
                else name
            )
            cycle.create_dataset(dataset_name, data=np.asarray([value]))
        cycle.create_dataset(
            "dominant_removed_depth_cell_id",
            data=np.asarray([effect_outcome_cell_id], dtype=np.int32),
        )

        step = handle.create_group("v2/step")
        action_loss_mask = np.ones(4, dtype=np.uint8)
        if primitive_episode_id == 0:
            action_loss_mask[:2] = 0
        elif primitive_episode_id == 1:
            action_loss_mask[1:] = 0
        step.create_dataset(
            "action_loss_mask",
            data=action_loss_mask,
        )
        step.create_dataset(
            "dig_cut_tokens",
            data=np.repeat(token[None, :], 4, axis=0),
        )


def _write_prior(path: Path) -> None:
    coverage_cells = [
        {
            "cell_id": cell_id,
            "entry": {
                "x_m": 0.20 * cell_id,
                "z_m": 0.05 * cell_id,
            },
            "exit": {
                "x_m": 0.20 * cell_id - 0.20,
                "z_m": 0.05 * cell_id + 0.10,
            },
        }
        for cell_id in range(6)
    ]
    path.write_text(
        json.dumps(
            {
                "schema_version": "v3",
                "coverage_cells": coverage_cells,
                "return_start_envelope_cells": [
                    {"cell_id": cell_id} for cell_id in range(6)
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _strict_split_payload(dataset_dir: Path) -> dict[str, object]:
    train_ids = list(range(STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT))
    val_ids = [
        STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT,
        STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT + 1,
    ]
    source_by_primitive = {
        primitive_id: STRICT18_TRAIN_SOURCE_EPISODE_IDS[
            primitive_id % len(STRICT18_TRAIN_SOURCE_EPISODE_IDS)
        ]
        for primitive_id in train_ids
    }
    source_by_primitive.update(
        {
            val_ids[0]: STRICT18_VALIDATION_SOURCE_EPISODE_IDS[0],
            val_ids[1]: STRICT18_VALIDATION_SOURCE_EPISODE_IDS[1],
        }
    )
    return {
        "schema_version": 1,
        "split_policy": "source_identity_exact_allowlist_v1",
        "dataset_dir": str(dataset_dir),
        "train_ids": train_ids,
        "val_ids": val_ids,
        "train_source_episode_ids": list(STRICT18_TRAIN_SOURCE_EPISODE_IDS),
        "val_source_episode_ids": list(STRICT18_VALIDATION_SOURCE_EPISODE_IDS),
        "allowed_source_episode_ids": sorted(
            (
                *STRICT18_TRAIN_SOURCE_EPISODE_IDS,
                *STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
            )
        ),
        "required_training_tier": "gold",
        "source_episode_id_by_primitive_episode_id": source_by_primitive,
    }


def _strict_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    dig_dir = tmp_path / "primitives_copy" / "dig"
    dig_dir.mkdir(parents=True)
    split_payload = _strict_split_payload(dig_dir)
    source_by_primitive = split_payload[
        "source_episode_id_by_primitive_episode_id"
    ]
    assert isinstance(source_by_primitive, dict)
    for primitive_episode_id in range(
        STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT
    ):
        outcome_cell_id = primitive_episode_id % 6
        corridor_id = (outcome_cell_id + 1) % 6
        _write_primitive(
            dig_dir / f"episode_{primitive_episode_id}.hdf5",
            primitive_episode_id=primitive_episode_id,
            source_episode_id=int(source_by_primitive[primitive_episode_id]),
            effect_outcome_cell_id=outcome_cell_id,
            corridor_id=corridor_id,
            local_tail_m=0.03 if primitive_episode_id < 219 else 0.015,
            plane_tail_m=0.04 + 0.0001 * primitive_episode_id,
        )
    split_path = tmp_path / "dig_source_split.yaml"
    split_path.write_text(
        yaml.safe_dump(split_payload, sort_keys=True),
        encoding="utf-8",
    )
    prior_path = tmp_path / "coverage_prior.json"
    _write_prior(prior_path)
    return dig_dir, split_path, prior_path


def test_builds_canonical_strict_train_execution_library_with_loo_p99(
    tmp_path: Path,
) -> None:
    dig_dir, split_path, prior_path = _strict_fixture(tmp_path)
    output_path = tmp_path / "coverage_execution_library.json"

    returned = build_coverage_execution_library(
        dig_primitives_dir=dig_dir,
        split_path=split_path,
        output_path=output_path,
        coverage_prior_path=prior_path,
    )

    assert returned == output_path.resolve()
    text = output_path.read_text(encoding="utf-8")
    artifact = json.loads(text)
    assert text == (
        json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    assert artifact["schema"] == COVERAGE_EXECUTION_LIBRARY_SCHEMA
    assert artifact["status"] == "completed"
    assert artifact["sample_count"] == 374
    assert artifact["tail_audit"]["local_max_minus_token_gt_0_02_count"] == 218
    assert artifact["source_lineage"]["partition"] == "train"
    assert artifact["source_lineage"]["train_source_episode_ids"] == list(
        STRICT18_TRAIN_SOURCE_EPISODE_IDS
    )
    assert artifact["source_lineage"]["validation_source_episode_ids"] == [33, 34]
    assert artifact["env_state_contract"] == "agx_env_state_v2_4_107"
    assert artifact["source_contract"]["env_state_contract"] == (
        "agx_env_state_v2_3_89"
    )
    assert artifact["geometry_contract"] == {
        "all_rows_identical": True,
        "cell_long_size_m": 1.0,
        "cell_short_size_m": 1.25,
        "grid_long_count": 3,
        "grid_short_count": 2,
        "long_axis": 2,
        "profile": "conservative_2d_worktool_swept_footprint_v1",
        "sample_count": 374,
        "source": "primitive_first_frame_env_state",
        "source_env_state_indices": {
            "cell_long_size_m": 73,
            "cell_short_size_m": 74,
            "grid_long_count": 18,
            "grid_short_count": 19,
            "long_axis": 17,
        },
        "worktool_width_m": 0.7,
    }
    assert len(artifact["records"]) == 374

    first = artifact["records"][0]
    assert first["primitive_episode_id"] == 0
    assert first["source_episode_id"] == STRICT18_TRAIN_SOURCE_EPISODE_IDS[0]
    assert first["effect_outcome_cell_id"] == 0
    assert first["exemplar_id"] == "episode_0"
    assert first["corridor_id"] == 1_000_000
    assert first["return_envelope_cell_id"] == 1
    assert first["token_peak_local_index"] == 1
    assert first["execution_tail_plane_depth_reserve_m"] == pytest.approx(0.04)
    assert first["execution_tail_action_loss_valid_count"] == 2
    assert first["local_max_minus_token_m"] == pytest.approx(0.03)
    assert first["tuple_consistency_residual_m"] == pytest.approx(
        cut_tuple_consistency_residual_m(first["raw_fields"])
    )
    assert first["expected_centerline_physical_cell_ids"] == [2, 3]
    assert first["expected_swept_physical_cell_ids"] == [2, 3]
    assert len(first["dig_cut_tokens"]) == 10
    assert len(first["start_removed_depth_grid_m"]) == 6
    assert set(first["raw_fields"]) == {
        "operator_entry_x_m",
        "operator_entry_y_m",
        "operator_entry_z_m",
        "operator_exit_x_m",
        "operator_exit_y_m",
        "operator_exit_z_m",
        "operator_cut_direction_x",
        "operator_cut_direction_y",
        "operator_cut_direction_z",
        "operator_cut_length_m",
        "operator_cut_depth_peak_m",
        "operator_cut_payload_gain_kg",
        "operator_effective_deposit_delta_kg",
        "operator_cut_valid",
    }
    assert first["source_sha256"] == hashlib.sha256(
        (dig_dir / "episode_0.hdf5").read_bytes()
    ).hexdigest()
    assert artifact["records"][1][
        "execution_tail_action_loss_valid_count"
    ] == 0
    assert artifact["records"][1][
        "execution_tail_plane_depth_reserve_m"
    ] == 0.0
    assert (
        first["leave_one_out_nearest_neighbor"]["primitive_episode_id"]
        != first["primitive_episode_id"]
    )
    assert first["leave_one_out_nearest_neighbor"]["distance"] >= 0.0
    assert first["outcome_cell_loo_nearest_distance_p99"] == pytest.approx(
        artifact["cell_summary"]["0"][
            "leave_one_out_nearest_neighbor_distance_p99"
        ]
    )
    assert artifact["distance_contract"] == {
        "distance": "sqrt(mean(weighted((query-reference)/scale)^2))",
        "leave_one_out": True,
        "removed_depth_scale_m": 0.12,
        "state_vector": "start_removed_depth_grid_m cells 0..5",
        "target_cell_weight": 2.0,
        "target_cell": "effect_outcome_cell_id",
        "tie_break": "distance_then_primitive_episode_id",
    }
    assert artifact["corridor_id_contract"] == {
        "base": 1_000_000,
        "formula": "1000000 + primitive_episode_id",
        "legacy_outcome_cell_id_range": [0, 5],
        "purpose": "stable exemplar corridor identity disjoint from outcome cells",
    }
    assert artifact["tuple_consistency_contract"] == {
        "formula": "norm((exit_xyz-entry_xyz)-direction_xyz*cut_length_m)",
        "unit": "m",
    }
    query_raw = dict(first["raw_fields"])
    query_raw["operator_cut_length_m"] = float(
        query_raw["operator_cut_length_m"]
    ) + 0.25
    query = evaluate_coverage_execution_query(
        artifact,
        effect_outcome_cell_id=0,
        start_removed_depth_grid_m=first["start_removed_depth_grid_m"],
        raw_fields=query_raw,
    )
    assert query["nearest_exemplar_id"] == "episode_0"
    assert query["removed_depth_distance"] == pytest.approx(0.0)
    assert query["tuple_consistency_residual_m"] > 0.20
    assert query["tuple_consistency_residual_p99_m"] == pytest.approx(
        artifact["tuple_consistency_audit"]["residual_m"]["p99"]
    )
    assert query["outcome_cell_tuple_consistency_residual_p99_m"] == pytest.approx(
        artifact["cell_summary"]["0"]["tuple_consistency_residual_p99_m"]
    )

    duplicate_path = tmp_path / "duplicate.json"
    build_coverage_execution_library(
        dig_primitives_dir=dig_dir,
        split_path=split_path,
        output_path=duplicate_path,
        coverage_prior_path=prior_path,
    )
    assert duplicate_path.read_bytes() == output_path.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build_coverage_execution_library(
            dig_primitives_dir=dig_dir,
            split_path=split_path,
            output_path=output_path,
            coverage_prior_path=prior_path,
        )


def test_rejects_non_exact_split_validation_leak_and_forbidden_views(
    tmp_path: Path,
) -> None:
    dig_dir = tmp_path / "primitives_copy" / "dig"
    dig_dir.mkdir(parents=True)
    split_path = tmp_path / "dig_source_split.yaml"
    payload = _strict_split_payload(dig_dir)
    payload["train_ids"] = list(range(373))
    split_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly 374"):
        build_coverage_execution_library(
            dig_primitives_dir=dig_dir,
            split_path=split_path,
            output_path=tmp_path / "too_few.json",
        )

    payload = _strict_split_payload(dig_dir)
    source_mapping = payload["source_episode_id_by_primitive_episode_id"]
    assert isinstance(source_mapping, dict)
    source_mapping[0] = 33
    split_path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="validation source"):
        build_coverage_execution_library(
            dig_primitives_dir=dig_dir,
            split_path=split_path,
            output_path=tmp_path / "leak.json",
        )

    forbidden_dir = tmp_path / "partial_salvage" / "primitives_copy" / "dig"
    forbidden_dir.mkdir(parents=True)
    forbidden_split = tmp_path / "forbidden_split.yaml"
    forbidden_split.write_text(
        yaml.safe_dump(_strict_split_payload(forbidden_dir), sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="partial/layered/salvage"):
        build_coverage_execution_library(
            dig_primitives_dir=forbidden_dir,
            split_path=forbidden_split,
            output_path=tmp_path / "forbidden.json",
        )
