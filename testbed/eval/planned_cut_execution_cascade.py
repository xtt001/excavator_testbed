"""Frozen-ACT planned-cut calibration and two-stage effect cascade."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.eval.executed_cut_effect_samples import vectorize_effect_input
from testbed.eval.terrain_effect_ensemble import load_terrain_effect_ensemble

PLANNED_EXECUTION_ARTIFACT_SCHEMA = "planned_execution_ensemble_artifact_v1"
PLANNED_EXECUTION_MEMBER_SCHEMA = "planned_execution_ensemble_member_v1"
PLANNED_EFFECT_CASCADE_SCHEMA = "planned_cut_effect_cascade_artifact_v1"
EXECUTION_TARGET_NAMES = (
    "actual_entry_x_m",
    "actual_entry_z_m",
    "actual_exit_x_m",
    "actual_exit_z_m",
    "actual_direction_x",
    "actual_direction_z",
    "actual_length_m",
    "actual_surface_penetration_peak_m",
)


@dataclass(frozen=True)
class PlannedExecutionEnsembleConfig:
    hidden_dims: tuple[int, int] = (64, 64)
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4)
    epochs: int = 100
    batch_size: int = 64
    learning_rate: float = 1.0e-3
    weight_decay: float = 1.0e-5
    huber_delta: float = 1.0
    device: str = "cpu"

    def __post_init__(self) -> None:
        if tuple(self.hidden_dims) != (64, 64):
            raise ValueError("planned execution v1 architecture is fixed at 2x64")
        if not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be non-empty and unique")
        if self.epochs <= 0 or self.batch_size <= 0:
            raise ValueError("epochs and batch_size must be positive")
        if self.learning_rate <= 0.0 or self.weight_decay < 0.0:
            raise ValueError("invalid optimizer configuration")
        if self.huber_delta <= 0.0:
            raise ValueError("huber_delta must be positive")
        if self.device not in {"cpu", "cuda"}:
            raise ValueError("device must be 'cpu' or 'cuda'")


def train_planned_execution_ensemble(
    *,
    train_records: Sequence[Mapping[str, Any]],
    eval_records: Sequence[Mapping[str, Any]],
    output_dir: str | Path,
    config: PlannedExecutionEnsembleConfig | None = None,
) -> dict[str, Any]:
    """Train planned+pre-state -> executed-cut distribution by reset group."""

    import torch

    config = config or PlannedExecutionEnsembleConfig()
    if not train_records or not eval_records:
        raise ValueError("train_records and eval_records must be non-empty")
    train_groups = _reset_groups(train_records)
    eval_groups = _reset_groups(eval_records)
    overlap = sorted(train_groups & eval_groups)
    if overlap:
        raise ValueError(f"reset-group split leakage: {overlap}")
    if config.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    train_x, names = _planned_features(train_records)
    eval_x, eval_names = _planned_features(eval_records)
    if names != eval_names:
        raise ValueError("train/eval feature schemas differ")
    train_y = _execution_targets(train_records)
    eval_y = _execution_targets(eval_records)
    x_mean, x_scale = _normalization(train_x)
    y_mean, y_scale = _normalization(train_y)

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=False)
    device = torch.device(config.device)
    x_tensor = torch.as_tensor(
        (train_x - x_mean) / x_scale,
        dtype=torch.float32,
        device=device,
    )
    y_tensor = torch.as_tensor(
        (train_y - y_mean) / y_scale,
        dtype=torch.float32,
        device=device,
    )
    eval_tensor = torch.as_tensor(
        (eval_x - x_mean) / x_scale,
        dtype=torch.float32,
        device=device,
    )
    members: list[dict[str, Any]] = []
    predictions: list[np.ndarray] = []
    for seed in config.seeds:
        _set_seed(torch, int(seed))
        model = _model(torch, train_x.shape[1], config.hidden_dims).to(device)
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )
        generator = torch.Generator(device="cpu")
        generator.manual_seed(int(seed))
        final_loss = float("nan")
        for _ in range(config.epochs):
            indices = torch.randperm(len(train_records), generator=generator).tolist()
            for start in range(0, len(indices), config.batch_size):
                batch = indices[start : start + config.batch_size]
                output = model(x_tensor[batch])
                loss = torch.nn.functional.huber_loss(
                    output,
                    y_tensor[batch],
                    delta=config.huber_delta,
                )
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
                final_loss = float(loss.detach().cpu().item())
        model.eval()
        with torch.no_grad():
            normalized = model(eval_tensor).cpu().numpy().astype(np.float64)
        predictions.append(normalized * y_scale + y_mean)
        checkpoint = destination / f"member_seed_{int(seed)}.pt"
        torch.save(
            {
                "schema": PLANNED_EXECUTION_MEMBER_SCHEMA,
                "seed": int(seed),
                "feature_names": names,
                "target_names": list(EXECUTION_TARGET_NAMES),
                "normalization": {
                    "feature_mean": x_mean.tolist(),
                    "feature_scale": x_scale.tolist(),
                    "target_mean": y_mean.tolist(),
                    "target_scale": y_scale.tolist(),
                },
                "state_dict": model.state_dict(),
            },
            checkpoint,
        )
        members.append(
            {
                "seed": int(seed),
                "checkpoint_file": checkpoint.name,
                "sha256": _sha256(checkpoint),
                "final_training_loss": final_loss,
            }
        )
    mean_prediction = np.mean(np.stack(predictions), axis=0)
    artifact = {
        "schema": PLANNED_EXECUTION_ARTIFACT_SCHEMA,
        "source": "controlled_frozen_act_planned_execution_trainer",
        "status": "present",
        "input_contract": "planned_cut",
        "output_contract": "executed_cut_distribution_v1",
        "model_stage": "planned_cut_to_executed_cut_distribution",
        "release_status": "offline_calibration_candidate",
        "config": asdict(config),
        "feature_names": names,
        "target_names": list(EXECUTION_TARGET_NAMES),
        "normalization": {
            "feature_mean": x_mean.tolist(),
            "feature_scale": x_scale.tolist(),
            "target_mean": y_mean.tolist(),
            "target_scale": y_scale.tolist(),
        },
        "member_count": len(members),
        "members": members,
        "reset_group_split": {
            "status": "disjoint",
            "train": sorted(train_groups),
            "eval": sorted(eval_groups),
        },
        "eval_mae": {
            name: float(np.mean(np.abs(mean_prediction[:, index] - eval_y[:, index])))
            for index, name in enumerate(EXECUTION_TARGET_NAMES)
        },
    }
    (destination / "artifact.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


class PlannedExecutionEnsemblePredictor:
    def __init__(self, *, artifact: Mapping[str, Any], models: Sequence[Any], torch: Any, device: Any) -> None:
        self.artifact = dict(artifact)
        self.models = tuple(models)
        self._torch = torch
        self._device = device
        self.input_contract = "planned_cut"

    def predict(self, record: Mapping[str, Any]) -> dict[str, Any]:
        values, names = vectorize_effect_input(record, input_contract="planned_cut")
        if names != list(self.artifact["feature_names"]):
            raise ValueError("planned execution feature schema mismatch")
        norm = self.artifact["normalization"]
        x = (np.asarray(values) - np.asarray(norm["feature_mean"])) / np.asarray(
            norm["feature_scale"]
        )
        tensor = self._torch.as_tensor(
            x.reshape(1, -1), dtype=self._torch.float32, device=self._device
        )
        rows: list[np.ndarray] = []
        with self._torch.no_grad():
            for model in self.models:
                output = model(tensor).cpu().numpy().astype(np.float64)[0]
                rows.append(
                    output * np.asarray(norm["target_scale"])
                    + np.asarray(norm["target_mean"])
                )
        members = np.stack(rows)
        return {
            "schema": "planned_execution_ensemble_prediction_v1",
            "status": "present",
            "executed_cut_mean": _executed_cut_dict(np.mean(members, axis=0)),
            "executed_cut_std": {
                name: float(value)
                for name, value in zip(
                    EXECUTION_TARGET_NAMES,
                    np.std(members, axis=0, ddof=0),
                    strict=True,
                )
            },
            "member_executed_cuts": [
                _executed_cut_dict(row) for row in members
            ],
        }


def load_planned_execution_ensemble(
    artifact_path: str | Path,
    *,
    device: str = "cpu",
) -> PlannedExecutionEnsemblePredictor:
    import torch

    path = Path(artifact_path).resolve()
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if artifact.get("schema") != PLANNED_EXECUTION_ARTIFACT_SCHEMA:
        raise ValueError("planned execution artifact schema mismatch")
    if artifact.get("status") != "present":
        raise ValueError("planned execution artifact is not present")
    torch_device = torch.device(device)
    models = []
    for member in artifact.get("members", []):
        checkpoint_path = path.parent / str(member["checkpoint_file"])
        if _sha256(checkpoint_path) != member.get("sha256"):
            raise ValueError("planned execution member sha256 mismatch")
        try:
            checkpoint = torch.load(
                checkpoint_path, map_location=torch_device, weights_only=True
            )
        except TypeError:
            checkpoint = torch.load(checkpoint_path, map_location=torch_device)
        if checkpoint.get("schema") != PLANNED_EXECUTION_MEMBER_SCHEMA:
            raise ValueError("planned execution member schema mismatch")
        model = _model(
            torch,
            len(artifact["feature_names"]),
            tuple(artifact["config"]["hidden_dims"]),
        ).to(torch_device)
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        models.append(model)
    if len(models) != int(artifact.get("member_count", -1)) or not models:
        raise ValueError("planned execution member count mismatch")
    return PlannedExecutionEnsemblePredictor(
        artifact=artifact,
        models=models,
        torch=torch,
        device=torch_device,
    )


def build_planned_cut_effect_cascade(
    *,
    planned_execution_artifact_path: str | Path,
    silver_effect_artifact_path: str | Path,
    acceptance: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Release a cascade only after the held-out reset gate passes."""

    if acceptance.get("schema") != "planned_cut_calibration_acceptance_v1":
        raise ValueError("planned calibration acceptance schema mismatch")
    if (
        acceptance.get("status") != "pass"
        or not isinstance(acceptance.get("two_stage_calibration_gate"), Mapping)
        or acceptance["two_stage_calibration_gate"].get("status") != "pass"
    ):
        raise ValueError("two-stage held-out reset calibration gate not passed")
    planned_path = Path(planned_execution_artifact_path).resolve()
    silver_path = Path(silver_effect_artifact_path).resolve()
    # Loading here verifies model schemas and every member checkpoint.
    load_planned_execution_ensemble(planned_path)
    silver = load_terrain_effect_ensemble(silver_path)
    if silver.input_contract != "executed_cut":
        raise ValueError("cascade requires an executed_cut silver effect model")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=False)
    artifact = {
        "schema": PLANNED_EFFECT_CASCADE_SCHEMA,
        "source": "frozen_act_planned_to_executed_to_silver_cascade",
        "status": "present",
        "input_contract": "planned_cut",
        "output_contract": "planned_cut_effect_v1",
        "model_stage": "plan_to_executed_to_silver",
        "release_status": "released",
        "planned_execution": {
            "artifact_path": str(planned_path),
            "sha256": _sha256(planned_path),
        },
        "silver_effect": {
            "artifact_path": str(silver_path),
            "sha256": _sha256(silver_path),
        },
        "calibration_acceptance": dict(acceptance),
        "direct_planned_residual": {
            "status": acceptance.get("direct_planned_residual_gate", {}).get(
                "status", "not_evaluated_not_release"
            )
        },
    }
    (destination / "artifact.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


class PlannedCutEffectCascadePredictor:
    input_contract = "planned_cut"

    def __init__(self, calibration: PlannedExecutionEnsemblePredictor, silver: Any) -> None:
        self.calibration = calibration
        self.silver = silver

    def predict(self, record: Mapping[str, Any]) -> dict[str, Any]:
        execution = self.calibration.predict(record)
        effect_rows = [
            self.silver.predict(_as_executed_record(record, cut))
            for cut in execution["member_executed_cuts"]
        ]
        delta_means = np.asarray(
            [row["signed_depth_delta_m"] for row in effect_rows], dtype=np.float64
        )
        delta_stds = np.asarray(
            [row["uncertainty"]["signed_depth_delta_std_m"] for row in effect_rows],
            dtype=np.float64,
        )
        payload_means = np.asarray(
            [row["payload_gain_kg"] for row in effect_rows], dtype=np.float64
        )
        payload_stds = np.asarray(
            [row["uncertainty"]["payload_gain_kg_std"] for row in effect_rows],
            dtype=np.float64,
        )
        removed_means = np.asarray(
            [row["derived_volume"]["removed_volume_m3"] for row in effect_rows],
            dtype=np.float64,
        )
        removed_stds = np.asarray(
            [row["uncertainty"]["removed_volume_m3_std"] for row in effect_rows],
            dtype=np.float64,
        )
        refill_means = np.asarray(
            [row["derived_volume"]["refill_volume_m3"] for row in effect_rows],
            dtype=np.float64,
        )
        refill_stds = np.asarray(
            [row["uncertainty"]["refill_volume_m3_std"] for row in effect_rows],
            dtype=np.float64,
        )
        return {
            "schema": "planned_cut_effect_cascade_prediction_v1",
            "status": "present",
            "input_contract": "planned_cut",
            "signed_depth_delta_m": np.mean(delta_means, axis=0).tolist(),
            "payload_gain_kg": float(np.mean(payload_means)),
            "derived_volume": {
                "removed_volume_m3": float(np.mean(removed_means)),
                "refill_volume_m3": float(np.mean(refill_means)),
            },
            "uncertainty": {
                "status": "calibration_and_silver_ensemble_total_variance",
                "signed_depth_delta_std_m": _total_std(
                    delta_means, delta_stds
                ).tolist(),
                "payload_gain_kg_std": float(
                    _total_std(payload_means, payload_stds)
                ),
                "removed_volume_m3_std": float(
                    _total_std(removed_means, removed_stds)
                ),
                "refill_volume_m3_std": float(
                    _total_std(refill_means, refill_stds)
                ),
            },
            "capability_status": "rule_or_separately_gated_capability_only",
        }


def load_planned_cut_effect_cascade(
    artifact_path: str | Path,
    *,
    device: str = "cpu",
) -> PlannedCutEffectCascadePredictor:
    path = Path(artifact_path).resolve()
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if artifact.get("schema") != PLANNED_EFFECT_CASCADE_SCHEMA:
        raise ValueError("planned effect cascade schema mismatch")
    if artifact.get("status") != "present" or artifact.get("release_status") != "released":
        raise ValueError("planned effect cascade is not released")
    planned_path = _verified_reference(path, artifact["planned_execution"])
    silver_path = _verified_reference(path, artifact["silver_effect"])
    return PlannedCutEffectCascadePredictor(
        load_planned_execution_ensemble(planned_path, device=device),
        load_terrain_effect_ensemble(silver_path, device=device),
    )


def _planned_features(
    records: Sequence[Mapping[str, Any]],
) -> tuple[np.ndarray, list[str]]:
    rows = []
    names: list[str] | None = None
    for record in records:
        values, row_names = vectorize_effect_input(record, input_contract="planned_cut")
        if names is None:
            names = row_names
        elif row_names != names:
            raise ValueError("planned feature schema differs between records")
        rows.append(values)
    matrix = np.asarray(rows, dtype=np.float64)
    if not np.isfinite(matrix).all():
        raise ValueError("planned features contain non-finite values")
    return matrix, list(names or [])


def _execution_targets(records: Sequence[Mapping[str, Any]]) -> np.ndarray:
    rows = []
    for index, record in enumerate(records):
        execution = record.get("execution")
        if not isinstance(execution, Mapping):
            raise ValueError(f"record {index} execution must be an object")
        row = []
        for field in EXECUTION_TARGET_NAMES:
            try:
                value = float(execution[field])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"execution.{field} must be finite") from exc
            if not np.isfinite(value):
                raise ValueError(f"execution.{field} must be finite")
            row.append(value)
        rows.append(row)
    return np.asarray(rows, dtype=np.float64)


def _executed_cut_dict(values: np.ndarray) -> dict[str, Any]:
    actual = {
        name: float(value)
        for name, value in zip(EXECUTION_TARGET_NAMES, values, strict=True)
    }
    return {
        "entry_x_m": actual["actual_entry_x_m"],
        "entry_z_m": actual["actual_entry_z_m"],
        "exit_x_m": actual["actual_exit_x_m"],
        "exit_z_m": actual["actual_exit_z_m"],
        "direction_x": actual["actual_direction_x"],
        "direction_z": actual["actual_direction_z"],
        "length_m": max(0.0, actual["actual_length_m"]),
        "actual_surface_penetration_peak_m": max(
            0.0, actual["actual_surface_penetration_peak_m"]
        ),
        "valid": True,
    }


def _as_executed_record(
    planned: Mapping[str, Any], cut: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "effect_input_schema": planned["effect_input_schema"],
        "pre_terrain": planned["pre_terrain"],
        "execution_context": planned["execution_context"],
        "executed_cut": dict(cut),
    }


def _total_std(means: np.ndarray, within_stds: np.ndarray) -> np.ndarray:
    mean = np.mean(means, axis=0)
    variance = np.mean(within_stds**2 + means**2, axis=0) - mean**2
    return np.sqrt(np.maximum(variance, 0.0))


def _model(torch: Any, input_dim: int, hidden_dims: tuple[int, int]) -> Any:
    return torch.nn.Sequential(
        torch.nn.Linear(input_dim, hidden_dims[0]),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden_dims[0], hidden_dims[1]),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden_dims[1], len(EXECUTION_TARGET_NAMES)),
    )


def _normalization(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = np.mean(values, axis=0)
    scale = np.std(values, axis=0)
    scale = np.where(scale < 1.0e-6, 1.0, scale)
    return mean, scale


def _reset_groups(records: Sequence[Mapping[str, Any]]) -> set[str]:
    groups: set[str] = set()
    for record in records:
        value = record.get("reset_group_id")
        if not isinstance(value, str) or not value:
            raise ValueError("every planned calibration record needs reset_group_id")
        groups.add(value)
    return groups


def _set_seed(torch: Any, seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verified_reference(parent: Path, descriptor: Mapping[str, Any]) -> Path:
    referenced = Path(str(descriptor["artifact_path"]))
    if not referenced.is_absolute():
        referenced = parent.parent / referenced
    referenced = referenced.resolve()
    if _sha256(referenced) != descriptor.get("sha256"):
        raise ValueError("cascade artifact reference sha256 mismatch")
    return referenced


__all__ = [
    "EXECUTION_TARGET_NAMES",
    "PLANNED_EFFECT_CASCADE_SCHEMA",
    "PLANNED_EXECUTION_ARTIFACT_SCHEMA",
    "PlannedExecutionEnsembleConfig",
    "build_planned_cut_effect_cascade",
    "load_planned_cut_effect_cascade",
    "load_planned_execution_ensemble",
    "train_planned_execution_ensemble",
]
