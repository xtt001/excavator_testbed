"""Planner evidence trace schema and conservative capability classifier."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class EvidenceTraceError(ValueError):
    """Raised when a planner evidence trace row is malformed."""


@dataclass(frozen=True)
class EvidenceEvent:
    tick_id: int
    capability_id: str
    event_type: str
    producer: str
    observed: bool = True
    consumed_by_decision: bool = False
    reported: bool = False
    supports: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "tick_id": int(self.tick_id),
            "capability_id": self.capability_id,
            "event_type": self.event_type,
            "producer": self.producer,
            "observed": bool(self.observed),
            "consumed_by_decision": bool(self.consumed_by_decision),
            "reported": bool(self.reported),
            "supports": list(self.supports),
            "payload": _jsonable(self.payload),
        }

    @classmethod
    def from_json(cls, row: dict[str, Any]) -> EvidenceEvent:
        for key in ("tick_id", "capability_id", "event_type", "producer"):
            if key not in row:
                raise EvidenceTraceError(f"missing evidence trace field: {key}")
        schema_version = int(row.get("schema_version", SCHEMA_VERSION))
        if schema_version != SCHEMA_VERSION:
            raise EvidenceTraceError(f"unsupported schema_version: {schema_version}")
        supports = row.get("supports", ())
        if supports is None:
            supports = ()
        if not isinstance(supports, (list, tuple)):
            raise EvidenceTraceError("supports must be a list")
        payload = row.get("payload", {})
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise EvidenceTraceError("payload must be an object")
        return cls(
            tick_id=int(row["tick_id"]),
            capability_id=str(row["capability_id"]),
            event_type=str(row["event_type"]),
            producer=str(row["producer"]),
            observed=bool(row.get("observed", True)),
            consumed_by_decision=bool(row.get("consumed_by_decision", False)),
            reported=bool(row.get("reported", False)),
            supports=tuple(str(item) for item in supports),
            payload=payload,
        )


@dataclass(frozen=True)
class CapabilitySpec:
    capability_id: str
    owner: str
    category: str
    owner_classification: str = ""
    protect_when_unobserved: bool = False
    description: str = ""


@dataclass(frozen=True)
class CapabilityClassification:
    capability_id: str
    owner: str
    category: str
    classification: str
    retention_decision: str
    observed_count: int
    consumed_by_decision_count: int
    reported_count: int
    supported_live_count: int
    first_tick_id: int | None
    last_tick_id: int | None
    producers: tuple[str, ...]
    reasons: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "owner": self.owner,
            "category": self.category,
            "classification": self.classification,
            "retention_decision": self.retention_decision,
            "observed_count": self.observed_count,
            "consumed_by_decision_count": self.consumed_by_decision_count,
            "reported_count": self.reported_count,
            "supported_live_count": self.supported_live_count,
            "first_tick_id": self.first_tick_id,
            "last_tick_id": self.last_tick_id,
            "producers": list(self.producers),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class EvidenceClassificationReport:
    rows: tuple[CapabilityClassification, ...]
    event_count: int
    evidence_packet_count: int
    dead_candidate_min_packets: int

    def to_json(self) -> dict[str, Any]:
        counts: dict[str, int] = defaultdict(int)
        for row in self.rows:
            counts[row.classification] += 1
        return {
            "schema_version": SCHEMA_VERSION,
            "event_count": self.event_count,
            "evidence_packet_count": self.evidence_packet_count,
            "dead_candidate_min_packets": self.dead_candidate_min_packets,
            "classification_counts": dict(sorted(counts.items())),
            "rows": [row.to_json() for row in self.rows],
        }

    def to_markdown(self) -> str:
        lines = [
            "# Planner Evidence Classification Report",
            "",
            f"- event_count: {self.event_count}",
            f"- evidence_packet_count: {self.evidence_packet_count}",
            f"- dead_candidate_min_packets: {self.dead_candidate_min_packets}",
            "",
            "| classification | retention | capability | owner | observed | decision | reported |",
            "| --- | --- | --- | --- | ---: | ---: | ---: |",
        ]
        for row in self.rows:
            lines.append(
                "| "
                f"{row.classification} | "
                f"{row.retention_decision} | "
                f"`{row.capability_id}` | "
                f"`{row.owner}` | "
                f"{row.observed_count} | "
                f"{row.consumed_by_decision_count} | "
                f"{row.reported_count} |"
            )
        lines.append("")
        return "\n".join(lines)


BASELINE_CAPABILITY_SPECS: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        "execution.predict_tick",
        "PrimitivePlannerACTPolicy.predict",
        "execution",
        description="Public planner tick execution entry.",
    ),
    CapabilitySpec(
        "fsm.skill_switch",
        "PrimitivePlannerACTPolicy._maybe_switch_skill/_set_skill",
        "decision",
        description="Inline baseline FSM skill and switch-reason logic.",
    ),
    CapabilitySpec(
        "action.dispatch",
        "PrimitivePlannerACTPolicy.predict/_active_policy",
        "execution",
        description="Scripted, pre-dig-align, or low-level ACT action dispatch.",
    ),
    CapabilitySpec(
        "token.goal",
        "PrimitiveTokenPlannerFactory.goal_tokens_for_cycle/PrimitiveTokenObservationRuntime.policy_obs",
        "token",
    ),
    CapabilitySpec(
        "token.cell_entry",
        "removed primitive-planner cell-entry runtime (data/schema compatibility only)",
        "compatibility",
        owner_classification="removed-runtime",
    ),
    CapabilitySpec(
        "token.dig_cut",
        "PrimitivePlannerACTPolicy._ensure_dig_cut_plan_for_cycle",
        "token",
    ),
    CapabilitySpec(
        "token.dig_depth_profile",
        "PrimitivePlannerACTPolicy._dig_depth_profile_tokens_for_obs",
        "token",
    ),
    CapabilitySpec(
        "token.return_target",
        "PrimitivePlannerACTPolicy._ensure_return_target_plan_for_cycle",
        "token",
    ),
    CapabilitySpec(
        "token.return_relocate",
        "PrimitivePlannerACTPolicy._return_relocate_tokens_for_obs",
        "token",
    ),
    CapabilitySpec(
        "token.return_start_envelope",
        "PrimitivePlannerACTPolicy._return_start_envelope_tokens_for_obs",
        "token",
    ),
    CapabilitySpec(
        "gate.pre_dig_align",
        "PrimitivePlannerACTPolicy._maybe_switch_skill/pre_dig_align",
        "gate",
    ),
    CapabilitySpec(
        "metric.dig_progress",
        "PrimitivePlannerACTPolicy._update_dig_progress",
        "metric",
    ),
    CapabilitySpec(
        "gate.dig_to_carry",
        "PrimitivePlannerACTPolicy._maybe_switch_skill/dig",
        "gate",
    ),
    CapabilitySpec(
        "gate.carry_to_dump",
        "PrimitivePlannerACTPolicy._maybe_switch_skill/carry",
        "gate",
    ),
    CapabilitySpec(
        "gate.dump_to_return",
        "PrimitivePlannerACTPolicy._maybe_switch_skill/dump",
        "gate",
    ),
    CapabilitySpec(
        "gate.return_to_dig",
        "PrimitivePlannerACTPolicy._maybe_switch_skill/return",
        "gate",
    ),
    CapabilitySpec(
        "coverage.corridor",
        "PrimitivePlannerACTPolicy coverage corridor helpers",
        "coverage",
    ),
    CapabilitySpec(
        "debug.debug_state",
        "PrimitivePlannerACTPolicy.debug_state/_make_debug_state",
        "report",
    ),
    CapabilitySpec(
        "report.rollout_summary",
        "PrimitivePlannerACTPolicy.rollout_summary",
        "report",
    ),
    CapabilitySpec(
        "trace.planner_trace",
        "PrimitivePlannerACTPolicy.planner_trace",
        "report",
    ),
    CapabilitySpec(
        "policy.public_adapter",
        "PrimitivePlannerACTPolicy",
        "compatibility",
        owner_classification="compatibility",
    ),
    CapabilitySpec(
        "compat.5p_policy",
        "removed 5P runtime planner (git history only)",
        "compatibility",
        owner_classification="removed-runtime",
    ),
)


def write_evidence_jsonl(path: Path, events: Iterable[EvidenceEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event.to_json(), sort_keys=True, allow_nan=False))
            f.write("\n")


def read_evidence_jsonl(path: Path) -> list[EvidenceEvent]:
    events: list[EvidenceEvent] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                events.append(EvidenceEvent.from_json(row))
            except (json.JSONDecodeError, EvidenceTraceError) as exc:
                raise EvidenceTraceError(f"{path}:{line_number}: {exc}") from exc
    return events


def read_rollout_jsonl_events(path: Path) -> list[EvidenceEvent]:
    events: list[EvidenceEvent] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvidenceTraceError(f"{path}:{line_number}: {exc}") from exc
            events.extend(events_from_rollout_row(row))
    return events


def events_from_rollout_row(row: dict[str, Any]) -> list[EvidenceEvent]:
    tick_id = int(row.get("t", row.get("tick_id", row.get("step_id", -1))))
    skill = str(row.get("skill_name", ""))
    switch_reason = str(row.get("skill_switch_reason", ""))
    events: list[EvidenceEvent] = []

    events.append(
        EvidenceEvent(
            tick_id=tick_id,
            capability_id="execution.predict_tick",
            event_type="execution",
            producer="PrimitivePlannerACTPolicy.predict",
            consumed_by_decision=True,
            reported=True,
            payload={
                "skill_name": skill,
                "step_id": row.get("step_id"),
                "transition_timeout": bool(row.get("transition_timeout", False)),
                "transition_completed": bool(row.get("transition_completed", False)),
            },
        )
    )
    events.append(
        EvidenceEvent(
            tick_id=tick_id,
            capability_id="fsm.skill_switch",
            event_type="decision",
            producer="PrimitivePlannerACTPolicy._maybe_switch_skill/_set_skill",
            consumed_by_decision=bool(skill),
            reported=True,
            payload={"skill_name": skill, "switch_reason": switch_reason},
        )
    )
    if "action" in row:
        events.append(
            EvidenceEvent(
                tick_id=tick_id,
                capability_id="action.dispatch",
                event_type="action",
                producer="PrimitivePlannerACTPolicy.predict/_active_policy",
                consumed_by_decision=True,
                reported=True,
                payload={
                    "action_source": _infer_action_source(skill),
                    "skill_name": skill,
                },
            )
        )

    if "goal_tokens" in row:
        events.append(
            _token_event(
                tick_id,
                "token.goal",
                "PrimitiveTokenPlannerFactory.goal_tokens_for_cycle/PrimitiveTokenObservationRuntime.policy_obs",
                source="goal_tokens",
                injected=True,
                supports=("action.dispatch",),
            )
        )
    _append_token_event(
        events,
        row=row,
        tick_id=tick_id,
        capability_id="token.dig_cut",
        producer="PrimitivePlannerACTPolicy._ensure_dig_cut_plan_for_cycle",
        injected_key="dig_cut_token_injected",
        source_key="dig_cut_token_source",
        supports=("gate.dig_to_carry", "coverage.corridor"),
    )
    _append_token_event(
        events,
        row=row,
        tick_id=tick_id,
        capability_id="token.dig_depth_profile",
        producer="PrimitivePlannerACTPolicy._dig_depth_profile_tokens_for_obs",
        injected_key="dig_depth_profile_token_injected",
        source_key="dig_depth_profile_token_source",
        supports=("gate.dig_to_carry", "coverage.corridor"),
    )
    _append_token_event(
        events,
        row=row,
        tick_id=tick_id,
        capability_id="token.return_target",
        producer="PrimitivePlannerACTPolicy._ensure_return_target_plan_for_cycle",
        injected_key="return_target_token_injected",
        source_key="return_target_token_source",
        supports=("gate.return_to_dig",),
    )
    _append_token_event(
        events,
        row=row,
        tick_id=tick_id,
        capability_id="token.return_relocate",
        producer="PrimitivePlannerACTPolicy._return_relocate_tokens_for_obs",
        injected_key="return_relocate_token_injected",
        source_key="return_relocate_token_source",
        supports=("gate.return_to_dig",),
    )
    _append_token_event(
        events,
        row=row,
        tick_id=tick_id,
        capability_id="token.return_start_envelope",
        producer="PrimitivePlannerACTPolicy._return_start_envelope_tokens_for_obs",
        injected_key="return_start_envelope_token_injected",
        source_key="return_start_envelope_token_source",
        supports=("gate.return_to_dig",),
    )

    if _pre_dig_align_observed(row, skill, switch_reason):
        events.append(
            EvidenceEvent(
                tick_id=tick_id,
                capability_id="gate.pre_dig_align",
                event_type="gate",
                producer="PrimitivePlannerACTPolicy._maybe_switch_skill/pre_dig_align",
                consumed_by_decision=True,
                reported=True,
                payload={
                    "skill_name": skill,
                    "switch_reason": switch_reason,
                    "entry_error_m": row.get("pre_dig_align_entry_error_m"),
                    "completed_count": row.get("pre_dig_align_completed_count"),
                    "timeout_count": row.get("pre_dig_align_timeout_count"),
                },
            )
        )
    if _dig_progress_observed(row, skill):
        events.append(
            EvidenceEvent(
                tick_id=tick_id,
                capability_id="metric.dig_progress",
                event_type="metric",
                producer="PrimitivePlannerACTPolicy._update_dig_progress",
                reported=True,
                supports=("gate.dig_to_carry",),
                payload={
                    "dig_step_count": row.get("dig_step_count"),
                    "dig_best_mass_kg": row.get("dig_best_mass_kg"),
                    "dig_mass_plateau_count": row.get("dig_mass_plateau_count"),
                },
            )
        )
    if _dig_to_carry_observed(row, skill, switch_reason):
        events.append(
            EvidenceEvent(
                tick_id=tick_id,
                capability_id="gate.dig_to_carry",
                event_type="gate",
                producer="PrimitivePlannerACTPolicy._maybe_switch_skill/dig",
                consumed_by_decision=bool(
                    skill == "dig"
                    or switch_reason.startswith("dig_to_carry_")
                    or row.get("dig_to_carry_reason")
                ),
                reported=True,
                payload={
                    "skill_name": skill,
                    "switch_reason": switch_reason,
                    "dig_to_carry_reason": row.get("dig_to_carry_reason"),
                },
            )
        )
    if _carry_to_dump_observed(row, skill, switch_reason):
        events.append(
            EvidenceEvent(
                tick_id=tick_id,
                capability_id="gate.carry_to_dump",
                event_type="gate",
                producer="PrimitivePlannerACTPolicy._maybe_switch_skill/carry",
                consumed_by_decision=bool(
                    skill == "carry" or switch_reason.startswith("carry_to_dump_")
                ),
                reported=True,
                payload={
                    "skill_name": skill,
                    "switch_reason": switch_reason,
                    "dump_ready_hold_count": row.get("dump_ready_hold_count"),
                    "dump_start_mask": row.get("dump_start_mask"),
                },
            )
        )
    if _dump_to_return_observed(row, skill, switch_reason):
        events.append(
            EvidenceEvent(
                tick_id=tick_id,
                capability_id="gate.dump_to_return",
                event_type="gate",
                producer="PrimitivePlannerACTPolicy._maybe_switch_skill/dump",
                consumed_by_decision=bool(
                    skill == "dump"
                    or switch_reason.startswith(("dump_to_", "dump_done_"))
                ),
                reported=True,
                payload={
                    "skill_name": skill,
                    "switch_reason": switch_reason,
                    "dump_done_hold_count": row.get("dump_done_hold_count"),
                    "dump_end_mask": row.get("dump_end_mask"),
                },
            )
        )
    if _return_to_dig_observed(row, skill, switch_reason):
        events.append(
            EvidenceEvent(
                tick_id=tick_id,
                capability_id="gate.return_to_dig",
                event_type="gate",
                producer="PrimitivePlannerACTPolicy._maybe_switch_skill/return",
                consumed_by_decision=bool(
                    skill == "return" or switch_reason.startswith("return_to_")
                ),
                reported=True,
                payload={
                    "skill_name": skill,
                    "switch_reason": switch_reason,
                    "entry_close": row.get("return_to_dig_entry_close"),
                    "entry_error_m": row.get("return_to_dig_entry_error_m"),
                },
            )
        )
    if _coverage_observed(row):
        events.append(
            EvidenceEvent(
                tick_id=tick_id,
                capability_id="coverage.corridor",
                event_type="coverage",
                producer="PrimitivePlannerACTPolicy coverage corridor helpers",
                consumed_by_decision=True,
                reported=True,
                supports=("token.dig_cut", "gate.pre_dig_align"),
                payload={
                    "corridor_id": row.get("coverage_corridor_id"),
                    "terminal_stop_requested": row.get(
                        "coverage_terminal_stop_requested"
                    ),
                    "terminal_stop_reason": row.get("coverage_terminal_stop_reason"),
                    "depleted_count": row.get("coverage_depleted_count"),
                },
            )
        )

    if "skill_name" in row:
        events.append(
            EvidenceEvent(
                tick_id=tick_id,
                capability_id="debug.debug_state",
                event_type="report",
                producer="PrimitivePlannerACTPolicy.debug_state/_make_debug_state",
                reported=True,
                payload={"debug_key_count": len(row)},
            )
        )
    return events


def events_from_planner_trace(trace: dict[str, Any], *, tick_id: int = -1) -> list[EvidenceEvent]:
    events: list[EvidenceEvent] = []
    if not trace:
        return events
    if "coverage_corridors" in trace:
        events.append(
            EvidenceEvent(
                tick_id=tick_id,
                capability_id="coverage.corridor",
                event_type="coverage",
                producer="PrimitivePlannerACTPolicy.planner_trace/coverage",
                consumed_by_decision=bool(trace.get("coverage_corridors")),
                reported=True,
                payload={
                    "coverage_corridor_count": len(trace.get("coverage_corridors") or []),
                    "terminal_stop_requested": trace.get(
                        "coverage_terminal_stop_requested"
                    ),
                    "terminal_stop_reason": trace.get("coverage_terminal_stop_reason"),
                },
            )
        )
    events.append(
        EvidenceEvent(
            tick_id=tick_id,
            capability_id="trace.planner_trace",
            event_type="report",
            producer="PrimitivePlannerACTPolicy.planner_trace",
            reported=True,
            payload={"trace_keys": sorted(str(key) for key in trace.keys())},
        )
    )
    return events


def events_from_rollout_summary(
    summary: dict[str, Any],
    *,
    tick_id: int = -1,
) -> list[EvidenceEvent]:
    if not summary:
        return []
    events = [
        EvidenceEvent(
            tick_id=tick_id,
            capability_id="report.rollout_summary",
            event_type="report",
            producer="PrimitivePlannerACTPolicy.rollout_summary",
            reported=True,
            payload={
                "summary_keys": sorted(str(key) for key in summary.keys()),
                "primitive_final_skill": summary.get("primitive_final_skill"),
                "primitive_cycle_index": summary.get("primitive_cycle_index"),
                "completed_transition_count": summary.get(
                    "completed_transition_count"
                ),
            },
        )
    ]
    if (
        "coverage_terminal_stop_requested" in summary
        or "coverage_terminal_stop_reason" in summary
    ):
        events.append(
            EvidenceEvent(
                tick_id=tick_id,
                capability_id="coverage.corridor",
                event_type="coverage",
                producer="PrimitivePlannerACTPolicy.rollout_summary/coverage",
                consumed_by_decision=bool(
                    summary.get("coverage_terminal_stop_requested")
                    or summary.get("coverage_terminal_stop_reason")
                ),
                reported=True,
                payload={
                    "terminal_stop_requested": summary.get(
                        "coverage_terminal_stop_requested"
                    ),
                    "terminal_stop_reason": summary.get(
                        "coverage_terminal_stop_reason"
                    ),
                    "completed_dump_count": summary.get(
                        "coverage_completed_dump_count"
                    ),
                },
            )
        )
    return events


def classify_evidence(
    events: Iterable[EvidenceEvent],
    specs: Sequence[CapabilitySpec] = BASELINE_CAPABILITY_SPECS,
    *,
    evidence_packet_count: int = 1,
    dead_candidate_min_packets: int = 1,
) -> EvidenceClassificationReport:
    event_list = [event for event in events if event.observed]
    events_by_id: dict[str, list[EvidenceEvent]] = defaultdict(list)
    for event in event_list:
        events_by_id[event.capability_id].append(event)

    confirmed_ids = {
        capability_id
        for capability_id, rows in events_by_id.items()
        if any(row.consumed_by_decision for row in rows)
    }
    rows: list[CapabilityClassification] = []
    for spec in specs:
        rows_for_spec = events_by_id.get(spec.capability_id, [])
        supported_live = [
            row
            for row in rows_for_spec
            if any(supported_id in confirmed_ids for supported_id in row.supports)
        ]
        classification = _classification_for_spec(
            spec,
            rows_for_spec,
            supported_live=supported_live,
            evidence_packet_count=evidence_packet_count,
            dead_candidate_min_packets=dead_candidate_min_packets,
        )
        tick_ids = [row.tick_id for row in rows_for_spec]
        rows.append(
            CapabilityClassification(
                capability_id=spec.capability_id,
                owner=spec.owner,
                category=spec.category,
                classification=classification,
                retention_decision=_retention_decision(classification),
                observed_count=len(rows_for_spec),
                consumed_by_decision_count=sum(
                    1 for row in rows_for_spec if row.consumed_by_decision
                ),
                reported_count=sum(1 for row in rows_for_spec if row.reported),
                supported_live_count=len(supported_live),
                first_tick_id=min(tick_ids) if tick_ids else None,
                last_tick_id=max(tick_ids) if tick_ids else None,
                producers=tuple(sorted({row.producer for row in rows_for_spec})),
                reasons=_reasons(rows_for_spec),
            )
        )

    return EvidenceClassificationReport(
        rows=tuple(rows),
        event_count=len(event_list),
        evidence_packet_count=int(evidence_packet_count),
        dead_candidate_min_packets=int(dead_candidate_min_packets),
    )


def write_report_json(path: Path, report: EvidenceClassificationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_json(), indent=2, sort_keys=True), encoding="utf-8")


def write_report_markdown(path: Path, report: EvidenceClassificationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_markdown(), encoding="utf-8")


def _classification_for_spec(
    spec: CapabilitySpec,
    rows: list[EvidenceEvent],
    *,
    supported_live: list[EvidenceEvent],
    evidence_packet_count: int,
    dead_candidate_min_packets: int,
) -> str:
    if spec.owner_classification:
        return spec.owner_classification
    if any(row.consumed_by_decision for row in rows):
        return "confirmed-live"
    if supported_live:
        return "support-live"
    if any(row.reported for row in rows):
        return "report-only"
    if spec.protect_when_unobserved:
        return "not-observed"
    if evidence_packet_count >= dead_candidate_min_packets:
        return "dead-candidate"
    return "not-observed"


def _retention_decision(classification: str) -> str:
    if classification in {"confirmed-live", "support-live"}:
        return "retain-and-migrate"
    if classification == "report-only":
        return "retain-report-boundary"
    if classification == "compatibility":
        return "retain-compatibility"
    if classification == "test-only":
        return "retain-test-only"
    if classification == "removed-runtime":
        return "removed-runtime-cleanup"
    if classification == "dead-candidate":
        return "retain-legacy-parking"
    return "hold-unobserved"


def _reasons(rows: list[EvidenceEvent]) -> tuple[str, ...]:
    values: set[str] = set()
    for row in rows:
        for key in (
            "switch_reason",
            "reason",
            "source",
            "terminal_stop_reason",
            "dig_to_carry_reason",
        ):
            value = row.payload.get(key)
            if value is None or value == "":
                continue
            values.add(str(value))
    return tuple(sorted(values))


def _append_token_event(
    events: list[EvidenceEvent],
    *,
    row: dict[str, Any],
    tick_id: int,
    capability_id: str,
    producer: str,
    injected_key: str,
    source_key: str,
    supports: tuple[str, ...],
) -> None:
    if injected_key not in row and source_key not in row:
        return
    source = str(row.get(source_key, ""))
    injected = bool(row.get(injected_key, False))
    if not injected and source in ("", "none", "None"):
        return
    events.append(
        _token_event(
            tick_id,
            capability_id,
            producer,
            source=source,
            injected=injected,
            supports=supports,
        )
    )


def _token_event(
    tick_id: int,
    capability_id: str,
    producer: str,
    *,
    source: str,
    injected: bool,
    supports: tuple[str, ...],
) -> EvidenceEvent:
    return EvidenceEvent(
        tick_id=tick_id,
        capability_id=capability_id,
        event_type="token",
        producer=producer,
        consumed_by_decision=True,
        reported=True,
        supports=supports,
        payload={"source": source, "injected": bool(injected)},
    )


def _pre_dig_align_observed(
    row: dict[str, Any],
    skill: str,
    switch_reason: str,
) -> bool:
    return (
        skill == "pre_dig_align"
        or "pre_dig_align" in switch_reason
        or _truthy_number(row.get("pre_dig_align_completed_count"))
        or _truthy_number(row.get("pre_dig_align_timeout_count"))
        or _finite_number(row.get("pre_dig_align_entry_error_m"))
    )


def _dig_progress_observed(row: dict[str, Any], skill: str) -> bool:
    return (
        skill == "dig"
        or _truthy_number(row.get("dig_step_count"))
        or _truthy_number(row.get("dig_best_mass_kg"))
        or _truthy_number(row.get("dig_mass_plateau_count"))
    )


def _dig_to_carry_observed(
    row: dict[str, Any],
    skill: str,
    switch_reason: str,
) -> bool:
    return (
        skill == "dig"
        or switch_reason.startswith("dig_to_carry_")
        or bool(row.get("dig_to_carry_reason"))
    )


def _carry_to_dump_observed(
    row: dict[str, Any],
    skill: str,
    switch_reason: str,
) -> bool:
    return (
        skill == "carry"
        or switch_reason.startswith("carry_to_dump_")
        or _truthy_number(row.get("dump_ready_hold_count"))
        or _truthy_number(row.get("dump_start_mask"))
    )


def _dump_to_return_observed(
    row: dict[str, Any],
    skill: str,
    switch_reason: str,
) -> bool:
    return (
        skill == "dump"
        or switch_reason.startswith(("dump_to_", "dump_done_"))
        or _truthy_number(row.get("dump_done_hold_count"))
        or _truthy_number(row.get("dump_end_mask"))
    )


def _return_to_dig_observed(
    row: dict[str, Any],
    skill: str,
    switch_reason: str,
) -> bool:
    return (
        skill == "return"
        or switch_reason.startswith("return_to_")
        or _finite_number(row.get("return_to_dig_entry_error_m"))
        or "return_to_dig_entry_close" in row
    )


def _coverage_observed(row: dict[str, Any]) -> bool:
    corridor_id = row.get("coverage_corridor_id")
    return (
        _truthy_number(row.get("coverage_terminal_stop_requested"))
        or _truthy_number(row.get("coverage_depleted_count"))
        or _finite_number(row.get("coverage_corridor_score"))
        or (isinstance(corridor_id, int) and corridor_id >= 0)
    )


def _infer_action_source(skill: str) -> str:
    if skill == "bootstrap":
        return "scripted_bootstrap"
    if skill == "pre_dig_align":
        return "pre_dig_align"
    return "act_policy"


def _truthy_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and abs(number) > 0.0


def _finite_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
