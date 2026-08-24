"""Orchestrate the opt-in, offline-only Dig ACT dispatch diagnostic."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import torch

from testbed.eval.dig_receding_horizon_artifacts import (
    FIXED_ARTIFACT_PATHS,
    create_no_overwrite_output_root,
    file_identity,
    write_json_exclusive,
    write_jsonl_exclusive,
    write_text_exclusive,
)
from testbed.eval.dig_receding_horizon_data import (
    load_and_select_supported_variants,
)
from testbed.eval.dig_receding_horizon_inference import (
    collect_frozen_act_dispatch_pairs,
)
from testbed.eval.dig_receding_horizon_lineage import (
    DiagnosticLineageError,
    require_complete_lineage,
    resolve_authoritative_lineage,
)
from testbed.eval.dig_receding_horizon_metrics import (
    classify_dispatch_diagnostic,
    hierarchical_paired_source_episode_bootstrap,
)
from testbed.eval.dig_receding_horizon_projection_runtime import (
    project_dispatch_pairs,
)
from testbed.eval.dig_receding_horizon_reporting import (
    aggregate_pair_metrics,
    render_report,
    write_diagnostic_plots,
)

DIAGNOSTIC_ID = "dig_act_receding_horizon_dispatch_diagnostic_v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_ROOT = (
    REPO_ROOT / "runs/eval/dig_token_swap_effect_consistency_20260822T150051+0800"
)
AUTHORITATIVE_BASE = HISTORY_ROOT / "predictor_source_grouped_v1/bucket_only_v1"
DEFAULT_REANCHOR_DECISION = AUTHORITATIVE_BASE / "reanchor_eval_v2/decision.json"
DEFAULT_STRUCTURE_DECISION = (
    AUTHORITATIVE_BASE / "structure_comparison_full_v1/decision.json"
)
DEFAULT_COMPARISON_ARTIFACT = AUTHORITATIVE_BASE / "comparison_full_v1/artifact.json"
DEFAULT_VARIANT_COUNT = 112
DEFAULT_BOOTSTRAP_RESAMPLES = 2000
DEFAULT_BOOTSTRAP_SEED = 20260823


def build_diagnostic_contract(
    *, variant_count: int, bootstrap_resamples: int
) -> dict[str, Any]:
    if variant_count < 100:
        raise ValueError("Dig dispatch diagnostic requires at least 100 variants")
    if bootstrap_resamples < 100:
        raise ValueError(
            "Dig dispatch diagnostic requires at least 100 bootstrap resamples"
        )
    return {
        "schema": "dig_act_receding_horizon_dispatch_contract_v1",
        "diagnostic_id": DIAGNOSTIC_ID,
        "status": "pre_registered",
        "enabled_by_default": False,
        "diagnostic_only": True,
        "request_local": True,
        "promotion_eligible": False,
        "dispatch_strategies": {
            "legacy": {
                "api": "ACTAdapter.predict",
                "semantics": "resolved_current_legacy_temporal_aggregation",
                "default_behaviour_changed": False,
            },
            "latest": {
                "api": "ACTAdapter.predict_action_chunk.first_action_each_frame",
                "old_chunk_contribution_allowed": False,
                "goal_sha_change_resets_cache": True,
                "default_enabled": False,
                "request_local": True,
                "diagnostic_only": True,
                "promotion_eligible": False,
            },
        },
        "data": {
            "variant_count": int(variant_count),
            "minimum_variant_count": 100,
            "variant_type": "position_translation",
            "dispatch_observation_frames_per_variant": 100,
            "one_variant_per_primitive_episode": True,
            "minimum_full_support_episodes_per_source": 8,
            "source_episode_grouped": True,
            "window_random_split": False,
            "source_33_34_used": False,
            "baseline_alternate_share_recorded_observation": True,
        },
        "projection": {
            "evidence_kind": "short_horizon_projection_only",
            "horizons": [5, 10],
            "recorded_state_anchor_count_per_variant": 91,
            "long_horizon_100_step_allowed": False,
            "unity_or_real_trajectory_claim_allowed": False,
            "soil_effect_claim_allowed": False,
            "training_or_tuning_allowed": False,
        },
        "thresholds": {
            "latest_direction_success_min": 0.8,
            "latest_ranking_accuracy_min": 0.8,
            "latest_improvement_min_fraction": 0.15,
            "latest_projected_tip_separation_p10_min_m": 0.02,
            "action_support_violation_rate_delta_max": 0.01,
            "bootstrap_ci95_low_min": 0.0,
        },
        "bootstrap": {
            "resamples": int(bootstrap_resamples),
            "pairing": "source_then_episode_with_replacement",
        },
        "hard_boundaries": {
            "optimizer_creation_allowed": False,
            "backward_allowed": False,
            "checkpoint_modification_allowed": False,
            "act_training_allowed": False,
            "soil_model_training_allowed": False,
            "backend_call_allowed": False,
            "unity_start_allowed": False,
            "action_send_allowed": False,
            "production_default_change_allowed": False,
            "output_overwrite_allowed": False,
        },
        "required_artifacts": list(FIXED_ARTIFACT_PATHS),
    }


def run_diagnostic_dry_run(
    *,
    variant_count: int = DEFAULT_VARIANT_COUNT,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    **_: Any,
) -> dict[str, Any]:
    return {
        "schema": "dig_act_receding_horizon_dispatch_dry_run_v1",
        "status": "dry_run",
        "contract": build_diagnostic_contract(
            variant_count=variant_count,
            bootstrap_resamples=bootstrap_resamples,
        ),
        "optimizer_created": False,
        "backward_called": False,
        "backend_called": False,
        "unity_started": False,
        "action_sent": False,
        "production_defaults_changed": False,
    }


def run_offline_dispatch_diagnostic(
    *,
    output_dir: str | Path,
    reanchor_decision_path: str | Path = DEFAULT_REANCHOR_DECISION,
    structure_decision_path: str | Path = DEFAULT_STRUCTURE_DECISION,
    comparison_artifact_path: str | Path = DEFAULT_COMPARISON_ARTIFACT,
    variant_count: int = DEFAULT_VARIANT_COUNT,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    device: str = "cuda",
    projection_device: str = "cpu",
) -> dict[str, Any]:
    """Execute the diagnostic without importing or calling any backend."""
    contract = build_diagnostic_contract(
        variant_count=variant_count,
        bootstrap_resamples=bootstrap_resamples,
    )
    runtime_git = _git_identity()
    _configure_deterministic_inference()
    destination = create_no_overwrite_output_root(output_dir)
    write_json_exclusive(destination / "contract.json", contract)
    try:
        lineage = resolve_authoritative_lineage(
            reanchor_decision_path=reanchor_decision_path,
            structure_decision_path=structure_decision_path,
            comparison_artifact_path=comparison_artifact_path,
        )
        selected = load_and_select_supported_variants(
            lineage, count=variant_count, horizon=100
        )
        write_jsonl_exclusive(destination / "variants.jsonl", selected)
        dataset_files = {
            str(row["primitive_episode_id"]): file_identity(row["dataset_path"])
            for row in selected
        }
        pairs, traces, collection = collect_frozen_act_dispatch_pairs(
            lineage=lineage,
            variants=selected,
            device=device,
        )
        write_jsonl_exclusive(destination / "legacy/trace.jsonl", traces["legacy"])
        write_jsonl_exclusive(destination / "latest/trace.jsonl", traces["latest"])
        projected, projection_runtime = project_dispatch_pairs(
            pairs,
            lineage=lineage,
            device=projection_device,
        )
        pair_metrics, bootstrap_rows, invalid_reasons = aggregate_pair_metrics(
            pairs=projected,
            traces=traces,
            collection=collection,
            short_horizon_gate=lineage.short_horizon_gate,
        )
        try:
            require_complete_lineage(
                {
                    "checkpoint": lineage.checkpoint.as_dict(),
                    "stats": lineage.stats.as_dict(),
                    "support": lineage.support.as_dict(),
                    "token_order": lineage.token_order,
                    "observation_order": lineage.low_dim_order,
                    "camera_order": lineage.camera_order,
                    "state_lineage_sha256": collection["state_lineage_sha256"],
                }
            )
        except DiagnosticLineageError as exc:
            invalid_reasons += (str(exc),)
            pair_metrics["valid"] = False
            pair_metrics["invalid_reasons"] = list(invalid_reasons)
        bootstrap = hierarchical_paired_source_episode_bootstrap(
            bootstrap_rows,
            metrics=(
                "direction_success",
                "ranking_accuracy",
                "projected_tip_separation_m",
            ),
            resamples=bootstrap_resamples,
            seed=bootstrap_seed,
        )
        decision = classify_dispatch_diagnostic(
            pair_metrics=pair_metrics,
            bootstrap=bootstrap,
            invalid_reasons=invalid_reasons,
        )
        write_json_exclusive(destination / "pair_metrics.json", pair_metrics)
        write_json_exclusive(destination / "bootstrap.json", bootstrap)
        variants_identity = file_identity(destination / "variants.jsonl")
        input_manifest = {
            "schema": "dig_act_receding_horizon_dispatch_input_manifest_v1",
            "status": "completed",
            "diagnostic_id": DIAGNOSTIC_ID,
            "runtime": {
                "python": sys.version,
                "torch": torch.__version__,
                "git": runtime_git,
                "device": device,
                "projection_device": projection_device,
                "deterministic": {
                    "allow_tf32": False,
                    "cudnn_benchmark": False,
                },
            },
            "authoritative_lineage": lineage.as_manifest(),
            "selected_variants": variants_identity,
            "selected_variant_count": len(selected),
            "selected_source_counts": {
                str(key): value
                for key, value in sorted(
                    Counter(int(row["source_episode_id"]) for row in selected).items()
                )
            },
            "dataset_episode_files": dataset_files,
            "state_lineage_sha256": collection["state_lineage_sha256"],
            "collection": collection,
            "projection_runtime": projection_runtime,
            "code": _code_identities(),
            "evidence_boundary": {
                "teacher_forced_recorded_observation": True,
                "short_horizon_projection_only": True,
                "unity_or_real_trajectory": False,
                "soil_effect": False,
                "closed_loop_goal_following": False,
                "production_proof": False,
            },
            "act_trained": False,
            "act_checkpoint_modified": False,
            "optimizer_created": False,
            "backward_called": False,
            "backend_called": False,
            "unity_started": False,
            "action_sent": False,
            "production_defaults_changed": False,
        }
        write_json_exclusive(destination / "input_manifest.json", input_manifest)
        plots = write_diagnostic_plots(destination, pair_metrics=pair_metrics)
        decision["plots"] = plots
        write_json_exclusive(destination / "decision.json", decision)
        report = render_report(
            pair_metrics=pair_metrics,
            bootstrap=bootstrap,
            decision=decision,
            output_dir=destination,
        )
        write_text_exclusive(destination / "report.md", report)
        return {
            "output_dir": str(destination),
            "decision": decision,
            "pair_metrics": pair_metrics,
            "bootstrap": bootstrap,
        }
    except DiagnosticLineageError as exc:
        return _write_invalid_diagnostic(
            destination=destination,
            reason=str(exc),
            runtime_git=runtime_git,
        )


def _write_invalid_diagnostic(
    *, destination: Path, reason: str, runtime_git: dict[str, Any]
) -> dict[str, Any]:
    for relative in ("variants.jsonl", "legacy/trace.jsonl", "latest/trace.jsonl"):
        path = destination / relative
        if not path.exists():
            write_jsonl_exclusive(path, [])
    pair_metrics = {
        "schema": "dig_act_receding_horizon_pair_metrics_v1",
        "status": "invalid",
        "valid": False,
        "invalid_reasons": [reason],
        "by_source": {},
        "by_episode": {},
        "by_variant": [],
    }
    bootstrap = {
        "schema": "dig_dispatch_paired_source_episode_bootstrap_v1",
        "status": "not_run_invalid_diagnostic",
        "metrics": {},
    }
    decision = classify_dispatch_diagnostic(
        pair_metrics=pair_metrics,
        bootstrap=bootstrap,
        invalid_reasons=(reason,),
    )
    for name, payload in (
        ("pair_metrics.json", pair_metrics),
        ("bootstrap.json", bootstrap),
        ("decision.json", decision),
        (
            "input_manifest.json",
            {
                "schema": "dig_act_receding_horizon_dispatch_input_manifest_v1",
                "status": "invalid",
                "invalid_reason": reason,
                "runtime": {"git": runtime_git, "python": sys.version},
                "optimizer_created": False,
                "backend_called": False,
                "unity_started": False,
                "action_sent": False,
            },
        ),
    ):
        path = destination / name
        if not path.exists():
            write_json_exclusive(path, payload)
    report_path = destination / "report.md"
    if not report_path.exists():
        write_text_exclusive(
            report_path,
            "# Dig ACT dispatch 离线诊断\n\n"
            f"诊断无效：`{reason}`。没有训练 ACT，没有启动 Unity，也没有发送动作。",
        )
    return {"output_dir": str(destination), "decision": decision}


def _configure_deterministic_inference() -> None:
    if hasattr(torch.backends, "cuda"):
        torch.backends.cuda.matmul.allow_tf32 = False
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
    torch.set_float32_matmul_precision("highest")


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


def _code_identities() -> dict[str, Any]:
    return {
        relative: file_identity(REPO_ROOT / relative)
        for relative in diagnostic_code_paths()
    }


def diagnostic_code_paths() -> tuple[str, ...]:
    """List every direct source dependency that must be content-hash locked."""
    return (
        "testbed/policies/act/adapter.py",
        "testbed/policies/act/detr/main.py",
        "testbed/policies/act/inference.py",
        "testbed/data/camera_images.py",
        "testbed/data/operator_first_v2_2.py",
        "testbed/eval/dig_effect_state.py",
        "testbed/eval/temporal_dispatch_contract.py",
        "testbed/policies/dig_effect_fk.py",
        "testbed/policies/dig_transition_predictor.py",
        "testbed/eval/dig_receding_horizon_artifacts.py",
        "testbed/eval/dig_receding_horizon_dispatch.py",
        "testbed/eval/dig_receding_horizon_lineage.py",
        "testbed/eval/dig_receding_horizon_data.py",
        "testbed/eval/dig_receding_horizon_inference.py",
        "testbed/eval/dig_short_horizon_projection.py",
        "testbed/eval/dig_receding_horizon_projection_runtime.py",
        "testbed/eval/dig_receding_horizon_metrics.py",
        "testbed/eval/dig_receding_horizon_reporting.py",
        "testbed/eval/dig_receding_horizon_runtime.py",
        "testbed/cli/dig_act_receding_horizon_dispatch_diagnostic.py",
    )


__all__ = [
    "DEFAULT_BOOTSTRAP_RESAMPLES",
    "DEFAULT_BOOTSTRAP_SEED",
    "DEFAULT_COMPARISON_ARTIFACT",
    "DEFAULT_REANCHOR_DECISION",
    "DEFAULT_STRUCTURE_DECISION",
    "DEFAULT_VARIANT_COUNT",
    "DIAGNOSTIC_ID",
    "build_diagnostic_contract",
    "diagnostic_code_paths",
    "run_diagnostic_dry_run",
    "run_offline_dispatch_diagnostic",
]
