"""No-overwrite persistence for continuous-goal qpos predictor artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import torch

from testbed.eval.continuous_goal_qpos_calibration import (
    CalibrationContractError,
    ConformalQposCalibration,
    FeatureNormalization,
    LosoOODCalibration,
    SourceGroupedFold,
    combined_calibration_sha256,
    predictor_normalization_lineage_sha256,
    validate_qpos_predictor_semantics,
)
from testbed.policies.continuous_goal_qpos_predictor import (
    CONTINUOUS_GOAL_QPOS_PREDICTOR_PROFILE,
    CONTINUOUS_GOAL_QPOS_PREDICTOR_VERSION,
    ContinuousGoalQposEnsembleMember,
    ContinuousGoalQposPredictorConfig,
    ContinuousGoalQposPredictorError,
    ContinuousGoalQposSweepPredictor,
    build_continuous_goal_qpos_mlp,
    canonical_continuous_goal_qpos_code_sha256,
    checkpoint_lineage_sha256,
)

CONTINUOUS_GOAL_QPOS_ARTIFACT_SCHEMA = "continuous_goal_qpos_predictor_artifact_v1"
CONTINUOUS_GOAL_QPOS_MEMBER_SCHEMA = "continuous_goal_qpos_predictor_member_v1"
MANIFEST_FILE = "manifest.json"


class ContinuousGoalQposArtifactError(ValueError):
    """Raised when a persisted predictor is incomplete or has drifted."""


def save_continuous_goal_qpos_predictor(
    predictor: ContinuousGoalQposSweepPredictor,
    output_dir: str | Path,
) -> Path:
    """Atomically create one artifact directory; never overwrite."""

    if not isinstance(predictor, ContinuousGoalQposSweepPredictor):
        raise ContinuousGoalQposArtifactError(
            "predictor artifact requires a trained predictor"
        )
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"predictor artifact destination already exists: {destination}"
        )
    _validate_predictor_lineage(predictor)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-",
            dir=destination.parent,
        )
    )
    try:
        members_payload: list[dict[str, Any]] = []
        for member in predictor.members:
            filename = f"member_seed_{member.seed}.pt"
            path = temporary / filename
            torch.save(
                {
                    "schema": CONTINUOUS_GOAL_QPOS_MEMBER_SCHEMA,
                    "profile": CONTINUOUS_GOAL_QPOS_PREDICTOR_PROFILE,
                    "version": CONTINUOUS_GOAL_QPOS_PREDICTOR_VERSION,
                    "seed": member.seed,
                    "train_source_ids": list(member.train_source_ids),
                    "validation_source_ids": list(member.validation_source_ids),
                    "input_dim": len(predictor.feature_names),
                    "normalization": member.normalization.as_dict(),
                    "state_dict": member.model.state_dict(),
                },
                path,
            )
            members_payload.append(
                {
                    "seed": member.seed,
                    "file": filename,
                    "file_sha256": _file_sha256(path),
                    "train_source_ids": list(member.train_source_ids),
                    "validation_source_ids": list(member.validation_source_ids),
                    "normalization_sha256": (member.normalization.lineage_sha256),
                    "final_training_loss": member.final_training_loss,
                }
            )
        conformal = predictor.conformal_calibration
        if conformal is None:
            raise ContinuousGoalQposArtifactError(
                "cannot persist predictor without conformal calibration"
            )
        manifest: dict[str, Any] = {
            "schema": CONTINUOUS_GOAL_QPOS_ARTIFACT_SCHEMA,
            "profile": CONTINUOUS_GOAL_QPOS_PREDICTOR_PROFILE,
            "version": CONTINUOUS_GOAL_QPOS_PREDICTOR_VERSION,
            "config": asdict(predictor.config),
            "feature_names": list(predictor.feature_names),
            "source_grouped_folds": [
                {
                    "fold_index": fold.fold_index,
                    "train_source_ids": list(fold.train_source_ids),
                    "validation_source_ids": list(fold.validation_source_ids),
                }
                for fold in predictor.source_grouped_folds
            ],
            "normalization": predictor.normalization.as_dict(),
            "ood_calibration": predictor.ood_calibration.as_dict(),
            "conformal_calibration": conformal.as_dict(),
            "members": members_payload,
            "lineage": {
                "normalization_sha256": (predictor.normalization_lineage_sha256),
                "checkpoint_sha256": (predictor.checkpoint_lineage_sha256),
                "calibration_sha256": (predictor.calibration_lineage_sha256),
                "predictor_code_sha256": (predictor.predictor_code_sha256),
            },
        }
        manifest["artifact_payload_sha256"] = _canonical_sha256(manifest)
        (temporary / MANIFEST_FILE).write_text(
            json.dumps(
                manifest,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        if destination.exists():
            raise FileExistsError(
                f"predictor artifact destination appeared during save: {destination}"
            )
        os.rename(temporary, destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return destination


def load_continuous_goal_qpos_predictor(
    artifact_dir: str | Path,
    *,
    device: str = "cpu",
) -> ContinuousGoalQposSweepPredictor:
    """Strictly load model state and re-verify every declared lineage."""

    root = Path(artifact_dir).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ContinuousGoalQposArtifactError(
            f"predictor artifact must be a directory: {root}"
        )
    manifest = _mapping(
        json.loads((root / MANIFEST_FILE).read_text(encoding="utf-8")),
        label="manifest",
    )
    if manifest.get("schema") != CONTINUOUS_GOAL_QPOS_ARTIFACT_SCHEMA:
        raise ContinuousGoalQposArtifactError("predictor artifact schema mismatch")
    if (
        manifest.get("profile") != CONTINUOUS_GOAL_QPOS_PREDICTOR_PROFILE
        or manifest.get("version") != CONTINUOUS_GOAL_QPOS_PREDICTOR_VERSION
    ):
        raise ContinuousGoalQposArtifactError(
            "predictor artifact profile/version mismatch"
        )
    supplied_artifact_sha = str(manifest.get("artifact_payload_sha256", ""))
    payload_without_sha = dict(manifest)
    payload_without_sha.pop("artifact_payload_sha256", None)
    if supplied_artifact_sha != _canonical_sha256(payload_without_sha):
        raise ContinuousGoalQposArtifactError(
            "predictor artifact manifest lineage mismatch"
        )
    config_mapping = dict(_mapping(manifest.get("config"), label="config"))
    config_mapping["hidden_dims"] = tuple(config_mapping["hidden_dims"])
    config_mapping["seeds"] = tuple(config_mapping["seeds"])
    config_mapping["device"] = device
    try:
        config = ContinuousGoalQposPredictorConfig(**config_mapping)
    except (KeyError, TypeError, ContinuousGoalQposPredictorError) as exc:
        raise ContinuousGoalQposArtifactError(
            "predictor artifact config invalid"
        ) from exc
    feature_names = tuple(str(value) for value in manifest["feature_names"])
    if not feature_names or len(set(feature_names)) != len(feature_names):
        raise ContinuousGoalQposArtifactError(
            "predictor artifact feature schema invalid"
        )
    normalization = _load_normalization(
        _mapping(manifest.get("normalization"), label="normalization"),
        feature_names=feature_names,
    )
    ood = _load_ood(
        _mapping(manifest.get("ood_calibration"), label="ood_calibration"),
        feature_dim=len(feature_names),
    )
    conformal = _load_conformal(
        _mapping(
            manifest.get("conformal_calibration"),
            label="conformal_calibration",
        )
    )
    folds = tuple(
        SourceGroupedFold(
            fold_index=_strict_int(
                row["fold_index"],
                label="fold_index",
                minimum=0,
            ),
            train_source_ids=tuple(
                _strict_int(value, label="train_source_id", minimum=0)
                for value in row["train_source_ids"]
            ),
            validation_source_ids=tuple(
                _strict_int(
                    value,
                    label="validation_source_id",
                    minimum=0,
                )
                for value in row["validation_source_ids"]
            ),
        )
        for row in (
            _mapping(value, label="source_grouped_fold")
            for value in manifest["source_grouped_folds"]
        )
    )
    member_rows = tuple(
        _mapping(value, label="member") for value in manifest["members"]
    )
    expected_files = {MANIFEST_FILE} | {str(row["file"]) for row in member_rows}
    observed_files = {path.name for path in root.iterdir()}
    if observed_files != expected_files:
        raise ContinuousGoalQposArtifactError(
            "predictor artifact file inventory mismatch"
        )
    members: list[ContinuousGoalQposEnsembleMember] = []
    for row in member_rows:
        path = root / str(row["file"])
        if _file_sha256(path) != str(row.get("file_sha256", "")):
            raise ContinuousGoalQposArtifactError(
                f"predictor member file lineage mismatch: {path.name}"
            )
        checkpoint = _mapping(
            torch.load(path, map_location=device, weights_only=True),
            label="member_checkpoint",
        )
        _validate_member_checkpoint(
            checkpoint,
            row=row,
            input_dim=len(feature_names),
        )
        model = build_continuous_goal_qpos_mlp(input_dim=len(feature_names)).to(
            torch.device(device)
        )
        try:
            model.load_state_dict(checkpoint["state_dict"], strict=True)
        except RuntimeError as exc:
            raise ContinuousGoalQposArtifactError(
                f"predictor member state invalid: {path.name}"
            ) from exc
        model.eval()
        raw_final_loss = row["final_training_loss"]
        if isinstance(raw_final_loss, bool):
            raise ContinuousGoalQposArtifactError(
                f"predictor member loss invalid: {path.name}"
            )
        final_training_loss = float(raw_final_loss)
        if not np.isfinite(final_training_loss):
            raise ContinuousGoalQposArtifactError(
                f"predictor member loss invalid: {path.name}"
            )
        member_normalization = _load_normalization(
            _mapping(
                checkpoint.get("normalization"),
                label="member.normalization",
            ),
            feature_names=feature_names,
        )
        if member_normalization.lineage_sha256 != str(
            row.get("normalization_sha256", "")
        ):
            raise ContinuousGoalQposArtifactError(
                f"predictor member normalization drift: {path.name}"
            )
        members.append(
            ContinuousGoalQposEnsembleMember(
                seed=_strict_int(
                    row["seed"],
                    label="member seed",
                    minimum=0,
                ),
                train_source_ids=tuple(
                    _strict_int(
                        value,
                        label="member train_source_id",
                        minimum=0,
                    )
                    for value in row["train_source_ids"]
                ),
                validation_source_ids=tuple(
                    _strict_int(
                        value,
                        label="member validation_source_id",
                        minimum=0,
                    )
                    for value in row["validation_source_ids"]
                ),
                normalization=member_normalization,
                model=model,
                final_training_loss=final_training_loss,
            )
        )
    lineage = _mapping(manifest.get("lineage"), label="lineage")
    member_tuple = tuple(members)
    normalization_lineage = predictor_normalization_lineage_sha256(
        ood_normalization=normalization,
        members=member_tuple,
    )
    expected_lineage = {
        "normalization_sha256": normalization_lineage,
        "checkpoint_sha256": str(lineage.get("checkpoint_sha256", "")),
        "calibration_sha256": str(lineage.get("calibration_sha256", "")),
        "predictor_code_sha256": str(lineage.get("predictor_code_sha256", "")),
    }
    if dict(lineage) != expected_lineage:
        raise ContinuousGoalQposArtifactError(
            "predictor manifest lineage inventory mismatch"
        )
    try:
        predictor = ContinuousGoalQposSweepPredictor(
            config=config,
            members=member_tuple,
            source_grouped_folds=folds,
            feature_names=feature_names,
            normalization=normalization,
            ood_calibration=ood,
            conformal_calibration=conformal,
            predictor_code_sha256=str(lineage.get("predictor_code_sha256", "")),
            normalization_lineage_sha256=normalization_lineage,
            checkpoint_lineage_sha256=str(lineage.get("checkpoint_sha256", "")),
            calibration_lineage_sha256=str(lineage.get("calibration_sha256", "")),
        )
    except ContinuousGoalQposPredictorError as exc:
        raise ContinuousGoalQposArtifactError(
            f"predictor artifact fixed semantics invalid: {exc}"
        ) from exc
    _validate_predictor_lineage(predictor)
    return predictor


def _load_normalization(
    value: Mapping[str, Any],
    *,
    feature_names: tuple[str, ...],
) -> FeatureNormalization:
    names = tuple(str(item) for item in value["feature_names"])
    mean = np.asarray(value["mean"], dtype=np.float64)
    scale = np.asarray(value["scale"], dtype=np.float64)
    if (
        names != feature_names
        or mean.shape != (len(names),)
        or scale.shape != (len(names),)
        or not np.all(np.isfinite(mean))
        or not np.all(np.isfinite(scale))
        or np.any(scale <= 0.0)
    ):
        raise ContinuousGoalQposArtifactError("predictor normalization invalid")
    mean.setflags(write=False)
    scale.setflags(write=False)
    normalization = FeatureNormalization(
        feature_names=names,
        mean=mean,
        scale=scale,
        lineage_sha256=str(value.get("lineage_sha256", "")),
    )
    if normalization.computed_lineage_sha256() != (normalization.lineage_sha256):
        raise ContinuousGoalQposArtifactError(
            "predictor normalization lineage mismatch"
        )
    return normalization


def _load_ood(
    value: Mapping[str, Any],
    *,
    feature_dim: int,
) -> LosoOODCalibration:
    source_ids = tuple(
        _strict_int(item, label="OOD source_id", minimum=0)
        for item in value["source_ids"]
    )
    centroids = np.asarray(value["source_centroids"], dtype=np.float64)
    distance_samples = np.asarray(
        value["loso_distance_samples"],
        dtype=np.float64,
    )
    training_sample_count = _strict_int(
        value["training_sample_count"],
        label="OOD training sample count",
        minimum=1,
    )
    if isinstance(value["threshold"], bool):
        raise ContinuousGoalQposArtifactError("predictor OOD threshold invalid")
    threshold = float(value["threshold"])
    if (
        centroids.shape != (len(source_ids), feature_dim)
        or not np.all(np.isfinite(centroids))
        or distance_samples.shape != (training_sample_count,)
        or not np.all(np.isfinite(distance_samples))
        or np.any(distance_samples < 0.0)
        or not np.isfinite(threshold)
        or threshold < 0.0
    ):
        raise ContinuousGoalQposArtifactError("predictor OOD calibration invalid")
    centroids.setflags(write=False)
    distance_samples.setflags(write=False)
    calibration = LosoOODCalibration(
        source_ids=source_ids,
        source_centroids=centroids,
        loso_distance_samples=distance_samples,
        training_sample_count=training_sample_count,
        threshold=threshold,
        threshold_rule=str(value["threshold_rule"]),
        lineage_sha256=str(value.get("lineage_sha256", "")),
    )
    if calibration.computed_lineage_sha256() != calibration.lineage_sha256:
        raise ContinuousGoalQposArtifactError(
            "predictor OOD calibration lineage mismatch"
        )
    return calibration


def _load_conformal(
    value: Mapping[str, Any],
) -> ConformalQposCalibration:
    bounds = np.asarray(value["absolute_error_bound"], dtype=np.float64)
    raw_coverage = value["coverage_level"]
    if isinstance(raw_coverage, bool):
        raise ContinuousGoalQposArtifactError("predictor conformal coverage invalid")
    sample_count = _strict_int(
        value["calibration_sample_count"],
        label="predictor conformal sample count",
        minimum=1,
    )
    source_ids = tuple(
        _strict_int(item, label="conformal source_id", minimum=0)
        for item in value["source_ids"]
    )
    source_sample_counts = tuple(
        _source_count_pair(item) for item in value["source_sample_counts"]
    )
    if (
        bounds.shape != (64, 4)
        or not np.all(np.isfinite(bounds))
        or np.any(bounds < 0.0)
    ):
        raise ContinuousGoalQposArtifactError("predictor conformal calibration invalid")
    bounds.setflags(write=False)
    calibration = ConformalQposCalibration(
        absolute_error_bound=bounds,
        coverage_level=float(raw_coverage),
        source_ids=source_ids,
        source_sample_counts=source_sample_counts,
        calibration_sample_count=sample_count,
        lineage_sha256=str(value.get("lineage_sha256", "")),
    )
    if calibration.computed_lineage_sha256() != calibration.lineage_sha256:
        raise ContinuousGoalQposArtifactError(
            "predictor conformal calibration lineage mismatch"
        )
    return calibration


def _validate_member_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    row: Mapping[str, Any],
    input_dim: int,
) -> None:
    expected = {
        "schema": CONTINUOUS_GOAL_QPOS_MEMBER_SCHEMA,
        "profile": CONTINUOUS_GOAL_QPOS_PREDICTOR_PROFILE,
        "version": CONTINUOUS_GOAL_QPOS_PREDICTOR_VERSION,
    }
    for field, expected_value in expected.items():
        if checkpoint.get(field) != expected_value:
            raise ContinuousGoalQposArtifactError(
                f"predictor member checkpoint {field} mismatch"
            )
    for field, minimum in (("seed", 0), ("input_dim", 1)):
        if _strict_int(
            checkpoint.get(field),
            label=f"checkpoint {field}",
            minimum=minimum,
        ) != _strict_int(
            row["seed"] if field == "seed" else input_dim,
            label=f"manifest {field}",
            minimum=minimum,
        ):
            raise ContinuousGoalQposArtifactError(
                f"predictor member checkpoint {field} mismatch"
            )
    for field in ("train_source_ids", "validation_source_ids"):
        checkpoint_ids = tuple(
            _strict_int(
                value,
                label=f"checkpoint {field}",
                minimum=0,
            )
            for value in checkpoint.get(field, ())
        )
        manifest_ids = tuple(
            _strict_int(
                value,
                label=f"manifest {field}",
                minimum=0,
            )
            for value in row[field]
        )
        if checkpoint_ids != manifest_ids:
            raise ContinuousGoalQposArtifactError(
                f"predictor member checkpoint {field} mismatch"
            )
    if not isinstance(checkpoint.get("normalization"), Mapping):
        raise ContinuousGoalQposArtifactError(
            "predictor member checkpoint normalization missing"
        )
    if not isinstance(checkpoint.get("state_dict"), Mapping):
        raise ContinuousGoalQposArtifactError(
            "predictor member checkpoint state_dict missing"
        )


def _validate_predictor_lineage(
    predictor: ContinuousGoalQposSweepPredictor,
) -> None:
    conformal = predictor.conformal_calibration
    if conformal is None:
        raise ContinuousGoalQposArtifactError("predictor conformal calibration missing")
    try:
        validate_qpos_predictor_semantics(
            members=predictor.members,
            folds=predictor.source_grouped_folds,
            feature_names=predictor.feature_names,
            ood_normalization=predictor.normalization,
            ood=predictor.ood_calibration,
            conformal=conformal,
        )
    except CalibrationContractError as exc:
        raise ContinuousGoalQposArtifactError(
            f"predictor fixed semantics invalid: {exc}"
        ) from exc
    if (
        predictor_normalization_lineage_sha256(
            ood_normalization=predictor.normalization,
            members=predictor.members,
        )
        != predictor.normalization_lineage_sha256
        or checkpoint_lineage_sha256(
            predictor.members,
            predictor.feature_names,
        )
        != predictor.checkpoint_lineage_sha256
        or combined_calibration_sha256(
            ood=predictor.ood_calibration,
            conformal=conformal,
        )
        != predictor.calibration_lineage_sha256
        or predictor.predictor_code_sha256
        != canonical_continuous_goal_qpos_code_sha256()
    ):
        raise ContinuousGoalQposArtifactError("predictor artifact lineage mismatch")


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContinuousGoalQposArtifactError(f"{label} must be a mapping")
    return value


def _strict_int(value: Any, *, label: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ContinuousGoalQposArtifactError(
            f"{label} must be an integer >= {minimum}"
        )
    parsed = int(value)
    if parsed < minimum:
        raise ContinuousGoalQposArtifactError(
            f"{label} must be an integer >= {minimum}"
        )
    return parsed


def _source_count_pair(value: Any) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ContinuousGoalQposArtifactError(
            "conformal source sample count must be a pair"
        )
    return (
        _strict_int(value[0], label="conformal count source_id", minimum=0),
        _strict_int(value[1], label="conformal source sample count", minimum=1),
    )


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "CONTINUOUS_GOAL_QPOS_ARTIFACT_SCHEMA",
    "CONTINUOUS_GOAL_QPOS_MEMBER_SCHEMA",
    "ContinuousGoalQposArtifactError",
    "load_continuous_goal_qpos_predictor",
    "save_continuous_goal_qpos_predictor",
]
