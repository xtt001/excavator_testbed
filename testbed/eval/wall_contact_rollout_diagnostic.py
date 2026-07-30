"""Evidence contract for one observe-only multi-shovel wall-contact rollout.

This module is deliberately an offline owner.  It validates the canonical
rollout JSONL after execution and summarizes what happened; it does not make
online safety decisions or promote the diagnostic result into production.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from testbed.data.schema import (
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.wall_contact_evidence_contracts import (
    CONTACT_DETAIL_WARNING_PREFIX,
    ContactEvidenceContractError,
    parse_worktool_wall_contact_detail,
)
from testbed.eval.wall_contact_rollout_safety_evidence import (
    BUCKET_TIP_PROGRESS_M,
    QPOS_PROGRESS_M,
    TANGENTIAL_PROGRESS_M,
    WallContactSafetyEvidenceError,
    build_contact_motion_summary,
    require_independent_contact_hard_stop_chain,
    require_unsafe_terminal_chain,
)
from testbed.planner.box_emptying.wall_contact_detail import (
    WALL_CONTACT_HARD_MAX_FORCE_N,
)

REPORT_SCHEMA = "wall_contact_observe_only_multicycle_report_v1"
OBSERVE_ONLY_MODE = "record_bucket_all_contacts"
MAX_DIAGNOSTIC_SHOVELS = 10

_OBSERVE_ONLY_SIDE_EFFECT_FIELDS = (
    "box_safety_awaiting_neutral_ack",
    "box_safety_neutral_acknowledged",
    "box_safety_replan",
    "box_safety_terminal",
    "box_safety_policy_restarted",
)


class WallContactRolloutDiagnosticError(RuntimeError):
    """Raised when a diagnostic rollout cannot be trusted."""


def build_wall_contact_rollout_report(
    *,
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    max_shovels: int = MAX_DIAGNOSTIC_SHOVELS,
) -> dict[str, Any]:
    """Validate and summarize one diagnostic-only closed-loop rollout."""

    shovel_limit = _max_shovels(max_shovels)
    normalized_rows = _rows(rows)
    normalized_summary = _mapping(summary, "rollout_summary")
    _validate_debug_lineage(normalized_rows)

    contacts, contact_by_row = _contact_details(normalized_rows)
    unsafe_events = [
        {
            "step_id": int(contact["step_id"]),
            "cycle_id": int(contact["cycle_id"]),
            "reason": str(contact["unsafe_reason"]),
            "components": list(contact["components"]),
            "walls": list(contact["walls"]),
            "terminal_chain": dict(contact["terminal_chain"]),
        }
        for contact in contacts
        if contact["unsafe_reason"]
    ]
    cycle_ids = _cycle_ids(normalized_rows, shovel_limit)
    shovels = [
        _summarize_shovel(
            cycle_id=cycle_id,
            rows=[
                row
                for row in normalized_rows
                if _cycle(row) == cycle_id
            ],
            contacts=[
                contact
                for contact in contacts
                if int(contact["cycle_id"]) == cycle_id
            ],
        )
        for cycle_id in cycle_ids
    ]

    completed_dump_count = sum(
        int(shovel["dump_completed"]) for shovel in shovels
    )
    _validate_summary_dump_count(
        normalized_summary,
        completed_dump_count=completed_dump_count,
    )
    terminal_neutral = _terminal_neutral_evidence(normalized_rows)
    stop_reason = str(normalized_summary.get("rollout_stop_reason", "")).strip()
    outcome = _outcome(
        completed_dump_count=completed_dump_count,
        max_shovels=shovel_limit,
        stop_reason=stop_reason,
        terminal_neutral=terminal_neutral,
    )
    hard_stop_reasons = _hard_stop_reasons(
        rows=normalized_rows,
        contacts=contacts,
        stop_reason=stop_reason,
    )
    neutral_owned_stop = bool(
        stop_reason.startswith("box_safety:")
        or terminal_neutral["terminal_observed"]
    )
    if neutral_owned_stop and not terminal_neutral["acknowledged"]:
        raise WallContactRolloutDiagnosticError(
            "hard_stop_terminal_neutral_ack_missing"
        )

    contact_tick_count = len(contact_by_row)
    return {
        "schema": REPORT_SCHEMA,
        "status": "passed",
        "outcome": outcome,
        "diagnostic_only": True,
        "non_promotable": True,
        "production_promotion_allowed": False,
        "writes_training_hdf5": False,
        "max_shovels": shovel_limit,
        "started_shovel_count": len(shovels),
        "completed_dump_count": completed_dump_count,
        "partial_shovel_count": sum(
            int(not bool(shovel["dump_completed"])) for shovel in shovels
        ),
        "contact_tick_count": contact_tick_count,
        "contact_observed": bool(contact_tick_count),
        "unsafe_contact_events": unsafe_events,
        "side_effect_free_allowed_contact_every_tick": all(
            bool(contact["observe_only_side_effect_free"])
            for contact in contacts
            if bool(contact["eligible_observe_only_bucket_contact"])
        ),
        "hard_stop_reasons": hard_stop_reasons,
        "rollout_stop_reason": stop_reason,
        "terminal_neutral": terminal_neutral,
        "motion_progress_thresholds": {
            "qpos_max_axis_range": QPOS_PROGRESS_M,
            "bucket_tip_max_displacement_m": BUCKET_TIP_PROGRESS_M,
            "max_tangential_displacement_m": TANGENTIAL_PROGRESS_M,
        },
        "force_statistics_semantics": (
            "RMS values are over per-contact-tick pair maxima"
        ),
        "normal_impulse_semantics": (
            "per-shovel total uses cumulative Unity session impulse deltas; "
            "component-wall values use step-peak-normal-force times dt proxy"
        ),
        "shovels": shovels,
    }


def _rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        raise WallContactRolloutDiagnosticError("rollout_rows_invalid")
    if not rows:
        raise WallContactRolloutDiagnosticError("rollout_rows_empty")
    result: list[dict[str, Any]] = []
    previous_step: int | None = None
    for index, raw in enumerate(rows):
        row = dict(_mapping(raw, f"row_{index}"))
        step = _integer(row.get("step_id"), f"row_{index}.step_id", minimum=0)
        if previous_step is not None and step <= previous_step:
            raise WallContactRolloutDiagnosticError(
                "rollout_step_lineage_invalid"
            )
        previous_step = step
        _finite_vector(row.get("qpos"), 4, f"row_{index}.qpos")
        _finite_vector(row.get("qvel"), 4, f"row_{index}.qvel")
        _finite_vector(row.get("action"), 4, f"row_{index}.action")
        _finite_vector(
            row.get("env_state"),
            ENV_STATE_V2_4_DIM,
            f"row_{index}.env_state",
        )
        result.append(row)
    return result


def _validate_debug_lineage(rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        if (
            row.get(
                "box_safety_wall_contact_diagnostic_observe_only_enabled"
            )
            is not True
            or row.get("box_safety_wall_contact_diagnostic_ab_enabled")
            is not False
            or str(row.get("box_safety_wall_first_touch_mode", ""))
            != OBSERVE_ONLY_MODE
        ):
            raise WallContactRolloutDiagnosticError(
                "observe_only_debug_lineage_invalid"
            )


def _contact_details(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    contacts: list[dict[str, Any]] = []
    by_row: dict[int, dict[str, Any]] = {}
    last_session_count = 0
    last_contact_detail: dict[str, Any] | None = None
    last_contact_row_index = -1
    session_last_impulse: dict[int, float] = {}
    session_unsafe_reasons: dict[int, str] = {}
    session_terminal_chains: dict[int, dict[str, Any]] = {}
    decision_offset: int | None = None

    for row_index, row in enumerate(rows):
        env = _finite_vector(row.get("env_state"), ENV_STATE_V2_4_DIM, f"row_{row_index}.env_state")
        wall_positive = (
            env[ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX] >= 0.5
        )
        warnings = row.get("warnings", ())
        warnings_valid = not isinstance(warnings, (str, bytes)) and isinstance(
            warnings, Sequence
        )
        warning_values = list(warnings) if warnings_valid else []
        sidecar_count = sum(
            isinstance(value, str)
            and value.startswith(CONTACT_DETAIL_WARNING_PREFIX)
            for value in warning_values
        )
        aggregate_force = env[
            ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX
        ]
        try:
            aggregate_sessions = _integer_float(
                env[ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX],
                f"row_{row_index}.wall_session_count",
                minimum=0,
            )
        except WallContactRolloutDiagnosticError:
            aggregate_sessions = -1
        contact_free_valid = bool(
            not wall_positive
            and warnings_valid
            and sidecar_count == 0
            and abs(aggregate_force) <= 1.0e-6
            and aggregate_sessions in {0, last_session_count}
        )
        if contact_free_valid:
            continue

        detail: dict[str, Any] | None = None
        lineage_valid = bool(
            wall_positive
            and warnings_valid
            and sidecar_count == 1
            and aggregate_sessions >= last_session_count
            and aggregate_sessions <= last_session_count + 1
        )
        try:
            if lineage_valid:
                detail = parse_worktool_wall_contact_detail(warning_values)
                _validate_contact_row_lineage(
                    row=row,
                    detail=detail,
                    aggregate_force=aggregate_force,
                    aggregate_sessions=aggregate_sessions,
                )
                _validate_session_progression(
                    detail=detail,
                    previous_detail=last_contact_detail,
                    clear_tick_count=(
                        0
                        if last_contact_detail is None
                        else row_index - last_contact_row_index - 1
                    ),
                )
        except (ContactEvidenceContractError, WallContactRolloutDiagnosticError):
            lineage_valid = False

        components = (
            []
            if detail is None
            else sorted({str(pair["component"]) for pair in detail["pairs"]})
        )
        walls = (
            []
            if detail is None
            else sorted({str(pair["wall_name"]) for pair in detail["pairs"]})
        )
        forces = (
            []
            if detail is None
            else [
                float(value)
                for pair in detail["pairs"]
                for value in (
                    pair["max_normal_force_n"],
                    pair["max_tangential_force_n"],
                    pair["max_total_force_n"],
                )
            ]
        )
        impulse = (
            math.nan
            if detail is None
            else float(detail["session_normal_impulse_n_s"])
        )
        unsafe_reason = _unsafe_contact_reason(
            lineage_valid=lineage_valid,
            components=components,
            forces=[aggregate_force, *forces],
            impulse=impulse,
        )
        session_id = (
            aggregate_sessions if detail is None else int(detail["session_id"])
        )
        previous_impulse = session_last_impulse.get(session_id, 0.0)
        impulse_delta = 0.0
        if math.isfinite(impulse) and math.isfinite(previous_impulse):
            if impulse + 1.0e-9 < previous_impulse:
                unsafe_reason = "wall_contact_detail_invalid"
            else:
                impulse_delta = impulse - previous_impulse
                session_last_impulse[session_id] = impulse
        latched_unsafe_reason = session_unsafe_reasons.get(session_id, "")
        if latched_unsafe_reason:
            unsafe_reason = latched_unsafe_reason
        elif unsafe_reason:
            session_unsafe_reasons[session_id] = unsafe_reason

        eligible = not unsafe_reason
        if eligible:
            side_effect_free, decision_offset = _validate_contact_side_effects(
                rows=rows,
                row_index=row_index,
                eligible=True,
                decision_offset=decision_offset,
            )
            terminal_chain: dict[str, Any] = {}
        else:
            side_effect_free = False
            terminal_chain = session_terminal_chains.get(session_id)
            if terminal_chain is None:
                terminal_chain = _require_unsafe_terminal_chain(
                    rows=rows,
                    row_index=row_index,
                    reason=unsafe_reason,
                )
                session_terminal_chains[session_id] = terminal_chain
            else:
                terminal_chain = dict(terminal_chain)
        statistics_valid = bool(
            detail is not None
            and all(math.isfinite(value) and value >= 0.0 for value in forces)
            and math.isfinite(impulse)
            and impulse >= 0.0
        )
        contact = {
            "row_index": row_index,
            "cycle_id": _cycle(row),
            "step_id": int(row["step_id"]),
            "detail": detail,
            "session_id": session_id,
            "normal_impulse_delta_n_s": impulse_delta,
            "components": components,
            "walls": walls,
            "eligible_observe_only_bucket_contact": eligible,
            "observe_only_side_effect_free": side_effect_free,
            "unsafe_reason": unsafe_reason,
            "terminal_chain": terminal_chain,
            "statistics_valid": statistics_valid,
        }
        contacts.append(contact)
        by_row[row_index] = contact
        if aggregate_sessions >= last_session_count:
            last_session_count = aggregate_sessions
        if lineage_valid and detail is not None:
            last_contact_detail = detail
            last_contact_row_index = row_index
    return contacts, by_row


def _unsafe_contact_reason(
    *,
    lineage_valid: bool,
    components: Sequence[str],
    forces: Sequence[float],
    impulse: float,
) -> str:
    if not lineage_valid:
        return "wall_contact_detail_invalid"
    if any(component != "bucket" for component in components):
        return "wall_contact_forbidden_component"
    if (
        not math.isfinite(impulse)
        or not all(math.isfinite(force) for force in forces)
        or any(force >= WALL_CONTACT_HARD_MAX_FORCE_N for force in forces)
    ):
        return "wall_contact_high_force"
    if impulse < 0.0 or any(force < 0.0 for force in forces):
        return "wall_contact_detail_invalid"
    return ""


def _require_unsafe_terminal_chain(
    *,
    rows: Sequence[Mapping[str, Any]],
    row_index: int,
    reason: str,
) -> dict[str, Any]:
    try:
        return require_unsafe_terminal_chain(
            rows=rows,
            row_index=row_index,
            reason=reason,
        )
    except WallContactSafetyEvidenceError as exc:
        raise WallContactRolloutDiagnosticError(str(exc)) from exc


def _validate_contact_row_lineage(
    *,
    row: Mapping[str, Any],
    detail: Mapping[str, Any],
    aggregate_force: float,
    aggregate_sessions: int,
) -> None:
    if int(detail.get("step_id", -1)) != int(row.get("step_id", -2)):
        raise WallContactRolloutDiagnosticError(
            "contact_step_lineage_invalid"
        )
    sim_time_ns = _integer(
        row.get("sim_time_ns"),
        "contact.sim_time_ns",
        minimum=0,
    )
    delta_time_s = _finite(
        detail.get("delta_time_s"),
        "contact.delta_time_s",
        minimum=0.0,
        strictly_greater=True,
    )
    expected_sim_time_s = sim_time_ns / 1_000_000_000.0
    if not math.isclose(
        _finite(detail.get("sim_time_s"), "contact.sim_time_s", minimum=0.0),
        expected_sim_time_s,
        abs_tol=max(1.0e-6, delta_time_s * 1.0e-5),
        rel_tol=0.0,
    ):
        raise WallContactRolloutDiagnosticError(
            "contact_sim_time_lineage_invalid"
        )
    if (
        int(detail.get("session_id", -1)) != aggregate_sessions
        or int(detail.get("session_count", -1)) != aggregate_sessions
    ):
        raise WallContactRolloutDiagnosticError(
            "contact_session_lineage_invalid"
        )
    normal_max = max(
        float(pair["max_normal_force_n"]) for pair in detail["pairs"]
    )
    if (
        math.isfinite(normal_max)
        and math.isfinite(aggregate_force)
        and not math.isclose(
            normal_max,
            aggregate_force,
            abs_tol=max(1.0e-3, abs(normal_max) * 1.0e-5),
            rel_tol=0.0,
        )
    ):
        raise WallContactRolloutDiagnosticError(
            "contact_force_lineage_invalid"
        )


def _validate_session_progression(
    *,
    detail: Mapping[str, Any],
    previous_detail: Mapping[str, Any] | None,
    clear_tick_count: int,
) -> None:
    if previous_detail is None:
        if (
            int(detail["session_id"]) != 1
            or int(detail["consecutive_contact_steps"]) != 1
        ):
            raise WallContactRolloutDiagnosticError(
                "contact_initial_session_lineage_invalid"
            )
        return
    current_session = int(detail["session_id"])
    previous_session = int(previous_detail["session_id"])
    if clear_tick_count == 0:
        if current_session != previous_session:
            raise WallContactRolloutDiagnosticError(
                "contact_session_changed_without_clear_tick"
            )
        if int(detail["consecutive_contact_steps"]) <= int(
            previous_detail["consecutive_contact_steps"]
        ):
            raise WallContactRolloutDiagnosticError(
                "contact_consecutive_steps_not_increasing"
            )
        if float(detail["session_duration_s"]) <= float(
            previous_detail["session_duration_s"]
        ):
            raise WallContactRolloutDiagnosticError(
                "contact_session_duration_not_increasing"
            )
        return
    if (
        current_session != previous_session + 1
        or int(detail["consecutive_contact_steps"]) != 1
    ):
        raise WallContactRolloutDiagnosticError(
            "contact_new_session_lineage_invalid"
        )


def _validate_contact_side_effects(
    *,
    rows: Sequence[Mapping[str, Any]],
    row_index: int,
    eligible: bool,
    decision_offset: int | None,
) -> tuple[bool, int | None]:
    row = rows[row_index]
    if not eligible:
        response_index = row_index + (decision_offset or 0)
        if (
            response_index < len(rows)
            and rows[response_index].get(
                "box_safety_wall_contact_diagnostic_allowed"
            )
            is True
        ):
            raise WallContactRolloutDiagnosticError(
                "unsafe_contact_diagnostic_allow"
            )
        return False, decision_offset
    try:
        require_independent_contact_hard_stop_chain(
            rows=rows,
            row_index=row_index,
        )
    except WallContactSafetyEvidenceError:
        pass
    else:
        return True, decision_offset
    if decision_offset is None:
        decision_offset = _observe_only_decision_offset(rows, row_index)
    response_index = row_index + decision_offset
    if response_index >= len(rows):
        raise WallContactRolloutDiagnosticError(
            "observe_only_contact_response_missing"
        )
    row = rows[response_index]
    has_side_effect = any(bool(row.get(field, False)) for field in (
        _OBSERVE_ONLY_SIDE_EFFECT_FIELDS
    ))
    has_side_effect = bool(
        has_side_effect
        or str(row.get("box_safety_reason", "")).strip()
        or int(row.get("box_safety_blocked_corridor_id", -1)) != -1
        or str(row.get("box_safety_contact_kind", "none")) != "none"
        or row.get("box_safety_wall_contact_diagnostic_allowed") is not True
    )
    if has_side_effect:
        raise WallContactRolloutDiagnosticError(
            "observe_only_contact_side_effect"
        )
    return True, decision_offset


def _observe_only_decision_offset(
    rows: Sequence[Mapping[str, Any]],
    contact_row_index: int,
) -> int:
    """Resolve synthetic same-row versus live post-step JSONL lineage once."""

    if rows[contact_row_index].get(
        "box_safety_wall_contact_diagnostic_allowed"
    ) is True:
        return 0
    next_index = contact_row_index + 1
    if (
        next_index < len(rows)
        and rows[next_index].get(
            "box_safety_wall_contact_diagnostic_allowed"
        )
        is True
    ):
        return 1
    raise WallContactRolloutDiagnosticError(
        "observe_only_contact_response_missing"
    )


def _summarize_shovel(
    *,
    cycle_id: int,
    rows: Sequence[Mapping[str, Any]],
    contacts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    details = [
        dict(contact["detail"])
        for contact in contacts
        if contact["detail"] is not None
    ]
    statistical_details = [
        dict(contact["detail"])
        for contact in contacts
        if contact["detail"] is not None and contact["statistics_valid"]
    ]
    step_peak_total = [
        max(float(pair["max_total_force_n"]) for pair in detail["pairs"])
        for detail in statistical_details
    ]
    step_peak_normal = [
        max(float(pair["max_normal_force_n"]) for pair in detail["pairs"])
        for detail in statistical_details
    ]
    step_peak_tangential = [
        max(
            float(pair["max_tangential_force_n"])
            for pair in detail["pairs"]
        )
        for detail in statistical_details
    ]
    motion = _motion_summary(rows=rows, contacts=contacts)
    dump_pulse_count = sum(
        _integer_float(
            row.get("dump_end_mask", 0),
            "dump_end_mask",
            minimum=0,
        )
        for row in rows
    )
    if dump_pulse_count > 1:
        raise WallContactRolloutDiagnosticError(
            "duplicate_dump_completion_pulse"
        )
    return {
        "shovel_index": cycle_id,
        "cycle_id": cycle_id,
        "dump_completed": dump_pulse_count == 1,
        "contact_observed": bool(contacts),
        "contact_tick_count": len(contacts),
        "session_ids": sorted(
            {
                int(contact["session_id"])
                for contact in contacts
                if int(contact["session_id"]) >= 0
            }
        ),
        "components": sorted(
            {
                str(pair["component"])
                for detail in details
                for pair in detail["pairs"]
            }
        ),
        "walls": sorted(
            {
                str(pair["wall_name"])
                for detail in details
                for pair in detail["pairs"]
            }
        ),
        "peak_normal_force_n": max(step_peak_normal, default=0.0),
        "peak_tangential_force_n": max(
            step_peak_tangential,
            default=0.0,
        ),
        "peak_total_force_n": max(step_peak_total, default=0.0),
        "rms_of_step_peak_normal_force_n": _rms(step_peak_normal),
        "rms_of_step_peak_tangential_force_n": _rms(
            step_peak_tangential
        ),
        "rms_of_step_peak_total_force_n": _rms(step_peak_total),
        "normal_impulse_n_s": sum(
            float(contact["normal_impulse_delta_n_s"])
            for contact in contacts
        ),
        "contact_duration_s": sum(
            float(detail["delta_time_s"]) for detail in details
        ),
        "force_statistics_invalid_contact_tick_count": sum(
            int(not bool(contact["statistics_valid"])) for contact in contacts
        ),
        "unsafe_contact_reasons": sorted(
            {
                str(contact["unsafe_reason"])
                for contact in contacts
                if contact["unsafe_reason"]
            }
        ),
        "component_wall_summaries": _component_wall_summaries(
            statistical_details
        ),
        "motion_progress_observed": motion["observed"],
        "motion": motion["measurements"],
    }


def _component_wall_summaries(
    details: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    per_key: dict[
        tuple[str, str],
        dict[str, Any],
    ] = defaultdict(
        lambda: {
            "normal": [],
            "tangential": [],
            "total": [],
            "duration": 0.0,
            "impulse_proxy": 0.0,
            "sessions": set(),
            "ticks": set(),
        }
    )
    for detail in details:
        dt = float(detail["delta_time_s"])
        session_id = int(detail["session_id"])
        per_tick: dict[tuple[str, str], dict[str, float]] = {}
        for pair in detail["pairs"]:
            key = (str(pair["component"]), str(pair["wall_name"]))
            values = per_tick.setdefault(
                key,
                {"normal": 0.0, "tangential": 0.0, "total": 0.0},
            )
            values["normal"] = max(
                values["normal"],
                float(pair["max_normal_force_n"]),
            )
            values["tangential"] = max(
                values["tangential"],
                float(pair["max_tangential_force_n"]),
            )
            values["total"] = max(
                values["total"],
                float(pair["max_total_force_n"]),
            )
        for key, values in per_tick.items():
            accumulator = per_key[key]
            accumulator["normal"].append(values["normal"])
            accumulator["tangential"].append(values["tangential"])
            accumulator["total"].append(values["total"])
            accumulator["duration"] += dt
            accumulator["impulse_proxy"] += values["normal"] * dt
            accumulator["sessions"].add(session_id)
            accumulator["ticks"].add(int(detail["step_id"]))
    return [
        {
            "component": component,
            "wall_name": wall,
            "contact_tick_count": len(values["ticks"]),
            "session_ids": sorted(values["sessions"]),
            "peak_normal_force_n": max(values["normal"]),
            "rms_of_step_peak_normal_force_n": _rms(values["normal"]),
            "peak_tangential_force_n": max(values["tangential"]),
            "rms_of_step_peak_tangential_force_n": _rms(
                values["tangential"]
            ),
            "peak_total_force_n": max(values["total"]),
            "rms_of_step_peak_total_force_n": _rms(values["total"]),
            "normal_impulse_n_s": values["impulse_proxy"],
            "normal_impulse_is_proxy": True,
            "contact_duration_s": values["duration"],
        }
        for (component, wall), values in sorted(per_key.items())
    ]


def _motion_summary(
    *,
    rows: Sequence[Mapping[str, Any]],
    contacts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    try:
        return build_contact_motion_summary(rows=rows, contacts=contacts)
    except WallContactSafetyEvidenceError as exc:
        raise WallContactRolloutDiagnosticError(str(exc)) from exc


def _terminal_neutral_evidence(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    awaiting = [
        row
        for row in rows
        if bool(row.get("box_safety_awaiting_neutral_ack", False))
    ]
    acknowledged = [
        row
        for row in rows
        if bool(row.get("box_safety_neutral_acknowledged", False))
    ]
    terminal = [
        row for row in rows if bool(row.get("box_safety_terminal", False))
    ]
    return {
        "requested": bool(awaiting),
        "acknowledged": bool(acknowledged),
        "terminal_observed": bool(terminal),
        "request_step_id": (
            -1 if not awaiting else int(awaiting[0].get("step_id", -1))
        ),
        "ack_step_id": (
            -1
            if not acknowledged
            else int(acknowledged[-1].get("step_id", -1))
        ),
        "reason": str(
            (
                acknowledged[-1]
                if acknowledged
                else (awaiting[-1] if awaiting else {})
            ).get("box_safety_reason", "")
        ),
    }


def _hard_stop_reasons(
    *,
    rows: Sequence[Mapping[str, Any]],
    contacts: Sequence[Mapping[str, Any]],
    stop_reason: str,
) -> list[str]:
    reasons = {
        str(row.get("box_safety_reason", "")).strip()
        for row in rows
        if str(row.get("box_safety_reason", "")).strip()
    }
    for contact in contacts:
        if contact["unsafe_reason"]:
            reasons.add(str(contact["unsafe_reason"]))
    if stop_reason.startswith("box_safety:"):
        reasons.add(stop_reason.removeprefix("box_safety:"))
    return sorted(reasons)


def _outcome(
    *,
    completed_dump_count: int,
    max_shovels: int,
    stop_reason: str,
    terminal_neutral: Mapping[str, Any],
) -> str:
    if completed_dump_count >= max_shovels:
        return "completed_10_dumps"
    if (
        stop_reason.startswith("box_safety:")
        or "timeout" in stop_reason
        or bool(terminal_neutral.get("terminal_observed", False))
    ):
        return "hard_safety_stop_before_10"
    return "inconclusive"


def _cycle_ids(
    rows: Sequence[Mapping[str, Any]],
    max_shovels: int,
) -> list[int]:
    cycle_ids = sorted(
        {
            _cycle(row)
            for row in rows
            if str(row.get("skill_name", "")) == "dig"
            or _integer_float(
                row.get("dump_end_mask", 0),
                "dump_end_mask",
                minimum=0,
            )
            == 1
        }
    )
    if any(value < 0 for value in cycle_ids):
        raise WallContactRolloutDiagnosticError(
            "shovel_cycle_id_invalid"
        )
    if cycle_ids != list(range(len(cycle_ids))):
        raise WallContactRolloutDiagnosticError(
            "shovel_cycle_inventory_invalid"
        )
    if len(cycle_ids) > max_shovels:
        raise WallContactRolloutDiagnosticError(
            "max_shovels_exceeded"
        )
    return cycle_ids


def _validate_summary_dump_count(
    summary: Mapping[str, Any],
    *,
    completed_dump_count: int,
) -> None:
    authoritative_key = "target_cycle_completed_dump_count"
    if authoritative_key not in summary:
        raise WallContactRolloutDiagnosticError(
            "summary_dump_count_missing"
        )
    if (
        _integer_float(
            summary[authoritative_key],
            authoritative_key,
            minimum=0,
        )
        != completed_dump_count
    ):
        raise WallContactRolloutDiagnosticError(
            "summary_dump_count_drift"
        )


def _cycle(row: Mapping[str, Any]) -> int:
    return _integer_float(
        row.get("primitive_cycle_index"),
        "primitive_cycle_index",
        minimum=0,
    )


def _max_shovels(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WallContactRolloutDiagnosticError("max_shovels_invalid")
    if not 1 <= value <= MAX_DIAGNOSTIC_SHOVELS:
        raise WallContactRolloutDiagnosticError("max_shovels_invalid")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WallContactRolloutDiagnosticError(f"{label}_invalid")
    return value


def _integer(value: Any, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WallContactRolloutDiagnosticError(f"{label}_invalid")
    if value < minimum:
        raise WallContactRolloutDiagnosticError(f"{label}_invalid")
    return value


def _integer_float(value: Any, label: str, *, minimum: int) -> int:
    number = _finite(value, label, minimum=float(minimum))
    integer = int(round(number))
    if abs(number - integer) > 1.0e-6:
        raise WallContactRolloutDiagnosticError(f"{label}_invalid")
    return integer


def _finite(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    strictly_greater: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WallContactRolloutDiagnosticError(f"{label}_invalid")
    number = float(value)
    if not math.isfinite(number):
        raise WallContactRolloutDiagnosticError(f"{label}_nonfinite")
    if minimum is not None and (
        number <= minimum if strictly_greater else number < minimum
    ):
        raise WallContactRolloutDiagnosticError(f"{label}_invalid")
    return number


def _finite_vector(value: Any, size: int, label: str) -> list[float]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or len(value) != size
    ):
        raise WallContactRolloutDiagnosticError(f"{label}_invalid")
    return [_finite(item, f"{label}[]") for item in value]


def _rms(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(value * value for value in values) / len(values))


__all__ = [
    "MAX_DIAGNOSTIC_SHOVELS",
    "OBSERVE_ONLY_MODE",
    "REPORT_SCHEMA",
    "WallContactRolloutDiagnosticError",
    "build_wall_contact_rollout_report",
]
