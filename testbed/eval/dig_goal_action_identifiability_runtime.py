"""Run the default-off, offline-only Dig data identifiability precheck."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from testbed.eval.dig_goal_action_data import (
    enumerate_identifiability_pairs,
    evaluate_variant_demonstration_coverage,
    load_strict_train_episode_starts,
)
from testbed.eval.dig_goal_action_identifiability import (
    assess_action_signal,
    build_identifiability_contract,
    classify_goal_relation,
    classify_identifiability_precheck,
    hierarchical_source_episode_signal_bootstrap,
)
from testbed.eval.dig_goal_action_identifiability_reporting import (
    render_identifiability_report,
    write_identifiability_plots,
)
from testbed.eval.dig_goal_action_lineage import (
    IdentifiabilityLineageError,
    resolve_identifiability_lineage,
)
from testbed.eval.dig_receding_horizon_artifacts import (
    file_identity,
    write_json_exclusive,
    write_jsonl_exclusive,
    write_text_exclusive,
)

PRECHECK_ID = "dig_goal_action_identifiability_precheck_v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DISPATCH_MANIFEST = (
    REPO_ROOT
    / "runs/eval/dig_act_receding_horizon_dispatch_diagnostic_20260823T184504+0800/input_manifest.json"
)
DEFAULT_BOOTSTRAP_RESAMPLES = 2000
DEFAULT_BOOTSTRAP_SEED = 20260823
REQUIRED_ARTIFACTS = (
    "contract.json",
    "input_manifest.json",
    "episode_inventory.json",
    "same_goal_noise.json",
    "pair_candidates.jsonl",
    "variant_coverage.jsonl",
    "summary.json",
    "bootstrap.json",
    "decision.json",
    "report.md",
)


def build_precheck_contract(*, bootstrap_resamples: int) -> dict[str, Any]:
    contract = build_identifiability_contract()
    if bootstrap_resamples < contract.minimum_bootstrap_resamples:
        raise ValueError("identifiability bootstrap budget is too small")
    return {
        "schema": "dig_goal_action_identifiability_contract_v1",
        "precheck_id": PRECHECK_ID,
        "status": "pre_registered",
        "default_enabled": False,
        "diagnostic_only": True,
        "data": {
            "frame_scope": "primitive_t0_only",
            "action_horizon": contract.full_action_horizon,
            "planned_variant_count": 112,
            "source_33_34_used": False,
            "window_random_split": False,
            "goal_token_excluded_from_state_match": True,
        },
        "matching": {
            "qpos_max_abs": contract.qpos_max_abs,
            "qvel_max_abs": contract.qvel_max_abs,
            "same_source_required": True,
            "distinct_primitive_episode_required": True,
            "metadata_keys": list(contract.metadata_keys),
            "camera_mean_mae_max": contract.camera_mean_mae_max,
            "camera_mean_correlation_min": contract.camera_mean_correlation_min,
            "camera_mean_dhash_max": contract.camera_mean_dhash_max,
            "translation_magnitudes_m": list(contract.translation_magnitudes_m),
        },
        "gates": {
            "minimum_same_goal_noise_pairs": contract.minimum_noise_pairs,
            "minimum_same_goal_noise_sources": contract.minimum_noise_sources,
            "minimum_different_goal_pairs": contract.minimum_different_goal_pairs,
            "minimum_different_goal_sources": contract.minimum_different_goal_sources,
            "minimum_covered_variants": contract.minimum_covered_variants,
            "minimum_pairs_per_translation_bin": (
                contract.minimum_pairs_per_translation_bin
            ),
            "required_action_signal_fraction": contract.required_responsive_fraction,
            "bootstrap_ci95_low_min": 0.0,
        },
        "bootstrap": {
            "resamples": int(bootstrap_resamples),
            "grouping": "source_then_episode_pair",
        },
        "hard_boundaries": {
            "act_dp_training_allowed_in_precheck": False,
            "optimizer_creation_allowed": False,
            "backward_allowed": False,
            "soil_model_training_allowed": False,
            "failed_100_step_dynamics_allowed": False,
            "backend_call_allowed": False,
            "unity_start_allowed": False,
            "action_send_allowed": False,
            "temporal_parameter_change_allowed": False,
            "production_default_change_allowed": False,
            "output_overwrite_allowed": False,
        },
        "pure_contract": contract.as_dict(),
        "required_artifacts": list(REQUIRED_ARTIFACTS),
    }


def run_identifiability_dry_run(
    *, bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES, **_: Any
) -> dict[str, Any]:
    return {
        "schema": "dig_goal_action_identifiability_dry_run_v1",
        "status": "dry_run",
        "contract": build_precheck_contract(bootstrap_resamples=bootstrap_resamples),
        "act_dp_training_started": False,
        "optimizer_created": False,
        "backward_called": False,
        "backend_called": False,
        "unity_started": False,
        "action_sent": False,
        "production_defaults_changed": False,
    }


def run_goal_action_identifiability_precheck(
    *,
    output_dir: str | Path,
    dispatch_manifest_path: str | Path = DEFAULT_DISPATCH_MANIFEST,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    contract_payload = build_precheck_contract(bootstrap_resamples=bootstrap_resamples)
    contract = build_identifiability_contract()
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(destination / "contract.json", contract_payload)
    runtime_git = _git_identity()
    try:
        lineage = resolve_identifiability_lineage(dispatch_manifest_path)
        episode_rows, episode_summary = load_strict_train_episode_starts(
            dataset_dir=lineage.dataset_dir,
            split_path=lineage.split.path,
            support_p01=lineage.support_p01,
            support_p99=lineage.support_p99,
            camera_order=lineage.camera_order,
            contract=contract,
        )
        variants = [
            json.loads(line)
            for line in lineage.variants.path.open(encoding="utf-8")
            if line.strip()
        ]
        _validate_frozen_variants(variants, contract=contract)
        pair_inventory = enumerate_identifiability_pairs(
            episode_rows,
            action_std=lineage.action_std,
            contract=contract,
        )
        noise_pairs = pair_inventory["same_goal_pairs"]
        different_pairs = pair_inventory["different_goal_pairs"]
        noise_p95 = (
            float(
                np.quantile(
                    [float(row["first_10_mean_l2"]) for row in noise_pairs], 0.95
                )
            )
            if noise_pairs
            else None
        )
        for row in different_pairs:
            row["action_signal_assessment"] = (
                assess_action_signal(
                    row,
                    same_goal_noise_p95=float(noise_p95),
                    contract=contract,
                )
                if noise_p95 is not None
                else {
                    "passed": False,
                    "checks": {"same_goal_noise_available": False},
                    "same_goal_noise_p95": None,
                    "signal_margin_over_noise_p95": None,
                }
            )
        coverage_rows = [
            evaluate_variant_demonstration_coverage(
                variant,
                episode_rows=episode_rows,
                same_goal_noise_p95=(
                    float(noise_p95) if noise_p95 is not None else float("inf")
                ),
                action_std=lineage.action_std,
                contract=contract,
            )
            for variant in variants
        ]
        bootstrap = _signal_bootstrap(
            signal_pairs=different_pairs,
            noise_pairs=noise_pairs,
            resamples=bootstrap_resamples,
            seed=bootstrap_seed,
        )
        summary = _summary(
            episode_summary=episode_summary,
            noise_pairs=noise_pairs,
            different_pairs=different_pairs,
            pair_audit=pair_inventory["audit"],
            coverage_rows=coverage_rows,
            bootstrap=bootstrap,
            episode_rows=episode_rows,
            lineage=lineage,
            contract=contract,
        )
        decision = classify_identifiability_precheck(
            summary={
                **summary,
                "bootstrap_ci95_low": (
                    float(bootstrap["ci95_low"])
                    if bootstrap.get("ci95_low") is not None
                    else -1.0
                ),
            },
            invalid_reasons=(),
            contract=contract,
        )
        plots = write_identifiability_plots(
            destination,
            summary=summary,
            noise_pairs=noise_pairs,
            signal_pairs=different_pairs,
            coverage_rows=coverage_rows,
        )
        decision["plots"] = plots
        episode_inventory = {
            **episode_summary,
            "rows": [_episode_manifest_row(row) for row in episode_rows],
        }
        input_manifest = {
            "schema": "dig_goal_action_identifiability_input_manifest_v1",
            "status": "completed",
            "precheck_id": PRECHECK_ID,
            "runtime": {
                "python": sys.version,
                "git": runtime_git,
            },
            "source_lineage": lineage.as_manifest(),
            "dataset_episode_files": {
                str(row["primitive_episode_id"]): file_identity(row["dataset_path"])
                for row in episode_rows
            },
            "episode_state_lineage_sha256": _episode_state_lineage_sha256(episode_rows),
            "code": _code_identities(),
            "act_dp_training_started": False,
            "optimizer_created": False,
            "backward_called": False,
            "soil_model_trained": False,
            "backend_called": False,
            "unity_started": False,
            "action_sent": False,
            "temporal_parameters_changed": False,
            "production_defaults_changed": False,
        }
        write_json_exclusive(destination / "input_manifest.json", input_manifest)
        write_json_exclusive(destination / "episode_inventory.json", episode_inventory)
        write_json_exclusive(
            destination / "same_goal_noise.json",
            {
                "schema": "dig_same_goal_action_noise_v1",
                "pair_count": len(noise_pairs),
                "source_count": len(
                    {int(row["source_episode_id"]) for row in noise_pairs}
                ),
                "first_10_mean_l2_p95": noise_p95,
                "pairs": noise_pairs,
            },
        )
        write_jsonl_exclusive(
            destination / "pair_candidates.jsonl",
            [{"pair_type": "same_goal_noise", **row} for row in noise_pairs]
            + [
                {"pair_type": "different_goal_signal", **row} for row in different_pairs
            ],
        )
        write_jsonl_exclusive(destination / "variant_coverage.jsonl", coverage_rows)
        write_json_exclusive(destination / "summary.json", summary)
        write_json_exclusive(destination / "bootstrap.json", bootstrap)
        write_json_exclusive(destination / "decision.json", decision)
        write_text_exclusive(
            destination / "report.md",
            render_identifiability_report(
                summary=summary,
                bootstrap=bootstrap,
                decision=decision,
                output_dir=destination,
            ),
        )
        return {
            "output_dir": str(destination),
            "decision": decision,
            "summary": summary,
            "bootstrap": bootstrap,
        }
    except IdentifiabilityLineageError as exc:
        return _write_invalid_precheck(
            destination=destination,
            reason=str(exc),
            runtime_git=runtime_git,
            contract=contract,
        )


def _summary(
    *,
    episode_summary: dict[str, Any],
    noise_pairs: list[dict[str, Any]],
    different_pairs: list[dict[str, Any]],
    pair_audit: dict[str, Any],
    coverage_rows: list[dict[str, Any]],
    bootstrap: dict[str, Any],
    episode_rows: list[dict[str, Any]],
    lineage: Any,
    contract: Any,
) -> dict[str, Any]:
    passing_signal = [
        row
        for row in different_pairs
        if bool(row["action_signal_assessment"]["passed"])
    ]
    covered = [row for row in coverage_rows if bool(row["covered"])]
    bin_counts = Counter(
        str(row["translation_bin"]) for row in covered if row["translation_bin"]
    )
    action_support = _training_action_support(
        episode_rows,
        p01=lineage.action_p01,
        p99=lineage.action_p99,
    )
    variant_demo_funnel = {
        "variants_with_reference_episode": sum(
            row["reason"] != "reference_episode_missing" for row in coverage_rows
        ),
        "variants_with_any_base_demo": sum(
            int(row["base_demo_count"]) > 0 for row in coverage_rows
        ),
        "variants_with_any_alternate_demo": sum(
            int(row["alternate_demo_count"]) > 0 for row in coverage_rows
        ),
        "base_state_matched_candidates": sum(
            int(row.get("base_demo_funnel", {}).get("state_matched", 0))
            for row in coverage_rows
        ),
        "alternate_state_matched_candidates": sum(
            int(row.get("alternate_demo_funnel", {}).get("state_matched", 0))
            for row in coverage_rows
        ),
        "base_target_matched_candidates": sum(
            int(row.get("base_demo_funnel", {}).get("target_matched", 0))
            for row in coverage_rows
        ),
        "alternate_target_matched_candidates": sum(
            int(row.get("alternate_demo_funnel", {}).get("target_matched", 0))
            for row in coverage_rows
        ),
    }
    return {
        "schema": "dig_goal_action_identifiability_summary_v1",
        "status": "completed",
        "eligible_episode_count": int(episode_summary["eligible_episode_count"]),
        "eligible_source_count": len(episode_summary["eligible_source_episode_ids"]),
        "same_goal_noise_pair_count": len(noise_pairs),
        "same_goal_noise_source_count": len(
            {int(row["source_episode_id"]) for row in noise_pairs}
        ),
        "different_goal_pair_count": len(different_pairs),
        "different_goal_source_count": len(
            {int(row["source_episode_id"]) for row in different_pairs}
        ),
        "different_goal_action_signal_pass_count": len(passing_signal),
        "action_signal_pass_fraction": (
            len(passing_signal) / len(different_pairs) if different_pairs else 0.0
        ),
        "covered_variant_count": len(covered),
        "planned_variant_count": len(coverage_rows),
        "translation_bin_counts": {
            name: int(bin_counts.get(name, 0))
            for name in contract.required_translation_bins
        },
        "pair_funnel": dict(pair_audit),
        "variant_demo_funnel": variant_demo_funnel,
        "bootstrap_ci95_low": bootstrap.get("ci95_low"),
        "bootstrap_ci95_high": bootstrap.get("ci95_high"),
        "training_action_support": action_support,
        "source_33_34_used": False,
        "window_random_split": False,
        "act_dp_training_started": False,
        "unity_started": False,
        "production_defaults_changed": False,
    }


def _signal_bootstrap(
    *,
    signal_pairs: list[dict[str, Any]],
    noise_pairs: list[dict[str, Any]],
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    try:
        return hierarchical_source_episode_signal_bootstrap(
            signal_pairs=signal_pairs,
            noise_pairs=noise_pairs,
            resamples=resamples,
            seed=seed,
        )
    except ValueError as exc:
        return {
            "schema": "dig_goal_action_signal_bootstrap_v1",
            "status": "insufficient_pairs",
            "reason": str(exc),
            "common_source_count": len(
                {int(row["source_episode_id"]) for row in signal_pairs}
                & {int(row["source_episode_id"]) for row in noise_pairs}
            ),
            "signal_pair_count": len(signal_pairs),
            "noise_pair_count": len(noise_pairs),
            "resamples": resamples,
            "seed": seed,
            "point_difference": None,
            "ci95_low": None,
            "ci95_high": None,
        }


def _training_action_support(
    rows: list[dict[str, Any]], *, p01: np.ndarray, p99: np.ndarray
) -> dict[str, Any]:
    actions = np.concatenate([np.asarray(row["actions"]) for row in rows], axis=0)
    outside = (actions < np.asarray(p01)[None, :]) | (
        actions > np.asarray(p99)[None, :]
    )
    row_violation = np.any(outside, axis=1)
    return {
        "action_count": int(actions.shape[0]),
        "support_violation_count": int(np.count_nonzero(row_violation)),
        "support_violation_rate": float(np.mean(row_violation)),
        "support_violation_by_axis": np.count_nonzero(outside, axis=0).tolist(),
        "nonfinite_count": int(np.count_nonzero(~np.isfinite(actions).all(axis=1))),
    }


def _validate_frozen_variants(variants: list[dict[str, Any]], *, contract: Any) -> None:
    if len(variants) != 112:
        raise IdentifiabilityLineageError("frozen_variant_count_mismatch")
    for value in variants:
        if int(value["source_episode_id"]) in contract.excluded_source_episode_ids:
            raise IdentifiabilityLineageError("source_33_34_in_frozen_variants")
        relation = classify_goal_relation(
            value["base_token"], value["variant_token"], contract=contract
        )
        if relation["relation"] != "position_translation":
            raise IdentifiabilityLineageError("frozen_variant_relation_mismatch")


def _episode_manifest_row(row: dict[str, Any]) -> dict[str, Any]:
    signature = row["image_signature"]
    return {
        "source_episode_id": int(row["source_episode_id"]),
        "primitive_episode_id": int(row["primitive_episode_id"]),
        "dataset_path": row["dataset_path"],
        "controller_epoch": row["controller_epoch"],
        "controller_profile": row["controller_profile"],
        "calibration_schema": row["calibration_schema"],
        "qpos_sha256": _array_sha256(row["qpos"]),
        "qvel_sha256": _array_sha256(row["qvel"]),
        "token_sha256": _array_sha256(row["token"]),
        "actions_sha256": _array_sha256(row["actions"]),
        "images_sha256": _array_sha256(signature["rgb_64x64"]),
        "image_hash_sha256": _array_sha256(signature["difference_hash"]),
    }


def _episode_state_lineage_sha256(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        [_episode_manifest_row(row) for row in rows],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _array_sha256(value: Any) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode())
    digest.update(array.tobytes())
    return digest.hexdigest()


def _write_invalid_precheck(
    *, destination: Path, reason: str, runtime_git: dict[str, Any], contract: Any
) -> dict[str, Any]:
    summary = {
        "schema": "dig_goal_action_identifiability_summary_v1",
        "status": "invalid",
        "invalid_reason": reason,
    }
    bootstrap = {
        "schema": "dig_goal_action_signal_bootstrap_v1",
        "status": "not_run_invalid_precheck",
        "ci95_low": None,
        "ci95_high": None,
    }
    decision = classify_identifiability_precheck(
        summary={}, invalid_reasons=(reason,), contract=contract
    )
    empty_json = {
        "schema": "dig_goal_action_identifiability_empty_v1",
        "status": "invalid",
        "reason": reason,
    }
    for name, payload in (
        ("input_manifest.json", {**empty_json, "runtime": {"git": runtime_git}}),
        ("episode_inventory.json", empty_json),
        ("same_goal_noise.json", empty_json),
        ("summary.json", summary),
        ("bootstrap.json", bootstrap),
        ("decision.json", decision),
    ):
        write_json_exclusive(destination / name, payload)
    write_jsonl_exclusive(destination / "pair_candidates.jsonl", [])
    write_jsonl_exclusive(destination / "variant_coverage.jsonl", [])
    write_text_exclusive(
        destination / "report.md",
        "# Dig goal/action 数据可辨识性预检\n\n"
        f"预检无效：`{reason}`。没有启动 ACT/DP 训练、Unity 或动作发送。",
    )
    return {"output_dir": str(destination), "decision": decision}


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


def precheck_code_paths() -> tuple[str, ...]:
    return (
        "testbed/data/camera_images.py",
        "testbed/eval/dig_goal_action_identifiability.py",
        "testbed/eval/dig_goal_action_data.py",
        "testbed/eval/dig_goal_action_lineage.py",
        "testbed/eval/dig_goal_action_identifiability_reporting.py",
        "testbed/eval/dig_goal_action_identifiability_runtime.py",
        "testbed/eval/dig_receding_horizon_artifacts.py",
        "testbed/cli/dig_goal_action_identifiability_precheck.py",
    )


def _code_identities() -> dict[str, Any]:
    return {path: file_identity(REPO_ROOT / path) for path in precheck_code_paths()}


__all__ = [
    "DEFAULT_BOOTSTRAP_RESAMPLES",
    "DEFAULT_BOOTSTRAP_SEED",
    "DEFAULT_DISPATCH_MANIFEST",
    "PRECHECK_ID",
    "build_precheck_contract",
    "precheck_code_paths",
    "run_goal_action_identifiability_precheck",
    "run_identifiability_dry_run",
]
