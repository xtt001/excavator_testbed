"""Small deterministic PyTorch ensemble for terrain-effect calibration."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.eval.executed_cut_effect_samples import (
    EVIDENCE_TIER,
    EffectInputContract,
    vectorize_effect_input,
)
from testbed.eval.planned_cut_calibration import (
    assess_capability_label_support,
    assign_episode_grouped_folds,
)

ENSEMBLE_CONFIG_SCHEMA = "terrain_effect_ensemble_config_v1"
ENSEMBLE_ARTIFACT_SCHEMA = "terrain_effect_ensemble_artifact_v1"
ENSEMBLE_MEMBER_SCHEMA = "terrain_effect_ensemble_member_v1"
ENSEMBLE_PREDICTION_SCHEMA = "terrain_effect_ensemble_prediction_v1"
DEFAULT_GROUPED_FOLD_COUNT = 6
REGRESSION_TARGET_NAMES = tuple(
    [f"signed_depth_delta_m[{index}]" for index in range(6)] + ["payload_gain_kg"]
)


@dataclass(frozen=True)
class TerrainEffectEnsembleConfig:
    """Versioned production defaults; seeds/epochs can shrink for smoke tests."""

    schema: str = ENSEMBLE_CONFIG_SCHEMA
    hidden_dims: tuple[int, int] = (64, 64)
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4)
    grouped_cv_folds: int = DEFAULT_GROUPED_FOLD_COUNT
    epochs: int = 100
    batch_size: int = 64
    learning_rate: float = 1.0e-3
    weight_decay: float = 1.0e-5
    capability_loss_weight: float = 1.0
    regression_loss: str = "huber"
    huber_delta: float = 1.0
    device: str = "cpu"

    def __post_init__(self) -> None:
        if self.schema != ENSEMBLE_CONFIG_SCHEMA:
            raise ValueError(f"schema must be {ENSEMBLE_CONFIG_SCHEMA!r}.")
        if tuple(self.hidden_dims) != (64, 64):
            raise ValueError("The v1 effect ensemble architecture is fixed at 2x64.")
        if not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must contain at least one unique integer.")
        if any(isinstance(seed, bool) or int(seed) != seed for seed in self.seeds):
            raise ValueError("Each seed must be an integer.")
        if self.grouped_cv_folds != DEFAULT_GROUPED_FOLD_COUNT:
            raise ValueError(
                "The production v1 grouped CV contract is fixed at 6 folds."
            )
        if self.epochs <= 0 or self.batch_size <= 0:
            raise ValueError("epochs and batch_size must be positive.")
        if self.learning_rate <= 0.0 or self.weight_decay < 0.0:
            raise ValueError(
                "learning_rate must be positive and weight_decay non-negative."
            )
        if self.capability_loss_weight < 0.0:
            raise ValueError("capability_loss_weight must be non-negative.")
        if self.regression_loss != "huber":
            raise ValueError("The production v1 regression loss is fixed to Huber.")
        if self.huber_delta <= 0.0:
            raise ValueError("huber_delta must be positive.")
        if self.device not in {"cpu", "cuda"}:
            raise ValueError("device must be 'cpu' or 'cuda'.")


def train_terrain_effect_ensemble(
    *,
    train_records: Sequence[Mapping[str, Any]],
    eval_records: Sequence[Mapping[str, Any]],
    output_dir: str | Path,
    input_contract: EffectInputContract,
    config: TerrainEffectEnsembleConfig | None = None,
    split_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Train and evaluate a no-overwrite ensemble on an explicit episode split."""

    import torch

    config = config or TerrainEffectEnsembleConfig()
    if input_contract not in {"executed_cut", "planned_cut"}:
        raise ValueError(f"Unsupported input_contract: {input_contract!r}")
    if not train_records:
        raise ValueError("train_records must not be empty.")
    if not eval_records:
        raise ValueError("eval_records must not be empty.")
    if config.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available.")
    train_episode_ids = _episode_ids(train_records, "train_records")
    eval_episode_ids = _episode_ids(eval_records, "eval_records")
    overlap = sorted(train_episode_ids & eval_episode_ids)
    if overlap:
        raise ValueError(f"Episode-group split leakage detected: {overlap}")

    train_x, train_feature_names = _feature_matrix(
        train_records,
        input_contract=input_contract,
    )
    eval_x, eval_feature_names = _feature_matrix(
        eval_records,
        input_contract=input_contract,
    )
    if eval_feature_names != train_feature_names:
        raise ValueError("Train/eval feature schemas differ.")
    train_y = _regression_matrix(train_records)
    eval_y = _regression_matrix(eval_records)
    capability_names, excluded_capability_labels = _capability_training_contract(
        train_records,
        eval_records,
    )
    train_capability = _capability_matrix(train_records, capability_names)
    eval_capability = _capability_matrix(eval_records, capability_names)

    x_mean, x_scale = _normalization(train_x)
    y_mean, y_scale = _normalization(train_y)
    train_x_norm = (train_x - x_mean) / x_scale
    eval_x_norm = (eval_x - x_mean) / x_scale
    train_y_norm = (train_y - y_mean) / y_scale

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=False)
    device = torch.device(config.device)
    train_x_tensor = torch.as_tensor(train_x_norm, dtype=torch.float32, device=device)
    train_y_tensor = torch.as_tensor(train_y_norm, dtype=torch.float32, device=device)
    train_cap_tensor = torch.as_tensor(
        train_capability,
        dtype=torch.float32,
        device=device,
    )
    eval_x_tensor = torch.as_tensor(eval_x_norm, dtype=torch.float32, device=device)

    members: list[dict[str, Any]] = []
    regression_predictions: list[np.ndarray] = []
    capability_predictions: list[np.ndarray] = []
    for seed in config.seeds:
        _set_seed(torch, int(seed))
        model = _build_model(
            torch,
            input_dim=train_x.shape[1],
            regression_dim=train_y.shape[1],
            capability_dim=len(capability_names),
            hidden_dims=config.hidden_dims,
        ).to(device)
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )
        final_loss = _train_member(
            torch=torch,
            model=model,
            optimizer=optimizer,
            features=train_x_tensor,
            regression_targets=train_y_tensor,
            capability_targets=train_cap_tensor,
            regression_dim=train_y.shape[1],
            capability_dim=len(capability_names),
            config=config,
            seed=int(seed),
        )
        model.eval()
        with torch.no_grad():
            output = model(eval_x_tensor).cpu().numpy().astype(np.float64)
        prediction_y = output[:, : train_y.shape[1]] * y_scale + y_mean
        regression_predictions.append(prediction_y)
        if capability_names:
            logits = output[:, train_y.shape[1] :]
            capability_predictions.append(1.0 / (1.0 + np.exp(-logits)))

        checkpoint_path = destination / f"member_seed_{int(seed)}.pt"
        torch.save(
            {
                "schema": ENSEMBLE_MEMBER_SCHEMA,
                "input_contract": input_contract,
                "seed": int(seed),
                "config": _json_config(config),
                "feature_names": train_feature_names,
                "regression_target_names": list(REGRESSION_TARGET_NAMES),
                "capability_target_names": capability_names,
                "normalization": {
                    "feature_mean": x_mean.tolist(),
                    "feature_scale": x_scale.tolist(),
                    "regression_mean": y_mean.tolist(),
                    "regression_scale": y_scale.tolist(),
                },
                "state_dict": model.state_dict(),
            },
            checkpoint_path,
        )
        members.append(
            {
                "seed": int(seed),
                "checkpoint_path": str(checkpoint_path.resolve()),
                "checkpoint_file": checkpoint_path.name,
                "final_training_loss": final_loss,
            }
        )

    ensemble_y = np.mean(np.stack(regression_predictions, axis=0), axis=0)
    if capability_names:
        ensemble_capability = np.mean(
            np.stack(capability_predictions, axis=0),
            axis=0,
        )
    else:
        ensemble_capability = np.empty((len(eval_records), 0), dtype=np.float64)
    regression_metrics = _regression_metrics(eval_y, ensemble_y)
    capability_metrics = _capability_metrics(
        eval_capability,
        ensemble_capability,
        capability_names,
    )
    artifact: dict[str, Any] = {
        "schema": ENSEMBLE_ARTIFACT_SCHEMA,
        "source": "offline_terrain_effect_ensemble_trainer",
        "status": "present",
        "input_contract": input_contract,
        "model_stage": (
            "stage1_executed_cut_to_outcome"
            if input_contract == "executed_cut"
            else "direct_planned_cut_to_outcome_ablation"
        ),
        "two_stage_calibration_status": (
            "not_applicable_stage1"
            if input_contract == "executed_cut"
            else "not_implemented"
        ),
        "release_status": (
            "offline_stage1_candidate"
            if input_contract == "executed_cut"
            else "not_release_without_incremental_5_percent_gate"
        ),
        "training_evidence": (
            EVIDENCE_TIER
            if input_contract == "executed_cut"
            else "controlled_frozen_act_calibration"
        ),
        "config": _json_config(config),
        "model": {
            "framework": "pytorch",
            "architecture": "mlp",
            "hidden_dims": list(config.hidden_dims),
            "activation": "relu",
            "regression_output_dim": len(REGRESSION_TARGET_NAMES),
            "capability_output_dim": len(capability_names),
        },
        "training_objective": {
            "regression_loss": config.regression_loss,
            "huber_delta": config.huber_delta,
            "capability_loss": (
                "binary_cross_entropy_with_logits"
                if capability_names
                else "not_trained"
            ),
        },
        "feature_names": train_feature_names,
        "regression_target_names": list(REGRESSION_TARGET_NAMES),
        "capability_target_names": capability_names,
        "capability_training_status": (
            (
                "hybrid_learned_and_rule_only"
                if excluded_capability_labels
                else "learned_classifier"
            )
            if capability_names
            else "rule_only_due_to_class_imbalance"
        ),
        "excluded_capability_labels": excluded_capability_labels,
        "train_record_count": len(train_records),
        "eval_record_count": len(eval_records),
        "episode_group_split": {
            "status": "disjoint",
            "train_episode_ids": sorted(train_episode_ids),
            "eval_episode_ids": sorted(eval_episode_ids),
            "provenance": dict(split_provenance or {}),
        },
        "normalization": {
            "feature_mean": x_mean.tolist(),
            "feature_scale": x_scale.tolist(),
            "regression_mean": y_mean.tolist(),
            "regression_scale": y_scale.tolist(),
        },
        "member_count": len(members),
        "members": members,
        "regression_metrics": regression_metrics,
        "capability_metrics": capability_metrics,
        "capability_identifiability": {
            name: metrics["status"] for name, metrics in capability_metrics.items()
        },
    }
    artifact_path = destination / "artifact.json"
    artifact["artifact_path"] = str(artifact_path.resolve())
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def train_terrain_effect_ensemble_from_grouped_fold(
    *,
    records: Sequence[Mapping[str, Any]],
    output_dir: str | Path,
    input_contract: EffectInputContract,
    fold_count: int = DEFAULT_GROUPED_FOLD_COUNT,
    eval_fold: int = 0,
    fold_salt: str = "terrain_effect_episode_grouped_v1",
    config: TerrainEffectEnsembleConfig | None = None,
) -> dict[str, Any]:
    """Assign deterministic episode folds and train on all non-eval folds."""

    resolved_config = config or TerrainEffectEnsembleConfig()
    if fold_count != resolved_config.grouped_cv_folds:
        raise ValueError(
            "fold_count must match the production config grouped_cv_folds."
        )
    if eval_fold < 0 or eval_fold >= fold_count:
        raise ValueError("eval_fold must be in [0, fold_count).")
    assignments = assign_episode_grouped_folds(
        records,
        fold_count=fold_count,
        salt=fold_salt,
    )
    train_records = [
        record
        for record in records
        if assignments[str(record["episode_id"])] != eval_fold
    ]
    eval_records = [
        record
        for record in records
        if assignments[str(record["episode_id"])] == eval_fold
    ]
    return train_terrain_effect_ensemble(
        train_records=train_records,
        eval_records=eval_records,
        output_dir=output_dir,
        input_contract=input_contract,
        config=resolved_config,
        split_provenance={
            "schema": "episode_grouped_fold_assignment_v1",
            "fold_count": int(fold_count),
            "eval_fold": int(eval_fold),
            "salt": fold_salt,
            "episode_to_fold": assignments,
        },
    )


class TerrainEffectEnsemblePredictor:
    """Loaded member models with a leakage-safe record-level prediction API."""

    def __init__(
        self,
        *,
        artifact: Mapping[str, Any],
        models: Sequence[Any],
        torch: Any,
        device: Any,
    ) -> None:
        self.artifact = dict(artifact)
        self.models = tuple(models)
        self._torch = torch
        self._device = device
        self.input_contract = str(self.artifact["input_contract"])

    def predict(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Predict signed net depth delta, payload, volume, and ensemble spread."""

        values, names = vectorize_effect_input(
            record,
            input_contract=self.input_contract,  # type: ignore[arg-type]
        )
        expected_names = list(self.artifact["feature_names"])
        if names != expected_names:
            raise ValueError("Prediction feature schema differs from the artifact.")
        normalization = self.artifact["normalization"]
        x_mean = np.asarray(normalization["feature_mean"], dtype=np.float64)
        x_scale = np.asarray(normalization["feature_scale"], dtype=np.float64)
        y_mean = np.asarray(normalization["regression_mean"], dtype=np.float64)
        y_scale = np.asarray(normalization["regression_scale"], dtype=np.float64)
        features = (np.asarray(values, dtype=np.float64) - x_mean) / x_scale
        feature_tensor = self._torch.as_tensor(
            features.reshape(1, -1),
            dtype=self._torch.float32,
            device=self._device,
        )
        member_regression: list[np.ndarray] = []
        with self._torch.no_grad():
            for model in self.models:
                output = model(feature_tensor).cpu().numpy().astype(np.float64)[0]
                member_regression.append(
                    output[: len(REGRESSION_TARGET_NAMES)] * y_scale + y_mean
                )
        predictions = np.stack(member_regression, axis=0)
        delta_members = predictions[:, :6]
        payload_members = predictions[:, 6]
        delta_mean = np.mean(delta_members, axis=0)
        payload_mean = float(np.mean(payload_members))

        pre_terrain = record.get("pre_terrain")
        if not isinstance(pre_terrain, Mapping):
            raise ValueError("pre_terrain must be an object.")
        valid_mask = np.asarray(
            pre_terrain.get("valid_mask"), dtype=np.float64
        ).reshape(-1)
        if valid_mask.size != 6 or not np.isfinite(valid_mask).all():
            raise ValueError("pre_terrain.valid_mask must contain 6 finite values.")
        valid_mask = valid_mask >= 0.5
        try:
            cell_area_m2 = float(pre_terrain.get("cell_area_m2"))
        except (TypeError, ValueError) as exc:
            raise ValueError("pre_terrain.cell_area_m2 must be positive.") from exc
        if not np.isfinite(cell_area_m2) or cell_area_m2 <= 0.0:
            raise ValueError("pre_terrain.cell_area_m2 must be positive.")
        removed_volume_members = (
            np.sum(
                np.where(valid_mask[None, :], np.maximum(delta_members, 0.0), 0.0),
                axis=1,
            )
            * cell_area_m2
        )
        refill_volume_members = (
            np.sum(
                np.where(valid_mask[None, :], np.maximum(-delta_members, 0.0), 0.0),
                axis=1,
            )
            * cell_area_m2
        )
        uncertainty_status = (
            "ensemble_standard_deviation"
            if len(self.models) >= 2
            else "single_member_zero_spread_not_ensemble_uncertainty"
        )
        return {
            "schema": ENSEMBLE_PREDICTION_SCHEMA,
            "source": "loaded_terrain_effect_ensemble",
            "status": "present",
            "input_contract": self.input_contract,
            "terrain_delta_semantics": "predicted_stable_post_minus_pre_signed_net",
            "signed_depth_delta_m": delta_mean.astype(float).tolist(),
            "payload_gain_kg": payload_mean,
            "derived_volume": {
                "semantics": (
                    "per_member_sum_max_signed_depth_delta_zero_times_"
                    "cell_area_over_valid_cells"
                ),
                "cell_area_source": "pre_terrain.cell_area_m2",
                "cell_area_m2": cell_area_m2,
                "valid_mask": valid_mask.astype(float).tolist(),
                "removed_volume_m3": float(np.mean(removed_volume_members)),
                "refill_volume_m3": float(np.mean(refill_volume_members)),
            },
            "uncertainty": {
                "status": uncertainty_status,
                "member_count": len(self.models),
                "signed_depth_delta_std_m": np.std(delta_members, axis=0, ddof=0)
                .astype(float)
                .tolist(),
                "payload_gain_kg_std": float(np.std(payload_members, ddof=0)),
                "removed_volume_m3_std": float(np.std(removed_volume_members, ddof=0)),
                "refill_volume_m3_std": float(np.std(refill_volume_members, ddof=0)),
            },
            "capability_status": self.artifact.get(
                "capability_training_status",
                "rule_only_due_to_class_imbalance",
            ),
        }


def load_terrain_effect_ensemble(
    artifact_path: str | Path,
    *,
    device: str = "cpu",
) -> TerrainEffectEnsemblePredictor:
    """Load every member checkpoint referenced by a v1 ensemble artifact."""

    import torch

    path = Path(artifact_path).resolve()
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if artifact.get("schema") != ENSEMBLE_ARTIFACT_SCHEMA:
        raise ValueError(f"Artifact schema must be {ENSEMBLE_ARTIFACT_SCHEMA!r}.")
    if artifact.get("status") != "present":
        raise ValueError("Only a present ensemble artifact can be loaded.")
    if device not in {"cpu", "cuda"}:
        raise ValueError("device must be 'cpu' or 'cuda'.")
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available.")
    torch_device = torch.device(device)
    input_dim = len(artifact.get("feature_names", []))
    capability_dim = len(artifact.get("capability_target_names", []))
    hidden_dims = tuple(int(value) for value in artifact["model"]["hidden_dims"])
    models: list[Any] = []
    for member in artifact.get("members", []):
        checkpoint_file = member.get("checkpoint_file")
        checkpoint_path = (
            path.parent / str(checkpoint_file)
            if checkpoint_file
            else Path(str(member["checkpoint_path"]))
        )
        try:
            checkpoint = torch.load(
                checkpoint_path,
                map_location=torch_device,
                weights_only=True,
            )
        except TypeError:
            checkpoint = torch.load(checkpoint_path, map_location=torch_device)
        if checkpoint.get("schema") != ENSEMBLE_MEMBER_SCHEMA:
            raise ValueError(f"Invalid ensemble member: {checkpoint_path}.")
        model = _build_model(
            torch,
            input_dim=input_dim,
            regression_dim=len(REGRESSION_TARGET_NAMES),
            capability_dim=capability_dim,
            hidden_dims=hidden_dims,  # type: ignore[arg-type]
        ).to(torch_device)
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        models.append(model)
    if not models:
        raise ValueError("Artifact contains no ensemble members.")
    if len(models) != int(artifact.get("member_count", -1)):
        raise ValueError("Artifact member count does not match loaded checkpoints.")
    return TerrainEffectEnsemblePredictor(
        artifact=artifact,
        models=models,
        torch=torch,
        device=torch_device,
    )


def load_planned_cut_effect_ensemble(
    artifact_path: str | Path,
    *,
    device: str = "cpu",
) -> TerrainEffectEnsemblePredictor:
    """Load an ensemble for the online planned-cut -> ACT-outcome boundary."""

    predictor = load_terrain_effect_ensemble(artifact_path, device=device)
    if predictor.input_contract != "planned_cut":
        raise ValueError("Online effect inference requires a planned_cut artifact.")
    if predictor.artifact.get("release_status") not in {
        "released",
        "release_allowed",
    }:
        raise ValueError(
            "The planned-cut effect artifact is not released for online use."
        )
    return predictor


def _build_model(
    torch: Any,
    *,
    input_dim: int,
    regression_dim: int,
    capability_dim: int,
    hidden_dims: tuple[int, int],
) -> Any:
    return torch.nn.Sequential(
        torch.nn.Linear(input_dim, hidden_dims[0]),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden_dims[0], hidden_dims[1]),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden_dims[1], regression_dim + capability_dim),
    )


def _train_member(
    *,
    torch: Any,
    model: Any,
    optimizer: Any,
    features: Any,
    regression_targets: Any,
    capability_targets: Any,
    regression_dim: int,
    capability_dim: int,
    config: TerrainEffectEnsembleConfig,
    seed: int,
) -> float:
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    final_loss = float("nan")
    n_rows = int(features.shape[0])
    for _ in range(config.epochs):
        permutation = torch.randperm(n_rows, generator=generator).tolist()
        for start in range(0, n_rows, config.batch_size):
            indices = permutation[start : start + config.batch_size]
            x_batch = features[indices]
            y_batch = regression_targets[indices]
            output = model(x_batch)
            regression_loss = torch.nn.functional.huber_loss(
                output[:, :regression_dim],
                y_batch,
                delta=config.huber_delta,
            )
            loss = regression_loss
            if capability_dim:
                capability_loss = torch.nn.functional.binary_cross_entropy_with_logits(
                    output[:, regression_dim:],
                    capability_targets[indices],
                )
                loss = loss + config.capability_loss_weight * capability_loss
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            final_loss = float(loss.detach().cpu().item())
    return final_loss


def _feature_matrix(
    records: Sequence[Mapping[str, Any]],
    *,
    input_contract: EffectInputContract,
) -> tuple[np.ndarray, list[str]]:
    rows: list[list[float]] = []
    names: list[str] | None = None
    for index, record in enumerate(records):
        values, row_names = vectorize_effect_input(
            record,
            input_contract=input_contract,
        )
        if names is None:
            names = row_names
        elif row_names != names:
            raise ValueError(f"Feature schema differs at record {index}.")
        rows.append(values)
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError("Effect input features must form a finite matrix.")
    return matrix, list(names or [])


def _regression_matrix(records: Sequence[Mapping[str, Any]]) -> np.ndarray:
    rows: list[list[float]] = []
    for index, record in enumerate(records):
        outcome = record.get("outcome")
        if not isinstance(outcome, Mapping):
            raise ValueError(f"Record {index} outcome must be an object.")
        delta = np.asarray(
            outcome.get("signed_depth_delta_m"),
            dtype=np.float64,
        ).reshape(-1)
        try:
            payload = float(outcome.get("payload_gain_kg"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Record {index} payload_gain_kg must be finite.") from exc
        if delta.size != 6 or not np.isfinite(delta).all() or not np.isfinite(payload):
            raise ValueError(
                f"Record {index} requires six finite terrain deltas and payload."
            )
        rows.append(delta.astype(float).tolist() + [payload])
    return np.asarray(rows, dtype=np.float64)


def _capability_training_contract(
    train_records: Sequence[Mapping[str, Any]],
    eval_records: Sequence[Mapping[str, Any]],
) -> tuple[list[str], dict[str, str]]:
    all_records = list(train_records) + list(eval_records)
    if not all_records:
        return [], {}
    candidates = sorted(
        {
            str(name)
            for record in all_records
            if isinstance(record.get("capability_labels"), Mapping)
            for name in record["capability_labels"]
        }
    )
    trainable: list[str] = []
    excluded: dict[str, str] = {}
    support = assess_capability_label_support(train_records)
    for name in candidates:
        if not all(
            isinstance(record.get("capability_labels"), Mapping)
            and isinstance(record["capability_labels"].get(name), (bool, np.bool_))
            for record in all_records
        ):
            excluded[name] = "missing_explicit_boolean_label"
            continue
        train_values = {
            bool(record["capability_labels"][name]) for record in train_records
        }
        if len(train_values) < 2:
            excluded[name] = "single_class_in_training_split"
            continue
        support_result = support["labels"].get(name, {})
        if support_result.get("status") != "eligible_for_learned_classifier":
            excluded[name] = "insufficient_20_each_or_3_reset_groups_per_class"
            continue
        trainable.append(name)
    return trainable, excluded


def _capability_matrix(
    records: Sequence[Mapping[str, Any]],
    names: Sequence[str],
) -> np.ndarray:
    return np.asarray(
        [
            [float(bool(record["capability_labels"][name])) for name in names]
            for record in records
        ],
        dtype=np.float64,
    ).reshape(len(records), len(names))


def _normalization(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = np.mean(values, axis=0)
    scale = np.std(values, axis=0)
    scale = np.where(scale < 1.0e-8, 1.0, scale)
    return mean, scale


def _regression_metrics(
    expected: np.ndarray,
    predicted: np.ndarray,
) -> dict[str, Any]:
    error = predicted - expected
    return {
        "status": "present",
        "mae": float(np.mean(np.abs(error))),
        "mse": float(np.mean(np.square(error))),
        "by_target": {
            name: {
                "mae": float(np.mean(np.abs(error[:, index]))),
                "mse": float(np.mean(np.square(error[:, index]))),
            }
            for index, name in enumerate(REGRESSION_TARGET_NAMES)
        },
    }


def _capability_metrics(
    expected: np.ndarray,
    probabilities: np.ndarray,
    names: Sequence[str],
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    epsilon = 1.0e-7
    for index, name in enumerate(names):
        target = expected[:, index]
        probability = np.clip(probabilities[:, index], epsilon, 1.0 - epsilon)
        unique = np.unique(target)
        metrics[name] = {
            "status": (
                "present" if unique.size >= 2 else "not_identifiable_single_class"
            ),
            "positive_count": int(np.count_nonzero(target >= 0.5)),
            "negative_count": int(np.count_nonzero(target < 0.5)),
            "accuracy_at_0_5": float(np.mean((probability >= 0.5) == (target >= 0.5))),
            "binary_cross_entropy": float(
                -np.mean(
                    target * np.log(probability)
                    + (1.0 - target) * np.log(1.0 - probability)
                )
            ),
        }
    return metrics


def _episode_ids(
    records: Sequence[Mapping[str, Any]],
    collection_name: str,
) -> set[str]:
    result: set[str] = set()
    for index, record in enumerate(records):
        episode_id = record.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id.strip():
            raise ValueError(
                f"{collection_name}[{index}] requires a non-empty episode_id."
            )
        result.add(episode_id)
    return result


def _set_seed(torch: Any, seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _json_config(config: TerrainEffectEnsembleConfig) -> dict[str, Any]:
    result = asdict(config)
    result["hidden_dims"] = list(config.hidden_dims)
    result["seeds"] = list(config.seeds)
    return result


__all__ = [
    "DEFAULT_GROUPED_FOLD_COUNT",
    "ENSEMBLE_ARTIFACT_SCHEMA",
    "ENSEMBLE_CONFIG_SCHEMA",
    "ENSEMBLE_MEMBER_SCHEMA",
    "ENSEMBLE_PREDICTION_SCHEMA",
    "REGRESSION_TARGET_NAMES",
    "TerrainEffectEnsembleConfig",
    "TerrainEffectEnsemblePredictor",
    "load_planned_cut_effect_ensemble",
    "load_terrain_effect_ensemble",
    "train_terrain_effect_ensemble",
    "train_terrain_effect_ensemble_from_grouped_fold",
]
