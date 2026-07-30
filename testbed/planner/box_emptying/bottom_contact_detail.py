"""Typed FactoryFloor sidecar parsing and fail-closed diagnostic decisions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from numbers import Integral
from typing import Any

import numpy as np

from testbed.planner.box_emptying.wall_contact_detail import (
    WALL_CONTACT_HARD_MAX_FORCE_N,
    WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS,
    validate_wall_high_force_threshold,
)

WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_SCHEMA = (
    "worktool_factory_floor_contact_detail_v1"
)
WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX = (
    f"{WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_SCHEMA}:"
)
WORKTOOL_FACTORY_FLOOR_CONTACT_COMPONENTS = frozenset(
    {"boom", "bucket", "other", "stick"}
)
_COMPONENT_ORDER = {
    "boom": 0,
    "stick": 1,
    "bucket": 2,
    "other": 3,
}
WORKTOOL_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA = (
    "worktool_factory_floor_contact_lineage_incomplete_v1"
)
WORKTOOL_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_PREFIX = (
    f"{WORKTOOL_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA}:"
)
# Compatibility aliases for the aggregate-only diagnostic that preceded the
# all-part FactoryFloor sidecar.  The old warning remains fail-closed.
BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA = (
    "bucket_factory_floor_contact_lineage_incomplete_v1"
)
BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_PREFIX = (
    f"{BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA}:"
)
WORKTOOL_CONTACT_MONITOR_STATUS_PREFIX = (
    "worktool_contact_monitor_status_v1:"
)
WORKTOOL_CONTACT_MONITOR_STATUS_MISSING = (
    f"{WORKTOOL_CONTACT_MONITOR_STATUS_PREFIX}status=missing"
)
WORKTOOL_CONTACT_MONITOR_STATUS_NOT_REGISTERED = (
    f"{WORKTOOL_CONTACT_MONITOR_STATUS_PREFIX}status=not_registered"
)
UNITY_CONTACT_DIAGNOSTIC_BACKEND_AGX_UNITY = "agx_unity"

BOTTOM_GATE_NONE = "none"
BOTTOM_GATE_DIAGNOSTIC_ALLOW = "diagnostic_allow"
BOTTOM_GATE_TERMINAL = "terminal"
FACTORY_FLOOR_CONTACT_FORBIDDEN_COMPONENT_REASON = (
    "factory_floor_contact_forbidden_component"
)
FACTORY_FLOOR_CONTACT_HIGH_FORCE_REASON = (
    "factory_floor_contact_high_force"
)

_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "step_id",
        "sim_time_s",
        "delta_time_s",
        "session_id",
        "session_count",
        "consecutive_contact_steps",
        "session_duration_s",
        "step_max_normal_force_n",
        "step_max_tangential_force_n",
        "step_max_total_force_n",
        "parts",
        "pairs",
    }
)
_PAIR_FIELDS = frozenset(
    {
        "component",
        "machine_shape_path",
        "floor_shape_path",
        "callback_count",
        "contact_point_count",
        "max_normal_force_n",
        "max_tangential_force_n",
        "max_total_force_n",
        "contact_points_world_m",
        "representative_contact_point_component_local_m",
    }
)


class FactoryFloorContactDetailContractError(ValueError):
    """Raised when a FactoryFloor sidecar is missing or non-canonical."""


@dataclass(frozen=True)
class WorktoolFactoryFloorContactPair:
    component: str
    machine_shape_path: str
    floor_shape_path: str
    callback_count: int
    contact_point_count: int
    max_normal_force_n: float
    max_tangential_force_n: float
    max_total_force_n: float
    contact_points_world_m: tuple[tuple[float, float, float], ...]
    representative_contact_point_component_local_m: (
        tuple[float, float, float] | None
    )


@dataclass(frozen=True)
class WorktoolFactoryFloorContactDetail:
    schema: str
    step_id: int
    sim_time_s: float
    delta_time_s: float
    session_id: int
    session_count: int
    consecutive_contact_steps: int
    session_duration_s: float
    step_max_normal_force_n: float
    step_max_tangential_force_n: float
    step_max_total_force_n: float
    parts: tuple[str, ...]
    pairs: tuple[WorktoolFactoryFloorContactPair, ...]


@dataclass(frozen=True)
class FactoryFloorContactGateResult:
    """One tick's validated all-part FactoryFloor contact decision."""

    kind: str = BOTTOM_GATE_NONE
    reason: str = ""
    force_n: float = 0.0
    session_count: int = 0
    detail: WorktoolFactoryFloorContactDetail | None = None

    @property
    def terminal(self) -> bool:
        return self.kind == BOTTOM_GATE_TERMINAL

    @property
    def diagnostic_allowed(self) -> bool:
        return self.kind == BOTTOM_GATE_DIAGNOSTIC_ALLOW


def parse_worktool_factory_floor_contact_detail(
    warnings: Sequence[Any],
    *,
    expected_step_id: int | None = None,
    expected_sim_time_ns: int | None = None,
) -> WorktoolFactoryFloorContactDetail:
    """Parse exactly one canonical all-part FactoryFloor warning."""

    if isinstance(warnings, (str, bytes)) or not isinstance(
        warnings,
        Sequence,
    ):
        raise FactoryFloorContactDetailContractError(
            "worktool FactoryFloor contact warnings must be a sequence"
        )
    matching = [
        value
        for value in warnings
        if isinstance(value, str)
        and value.startswith(
            WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX
        )
    ]
    if not matching:
        raise FactoryFloorContactDetailContractError(
            "worktool FactoryFloor contact detail missing"
        )
    if len(matching) != 1:
        raise FactoryFloorContactDetailContractError(
            "worktool FactoryFloor contact detail ambiguous"
        )
    encoded = matching[0][
        len(WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX) :
    ]
    try:
        payload = json.loads(encoded)
    except (json.JSONDecodeError, TypeError) as exc:
        raise FactoryFloorContactDetailContractError(
            "worktool FactoryFloor contact detail JSON invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise FactoryFloorContactDetailContractError(
            "worktool FactoryFloor contact detail must be an object"
        )
    _require_exact_fields(payload, _TOP_LEVEL_FIELDS, "top-level")
    schema = _string(payload["schema"], "schema")
    if schema != WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_SCHEMA:
        raise FactoryFloorContactDetailContractError(
            f"worktool FactoryFloor contact schema invalid: {schema!r}"
        )

    step_id = _integer(payload["step_id"], "step_id", minimum=0)
    sim_time_s = _finite_number(payload["sim_time_s"], "sim_time_s")
    delta_time_s = _finite_number(payload["delta_time_s"], "delta_time_s")
    session_id = _integer(payload["session_id"], "session_id", minimum=1)
    session_count = _integer(
        payload["session_count"],
        "session_count",
        minimum=1,
    )
    consecutive_steps = _integer(
        payload["consecutive_contact_steps"],
        "consecutive_contact_steps",
        minimum=1,
    )
    session_duration_s = _finite_number(
        payload["session_duration_s"],
        "session_duration_s",
    )
    top_forces = (
        _force_number(
            payload["step_max_normal_force_n"],
            "step_max_normal_force_n",
        ),
        _force_number(
            payload["step_max_tangential_force_n"],
            "step_max_tangential_force_n",
        ),
        _force_number(
            payload["step_max_total_force_n"],
            "step_max_total_force_n",
        ),
    )
    if sim_time_s < 0.0:
        raise FactoryFloorContactDetailContractError(
            "sim_time_s must be non-negative"
        )
    if delta_time_s <= 0.0:
        raise FactoryFloorContactDetailContractError(
            "delta_time_s must be positive"
        )
    if session_duration_s <= 0.0:
        raise FactoryFloorContactDetailContractError(
            "session_duration_s must be positive"
        )
    if session_id != session_count:
        raise FactoryFloorContactDetailContractError(
            "session_id and session_count lineage differ"
        )

    parts = _ordered_unique_components(payload["parts"], "parts")
    raw_pairs = payload["pairs"]
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise FactoryFloorContactDetailContractError(
            "pairs must be a non-empty list"
        )
    pairs = tuple(
        _parse_pair(value, index=index)
        for index, value in enumerate(raw_pairs)
    )
    if any(
        pair.component not in WORKTOOL_FACTORY_FLOOR_CONTACT_COMPONENTS
        for pair in pairs
    ):
        raise FactoryFloorContactDetailContractError(
            "pair component is not canonical"
        )
    pair_keys = tuple(
        (
            _COMPONENT_ORDER[pair.component],
            pair.component,
            pair.machine_shape_path,
            pair.floor_shape_path,
        )
        for pair in pairs
    )
    if pair_keys != tuple(sorted(set(pair_keys))):
        raise FactoryFloorContactDetailContractError(
            "pairs must use deterministic unique ordering"
        )
    pair_parts = tuple(dict.fromkeys(pair.component for pair in pairs))
    if parts != pair_parts:
        raise FactoryFloorContactDetailContractError(
            "parts do not match pair components"
        )
    pair_force_maxima = (
        max(pair.max_normal_force_n for pair in pairs),
        max(pair.max_tangential_force_n for pair in pairs),
        max(pair.max_total_force_n for pair in pairs),
    )
    if any(
        not _force_close(top, pair_max)
        for top, pair_max in zip(
            top_forces,
            pair_force_maxima,
            strict=True,
        )
    ):
        raise FactoryFloorContactDetailContractError(
            "top-level force maxima do not match pair maxima"
        )
    if expected_step_id is not None and step_id != int(expected_step_id):
        raise FactoryFloorContactDetailContractError(
            "FactoryFloor contact detail step lineage differs"
        )
    if expected_sim_time_ns is not None:
        expected_seconds = int(expected_sim_time_ns) / 1_000_000_000.0
        tolerance = max(1.0e-6, abs(delta_time_s) * 1.0e-5)
        if abs(sim_time_s - expected_seconds) > tolerance:
            raise FactoryFloorContactDetailContractError(
                "FactoryFloor contact detail sim-time lineage differs"
            )
    return WorktoolFactoryFloorContactDetail(
        schema=schema,
        step_id=step_id,
        sim_time_s=sim_time_s,
        delta_time_s=delta_time_s,
        session_id=session_id,
        session_count=session_count,
        consecutive_contact_steps=consecutive_steps,
        session_duration_s=session_duration_s,
        step_max_normal_force_n=top_forces[0],
        step_max_tangential_force_n=top_forces[1],
        step_max_total_force_n=top_forces[2],
        parts=parts,
        pairs=pairs,
    )


def validate_unity_contact_diagnostic_scope(
    *,
    enabled: Any,
    backend: Any,
    wall_observe_only_enabled: bool,
    wall_first_touch_mode: str,
    high_force_n: Any,
) -> str:
    """Require an explicit AGX Unity marker around the combined diagnostic."""

    if not isinstance(enabled, bool):
        raise ValueError(
            "unity_contact_diagnostic_observe_only_enabled "
            "must be a boolean"
        )
    if not isinstance(backend, str):
        raise ValueError("unity_contact_diagnostic_backend must be a string")
    normalized_backend = backend.strip()
    if not enabled:
        if normalized_backend:
            raise ValueError(
                "unity_contact_diagnostic_backend must be empty when "
                "unity contact diagnostic is disabled"
            )
        return ""
    if normalized_backend != UNITY_CONTACT_DIAGNOSTIC_BACKEND_AGX_UNITY:
        raise ValueError(
            "unity_contact_diagnostic_backend must be 'agx_unity' "
            "when Unity contact diagnostic is enabled"
        )
    if (
        not bool(wall_observe_only_enabled)
        or str(wall_first_touch_mode)
        != WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS
    ):
        raise ValueError(
            "Unity contact diagnostic requires "
            "wall_contact_diagnostic_observe_only_enabled=true and "
            "wall_first_touch_mode='record_bucket_all_contacts'"
        )
    if float(high_force_n) != WALL_CONTACT_HARD_MAX_FORCE_N:
        raise ValueError(
            "Unity contact diagnostic requires wall_high_force_n "
            "exactly 100000"
        )
    return normalized_backend


@dataclass
class FactoryFloorContactService:
    """Validate sidecar and legacy 107D lineage before allowing contact."""

    high_force_n: float = 100_000.0
    _last_sidecar_session_count: int = field(default=0, init=False)
    _last_sidecar_detail: WorktoolFactoryFloorContactDetail | None = field(
        default=None,
        init=False,
    )
    _sidecar_clear_ticks: int = field(default=0, init=False)
    _last_aggregate_session_count: int = field(default=0, init=False)
    _last_aggregate_positive: bool = field(default=False, init=False)
    _last_cache_key: tuple[Any, ...] | None = field(default=None, init=False)
    _last_cache_result: FactoryFloorContactGateResult | None = field(
        default=None,
        init=False,
    )

    def __post_init__(self) -> None:
        self.high_force_n = validate_wall_high_force_threshold(
            self.high_force_n
        )

    def reset(self) -> None:
        self._last_sidecar_session_count = 0
        self._last_sidecar_detail = None
        self._sidecar_clear_ticks = 0
        self._last_aggregate_session_count = 0
        self._last_aggregate_positive = False
        self._last_cache_key = None
        self._last_cache_result = None

    @property
    def last_result(self) -> FactoryFloorContactGateResult | None:
        return self._last_cache_result

    def evaluate(
        self,
        *,
        typed_mask: float,
        aggregate_force_n: float,
        aggregate_session_count: float,
        warnings: Sequence[Any],
        step_id: int,
        sim_time_ns: int | None,
    ) -> FactoryFloorContactGateResult:
        warning_key = (
            tuple(repr(value) for value in warnings)
            if isinstance(warnings, Sequence)
            and not isinstance(warnings, (str, bytes))
            else ("<invalid-warning-container>",)
        )
        cache_key = (
            repr(float(typed_mask)),
            repr(float(aggregate_force_n)),
            repr(float(aggregate_session_count)),
            warning_key,
            int(step_id),
            None if sim_time_ns is None else int(sim_time_ns),
        )
        if cache_key == self._last_cache_key:
            assert self._last_cache_result is not None
            return self._last_cache_result
        if (
            isinstance(warnings, (str, bytes))
            or not isinstance(warnings, Sequence)
        ):
            return self._cache(cache_key, self._invalid_result())
        warning_values = list(warnings)
        monitor_status_reason = _monitor_status_failure_reason(
            warning_values
        )
        if monitor_status_reason:
            return self._cache(
                cache_key,
                FactoryFloorContactGateResult(
                    kind=BOTTOM_GATE_TERMINAL,
                    reason=monitor_status_reason,
                ),
            )
        if _has_incomplete_lineage_warning(warning_values):
            return self._cache(
                cache_key,
                FactoryFloorContactGateResult(
                    kind=BOTTOM_GATE_TERMINAL,
                    reason="factory_floor_contact_lineage_incomplete",
                ),
            )

        aggregate = self._validated_aggregate(
            typed_mask=typed_mask,
            aggregate_force_n=aggregate_force_n,
            aggregate_session_count=aggregate_session_count,
        )
        if aggregate is None:
            return self._cache(cache_key, self._invalid_result())
        contact_positive, force, session_count = aggregate
        matching_sidecars = [
            value
            for value in warning_values
            if isinstance(value, str)
            and value.startswith(
                WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX
            )
        ]
        if not matching_sidecars:
            if contact_positive:
                return self._cache(cache_key, self._invalid_result())
            if not self._aggregate_clear_valid(
                force=force,
                session_count=session_count,
            ):
                return self._cache(cache_key, self._invalid_result())
            self._record_aggregate(
                contact_positive=False,
                session_count=session_count,
            )
            self._sidecar_clear_ticks += 1
            return self._cache(
                cache_key,
                FactoryFloorContactGateResult(
                    force_n=force,
                    session_count=session_count,
                ),
            )
        if len(matching_sidecars) != 1 or sim_time_ns is None:
            return self._cache(cache_key, self._invalid_result())
        try:
            detail = parse_worktool_factory_floor_contact_detail(
                warning_values,
                expected_step_id=step_id,
                expected_sim_time_ns=sim_time_ns,
            )
        except FactoryFloorContactDetailContractError:
            return self._cache(cache_key, self._invalid_result())
        if not self._sidecar_sequence_valid(detail):
            return self._cache(
                cache_key,
                self._invalid_result(detail=detail),
            )
        if contact_positive:
            if not self._aggregate_contact_valid(
                force=force,
                session_count=session_count,
            ):
                return self._cache(
                    cache_key,
                    self._invalid_result(detail=detail),
                )
        elif not self._aggregate_clear_valid(
            force=force,
            session_count=session_count,
        ):
            return self._cache(
                cache_key,
                self._invalid_result(detail=detail),
            )

        self._record_sidecar(detail)
        self._record_aggregate(
            contact_positive=contact_positive,
            session_count=session_count,
        )
        if any(part != "bucket" for part in detail.parts):
            return self._cache(
                cache_key,
                FactoryFloorContactGateResult(
                    kind=BOTTOM_GATE_TERMINAL,
                    reason=(
                        FACTORY_FLOOR_CONTACT_FORBIDDEN_COMPONENT_REASON
                    ),
                    force_n=force,
                    session_count=session_count,
                    detail=detail,
                ),
            )
        sidecar_forces = [
            force_value
            for pair in detail.pairs
            for force_value in (
                pair.max_normal_force_n,
                pair.max_tangential_force_n,
                pair.max_total_force_n,
            )
        ]
        forces = [
            force,
            detail.step_max_normal_force_n,
            detail.step_max_tangential_force_n,
            detail.step_max_total_force_n,
            *sidecar_forces,
        ]
        if any(value >= self.high_force_n for value in forces):
            return self._cache(
                cache_key,
                FactoryFloorContactGateResult(
                    kind=BOTTOM_GATE_TERMINAL,
                    reason=FACTORY_FLOOR_CONTACT_HIGH_FORCE_REASON,
                    force_n=force,
                    session_count=session_count,
                    detail=detail,
                ),
            )
        return self._cache(
            cache_key,
            FactoryFloorContactGateResult(
                kind=BOTTOM_GATE_DIAGNOSTIC_ALLOW,
                reason="factory_floor_contact_bucket_record_only",
                force_n=force,
                session_count=session_count,
                detail=detail,
            ),
        )

    def _validated_aggregate(
        self,
        *,
        typed_mask: float,
        aggregate_force_n: float,
        aggregate_session_count: float,
    ) -> tuple[bool, float, int] | None:
        mask = float(typed_mask)
        force = float(aggregate_force_n)
        session_value = float(aggregate_session_count)
        if (
            not np.isfinite(mask)
            or mask not in {0.0, 1.0}
            or not np.isfinite(force)
            or force < 0.0
            or not np.isfinite(session_value)
            or session_value < 0.0
            or not session_value.is_integer()
        ):
            return None
        return mask == 1.0, force, int(session_value)

    def _aggregate_contact_valid(
        self,
        *,
        force: float,
        session_count: int,
    ) -> bool:
        if force < 0.0 or session_count < 1:
            return False
        if self._last_aggregate_positive:
            return session_count == self._last_aggregate_session_count
        return session_count == self._last_aggregate_session_count + 1

    def _aggregate_clear_valid(
        self,
        *,
        force: float,
        session_count: int,
    ) -> bool:
        return bool(
            abs(force) <= 1.0e-6
            and session_count == self._last_aggregate_session_count
        )

    def _sidecar_sequence_valid(
        self,
        detail: WorktoolFactoryFloorContactDetail,
    ) -> bool:
        previous = self._last_sidecar_detail
        if previous is None:
            return bool(
                self._last_sidecar_session_count == 0
                and detail.session_id == 1
                and detail.consecutive_contact_steps == 1
            )
        if self._sidecar_clear_ticks == 0:
            return bool(
                detail.session_id == previous.session_id
                and detail.session_count
                == self._last_sidecar_session_count
                and detail.consecutive_contact_steps
                == previous.consecutive_contact_steps + 1
                and detail.session_duration_s
                > previous.session_duration_s
            )
        return bool(
            detail.session_id == previous.session_id + 1
            and detail.session_count
            == self._last_sidecar_session_count + 1
            and detail.consecutive_contact_steps == 1
        )

    def _record_sidecar(
        self,
        detail: WorktoolFactoryFloorContactDetail,
    ) -> None:
        self._last_sidecar_detail = detail
        self._last_sidecar_session_count = detail.session_count
        self._sidecar_clear_ticks = 0

    def _record_aggregate(
        self,
        *,
        contact_positive: bool,
        session_count: int,
    ) -> None:
        self._last_aggregate_positive = bool(contact_positive)
        self._last_aggregate_session_count = int(session_count)

    def _cache(
        self,
        cache_key: tuple[Any, ...],
        result: FactoryFloorContactGateResult,
    ) -> FactoryFloorContactGateResult:
        self._last_cache_key = cache_key
        self._last_cache_result = result
        return result

    @staticmethod
    def _invalid_result(
        *,
        detail: WorktoolFactoryFloorContactDetail | None = None,
    ) -> FactoryFloorContactGateResult:
        return FactoryFloorContactGateResult(
            kind=BOTTOM_GATE_TERMINAL,
            reason="factory_floor_contact_detail_invalid",
            detail=detail,
        )


def _has_incomplete_lineage_warning(warnings: Sequence[Any]) -> bool:
    incomplete_schemas = (
        WORKTOOL_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA,
        BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA,
    )
    incomplete_prefixes = (
        WORKTOOL_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_PREFIX,
        BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_PREFIX,
    )
    for value in warnings:
        if not isinstance(value, str):
            continue
        if value in {
            *incomplete_schemas,
        } or value.startswith(incomplete_prefixes):
            return True
    return False


def _monitor_status_failure_reason(warnings: Sequence[Any]) -> str:
    statuses = [
        value
        for value in warnings
        if isinstance(value, str)
        and value.startswith(WORKTOOL_CONTACT_MONITOR_STATUS_PREFIX)
    ]
    if not statuses:
        return ""
    if len(statuses) != 1:
        return "factory_floor_contact_detail_invalid"
    if statuses[0] in {
        WORKTOOL_CONTACT_MONITOR_STATUS_MISSING,
        WORKTOOL_CONTACT_MONITOR_STATUS_NOT_REGISTERED,
    }:
        return "factory_floor_contact_lineage_incomplete"
    return "factory_floor_contact_detail_invalid"


def _parse_pair(
    value: Any,
    *,
    index: int,
) -> WorktoolFactoryFloorContactPair:
    if not isinstance(value, dict):
        raise FactoryFloorContactDetailContractError(
            f"pairs[{index}] must be an object"
        )
    _require_exact_fields(value, _PAIR_FIELDS, f"pairs[{index}]")
    points = _points(
        value["contact_points_world_m"],
        f"pairs[{index}].contact_points_world_m",
    )
    contact_point_count = _integer(
        value["contact_point_count"],
        f"pairs[{index}].contact_point_count",
        minimum=1,
    )
    if len(points) != contact_point_count:
        raise FactoryFloorContactDetailContractError(
            f"pairs[{index}] contact point count differs from points"
        )
    representative = _nullable_point(
        value["representative_contact_point_component_local_m"],
        f"pairs[{index}].representative_contact_point_component_local_m",
    )
    return WorktoolFactoryFloorContactPair(
        component=_string(
            value["component"],
            f"pairs[{index}].component",
        ),
        machine_shape_path=_string(
            value["machine_shape_path"],
            f"pairs[{index}].machine_shape_path",
        ),
        floor_shape_path=_string(
            value["floor_shape_path"],
            f"pairs[{index}].floor_shape_path",
        ),
        callback_count=_integer(
            value["callback_count"],
            f"pairs[{index}].callback_count",
            minimum=1,
        ),
        contact_point_count=contact_point_count,
        max_normal_force_n=_force_number(
            value["max_normal_force_n"],
            f"pairs[{index}].max_normal_force_n",
        ),
        max_tangential_force_n=_force_number(
            value["max_tangential_force_n"],
            f"pairs[{index}].max_tangential_force_n",
        ),
        max_total_force_n=_force_number(
            value["max_total_force_n"],
            f"pairs[{index}].max_total_force_n",
        ),
        contact_points_world_m=points,
        representative_contact_point_component_local_m=representative,
    )


def _require_exact_fields(
    value: dict[str, Any],
    expected: frozenset[str],
    label: str,
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise FactoryFloorContactDetailContractError(
            f"{label} fields differ: "
            f"missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FactoryFloorContactDetailContractError(
            f"{label} must be a non-empty string"
        )
    return value


def _integer(value: Any, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise FactoryFloorContactDetailContractError(
            f"{label} must be an integer"
        )
    result = int(value)
    if result < minimum:
        raise FactoryFloorContactDetailContractError(
            f"{label} must be at least {minimum}"
        )
    return result


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FactoryFloorContactDetailContractError(
            f"{label} must be numeric"
        )
    result = float(value)
    if not np.isfinite(result):
        raise FactoryFloorContactDetailContractError(
            f"{label} must be finite"
        )
    return result


def _force_number(value: Any, label: str) -> float:
    result = _finite_number(value, label)
    if result < 0.0:
        raise FactoryFloorContactDetailContractError(
            f"{label} must be non-negative"
        )
    return result


def _ordered_unique_components(
    value: Any,
    label: str,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise FactoryFloorContactDetailContractError(
            f"{label} must be a non-empty list"
        )
    result = tuple(_string(item, f"{label}[]") for item in value)
    if any(item not in _COMPONENT_ORDER for item in result):
        raise FactoryFloorContactDetailContractError(
            f"{label} contains a non-canonical component"
        )
    if result != tuple(
        sorted(
            set(result),
            key=_COMPONENT_ORDER.__getitem__,
        )
    ):
        raise FactoryFloorContactDetailContractError(
            f"{label} must use canonical part order and be unique"
        )
    return result


def _points(
    value: Any,
    label: str,
) -> tuple[tuple[float, float, float], ...]:
    if not isinstance(value, list) or not value:
        raise FactoryFloorContactDetailContractError(
            f"{label} must be a non-empty list"
        )
    points = tuple(
        _point(item, f"{label}[{index}]")
        for index, item in enumerate(value)
    )
    if points != tuple(sorted(set(points))):
        raise FactoryFloorContactDetailContractError(
            f"{label} must be sorted and unique"
        )
    return points


def _nullable_point(
    value: Any,
    label: str,
) -> tuple[float, float, float] | None:
    if value is None:
        return None
    return _point(value, label)


def _point(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise FactoryFloorContactDetailContractError(
            f"{label} must contain three coordinates"
        )
    return tuple(
        _finite_number(item, f"{label}[{index}]")
        for index, item in enumerate(value)
    )


def _force_close(first: float, second: float) -> bool:
    return bool(
        abs(first - second) <= max(1.0e-3, abs(second) * 1.0e-5)
    )


__all__ = [
    "BOTTOM_GATE_DIAGNOSTIC_ALLOW",
    "BOTTOM_GATE_NONE",
    "BOTTOM_GATE_TERMINAL",
    "BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_PREFIX",
    "BUCKET_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA",
    "FactoryFloorContactDetailContractError",
    "FactoryFloorContactGateResult",
    "FactoryFloorContactService",
    "FACTORY_FLOOR_CONTACT_FORBIDDEN_COMPONENT_REASON",
    "FACTORY_FLOOR_CONTACT_HIGH_FORCE_REASON",
    "UNITY_CONTACT_DIAGNOSTIC_BACKEND_AGX_UNITY",
    "WORKTOOL_CONTACT_MONITOR_STATUS_MISSING",
    "WORKTOOL_CONTACT_MONITOR_STATUS_NOT_REGISTERED",
    "WORKTOOL_CONTACT_MONITOR_STATUS_PREFIX",
    "WORKTOOL_FACTORY_FLOOR_CONTACT_COMPONENTS",
    "WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX",
    "WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_SCHEMA",
    "WORKTOOL_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_PREFIX",
    "WORKTOOL_FACTORY_FLOOR_CONTACT_LINEAGE_INCOMPLETE_SCHEMA",
    "WorktoolFactoryFloorContactDetail",
    "WorktoolFactoryFloorContactPair",
    "parse_worktool_factory_floor_contact_detail",
    "validate_unity_contact_diagnostic_scope",
]
