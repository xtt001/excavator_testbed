"""Planner runtime effect type names shared by backend implementations."""

LEGACY_FSM_TRANSITION_EFFECT = "run_legacy_fsm_transition"
APPLY_BOOTSTRAP_TRANSITION_DECISION_EFFECT = "apply_bootstrap_transition_decision"
APPLY_PRE_DIG_ALIGN_OUTCOME_EFFECT = "apply_pre_dig_align_outcome"
APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT = (
    "apply_dig_transition_runtime_projection"
)
APPLY_CARRY_TRANSITION_RUNTIME_EFFECT = "apply_carry_transition_runtime"
APPLY_DUMP_TRANSITION_RUNTIME_EFFECT = "apply_dump_transition_runtime"
APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT = (
    "apply_return_to_dig_transition_runtime"
)


__all__ = [
    "APPLY_BOOTSTRAP_TRANSITION_DECISION_EFFECT",
    "APPLY_CARRY_TRANSITION_RUNTIME_EFFECT",
    "APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT",
    "APPLY_DUMP_TRANSITION_RUNTIME_EFFECT",
    "APPLY_PRE_DIG_ALIGN_OUTCOME_EFFECT",
    "APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT",
    "LEGACY_FSM_TRANSITION_EFFECT",
]
