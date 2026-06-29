"""Backend-neutral primitive decision trace records and export helpers."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from testbed.planner.primitive.decision.contracts import (
    LEGACY_FSM_DECISION_SOURCE,
    PlannerEffect,
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
)


DECISION_TRACE_SCHEMA_VERSION = "primitive_decision_trace_v1"

DecisionTraceStatus = Literal["success", "fallback", "contract_error", "skipped"]
DecisionValidationStatus = Literal["accepted", "rejected", "skipped"]
DecisionDiagnosticStatus = Literal["pass", "fail", "skipped", "unknown"]

_DIAGNOSTIC_STATUSES = {"pass", "fail", "skipped", "unknown"}
_TRACE_STATUSES = {"success", "fallback", "contract_error", "skipped"}
_VALIDATION_STATUSES = {"accepted", "rejected", "skipped"}

LEGACY_FSM_TRACE_BACKEND_NAME = "legacy_fsm"
LEGACY_FSM_TRACE_BACKEND_KIND = "legacy_fsm"
LEGACY_FSM_PAYLOAD_SCHEMA_VERSION = "legacy_fsm_payload_v1"

BEHAVIOR_TREE_SHADOW_TRACE_BACKEND_NAME = "behavior_tree_shadow"
BEHAVIOR_TREE_TRACE_BACKEND_KIND = "behavior_tree"
BEHAVIOR_TREE_PAYLOAD_SCHEMA_VERSION = "behavior_tree_payload_v1"

_LEGACY_FSM_BRANCH_BY_DECISION_SOURCE = {
    "legacy_fsm_bootstrap_requested_effect": "bootstrap",
    "legacy_fsm_dig_requested_effect": "dig",
    "legacy_fsm_carry_requested_effect": "carry",
    "legacy_fsm_dump_requested_effect": "dump",
    "legacy_fsm_return_requested_effect": "return",
    "legacy_fsm_pre_dig_align_requested_effect": "pre_dig_align",
}

_LEGACY_FSM_BRANCH_ORDER_INDEX = {
    "bootstrap": 0,
    "dig": 1,
    "carry": 2,
    "dump": 3,
    "return": 4,
    "pre_dig_align": -1,
}


@dataclass(frozen=True)
class DecisionEffectSummary:
    """Safe trace summary for one decision effect."""

    effect_type: str
    reason: str = ""
    already_applied: bool = False
    payload_keys: tuple[str, ...] = ()

    @classmethod
    def from_effect(cls, effect: PlannerEffect) -> "DecisionEffectSummary":
        payload = getattr(effect, "payload", None)
        payload_keys: tuple[str, ...] = ()
        if isinstance(payload, Mapping):
            payload_keys = tuple(sorted(str(key) for key in payload))
        reason = str(
            getattr(
                effect,
                "reason",
                getattr(effect, "switch_reason", ""),
            )
        )
        return cls(
            effect_type=str(effect.effect_type),
            reason=reason,
            already_applied=bool(effect.already_applied),
            payload_keys=payload_keys,
        )

    def to_compact_dict(self) -> dict[str, object]:
        return {
            "effect_type": str(self.effect_type),
            "reason": str(self.reason),
            "already_applied": bool(self.already_applied),
        }

    def to_rich_dict(self) -> dict[str, object]:
        data = self.to_compact_dict()
        data["payload_keys"] = list(self.payload_keys)
        return data


@dataclass(frozen=True)
class DecisionDiagnosticCheck:
    """Backend-neutral diagnostic check for decision trace export."""

    name: str
    status: DecisionDiagnosticStatus
    reason: str = ""
    value: object | None = None

    def __post_init__(self) -> None:
        status = str(self.status)
        if status not in _DIAGNOSTIC_STATUSES:
            raise PrimitiveDecisionContractError(
                f"unsupported decision diagnostic status: {status!r}"
            )
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason", str(self.reason))

    def to_dict(self) -> dict[str, object]:
        return {
            "name": str(self.name),
            "status": str(self.status),
            "reason": str(self.reason),
            "value": _json_safe_value(self.value),
        }


@dataclass(frozen=True)
class DecisionTraceMetadata:
    """Optional tick/run metadata for generic decision trace assembly."""

    backend_name: str
    backend_kind: str
    tick_id: str | None = None
    episode_id: str | None = None
    sim_time_s: float | None = None
    selected_operation: str | None = None
    fallback_type: str = "none"
    reason_codes: tuple[str, ...] = ()
    diagnostic_checks: tuple[DecisionDiagnosticCheck, ...] = ()
    confidence: float | None = None
    score: float | None = None
    trace_status: DecisionTraceStatus | None = None
    validation_status: DecisionValidationStatus = "skipped"

    def __post_init__(self) -> None:
        backend_name = str(self.backend_name)
        backend_kind = str(self.backend_kind)
        if not backend_name.strip():
            raise PrimitiveDecisionContractError("decision trace requires backend_name")
        if not backend_kind.strip():
            raise PrimitiveDecisionContractError("decision trace requires backend_kind")
        if self.trace_status is not None:
            trace_status = str(self.trace_status)
            if trace_status not in _TRACE_STATUSES:
                raise PrimitiveDecisionContractError(
                    f"unsupported decision trace status: {trace_status!r}"
                )
            object.__setattr__(self, "trace_status", trace_status)
        validation_status = str(self.validation_status or "skipped")
        if validation_status not in _VALIDATION_STATUSES:
            raise PrimitiveDecisionContractError(
                f"unsupported decision validation status: {validation_status!r}"
            )
        object.__setattr__(self, "validation_status", validation_status)
        object.__setattr__(self, "backend_name", backend_name)
        object.__setattr__(self, "backend_kind", backend_kind)
        object.__setattr__(
            self,
            "fallback_type",
            str(self.fallback_type or "none"),
        )
        object.__setattr__(
            self,
            "reason_codes",
            tuple(str(code) for code in self.reason_codes),
        )
        object.__setattr__(
            self,
            "diagnostic_checks",
            tuple(self.diagnostic_checks),
        )


@dataclass(frozen=True)
class DecisionTraceRecord:
    """Backend-neutral sidecar record for primitive decision explanation."""

    backend_name: str
    backend_kind: str
    decision_source: str
    decision_status: str
    trace_status: DecisionTraceStatus
    validation_status: DecisionValidationStatus
    skill_before: str
    skill_after: str
    switch_reason: str
    selected_operation: str
    fallback_type: str
    reason_codes: tuple[str, ...]
    requested_effects_summary: tuple[DecisionEffectSummary, ...]
    diagnostic_checks: tuple[DecisionDiagnosticCheck, ...]
    confidence: float | None = None
    score: float | None = None
    tick_id: str | None = None
    episode_id: str | None = None
    sim_time_s: float | None = None
    backend_payload: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = field(
        default=DECISION_TRACE_SCHEMA_VERSION,
        init=False,
    )

    def __post_init__(self) -> None:
        trace_status = str(self.trace_status)
        if trace_status not in _TRACE_STATUSES:
            raise PrimitiveDecisionContractError(
                f"unsupported decision trace status: {trace_status!r}"
            )
        validation_status = str(self.validation_status or "skipped")
        if validation_status not in _VALIDATION_STATUSES:
            raise PrimitiveDecisionContractError(
                f"unsupported decision validation status: {validation_status!r}"
            )
        if not isinstance(self.backend_payload, Mapping):
            raise PrimitiveDecisionContractError(
                "decision trace backend_payload must be mapping-like"
            )
        object.__setattr__(self, "backend_name", str(self.backend_name))
        object.__setattr__(self, "backend_kind", str(self.backend_kind))
        object.__setattr__(self, "decision_source", str(self.decision_source))
        object.__setattr__(self, "decision_status", str(self.decision_status))
        object.__setattr__(self, "trace_status", trace_status)
        object.__setattr__(self, "validation_status", validation_status)
        object.__setattr__(self, "skill_before", str(self.skill_before))
        object.__setattr__(self, "skill_after", str(self.skill_after))
        object.__setattr__(self, "switch_reason", str(self.switch_reason))
        object.__setattr__(
            self,
            "selected_operation",
            str(self.selected_operation or "unknown"),
        )
        object.__setattr__(self, "fallback_type", str(self.fallback_type or "none"))
        object.__setattr__(
            self,
            "reason_codes",
            tuple(str(code) for code in self.reason_codes),
        )
        object.__setattr__(
            self,
            "requested_effects_summary",
            tuple(self.requested_effects_summary),
        )
        object.__setattr__(
            self,
            "diagnostic_checks",
            tuple(self.diagnostic_checks),
        )
        object.__setattr__(
            self,
            "backend_payload",
            _json_safe_mapping(self.backend_payload),
        )

    def to_compact_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "backend_name": self.backend_name,
            "backend_kind": self.backend_kind,
            "decision_source": self.decision_source,
            "decision_status": self.decision_status,
            "trace_status": self.trace_status,
            "validation_status": self.validation_status,
            "skill_before": self.skill_before,
            "skill_after": self.skill_after,
            "selected_operation": self.selected_operation,
            "fallback_type": self.fallback_type,
            "reason_codes": list(self.reason_codes),
            "requested_effects_summary": [
                effect.to_compact_dict()
                for effect in self.requested_effects_summary
            ],
            "confidence": self.confidence,
            "score": self.score,
            "tick_id": self.tick_id,
            "sim_time_s": self.sim_time_s,
        }

    def to_rich_dict(self) -> dict[str, object]:
        data = self.to_compact_dict()
        data["switch_reason"] = self.switch_reason
        data["diagnostic_checks"] = [
            check.to_dict() for check in self.diagnostic_checks
        ]
        data["requested_effects_summary"] = [
            effect.to_rich_dict() for effect in self.requested_effects_summary
        ]
        data["episode_id"] = self.episode_id
        data["backend_payload"] = dict(self.backend_payload)
        return data


class DecisionTraceAssembler:
    """Assemble decision trace records from result, payload, and metadata."""

    @staticmethod
    def assemble(
        *,
        result: PrimitiveDecisionResult,
        backend_payload: Mapping[str, object] | None,
        metadata: DecisionTraceMetadata,
    ) -> DecisionTraceRecord:
        fallback_type = str(metadata.fallback_type or "none")
        selected_operation = metadata.selected_operation or _selected_operation(result)
        trace_status = metadata.trace_status or _trace_status(fallback_type)
        return DecisionTraceRecord(
            backend_name=metadata.backend_name,
            backend_kind=metadata.backend_kind,
            decision_source=str(result.decision_source),
            decision_status=str(result.status),
            trace_status=trace_status,
            validation_status=metadata.validation_status,
            skill_before=str(result.skill_before),
            skill_after=str(result.skill_after),
            switch_reason=str(result.switch_reason),
            selected_operation=str(selected_operation),
            fallback_type=fallback_type,
            reason_codes=metadata.reason_codes,
            requested_effects_summary=tuple(
                DecisionEffectSummary.from_effect(effect)
                for effect in result.effects
            ),
            diagnostic_checks=metadata.diagnostic_checks,
            confidence=metadata.confidence,
            score=metadata.score,
            tick_id=metadata.tick_id,
            episode_id=metadata.episode_id,
            sim_time_s=metadata.sim_time_s,
            backend_payload=backend_payload or {},
        )


def assemble_legacy_fsm_decision_trace(
    *,
    result: PrimitiveDecisionResult,
    tick_id: str | None = None,
    episode_id: str | None = None,
    sim_time_s: float | None = None,
    confidence: float | None = None,
    score: float | None = None,
    trace_status: DecisionTraceStatus | None = None,
) -> DecisionTraceRecord:
    """Assemble a generic trace record for a legacy-FSM decision result."""

    payload = build_legacy_fsm_backend_payload(result)
    reason_code = (
        "legacy_fsm_compatibility_outcome"
        if result.side_effects_applied
        else "legacy_fsm_branch_selected"
    )
    return DecisionTraceAssembler.assemble(
        result=result,
        backend_payload=payload,
        metadata=DecisionTraceMetadata(
            backend_name=LEGACY_FSM_TRACE_BACKEND_NAME,
            backend_kind=LEGACY_FSM_TRACE_BACKEND_KIND,
            tick_id=tick_id,
            episode_id=episode_id,
            sim_time_s=sim_time_s,
            selected_operation=_selected_operation(result),
            fallback_type="none",
            reason_codes=(reason_code,),
            confidence=confidence,
            score=score,
            trace_status=trace_status,
        ),
    )


def assemble_behavior_tree_shadow_decision_trace(
    *,
    result: PrimitiveDecisionResult,
    node_trace: Sequence[object],
    tick_id: str | None = None,
    episode_id: str | None = None,
    sim_time_s: float | None = None,
    confidence: float | None = None,
    score: float | None = None,
    trace_status: DecisionTraceStatus | None = None,
) -> DecisionTraceRecord:
    """Assemble a generic trace record for the non-default BT shadow backend."""

    payload = build_behavior_tree_backend_payload(node_trace)
    selected_path = tuple(str(name) for name in payload["selected_path"])
    is_continue_fallback = (
        str(result.status) == "no_change"
        and bool(selected_path)
        and selected_path[-1] == "continue_current_skill"
    )
    fallback_type = "continue_current_skill" if is_continue_fallback else "none"
    reason_codes = ["bt_node_selected"] if payload["node_results"] else []
    if is_continue_fallback:
        reason_codes.append("bt_continue_fallback")
    return DecisionTraceAssembler.assemble(
        result=result,
        backend_payload=payload,
        metadata=DecisionTraceMetadata(
            backend_name=BEHAVIOR_TREE_SHADOW_TRACE_BACKEND_NAME,
            backend_kind=BEHAVIOR_TREE_TRACE_BACKEND_KIND,
            tick_id=tick_id,
            episode_id=episode_id,
            sim_time_s=sim_time_s,
            selected_operation=_selected_operation(result),
            fallback_type=fallback_type,
            reason_codes=tuple(reason_codes),
            confidence=confidence,
            score=score,
            trace_status=trace_status,
        ),
    )


def build_legacy_fsm_backend_payload(
    result: PrimitiveDecisionResult,
) -> dict[str, object]:
    """Build the legacy-FSM backend-specific trace payload from public fields."""

    decision_source = str(result.decision_source)
    payload_kind = (
        "compatibility_outcome"
        if result.side_effects_applied or decision_source == LEGACY_FSM_DECISION_SOURCE
        else "requested_branch"
    )
    if payload_kind == "requested_branch":
        branch_name = _LEGACY_FSM_BRANCH_BY_DECISION_SOURCE.get(
            decision_source,
            "unknown",
        )
    else:
        branch_name = "unknown"
    branch_order_index = _LEGACY_FSM_BRANCH_ORDER_INDEX.get(branch_name)
    effect_types = [str(effect.effect_type) for effect in result.effects]
    return {
        "backend_family": "legacy_fsm",
        "payload_schema_version": LEGACY_FSM_PAYLOAD_SCHEMA_VERSION,
        "payload_kind": payload_kind,
        "summary": f"{payload_kind}:{branch_name}:{result.status}",
        "branch_name": branch_name,
        "branch_order_index": branch_order_index,
        "decision_source": decision_source,
        "legacy_reason": str(result.switch_reason),
        "side_effects_applied": bool(result.side_effects_applied),
        "effect_types": effect_types,
    }


def build_behavior_tree_backend_payload(
    node_trace: Sequence[object],
) -> dict[str, object]:
    """Build a BT backend-specific payload without importing BT classes."""

    node_results = [_behavior_tree_node_result(node) for node in node_trace]
    root_status = str(node_results[0]["status"]) if node_results else "unknown"
    selected_path = [
        str(node["node_name"])
        for node in node_results
        if str(node["status"]) == "success"
    ]
    failed_conditions = [
        str(node["reason"])
        for node in node_results
        if str(node["status"]) == "failure" and str(node["reason"])
    ]
    summary = " > ".join(selected_path) if selected_path else root_status
    return {
        "backend_family": "behavior_tree",
        "payload_schema_version": BEHAVIOR_TREE_PAYLOAD_SCHEMA_VERSION,
        "payload_kind": "node_trace",
        "summary": summary,
        "root_status": root_status,
        "selected_path": selected_path,
        "node_results": node_results,
        "failed_conditions": failed_conditions,
    }


def diagnostic_checks_from_dig_status(
    status: object | None,
) -> tuple[DecisionDiagnosticCheck, ...]:
    """Map existing dig transition status fields into trace diagnostics."""

    if status is None:
        return _unknown_checks(
            (
                "dig_bad_replan_ready",
                "dig_exit_guard_ready",
                "dig_to_carry_ready",
            )
        )
    common_value = {
        "dig_step_count": _shape_value(status, "dig_step_count", 0),
        "mass_in_bucket_kg": _shape_value(status, "mass_in_bucket_kg", 0.0),
        "coverage_terminal_stop_requested": _shape_value(
            status,
            "coverage_terminal_stop_requested",
            False,
        ),
    }
    return (
        _diagnostic_from_bool(
            name="dig_bad_replan_ready",
            passed=bool(_shape_value(status, "dig_bad_replan_ready", False)),
            pass_reason="dig_bad_replan_ready",
            value=common_value,
        ),
        _diagnostic_from_bool(
            name="dig_exit_guard_ready",
            passed=bool(_shape_value(status, "dig_exit_guard_ready", False)),
            pass_reason="dig_exit_guard_ready",
            value=common_value,
        ),
        _diagnostic_from_bool(
            name="dig_to_carry_ready",
            passed=bool(_shape_value(status, "dig_to_carry_ready", False)),
            pass_reason=str(_shape_value(status, "dig_to_carry_reason", "")),
            value={
                "transition_mass_in_bucket_kg": _shape_value(
                    status,
                    "transition_mass_in_bucket_kg",
                    0.0,
                ),
                "transition_min_distance_to_dig_area_m": _shape_value(
                    status,
                    "transition_min_distance_to_dig_area_m",
                    0.0,
                ),
                "distance_ready": _shape_value(status, "distance_ready", False),
                "dig_complete_boundary": _shape_value(
                    status,
                    "dig_complete_boundary",
                    False,
                ),
                "dig_mass_plateau_ready": _shape_value(
                    status,
                    "dig_mass_plateau_ready",
                    False,
                ),
            },
        ),
    )


def diagnostic_checks_from_carry_status(
    status: object | None,
) -> tuple[DecisionDiagnosticCheck, ...]:
    """Map existing carry transition status fields into trace diagnostics."""

    if status is None:
        return _unknown_checks(("carry_dump_ready", "carry_return_ready"))
    return (
        _diagnostic_from_bool(
            name="carry_dump_ready",
            passed=bool(_shape_value(status, "ready_to_dump", False)),
            pass_reason=str(_shape_value(status, "carry_to_dump_reason", "")),
            value={
                "dump_ready": _shape_value(status, "dump_ready", False),
                "next_dump_ready_hold_count": _shape_value(
                    status,
                    "next_dump_ready_hold_count",
                    0,
                ),
                "ready_to_dump": _shape_value(status, "ready_to_dump", False),
                "dump_committed_event": _shape_value(
                    status,
                    "dump_committed_event",
                    False,
                ),
                "release_onset_event": _shape_value(
                    status,
                    "release_onset_event",
                    False,
                ),
                "legacy_dump_start_event": _shape_value(
                    status,
                    "legacy_dump_start_event",
                    False,
                ),
            },
        ),
        _diagnostic_from_bool(
            name="carry_return_ready",
            passed=bool(str(_shape_value(status, "carry_to_return_reason", ""))),
            pass_reason=str(_shape_value(status, "carry_to_return_reason", "")),
            value={
                "carry_release_safety_done": _shape_value(
                    status,
                    "carry_release_safety_done",
                    False,
                ),
                "dump_complete_event": _shape_value(
                    status,
                    "dump_complete_event",
                    False,
                ),
                "deposit_delta_since_cycle_start_kg": _shape_value(
                    status,
                    "deposit_delta_since_cycle_start_kg",
                    0.0,
                ),
            },
        ),
    )


def diagnostic_checks_from_dump_status(
    status: object | None,
) -> tuple[DecisionDiagnosticCheck, ...]:
    """Map existing dump transition status fields into trace diagnostics."""

    if status is None:
        return _unknown_checks(("dump_return_ready",))
    return (
        _diagnostic_from_bool(
            name="dump_return_ready",
            passed=bool(_shape_value(status, "ready_to_return", False)),
            pass_reason=str(_shape_value(status, "dump_to_return_reason", "")),
            value={
                "boundary_dump_done": _shape_value(
                    status,
                    "boundary_dump_done",
                    False,
                ),
                "dump_done_mass_low": _shape_value(
                    status,
                    "dump_done_mass_low",
                    False,
                ),
                "next_dump_done_hold_count": _shape_value(
                    status,
                    "next_dump_done_hold_count",
                    0,
                ),
                "coverage_completion_reason": _shape_value(
                    status,
                    "coverage_completion_reason",
                    "",
                ),
                "deposit_delta_since_dump_start_kg": _shape_value(
                    status,
                    "deposit_delta_since_dump_start_kg",
                    0.0,
                ),
            },
        ),
    )


def diagnostic_checks_from_return_status(
    status: object | None,
) -> tuple[DecisionDiagnosticCheck, ...]:
    """Map existing return transition status fields into trace diagnostics."""

    if status is None:
        return _unknown_checks(
            (
                "return_entry_close",
                "return_start_envelope_ready",
                "return_handoff_ready",
                "return_direct_handoff_ready",
                "return_shallow_guard_ready",
            )
        )
    shallow_reason = ""
    if bool(_shape_value(status, "shallow_guard_allowed", False)):
        shallow_reason = "shallow_guard_allowed"
    elif bool(_shape_value(status, "shallow_guard_ready", False)):
        shallow_reason = "shallow_guard_ready"
    return (
        _diagnostic_from_bool(
            name="return_entry_close",
            passed=bool(_shape_value(status, "entry_close", False)),
            pass_reason="entry_close",
            value={
                "min_distance_to_dig_area_m": _shape_value(
                    status,
                    "min_distance_to_dig_area_m",
                    0.0,
                ),
                "next_dig_event": _shape_value(status, "next_dig_event", False),
                "next_or_seen_dig_event": _shape_value(
                    status,
                    "next_or_seen_dig_event",
                    False,
                ),
            },
        ),
        _diagnostic_from_bool(
            name="return_start_envelope_ready",
            passed=bool(_shape_value(status, "start_envelope_ready", False)),
            pass_reason="start_envelope_ready",
            value={
                "bucket_depth_below_dig_area_plane_m": _shape_value(
                    status,
                    "bucket_depth_below_dig_area_plane_m",
                    0.0,
                ),
                "semantic_boundary_profile_active": _shape_value(
                    status,
                    "semantic_boundary_profile_active",
                    False,
                ),
            },
        ),
        _diagnostic_from_bool(
            name="return_handoff_ready",
            passed=bool(_shape_value(status, "handoff_ready", False)),
            pass_reason=str(_shape_value(status, "switch_reason", "")),
            value={
                "entry_close": _shape_value(status, "entry_close", False),
                "start_envelope_ready": _shape_value(
                    status,
                    "start_envelope_ready",
                    False,
                ),
                "completed_transition": _shape_value(
                    status,
                    "completed_transition",
                    False,
                ),
                "next_skill": _shape_value(status, "next_skill", ""),
            },
        ),
        _diagnostic_from_bool(
            name="return_direct_handoff_ready",
            passed=bool(_shape_value(status, "direct_handoff_ready", False)),
            pass_reason="direct_handoff_ready",
            value={
                "direct_handoff_ready": _shape_value(
                    status,
                    "direct_handoff_ready",
                    False,
                ),
                "mass_in_bucket_kg": _shape_value(
                    status,
                    "mass_in_bucket_kg",
                    0.0,
                ),
                "start_envelope_ready": _shape_value(
                    status,
                    "start_envelope_ready",
                    False,
                ),
            },
        ),
        _diagnostic_from_bool(
            name="return_shallow_guard_ready",
            passed=bool(_shape_value(status, "shallow_guard_ready", False)),
            pass_reason=shallow_reason,
            value={
                "shallow_guard_ready": _shape_value(
                    status,
                    "shallow_guard_ready",
                    False,
                ),
                "shallow_guard_allowed": _shape_value(
                    status,
                    "shallow_guard_allowed",
                    False,
                ),
                "mass_in_bucket_kg": _shape_value(
                    status,
                    "mass_in_bucket_kg",
                    0.0,
                ),
                "bucket_depth_below_dig_area_plane_m": _shape_value(
                    status,
                    "bucket_depth_below_dig_area_plane_m",
                    0.0,
                ),
            },
        ),
    )


def _selected_operation(result: PrimitiveDecisionResult) -> str:
    if str(result.status) == "skill_switch":
        return "switch_skill"
    if str(result.status) == "no_change" and not result.effects:
        return "continue_current_skill"
    return "unknown"


def _trace_status(fallback_type: str) -> DecisionTraceStatus:
    if str(fallback_type or "none") not in {"", "none"}:
        return "fallback"
    return "success"


def _json_safe_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {
        str(key): _json_safe_value(value[key])
        for key in sorted(value, key=lambda item: str(item))
    }


def _behavior_tree_node_result(node: object) -> dict[str, object]:
    return {
        "node_name": str(_value_from_shape(node, "node_name")),
        "status": str(_value_from_shape(node, "status")),
        "reason": str(_value_from_shape(node, "reason")),
    }


def _value_from_shape(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name, "")
    return getattr(value, name, "")


def _shape_value(value: object, name: str, default: object) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _diagnostic_from_bool(
    *,
    name: str,
    passed: bool,
    pass_reason: str,
    value: Mapping[str, object],
) -> DecisionDiagnosticCheck:
    return DecisionDiagnosticCheck(
        name=name,
        status="pass" if bool(passed) else "fail",
        reason=str(pass_reason) if bool(passed) else "",
        value=value,
    )


def _unknown_checks(names: Sequence[str]) -> tuple[DecisionDiagnosticCheck, ...]:
    return tuple(
        DecisionDiagnosticCheck(
            name=name,
            status="unknown",
            reason="status_unavailable",
            value=None,
        )
        for name in names
    )


def _json_safe_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)
    if isinstance(value, (set, frozenset)):
        return sorted((_json_safe_value(item) for item in value), key=repr)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe_value(item) for item in value]
    return repr(value)


__all__ = [
    "DECISION_TRACE_SCHEMA_VERSION",
    "BEHAVIOR_TREE_PAYLOAD_SCHEMA_VERSION",
    "BEHAVIOR_TREE_SHADOW_TRACE_BACKEND_NAME",
    "BEHAVIOR_TREE_TRACE_BACKEND_KIND",
    "DecisionDiagnosticCheck",
    "DecisionDiagnosticStatus",
    "DecisionEffectSummary",
    "DecisionTraceAssembler",
    "DecisionTraceMetadata",
    "DecisionTraceRecord",
    "DecisionTraceStatus",
    "DecisionValidationStatus",
    "LEGACY_FSM_PAYLOAD_SCHEMA_VERSION",
    "LEGACY_FSM_TRACE_BACKEND_KIND",
    "LEGACY_FSM_TRACE_BACKEND_NAME",
    "assemble_behavior_tree_shadow_decision_trace",
    "assemble_legacy_fsm_decision_trace",
    "build_behavior_tree_backend_payload",
    "build_legacy_fsm_backend_payload",
    "diagnostic_checks_from_carry_status",
    "diagnostic_checks_from_dig_status",
    "diagnostic_checks_from_dump_status",
    "diagnostic_checks_from_return_status",
]
