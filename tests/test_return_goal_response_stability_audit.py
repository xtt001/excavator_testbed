from __future__ import annotations

import json
import pickle
from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np
import pytest
import yaml

from testbed.eval import return_goal_response_stability_audit as audit
from testbed.eval.return_goal_response_stability_contract import (
    STAGE_A_MANIFEST_SCHEMA,
    sha256,
)


class _FakeTemporalPolicy:
    """Small deterministic policy whose aggregation can cancel a response."""

    def __init__(self, *, token_scale: float) -> None:
        self.token_scale = token_scale
        self.t = 0
        self._chunks: list[np.ndarray] = []

    def reset(self) -> None:
        self.t = 0
        self._chunks = []

    @property
    def temporal_aggregation_contract(self):
        return SimpleNamespace(
            enabled=True,
            num_queries=3,
            window=3,
            weight_order="legacy_oldest_first",
            decay=0.0,
            as_dict=lambda: {
                "enabled": True,
                "num_queries": 3,
                "window": 3,
                "weight_order": "legacy_oldest_first",
                "decay": 0.0,
            },
        )

    def predict_action_chunk(self, observation):
        token = float(np.asarray(observation["return_start_envelope_tokens_v1"])[0])
        # The first query responds, while later queries deliberately cancel it.
        return SimpleNamespace(
            actions=np.asarray(
                [
                    [token * self.token_scale],
                    [-token * self.token_scale],
                    [-token * self.token_scale],
                ],
                dtype=np.float32,
            )
        )

    def predict(self, observation):
        chunk = self.predict_action_chunk(observation).actions
        self._chunks.append(chunk)
        start = max(0, self.t - 2)
        contributors = [
            self._chunks[source][self.t - source]
            for source in range(start, self.t + 1)
        ]
        self.t += 1
        return np.mean(np.stack(contributors), axis=0)


def test_runtime_and_training_proprio_normalisation_match_for_return_token() -> None:
    stats = {
        "proprio_keys": np.asarray(
            ["qpos", "qvel", "return_start_envelope_tokens_v1"], dtype=object
        ),
        "proprio_mean": np.arange(26, dtype=np.float32),
        "proprio_std": np.full(26, 2.0, dtype=np.float32),
        "proprio_dim": 26,
    }
    observations = [
        {
            "qpos": np.asarray([1, 2, 3, 4], dtype=np.float32),
            "qvel": np.asarray([5, 6, 7, 8], dtype=np.float32),
        },
        {
            "qpos": np.asarray([2, 3, 4, 5], dtype=np.float32),
            "qvel": np.asarray([6, 7, 8, 9], dtype=np.float32),
        },
    ]
    token = np.arange(18, dtype=np.float32)

    result = audit.audit_return_token_normalisation(
        observations=observations,
        token=token,
        low_dim_keys=("qpos", "qvel", "return_start_envelope_tokens_v1"),
        norm_stats=stats,
    )

    assert result["status"] == "passed"
    assert result["raw_proprio_max_abs_delta"] == 0.0
    assert result["normalised_proprio_max_abs_delta"] == 0.0
    assert result["token_slice"] == {"start": 8, "stop": 26}


def test_temporal_diagnostics_identify_cancellation_without_relaxing_gate() -> None:
    baseline = np.zeros((3, 3, 1), dtype=np.float32)
    alternate = np.asarray(
        [
            [[1.0], [-1.0], [-1.0]],
            [[1.0], [-1.0], [-1.0]],
            [[1.0], [-1.0], [-1.0]],
        ],
        dtype=np.float32,
    )
    contract = {
        "enabled": True,
        "num_queries": 3,
        "window": 3,
        "weight_order": "legacy_oldest_first",
        "decay": 0.0,
    }

    result = audit.derive_temporal_aggregation_diagnostics(
        baseline_chunks=baseline,
        alternate_chunks=alternate,
        action_threshold=np.asarray([0.5], dtype=np.float32),
        temporal_contract=contract,
        required_responsive_frame_fraction=0.8,
    )

    assert result["raw_current_query_response_fraction"] == 1.0
    assert result["temporal_aggregated_response_fraction"] == pytest.approx(1 / 3)
    assert result["temporal_dilution_frame_indices"] == [1, 2]
    assert result["temporal_dilution_explains_gate_failure"] is True
    assert result["fixed_required_responsive_frame_fraction"] == 0.8
    assert result["cache_contributors"][2]["contributors"][0]["query_index"] == 2


def test_history_alignment_fingerprint_uses_pre_action_observation_rows(
    tmp_path: Path,
) -> None:
    hdf5_path = tmp_path / "episode.hdf5"
    with h5py.File(hdf5_path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.attrs["camera_names"] = "fpv"
        handle.create_dataset("timestamps/step_id", data=np.asarray([10, 11, 12]))
        handle.create_dataset("action", data=np.zeros((3, 4), dtype=np.float32))
        handle.create_dataset("observations/qpos", data=np.arange(12).reshape(3, 4))
        handle.create_dataset("observations/qvel", data=np.arange(12, 24).reshape(3, 4))
        handle.create_dataset(
            "observations/images/fpv",
            data=np.zeros((3, 2, 2, 3), dtype=np.uint8),
        )
    frames = (
        SimpleNamespace(
            action_step_id=11,
            observation_step_id=10,
            action_hdf5_index=1,
            observation_hdf5_index=0,
            qpos=np.asarray([0, 1, 2, 3], dtype=np.float32),
            qvel=np.asarray([12, 13, 14, 15], dtype=np.float32),
            model_token_key=None,
            token=None,
        ),
        SimpleNamespace(
            action_step_id=12,
            observation_step_id=11,
            action_hdf5_index=2,
            observation_hdf5_index=1,
            qpos=np.asarray([4, 5, 6, 7], dtype=np.float32),
            qvel=np.asarray([16, 17, 18, 19], dtype=np.float32),
            model_token_key=None,
            token=None,
        ),
    )

    with h5py.File(hdf5_path, "r") as handle:
        result = audit.audit_pre_action_observation_identity(
            hdf5_file=handle,
            frames=frames,
            camera_names=("fpv",),
        )

    assert result["status"] == "passed"
    assert result["frame_count"] == 2
    assert result["alignment_relation"] == "action_observation_step_id_delta_one"
    assert len(result["qpos_sequence_sha256"]) == 64
    assert len(result["raw_camera_sequence_sha256"]["fpv"]) == 64
    assert len(
        result["model_input_image_sequence_sha256"]["post_imagenet_normalisation"]
    ) == 64


def test_causal_status_uses_only_the_frozen_contract_statuses() -> None:
    both_inputs = audit._input_causal_status(
        token_audit={"status": "mismatch"},
        observation_identity={"status": "mismatch"},
    )
    assert both_inputs == {
        "status": "normalization_mismatch",
        "additional_statuses": ["observation_history_mismatch"],
        "reason": "frozen input contract did not reproduce before policy replay",
    }
    temporal = audit._temporal_causal_status(
        integrity_passed=True,
        temporal={
            "temporal_dilution_explains_gate_failure": True,
            "raw_current_query_response_fraction": 1.0,
        },
    )
    assert temporal["status"] == "temporal_aggregation_dilution"
    unexplained = audit._temporal_causal_status(
        integrity_passed=True,
        temporal={
            "temporal_dilution_explains_gate_failure": False,
            "raw_current_query_response_fraction": 0.7,
        },
    )
    assert unexplained == {
        "status": "not_explained_by_frozen_inputs",
        "reason": "input contract and temporal cache checks passed without a sufficient dilution explanation",
        "finding": "raw_frozen_policy_response_intermittent",
    }


def test_runner_writes_no_overwrite_causal_evidence_from_immutable_stage_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage_root = tmp_path / "stage"
    stage_root.mkdir()
    source = tmp_path / "source"
    (source / "rollouts").mkdir(parents=True)
    (source / "hdf5_rollouts").mkdir()
    checkpoint_dir = tmp_path / "checkpoint"
    checkpoint_dir.mkdir()
    checkpoint = checkpoint_dir / "policy_best.ckpt"
    checkpoint.write_bytes(b"checkpoint")
    stats_path = checkpoint_dir / "dataset_stats.pkl"
    with stats_path.open("wb") as handle:
        pickle.dump(
            {
                "action_std": np.ones(1, dtype=np.float32),
                "proprio_keys": np.asarray(
                    ["qpos", "qvel", "return_start_envelope_tokens_v1"],
                    dtype=object,
                ),
                "proprio_mean": np.zeros(26, dtype=np.float32),
                "proprio_std": np.ones(26, dtype=np.float32),
                "proprio_dim": 26,
            },
            handle,
        )
    eval_config = source / "eval_resolved_config.yaml"
    eval_config.write_text(
        yaml.safe_dump(
            {
                "task": {
                    "camera_names": ["fpv"],
                    "equipment_model": "yulong",
                    "episode_len": 10,
                },
                "policy": {
                    "return_ckpt_path": str(checkpoint),
                    "return_low_dim_keys": [
                        "qpos",
                        "qvel",
                        "return_start_envelope_tokens_v1",
                    ],
                    "act_params": {"chunk_size": 3},
                },
                "eval": {},
            }
        ),
        encoding="utf-8",
    )
    train_config = tmp_path / "return_train.yaml"
    train_config.write_text(
        yaml.safe_dump(
            {
                "policy": {
                    "low_dim_keys": [
                        "qpos",
                        "qvel",
                        "return_start_envelope_tokens_v1",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    metadata = source / "eval_run_metadata.json"
    metadata.write_text("{}\n", encoding="utf-8")
    jsonl = source / "rollouts" / "rollout_000.jsonl"
    jsonl.write_text("{}\n", encoding="utf-8")
    hdf5 = source / "hdf5_rollouts" / "episode_0.hdf5"
    hdf5.write_bytes(b"hdf5")

    def source_record(path: Path) -> dict[str, object]:
        return {"path": str(path), "sha256": sha256(path), "size_bytes": path.stat().st_size}

    manifest = {
        "schema": STAGE_A_MANIFEST_SCHEMA,
        "status": "completed",
        "evidence_kind": audit.EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "applied_support_contract_by_primitive": {
            "return": {"support_contract_version": "support_contract_v2"}
        },
        "source_lineage": {
            "source_results_root": str(source),
            "eval_resolved_config": source_record(eval_config),
            "eval_run_metadata": source_record(metadata),
            "rollout_jsonl": source_record(jsonl),
            "rollout_hdf5": source_record(hdf5),
            "return_training_config": source_record(train_config),
            "checkpoints_and_stats": {
                "return": {
                    "checkpoint": source_record(checkpoint),
                    "dataset_stats": source_record(stats_path),
                }
            },
        },
        "torch_performance": {
            "allow_tf32": False,
            "cudnn_benchmark": False,
            "matmul_precision": "highest",
        },
        "inference_instances": {},
    }
    (stage_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (stage_root / "baseline.json").write_text("{}\n", encoding="utf-8")
    return_payload = {
        "schema": "act_goal_condition_sensitivity_primitive_v1",
        "primitive": "return",
        "status": "completed",
        "segment_pair_records": [
            _invalid_record(audit.RETURN_INVALID_SEGMENT_IDS[0], audit.RETURN_INVALID_SEGMENT_IDS[1]),
            _invalid_record(audit.RETURN_INVALID_SEGMENT_IDS[1], "return:2323-2534:87aa0fb8c981"),
        ],
    }
    (stage_root / "return.json").write_text(json.dumps(return_payload), encoding="utf-8")

    segments = {
        audit.RETURN_INVALID_SEGMENT_IDS[0]: _segment(
            audit.RETURN_INVALID_SEGMENT_IDS[0], start=100, token=0.0
        ),
        audit.RETURN_INVALID_SEGMENT_IDS[1]: _segment(
            audit.RETURN_INVALID_SEGMENT_IDS[1], start=200, token=1.0
        ),
        "return:2323-2534:87aa0fb8c981": _segment(
            "return:2323-2534:87aa0fb8c981", start=300, token=2.0
        ),
    }
    monkeypatch.setattr(audit, "_load_return_segments", lambda **_kwargs: segments)
    monkeypatch.setattr(
        audit,
        "_audit_segment",
        lambda **kwargs: {
            "status": "completed",
            "baseline_segment": {"segment_id": kwargs["baseline_segment"].segment_id},
            "causal_status": {"status": "synthetic"},
            "temporal_aggregation": {"temporal_aggregated_response_fraction": 0.7},
        },
    )
    monkeypatch.setattr(
        audit,
        "_return_stage_temporal_contract",
        lambda **_kwargs: {
            "enabled": True,
            "num_queries": 3,
            "window": 3,
            "weight_order": "legacy_oldest_first",
            "decay": 0.0,
        },
    )

    result = audit.run_return_goal_response_stability_audit(
        stage_a_v2_output_root=stage_root,
        output_root=tmp_path / "out",
        device="cpu",
        policy_factory_builder=lambda _label: _FakeTemporalPolicy(token_scale=1.0),
        policy_describer=lambda _policy: {
            "temporal_aggregation": {
                "enabled": True,
                "num_queries": 3,
                "window": 3,
                "weight_order": "legacy_oldest_first",
                "decay": 0.0,
            },
            "action_std": [1.0],
        },
        require_clean_worktree=False,
    )

    assert result["status"] == "completed"
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == [
        "manifest.json",
        "report.md",
        "return_segments.json",
    ]
    with pytest.raises(FileExistsError):
        audit.run_return_goal_response_stability_audit(
            stage_a_v2_output_root=stage_root,
            output_root=tmp_path / "out",
            require_clean_worktree=False,
        )


def _segment(segment_id: str, *, start: int, token: float):
    values = np.full(18, token, dtype=np.float32)
    frames = tuple(
        SimpleNamespace(
            action_step_id=start + index,
            observation_step_id=start + index - 1,
            action_hdf5_index=start + index,
            observation_hdf5_index=start + index - 1,
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            token=values,
            model_token_key="return_start_envelope_tokens_v1",
            policy_dispatched=True,
            skill_name="return",
            skill_switch_reason="dump_to_return",
            policy_restarted=False,
        )
        for index in range(3)
    )
    return SimpleNamespace(
        segment_id=segment_id,
        skill_name="return",
        model_token_key="return_start_envelope_tokens_v1",
        token=values,
        token_sha256=f"token-{token}",
        token_source="synthetic",
        frames=frames,
        start_action_step_id=start,
        end_action_step_id=start + 2,
        frame_count=3,
    )


def _invalid_record(segment_id: str, alternate_segment_id: str) -> dict[str, object]:
    return {
        "segment": {"segment_id": segment_id},
        "alternate_segment": {"segment_id": alternate_segment_id},
        "result": {
            "status": "completed",
            "artifact_validity": {
                "passed": True,
                "replica_tolerance": {
                    "dispatched_tolerance_axis": [1.0e-6],
                    "replica_noise_cap_axis": [0.005],
                },
            },
            "baseline": {"response_threshold": [0.05], "action_std": [1.0]},
            "conditions": {
                "alternate": {
                    "classification": "goal_response_invalid",
                    "support": {
                        "baseline": {"status": "supported", "in_support_fraction": 1.0},
                        "counterfactual": {"status": "supported", "in_support_fraction": 1.0},
                    },
                    "replica_validity": {"passed": True},
                    "response_gate": {
                        "required_responsive_frame_fraction": 0.8,
                        "responsive_anchor_count": 3,
                        "anchor_count": 3,
                        "responsive_frame_fraction": 0.7,
                        "passed": False,
                    },
                    "temporal_aggregated_action_deltas": [[0.0], [0.0], [0.0]],
                }
            },
        },
    }
