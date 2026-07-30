"""Safety-response alignment and motion windows for wall-contact rollouts."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from testbed.data.schema import (
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.box_emptying.bottom_contact_detail import (
    FACTORY_FLOOR_CONTACT_FORBIDDEN_COMPONENT_REASON,
    FACTORY_FLOOR_CONTACT_HIGH_FORCE_REASON,
    WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX,
)

QPOS_PROGRESS_M = 0.005
BUCKET_TIP_PROGRESS_M = 0.02
TANGENTIAL_PROGRESS_M = 0.01
MOTION_WINDOW_SEMANTICS = (
    "pre-contact post-step pose plus contiguous contact-positive post-step poses"
)


class WallContactSafetyEvidenceError(ValueError):
    """Raised when contact safety evidence cannot prove its contract."""


def require_unsafe_terminal_chain(
    *,
    rows: Sequence[Mapping[str, Any]],
    row_index: int,
    reason: str,
) -> dict[str, Any]:
    """Require one adjacent zero-request/terminal-ack pair for an unsafe tick."""

    proofs = [(reason, "wall")]
    if _typed_hard_bottom_positive(rows[row_index]):
        proofs.insert(0, ("hard_bottom_contact", "hard_bottom"))
    if _factory_floor_sidecar_present(rows[row_index]):
        proofs[0:0] = [
            (
                FACTORY_FLOOR_CONTACT_FORBIDDEN_COMPONENT_REASON,
                "hard_bottom",
            ),
            (FACTORY_FLOOR_CONTACT_HIGH_FORCE_REASON, "hard_bottom"),
        ]
    for proof_reason, contact_kind in proofs:
        for request_index in (row_index - 1, row_index, row_index + 1):
            ack_index = request_index + 1
            if request_index < 0 or ack_index >= len(rows):
                continue
            request, ack = rows[request_index], rows[ack_index]
            request_event = _event_id(request.get("box_safety_event_id", -1))
            if request_event is None or not _is_neutral_request(
                request,
                reason=proof_reason,
                contact_kind=contact_kind,
            ):
                continue
            if _is_terminal_ack(
                ack,
                reason=proof_reason,
                contact_kind=contact_kind,
                event_id=request_event,
            ):
                return {
                    "event_id": request_event,
                    "neutral_request_step_id": int(request["step_id"]),
                    "terminal_ack_step_id": int(ack["step_id"]),
                }
    raise WallContactSafetyEvidenceError(
        f"unsafe_contact_terminal_chain_missing:{reason}:row_{row_index}"
    )


def require_independent_contact_hard_stop_chain(
    *,
    rows: Sequence[Mapping[str, Any]],
    row_index: int,
) -> dict[str, Any]:
    """Prove that timeout/stuck, not allowed contact, owned termination."""

    # Contact sidecars describe the just-completed Unity step, while the
    # decision owning that observation can be serialized on the following
    # JSONL row.  Admit only the immediately adjacent request/ack pair.
    for request_index in (row_index - 1, row_index, row_index + 1):
        ack_index = request_index + 1
        if request_index < 0 or ack_index >= len(rows):
            continue
        request, ack = rows[request_index], rows[ack_index]
        reason = str(request.get("box_safety_reason", "")).strip()
        if not _is_independent_hard_stop_reason(reason):
            continue
        if (
            request_index == row_index + 1
            and not _is_clean_contact_before_independent_hard_stop(
                rows[row_index]
            )
        ):
            continue
        if (
            str(ack.get("box_safety_reason", "")).strip() != reason
            or not _is_independent_hard_stop_request(request)
            or not _is_independent_hard_stop_ack(ack)
        ):
            continue
        return {
            "reason": reason,
            "neutral_request_step_id": int(request["step_id"]),
            "terminal_ack_step_id": int(ack["step_id"]),
        }
    raise WallContactSafetyEvidenceError(
        f"independent_contact_hard_stop_chain_missing:row_{row_index}"
    )


def build_contact_motion_summary(
    *,
    rows: Sequence[Mapping[str, Any]],
    contacts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Measure motion from the pre-contact pose through contact-positive poses."""

    contact_steps = {int(contact["step_id"]) for contact in contacts}
    positions = [
        index
        for index, row in enumerate(rows)
        if int(row["step_id"]) in contact_steps
    ]
    groups: list[list[int]] = []
    for position in positions:
        if not groups or position != groups[-1][-1] + 1:
            groups.append([position])
        else:
            groups[-1].append(position)

    windows: list[dict[str, Any]] = []
    qpos_window_ranges: list[list[float]] = []
    tip_window_displacements: list[float] = []
    tip_window_paths: list[float] = []
    evidence_positions: set[int] = set()
    has_pose_delta = False
    for group in groups:
        sample_start = max(0, group[0] - 1)
        sample_end = group[-1]
        sample_positions = list(range(sample_start, sample_end + 1))
        has_pose_delta = has_pose_delta or len(sample_positions) >= 2
        evidence_positions.update(sample_positions)
        sample_rows = [rows[index] for index in sample_positions]
        qpos_samples = [
            _finite_vector(row.get("qpos"), 4, "contact_window.qpos")
            for row in sample_rows
        ]
        tip_samples = [
            _finite_vector(
                row.get("env_state"),
                ENV_STATE_V2_4_DIM,
                "contact_window.env_state",
            )[
                ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX :
                ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX + 3
            ]
            for row in sample_rows
        ]
        qpos_window_ranges.append(_axis_ranges(qpos_samples, 4))
        tip_window_displacements.append(_max_displacement(tip_samples))
        tip_window_paths.append(_path_length(tip_samples))
        windows.append(
            {
                "contact_step_ids": [
                    int(rows[index]["step_id"]) for index in group
                ],
                "sample_step_ids": [
                    int(rows[index]["step_id"]) for index in sample_positions
                ],
                "pre_contact_neighbor_included": sample_start < group[0],
                "post_contact_neighbor_included": False,
            }
        )

    qpos_ranges = [
        max((values[axis] for values in qpos_window_ranges), default=0.0)
        for axis in range(4)
    ]
    qpos_max = max(qpos_ranges, default=0.0)
    tip_max = max(tip_window_displacements, default=0.0)
    max_tangential = max(
        (
            float(pair["tangential_displacement_m"])
            for contact in contacts
            if contact.get("detail") is not None
            for pair in contact["detail"]["pairs"]
        ),
        default=0.0,
    )
    observed = (
        None
        if not contacts or (not has_pose_delta and max_tangential <= 0.0)
        else bool(
            qpos_max > QPOS_PROGRESS_M
            or tip_max > BUCKET_TIP_PROGRESS_M
            or max_tangential > TANGENTIAL_PROGRESS_M
        )
    )
    return {
        "observed": observed,
        "measurements": {
            "evidence_sufficient": observed is not None,
            "contact_pose_sample_count": len(positions),
            "evidence_pose_sample_count": len(evidence_positions),
            "evidence_window_semantics": MOTION_WINDOW_SEMANTICS,
            "evidence_windows": windows,
            "qpos_axis_ranges": qpos_ranges,
            "qpos_max_axis_range": qpos_max,
            "bucket_tip_max_displacement_m": tip_max,
            "bucket_tip_path_length_m": sum(tip_window_paths),
            "max_tangential_displacement_m": max_tangential,
        },
    }


def _is_neutral_request(
    row: Mapping[str, Any],
    *,
    reason: str,
    contact_kind: str,
) -> bool:
    return bool(
        str(row.get("box_safety_reason", "")) == reason
        and bool(row.get("box_safety_awaiting_neutral_ack", False))
        and not bool(row.get("box_safety_neutral_acknowledged", False))
        and not bool(row.get("box_safety_terminal", False))
        and not bool(row.get("box_safety_replan", False))
        and not bool(row.get("box_safety_policy_restarted", False))
        and not bool(row.get("box_safety_wall_contact_diagnostic_allowed", False))
        and str(row.get("box_safety_contact_kind", "")) == contact_kind
        and _is_zero_action(row)
    )


def _is_terminal_ack(
    row: Mapping[str, Any],
    *,
    reason: str,
    contact_kind: str,
    event_id: int,
) -> bool:
    return bool(
        str(row.get("box_safety_reason", "")) == reason
        and _event_id(row.get("box_safety_event_id", -2)) == event_id
        and bool(row.get("box_safety_neutral_acknowledged", False))
        and bool(row.get("box_safety_terminal", False))
        and not bool(row.get("box_safety_awaiting_neutral_ack", False))
        and not bool(row.get("box_safety_replan", False))
        and not bool(row.get("box_safety_policy_restarted", False))
        and not bool(row.get("box_safety_wall_contact_diagnostic_allowed", False))
        and str(row.get("box_safety_contact_kind", "")) == contact_kind
        and _is_zero_action(row)
    )


def _is_zero_action(row: Mapping[str, Any]) -> bool:
    return max(
        abs(value)
        for value in _finite_vector(row.get("action"), 4, "hard_stop.action")
    ) <= 1.0e-6


def _is_independent_hard_stop_reason(reason: str) -> bool:
    return bool(
        reason == "timeout"
        or reason.startswith("timeout_")
        or reason.startswith("stuck")
    )


def _is_clean_contact_before_independent_hard_stop(
    row: Mapping[str, Any],
) -> bool:
    return bool(
        not bool(row.get("box_safety_awaiting_neutral_ack", False))
        and not bool(row.get("box_safety_neutral_acknowledged", False))
        and not bool(row.get("box_safety_replan", False))
        and not bool(row.get("box_safety_terminal", False))
        and not bool(row.get("box_safety_policy_restarted", False))
        and not str(row.get("box_safety_reason", "")).strip()
        and int(row.get("box_safety_blocked_corridor_id", -1)) == -1
        and str(row.get("box_safety_contact_kind", "none")) == "none"
    )


def _is_independent_hard_stop_request(
    row: Mapping[str, Any],
) -> bool:
    return bool(
        bool(row.get("box_safety_awaiting_neutral_ack", False))
        and not bool(row.get("box_safety_neutral_acknowledged", False))
        and not bool(row.get("box_safety_terminal", False))
        and _is_independent_hard_stop_common(row)
    )


def _is_independent_hard_stop_ack(row: Mapping[str, Any]) -> bool:
    return bool(
        not bool(row.get("box_safety_awaiting_neutral_ack", False))
        and bool(row.get("box_safety_neutral_acknowledged", False))
        and bool(row.get("box_safety_terminal", False))
        and _is_independent_hard_stop_common(row)
    )


def _is_independent_hard_stop_common(
    row: Mapping[str, Any],
) -> bool:
    return bool(
        not bool(row.get("box_safety_replan", False))
        and not bool(row.get("box_safety_policy_restarted", False))
        and int(row.get("box_safety_blocked_corridor_id", -1)) == -1
        and str(row.get("box_safety_contact_kind", "none")) == "none"
        and not bool(
            row.get(
                "box_safety_wall_contact_diagnostic_allowed",
                False,
            )
        )
        and not bool(
            row.get(
                "box_safety_factory_floor_contact_diagnostic_allowed",
                False,
            )
        )
        and not bool(
            row.get(
                "box_safety_unity_contact_diagnostic_allowed",
                False,
            )
        )
        and _is_zero_action(row)
    )


def _event_id(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _typed_hard_bottom_positive(row: Mapping[str, Any]) -> bool:
    env = _finite_vector(
        row.get("env_state"),
        ENV_STATE_V2_4_DIM,
        "hard_bottom_priority.env_state",
    )
    return bool(
        env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX] >= 0.5
        and env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX] >= 1.0
    )


def _factory_floor_sidecar_present(row: Mapping[str, Any]) -> bool:
    warnings = row.get("warnings")
    if isinstance(warnings, (str, bytes)) or not isinstance(
        warnings,
        Sequence,
    ):
        return False
    return (
        sum(
            isinstance(value, str)
            and value.startswith(
                WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX
            )
            for value in warnings
        )
        == 1
    )


def _finite_vector(value: Any, size: int, label: str) -> list[float]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or len(value) != size
    ):
        raise WallContactSafetyEvidenceError(f"{label}_invalid")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise WallContactSafetyEvidenceError(f"{label}_invalid")
        number = float(item)
        if not math.isfinite(number):
            raise WallContactSafetyEvidenceError(f"{label}_nonfinite")
        result.append(number)
    return result


def _axis_ranges(
    samples: Sequence[Sequence[float]],
    size: int,
) -> list[float]:
    if not samples:
        return [0.0] * size
    return [
        max(sample[index] for sample in samples)
        - min(sample[index] for sample in samples)
        for index in range(size)
    ]


def _max_displacement(samples: Sequence[Sequence[float]]) -> float:
    if len(samples) < 2:
        return 0.0
    return max(
        math.dist(first, second)
        for index, first in enumerate(samples)
        for second in samples[index + 1 :]
    )


def _path_length(samples: Sequence[Sequence[float]]) -> float:
    return sum(
        math.dist(first, second)
        for first, second in zip(samples, samples[1:], strict=False)
    )


__all__ = [
    "BUCKET_TIP_PROGRESS_M",
    "MOTION_WINDOW_SEMANTICS",
    "QPOS_PROGRESS_M",
    "TANGENTIAL_PROGRESS_M",
    "WallContactSafetyEvidenceError",
    "build_contact_motion_summary",
    "require_independent_contact_hard_stop_chain",
    "require_unsafe_terminal_chain",
]
