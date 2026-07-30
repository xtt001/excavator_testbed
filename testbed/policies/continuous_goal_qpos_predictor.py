"""Five-member continuous-goal qpos sweep predictor.

The v1 model is intentionally small and fixed: two 64-unit hidden layers,
five source-grouped members, Huber loss, and no nearest-trajectory fallback.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as torch_functional

from testbed.data.continuous_goal_qpos_paths import (
    BSPLINE_CONTROL_POINT_COUNT,
    PATH_PROGRESS,
    QPOS_DIM,
    ContinuousGoalQposPathContractError,
    ContinuousGoalWorktoolSweepInputV2,
    LegacyContinuousGoalWorktoolSweepInputV1,
    evaluate_qpos_bspline,
    fit_qpos_bspline,
    predictor_feature_map,
    qpos_path_sha256,
    read_continuous_goal_worktool_sweep_input,
    resample_qpos_path_by_joint_arc_length,
    vectorize_sweep_input,
)
from testbed.eval.continuous_goal_qpos_calibration import (
    CONFORMAL_COVERAGE_LEVEL,
    CONFORMAL_HELDOUT_SOURCE_IDS,
    SOURCE_GROUPED_FOLD_COUNT,
    CalibrationContractError,
    ConformalQposCalibration,
    FeatureNormalization,
    LosoOODCalibration,
    SourceGroupedFold,
    build_source_grouped_folds,
    combined_calibration_sha256,
    fit_conformal_qpos_calibration,
    fit_loso_ood_calibration,
    predictor_normalization_lineage_sha256,
    validate_qpos_predictor_semantics,
)

CONTINUOUS_GOAL_QPOS_PREDICTOR_CONFIG_SCHEMA = (
    "continuous_goal_qpos_predictor_config_v1"
)
CONTINUOUS_GOAL_QPOS_PREDICTION_SCHEMA = "continuous_goal_qpos_sweep_prediction_v1"
CONTINUOUS_GOAL_QPOS_PREDICTOR_PROFILE = "continuous_goal_qpos_bspline_ensemble_v1"
CONTINUOUS_GOAL_QPOS_PREDICTOR_VERSION = "1"
ENSEMBLE_SEEDS = (0, 1, 2, 3, 4)
HIDDEN_DIMS = (64, 64)
FREE_CONTROL_POINT_COUNT = BSPLINE_CONTROL_POINT_COUNT - 1
MODEL_OUTPUT_DIM = FREE_CONTROL_POINT_COUNT * QPOS_DIM
QPOS_ORDER = ("swing", "boom", "stick", "bucket")
_CODE_LINEAGE_RELATIVE_PATHS = (
    "testbed/data/continuous_goal_qpos_paths.py",
    "testbed/data/terrain_signature.py",
    "testbed/eval/continuous_goal_qpos_calibration.py",
    "testbed/planner/primitive/coverage/continuous_goal.py",
    "testbed/policies/continuous_goal_qpos_artifact.py",
    "testbed/policies/continuous_goal_qpos_predictor.py",
)


class ContinuousGoalQposPredictorError(ValueError):
    """Raised when predictor training data violates the fixed contract."""


@dataclass(frozen=True)
class ContinuousGoalQposPredictorConfig:
    """Fixed architecture with reducible optimization time for tests."""

    schema: str = CONTINUOUS_GOAL_QPOS_PREDICTOR_CONFIG_SCHEMA
    hidden_dims: tuple[int, int] = HIDDEN_DIMS
    seeds: tuple[int, ...] = ENSEMBLE_SEEDS
    grouped_cv_folds: int = SOURCE_GROUPED_FOLD_COUNT
    loss: str = "huber"
    huber_delta: float = 1.0
    epochs: int = 100
    batch_size: int = 64
    learning_rate: float = 1.0e-3
    weight_decay: float = 1.0e-5
    device: str = "cpu"

    def __post_init__(self) -> None:
        if self.schema != CONTINUOUS_GOAL_QPOS_PREDICTOR_CONFIG_SCHEMA:
            raise ContinuousGoalQposPredictorError(
                "continuous qpos predictor config schema mismatch"
            )
        if tuple(self.hidden_dims) != HIDDEN_DIMS or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in self.hidden_dims
        ):
            raise ContinuousGoalQposPredictorError(
                "continuous qpos predictor v1 hidden layers are fixed to 64x64"
            )
        if tuple(self.seeds) != ENSEMBLE_SEEDS or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in self.seeds
        ):
            raise ContinuousGoalQposPredictorError(
                "continuous qpos predictor v1 seeds are fixed to 0 through 4"
            )
        if (
            isinstance(self.grouped_cv_folds, bool)
            or not isinstance(self.grouped_cv_folds, int)
            or self.grouped_cv_folds != SOURCE_GROUPED_FOLD_COUNT
        ):
            raise ContinuousGoalQposPredictorError(
                "continuous qpos predictor v1 uses five source-grouped folds"
            )
        if self.loss != "huber" or not _valid_finite_number(
            self.huber_delta, positive=True
        ):
            raise ContinuousGoalQposPredictorError(
                "continuous qpos predictor v1 uses positive-delta Huber loss"
            )
        if not _positive_int(self.epochs) or not _positive_int(self.batch_size):
            raise ContinuousGoalQposPredictorError(
                "epochs and batch_size must be positive"
            )
        if not _valid_finite_number(
            self.learning_rate,
            positive=True,
        ) or not _valid_finite_number(
            self.weight_decay,
            positive=False,
        ):
            raise ContinuousGoalQposPredictorError(
                "learning_rate must be positive and weight_decay non-negative"
            )
        if self.device not in {"cpu", "cuda"}:
            raise ContinuousGoalQposPredictorError(
                "predictor device must be cpu or cuda"
            )


@dataclass(frozen=True)
class ContinuousGoalQposTrainingExample:
    """One expert path and its source identity used only for grouped splitting."""

    source_id: int
    sweep_input: ContinuousGoalWorktoolSweepInputV2
    normalized_qpos_path: np.ndarray
    spline_control_points: np.ndarray

    @classmethod
    def create(
        cls,
        *,
        source_id: int,
        sweep_input: Any,
        expert_qpos_path: Any,
    ) -> ContinuousGoalQposTrainingExample:
        parsed_source = _source_id(source_id)
        request = read_continuous_goal_worktool_sweep_input(
            sweep_input,
            allow_legacy_v1=False,
        )
        if not isinstance(request, ContinuousGoalWorktoolSweepInputV2):
            raise ContinuousGoalQposPredictorError(
                "training examples require continuous goal sweep input v2"
            )
        normalized_path = resample_qpos_path_by_joint_arc_length(expert_qpos_path)
        spline = fit_qpos_bspline(
            normalized_path,
            handoff_qpos=request.handoff_qpos,
        )
        normalized_path.setflags(write=False)
        return cls(
            source_id=parsed_source,
            sweep_input=request,
            normalized_qpos_path=normalized_path,
            spline_control_points=spline.control_points,
        )


class _QposControlMLP(nn.Module):
    def __init__(self, *, input_dim: int) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, HIDDEN_DIMS[0]),
            nn.ReLU(),
            nn.Linear(HIDDEN_DIMS[0], HIDDEN_DIMS[1]),
            nn.ReLU(),
            nn.Linear(HIDDEN_DIMS[1], MODEL_OUTPUT_DIM),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.network(features)


@dataclass(frozen=True)
class ContinuousGoalQposEnsembleMember:
    """One seed/fold member and its source ownership."""

    seed: int
    train_source_ids: tuple[int, ...]
    validation_source_ids: tuple[int, ...]
    normalization: FeatureNormalization
    model: nn.Module
    final_training_loss: float


@dataclass(frozen=True)
class ContinuousGoalQposPrediction:
    """Successful reference/bounds or a fail-closed blocker set."""

    status: str
    blockers: tuple[str, ...]
    support_status: str
    ood_score: float | None
    path_progress: np.ndarray | None
    qpos_path: np.ndarray | None
    qpos_abs_error_bound: np.ndarray | None
    coverage_level: float | None
    handoff_qpos: tuple[float, ...] = ()
    handoff_qvel: tuple[float, ...] = ()
    normalization_lineage_sha256: str = ""
    checkpoint_lineage_sha256: str = ""
    calibration_lineage_sha256: str = ""
    goal_lineage_sha256: str = ""
    predictor_code_lineage_sha256: str = ""
    path_lineage_sha256: str = ""
    input_lineage_sha256: str = ""
    schema: str = CONTINUOUS_GOAL_QPOS_PREDICTION_SCHEMA

    @property
    def inference_allowed(self) -> bool:
        return bool(
            self.status == "passed"
            and not self.blockers
            and self.support_status == "supported"
            and self.qpos_path is not None
            and self.qpos_abs_error_bound is not None
        )

    def as_dict(self) -> dict[str, Any]:
        qpos_path = None if self.qpos_path is None else self.qpos_path.tolist()
        bounds = (
            None
            if self.qpos_abs_error_bound is None
            else self.qpos_abs_error_bound.tolist()
        )
        progress = None if self.path_progress is None else self.path_progress.tolist()
        return {
            "schema": self.schema,
            "status": self.status,
            "blockers": list(self.blockers),
            "inference_allowed": self.inference_allowed,
            "support_status": self.support_status,
            "ood_score": self.ood_score,
            "path_progress": progress,
            "qpos_path": qpos_path,
            "planned_qpos_path": qpos_path,
            "qpos_abs_error_bound": bounds,
            "coverage_level": self.coverage_level,
            "goal_id": self.goal_lineage_sha256,
            "goal_sha256": self.goal_lineage_sha256,
            "handoff_qpos": list(self.handoff_qpos),
            "handoff_qvel": list(self.handoff_qvel),
            "qpos_order": list(QPOS_ORDER),
            "path_sha256": self.path_lineage_sha256,
            "input_sha256": self.input_lineage_sha256,
            "predictor": {
                "provider": "continuous_goal_qpos_sweep_predictor",
                "profile": CONTINUOUS_GOAL_QPOS_PREDICTOR_PROFILE,
                "version": CONTINUOUS_GOAL_QPOS_PREDICTOR_VERSION,
                "code_sha256": self.predictor_code_lineage_sha256,
            },
            "lineage": {
                "normalization_sha256": (self.normalization_lineage_sha256),
                "checkpoint_sha256": self.checkpoint_lineage_sha256,
                "calibration_sha256": self.calibration_lineage_sha256,
                "goal_sha256": self.goal_lineage_sha256,
                "predictor_code_sha256": (self.predictor_code_lineage_sha256),
                "path_sha256": self.path_lineage_sha256,
                "input_sha256": self.input_lineage_sha256,
            },
        }


@dataclass(frozen=True)
class ContinuousGoalQposSweepPredictor:
    """Trained source-grouped ensemble with fail-closed calibration."""

    config: ContinuousGoalQposPredictorConfig
    members: tuple[ContinuousGoalQposEnsembleMember, ...]
    source_grouped_folds: tuple[SourceGroupedFold, ...]
    feature_names: tuple[str, ...]
    normalization: FeatureNormalization
    ood_calibration: LosoOODCalibration
    conformal_calibration: ConformalQposCalibration | None
    predictor_code_sha256: str
    normalization_lineage_sha256: str
    checkpoint_lineage_sha256: str
    calibration_lineage_sha256: str

    def __post_init__(self) -> None:
        try:
            validate_qpos_predictor_semantics(
                members=self.members,
                folds=self.source_grouped_folds,
                feature_names=self.feature_names,
                ood_normalization=self.normalization,
                ood=self.ood_calibration,
                conformal=self.conformal_calibration,
            )
        except CalibrationContractError as exc:
            raise ContinuousGoalQposPredictorError(
                f"predictor fixed semantics invalid: {exc}"
            ) from exc
        if self._lineage_blockers(request=None, expected_lineage=None):
            raise ContinuousGoalQposPredictorError(
                "predictor canonical lineage is invalid"
            )

    def predict(
        self,
        sweep_input: Any,
        *,
        expected_lineage: Mapping[str, str] | None = None,
    ) -> ContinuousGoalQposPrediction:
        """Predict only for valid v2, supported, lineage-matched inputs."""

        try:
            request = read_continuous_goal_worktool_sweep_input(sweep_input)
        except (ContinuousGoalQposPathContractError, TypeError, ValueError):
            return self._blocked(
                blockers=("input_invalid",),
                support_status="invalid",
            )
        if isinstance(request, LegacyContinuousGoalWorktoolSweepInputV1):
            return self._blocked(
                blockers=("input_contract_v2_required",),
                support_status="invalid",
            )
        lineage_blockers = self._lineage_blockers(
            request=request,
            expected_lineage=expected_lineage,
        )
        if lineage_blockers:
            return self._blocked(
                blockers=lineage_blockers,
                support_status="invalid",
                request=request,
            )
        if self.conformal_calibration is None:
            return self._blocked(
                blockers=("calibration_missing",),
                support_status="invalid",
                request=request,
            )
        try:
            feature = vectorize_sweep_input(
                request,
                feature_names=self.feature_names,
            )
            ood_score = self.ood_calibration.score(
                feature,
                normalization=self.normalization,
            )
        except (ContinuousGoalQposPathContractError, ValueError):
            return self._blocked(
                blockers=("nonfinite_or_invalid_input",),
                support_status="invalid",
                request=request,
            )
        if not math.isfinite(ood_score):
            return self._blocked(
                blockers=("nonfinite_ood_score",),
                support_status="invalid",
                request=request,
            )
        if ood_score > self.ood_calibration.threshold:
            return self._blocked(
                blockers=("ood",),
                support_status="ood",
                request=request,
                ood_score=ood_score,
            )
        try:
            controls = self._predict_control_points(feature)
            relative_path = evaluate_qpos_bspline(controls)
            qpos_path = (
                relative_path
                + np.asarray(
                    request.handoff_qpos,
                    dtype=np.float64,
                )[None, :]
            )
            qpos_path[0] = np.asarray(
                request.handoff_qpos,
                dtype=np.float64,
            )
            bounds = np.asarray(
                self.conformal_calibration.absolute_error_bound,
                dtype=np.float64,
            ).copy()
            if (
                qpos_path.shape != (64, QPOS_DIM)
                or bounds.shape != (64, QPOS_DIM)
                or not np.all(np.isfinite(qpos_path))
                or not np.all(np.isfinite(bounds))
                or np.any(bounds < 0.0)
            ):
                raise ContinuousGoalQposPredictorError("non-finite predictor output")
            start_error = float(
                np.max(
                    np.abs(
                        qpos_path[0]
                        - np.asarray(request.handoff_qpos, dtype=np.float64)
                    )
                )
            )
            if start_error > 1.0e-6:
                raise ContinuousGoalQposPredictorError(
                    "predicted path does not start at actual handoff"
                )
            path_lineage = qpos_path_sha256(qpos_path)
        except Exception:
            return self._blocked(
                blockers=("nonfinite_or_invalid_output",),
                support_status="invalid",
                request=request,
                ood_score=ood_score,
            )
        if _expected_path_lineage_mismatch(
            expected_lineage,
            path_lineage=path_lineage,
        ):
            return self._blocked(
                blockers=("lineage_mismatch",),
                support_status="invalid",
                request=request,
                ood_score=ood_score,
            )
        qpos_path.setflags(write=False)
        bounds.setflags(write=False)
        return ContinuousGoalQposPrediction(
            status="passed",
            blockers=(),
            support_status="supported",
            ood_score=ood_score,
            path_progress=PATH_PROGRESS,
            qpos_path=qpos_path,
            qpos_abs_error_bound=bounds,
            coverage_level=CONFORMAL_COVERAGE_LEVEL,
            handoff_qpos=request.handoff_qpos,
            handoff_qvel=request.handoff_qvel,
            normalization_lineage_sha256=(self.normalization_lineage_sha256),
            checkpoint_lineage_sha256=self.checkpoint_lineage_sha256,
            calibration_lineage_sha256=self.calibration_lineage_sha256,
            goal_lineage_sha256=request.goal_sha256,
            predictor_code_lineage_sha256=self.predictor_code_sha256,
            path_lineage_sha256=path_lineage,
            input_lineage_sha256=request.input_sha256,
        )

    def _predict_control_points(self, feature: np.ndarray) -> np.ndarray:
        return _predict_control_points_for_members(
            feature=feature,
            members=self.members,
            device=torch.device(self.config.device),
        )

    def _lineage_blockers(
        self,
        *,
        request: ContinuousGoalWorktoolSweepInputV2 | None,
        expected_lineage: Mapping[str, str] | None,
    ) -> tuple[str, ...]:
        try:
            validate_qpos_predictor_semantics(
                members=self.members,
                folds=self.source_grouped_folds,
                feature_names=self.feature_names,
                ood_normalization=self.normalization,
                ood=self.ood_calibration,
                conformal=self.conformal_calibration,
            )
            if (
                predictor_normalization_lineage_sha256(
                    ood_normalization=self.normalization,
                    members=self.members,
                )
                != self.normalization_lineage_sha256
            ):
                return ("lineage_mismatch",)
            if (
                self.predictor_code_sha256
                != canonical_continuous_goal_qpos_code_sha256()
                or checkpoint_lineage_sha256(
                    self.members,
                    self.feature_names,
                )
                != self.checkpoint_lineage_sha256
            ):
                return ("lineage_mismatch",)
            computed_calibration = combined_calibration_sha256(
                ood=self.ood_calibration,
                conformal=self.conformal_calibration,
            )
            if computed_calibration != self.calibration_lineage_sha256:
                return ("lineage_mismatch",)
        except CalibrationContractError:
            if self.conformal_calibration is None:
                return ("calibration_missing",)
            return ("contract_invalid",)
        except Exception:
            return ("lineage_mismatch",)
        if expected_lineage is None:
            return ()
        if not isinstance(expected_lineage, Mapping):
            return ("lineage_mismatch",)
        aliases = {
            "normalization_sha256": self.normalization_lineage_sha256,
            "normalization_lineage_sha256": (self.normalization_lineage_sha256),
            "checkpoint_sha256": self.checkpoint_lineage_sha256,
            "checkpoint_lineage_sha256": self.checkpoint_lineage_sha256,
            "calibration_sha256": self.calibration_lineage_sha256,
            "calibration_lineage_sha256": self.calibration_lineage_sha256,
            "goal_sha256": request.goal_sha256,
            "goal_lineage_sha256": request.goal_sha256,
            "code_sha256": self.predictor_code_sha256,
            "predictor_code_sha256": self.predictor_code_sha256,
            "input_sha256": request.input_sha256,
            "input_lineage_sha256": request.input_sha256,
        }
        for key, supplied in expected_lineage.items():
            if str(key) in {"path_sha256", "path_lineage_sha256"}:
                continue
            expected = aliases.get(str(key))
            if (
                expected is None
                or not _is_sha256(str(supplied))
                or str(supplied) != expected
            ):
                return ("lineage_mismatch",)
        return ()

    def _blocked(
        self,
        *,
        blockers: Sequence[str],
        support_status: str,
        request: ContinuousGoalWorktoolSweepInputV2 | None = None,
        ood_score: float | None = None,
    ) -> ContinuousGoalQposPrediction:
        return ContinuousGoalQposPrediction(
            status="blocked",
            blockers=tuple(str(value) for value in blockers),
            support_status=support_status,
            ood_score=ood_score,
            path_progress=PATH_PROGRESS,
            qpos_path=None,
            qpos_abs_error_bound=None,
            coverage_level=(
                None
                if self.conformal_calibration is None
                else self.conformal_calibration.coverage_level
            ),
            handoff_qpos=() if request is None else request.handoff_qpos,
            handoff_qvel=() if request is None else request.handoff_qvel,
            normalization_lineage_sha256=(self.normalization_lineage_sha256),
            checkpoint_lineage_sha256=self.checkpoint_lineage_sha256,
            calibration_lineage_sha256=self.calibration_lineage_sha256,
            goal_lineage_sha256=("" if request is None else request.goal_sha256),
            predictor_code_lineage_sha256=self.predictor_code_sha256,
            path_lineage_sha256="",
            input_lineage_sha256=("" if request is None else request.input_sha256),
        )


def train_continuous_goal_qpos_predictor(
    *,
    examples: Sequence[ContinuousGoalQposTrainingExample],
    predictor_code_sha256: str | None = None,
    config: ContinuousGoalQposPredictorConfig | None = None,
) -> ContinuousGoalQposSweepPredictor:
    """Train five source-grouped members and calibrate on sources 33/34."""

    config = config or ContinuousGoalQposPredictorConfig()
    if not examples:
        raise ContinuousGoalQposPredictorError(
            "continuous qpos predictor examples must not be empty"
        )
    canonical_code_sha = canonical_continuous_goal_qpos_code_sha256()
    if (
        predictor_code_sha256 is not None
        and predictor_code_sha256 != canonical_code_sha
    ):
        raise ContinuousGoalQposPredictorError(
            "predictor_code_sha256 must match canonical code lineage"
        )
    if config.device == "cuda" and not torch.cuda.is_available():
        raise ContinuousGoalQposPredictorError(
            "CUDA predictor training requested but CUDA is unavailable"
        )
    rows = tuple(examples)
    if any(not isinstance(row, ContinuousGoalQposTrainingExample) for row in rows):
        raise ContinuousGoalQposPredictorError(
            "examples must be ContinuousGoalQposTrainingExample objects"
        )
    source_ids = np.asarray([row.source_id for row in rows], dtype=np.int64)
    folds = build_source_grouped_folds(source_ids.tolist())
    training_mask = ~np.isin(source_ids, CONFORMAL_HELDOUT_SOURCE_IDS)
    calibration_mask = np.isin(source_ids, CONFORMAL_HELDOUT_SOURCE_IDS)
    if not np.any(training_mask) or not np.any(calibration_mask):
        raise ContinuousGoalQposPredictorError(
            "training and sources 33/34 calibration rows are required"
        )
    training_feature_maps = [
        predictor_feature_map(rows[index].sweep_input)
        for index in np.flatnonzero(training_mask)
    ]
    feature_names = tuple(
        sorted(
            set().union(*(set(feature_map) for feature_map in training_feature_maps))
        )
    )
    feature_matrix = np.vstack(
        [
            vectorize_sweep_input(
                row.sweep_input,
                feature_names=feature_names,
            )
            for row in rows
        ]
    )
    targets = np.vstack([row.spline_control_points[1:].reshape(-1) for row in rows])
    normalization = FeatureNormalization.fit(
        feature_matrix[training_mask],
        feature_names=feature_names,
    )
    ood_calibration = fit_loso_ood_calibration(
        features=feature_matrix[training_mask],
        source_ids=source_ids[training_mask].tolist(),
        normalization=normalization,
    )
    device = torch.device(config.device)
    members: list[ContinuousGoalQposEnsembleMember] = []
    for seed, fold in zip(config.seeds, folds, strict=True):
        train_mask = np.isin(source_ids, fold.train_source_ids)
        member_normalization = FeatureNormalization.fit(
            feature_matrix[train_mask],
            feature_names=feature_names,
        )
        model = build_continuous_goal_qpos_mlp(input_dim=feature_matrix.shape[1]).to(
            device
        )
        _seed_all(int(seed))
        model.apply(_reset_module_parameters)
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=float(config.learning_rate),
            weight_decay=float(config.weight_decay),
        )
        final_loss = _train_member(
            model=model,
            optimizer=optimizer,
            features=member_normalization.transform(feature_matrix[train_mask]),
            targets=targets[train_mask],
            config=config,
            seed=int(seed),
            device=device,
        )
        model.eval()
        members.append(
            ContinuousGoalQposEnsembleMember(
                seed=int(seed),
                train_source_ids=fold.train_source_ids,
                validation_source_ids=fold.validation_source_ids,
                normalization=member_normalization,
                model=model,
                final_training_loss=final_loss,
            )
        )
    member_tuple = tuple(members)
    checkpoint_lineage = checkpoint_lineage_sha256(
        member_tuple,
        feature_names,
    )
    calibration_residuals: list[np.ndarray] = []
    calibration_sources: list[int] = []
    for index in np.flatnonzero(calibration_mask):
        controls = _predict_control_points_for_members(
            feature=feature_matrix[index],
            members=member_tuple,
            device=device,
        )
        predicted_path = (
            evaluate_qpos_bspline(controls)
            + np.asarray(
                rows[index].sweep_input.handoff_qpos,
                dtype=np.float64,
            )[None, :]
        )
        predicted_path[0] = rows[index].sweep_input.handoff_qpos
        calibration_residuals.append(
            np.abs(rows[index].normalized_qpos_path - predicted_path)
        )
        calibration_sources.append(int(source_ids[index]))
    conformal = fit_conformal_qpos_calibration(
        absolute_residuals=np.stack(calibration_residuals),
        source_ids=calibration_sources,
    )
    calibration_lineage = combined_calibration_sha256(
        ood=ood_calibration,
        conformal=conformal,
    )
    return ContinuousGoalQposSweepPredictor(
        config=config,
        members=member_tuple,
        source_grouped_folds=folds,
        feature_names=feature_names,
        normalization=normalization,
        ood_calibration=ood_calibration,
        conformal_calibration=conformal,
        predictor_code_sha256=canonical_code_sha,
        normalization_lineage_sha256=(
            predictor_normalization_lineage_sha256(
                ood_normalization=normalization,
                members=member_tuple,
            )
        ),
        checkpoint_lineage_sha256=checkpoint_lineage,
        calibration_lineage_sha256=calibration_lineage,
    )


def _predict_control_points_for_members(
    *,
    feature: np.ndarray,
    members: Sequence[ContinuousGoalQposEnsembleMember],
    device: torch.device,
) -> np.ndarray:
    predictions: list[np.ndarray] = []
    for member in members:
        normalized = member.normalization.transform(feature)
        tensor = torch.as_tensor(
            normalized[None, :],
            dtype=torch.float32,
            device=device,
        )
        member.model.eval()
        with torch.no_grad():
            raw = member.model(tensor).detach().cpu().numpy()
        if raw.shape != (1, MODEL_OUTPUT_DIM):
            raise ContinuousGoalQposPredictorError(
                "ensemble member output dimension mismatch"
            )
        predictions.append(raw[0].astype(np.float64))
    mean_prediction = np.mean(np.stack(predictions), axis=0)
    if not np.all(np.isfinite(mean_prediction)):
        raise ContinuousGoalQposPredictorError(
            "ensemble output contains non-finite values"
        )
    free_controls = mean_prediction.reshape(
        FREE_CONTROL_POINT_COUNT,
        QPOS_DIM,
    )
    controls = np.vstack((np.zeros((1, QPOS_DIM)), free_controls))
    controls[0] = 0.0
    return controls


def _train_member(
    *,
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    features: np.ndarray,
    targets: np.ndarray,
    config: ContinuousGoalQposPredictorConfig,
    seed: int,
    device: torch.device,
) -> float:
    feature_tensor = torch.as_tensor(
        features,
        dtype=torch.float32,
        device=device,
    )
    target_tensor = torch.as_tensor(
        targets,
        dtype=torch.float32,
        device=device,
    )
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    final_loss = math.nan
    model.train()
    for _ in range(int(config.epochs)):
        order = torch.randperm(
            feature_tensor.shape[0],
            generator=generator,
        )
        for start in range(0, order.numel(), int(config.batch_size)):
            indices = order[start : start + int(config.batch_size)].to(device)
            prediction = model(feature_tensor[indices])
            loss = torch_functional.huber_loss(
                prediction,
                target_tensor[indices],
                delta=float(config.huber_delta),
            )
            if not bool(torch.isfinite(loss)):
                raise ContinuousGoalQposPredictorError(
                    "predictor training produced non-finite Huber loss"
                )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            final_loss = float(loss.detach().cpu())
    if not math.isfinite(final_loss):
        raise ContinuousGoalQposPredictorError(
            "predictor training did not produce a finite loss"
        )
    return final_loss


def _seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _reset_module_parameters(module: nn.Module) -> None:
    reset = getattr(module, "reset_parameters", None)
    if callable(reset):
        reset()


def canonical_continuous_goal_qpos_code_sha256() -> str:
    """Hash the fixed predictor contract and implementation source set."""

    repository_root = Path(__file__).resolve().parents[2]
    source_lineage: list[dict[str, str]] = []
    for relative_path in _CODE_LINEAGE_RELATIVE_PATHS:
        path = repository_root / relative_path
        if not path.is_file():
            raise ContinuousGoalQposPredictorError(
                f"predictor code lineage source missing: {relative_path}"
            )
        source_lineage.append(
            {
                "path": relative_path,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return hashlib.sha256(
        json.dumps(
            source_lineage,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def build_continuous_goal_qpos_mlp(*, input_dim: int) -> nn.Module:
    """Construct the locked v1 architecture for training or strict loading."""

    if not _positive_int(input_dim):
        raise ContinuousGoalQposPredictorError(
            "continuous qpos predictor input_dim must be positive"
        )
    return _QposControlMLP(input_dim=input_dim)


def checkpoint_lineage_sha256(
    members: Sequence[ContinuousGoalQposEnsembleMember],
    feature_names: Sequence[str],
) -> str:
    digest = hashlib.sha256()
    metadata = {
        "profile": CONTINUOUS_GOAL_QPOS_PREDICTOR_PROFILE,
        "version": CONTINUOUS_GOAL_QPOS_PREDICTOR_VERSION,
        "hidden_dims": list(HIDDEN_DIMS),
        "seeds": [member.seed for member in members],
        "feature_names": list(feature_names),
        "output": "11_free_controls_x_4_joints",
    }
    digest.update(
        json.dumps(
            metadata,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    for member in members:
        digest.update(str(member.seed).encode("ascii"))
        digest.update(
            json.dumps(
                {
                    "train_source_ids": list(member.train_source_ids),
                    "validation_source_ids": list(member.validation_source_ids),
                    "normalization_sha256": (member.normalization.lineage_sha256),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        for name, tensor in sorted(member.model.state_dict().items()):
            array = tensor.detach().cpu().contiguous().numpy().astype("<f4", copy=False)
            digest.update(name.encode("utf-8"))
            digest.update(str(array.shape).encode("ascii"))
            digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _expected_path_lineage_mismatch(
    expected_lineage: Mapping[str, str] | None,
    *,
    path_lineage: str,
) -> bool:
    if expected_lineage is None:
        return False
    if not isinstance(expected_lineage, Mapping):
        return True
    supplied_values = [
        str(expected_lineage[key])
        for key in ("path_sha256", "path_lineage_sha256")
        if key in expected_lineage
    ]
    return any(
        not _is_sha256(value) or value != path_lineage for value in supplied_values
    )


def _source_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ContinuousGoalQposPredictorError(
            "source_id must be a non-negative integer"
        )
    parsed = int(value)
    if parsed < 0 or parsed != value:
        raise ContinuousGoalQposPredictorError(
            "source_id must be a non-negative integer"
        )
    return parsed


def _positive_int(value: Any) -> bool:
    return bool(not isinstance(value, bool) and isinstance(value, int) and value > 0)


def _valid_finite_number(value: Any, *, positive: bool) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    return bool(math.isfinite(number) and (number > 0.0 if positive else number >= 0.0))


def _is_sha256(value: str) -> bool:
    return bool(
        len(value) == 64 and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "CONTINUOUS_GOAL_QPOS_PREDICTION_SCHEMA",
    "CONTINUOUS_GOAL_QPOS_PREDICTOR_CONFIG_SCHEMA",
    "CONTINUOUS_GOAL_QPOS_PREDICTOR_PROFILE",
    "CONTINUOUS_GOAL_QPOS_PREDICTOR_VERSION",
    "ENSEMBLE_SEEDS",
    "HIDDEN_DIMS",
    "ContinuousGoalQposEnsembleMember",
    "ContinuousGoalQposPrediction",
    "ContinuousGoalQposPredictorConfig",
    "ContinuousGoalQposPredictorError",
    "ContinuousGoalQposSweepPredictor",
    "ContinuousGoalQposTrainingExample",
    "build_continuous_goal_qpos_mlp",
    "canonical_continuous_goal_qpos_code_sha256",
    "checkpoint_lineage_sha256",
    "predictor_normalization_lineage_sha256",
    "train_continuous_goal_qpos_predictor",
]
