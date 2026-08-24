"""Batched per-frame DDIM sampling for frozen DP probe checkpoints."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, TextIO

import numpy as np
import torch

from testbed.eval.dig_diffusion_probe_model import (
    DiffusionSchedule,
    MinimalConditionalDiffusionPolicy,
    sample_action_chunks,
)

CONDITION_NAMES = (
    "base_correct",
    "alternate_correct",
    "zero",
    "shuffled",
)


def evaluate_minimal_dp_model(
    *,
    model: MinimalConditionalDiffusionPolicy,
    schedule_betas: torch.Tensor,
    norm_stats: Mapping[str, torch.Tensor],
    evaluation_arrays: Mapping[str, np.ndarray],
    token_conditions: Mapping[str, np.ndarray],
    variant_records: Sequence[Mapping[str, Any]],
    training_seed: int,
    inference_noise_seeds: Sequence[int],
    inference_steps: int,
    action_p01: np.ndarray,
    action_p99: np.ndarray,
    device: str | torch.device,
    batch_size: int,
    trace_handle: TextIO | None = None,
) -> dict[str, Any]:
    target_device = torch.device(device)
    arrays = {name: np.asarray(value) for name, value in evaluation_arrays.items()}
    images = arrays["images"]
    qpos = np.asarray(arrays["qpos"], dtype=np.float32)
    qvel = np.asarray(arrays["qvel"], dtype=np.float32)
    if images.ndim != 5 or images.shape[2:] != (4, 32, 32):
        raise ValueError("DP evaluation images must be [V,F,4,32,32]")
    variant_count, frame_count = images.shape[:2]
    if qpos.shape != (variant_count, frame_count, 4) or qvel.shape != qpos.shape:
        raise ValueError("DP evaluation qpos/qvel shape mismatch")
    if len(variant_records) != variant_count:
        raise ValueError("DP evaluation variant lineage mismatch")
    tokens = {
        name: np.asarray(token_conditions[name], dtype=np.float32)
        for name in CONDITION_NAMES
    }
    if any(value.shape != (variant_count, 10) for value in tokens.values()):
        raise ValueError("DP evaluation token conditions must be [V,10]")
    lower = np.asarray(action_p01, dtype=np.float32).reshape(4)
    upper = np.asarray(action_p99, dtype=np.float32).reshape(4)
    stats = {
        name: torch.as_tensor(value).float().to(target_device)
        for name, value in norm_stats.items()
    }
    action_mean = stats["action_mean"].reshape(1, 1, 4)
    action_std = stats["action_std"].reshape(1, 1, 4)
    proprio_mean = stats["proprio_mean"].reshape(1, 18)
    proprio_std = stats["proprio_std"].reshape(1, 18)
    betas = torch.as_tensor(schedule_betas).float()
    schedule = DiffusionSchedule(
        betas=betas,
        alphas=1.0 - betas,
        alpha_bars=torch.cumprod(1.0 - betas, dim=0),
    )
    noise_seeds = tuple(int(value) for value in inference_noise_seeds)
    dispatched = {
        name: np.empty(
            (len(noise_seeds), variant_count, frame_count, 4), dtype=np.float32
        )
        for name in CONDITION_NAMES
    }
    chunk_goal_effect = []
    chunk_zero_effect = []
    chunk_shuffle_effect = []
    chunk_support_counts = CounterByCondition()
    nonfinite_count = 0
    raw_goal_responsive = []
    flat_count = variant_count * frame_count
    flat_images = images.reshape(flat_count, 4, 32, 32)
    flat_qpos = qpos.reshape(flat_count, 4)
    flat_qvel = qvel.reshape(flat_count, 4)
    flat_variant = np.repeat(np.arange(variant_count), frame_count)
    flat_frame = np.tile(np.arange(frame_count), variant_count)
    model = model.to(target_device)
    model.eval()
    for noise_index, noise_seed in enumerate(noise_seeds):
        generator = torch.Generator(device=target_device).manual_seed(noise_seed)
        for start in range(0, flat_count, batch_size):
            stop = min(start + batch_size, flat_count)
            count = stop - start
            image_batch = (
                torch.as_tensor(
                    flat_images[start:stop, :, None],
                    dtype=torch.float32,
                    device=target_device,
                )
                / 255.0
            )
            with torch.inference_mode():
                image_features = model.encode_images(image_batch)
            variant_indices = flat_variant[start:stop]
            condition_low_dim = []
            for name in CONDITION_NAMES:
                token = tokens[name][variant_indices]
                raw = np.concatenate(
                    (flat_qpos[start:stop], flat_qvel[start:stop], token), axis=1
                )
                condition_low_dim.append(raw)
            low_dim = torch.as_tensor(
                np.concatenate(condition_low_dim, axis=0),
                dtype=torch.float32,
                device=target_device,
            )
            low_dim = (low_dim - proprio_mean) / proprio_std
            base_noise = torch.randn(
                (count, 100, 4),
                generator=generator,
                device=target_device,
            )
            initial_noise = base_noise.repeat(len(CONDITION_NAMES), 1, 1)
            repeated_features = image_features.repeat(len(CONDITION_NAMES), 1)
            normalized_chunk = sample_action_chunks(
                model=model,
                schedule=schedule,
                images=None,
                low_dim=low_dim,
                initial_noise=initial_noise,
                inference_steps=inference_steps,
                image_features=repeated_features,
            )
            chunk = (normalized_chunk * action_std + action_mean).reshape(
                len(CONDITION_NAMES), count, 100, 4
            )
            chunk_np = chunk.detach().cpu().numpy().astype(np.float32)
            nonfinite_count += int(np.count_nonzero(~np.isfinite(chunk_np)))
            by_name = {
                name: chunk_np[index] for index, name in enumerate(CONDITION_NAMES)
            }
            goal_delta = by_name["alternate_correct"] - by_name["base_correct"]
            zero_delta = by_name["alternate_correct"] - by_name["zero"]
            shuffle_delta = by_name["alternate_correct"] - by_name["shuffled"]
            chunk_goal_effect.extend(
                np.mean(np.linalg.norm(goal_delta, axis=-1), axis=1)
            )
            chunk_zero_effect.extend(
                np.mean(np.linalg.norm(zero_delta, axis=-1), axis=1)
            )
            chunk_shuffle_effect.extend(
                np.mean(np.linalg.norm(shuffle_delta, axis=-1), axis=1)
            )
            threshold = action_std.detach().cpu().numpy().reshape(4) * 0.05
            raw_goal_responsive.extend(
                np.any(np.abs(goal_delta) > threshold[None, None, :], axis=(1, 2))
            )
            for condition_name, condition_chunk in by_name.items():
                chunk_support_counts.add(
                    condition_name,
                    condition_chunk,
                    lower=lower,
                    upper=upper,
                )
                first_actions = condition_chunk[:, 0]
                for offset in range(count):
                    flat_index = start + offset
                    variant_index = int(flat_variant[flat_index])
                    frame_index = int(flat_frame[flat_index])
                    dispatched[condition_name][
                        noise_index, variant_index, frame_index
                    ] = first_actions[offset]
                    if trace_handle is not None:
                        trace_handle.write(
                            json.dumps(
                                _trace_row(
                                    training_seed=training_seed,
                                    noise_seed=noise_seed,
                                    variant_index=variant_index,
                                    frame_index=frame_index,
                                    variant_record=variant_records[variant_index],
                                    condition=condition_name,
                                    chunk=condition_chunk[offset],
                                    lower=lower,
                                    upper=upper,
                                ),
                                sort_keys=True,
                                separators=(",", ":"),
                                allow_nan=False,
                            )
                            + "\n"
                        )
    return {
        "schema": "minimal_dp_model_evaluation_v1",
        "training_seed": int(training_seed),
        "inference_noise_seeds": list(noise_seeds),
        "dispatched_actions": dispatched,
        "resampled_chunk_count": len(noise_seeds) * flat_count * len(CONDITION_NAMES),
        "temporal_aggregation_used": False,
        "contributing_chunk_age": 0,
        "chunk_distribution": {
            "goal_effect_mean_query_l2_p10": float(
                np.quantile(chunk_goal_effect, 0.10)
            ),
            "goal_effect_mean_query_l2_p50": float(np.median(chunk_goal_effect)),
            "zero_effect_mean_query_l2_p50": float(np.median(chunk_zero_effect)),
            "shuffled_effect_mean_query_l2_p50": float(np.median(chunk_shuffle_effect)),
            "raw_goal_response_fraction": float(np.mean(raw_goal_responsive)),
            "support": chunk_support_counts.as_dict(),
            "nonfinite_count": nonfinite_count,
        },
    }


class CounterByCondition:
    def __init__(self) -> None:
        self.rows: dict[str, int] = {name: 0 for name in CONDITION_NAMES}
        self.violations: dict[str, int] = {name: 0 for name in CONDITION_NAMES}

    def add(
        self,
        name: str,
        actions: np.ndarray,
        *,
        lower: np.ndarray,
        upper: np.ndarray,
    ) -> None:
        flat = np.asarray(actions).reshape(-1, 4)
        outside = np.any((flat < lower[None]) | (flat > upper[None]), axis=1)
        self.rows[name] += int(flat.shape[0])
        self.violations[name] += int(np.count_nonzero(outside))

    def as_dict(self) -> dict[str, Any]:
        return {
            name: {
                "action_count": self.rows[name],
                "violation_count": self.violations[name],
                "violation_rate": (
                    self.violations[name] / self.rows[name] if self.rows[name] else 0.0
                ),
            }
            for name in CONDITION_NAMES
        }


def _trace_row(
    *,
    training_seed: int,
    noise_seed: int,
    variant_index: int,
    frame_index: int,
    variant_record: Mapping[str, Any],
    condition: str,
    chunk: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> dict[str, Any]:
    values = np.asarray(chunk, dtype=np.float32)
    first = values[0]
    first_violation = bool(np.any((first < lower) | (first > upper)))
    return {
        "schema": "minimal_dp_probe_trace_frame_v1",
        "training_seed": int(training_seed),
        "inference_noise_seed": int(noise_seed),
        "variant_index": variant_index,
        "variant_id": str(variant_record["variant_id"]),
        "source_episode_id": int(variant_record.get("source_episode_id", -1)),
        "primitive_episode_id": int(variant_record.get("primitive_episode_id", -1)),
        "frame_index": frame_index,
        "condition": condition,
        "raw_action_chunk_sha256": _array_sha256(values),
        "raw_action_chunk_mean": values.mean(axis=0).astype(float).tolist(),
        "raw_action_chunk_std": values.std(axis=0).astype(float).tolist(),
        "diagnostic_dispatched_action": first.astype(float).tolist(),
        "first_action_support_violation": first_violation,
        "nonfinite": bool(not np.isfinite(values).all()),
        "contributing_chunk_ages": [0],
        "temporal_aggregation_used": False,
        "clipping_applied": False,
    }


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode())
    digest.update(array.tobytes())
    return digest.hexdigest()


__all__ = ["CONDITION_NAMES", "evaluate_minimal_dp_model"]
