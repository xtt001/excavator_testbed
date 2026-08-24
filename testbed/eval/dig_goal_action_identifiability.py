"""Pure contracts and gates for Dig goal/action supervision identifiability."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

POSITION_SCALE_M = 2.0
LENGTH_SCALE_M = 2.0
DEPTH_SCALE_M = 0.8
PAYLOAD_SCALE_KG = 60.0


@dataclass(frozen=True)
class GoalActionIdentifiabilityContract:
    qpos_max_abs: float = 0.005
    qvel_max_abs: float = 0.02
    full_action_horizon: int = 100
    response_horizon: int = 10
    action_std_fraction: float = 0.05
    required_responsive_fraction: float = 0.80
    same_goal_endpoint_tolerance_m: float = 0.02
    target_endpoint_tolerance_m: float = 0.05
    direction_tolerance: float = 0.05
    length_tolerance_m: float = 0.05
    depth_tolerance_m: float = 0.04
    payload_tolerance_kg: float = 3.0
    translation_magnitudes_m: tuple[float, ...] = (0.10, 0.20)
    translation_magnitude_tolerance_m: float = 0.025
    translation_axis_off_component_max_m: float = 0.025
    entry_exit_translation_mismatch_max_m: float = 0.02
    camera_mean_mae_max: float = 0.10
    camera_mean_correlation_min: float = 0.90
    camera_mean_dhash_max: float = 0.15
    minimum_noise_pairs: int = 30
    minimum_noise_sources: int = 4
    minimum_different_goal_pairs: int = 100
    minimum_different_goal_sources: int = 8
    minimum_covered_variants: int = 100
    minimum_pairs_per_translation_bin: int = 8
    minimum_bootstrap_resamples: int = 100
    excluded_source_episode_ids: tuple[int, ...] = (33, 34)
    metadata_keys: tuple[str, ...] = (
        "controller_epoch",
        "controller_profile",
        "calibration_schema",
    )

    @property
    def required_translation_bins(self) -> tuple[str, ...]:
        return tuple(
            f"{axis}_{sign}_{magnitude}"
            for magnitude in ("0p10m", "0p20m")
            for axis in ("x", "z")
            for sign in ("plus", "minus")
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in self.__dict__.items()
        } | {"required_translation_bins": list(self.required_translation_bins)}


def build_identifiability_contract() -> GoalActionIdentifiabilityContract:
    return GoalActionIdentifiabilityContract()


def same_non_goal_observation(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    contract: GoalActionIdentifiabilityContract,
) -> dict[str, Any]:
    left_qpos = _vector(left.get("qpos"), 4, "left qpos")
    right_qpos = _vector(right.get("qpos"), 4, "right qpos")
    left_qvel = _vector(left.get("qvel"), 4, "left qvel")
    right_qvel = _vector(right.get("qvel"), 4, "right qvel")
    qpos_error = float(np.max(np.abs(left_qpos - right_qpos)))
    qvel_error = float(np.max(np.abs(left_qvel - right_qvel)))
    left_source = int(left.get("source_episode_id", -1))
    right_source = int(right.get("source_episode_id", -1))
    source_allowed = bool(
        left_source == right_source
        and left_source not in contract.excluded_source_episode_ids
    )
    distinct_episode = bool(
        int(left.get("primitive_episode_id", -1))
        != int(right.get("primitive_episode_id", -1))
    )
    metadata_equal = all(
        str(left.get(key, "")) == str(right.get(key, ""))
        and bool(str(left.get(key, "")))
        for key in contract.metadata_keys
    )
    checks = {
        "qpos": qpos_error <= contract.qpos_max_abs + 1.0e-9,
        "qvel": qvel_error <= contract.qvel_max_abs + 1.0e-9,
        "same_allowed_source": source_allowed,
        "distinct_primitive_episode": distinct_episode,
        "metadata_equal": metadata_equal,
    }
    return {
        "matched": bool(all(checks.values())),
        "checks": checks,
        "qpos_max_abs": qpos_error,
        "qvel_max_abs": qvel_error,
        "source_episode_id": left_source if source_allowed else None,
    }


def classify_goal_relation(
    left_token: Sequence[float] | np.ndarray,
    right_token: Sequence[float] | np.ndarray,
    *,
    contract: GoalActionIdentifiabilityContract,
) -> dict[str, Any]:
    left = _vector(left_token, 10, "left token")
    right = _vector(right_token, 10, "right token")
    geometry = _goal_geometry_delta(left, right)
    non_position = _non_position_delta(left, right)
    same_goal = bool(
        geometry["entry_distance_m"] <= contract.same_goal_endpoint_tolerance_m
        and geometry["exit_distance_m"] <= contract.same_goal_endpoint_tolerance_m
        and non_position["direction"] <= contract.direction_tolerance
        and non_position["length_m"] <= contract.length_tolerance_m
        and non_position["depth_m"] <= contract.depth_tolerance_m
        and non_position["payload_kg"] <= contract.payload_tolerance_kg
    )
    if same_goal:
        return {
            "relation": "same_goal",
            "translation_bin": None,
            **geometry,
            "non_position_delta": non_position,
        }
    translation = (geometry["entry_delta_m"] + geometry["exit_delta_m"]) / 2.0
    magnitude = float(np.linalg.norm(translation))
    closest = min(
        contract.translation_magnitudes_m,
        key=lambda value: abs(float(value) - magnitude),
    )
    dominant_axis = int(np.argmax(np.abs(translation)))
    off_axis = float(abs(translation[1 - dominant_axis]))
    target_like = target_token_matches(right, right, contract=contract)["matched"]
    non_position_ok = bool(
        non_position["direction"] <= contract.direction_tolerance
        and non_position["length_m"] <= contract.length_tolerance_m
        and non_position["depth_m"] <= contract.depth_tolerance_m
        and non_position["payload_kg"] <= contract.payload_tolerance_kg
    )
    translation_ok = bool(
        target_like
        and non_position_ok
        and abs(magnitude - closest) <= contract.translation_magnitude_tolerance_m
        and off_axis <= contract.translation_axis_off_component_max_m
        and geometry["translation_mismatch_m"]
        <= contract.entry_exit_translation_mismatch_max_m
    )
    axis = "x" if dominant_axis == 0 else "z"
    sign = "plus" if translation[dominant_axis] >= 0.0 else "minus"
    magnitude_name = "0p10m" if math.isclose(closest, 0.10) else "0p20m"
    return {
        "relation": "position_translation" if translation_ok else "other_goal_change",
        "translation_bin": (
            f"{axis}_{sign}_{magnitude_name}" if translation_ok else None
        ),
        "translation_magnitude_m": magnitude,
        "translation_vector_m": translation.tolist(),
        "off_axis_component_m": off_axis,
        **geometry,
        "non_position_delta": non_position,
    }


def target_token_matches(
    candidate_token: Sequence[float] | np.ndarray,
    target_token: Sequence[float] | np.ndarray,
    *,
    contract: GoalActionIdentifiabilityContract,
) -> dict[str, Any]:
    candidate = _vector(candidate_token, 10, "candidate token")
    target = _vector(target_token, 10, "target token")
    geometry = _goal_geometry_delta(target, candidate)
    non_position = _non_position_delta(target, candidate)
    checks = {
        "entry": geometry["entry_distance_m"] <= contract.target_endpoint_tolerance_m,
        "exit": geometry["exit_distance_m"] <= contract.target_endpoint_tolerance_m,
        "direction": non_position["direction"] <= contract.direction_tolerance,
        "length": non_position["length_m"] <= contract.length_tolerance_m,
        "depth": non_position["depth_m"] <= contract.depth_tolerance_m,
        "payload": non_position["payload_kg"] <= contract.payload_tolerance_kg,
        "valid": bool(candidate[9] > 0.5 and target[9] > 0.5),
    }
    return {
        "matched": bool(all(checks.values())),
        "checks": checks,
        **geometry,
        "non_position_delta": non_position,
    }


def camera_observation_matches(
    value: Mapping[str, Any],
    *,
    contract: GoalActionIdentifiabilityContract,
) -> dict[str, Any]:
    mae = float(value.get("mean_normalised_pixel_mae", float("nan")))
    correlation = float(value.get("mean_pixel_correlation", float("nan")))
    dhash = float(value.get("mean_difference_hash_hamming_fraction", float("nan")))
    checks = {
        "finite": bool(np.isfinite([mae, correlation, dhash]).all()),
        "mae": mae <= contract.camera_mean_mae_max,
        "correlation": correlation >= contract.camera_mean_correlation_min,
        "dhash": dhash <= contract.camera_mean_dhash_max,
    }
    return {
        "matched": bool(all(checks.values())),
        "checks": checks,
        "mean_normalised_pixel_mae": mae,
        "mean_pixel_correlation": correlation,
        "mean_difference_hash_hamming_fraction": dhash,
    }


def action_signal_metrics(
    baseline_actions: np.ndarray,
    alternate_actions: np.ndarray,
    *,
    action_std: Sequence[float] | np.ndarray,
    contract: GoalActionIdentifiabilityContract,
) -> dict[str, Any]:
    baseline = _action_chunk(baseline_actions, contract=contract, label="baseline")
    alternate = _action_chunk(alternate_actions, contract=contract, label="alternate")
    scale = _vector(action_std, 4, "action std")
    if np.any(scale <= 0.0):
        raise ValueError("action std must be positive")
    delta = alternate - baseline
    threshold = scale * contract.action_std_fraction
    responsive = np.any(np.abs(delta) > threshold[None, :], axis=1)
    norms = np.linalg.norm(delta, axis=1)
    first = slice(0, contract.response_horizon)
    return {
        "response_threshold": threshold.tolist(),
        "first_10_responsive_fraction": float(np.mean(responsive[first])),
        "full_100_responsive_fraction": float(np.mean(responsive)),
        "first_10_mean_l2": float(np.mean(norms[first])),
        "first_10_median_l2": float(np.median(norms[first])),
        "full_100_mean_l2": float(np.mean(norms)),
        "per_axis_first_10_responsive_fraction": np.mean(
            np.abs(delta[first]) > threshold[None, :], axis=0
        ).tolist(),
    }


def assess_action_signal(
    metrics: Mapping[str, Any],
    *,
    same_goal_noise_p95: float,
    contract: GoalActionIdentifiabilityContract,
) -> dict[str, Any]:
    noise = float(same_goal_noise_p95)
    response = float(metrics["first_10_responsive_fraction"])
    magnitude = float(metrics["first_10_mean_l2"])
    checks = {
        "noise_finite": bool(math.isfinite(noise) and noise >= 0.0),
        "responsive_fraction": response >= contract.required_responsive_fraction,
        "above_same_goal_noise_p95": magnitude > noise,
    }
    return {
        "passed": bool(all(checks.values())),
        "checks": checks,
        "same_goal_noise_p95": noise,
        "signal_margin_over_noise_p95": magnitude - noise,
    }


def hierarchical_source_episode_signal_bootstrap(
    *,
    signal_pairs: Sequence[Mapping[str, Any]],
    noise_pairs: Sequence[Mapping[str, Any]],
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    if resamples < 100:
        raise ValueError("signal bootstrap requires at least 100 resamples")
    signal = _group_metric_by_source(signal_pairs)
    noise = _group_metric_by_source(noise_pairs)
    common = np.asarray(sorted(set(signal) & set(noise)), dtype=np.int64)
    if common.size < 2:
        raise ValueError("signal bootstrap requires at least two common sources")
    point = float(
        np.mean(
            [float(np.mean(signal[int(s)]) - np.mean(noise[int(s)])) for s in common]
        )
    )
    rng = np.random.default_rng(int(seed))
    samples = np.empty(int(resamples), dtype=np.float64)
    for index in range(int(resamples)):
        sampled_sources = rng.choice(common, size=common.size, replace=True)
        differences = []
        for source_value in sampled_sources:
            source = int(source_value)
            signal_values = signal[source]
            noise_values = noise[source]
            signal_sample = rng.choice(
                signal_values, size=signal_values.size, replace=True
            )
            noise_sample = rng.choice(
                noise_values, size=noise_values.size, replace=True
            )
            differences.append(float(np.mean(signal_sample) - np.mean(noise_sample)))
        samples[index] = float(np.mean(differences))
    return {
        "schema": "dig_goal_action_signal_bootstrap_v1",
        "common_source_count": int(common.size),
        "signal_pair_count": int(sum(value.size for value in signal.values())),
        "noise_pair_count": int(sum(value.size for value in noise.values())),
        "resamples": int(resamples),
        "seed": int(seed),
        "point_difference": point,
        "ci95_low": float(np.quantile(samples, 0.025)),
        "ci95_high": float(np.quantile(samples, 0.975)),
    }


def classify_identifiability_precheck(
    *,
    summary: Mapping[str, Any],
    invalid_reasons: Sequence[str],
    contract: GoalActionIdentifiabilityContract,
) -> dict[str, Any]:
    reasons = tuple(str(value) for value in invalid_reasons if str(value))
    if reasons:
        classification = "invalid_precheck"
        next_experiment = "repair_identifiability_contract_or_lineage"
        checks: dict[str, bool] = {}
        allowed = False
    else:
        bin_counts = {
            str(key): int(value)
            for key, value in _mapping(
                summary.get("translation_bin_counts"), "translation bin counts"
            ).items()
        }
        checks = {
            "same_goal_noise_pair_count": int(summary["same_goal_noise_pair_count"])
            >= contract.minimum_noise_pairs,
            "same_goal_noise_source_count": int(summary["same_goal_noise_source_count"])
            >= contract.minimum_noise_sources,
            "different_goal_pair_count": int(summary["different_goal_pair_count"])
            >= contract.minimum_different_goal_pairs,
            "different_goal_source_count": int(summary["different_goal_source_count"])
            >= contract.minimum_different_goal_sources,
            "covered_variant_count": int(summary["covered_variant_count"])
            >= contract.minimum_covered_variants,
            "planned_variant_count": int(summary["planned_variant_count"]) == 112,
            "all_translation_bins": all(
                bin_counts.get(name, 0) >= contract.minimum_pairs_per_translation_bin
                for name in contract.required_translation_bins
            ),
            "action_signal_pass_fraction": float(summary["action_signal_pass_fraction"])
            >= contract.required_responsive_fraction,
            "bootstrap_positive": float(summary["bootstrap_ci95_low"]) > 0.0,
        }
        allowed = bool(all(checks.values()))
        if allowed:
            classification = "goal_action_supervision_identifiable"
            next_experiment = "fair_act_vs_diffusion_policy_training"
        else:
            classification = "data_supervision_unidentifiable"
            next_experiment = "paired_goal_action_demonstrations"
    return {
        "schema": "dig_goal_action_identifiability_decision_v1",
        "status": "completed",
        "classification": classification,
        "next_experiment": next_experiment,
        "checks": checks,
        "invalid_reasons": list(reasons),
        "act_dp_training_allowed": allowed,
        "act_dp_training_started": False,
        "act_trained": False,
        "diffusion_policy_trained": False,
        "soil_model_trained": False,
        "unity_started": False,
        "action_sent": False,
        "production_defaults_changed": False,
    }


def _goal_geometry_delta(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    left_entry = left[:2] * POSITION_SCALE_M
    left_exit = left[2:4] * POSITION_SCALE_M
    right_entry = right[:2] * POSITION_SCALE_M
    right_exit = right[2:4] * POSITION_SCALE_M
    entry_delta = right_entry - left_entry
    exit_delta = right_exit - left_exit
    return {
        "entry_delta_m": entry_delta,
        "exit_delta_m": exit_delta,
        "entry_distance_m": float(np.linalg.norm(entry_delta)),
        "exit_distance_m": float(np.linalg.norm(exit_delta)),
        "translation_mismatch_m": float(np.linalg.norm(entry_delta - exit_delta)),
    }


def _non_position_delta(left: np.ndarray, right: np.ndarray) -> dict[str, float]:
    return {
        "direction": float(np.linalg.norm(right[4:6] - left[4:6])),
        "length_m": float(abs(right[6] - left[6]) * LENGTH_SCALE_M),
        "depth_m": float(abs(right[7] - left[7]) * DEPTH_SCALE_M),
        "payload_kg": float(abs(right[8] - left[8]) * PAYLOAD_SCALE_KG),
    }


def _action_chunk(
    value: np.ndarray,
    *,
    contract: GoalActionIdentifiabilityContract,
    label: str,
) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if (
        result.shape != (contract.full_action_horizon, 4)
        or not np.isfinite(result).all()
    ):
        raise ValueError(f"{label} actions must be finite [100,4]")
    return result


def _group_metric_by_source(
    rows: Sequence[Mapping[str, Any]],
) -> dict[int, np.ndarray]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        source = int(row["source_episode_id"])
        episode_ids = tuple(int(value) for value in row["primitive_episode_ids"])
        if len(episode_ids) != 2 or episode_ids[0] == episode_ids[1]:
            raise ValueError("signal pairs must bind two distinct episodes")
        value = float(row["first_10_mean_l2"])
        if not math.isfinite(value) or value < 0.0:
            raise ValueError("signal pair metric must be finite and non-negative")
        grouped[source].append(value)
    return {
        source: np.asarray(values, dtype=np.float64)
        for source, values in grouped.items()
    }


def _vector(value: Any, length: int, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64).reshape(-1)
    if result.shape != (length,) or not np.isfinite(result).all():
        raise ValueError(f"{label} must be finite {length}D")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


__all__ = [
    "GoalActionIdentifiabilityContract",
    "action_signal_metrics",
    "assess_action_signal",
    "build_identifiability_contract",
    "camera_observation_matches",
    "classify_goal_relation",
    "classify_identifiability_precheck",
    "hierarchical_source_episode_signal_bootstrap",
    "same_non_goal_observation",
    "target_token_matches",
]
