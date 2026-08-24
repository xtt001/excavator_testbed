"""Shared, explicit inference contract for frozen ACT checkpoints.

This module owns the configuration and metadata that must agree between
training, runtime evaluation, and offline diagnostic replay.  It deliberately
does not decide task goals or safety policy: callers provide already grounded
low-dimensional inputs and receive only ACT action predictions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.data.v2_1 import GOAL_TOKEN_DIM
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM

if TYPE_CHECKING:
    from testbed.policies.act.adapter import ACTAdapter


@dataclass(frozen=True)
class TemporalAggregationContract:
    """Resolved temporal aggregation settings used by one ACT policy instance."""

    enabled: bool
    num_queries: int
    window: int
    weight_order: str
    decay: float

    def as_dict(self) -> dict[str, bool | float | int | str]:
        """Return a JSON-ready representation without implementation objects."""
        return {
            "enabled": self.enabled,
            "num_queries": self.num_queries,
            "window": self.window,
            "weight_order": self.weight_order,
            "decay": self.decay,
        }


@dataclass(frozen=True)
class ACTActionChunk:
    """One unnormalised ACT action chunk and its optional outcome prediction."""

    actions: np.ndarray
    outcome: np.ndarray | None = None

    def __post_init__(self) -> None:
        actions = np.asarray(self.actions, dtype=np.float32)
        if actions.ndim != 2:
            raise ValueError(
                "ACTActionChunk.actions must have shape "
                "(num_queries, action_dim), got "
                f"{actions.shape}."
            )
        object.__setattr__(self, "actions", actions)
        if self.outcome is not None:
            object.__setattr__(
                self,
                "outcome",
                np.asarray(self.outcome, dtype=np.float32).reshape(-1),
            )

    @property
    def action_chunk(self) -> np.ndarray:
        """Compatibility-friendly name for :attr:`actions`."""
        return self.actions

    @property
    def first_action(self) -> np.ndarray:
        """The first unnormalised action in the chunk."""
        return self.actions[0]


def resolve_act_low_dim_state_dim(
    low_dim_keys: Sequence[str],
    equipment_model: str,
) -> int:
    """Resolve the concatenated ACT proprioceptive state width.

    The result is intentionally shared by train, eval, and offline replay so a
    checkpoint cannot silently be instantiated with a different conditioning
    width from the data path that produced it.
    """
    return int(
        sum(
            _resolve_act_low_dim_key_dim(key, equipment_model)
            for key in low_dim_keys
        )
    )


def _resolve_act_low_dim_key_dim(key: str, equipment_model: str) -> int:
    equipment_model = str(equipment_model).lower()
    if key == "goal_tokens":
        return int(GOAL_TOKEN_DIM)
    if key == "cell_entry_tokens":
        return int(CELL_ENTRY_TOKEN_DIM)
    if key == "dig_cut_tokens":
        return int(DIG_CUT_TOKEN_DIM)
    if key == "dig_depth_profile_tokens_v1":
        return int(DIG_DEPTH_PROFILE_TOKEN_DIM)
    if key == "return_target_tokens":
        return int(RETURN_TARGET_TOKEN_DIM)
    if key == "return_relocate_tokens_v1":
        return int(RETURN_TARGET_TOKEN_DIM)
    if key == "return_start_envelope_tokens_v1":
        return int(RETURN_START_ENVELOPE_TOKEN_DIM)
    if key in ("qpos", "qvel"):
        if "bimanual" in equipment_model:
            return 14
        if (
            "excavator_simple" in equipment_model
            or "agxunity" in equipment_model
            or "agx" in equipment_model
            or "yulong" in equipment_model
        ):
            return 4
        return 7
    raise ValueError(f"Unsupported low-dim key {key!r}.")


def build_act_adapter_config(
    *,
    config: Mapping[str, Any],
    camera_names: Sequence[str],
    equipment_model: str,
    max_episode_len: int,
    low_dim_keys: Sequence[str],
    act_params: Mapping[str, Any] | None = None,
    outcome_head_config: Mapping[str, Any] | None = None,
    image_mask_config: Mapping[str, Any] | None = None,
    supervision_keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build the single checkpoint-compatible ``ACTAdapter`` configuration.

    ``config`` supplies the historical training learning-rate default.  The
    remaining arguments are explicit because an offline replay must record the
    exact cameras, equipment model, low-dimensional input order, and temporal
    settings used to load its frozen checkpoint.
    """
    train_cfg = dict(config.get("train", {}) or {})
    act_params = dict(act_params or {})
    outcome_head_config = dict(outcome_head_config or {})
    outcome_head_enabled = bool(outcome_head_config.get("enabled", False))
    outcome_dim = int(
        outcome_head_config.get("dim", 10 if outcome_head_enabled else 0)
    )
    policy_config: dict[str, Any] = {
        "lr": float(train_cfg.get("lr", 1e-5)),
        "num_queries": int(act_params.get("chunk_size", 100)),
        "kl_weight": float(act_params.get("kl_weight", 10)),
        "hidden_dim": int(act_params.get("hidden_dim", 512)),
        "dim_feedforward": int(act_params.get("dim_feedforward", 3200)),
        "lr_backbone": 1e-5,
        "backbone": "resnet18",
        "enc_layers": 4,
        "dec_layers": 7,
        "nheads": 8,
        "camera_names": list(camera_names),
        "equipment_model": str(equipment_model),
        "max_episode_len": int(max_episode_len),
        "low_dim_keys": list(low_dim_keys),
        "state_dim": resolve_act_low_dim_state_dim(
            low_dim_keys,
            equipment_model,
        ),
        "image_mask": dict(image_mask_config or {}),
        "outcome_head": outcome_head_config,
        "outcome_dim": outcome_dim if outcome_head_enabled else 0,
        "outcome_action_horizon": int(
            outcome_head_config.get(
                "action_horizon",
                act_params.get("chunk_size", 100),
            )
        ),
        "outcome_hidden_dim": outcome_head_config.get("hidden_dim"),
    }
    if supervision_keys is not None:
        policy_config["supervision_keys"] = list(supervision_keys)
    for temporal_key in (
        "temporal_agg_window",
        "temporal_agg_weight_order",
        "temporal_agg_decay",
    ):
        if temporal_key in act_params:
            policy_config[temporal_key] = act_params[temporal_key]
    return policy_config


def load_act_policy(
    *,
    ckpt_path: str | Path,
    policy_config: Mapping[str, Any],
    norm_stats_path: str | Path | None = None,
    temporal_agg: bool = False,
    device: str = "cuda",
    create_optimizer: bool = True,
) -> ACTAdapter:
    """Load a frozen ACT adapter with an explicit normalisation artifact."""
    from testbed.policies.act.adapter import ACTAdapter

    ckpt_path = Path(ckpt_path)
    resolved_norm_stats_path = (
        Path(norm_stats_path)
        if norm_stats_path is not None
        else ckpt_path.parent / "dataset_stats.pkl"
    )
    return ACTAdapter.from_checkpoint(
        ckpt_path=ckpt_path,
        policy_config=dict(policy_config),
        norm_stats_path=resolved_norm_stats_path,
        temporal_agg=bool(temporal_agg),
        device=device,
        create_optimizer=bool(create_optimizer),
    )


def describe_act_inference(policy: ACTAdapter) -> dict[str, Any]:
    """Return JSON-ready metadata for a loaded ACT inference instance.

    The description records resolved temporal aggregation rather than merely
    repeating YAML.  It also records the action de-normalisation scale used by
    the adapter, which is required to compare offline replay results safely.
    """
    contract = policy.temporal_aggregation_contract
    norm_stats = getattr(policy, "norm_stats", {})
    action_mean = np.asarray(norm_stats.get("action_mean", []), dtype=np.float32)
    action_std = np.asarray(norm_stats.get("action_std", []), dtype=np.float32)
    action_dim = int(action_mean.reshape(-1).shape[0])
    return {
        "temporal_aggregation": contract.as_dict(),
        "temporal_agg": contract.enabled,
        "temporal_agg_window": contract.window,
        "temporal_agg_weight_order": contract.weight_order,
        "temporal_agg_decay": contract.decay,
        "num_queries": contract.num_queries,
        "action_dim": action_dim,
        "action_mean": [float(value) for value in action_mean.reshape(-1)],
        "action_std": [float(value) for value in action_std.reshape(-1)],
        "low_dim_keys": list(getattr(policy, "_low_dim_keys", [])),
        "camera_names": list(getattr(policy, "_camera_names", [])),
    }


__all__ = [
    "ACTActionChunk",
    "TemporalAggregationContract",
    "build_act_adapter_config",
    "describe_act_inference",
    "load_act_policy",
    "resolve_act_low_dim_state_dim",
]
