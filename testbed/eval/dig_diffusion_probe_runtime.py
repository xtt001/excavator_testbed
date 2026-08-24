"""Orchestration contract for the offline, non-promotable minimal Dig DP probe."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

from testbed.eval.dig_diffusion_probe_data import (
    build_evaluation_observation_cache,
    build_evaluation_token_conditions,
    build_training_window_cache,
    load_npz_arrays,
)
from testbed.eval.dig_diffusion_probe_evaluation import evaluate_minimal_dp_model
from testbed.eval.dig_diffusion_probe_lineage import resolve_minimal_dp_probe_lineage
from testbed.eval.dig_diffusion_probe_metrics import (
    classify_minimal_dp_probe,
    condition_distribution_metrics,
    training_seed_direction_consistency,
)
from testbed.eval.dig_diffusion_probe_projection import project_dp_dispatch_replicas
from testbed.eval.dig_diffusion_probe_reporting import (
    render_minimal_dp_probe_report,
    write_minimal_dp_probe_plots,
)
from testbed.eval.dig_diffusion_probe_training import (
    MinimalDPTrainingConfig,
    load_minimal_dp_checkpoint,
    train_minimal_dp_seed,
)
from testbed.eval.dig_receding_horizon_artifacts import (
    file_identity,
    write_json_exclusive,
    write_text_exclusive,
)
from testbed.eval.dig_receding_horizon_lineage import resolve_authoritative_lineage
from testbed.eval.dig_receding_horizon_runtime import (
    DEFAULT_COMPARISON_ARTIFACT,
    DEFAULT_REANCHOR_DECISION,
    DEFAULT_STRUCTURE_DECISION,
)

TRAINING_SEEDS = (0, 1, 2)
INFERENCE_NOISE_SEEDS = (100, 101, 102)
SHUFFLE_SEED = 20260824
DEFAULT_TRAINING_UPDATES = 1000
DEFAULT_BATCH_SIZE = 128
DEFAULT_TRAIN_TIMESTEPS = 50
DEFAULT_INFERENCE_STEPS = 10
DEFAULT_BOOTSTRAP_RESAMPLES = 2000
DEFAULT_BOOTSTRAP_SEED = 20260824
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DISPATCH_MANIFEST = (
    REPO_ROOT
    / "runs/eval/dig_act_receding_horizon_dispatch_diagnostic_20260823T184504+0800/input_manifest.json"
)
DEFAULT_IDENTIFIABILITY_DECISION = (
    REPO_ROOT
    / "runs/eval/dig_goal_action_identifiability_precheck_20260823T205439+0800/decision.json"
)


def build_minimal_dp_probe_contract(*, training_updates: int) -> dict[str, Any]:
    if training_updates < 1:
        raise ValueError("minimal DP training updates must be positive")
    return {
        "schema": "minimal_dig_diffusion_probe_contract_v1",
        "status": "pre_registered",
        "default_enabled": False,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "unity_allowed": False,
        "data_identifiability_precheck_passed": False,
        "training_seeds": list(TRAINING_SEEDS),
        "inference_noise_seeds": list(INFERENCE_NOISE_SEEDS),
        "shuffle_seed": SHUFFLE_SEED,
        "reproducibility": {
            "allow_tf32": False,
            "cudnn_benchmark": False,
            "cudnn_deterministic": True,
            "deterministic_algorithms": True,
            "matmul_precision": "highest",
            "cublas_workspace_config": ":4096:8",
        },
        "data": {
            "camera_order": ["stick_up", "stick_down", "eye_left", "eye_right"],
            "camera_preprocessing": "grayscale_32x32_area",
            "low_dim_order": ["qpos", "qvel", "dig_cut_tokens"],
            "low_dim_dim": 18,
            "token_dim": 10,
            "action_horizon": 100,
            "action_dim": 4,
            "source_33_34_used": False,
            "window_random_split": False,
        },
        "training": {
            "updates_per_seed": int(training_updates),
            "batch_size": DEFAULT_BATCH_SIZE,
            "learning_rate": 1.0e-4,
            "weight_decay": 1.0e-5,
            "ema_decay": 0.995,
            "source_then_episode_balanced": True,
            "early_stopping": False,
            "model_selection": False,
        },
        "model": {
            "type": "conditional_temporal_conv_epsilon_predictor",
            "hidden_dim": 64,
            "camera_feature_dim": 16,
        },
        "diffusion": {
            "objective": "epsilon_prediction_mse",
            "train_timesteps": DEFAULT_TRAIN_TIMESTEPS,
            "sampler": "deterministic_ddim_eta_0",
            "inference_steps": DEFAULT_INFERENCE_STEPS,
            "initial_noise_paired_across_token_conditions": True,
        },
        "conditions": [
            "base_correct",
            "alternate_correct",
            "zero",
            "shuffled",
        ],
        "dispatch": {
            "latest_observation_receding_horizon": True,
            "resample_chunk_every_frame": True,
            "query_dispatched": 0,
            "temporal_aggregation": False,
            "cache": False,
        },
        "evaluation": {
            "variant_count": 112,
            "frames_per_variant": 100,
            "short_projection_horizons": [5, 10],
            "failed_100_step_dynamics_used": False,
            "controls": ["zero", "shuffled"],
        },
        "absolute_gates": {
            "direction_success_min": 0.80,
            "ranking_accuracy_min": 0.80,
            "projected_tip_separation_p10_min_m": 0.02,
            "bootstrap_ci95_low_min": 0.0,
            "action_support_rate_delta_max": 0.01,
            "training_seed_consistency_min": 0.80,
            "noise_effect_p95_below_goal_effect_p10": True,
        },
        "hard_boundaries": {
            "act_training_allowed": False,
            "act_modification_allowed": False,
            "soil_model_training_allowed": False,
            "backend_call_allowed": False,
            "unity_start_allowed": False,
            "action_send_allowed": False,
            "temporal_parameter_change_allowed": False,
            "production_default_change_allowed": False,
            "promotion_allowed": False,
            "output_overwrite_allowed": False,
        },
    }


def run_minimal_dp_probe_dry_run(
    *, training_updates: int = DEFAULT_TRAINING_UPDATES, **_: Any
) -> dict[str, Any]:
    return {
        "schema": "minimal_dig_diffusion_probe_dry_run_v1",
        "status": "dry_run",
        "contract": build_minimal_dp_probe_contract(training_updates=training_updates),
        "training_started": False,
        "backend_called": False,
        "unity_started": False,
        "action_sent": False,
        "production_defaults_changed": False,
    }


def run_minimal_dp_probe(**_: Any) -> dict[str, Any]:
    return _run_minimal_dp_probe_impl(**_)


def _run_minimal_dp_probe_impl(
    *,
    output_dir: str | Path,
    dispatch_manifest_path: str | Path = DEFAULT_DISPATCH_MANIFEST,
    identifiability_decision_path: str | Path = DEFAULT_IDENTIFIABILITY_DECISION,
    training_updates: int = DEFAULT_TRAINING_UPDATES,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    device: str = "cuda",
) -> dict[str, Any]:
    contract = build_minimal_dp_probe_contract(training_updates=training_updates)
    _configure_deterministic_runtime()
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "training").mkdir()
    (destination / "evaluation").mkdir()
    write_json_exclusive(destination / "contract.json", contract)
    runtime_git = _git_identity()
    lineage = resolve_minimal_dp_probe_lineage(
        dispatch_manifest_path=dispatch_manifest_path,
        identifiability_decision_path=identifiability_decision_path,
    )
    variants = [
        json.loads(line)
        for line in lineage.base.variants.path.open(encoding="utf-8")
        if line.strip()
    ]
    if len(variants) != 112:
        raise ValueError("minimal DP probe requires exactly 112 frozen variants")
    training_cache_path = destination / "training_cache.npz"
    training_cache_manifest = build_training_window_cache(
        rollout_windows_path=lineage.rollout_windows.path,
        dataset_dir=lineage.base.dataset_dir,
        camera_order=lineage.camera_order,
        output_path=training_cache_path,
        image_size=32,
    )
    training_cache_manifest["identity"] = file_identity(training_cache_path)
    write_json_exclusive(destination / "training_cache.json", training_cache_manifest)
    evaluation_cache_path = destination / "evaluation_cache.npz"
    evaluation_cache_manifest = build_evaluation_observation_cache(
        variants=variants,
        camera_order=lineage.camera_order,
        output_path=evaluation_cache_path,
        image_size=32,
    )
    evaluation_cache_manifest["identity"] = file_identity(evaluation_cache_path)
    write_json_exclusive(
        destination / "evaluation_cache.json", evaluation_cache_manifest
    )
    token_conditions = build_evaluation_token_conditions(
        variants, shuffle_seed=SHUFFLE_SEED
    )
    condition_artifact = {
        "schema": "minimal_dp_evaluation_token_conditions_v1",
        "shuffle_seed": SHUFFLE_SEED,
        "shuffle_shift": int(token_conditions["shuffle_shift"]),
        "shuffle_indices": token_conditions["shuffle_indices"].tolist(),
        "condition_sha256": {
            name: _array_sha256(token_conditions[name])
            for name in (
                "base_correct",
                "alternate_correct",
                "zero",
                "shuffled",
            )
        },
        "zero_token_intentional_out_of_support_control": True,
        "promotion_eligible": False,
    }
    write_json_exclusive(destination / "conditions.json", condition_artifact)
    training_arrays = load_npz_arrays(training_cache_path)
    training_config = MinimalDPTrainingConfig(
        updates=training_updates,
        batch_size=DEFAULT_BATCH_SIZE,
        hidden_dim=64,
        camera_feature_dim=16,
        train_timesteps=DEFAULT_TRAIN_TIMESTEPS,
    )
    training_results = []
    for seed in TRAINING_SEEDS:
        training_results.append(
            train_minimal_dp_seed(
                arrays=training_arrays,
                norm_stats=lineage.norm_stats,
                seed=seed,
                output_dir=destination / "training" / f"seed_{seed}",
                config=training_config,
                device=device,
                lineage={
                    "training_cache": training_cache_manifest["identity"],
                    "rollout_windows": lineage.rollout_windows.as_dict(),
                    "split": lineage.base.split.as_dict(),
                    "stats": lineage.base.stats.as_dict(),
                    "source_33_34_used": False,
                    "data_identifiability_precheck_passed": False,
                },
            )
        )
    write_json_exclusive(
        destination / "training.json",
        {
            "schema": "minimal_dp_three_seed_training_v1",
            "training_seeds": list(TRAINING_SEEDS),
            "results": training_results,
            "same_budget_each_seed": True,
            "early_stopping": False,
            "source_33_34_used": False,
            "promotion_eligible": False,
        },
    )
    del training_arrays
    evaluation_arrays = load_npz_arrays(evaluation_cache_path)
    per_seed_results = []
    action_arrays: dict[str, list[np.ndarray]] = {
        name: [] for name in ("base_correct", "alternate_correct", "zero", "shuffled")
    }
    projection_replicas = []
    trace_path = destination / "evaluation" / "trace.jsonl"
    with trace_path.open("x", encoding="utf-8") as trace_handle:
        for seed in TRAINING_SEEDS:
            model, checkpoint = load_minimal_dp_checkpoint(
                destination / "training" / f"seed_{seed}" / "checkpoint.pt",
                device=device,
            )
            evaluation = evaluate_minimal_dp_model(
                model=model,
                schedule_betas=checkpoint["schedule"]["betas"],
                norm_stats=checkpoint["norm_stats"],
                evaluation_arrays=evaluation_arrays,
                token_conditions=token_conditions,
                variant_records=variants,
                training_seed=seed,
                inference_noise_seeds=INFERENCE_NOISE_SEEDS,
                inference_steps=DEFAULT_INFERENCE_STEPS,
                action_p01=lineage.action_p01,
                action_p99=lineage.action_p99,
                device=device,
                batch_size=256,
                trace_handle=trace_handle,
            )
            dispatched = evaluation.pop("dispatched_actions")
            for name, values in dispatched.items():
                action_arrays[name].append(values)
            for noise_index, noise_seed in enumerate(INFERENCE_NOISE_SEEDS):
                projection_replicas.append(
                    {
                        "training_seed": seed,
                        "inference_noise_seed": noise_seed,
                        "base_correct": dispatched["base_correct"][noise_index],
                        "alternate_correct": dispatched["alternate_correct"][
                            noise_index
                        ],
                    }
                )
            evaluation_npz = destination / "evaluation" / f"seed_{seed}_actions.npz"
            np.savez_compressed(evaluation_npz, **dispatched)
            evaluation["actions_identity"] = file_identity(evaluation_npz)
            write_json_exclusive(
                destination / "evaluation" / f"seed_{seed}.json", evaluation
            )
            per_seed_results.append(evaluation)
            del model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
    stacked_actions = {
        name: np.stack(values, axis=0) for name, values in action_arrays.items()
    }
    distribution = condition_distribution_metrics(
        base_correct=stacked_actions["base_correct"],
        alternate_correct=stacked_actions["alternate_correct"],
        zero=stacked_actions["zero"],
        shuffled=stacked_actions["shuffled"],
        action_std=lineage.norm_stats["action_std"],
    )
    seed_consistency = training_seed_direction_consistency(
        np.mean(
            stacked_actions["alternate_correct"] - stacked_actions["base_correct"],
            axis=1,
        ),
        cosine_threshold=0.5,
    )
    authoritative_lineage = resolve_authoritative_lineage(
        reanchor_decision_path=DEFAULT_REANCHOR_DECISION,
        structure_decision_path=DEFAULT_STRUCTURE_DECISION,
        comparison_artifact_path=DEFAULT_COMPARISON_ARTIFACT,
    )
    projection = project_dp_dispatch_replicas(
        replicas=projection_replicas,
        variants=variants,
        recorded_qpos=evaluation_arrays["qpos"],
        recorded_qvel=evaluation_arrays["qvel"],
        lineage=authoritative_lineage,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
        device="cpu",
    )
    support = {
        name: _dispatched_action_support(
            values,
            lower=lineage.action_p01,
            upper=lineage.action_p99,
        )
        for name, values in stacked_actions.items()
    }
    metrics = {
        "schema": "minimal_dig_diffusion_probe_metrics_v1",
        "status": "completed",
        "valid": True,
        "direction_success": projection["direction_success"],
        "ranking_accuracy": projection["ranking_accuracy"],
        "projected_tip_separation_p10_m": projection["projected_tip_separation_p10_m"],
        "bootstrap_ci95_low": projection["bootstrap"]["joint_margin_ci95_low"],
        "action_support_violation_rate": support["alternate_correct"]["violation_rate"],
        "act_reference_support_violation_rate": (
            lineage.act_reference_support_violation_rate
        ),
        "nonfinite_count": distribution["nonfinite_count"],
        "noise_p95_below_goal_p10": distribution["noise_p95_below_goal_p10"],
        "training_seed_consistent_fraction": seed_consistency["consistent_fraction"],
        "condition_distribution": distribution,
        "training_seed_consistency": seed_consistency,
        "dispatched_action_support": support,
        "raw_chunk_distribution_by_training_seed": [
            result["chunk_distribution"] for result in per_seed_results
        ],
        "data_identifiability_precheck_passed": False,
        "promotion_eligible": False,
    }
    decision = classify_minimal_dp_probe(metrics=metrics, invalid_reasons=())
    write_json_exclusive(destination / "projection.json", projection)
    write_json_exclusive(destination / "metrics.json", metrics)
    plots = write_minimal_dp_probe_plots(
        destination,
        training_histories=training_results,
        metrics=metrics,
    )
    decision["plots"] = plots
    write_json_exclusive(destination / "decision.json", decision)
    input_manifest = {
        "schema": "minimal_dig_diffusion_probe_input_manifest_v1",
        "status": "completed",
        "runtime": {
            "python": sys.version,
            "torch": torch.__version__,
            "device": device,
            "git": runtime_git,
            "reproducibility": contract["reproducibility"],
        },
        "lineage": lineage.as_manifest(),
        "authoritative_projection_lineage": authoritative_lineage.as_manifest(),
        "training_cache": training_cache_manifest,
        "evaluation_cache": evaluation_cache_manifest,
        "conditions": condition_artifact,
        "training_checkpoints": [result["checkpoint"] for result in training_results],
        "evaluation_trace": file_identity(trace_path),
        "code": _code_identities(),
        "training_seeds": list(TRAINING_SEEDS),
        "inference_noise_seeds": list(INFERENCE_NOISE_SEEDS),
        "source_33_34_used": False,
        "act_trained": False,
        "act_modified": False,
        "dp_probe_trained": True,
        "soil_model_trained": False,
        "backend_called": False,
        "unity_started": False,
        "action_sent": False,
        "temporal_aggregation_used": False,
        "temporal_parameters_changed": False,
        "production_defaults_changed": False,
        "promotion_eligible": False,
    }
    write_json_exclusive(destination / "input_manifest.json", input_manifest)
    write_text_exclusive(
        destination / "report.md",
        render_minimal_dp_probe_report(
            metrics=metrics, decision=decision, output_dir=destination
        ),
    )
    return {
        "output_dir": str(destination),
        "decision": decision,
        "metrics": metrics,
    }


def _dispatched_action_support(
    values: np.ndarray, *, lower: np.ndarray, upper: np.ndarray
) -> dict[str, Any]:
    flat = np.asarray(values, dtype=np.float64).reshape(-1, 4)
    finite = np.isfinite(flat).all(axis=1)
    outside = finite & np.any(
        (flat < np.asarray(lower)[None]) | (flat > np.asarray(upper)[None]), axis=1
    )
    return {
        "action_count": int(flat.shape[0]),
        "violation_count": int(np.count_nonzero(outside)),
        "violation_rate": float(np.mean(outside)),
        "nonfinite_count": int(np.count_nonzero(~finite)),
    }


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode())
    digest.update(array.tobytes())
    return digest.hexdigest()


def _git_identity() -> dict[str, Any]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return {
        "head": head,
        "branch": branch,
        "dirty": bool(status),
        "status_entry_count": status.count(b"\x00"),
        "status_sha256": hashlib.sha256(status).hexdigest(),
    }


def _configure_deterministic_runtime() -> None:
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.set_float32_matmul_precision("highest")
    torch.use_deterministic_algorithms(True)


def minimal_dp_probe_code_paths() -> tuple[str, ...]:
    return (
        "testbed/data/camera_images.py",
        "testbed/eval/dig_diffusion_probe_model.py",
        "testbed/eval/dig_diffusion_probe_data.py",
        "testbed/eval/dig_diffusion_probe_training.py",
        "testbed/eval/dig_diffusion_probe_evaluation.py",
        "testbed/eval/dig_diffusion_probe_projection.py",
        "testbed/eval/dig_diffusion_probe_metrics.py",
        "testbed/eval/dig_diffusion_probe_reporting.py",
        "testbed/eval/dig_diffusion_probe_lineage.py",
        "testbed/eval/dig_diffusion_probe_runtime.py",
        "testbed/cli/dig_minimal_diffusion_probe.py",
        "testbed/eval/dig_goal_action_lineage.py",
        "testbed/eval/dig_receding_horizon_artifacts.py",
        "testbed/eval/dig_receding_horizon_lineage.py",
        "testbed/eval/dig_receding_horizon_metrics.py",
        "testbed/eval/dig_receding_horizon_runtime.py",
        "testbed/eval/dig_short_horizon_projection.py",
        "testbed/eval/dig_receding_horizon_projection_runtime.py",
        "testbed/policies/dig_effect_fk.py",
        "testbed/policies/dig_transition_predictor.py",
    )


def _code_identities() -> dict[str, Any]:
    return {
        path: file_identity(REPO_ROOT / path) for path in minimal_dp_probe_code_paths()
    }


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_BOOTSTRAP_RESAMPLES",
    "DEFAULT_BOOTSTRAP_SEED",
    "DEFAULT_DISPATCH_MANIFEST",
    "DEFAULT_IDENTIFIABILITY_DECISION",
    "DEFAULT_INFERENCE_STEPS",
    "DEFAULT_TRAINING_UPDATES",
    "INFERENCE_NOISE_SEEDS",
    "SHUFFLE_SEED",
    "TRAINING_SEEDS",
    "build_minimal_dp_probe_contract",
    "run_minimal_dp_probe",
    "run_minimal_dp_probe_dry_run",
]
