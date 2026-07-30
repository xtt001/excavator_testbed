"""Offline evidence owner for the Unity wall-and-floor contact diagnostic.

The diagnostic keeps the existing detailed wall-contact evidence contract and
adds an all-part FactoryFloor sidecar.  The legacy 107D in-footprint bucket
aggregate remains an independent lineage check and is never treated as a
complete FactoryFloor contact source.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from testbed.data.schema import (
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.wall_contact_rollout_diagnostic import (
    MAX_DIAGNOSTIC_SHOVELS,
    WallContactRolloutDiagnosticError,
    build_wall_contact_rollout_report,
)
from testbed.eval.wall_contact_rollout_safety_evidence import (
    WallContactSafetyEvidenceError,
    build_contact_motion_summary,
    require_independent_contact_hard_stop_chain,
)
from testbed.planner.box_emptying.bottom_contact_detail import (
    BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_PREFIX,
    BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA,
    FACTORY_FLOOR_CONTACT_FORBIDDEN_COMPONENT_REASON,
    FACTORY_FLOOR_CONTACT_HIGH_FORCE_REASON,
    WORKTOOL_CONTACT_MONITOR_STATUS_PREFIX,
    WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX,
    WORKTOOL_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_PREFIX,
    WORKTOOL_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA,
    FactoryFloorContactDetailContractError,
    parse_worktool_factory_floor_contact_detail,
)
from testbed.planner.box_emptying.wall_contact_detail import (
    WALL_CONTACT_HARD_MAX_FORCE_N,
)

REPORT_SCHEMA = "unity_contact_observe_only_multicycle_report_v1"
FACTORY_FLOOR_LINEAGE_WARNING = (
    WORKTOOL_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA
)
UNITY_DIAGNOSTIC_BACKEND = "agx_unity"

_ALLOWED_CONTACT_SIDE_EFFECT_FIELDS = (
    "box_safety_awaiting_neutral_ack",
    "box_safety_neutral_acknowledged",
    "box_safety_replan",
    "box_safety_terminal",
    "box_safety_policy_restarted",
    "box_safety_hard_bottom_recovery_active",
    "box_safety_hard_bottom_contact",
    "box_safety_hard_bottom_clearance_active",
    "box_safety_hard_bottom_clearance_completed",
    "box_safety_hard_bottom_clearance_neutral_acknowledged",
    "box_safety_hard_bottom_depth_budget_guard",
)
_DOWNSTREAM_GATES = {
    "production_contact_contract_change_allowed": False,
    "continuous_predictor_allowed": False,
    "offline_e0_g1_w1_allowed": False,
    "bounded_live_allowed": False,
    "functional_1x10_allowed": False,
}


# Keep one shared diagnostic exception boundary so reused wall-lineage helpers
# and the Unity extension fail through the same public type.
UnityContactObserveOnlyReportError = WallContactRolloutDiagnosticError


def build_unity_contact_observe_only_report(
    *,
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    max_shovels: int = MAX_DIAGNOSTIC_SHOVELS,
) -> dict[str, Any]:
    """Validate one diagnostic rollout and summarize wall/floor contact."""

    normalized = _validate_rows(rows)
    floor_contacts = _factory_floor_contacts(normalized)
    wall_report = build_wall_contact_rollout_report(
        rows=normalized,
        summary=summary,
        max_shovels=max_shovels,
    )
    shovels = []
    for wall_shovel in wall_report["shovels"]:
        cycle_id = int(wall_shovel["cycle_id"])
        cycle_rows = [
            row
            for row in normalized
            if _cycle_id(row) == cycle_id
        ]
        cycle_contacts = [
            contact
            for contact in floor_contacts
            if int(contact["cycle_id"]) == cycle_id
        ]
        shovels.append(
            {
                **wall_shovel,
                "wall_contact": {
                    key: value
                    for key, value in wall_shovel.items()
                    if key
                    not in {
                        "shovel_index",
                        "cycle_id",
                        "dump_completed",
                    }
                },
                "factory_floor_contact": _floor_summary(
                    rows=cycle_rows,
                    contacts=cycle_contacts,
                ),
                "combined_contact": _combined_contact_summary(
                    rows=cycle_rows,
                    wall_shovel=wall_shovel,
                    floor_contacts=cycle_contacts,
                ),
            }
        )

    completed = int(wall_report["completed_dump_count"])
    stop_reason = str(summary.get("rollout_stop_reason", "")).strip()
    category = _termination_category(
        completed_dump_count=completed,
        max_shovels=max_shovels,
        stop_reason=stop_reason,
        rows=normalized,
        floor_contacts=floor_contacts,
        wall_report=wall_report,
    )
    floor_tick_count = len(floor_contacts)
    return {
        "schema": REPORT_SCHEMA,
        "status": "failed" if category == "failed" else "passed",
        "termination_category": category,
        "diagnostic_only": True,
        "non_promotable": True,
        "production_contract_modified": False,
        "writes_training_hdf5": False,
        "max_shovels": int(max_shovels),
        "started_shovel_count": int(
            wall_report["started_shovel_count"]
        ),
        "completed_dump_count": completed,
        "partial_shovel_count": int(
            wall_report["partial_shovel_count"]
        ),
        "rollout_stop_reason": stop_reason,
        "wall_contact_tick_count": int(
            wall_report["contact_tick_count"]
        ),
        "factory_floor_contact_tick_count": floor_tick_count,
        "factory_floor_contact_observed": bool(floor_tick_count),
        "factory_floor_total_duration_s": sum(
            float(contact["delta_time_s"]) for contact in floor_contacts
        ),
        "factory_floor_peak_normal_force_n": max(
            (
                float(contact["step_peak_normal_force_n"])
                for contact in floor_contacts
            ),
            default=0.0,
        ),
        "factory_floor_rms_of_step_peak_normal_force_n": _rms(
            [
                float(contact["step_peak_normal_force_n"])
                for contact in floor_contacts
            ]
        ),
        "factory_floor_force_semantics": (
            "RMS is over all-part FactoryFloor sidecar per-contact-tick "
            "step-max normal force"
        ),
        "factory_floor_duration_semantics": (
            "sum of canonical FactoryFloor sidecar delta_time_s values"
        ),
        "factory_floor_impulse_n_s": None,
        "factory_floor_impulse_status": (
            "unsupported_by_factory_floor_detail_v1"
        ),
        "wall_report_schema": wall_report["schema"],
        "wall_terminal_neutral": wall_report["terminal_neutral"],
        "wall_hard_stop_reasons": wall_report["hard_stop_reasons"],
        "shovels": shovels,
        "downstream_gates": dict(_DOWNSTREAM_GATES),
    }


def _validate_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if (
        isinstance(rows, (str, bytes))
        or not isinstance(rows, Sequence)
        or not rows
    ):
        raise UnityContactObserveOnlyReportError("rollout_rows_invalid")
    normalized: list[dict[str, Any]] = []
    previous_step = -1
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise UnityContactObserveOnlyReportError(
                f"rollout_row_invalid:{index}"
            )
        row = dict(raw)
        step = _integer(row.get("step_id"), f"row_{index}.step_id")
        if step <= previous_step:
            raise UnityContactObserveOnlyReportError(
                "rollout_step_lineage_invalid"
            )
        previous_step = step
        env = _finite_vector(
            row.get("env_state"),
            ENV_STATE_V2_4_DIM,
            f"row_{index}.env_state",
        )
        _validate_unity_marker(row, index=index)
        _reject_legacy_hard_bottom_takeover(row, index=index)
        _reject_lineage_warning(row.get("warnings"), index=index)
        _validate_floor_scalars(env, index=index)
        normalized.append(row)
    return normalized


def _reject_legacy_hard_bottom_takeover(
    row: Mapping[str, Any],
    *,
    index: int,
) -> None:
    reason = str(row.get("box_safety_reason", "")).strip()
    if reason.startswith("hard_bottom_") or any(
        bool(row.get(field, False))
        for field in (
            "box_safety_hard_bottom_recovery_active",
            "box_safety_hard_bottom_contact",
            "box_safety_hard_bottom_clearance_active",
            "box_safety_hard_bottom_clearance_completed",
            "box_safety_hard_bottom_clearance_neutral_acknowledged",
            "box_safety_hard_bottom_depth_budget_guard",
        )
    ):
        raise UnityContactObserveOnlyReportError(
            f"unity_diagnostic_hard_bottom_takeover_observed:row_{index}"
        )


def _validate_unity_marker(
    row: Mapping[str, Any],
    *,
    index: int,
) -> None:
    if (
        row.get(
            "box_safety_unity_contact_diagnostic_observe_only_enabled"
        )
        is not True
        or row.get("box_safety_unity_contact_diagnostic_backend")
        != UNITY_DIAGNOSTIC_BACKEND
    ):
        raise UnityContactObserveOnlyReportError(
            f"unity_contact_debug_lineage_invalid:row_{index}"
        )


def _reject_lineage_warning(value: Any, *, index: int) -> None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise UnityContactObserveOnlyReportError(
            f"factory_floor_contact_lineage_invalid:row_{index}"
        )
    for warning in value:
        if isinstance(warning, str) and (
            warning.startswith(WORKTOOL_CONTACT_MONITOR_STATUS_PREFIX)
            or warning
            in {
                WORKTOOL_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA,
                BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA,
            }
            or warning.startswith(
                (
                    WORKTOOL_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_PREFIX,
                    BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_PREFIX,
                )
            )
        ):
            raise UnityContactObserveOnlyReportError(
                f"factory_floor_contact_lineage_invalid:row_{index}"
            )


def _validate_floor_scalars(
    env: Sequence[float],
    *,
    index: int,
) -> None:
    mask = env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX]
    force = env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX]
    session = env[
        ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX
    ]
    if (
        mask not in {0.0, 1.0}
        or force < 0.0
        or session < 0.0
        or abs(session - round(session)) > 1.0e-6
    ):
        raise UnityContactObserveOnlyReportError(
            f"factory_floor_contact_lineage_invalid:row_{index}"
        )


def _factory_floor_contacts(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    contacts: list[dict[str, Any]] = []
    previous_aggregate_session = 0
    previous_aggregate_positive = False
    previous_detail: dict[str, Any] | None = None
    sidecar_clear_ticks = 0
    for index, row in enumerate(rows):
        env = _finite_vector(
            row["env_state"],
            ENV_STATE_V2_4_DIM,
            f"row_{index}.env_state",
        )
        positive = bool(
            env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX]
            >= 0.5
        )
        force = float(
            env[
                ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX
            ]
        )
        session = int(
            round(
                env[
                    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX
                ]
            )
        )
        valid = (
            session >= previous_aggregate_session
            and session <= previous_aggregate_session + 1
        )
        if positive:
            valid = bool(
                valid
                and session >= 1
                and (
                    (
                        previous_aggregate_positive
                        and session == previous_aggregate_session
                    )
                    or (
                        not previous_aggregate_positive
                        and session == previous_aggregate_session + 1
                    )
                )
            )
        else:
            valid = bool(
                valid
                and abs(force) <= 1.0e-6
                and session == previous_aggregate_session
            )
        if not valid:
            raise UnityContactObserveOnlyReportError(
                f"factory_floor_contact_lineage_invalid:row_{index}"
            )
        warnings = row.get("warnings")
        assert isinstance(warnings, Sequence) and not isinstance(
            warnings,
            (str, bytes),
        )
        matching = [
            warning
            for warning in warnings
            if isinstance(warning, str)
            and warning.startswith(
                WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX
            )
        ]
        if not matching:
            if positive:
                raise UnityContactObserveOnlyReportError(
                    f"factory_floor_contact_lineage_invalid:row_{index}"
                )
            sidecar_clear_ticks += 1
            previous_aggregate_session = session
            previous_aggregate_positive = positive
            continue
        if len(matching) != 1:
            raise UnityContactObserveOnlyReportError(
                f"factory_floor_contact_lineage_invalid:row_{index}"
            )
        try:
            detail_object = parse_worktool_factory_floor_contact_detail(
                warnings,
                expected_step_id=int(row["step_id"]),
                expected_sim_time_ns=_sim_time_ns(row, index=index),
            )
        except FactoryFloorContactDetailContractError as exc:
            raise UnityContactObserveOnlyReportError(
                f"factory_floor_contact_lineage_invalid:row_{index}:{exc}"
            ) from exc
        detail = asdict(detail_object)
        _validate_sidecar_session_progression(
            detail=detail,
            previous_detail=previous_detail,
            clear_tick_count=sidecar_clear_ticks,
            index=index,
        )
        components = list(detail["parts"])
        pair_forces = [
            float(value)
            for pair in detail["pairs"]
            for value in (
                pair["max_normal_force_n"],
                pair["max_tangential_force_n"],
                pair["max_total_force_n"],
            )
        ]
        all_forces = [
            float(detail["step_max_normal_force_n"]),
            float(detail["step_max_tangential_force_n"]),
            float(detail["step_max_total_force_n"]),
            *pair_forces,
            *([force] if positive else []),
        ]
        unsafe_reason = ""
        if any(component != "bucket" for component in components):
            unsafe_reason = (
                FACTORY_FLOOR_CONTACT_FORBIDDEN_COMPONENT_REASON
            )
        elif any(
            value >= WALL_CONTACT_HARD_MAX_FORCE_N
            for value in all_forces
        ):
            unsafe_reason = FACTORY_FLOOR_CONTACT_HIGH_FORCE_REASON

        if unsafe_reason:
            terminal_chain = _require_factory_floor_terminal_chain(
                rows=rows,
                row_index=index,
                reason=unsafe_reason,
            )
            terminal_steps = {
                int(terminal_chain["neutral_request_step_id"]),
                int(terminal_chain["terminal_ack_step_id"]),
            }
            if any(
                _allowed_marker(candidate)
                for candidate in rows
                if int(candidate["step_id"]) in terminal_steps
            ):
                raise UnityContactObserveOnlyReportError(
                    "factory_floor_unsafe_contact_diagnostic_allow"
                )
        else:
            decision_offset = _allowed_decision_offset(rows, index)
            if decision_offset is None:
                try:
                    terminal_chain = (
                        require_independent_contact_hard_stop_chain(
                            rows=rows,
                            row_index=index,
                        )
                    )
                except WallContactSafetyEvidenceError as exc:
                    raise UnityContactObserveOnlyReportError(
                        "factory_floor_contact_allow_response_missing"
                    ) from exc
            else:
                _require_allowed_without_side_effects(
                    rows=rows,
                    contact_index=index,
                    decision_offset=decision_offset,
                )
                terminal_chain = {}
        contacts.append(
            {
                "row_index": index,
                "step_id": int(row["step_id"]),
                "cycle_id": _cycle_id(row),
                "components": components,
                "source": "FactoryFloor",
                "session_id": int(detail["session_id"]),
                "step_peak_normal_force_n": float(
                    detail["step_max_normal_force_n"]
                ),
                "step_peak_tangential_force_n": float(
                    detail["step_max_tangential_force_n"]
                ),
                "step_peak_total_force_n": float(
                    detail["step_max_total_force_n"]
                ),
                "delta_time_s": float(detail["delta_time_s"]),
                "aggregate_107d_positive": positive,
                "aggregate_107d_normal_force_n": force,
                "detail": detail,
                "unsafe_reason": unsafe_reason,
                "terminal_chain": terminal_chain,
            }
        )
        previous_detail = detail
        sidecar_clear_ticks = 0
        previous_aggregate_session = session
        previous_aggregate_positive = positive
    return contacts


def _require_factory_floor_terminal_chain(
    *,
    rows: Sequence[Mapping[str, Any]],
    row_index: int,
    reason: str,
) -> dict[str, Any]:
    for request_index in (row_index - 1, row_index, row_index + 1):
        ack_index = request_index + 1
        if request_index < 0 or ack_index >= len(rows):
            continue
        request = rows[request_index]
        ack = rows[ack_index]
        event_id = request.get("box_safety_event_id")
        if (
            isinstance(event_id, bool)
            or not isinstance(event_id, int)
            or not _floor_neutral_request(request, reason=reason)
            or not _floor_terminal_ack(
                ack,
                reason=reason,
                event_id=event_id,
            )
        ):
            continue
        return {
            "event_id": event_id,
            "neutral_request_step_id": int(request["step_id"]),
            "terminal_ack_step_id": int(ack["step_id"]),
        }
    raise UnityContactObserveOnlyReportError(
        f"unsafe_contact_terminal_chain_missing:{reason}:row_{row_index}"
    )


def _floor_neutral_request(
    row: Mapping[str, Any],
    *,
    reason: str,
) -> bool:
    return bool(
        str(row.get("box_safety_reason", "")) == reason
        and bool(row.get("box_safety_awaiting_neutral_ack", False))
        and not bool(row.get("box_safety_neutral_acknowledged", False))
        and not bool(row.get("box_safety_terminal", False))
        and not bool(row.get("box_safety_replan", False))
        and not bool(row.get("box_safety_policy_restarted", False))
        and not bool(
            row.get("box_safety_wall_contact_diagnostic_allowed", False)
        )
        and not _allowed_marker(row)
        and str(row.get("box_safety_contact_kind", "")) == "hard_bottom"
        and _zero_action(row)
    )


def _floor_terminal_ack(
    row: Mapping[str, Any],
    *,
    reason: str,
    event_id: int,
) -> bool:
    return bool(
        str(row.get("box_safety_reason", "")) == reason
        and row.get("box_safety_event_id") == event_id
        and bool(row.get("box_safety_neutral_acknowledged", False))
        and bool(row.get("box_safety_terminal", False))
        and not bool(row.get("box_safety_awaiting_neutral_ack", False))
        and not bool(row.get("box_safety_replan", False))
        and not bool(row.get("box_safety_policy_restarted", False))
        and not bool(
            row.get("box_safety_wall_contact_diagnostic_allowed", False)
        )
        and not _allowed_marker(row)
        and str(row.get("box_safety_contact_kind", "")) == "hard_bottom"
        and _zero_action(row)
    )


def _zero_action(row: Mapping[str, Any]) -> bool:
    return max(
        abs(value)
        for value in _finite_vector(
            row.get("action"),
            4,
            "factory_floor_terminal.action",
        )
    ) <= 1.0e-6


def _validate_sidecar_session_progression(
    *,
    detail: Mapping[str, Any],
    previous_detail: Mapping[str, Any] | None,
    clear_tick_count: int,
    index: int,
) -> None:
    if previous_detail is None:
        valid = bool(
            int(detail["session_id"]) == 1
            and int(detail["session_count"]) == 1
            and int(detail["consecutive_contact_steps"]) == 1
        )
    elif clear_tick_count == 0:
        valid = bool(
            int(detail["session_id"])
            == int(previous_detail["session_id"])
            and int(detail["session_count"])
            == int(previous_detail["session_count"])
            and int(detail["consecutive_contact_steps"])
            == int(previous_detail["consecutive_contact_steps"]) + 1
            and float(detail["session_duration_s"])
            > float(previous_detail["session_duration_s"])
        )
    else:
        valid = bool(
            int(detail["session_id"])
            == int(previous_detail["session_id"]) + 1
            and int(detail["session_count"])
            == int(previous_detail["session_count"]) + 1
            and int(detail["consecutive_contact_steps"]) == 1
        )
    if not valid:
        raise UnityContactObserveOnlyReportError(
            f"factory_floor_contact_lineage_invalid:row_{index}"
        )


def _allowed_decision_offset(
    rows: Sequence[Mapping[str, Any]],
    index: int,
) -> int | None:
    if _allowed_marker(rows[index]):
        return 0
    if index + 1 < len(rows) and _allowed_marker(rows[index + 1]):
        return 1
    return None


def _allowed_marker(row: Mapping[str, Any]) -> bool:
    return (
        row.get("box_safety_factory_floor_contact_diagnostic_allowed")
        is True
    )


def _require_allowed_without_side_effects(
    *,
    rows: Sequence[Mapping[str, Any]],
    contact_index: int,
    decision_offset: int,
) -> None:
    response_index = contact_index + decision_offset
    if response_index >= len(rows):
        raise UnityContactObserveOnlyReportError(
            "factory_floor_contact_allow_response_missing"
        )
    row = rows[response_index]
    side_effect = any(
        bool(row.get(field, False))
        for field in _ALLOWED_CONTACT_SIDE_EFFECT_FIELDS
    )
    side_effect = bool(
        side_effect
        or not _allowed_marker(row)
        or str(row.get("box_safety_reason", "")).strip()
        or int(row.get("box_safety_blocked_corridor_id", -1)) != -1
        or str(row.get("box_safety_contact_kind", "none")) != "none"
    )
    if side_effect:
        raise UnityContactObserveOnlyReportError(
            "floor_contact_observe_only_side_effect"
        )


def _floor_summary(
    *,
    rows: Sequence[Mapping[str, Any]],
    contacts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    normal_forces = [
        float(contact["step_peak_normal_force_n"])
        for contact in contacts
    ]
    tangential_forces = [
        float(contact["step_peak_tangential_force_n"])
        for contact in contacts
    ]
    total_forces = [
        float(contact["step_peak_total_force_n"])
        for contact in contacts
    ]
    try:
        motion = build_contact_motion_summary(
            rows=rows,
            contacts=[
                {**dict(contact), "detail": None}
                for contact in contacts
            ],
        )
    except WallContactSafetyEvidenceError as exc:
        raise UnityContactObserveOnlyReportError(str(exc)) from exc
    components = sorted(
        {
            str(component)
            for contact in contacts
            for component in contact["components"]
        }
    )
    return {
        "contact_observed": bool(contacts),
        "component": components[0] if len(components) == 1 else "",
        "components": components,
        "source": "FactoryFloor",
        "contact_tick_count": len(contacts),
        "session_ids": sorted(
            {int(contact["session_id"]) for contact in contacts}
        ),
        "aggregate_107d_positive_tick_count": sum(
            bool(contact["aggregate_107d_positive"])
            for contact in contacts
        ),
        "peak_normal_force_n": max(normal_forces, default=0.0),
        "rms_of_step_peak_normal_force_n": _rms(normal_forces),
        "peak_tangential_force_n": max(
            tangential_forces,
            default=0.0,
        ),
        "rms_of_step_peak_tangential_force_n": _rms(
            tangential_forces
        ),
        "peak_total_force_n": max(total_forces, default=0.0),
        "rms_of_step_peak_total_force_n": _rms(total_forces),
        "contact_duration_s": sum(
            float(contact["delta_time_s"]) for contact in contacts
        ),
        "force_statistics_semantics": (
            "peak and RMS of all-part FactoryFloor sidecar per-contact-tick "
            "force maxima"
        ),
        "impulse_n_s": None,
        "impulse_status": "unsupported_by_factory_floor_detail_v1",
        "unsafe_events": [
            {
                "step_id": int(contact["step_id"]),
                "reason": str(contact["unsafe_reason"]),
                "components": list(contact["components"]),
                "terminal_chain": dict(contact["terminal_chain"]),
            }
            for contact in contacts
            if contact["unsafe_reason"]
        ],
        "motion_progress_observed": motion["observed"],
        "motion": motion["measurements"],
    }


def _combined_contact_summary(
    *,
    rows: Sequence[Mapping[str, Any]],
    wall_shovel: Mapping[str, Any],
    floor_contacts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    per_tick_forces: list[float] = []
    duration = 0.0
    floor_by_step = {
        int(contact["step_id"]): contact
        for contact in floor_contacts
    }
    for index, row in enumerate(rows):
        env = _finite_vector(
            row["env_state"],
            ENV_STATE_V2_4_DIM,
            "combined_contact.env_state",
        )
        wall_positive = bool(
            env[ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX] >= 0.5
        )
        floor_contact = floor_by_step.get(int(row["step_id"]))
        if wall_positive or floor_contact is not None:
            per_tick_forces.append(
                max(
                    (
                        env[
                            ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX
                        ]
                        if wall_positive
                        else 0.0
                    ),
                    (
                        float(
                            floor_contact["step_peak_normal_force_n"]
                        )
                        if floor_contact is not None
                        else 0.0
                    ),
                )
            )
            duration += (
                float(floor_contact["delta_time_s"])
                if floor_contact is not None
                else _row_delta_time_s(rows, index)
            )
    floor_observed = bool(floor_contacts)
    floor_components = {
        str(component)
        for contact in floor_contacts
        for component in contact["components"]
    }
    return {
        "contact_observed": bool(per_tick_forces),
        "contact_tick_count": len(per_tick_forces),
        "components": sorted(
            set(wall_shovel.get("components", []))
            | floor_components
        ),
        "sources": sorted(
            set(wall_shovel.get("walls", []))
            | ({"FactoryFloor"} if floor_observed else set())
        ),
        "peak_normal_force_n": max(per_tick_forces, default=0.0),
        "rms_of_step_peak_normal_force_n": _rms(per_tick_forces),
        "contact_duration_s": duration,
        "duration_semantics": (
            "union of wall-positive and FactoryFloor-positive ticks"
        ),
        "impulse_n_s": None,
        "impulse_status": (
            "not_combined_wall_exact_floor_detail_v1_has_no_impulse"
        ),
        "motion_progress_observed": bool(
            wall_shovel.get("motion_progress_observed") is True
            or _floor_summary(
                rows=rows,
                contacts=floor_contacts,
            )["motion_progress_observed"]
            is True
        ),
    }


def _termination_category(
    *,
    completed_dump_count: int,
    max_shovels: int,
    stop_reason: str,
    rows: Sequence[Mapping[str, Any]],
    floor_contacts: Sequence[Mapping[str, Any]],
    wall_report: Mapping[str, Any],
) -> str:
    reasons = " ".join(
        [
            stop_reason,
            *[
                str(value)
                for value in wall_report.get("hard_stop_reasons", [])
            ],
            *[
                str(row.get("box_safety_reason", ""))
                for row in rows
            ],
        ]
    ).lower()
    if "detail_invalid" in reasons or "lineage_incomplete" in reasons:
        return "failed"
    if (
        "high_force" in reasons
        or any(
            float(contact["step_peak_normal_force_n"])
            >= WALL_CONTACT_HARD_MAX_FORCE_N
            for contact in floor_contacts
        )
    ):
        return "high_force"
    if "stuck" in reasons:
        return "stuck"
    if "timeout" in reasons:
        return "timeout"
    if completed_dump_count >= max_shovels:
        return f"normal_completed_{int(max_shovels)}"
    if (
        stop_reason.startswith("box_safety:")
        or any(bool(row.get("box_safety_terminal", False)) for row in rows)
    ):
        return "other_hard_stop"
    return "failed"


def _row_delta_time_s(
    rows: Sequence[Mapping[str, Any]],
    index: int,
) -> float:
    current = _sim_time_ns(rows[index], index=index)
    if index > 0:
        previous = _sim_time_ns(rows[index - 1], index=index - 1)
        delta = (current - previous) / 1_000_000_000.0
        if math.isfinite(delta) and delta > 0.0:
            return delta
    if index + 1 < len(rows):
        following = _sim_time_ns(rows[index + 1], index=index + 1)
        delta = (following - current) / 1_000_000_000.0
        if math.isfinite(delta) and delta > 0.0:
            return delta
    return 0.02


def _sim_time_ns(row: Mapping[str, Any], *, index: int) -> int:
    value = row.get("sim_time_ns")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UnityContactObserveOnlyReportError(
            f"sim_time_lineage_invalid:row_{index}"
        )
    return value


def _cycle_id(row: Mapping[str, Any]) -> int:
    value = row.get("primitive_cycle_index")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UnityContactObserveOnlyReportError(
            "shovel_cycle_id_invalid"
        )
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UnityContactObserveOnlyReportError(f"{label}_invalid")
    return value


def _finite_vector(
    value: Any,
    size: int,
    label: str,
) -> list[float]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or len(value) != size
    ):
        raise UnityContactObserveOnlyReportError(f"{label}_invalid")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise UnityContactObserveOnlyReportError(f"{label}_invalid")
        number = float(item)
        if not math.isfinite(number):
            raise UnityContactObserveOnlyReportError(
                f"factory_floor_contact_lineage_invalid:{label}"
            )
        result.append(number)
    return result


def _rms(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(
        sum(value * value for value in values) / len(values)
    )


__all__ = [
    "FACTORY_FLOOR_LINEAGE_WARNING",
    "REPORT_SCHEMA",
    "UNITY_DIAGNOSTIC_BACKEND",
    "UnityContactObserveOnlyReportError",
    "build_unity_contact_observe_only_report",
]
