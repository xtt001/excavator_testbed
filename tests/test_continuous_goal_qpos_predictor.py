from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace

import numpy as np
import pytest
import torch
from torch import nn

from testbed.data.continuous_goal_qpos_paths import (
    CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V1,
    PATH_PROGRESS,
    ContinuousGoalWorktoolSweepInputV2,
    vectorize_sweep_input,
)
from testbed.eval.continuous_goal_qpos_calibration import (
    FeatureNormalization,
    combined_calibration_sha256,
)
from testbed.policies.continuous_goal_qpos_artifact import (
    ContinuousGoalQposArtifactError,
    load_continuous_goal_qpos_predictor,
    save_continuous_goal_qpos_predictor,
)
from testbed.policies.continuous_goal_qpos_predictor import (
    ENSEMBLE_SEEDS,
    MODEL_OUTPUT_DIM,
    ContinuousGoalQposPredictorConfig,
    ContinuousGoalQposPredictorError,
    ContinuousGoalQposTrainingExample,
    canonical_continuous_goal_qpos_code_sha256,
    checkpoint_lineage_sha256,
    predictor_normalization_lineage_sha256,
    train_continuous_goal_qpos_predictor,
)


def _goal(
    depth: float = 0.12,
    *,
    effect_kind: str = "remove_soil",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "continuous_cut_goal_v1",
        "target_cell_id": 2,
        "entry_xz_m": [0.2, 0.4],
        "exit_xz_m": [0.5, 0.8],
        "direction_xz": [0.6, 0.8],
        "cut_length_m": 0.5,
        "planned_depth_m": depth,
        "payload_intent_kg": 45.0,
        "effect_intent": {
            "kind": effect_kind,
            "target_mass_kg": 45.0,
        },
        "terrain_signature": {"schema": "terrain_signature_v1"},
    }
    payload["goal_id"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return payload


def _request(
    *,
    source_id: int,
    sample_index: int,
    effect_kind: str = "remove_soil",
) -> ContinuousGoalWorktoolSweepInputV2:
    terrain = np.linspace(0.0, 0.2, 89)
    terrain += 0.001 * float(source_id % 10) + 0.0001 * sample_index
    return ContinuousGoalWorktoolSweepInputV2.create(
        handoff_qpos=[
            0.01 * source_id,
            0.2,
            0.3,
            0.4,
        ],
        handoff_qvel=[0.0, 0.01, 0.02, 0.03],
        continuous_goal=_goal(
            depth=0.10 + 0.001 * (source_id % 10),
            effect_kind=effect_kind,
        ),
        terrain_signature={
            "schema": "terrain_signature_v1",
            "values": terrain.tolist(),
        },
    )


def _path(request: ContinuousGoalWorktoolSweepInputV2) -> np.ndarray:
    offsets = np.column_stack(
        (
            0.08 * PATH_PROGRESS,
            -0.03 * PATH_PROGRESS**2,
            0.06 * PATH_PROGRESS,
            0.02 * np.sin(np.pi * PATH_PROGRESS),
        )
    )
    return np.asarray(request.handoff_qpos)[None, :] + offsets


def _examples() -> list[ContinuousGoalQposTrainingExample]:
    rows: list[ContinuousGoalQposTrainingExample] = []
    for source_id in range(5):
        for sample_index in range(2):
            request = _request(
                source_id=source_id,
                sample_index=sample_index,
            )
            rows.append(
                ContinuousGoalQposTrainingExample.create(
                    source_id=source_id,
                    sweep_input=request,
                    expert_qpos_path=_path(request),
                )
            )
    for source_id, sample_count in ((33, 29), (34, 30)):
        for sample_index in range(sample_count):
            request = _request(
                source_id=source_id,
                sample_index=sample_index,
            )
            rows.append(
                ContinuousGoalQposTrainingExample.create(
                    source_id=source_id,
                    sweep_input=request,
                    expert_qpos_path=_path(request),
                )
            )
    return rows


@pytest.fixture(scope="module")
def trained_predictor():
    return train_continuous_goal_qpos_predictor(
        examples=_examples(),
        config=ContinuousGoalQposPredictorConfig(
            epochs=2,
            batch_size=8,
            learning_rate=1.0e-2,
        ),
    )


def test_predictor_v1_architecture_and_grouped_training_are_locked(
    trained_predictor,
) -> None:
    config = trained_predictor.config

    assert config.hidden_dims == (64, 64)
    assert config.seeds == ENSEMBLE_SEEDS == (0, 1, 2, 3, 4)
    assert config.loss == "huber"
    assert len(trained_predictor.members) == 5
    assert len(trained_predictor.source_grouped_folds) == 5
    for member, fold in zip(
        trained_predictor.members,
        trained_predictor.source_grouped_folds,
        strict=True,
    ):
        assert member.seed == fold.fold_index
        assert not (set(member.train_source_ids) & set(fold.validation_source_ids))
        assert member.normalization.feature_names == (trained_predictor.feature_names)


def test_each_member_normalization_is_fit_only_on_its_training_sources(
    trained_predictor,
) -> None:
    examples = _examples()
    features = np.vstack(
        [
            vectorize_sweep_input(
                row.sweep_input,
                feature_names=trained_predictor.feature_names,
            )
            for row in examples
        ]
    )
    source_ids = np.asarray([row.source_id for row in examples])

    for member in trained_predictor.members:
        expected = FeatureNormalization.fit(
            features[np.isin(source_ids, member.train_source_ids)],
            feature_names=trained_predictor.feature_names,
        )
        assert member.normalization.mean == pytest.approx(expected.mean)
        assert member.normalization.scale == pytest.approx(expected.scale)
        assert member.normalization.lineage_sha256 == (expected.lineage_sha256)


def test_code_and_normalization_lineage_are_canonical(
    trained_predictor,
) -> None:
    code_sha = canonical_continuous_goal_qpos_code_sha256()
    normalization_sha = predictor_normalization_lineage_sha256(
        ood_normalization=trained_predictor.normalization,
        members=trained_predictor.members,
    )

    assert trained_predictor.predictor_code_sha256 == code_sha
    assert trained_predictor.normalization_lineage_sha256 == (normalization_sha)
    assert normalization_sha != trained_predictor.normalization.lineage_sha256

    with pytest.raises(
        ContinuousGoalQposPredictorError,
        match="canonical code lineage",
    ):
        train_continuous_goal_qpos_predictor(
            examples=_examples(),
            predictor_code_sha256="a" * 64,
            config=ContinuousGoalQposPredictorConfig(epochs=1),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"epochs": True},
        {"batch_size": True},
        {"learning_rate": True},
        {"weight_decay": False},
        {"huber_delta": True},
        {"seeds": (0, True, 2, 3, 4)},
    ],
)
def test_predictor_config_rejects_bool_optimization_and_count_values(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ContinuousGoalQposPredictorError):
        ContinuousGoalQposPredictorConfig(**kwargs)


def test_predictor_fold_index_rejects_bool(
    trained_predictor,
) -> None:
    folds = (
        replace(
            trained_predictor.source_grouped_folds[0],
            fold_index=True,
        ),
        *trained_predictor.source_grouped_folds[1:],
    )

    with pytest.raises(
        ContinuousGoalQposPredictorError,
        match="fold",
    ):
        replace(
            trained_predictor,
            source_grouped_folds=folds,
        )


def test_predictor_returns_64x4_path_bounds_and_complete_lineage(
    trained_predictor,
) -> None:
    request = _request(source_id=0, sample_index=0)

    result = trained_predictor.predict(request)

    assert result.status == "passed"
    assert result.inference_allowed is True
    assert result.support_status == "supported"
    assert result.path_progress.shape == (64,)
    assert result.qpos_path.shape == (64, 4)
    assert result.qpos_abs_error_bound.shape == (64, 4)
    assert result.coverage_level == 0.95
    assert result.normalization_lineage_sha256 == (
        trained_predictor.normalization_lineage_sha256
    )
    assert result.qpos_path[0] == pytest.approx(
        request.handoff_qpos,
        abs=1.0e-6,
    )
    assert np.all(result.qpos_abs_error_bound >= 0.0)
    for value in (
        result.normalization_lineage_sha256,
        result.checkpoint_lineage_sha256,
        result.calibration_lineage_sha256,
        result.goal_lineage_sha256,
        result.predictor_code_lineage_sha256,
        result.path_lineage_sha256,
    ):
        assert len(value) == 64
    assert np.asarray(result.as_dict()["qpos_path"]) == pytest.approx(result.qpos_path)


def test_predictor_fails_closed_on_ood_legacy_missing_calibration_and_drift(
    trained_predictor,
) -> None:
    request = _request(source_id=0, sample_index=0)
    far = request.as_dict()
    far["terrain_signature"]["values"] = [10000.0] * 89
    far.pop("input_sha256")

    ood = trained_predictor.predict(far)
    assert ood.status == "blocked"
    assert ood.support_status == "ood"
    assert ood.inference_allowed is False
    assert "ood" in ood.blockers

    legacy = trained_predictor.predict(
        {
            "schema": CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V1,
            "historic_payload": {},
        }
    )
    assert legacy.status == "blocked"
    assert "input_contract_v2_required" in legacy.blockers

    no_calibration_predictor = copy.copy(trained_predictor)
    object.__setattr__(
        no_calibration_predictor,
        "conformal_calibration",
        None,
    )
    no_calibration = no_calibration_predictor.predict(request)
    assert no_calibration.status == "blocked"
    assert "calibration_missing" in no_calibration.blockers

    drift = trained_predictor.predict(
        request,
        expected_lineage={"checkpoint_sha256": "b" * 64},
    )
    assert drift.status == "blocked"
    assert "lineage_mismatch" in drift.blockers


def test_in_memory_semantics_reject_rehashed_coverage_and_fake_ood_threshold(
    trained_predictor,
) -> None:
    conformal = replace(
        trained_predictor.conformal_calibration,
        coverage_level=0.90,
        lineage_sha256="",
    )
    conformal = replace(
        conformal,
        lineage_sha256=conformal.computed_lineage_sha256(),
    )
    with pytest.raises(
        ContinuousGoalQposPredictorError,
        match="conformal",
    ):
        replace(
            trained_predictor,
            conformal_calibration=conformal,
            calibration_lineage_sha256=combined_calibration_sha256(
                ood=trained_predictor.ood_calibration,
                conformal=conformal,
            ),
        )

    ood = replace(
        trained_predictor.ood_calibration,
        threshold=1.0e12,
        lineage_sha256="",
    )
    ood = replace(
        ood,
        lineage_sha256=ood.computed_lineage_sha256(),
    )
    with pytest.raises(
        ContinuousGoalQposPredictorError,
        match="OOD",
    ):
        replace(
            trained_predictor,
            ood_calibration=ood,
            calibration_lineage_sha256=combined_calibration_sha256(
                ood=ood,
                conformal=trained_predictor.conformal_calibration,
            ),
        )


def test_predict_rechecks_shared_semantics_after_memory_tampering(
    trained_predictor,
) -> None:
    conformal = replace(
        trained_predictor.conformal_calibration,
        coverage_level=0.90,
        lineage_sha256="",
    )
    conformal = replace(
        conformal,
        lineage_sha256=conformal.computed_lineage_sha256(),
    )
    predictor = copy.copy(trained_predictor)
    object.__setattr__(predictor, "conformal_calibration", conformal)
    object.__setattr__(
        predictor,
        "calibration_lineage_sha256",
        combined_calibration_sha256(
            ood=predictor.ood_calibration,
            conformal=conformal,
        ),
    )

    result = predictor.predict(_request(source_id=0, sample_index=0))

    assert result.status == "blocked"
    assert "contract_invalid" in result.blockers


def test_predictor_nonfinite_member_output_fails_closed(
    trained_predictor,
) -> None:
    class NonfiniteModel(nn.Module):
        def forward(self, features: torch.Tensor) -> torch.Tensor:
            return torch.full(
                (features.shape[0], MODEL_OUTPUT_DIM),
                float("nan"),
                dtype=features.dtype,
                device=features.device,
            )

    members = (
        replace(trained_predictor.members[0], model=NonfiniteModel()),
        *trained_predictor.members[1:],
    )
    predictor = replace(
        trained_predictor,
        members=members,
        checkpoint_lineage_sha256=checkpoint_lineage_sha256(
            members,
            trained_predictor.feature_names,
        ),
    )

    result = predictor.predict(_request(source_id=0, sample_index=0))

    assert result.status == "blocked"
    assert result.support_status == "invalid"
    assert "nonfinite_or_invalid_output" in result.blockers
    assert result.inference_allowed is False


def test_predictor_unknown_effect_category_fails_closed(
    trained_predictor,
) -> None:
    result = trained_predictor.predict(
        _request(
            source_id=0,
            sample_index=0,
            effect_kind="compact_soil",
        )
    )

    assert result.status == "blocked"
    assert result.support_status == "invalid"
    assert "nonfinite_or_invalid_input" in result.blockers


def test_predictor_artifact_round_trip_is_strict_and_no_overwrite(
    trained_predictor,
    tmp_path,
) -> None:
    artifact_dir = tmp_path / "predictor"

    saved = save_continuous_goal_qpos_predictor(
        trained_predictor,
        artifact_dir,
    )
    manifest_lineage = json.loads(
        (saved / "manifest.json").read_text(encoding="utf-8")
    )["lineage"]
    assert set(manifest_lineage) == {
        "normalization_sha256",
        "checkpoint_sha256",
        "calibration_sha256",
        "predictor_code_sha256",
    }
    loaded = load_continuous_goal_qpos_predictor(saved)

    assert loaded.checkpoint_lineage_sha256 == (
        trained_predictor.checkpoint_lineage_sha256
    )
    assert loaded.normalization.lineage_sha256 == (
        trained_predictor.normalization.lineage_sha256
    )
    assert loaded.normalization_lineage_sha256 == (
        trained_predictor.normalization_lineage_sha256
    )
    assert tuple(
        member.normalization.lineage_sha256 for member in loaded.members
    ) == tuple(
        member.normalization.lineage_sha256 for member in trained_predictor.members
    )
    assert loaded.calibration_lineage_sha256 == (
        trained_predictor.calibration_lineage_sha256
    )
    expected = trained_predictor.predict(_request(source_id=0, sample_index=0))
    actual = loaded.predict(_request(source_id=0, sample_index=0))
    assert actual.status == "passed"
    prediction_lineage = actual.as_dict()["lineage"]
    assert {
        key: prediction_lineage[key] for key in manifest_lineage
    } == manifest_lineage
    assert actual.qpos_path == pytest.approx(expected.qpos_path)
    assert actual.qpos_abs_error_bound == pytest.approx(expected.qpos_abs_error_bound)

    with pytest.raises(FileExistsError):
        save_continuous_goal_qpos_predictor(
            trained_predictor,
            artifact_dir,
        )


def test_predictor_artifact_rejects_checkpoint_file_drift(
    trained_predictor,
    tmp_path,
) -> None:
    artifact_dir = save_continuous_goal_qpos_predictor(
        trained_predictor,
        tmp_path / "drifted",
    )
    member_path = artifact_dir / "member_seed_0.pt"
    member_path.write_bytes(member_path.read_bytes() + b"drift")

    with pytest.raises(
        ContinuousGoalQposArtifactError,
        match="file lineage",
    ):
        load_continuous_goal_qpos_predictor(artifact_dir)


def test_artifact_rejects_rehashed_non_95_percent_conformal_semantics(
    trained_predictor,
    tmp_path,
) -> None:
    artifact_dir = save_continuous_goal_qpos_predictor(
        trained_predictor,
        tmp_path / "semantic-drift",
    )
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    conformal = manifest["conformal_calibration"]
    conformal["coverage_level"] = 0.90
    conformal["lineage_sha256"] = hashlib.sha256(
        json.dumps(
            {
                "absolute_error_bound": conformal["absolute_error_bound"],
                "coverage_level": 0.90,
                "source_ids": conformal["source_ids"],
                "source_sample_counts": conformal["source_sample_counts"],
                "calibration_sample_count": conformal["calibration_sample_count"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    manifest["lineage"]["calibration_sha256"] = hashlib.sha256(
        json.dumps(
            {
                "ood_lineage_sha256": manifest["ood_calibration"]["lineage_sha256"],
                "conformal_lineage_sha256": conformal["lineage_sha256"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    manifest.pop("artifact_payload_sha256")
    manifest["artifact_payload_sha256"] = hashlib.sha256(
        json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ContinuousGoalQposArtifactError,
        match="conformal semantics",
    ):
        load_continuous_goal_qpos_predictor(artifact_dir)


def test_artifact_save_rejects_non_95_percent_conformal_semantics(
    trained_predictor,
    tmp_path,
) -> None:
    conformal = replace(
        trained_predictor.conformal_calibration,
        coverage_level=0.90,
        lineage_sha256="",
    )
    conformal = replace(
        conformal,
        lineage_sha256=conformal.computed_lineage_sha256(),
    )
    predictor = copy.copy(trained_predictor)
    object.__setattr__(predictor, "conformal_calibration", conformal)
    object.__setattr__(
        predictor,
        "calibration_lineage_sha256",
        combined_calibration_sha256(
            ood=trained_predictor.ood_calibration,
            conformal=conformal,
        ),
    )

    with pytest.raises(
        ContinuousGoalQposArtifactError,
        match="conformal semantics",
    ):
        save_continuous_goal_qpos_predictor(
            predictor,
            tmp_path / "invalid-save",
        )


def test_artifact_load_rejects_bool_calibration_sample_count(
    trained_predictor,
    tmp_path,
) -> None:
    artifact_dir = save_continuous_goal_qpos_predictor(
        trained_predictor,
        tmp_path / "bool-count",
    )
    manifest_path = artifact_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["conformal_calibration"]["calibration_sample_count"] = True
    manifest.pop("artifact_payload_sha256")
    manifest["artifact_payload_sha256"] = hashlib.sha256(
        json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ContinuousGoalQposArtifactError,
        match="sample count",
    ):
        load_continuous_goal_qpos_predictor(artifact_dir)
