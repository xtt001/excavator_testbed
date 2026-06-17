"""Runner selection helpers for the primitive scheduler facade."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

LEGACY_FSM_RUNNER = "legacy_fsm"
ACTION_TREE_SHADOW_RUNNER = "action_tree_shadow"
NOT_APPLICABLE_RUNNER = "not_applicable"

_RUNNER_ALIASES = {
    "": LEGACY_FSM_RUNNER,
    "legacy": LEGACY_FSM_RUNNER,
    "legacy_fsm": LEGACY_FSM_RUNNER,
    "fsm": LEGACY_FSM_RUNNER,
    "action_tree": ACTION_TREE_SHADOW_RUNNER,
    "action_tree_shadow": ACTION_TREE_SHADOW_RUNNER,
}


def normalize_primitive_scheduler_runner(
    value: object = None,
    *,
    allow_not_applicable: bool = False,
) -> str:
    """Normalize runner config while preserving legacy as the default."""

    if value is None:
        return LEGACY_FSM_RUNNER
    key = str(value).strip().lower().replace("-", "_")
    aliases = dict(_RUNNER_ALIASES)
    if allow_not_applicable:
        aliases[NOT_APPLICABLE_RUNNER] = NOT_APPLICABLE_RUNNER
    if key not in aliases:
        supported_values = {LEGACY_FSM_RUNNER, ACTION_TREE_SHADOW_RUNNER}
        if allow_not_applicable:
            supported_values.add(NOT_APPLICABLE_RUNNER)
        supported = ", ".join(sorted(supported_values))
        raise ValueError(
            f"Unsupported primitive_scheduler_runner {value!r}; "
            f"supported values are: {supported}."
        )
    return aliases[key]


def primitive_scheduler_runner_from_policy_config(
    policy_cfg: Mapping[str, Any],
) -> str:
    """Read the primitive scheduler runner from policy config."""

    return normalize_primitive_scheduler_runner(
        dict(policy_cfg).get("primitive_scheduler_runner")
    )


def primitive_scheduler_runner_from_metadata(
    metadata: Mapping[str, Any] | None,
    resolved_config: Mapping[str, Any] | None = None,
) -> str:
    """Read runner metadata with backward-compatible legacy defaults."""

    del resolved_config
    raw_value = dict(metadata or {}).get("primitive_scheduler_runner")
    return normalize_primitive_scheduler_runner(
        raw_value,
        allow_not_applicable=True,
    )


def apply_primitive_scheduler_runner(
    *,
    policy: Any,
    policy_class: str,
    runner: object,
) -> str:
    """Apply a primitive scheduler runner to one policy instance."""

    normalized = normalize_primitive_scheduler_runner(runner)
    setattr(policy, "_primitive_scheduler_runner", normalized)
    if normalized == LEGACY_FSM_RUNNER:
        return normalized

    policy_class_name = str(policy_class).strip().upper()
    if policy_class_name != "PRIMITIVE_PLANNER_ACT":
        raise ValueError(
            "primitive_scheduler_runner=action_tree_shadow only supports "
            "PRIMITIVE_PLANNER_ACT 4P; 5P remains compatibility-only."
        )

    from testbed.planner.primitive_action_tree import PrimitiveActionTreeRunner

    action_tree_runner = PrimitiveActionTreeRunner()

    def _predict_with_action_tree(obs: dict[str, Any]):
        return action_tree_runner.predict(policy, obs)

    setattr(policy, "_primitive_action_tree_runner", action_tree_runner)
    setattr(policy, "predict", _predict_with_action_tree)
    return normalized
