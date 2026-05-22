"""Measure whether a conditioned dig ACT reacts to different dig_cut_tokens."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.operator_first_v2_2 import _build_dig_cut_token
from testbed.policies.act.adapter import ACTAdapter
from testbed.runtime._train import _resolve_low_dim_state_dim


DEFAULT_PRIOR_PATH = Path(
    "testbed/configs/planner_priors/yulong_operator_first_dig_cut_prior_v1.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-dig-token-sensitivity",
        description="Compare first-step ACT actions under several dig_cut_token variants.",
    )
    parser.add_argument("--config", required=True, help="ACT training YAML config.")
    parser.add_argument("--ckpt", required=True, help="policy_best.ckpt to test.")
    parser.add_argument(
        "--dataset-dir",
        default=None,
        help="Primitive dig dataset root. Defaults to task.dataset_dir in config.",
    )
    parser.add_argument("--episode-id", type=int, default=0)
    parser.add_argument("--step", type=int, default=0)
    parser.add_argument(
        "--prior",
        default=str(DEFAULT_PRIOR_PATH),
        help="Operator prior JSON used to synthesize token variants.",
    )
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument("--device", default=None, help="Override policy device.")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = yaml.safe_load(config_path.read_text()) or {}
    task_cfg = dict(config.get("task", {}) or {})
    policy_cfg = dict(config.get("policy", {}) or {})
    train_cfg = dict(config.get("train", {}) or {})
    act_params = dict(policy_cfg.get("act_params", {}) or {})
    outcome_head_cfg = dict(policy_cfg.get("outcome_head") or {})
    outcome_head_enabled = bool(outcome_head_cfg.get("enabled", False))

    dataset_dir = Path(args.dataset_dir or task_cfg["dataset_dir"])
    episode_path = dataset_dir / f"episode_{int(args.episode_id)}.hdf5"
    if not episode_path.exists():
        raise FileNotFoundError(episode_path)

    low_dim_keys = list(policy_cfg.get("low_dim_keys", ["qpos"]))
    if "dig_cut_tokens" not in low_dim_keys:
        raise ValueError(
            "dig token sensitivity requires policy.low_dim_keys to include "
            "'dig_cut_tokens'."
        )
    camera_names = list(task_cfg.get("camera_names", ["fpv"]))
    equipment_model = str(task_cfg.get("equipment_model", "yulong"))
    episode_len = int(task_cfg.get("episode_len", 128))
    device = str(args.device or policy_cfg.get("device") or train_cfg.get("device") or "cuda")
    ckpt_path = Path(args.ckpt)
    ckpt_dir = ckpt_path.parent

    adapter_config = {
        "lr": float(train_cfg.get("lr", 1.0e-5)),
        "num_queries": int(act_params.get("chunk_size", 100)),
        "kl_weight": float(act_params.get("kl_weight", 10.0)),
        "hidden_dim": int(act_params.get("hidden_dim", 512)),
        "dim_feedforward": int(act_params.get("dim_feedforward", 3200)),
        "lr_backbone": 1.0e-5,
        "backbone": "resnet18",
        "enc_layers": 4,
        "dec_layers": 7,
        "nheads": 8,
        "camera_names": camera_names,
        "equipment_model": equipment_model,
        "max_episode_len": episode_len,
        "low_dim_keys": low_dim_keys,
        "state_dim": _resolve_low_dim_state_dim(low_dim_keys, equipment_model),
        "image_mask": dict(policy_cfg.get("image_mask") or {}),
        "outcome_head": outcome_head_cfg,
        "outcome_dim": int(
            outcome_head_cfg.get("dim", 10 if outcome_head_enabled else 0)
        )
        if outcome_head_enabled
        else 0,
        "outcome_action_horizon": int(
            outcome_head_cfg.get("action_horizon", act_params.get("chunk_size", 100))
        ),
        "outcome_hidden_dim": outcome_head_cfg.get("hidden_dim"),
    }
    policy = ACTAdapter.from_checkpoint(
        ckpt_path=ckpt_path,
        policy_config=adapter_config,
        norm_stats_path=ckpt_dir / "dataset_stats.pkl",
        temporal_agg=False,
        device=device,
    )

    obs, observed_token = _read_single_obs(
        episode_path=episode_path,
        step=int(args.step),
        camera_names=camera_names,
    )
    variants = _build_token_variants(
        observed_token=observed_token,
        prior_path=Path(args.prior),
    )

    actions: dict[str, list[float]] = {}
    outcomes: dict[str, list[float] | None] = {}
    for name, token in variants.items():
        variant_obs = dict(obs)
        variant_obs["dig_cut_tokens"] = np.asarray(token, dtype=np.float32)
        policy.reset()
        action, outcome = policy.predict_with_outcome(variant_obs)
        actions[name] = [float(value) for value in action.reshape(-1)]
        outcomes[name] = (
            None
            if outcome is None
            else [float(value) for value in outcome.reshape(-1)]
        )

    baseline_name = "observed"
    baseline = np.asarray(actions[baseline_name], dtype=np.float32)
    deltas = {}
    for name, action in actions.items():
        action_arr = np.asarray(action, dtype=np.float32)
        diff = action_arr - baseline
        deltas[name] = {
            "l2": float(np.linalg.norm(diff)),
            "abs_max": float(np.max(np.abs(diff))) if diff.size else 0.0,
            "per_dim": [float(value) for value in diff.reshape(-1)],
        }

    action_matrix = np.asarray(list(actions.values()), dtype=np.float32)
    outcome_deltas = {}
    outcome_matrix = None
    if outcomes[baseline_name] is not None:
        baseline_outcome = np.asarray(outcomes[baseline_name], dtype=np.float32)
        valid_outcomes = []
        for name, outcome in outcomes.items():
            if outcome is None:
                continue
            outcome_arr = np.asarray(outcome, dtype=np.float32)
            valid_outcomes.append(outcome_arr)
            diff = outcome_arr - baseline_outcome
            outcome_deltas[name] = {
                "l2": float(np.linalg.norm(diff)),
                "abs_max": float(np.max(np.abs(diff))) if diff.size else 0.0,
                "per_dim": [float(value) for value in diff.reshape(-1)],
            }
        if valid_outcomes:
            outcome_matrix = np.asarray(valid_outcomes, dtype=np.float32)
    output = {
        "config": str(config_path),
        "checkpoint": str(ckpt_path),
        "dataset_dir": str(dataset_dir),
        "episode_path": str(episode_path),
        "episode_id": int(args.episode_id),
        "step": int(args.step),
        "low_dim_keys": low_dim_keys,
        "token_variants": {
            name: [float(value) for value in token.reshape(-1)]
            for name, token in variants.items()
        },
        "actions": actions,
        "predicted_outcomes": outcomes,
        "deltas_vs_observed": deltas,
        "outcome_deltas_vs_observed": outcome_deltas,
        "summary": {
            "variant_count": int(len(variants)),
            "mean_action_std": float(np.mean(np.std(action_matrix, axis=0))),
            "max_action_std": float(np.max(np.std(action_matrix, axis=0))),
            "has_outcome_head": bool(outcome_matrix is not None),
            "mean_outcome_std": float(np.mean(np.std(outcome_matrix, axis=0)))
            if outcome_matrix is not None
            else 0.0,
            "max_outcome_std": float(np.max(np.std(outcome_matrix, axis=0)))
            if outcome_matrix is not None
            else 0.0,
            "mean_l2_delta_vs_observed": float(
                np.mean(
                    [
                        value["l2"]
                        for name, value in deltas.items()
                        if name != baseline_name
                    ]
                )
            ),
            "max_l2_delta_vs_observed": float(
                np.max(
                    [
                        value["l2"]
                        for name, value in deltas.items()
                        if name != baseline_name
                    ]
                )
            ),
            "mean_outcome_l2_delta_vs_observed": float(
                np.mean(
                    [
                        value["l2"]
                        for name, value in outcome_deltas.items()
                        if name != baseline_name
                    ]
                )
            )
            if outcome_deltas
            else 0.0,
            "max_outcome_l2_delta_vs_observed": float(
                np.max(
                    [
                        value["l2"]
                        for name, value in outcome_deltas.items()
                        if name != baseline_name
                    ]
                )
            )
            if outcome_deltas
            else 0.0,
        },
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output["summary"], indent=2, sort_keys=True))
    print(output_path)


def _read_single_obs(
    *,
    episode_path: Path,
    step: int,
    camera_names: list[str],
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    with h5py.File(episode_path, "r") as handle:
        n_steps = int(handle["observations/qpos"].shape[0])
        if step < 0 or step >= n_steps:
            raise IndexError(f"step {step} out of range for {episode_path} ({n_steps})")
        obs: dict[str, np.ndarray] = {
            "qpos": handle["observations/qpos"][step].astype(np.float32),
            "qvel": handle["observations/qvel"][step].astype(np.float32),
        }
        if "v2/step/dig_cut_tokens" not in handle:
            raise KeyError(f"{episode_path} is missing /v2/step/dig_cut_tokens")
        observed_token = handle["v2/step/dig_cut_tokens"][step].astype(np.float32)
        for camera_name in camera_names:
            dataset_path = f"observations/images/{camera_name}"
            if dataset_path not in handle:
                raise KeyError(f"{episode_path} is missing {dataset_path}")
            obs[f"image_{camera_name}"] = handle[dataset_path][step]
    return obs, observed_token


def _build_token_variants(
    *,
    observed_token: np.ndarray,
    prior_path: Path,
) -> dict[str, np.ndarray]:
    variants: dict[str, np.ndarray] = {
        "observed": np.asarray(observed_token, dtype=np.float32),
        "zero_valid": np.asarray([0.0] * 9 + [1.0], dtype=np.float32),
    }
    if prior_path.exists():
        prior = json.loads(prior_path.read_text())
        fields = dict(prior.get("fields", {}) or {})
        for percentile in ("p10", "p50", "p90"):
            variants[f"prior_{percentile}"] = _build_dig_cut_token(
                _prior_fields(fields=fields, percentile=percentile)
            )
        variants["prior_entry_p10_exit_p90"] = _build_dig_cut_token(
            _prior_fields(
                fields=fields,
                percentile="p50",
                overrides={
                    "entry_x_m": "p10",
                    "entry_z_m": "p10",
                    "exit_x_m": "p90",
                    "exit_z_m": "p90",
                },
            )
        )
        variants["prior_entry_p90_exit_p10"] = _build_dig_cut_token(
            _prior_fields(
                fields=fields,
                percentile="p50",
                overrides={
                    "entry_x_m": "p90",
                    "entry_z_m": "p90",
                    "exit_x_m": "p10",
                    "exit_z_m": "p10",
                },
            )
        )
    return variants


def _prior_fields(
    *,
    fields: dict[str, Any],
    percentile: str,
    overrides: dict[str, str] | None = None,
) -> dict[str, float | int]:
    overrides = dict(overrides or {})

    def value(name: str, default: float = 0.0) -> float:
        source_percentile = overrides.get(name, percentile)
        stats = dict(fields.get(name, {}) or {})
        return float(stats.get(source_percentile, default))

    return {
        "operator_entry_x_m": value("entry_x_m"),
        "operator_entry_z_m": value("entry_z_m"),
        "operator_exit_x_m": value("exit_x_m"),
        "operator_exit_z_m": value("exit_z_m"),
        "operator_cut_direction_x": value("cut_direction_x", -1.0),
        "operator_cut_direction_z": value("cut_direction_z", 0.0),
        "operator_cut_length_m": value("cut_length_m", 1.0),
        "operator_cut_depth_peak_m": value("cut_depth_peak_m", 1.0),
        "operator_cut_payload_gain_kg": value("payload_gain_kg", 55.0),
        "operator_cut_valid": 1,
    }


if __name__ == "__main__":
    main()
