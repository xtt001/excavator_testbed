"""Strict-train episode-start data for Dig goal/action identifiability."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import cv2
import h5py
import numpy as np
import yaml

from testbed.data.camera_images import read_camera_rgb
from testbed.eval.dig_goal_action_identifiability import (
    GoalActionIdentifiabilityContract,
    action_signal_metrics,
    assess_action_signal,
    camera_observation_matches,
    classify_goal_relation,
    same_non_goal_observation,
    target_token_matches,
)

CameraMetricFn = Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]


def enumerate_identifiability_pairs(
    episode_rows: Sequence[Mapping[str, Any]],
    *,
    action_std: np.ndarray,
    contract: GoalActionIdentifiabilityContract,
    camera_metric_fn: CameraMetricFn | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Enumerate one t0 pair per unordered primitive-episode pair."""
    camera_fn = (
        camera_signature_metrics if camera_metric_fn is None else camera_metric_fn
    )
    rows = list(episode_rows)
    noise: list[dict[str, Any]] = []
    signal: list[dict[str, Any]] = []
    audit: Counter[str] = Counter()
    for left_index, left in enumerate(rows):
        for right in rows[left_index + 1 :]:
            audit["total_unordered_episode_pairs"] += 1
            state = same_non_goal_observation(left, right, contract=contract)
            state_checks = state["checks"]
            if all(
                state_checks[name]
                for name in (
                    "same_allowed_source",
                    "distinct_primitive_episode",
                    "metadata_equal",
                )
            ):
                audit["source_metadata_episode_matched"] += 1
            if not state["matched"]:
                continue
            audit["mechanical_state_matched"] += 1
            camera = camera_observation_matches(
                camera_fn(left, right), contract=contract
            )
            if not camera["matched"]:
                continue
            audit["camera_matched"] += 1
            relation = classify_goal_relation(
                left["token"], right["token"], contract=contract
            )
            if relation["relation"] not in {"same_goal", "position_translation"}:
                audit["other_goal_relation"] += 1
                continue
            action = action_signal_metrics(
                left["actions"],
                right["actions"],
                action_std=action_std,
                contract=contract,
            )
            record = {
                "source_episode_id": int(left["source_episode_id"]),
                "primitive_episode_ids": [
                    int(left["primitive_episode_id"]),
                    int(right["primitive_episode_id"]),
                ],
                "state_match": _jsonable(state),
                "camera_match": _jsonable(camera),
                "goal_relation": _jsonable(relation),
                "translation_bin": relation["translation_bin"],
                **action,
            }
            if relation["relation"] == "same_goal":
                audit["same_goal_relation"] += 1
                noise.append(record)
            else:
                audit["position_translation_relation"] += 1
                signal.append(record)
    return {
        "same_goal_pairs": noise,
        "different_goal_pairs": signal,
        "audit": {
            name: int(audit.get(name, 0))
            for name in (
                "total_unordered_episode_pairs",
                "source_metadata_episode_matched",
                "mechanical_state_matched",
                "camera_matched",
                "same_goal_relation",
                "position_translation_relation",
                "other_goal_relation",
            )
        },
    }


def evaluate_variant_demonstration_coverage(
    variant: Mapping[str, Any],
    *,
    episode_rows: Sequence[Mapping[str, Any]],
    same_goal_noise_p95: float,
    action_std: np.ndarray,
    contract: GoalActionIdentifiabilityContract,
    camera_metric_fn: CameraMetricFn | None = None,
) -> dict[str, Any]:
    """Require demonstrations for both frozen targets near one reference state."""
    camera_fn = (
        camera_signature_metrics if camera_metric_fn is None else camera_metric_fn
    )
    reference_id = int(variant["primitive_episode_id"])
    reference = next(
        (
            row
            for row in episode_rows
            if int(row["primitive_episode_id"]) == reference_id
        ),
        None,
    )
    relation = classify_goal_relation(
        variant["base_token"], variant["variant_token"], contract=contract
    )
    if reference is None:
        return _empty_variant_coverage(variant, relation, "reference_episode_missing")
    base_demos, base_funnel = _target_demonstrations(
        reference=reference,
        candidates=episode_rows,
        target_token=variant["base_token"],
        contract=contract,
        camera_metric_fn=camera_fn,
    )
    alternate_demos, alternate_funnel = _target_demonstrations(
        reference=reference,
        candidates=episode_rows,
        target_token=variant["variant_token"],
        contract=contract,
        camera_metric_fn=camera_fn,
    )
    passing_pairs = []
    evaluated_pair_count = 0
    for baseline in base_demos:
        for alternate in alternate_demos:
            if int(baseline["primitive_episode_id"]) == int(
                alternate["primitive_episode_id"]
            ):
                continue
            evaluated_pair_count += 1
            metrics = action_signal_metrics(
                baseline["actions"],
                alternate["actions"],
                action_std=action_std,
                contract=contract,
            )
            assessment = assess_action_signal(
                metrics,
                same_goal_noise_p95=same_goal_noise_p95,
                contract=contract,
            )
            if assessment["passed"]:
                passing_pairs.append(
                    {
                        "primitive_episode_ids": [
                            int(baseline["primitive_episode_id"]),
                            int(alternate["primitive_episode_id"]),
                        ],
                        "source_episode_id": int(reference["source_episode_id"]),
                        **metrics,
                        "assessment": assessment,
                    }
                )
    return {
        "variant_id": str(variant["variant_id"]),
        "source_episode_id": int(variant["source_episode_id"]),
        "reference_primitive_episode_id": reference_id,
        "translation_bin": relation["translation_bin"],
        "base_demo_count": len(base_demos),
        "alternate_demo_count": len(alternate_demos),
        "base_demo_funnel": base_funnel,
        "alternate_demo_funnel": alternate_funnel,
        "evaluated_pair_count": evaluated_pair_count,
        "passing_pair_count": len(passing_pairs),
        "covered": bool(passing_pairs),
        "passing_pairs": passing_pairs,
        "reason": None
        if passing_pairs
        else "paired_goal_action_demo_missing_or_inactive",
    }


def load_strict_train_episode_starts(
    *,
    dataset_dir: str | Path,
    split_path: str | Path,
    support_p01: np.ndarray,
    support_p99: np.ndarray,
    camera_order: Sequence[str],
    contract: GoalActionIdentifiabilityContract,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load one source-grouped t0 row with complete 100-step supervision."""
    dataset = Path(dataset_dir).expanduser().resolve(strict=True)
    split_file = Path(split_path).expanduser().resolve(strict=True)
    split = yaml.safe_load(split_file.read_text(encoding="utf-8"))
    train_ids = [int(value) for value in split["train_ids"]]
    source_by_episode = {
        int(key): int(value)
        for key, value in split["source_episode_id_by_primitive_episode_id"].items()
    }
    lower = np.asarray(support_p01, dtype=np.float64).reshape(-1)
    upper = np.asarray(support_p99, dtype=np.float64).reshape(-1)
    if lower.shape != (18,) or upper.shape != (18,) or np.any(lower > upper):
        raise ValueError("identifiability support bounds must be valid 18D")
    rows = []
    rejections: Counter[str] = Counter()
    for episode_id in train_ids:
        source_id = source_by_episode[episode_id]
        if source_id in contract.excluded_source_episode_ids:
            rejections["excluded_source_33_34"] += 1
            continue
        path = dataset / f"episode_{episode_id}.hdf5"
        with h5py.File(path, "r") as handle:
            metadata = dict(handle["metadata"].attrs) if "metadata" in handle else {}
            if str(metadata.get("training_tier", "")) != "gold":
                rejections["training_tier_not_gold"] += 1
                continue
            if handle["action"].shape[0] < contract.full_action_horizon:
                rejections["short_episode"] += 1
                continue
            action_mask = np.asarray(
                handle["v2/step/action_loss_mask"][: contract.full_action_horizon],
                dtype=np.uint8,
            )
            if action_mask.shape != (contract.full_action_horizon,) or not np.all(
                action_mask == 1
            ):
                rejections["incomplete_action_supervision"] += 1
                continue
            qpos = np.asarray(handle["observations/qpos"][0], dtype=np.float32)
            qvel = np.asarray(handle["observations/qvel"][0], dtype=np.float32)
            token = np.asarray(handle["v2/step/dig_cut_tokens"][0], dtype=np.float32)
            actions = np.asarray(
                handle["action"][: contract.full_action_horizon], dtype=np.float32
            )
            if (
                qpos.shape != (4,)
                or qvel.shape != (4,)
                or token.shape != (10,)
                or actions.shape != (contract.full_action_horizon, 4)
                or not np.isfinite(qpos).all()
                or not np.isfinite(qvel).all()
                or not np.isfinite(token).all()
                or not np.isfinite(actions).all()
            ):
                rejections["nonfinite_or_shape"] += 1
                continue
            feature = np.concatenate((qpos, qvel, token)).astype(np.float64)
            if np.any(feature < lower - 1.0e-8) or np.any(feature > upper + 1.0e-8):
                rejections["t0_out_of_18d_support"] += 1
                continue
            signature = read_image_signature(
                handle, frame_index=0, camera_order=camera_order
            )
        rows.append(
            {
                "source_episode_id": source_id,
                "primitive_episode_id": episode_id,
                "qpos": qpos,
                "qvel": qvel,
                "token": token,
                "actions": actions,
                "controller_epoch": str(metadata.get("controller_epoch", "")),
                "controller_profile": str(
                    metadata.get("action_source_controller_profile", "")
                ),
                "calibration_schema": str(
                    metadata.get("action_calibration_schema", "")
                ),
                "image_signature": signature,
                "dataset_path": str(path.resolve()),
            }
        )
    return rows, {
        "schema": "dig_goal_action_episode_start_inventory_v1",
        "train_id_count": len(train_ids),
        "eligible_episode_count": len(rows),
        "eligible_source_episode_ids": sorted(
            {int(row["source_episode_id"]) for row in rows}
        ),
        "rejection_counts": dict(sorted(rejections.items())),
        "source_33_34_used": False,
        "window_random_split": False,
        "frame_scope": "primitive_t0_only",
        "action_horizon": contract.full_action_horizon,
    }


def read_image_signature(
    hdf5_file: h5py.File,
    *,
    frame_index: int,
    camera_order: Sequence[str],
) -> dict[str, Any]:
    images = []
    hashes = []
    for camera in camera_order:
        rgb = read_camera_rgb(hdf5_file, str(camera), int(frame_index))
        small = cv2.resize(rgb, (64, 64), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(cv2.resize(rgb, (9, 8)), cv2.COLOR_RGB2GRAY)
        images.append(small.astype(np.uint8))
        hashes.append((gray[:, 1:] > gray[:, :-1]).reshape(-1))
    return {
        "camera_order": tuple(str(value) for value in camera_order),
        "rgb_64x64": np.stack(images),
        "difference_hash": np.stack(hashes),
    }


def camera_signature_metrics(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> dict[str, Any]:
    left_signature = left["image_signature"]
    right_signature = right["image_signature"]
    if tuple(left_signature["camera_order"]) != tuple(right_signature["camera_order"]):
        raise ValueError("camera signature order mismatch")
    left_rgb = np.asarray(left_signature["rgb_64x64"], dtype=np.float64)
    right_rgb = np.asarray(right_signature["rgb_64x64"], dtype=np.float64)
    left_hash = np.asarray(left_signature["difference_hash"], dtype=bool)
    right_hash = np.asarray(right_signature["difference_hash"], dtype=bool)
    if left_rgb.shape != right_rgb.shape or left_hash.shape != right_hash.shape:
        raise ValueError("camera signature shape mismatch")
    maes = np.mean(np.abs(left_rgb - right_rgb), axis=(1, 2, 3)) / 255.0
    correlations = []
    for left_image, right_image in zip(left_rgb, right_rgb, strict=True):
        left_flat = left_image.reshape(-1)
        right_flat = right_image.reshape(-1)
        if np.std(left_flat) == 0.0 or np.std(right_flat) == 0.0:
            correlations.append(float(np.array_equal(left_flat, right_flat)))
        else:
            correlations.append(float(np.corrcoef(left_flat, right_flat)[0, 1]))
    dhash = np.mean(left_hash != right_hash, axis=1)
    return {
        "mean_normalised_pixel_mae": float(np.mean(maes)),
        "mean_pixel_correlation": float(np.mean(correlations)),
        "mean_difference_hash_hamming_fraction": float(np.mean(dhash)),
        "by_camera": [
            {
                "normalised_pixel_mae": float(maes[index]),
                "pixel_correlation": float(correlations[index]),
                "difference_hash_hamming_fraction": float(dhash[index]),
            }
            for index in range(len(correlations))
        ],
    }


def _target_demonstrations(
    *,
    reference: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    target_token: Sequence[float],
    contract: GoalActionIdentifiabilityContract,
    camera_metric_fn: CameraMetricFn,
) -> tuple[list[Mapping[str, Any]], dict[str, int]]:
    result = []
    funnel: Counter[str] = Counter()
    reference_episode = int(reference["primitive_episode_id"])
    for candidate in candidates:
        funnel["total_candidates"] += 1
        candidate_episode = int(candidate["primitive_episode_id"])
        if candidate_episode == reference_episode:
            state_match = True
            camera_match = True
            funnel["source_metadata_matched"] += 1
        else:
            state_assessment = same_non_goal_observation(
                reference, candidate, contract=contract
            )
            state_checks = state_assessment["checks"]
            if all(
                state_checks[name]
                for name in (
                    "same_allowed_source",
                    "distinct_primitive_episode",
                    "metadata_equal",
                )
            ):
                funnel["source_metadata_matched"] += 1
            state_match = state_assessment["matched"]
            camera_match = bool(
                state_match
                and camera_observation_matches(
                    camera_metric_fn(reference, candidate), contract=contract
                )["matched"]
            )
        if state_match:
            funnel["state_matched"] += 1
        if camera_match:
            funnel["camera_matched"] += 1
        target_match = target_token_matches(
            candidate["token"], target_token, contract=contract
        )["matched"]
        if state_match and camera_match and target_match:
            funnel["target_matched"] += 1
            result.append(candidate)
    return result, {
        name: int(funnel.get(name, 0))
        for name in (
            "total_candidates",
            "source_metadata_matched",
            "state_matched",
            "camera_matched",
            "target_matched",
        )
    }


def _empty_variant_coverage(
    variant: Mapping[str, Any], relation: Mapping[str, Any], reason: str
) -> dict[str, Any]:
    return {
        "variant_id": str(variant["variant_id"]),
        "source_episode_id": int(variant["source_episode_id"]),
        "reference_primitive_episode_id": int(variant["primitive_episode_id"]),
        "translation_bin": relation["translation_bin"],
        "base_demo_count": 0,
        "alternate_demo_count": 0,
        "base_demo_funnel": {},
        "alternate_demo_funnel": {},
        "evaluated_pair_count": 0,
        "passing_pair_count": 0,
        "covered": False,
        "passing_pairs": [],
        "reason": reason,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer, np.bool_)):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


__all__ = [
    "camera_signature_metrics",
    "enumerate_identifiability_pairs",
    "evaluate_variant_demonstration_coverage",
    "load_strict_train_episode_starts",
    "read_image_signature",
]
