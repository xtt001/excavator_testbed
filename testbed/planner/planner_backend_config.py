"""Planner backend selection helpers for primitive planner eval/runtime paths."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from testbed.planner.runtime import PlannerBackend

LEGACY_FSM_BACKEND = "legacy_fsm"
ACTION_TREE_SHADOW_BACKEND = "action_tree_shadow"
NOT_APPLICABLE_BACKEND = "not_applicable"
PLANNER_BACKEND_CONFIG_KEY = "planner_backend"
_REMOVED_PRIMITIVE_SCHEDULER_RUNNER_KEY = "primitive_scheduler_runner"

_BACKEND_ALIASES = {
    "": LEGACY_FSM_BACKEND,
    "legacy": LEGACY_FSM_BACKEND,
    "legacy_fsm": LEGACY_FSM_BACKEND,
    "fsm": LEGACY_FSM_BACKEND,
    "action_tree": ACTION_TREE_SHADOW_BACKEND,
    "action_tree_shadow": ACTION_TREE_SHADOW_BACKEND,
}


def _reject_removed_runner_key(mapping: Mapping[str, Any]) -> None:
    if _REMOVED_PRIMITIVE_SCHEDULER_RUNNER_KEY in mapping:
        raise ValueError(
            "primitive_scheduler_runner has been replaced by planner_backend."
        )


def normalize_planner_backend(
    value: object = None,
    *,
    allow_not_applicable: bool = False,
) -> str:
    """Normalize planner backend config while preserving legacy as the default."""

    if value is None:
        return LEGACY_FSM_BACKEND
    key = str(value).strip().lower().replace("-", "_")
    aliases = dict(_BACKEND_ALIASES)
    if allow_not_applicable:
        aliases[NOT_APPLICABLE_BACKEND] = NOT_APPLICABLE_BACKEND
    if key not in aliases:
        supported_values = {LEGACY_FSM_BACKEND, ACTION_TREE_SHADOW_BACKEND}
        if allow_not_applicable:
            supported_values.add(NOT_APPLICABLE_BACKEND)
        supported = ", ".join(sorted(supported_values))
        raise ValueError(
            f"Unsupported {PLANNER_BACKEND_CONFIG_KEY} {value!r}; "
            f"supported values are: {supported}."
        )
    return aliases[key]


def planner_backend_from_policy_config(
    policy_cfg: Mapping[str, Any],
) -> str:
    """Read the planner backend from policy config."""

    cfg = dict(policy_cfg)
    _reject_removed_runner_key(cfg)
    return normalize_planner_backend(cfg.get(PLANNER_BACKEND_CONFIG_KEY))


def planner_backend_from_metadata(
    metadata: Mapping[str, Any] | None,
    resolved_config: Mapping[str, Any] | None = None,
) -> str:
    """Read planner backend metadata with default legacy semantics."""

    del resolved_config
    meta = dict(metadata or {})
    _reject_removed_runner_key(meta)
    return normalize_planner_backend(
        meta.get(PLANNER_BACKEND_CONFIG_KEY),
        allow_not_applicable=True,
    )


def apply_planner_backend(
    *,
    policy: Any,
    policy_class: str,
    backend: object,
) -> str:
    """Apply a planner backend selection to one policy instance."""

    normalized = normalize_planner_backend(backend)
    setattr(policy, "_planner_backend", normalized)
    if normalized == LEGACY_FSM_BACKEND:
        return normalized

    policy_class_name = str(policy_class).strip().upper()
    if policy_class_name != "PRIMITIVE_PLANNER_ACT":
        raise ValueError(
            "planner_backend=action_tree_shadow only supports "
            "PRIMITIVE_PLANNER_ACT 4P; 5P remains compatibility-only."
        )

    from testbed.planner.primitive_action_tree import PrimitiveActionTreeRunner

    action_tree_runner = PrimitiveActionTreeRunner()

    def _predict_with_action_tree(obs: dict[str, Any]):
        return action_tree_runner.predict(policy, obs)

    setattr(policy, "_primitive_action_tree_runner", action_tree_runner)
    setattr(policy, "predict", _predict_with_action_tree)
    return normalized


def make_planner_backend(backend: object = None) -> PlannerBackend:
    """Create a runtime planner backend for supported backend names."""

    normalized = normalize_planner_backend(backend)
    if normalized == ACTION_TREE_SHADOW_BACKEND:
        raise ValueError(
            "planner_backend=action_tree_shadow is a shadow adapter, not a "
            "runtime backend; use apply_planner_backend for the opt-in shadow "
            "path."
        )
    from testbed.planner.runtime import LegacyStateMachineBackend

    return LegacyStateMachineBackend()
