"""Typed Unity wall-contact sidecar parsing and first-session decisions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from numbers import Integral
from typing import Any

import numpy as np

WORKTOOL_WALL_CONTACT_DETAIL_SCHEMA = "worktool_wall_contact_detail_v1"
WORKTOOL_WALL_CONTACT_DETAIL_PREFIX = (
    f"{WORKTOOL_WALL_CONTACT_DETAIL_SCHEMA}:"
)
WORKTOOL_WALL_CONTACT_COMPONENTS = frozenset(
    {"boom", "bucket", "other", "stick"}
)
WORKTOOL_WALL_CONTACT_WALL_NAMES = frozenset(
    {
        "Dig_XMax_Board",
        "Dig_XMin_Board",
        "Dig_ZMax_Board",
        "Dig_ZMin_Board",
    }
)

WALL_FIRST_TOUCH_MODE_INTERRUPT = "interrupt"
WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_FIRST_SESSION = (
    "record_bucket_first_session"
)
WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS = (
    "record_bucket_all_contacts"
)
WALL_CONTACT_HARD_MAX_FORCE_N = 100_000.0
WALL_CONTACT_SESSION_END_CLEAR_TICKS_DEFAULT = 1
WALL_CONTACT_SESSION_END_CLEAR_TICKS_B2 = 2
SUPPORTED_WALL_FIRST_TOUCH_MODES = frozenset(
    {
        WALL_FIRST_TOUCH_MODE_INTERRUPT,
        WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS,
        WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_FIRST_SESSION,
    }
)

WALL_GATE_NONE = "none"
WALL_GATE_DIAGNOSTIC_ALLOW = "diagnostic_allow"
WALL_GATE_INTERRUPT = "interrupt"
WALL_GATE_TERMINAL = "terminal"

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
        "session_normal_impulse_n_s",
        "parts",
        "walls",
        "pairs",
    }
)
_PAIR_FIELDS = frozenset(
    {
        "component",
        "machine_shape_path",
        "wall_name",
        "wall_shape_path",
        "callback_count",
        "contact_point_count",
        "max_normal_force_n",
        "max_tangential_force_n",
        "max_total_force_n",
        "contact_points_world_m",
        "representative_contact_point_component_local_m",
        "tangential_displacement_m",
    }
)


class WallContactDetailContractError(ValueError):
    """Raised when a wall-positive tick lacks one canonical typed sidecar."""


@dataclass(frozen=True)
class WorktoolWallContactPair:
    component: str
    machine_shape_path: str
    wall_name: str
    wall_shape_path: str
    callback_count: int
    contact_point_count: int
    max_normal_force_n: float
    max_tangential_force_n: float
    max_total_force_n: float
    contact_points_world_m: tuple[tuple[float, float, float], ...]
    representative_contact_point_component_local_m: (
        tuple[float, float, float] | None
    )
    tangential_displacement_m: float


@dataclass(frozen=True)
class WorktoolWallContactDetail:
    schema: str
    step_id: int
    sim_time_s: float
    delta_time_s: float
    session_id: int
    session_count: int
    consecutive_contact_steps: int
    session_duration_s: float
    session_normal_impulse_n_s: float
    parts: tuple[str, ...]
    walls: tuple[str, ...]
    pairs: tuple[WorktoolWallContactPair, ...]


@dataclass(frozen=True)
class WallContactGateResult:
    kind: str = WALL_GATE_NONE
    reason: str = ""
    detail: WorktoolWallContactDetail | None = None

    @property
    def stops_action(self) -> bool:
        return self.kind in {WALL_GATE_INTERRUPT, WALL_GATE_TERMINAL}

    @property
    def terminal(self) -> bool:
        return self.kind == WALL_GATE_TERMINAL

    @property
    def diagnostic_allowed(self) -> bool:
        return self.kind == WALL_GATE_DIAGNOSTIC_ALLOW


def validate_wall_first_touch_mode(value: str) -> str:
    mode = str(value).strip()
    if mode not in SUPPORTED_WALL_FIRST_TOUCH_MODES:
        allowed = "|".join(sorted(SUPPORTED_WALL_FIRST_TOUCH_MODES))
        raise ValueError(
            f"wall_first_touch_mode must be one of {allowed}; got {mode!r}"
        )
    return mode


def validate_wall_high_force_threshold(value: float) -> float:
    threshold = float(value)
    if (
        not np.isfinite(threshold)
        or threshold <= 0.0
        or threshold > WALL_CONTACT_HARD_MAX_FORCE_N
    ):
        raise ValueError(
            "wall_high_force_n must be finite, positive, and at most 100000"
        )
    return threshold


def validate_wall_contact_session_end_clear_ticks(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(
            "wall_contact_session_end_clear_ticks must be integer 1 or 2"
        )
    clear_ticks = int(value)
    if clear_ticks not in {
        WALL_CONTACT_SESSION_END_CLEAR_TICKS_DEFAULT,
        WALL_CONTACT_SESSION_END_CLEAR_TICKS_B2,
    }:
        raise ValueError(
            "wall_contact_session_end_clear_ticks must be integer 1 or 2"
        )
    return clear_ticks


def parse_worktool_wall_contact_detail(
    warnings: Sequence[Any],
    *,
    expected_step_id: int | None = None,
    expected_sim_time_ns: int | None = None,
) -> WorktoolWallContactDetail:
    """Parse exactly one canonical contact warning and validate its lineage."""

    if isinstance(warnings, (str, bytes)) or not isinstance(
        warnings, Sequence
    ):
        raise WallContactDetailContractError(
            "worktool wall contact warnings must be a sequence"
        )
    matching = [
        value
        for value in warnings
        if isinstance(value, str)
        and value.startswith(WORKTOOL_WALL_CONTACT_DETAIL_PREFIX)
    ]
    if not matching:
        raise WallContactDetailContractError(
            "worktool wall contact detail missing"
        )
    if len(matching) != 1:
        raise WallContactDetailContractError(
            "worktool wall contact detail ambiguous"
        )
    encoded = matching[0][len(WORKTOOL_WALL_CONTACT_DETAIL_PREFIX) :]
    try:
        payload = json.loads(encoded)
    except (json.JSONDecodeError, TypeError) as exc:
        raise WallContactDetailContractError(
            "worktool wall contact detail JSON invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise WallContactDetailContractError(
            "worktool wall contact detail must be an object"
        )
    _require_exact_fields(payload, _TOP_LEVEL_FIELDS, "top-level")
    schema = _string(payload["schema"], "schema")
    if schema != WORKTOOL_WALL_CONTACT_DETAIL_SCHEMA:
        raise WallContactDetailContractError(
            f"worktool wall contact schema invalid: {schema!r}"
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
    session_impulse = _force_number(
        payload["session_normal_impulse_n_s"],
        "session_normal_impulse_n_s",
    )
    if sim_time_s < 0.0:
        raise WallContactDetailContractError("sim_time_s must be non-negative")
    if delta_time_s <= 0.0:
        raise WallContactDetailContractError("delta_time_s must be positive")
    if session_duration_s <= 0.0:
        raise WallContactDetailContractError(
            "session_duration_s must be positive"
        )
    if session_impulse < 0.0:
        raise WallContactDetailContractError(
            "session_normal_impulse_n_s must be non-negative"
        )
    if session_id != session_count:
        raise WallContactDetailContractError(
            "session_id and session_count lineage differ"
        )

    parts = _sorted_unique_strings(payload["parts"], "parts")
    walls = _sorted_unique_strings(payload["walls"], "walls")
    raw_pairs = payload["pairs"]
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise WallContactDetailContractError("pairs must be a non-empty list")
    pairs = tuple(
        _parse_pair(value, index=index)
        for index, value in enumerate(raw_pairs)
    )
    if any(
        pair.component not in WORKTOOL_WALL_CONTACT_COMPONENTS
        for pair in pairs
    ):
        raise WallContactDetailContractError(
            "pair component is not canonical"
        )
    if any(
        pair.wall_name not in WORKTOOL_WALL_CONTACT_WALL_NAMES
        for pair in pairs
    ):
        raise WallContactDetailContractError("pair wall is not canonical")
    pair_keys = tuple(
        (
            pair.component,
            pair.machine_shape_path,
            pair.wall_name,
            pair.wall_shape_path,
        )
        for pair in pairs
    )
    if pair_keys != tuple(sorted(set(pair_keys))):
        raise WallContactDetailContractError(
            "pairs must use deterministic unique ordering"
        )
    pair_parts = tuple(sorted({pair.component for pair in pairs}))
    pair_walls = tuple(sorted({pair.wall_name for pair in pairs}))
    if parts != pair_parts:
        raise WallContactDetailContractError(
            "parts do not match pair components"
        )
    if walls != pair_walls:
        raise WallContactDetailContractError(
            "walls do not match pair wall names"
        )
    if expected_step_id is not None and step_id != int(expected_step_id):
        raise WallContactDetailContractError(
            "wall contact detail step lineage differs"
        )
    if expected_sim_time_ns is not None:
        expected_seconds = int(expected_sim_time_ns) / 1_000_000_000.0
        tolerance = max(1.0e-6, abs(delta_time_s) * 1.0e-5)
        if abs(sim_time_s - expected_seconds) > tolerance:
            raise WallContactDetailContractError(
                "wall contact detail sim-time lineage differs"
            )
    return WorktoolWallContactDetail(
        schema=schema,
        step_id=step_id,
        sim_time_s=sim_time_s,
        delta_time_s=delta_time_s,
        session_id=session_id,
        session_count=session_count,
        consecutive_contact_steps=consecutive_steps,
        session_duration_s=session_duration_s,
        session_normal_impulse_n_s=session_impulse,
        parts=parts,
        walls=walls,
        pairs=pairs,
    )


@dataclass
class WallContactFirstSessionService:
    """Stateful hard gate with explicit diagnostic bucket-contact modes."""

    mode: str = WALL_FIRST_TOUCH_MODE_INTERRUPT
    high_force_n: float = 100_000.0
    session_end_clear_ticks: int = (
        WALL_CONTACT_SESSION_END_CLEAR_TICKS_DEFAULT
    )
    _diagnostic_started: bool = field(default=False, init=False)
    _diagnostic_consumed: bool = field(default=False, init=False)
    _consecutive_clear_ticks: int = field(default=0, init=False)
    _session_id: int = field(default=-1, init=False)
    _last_aggregate_session_count: int = field(default=0, init=False)
    _wall_name: str = field(default="", init=False)
    _last_consecutive_steps: int = field(default=0, init=False)
    _last_session_duration_s: float = field(default=0.0, init=False)
    _last_cache_key: tuple[Any, ...] | None = field(default=None, init=False)
    _last_cache_result: WallContactGateResult | None = field(
        default=None,
        init=False,
    )

    def __post_init__(self) -> None:
        self.mode = validate_wall_first_touch_mode(self.mode)
        self.high_force_n = validate_wall_high_force_threshold(
            self.high_force_n
        )
        self.session_end_clear_ticks = (
            validate_wall_contact_session_end_clear_ticks(
                self.session_end_clear_ticks
            )
        )

    def reset(self) -> None:
        self._diagnostic_started = False
        self._diagnostic_consumed = False
        self._consecutive_clear_ticks = 0
        self._session_id = -1
        self._last_aggregate_session_count = 0
        self._wall_name = ""
        self._last_consecutive_steps = 0
        self._last_session_duration_s = 0.0
        self._last_cache_key = None
        self._last_cache_result = None

    @property
    def last_result(self) -> WallContactGateResult | None:
        return self._last_cache_result

    def evaluate(
        self,
        *,
        wall_positive: bool,
        aggregate_session_count: float,
        aggregate_force_n: float,
        warnings: Sequence[Any],
        step_id: int,
        sim_time_ns: int | None,
    ) -> WallContactGateResult:
        cache_key = (
            bool(wall_positive),
            repr(float(aggregate_session_count)),
            repr(float(aggregate_force_n)),
            tuple(repr(value) for value in warnings),
            int(step_id),
            None if sim_time_ns is None else int(sim_time_ns),
        )
        if cache_key == self._last_cache_key:
            assert self._last_cache_result is not None
            return self._last_cache_result

        matching_sidecars = [
            value
            for value in warnings
            if isinstance(value, str)
            and value.startswith(WORKTOOL_WALL_CONTACT_DETAIL_PREFIX)
        ]
        try:
            aggregate_sessions_any = _integer_number(
                aggregate_session_count,
                "aggregate wall session count",
                minimum=0,
            )
        except WallContactDetailContractError:
            return self._cache(
                cache_key,
                WallContactGateResult(
                    kind=WALL_GATE_TERMINAL,
                    reason="wall_contact_detail_invalid",
                ),
            )
        aggregate_force_any = float(aggregate_force_n)

        if not wall_positive:
            if (
                matching_sidecars
                or not np.isfinite(aggregate_force_any)
                or aggregate_force_any < 0.0
                or abs(aggregate_force_any) > 1.0e-6
                or aggregate_sessions_any
                != self._last_aggregate_session_count
            ):
                return self._cache(
                    cache_key,
                    WallContactGateResult(
                        kind=WALL_GATE_TERMINAL,
                        reason="wall_contact_detail_invalid",
                    ),
                )
            if self._diagnostic_started and not self._diagnostic_consumed:
                self._consecutive_clear_ticks += 1
                if (
                    self.mode
                    != WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS
                    and
                    self._consecutive_clear_ticks
                    >= self.session_end_clear_ticks
                ):
                    self._diagnostic_consumed = True
            return self._cache(cache_key, WallContactGateResult())

        try:
            detail = parse_worktool_wall_contact_detail(
                warnings,
                expected_step_id=step_id,
                expected_sim_time_ns=sim_time_ns,
            )
            aggregate_sessions = _integer_number(
                aggregate_session_count,
                "aggregate wall session count",
                minimum=1,
            )
        except WallContactDetailContractError:
            return self._cache(
                cache_key,
                WallContactGateResult(
                    kind=WALL_GATE_TERMINAL,
                    reason="wall_contact_detail_invalid",
                ),
            )

        if detail.session_count != aggregate_sessions:
            return self._cache(
                cache_key,
                WallContactGateResult(
                    kind=WALL_GATE_TERMINAL,
                    reason="wall_contact_detail_invalid",
                    detail=detail,
                ),
            )
        if (
            self.mode
            != WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS
            and len(detail.walls) != 1
        ):
            return self._cache(
                cache_key,
                WallContactGateResult(
                    kind=WALL_GATE_TERMINAL,
                    reason="wall_contact_detail_invalid",
                    detail=detail,
                ),
            )
        sidecar_max_force = max(
            pair.max_normal_force_n for pair in detail.pairs
        )
        aggregate_force = float(aggregate_force_n)
        if np.isfinite(aggregate_force) and np.isfinite(sidecar_max_force):
            tolerance = max(1.0e-3, abs(sidecar_max_force) * 1.0e-5)
            if abs(aggregate_force - sidecar_max_force) > tolerance:
                return self._cache(
                    cache_key,
                    WallContactGateResult(
                        kind=WALL_GATE_TERMINAL,
                        reason="wall_contact_detail_invalid",
                        detail=detail,
                    ),
                )
        if any(part != "bucket" for part in detail.parts):
            return self._cache(
                cache_key,
                WallContactGateResult(
                    kind=WALL_GATE_TERMINAL,
                    reason="wall_contact_forbidden_component",
                    detail=detail,
                ),
            )

        pair_forces = [
            force
            for pair in detail.pairs
            for force in (
                pair.max_normal_force_n,
                pair.max_tangential_force_n,
                pair.max_total_force_n,
            )
        ]
        forces = [float(aggregate_force_n), *pair_forces]
        if (
            not np.isfinite(detail.session_normal_impulse_n_s)
            or not all(np.isfinite(force) for force in forces)
            or any(force >= self.high_force_n for force in forces)
        ):
            return self._cache(
                cache_key,
                WallContactGateResult(
                    kind=WALL_GATE_TERMINAL,
                    reason="wall_contact_high_force",
                    detail=detail,
                ),
            )
        if any(force < 0.0 for force in forces):
            return self._cache(
                cache_key,
                WallContactGateResult(
                    kind=WALL_GATE_TERMINAL,
                    reason="wall_contact_detail_invalid",
                    detail=detail,
                ),
            )
        if self.mode == WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS:
            sequence_valid = False
            if not self._diagnostic_started:
                sequence_valid = (
                    self._last_aggregate_session_count == 0
                    and aggregate_sessions == 1
                    and detail.session_id == 1
                    and detail.consecutive_contact_steps == 1
                )
                self._diagnostic_started = sequence_valid
            elif aggregate_sessions == self._last_aggregate_session_count:
                sequence_valid = (
                    detail.session_id == self._session_id
                    and detail.consecutive_contact_steps
                    > self._last_consecutive_steps
                    and detail.session_duration_s
                    > self._last_session_duration_s
                )
            elif (
                aggregate_sessions
                == self._last_aggregate_session_count + 1
            ):
                sequence_valid = (
                    self._consecutive_clear_ticks > 0
                    and detail.session_id == aggregate_sessions
                    and detail.consecutive_contact_steps == 1
                )
            if not sequence_valid:
                return self._cache(
                    cache_key,
                    WallContactGateResult(
                        kind=WALL_GATE_TERMINAL,
                        reason="wall_contact_detail_invalid",
                        detail=detail,
                    ),
                )
            self._session_id = detail.session_id
            self._last_consecutive_steps = (
                detail.consecutive_contact_steps
            )
            self._last_session_duration_s = detail.session_duration_s
            self._last_aggregate_session_count = aggregate_sessions
            self._consecutive_clear_ticks = 0
            return self._cache(
                cache_key,
                WallContactGateResult(
                    kind=WALL_GATE_DIAGNOSTIC_ALLOW,
                    reason="wall_contact_bucket_record_only",
                    detail=detail,
                ),
            )
        if self._diagnostic_consumed:
            return self._cache(
                cache_key,
                WallContactGateResult(
                    kind=WALL_GATE_TERMINAL,
                    reason="wall_contact_repeat_session",
                    detail=detail,
                ),
            )

        wall_name = detail.walls[0]
        if not self._diagnostic_started:
            if aggregate_sessions != 1:
                return self._cache(
                    cache_key,
                    WallContactGateResult(
                        kind=WALL_GATE_TERMINAL,
                        reason="wall_contact_repeat_session",
                        detail=detail,
                    ),
                )
            self._diagnostic_started = True
            self._session_id = detail.session_id
            self._wall_name = wall_name
        else:
            if wall_name != self._wall_name:
                return self._cache(
                    cache_key,
                    WallContactGateResult(
                        kind=WALL_GATE_TERMINAL,
                        reason="wall_contact_identity_drift",
                        detail=detail,
                    ),
                )
            resumed_before_session_end = (
                0
                < self._consecutive_clear_ticks
                < self.session_end_clear_ticks
            )
            same_raw_session = (
                detail.session_id == self._session_id
                and aggregate_sessions
                == self._last_aggregate_session_count
            )
            next_raw_session_after_tolerated_gap = (
                resumed_before_session_end
                and detail.session_id != self._session_id
                and aggregate_sessions
                == self._last_aggregate_session_count + 1
            )
            if not (
                same_raw_session
                or next_raw_session_after_tolerated_gap
            ):
                return self._cache(
                    cache_key,
                    WallContactGateResult(
                        kind=WALL_GATE_TERMINAL,
                        reason="wall_contact_repeat_session",
                        detail=detail,
                    ),
                )
            if same_raw_session and (
                detail.consecutive_contact_steps
                <= self._last_consecutive_steps
                or detail.session_duration_s
                <= self._last_session_duration_s
            ):
                return self._cache(
                    cache_key,
                    WallContactGateResult(
                        kind=WALL_GATE_TERMINAL,
                        reason="wall_contact_identity_drift",
                        detail=detail,
                    ),
                )
            if next_raw_session_after_tolerated_gap:
                if detail.consecutive_contact_steps != 1:
                    return self._cache(
                        cache_key,
                        WallContactGateResult(
                            kind=WALL_GATE_TERMINAL,
                            reason="wall_contact_identity_drift",
                            detail=detail,
                        ),
                    )
                self._session_id = detail.session_id
        self._last_consecutive_steps = detail.consecutive_contact_steps
        self._last_session_duration_s = detail.session_duration_s
        self._last_aggregate_session_count = aggregate_sessions
        self._consecutive_clear_ticks = 0
        if self.mode == WALL_FIRST_TOUCH_MODE_INTERRUPT:
            return self._cache(
                cache_key,
                WallContactGateResult(
                    kind=WALL_GATE_INTERRUPT,
                    reason="wall_contact_first_session",
                    detail=detail,
                ),
            )
        return self._cache(
            cache_key,
            WallContactGateResult(
                kind=WALL_GATE_DIAGNOSTIC_ALLOW,
                reason="wall_contact_bucket_first_session_allowed",
                detail=detail,
            ),
        )

    def _cache(
        self,
        key: tuple[Any, ...],
        result: WallContactGateResult,
    ) -> WallContactGateResult:
        self._last_cache_key = key
        self._last_cache_result = result
        return result


def _parse_pair(value: Any, *, index: int) -> WorktoolWallContactPair:
    if not isinstance(value, dict):
        raise WallContactDetailContractError(f"pairs[{index}] must be an object")
    _require_exact_fields(value, _PAIR_FIELDS, f"pairs[{index}]")
    component = _string(value["component"], f"pairs[{index}].component")
    machine_path = _string(
        value["machine_shape_path"],
        f"pairs[{index}].machine_shape_path",
    )
    wall_name = _string(value["wall_name"], f"pairs[{index}].wall_name")
    wall_path = _string(
        value["wall_shape_path"],
        f"pairs[{index}].wall_shape_path",
    )
    callback_count = _integer(
        value["callback_count"],
        f"pairs[{index}].callback_count",
        minimum=1,
    )
    contact_point_count = _integer(
        value["contact_point_count"],
        f"pairs[{index}].contact_point_count",
        minimum=1,
    )
    points = _points(
        value["contact_points_world_m"],
        f"pairs[{index}].contact_points_world_m",
    )
    if len(points) != contact_point_count:
        raise WallContactDetailContractError(
            f"pairs[{index}] contact point count differs from points"
        )
    local_value = value["representative_contact_point_component_local_m"]
    local_point = (
        None
        if local_value is None or local_value == []
        else _point(
            local_value,
            (
                f"pairs[{index}]"
                ".representative_contact_point_component_local_m"
            ),
        )
    )
    displacement = _finite_number(
        value["tangential_displacement_m"],
        f"pairs[{index}].tangential_displacement_m",
    )
    if displacement < 0.0:
        raise WallContactDetailContractError(
            f"pairs[{index}].tangential_displacement_m must be non-negative"
        )
    return WorktoolWallContactPair(
        component=component,
        machine_shape_path=machine_path,
        wall_name=wall_name,
        wall_shape_path=wall_path,
        callback_count=callback_count,
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
        representative_contact_point_component_local_m=local_point,
        tangential_displacement_m=displacement,
    )


def _require_exact_fields(
    value: dict[str, Any],
    expected: frozenset[str],
    field: str,
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise WallContactDetailContractError(
            f"{field} fields invalid: missing={missing}, extra={extra}"
        )


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WallContactDetailContractError(f"{field} must be a non-empty string")
    return value.strip()


def _sorted_unique_strings(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise WallContactDetailContractError(
            f"{field} must be a non-empty list"
        )
    strings = tuple(_string(item, f"{field}[]") for item in value)
    if strings != tuple(sorted(set(strings))):
        raise WallContactDetailContractError(
            f"{field} must be sorted and unique"
        )
    return strings


def _integer(value: Any, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WallContactDetailContractError(f"{field} must be an integer")
    if value < minimum:
        raise WallContactDetailContractError(
            f"{field} must be at least {minimum}"
        )
    return int(value)


def _integer_number(value: Any, field: str, *, minimum: int) -> int:
    number = _finite_number(value, field)
    integer = int(round(number))
    if abs(number - integer) > 1.0e-6 or integer < minimum:
        raise WallContactDetailContractError(
            f"{field} must be an integer at least {minimum}"
        )
    return integer


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WallContactDetailContractError(f"{field} must be numeric")
    return float(value)


def _force_number(value: Any, field: str) -> float:
    # Unity's strict JSON writer uses null for a non-finite force or impulse.
    # Preserve that as NaN so the decision service reaches the frozen
    # non-finite/high-force gate instead of misclassifying it as bad lineage.
    if value is None:
        return float("nan")
    return _number(value, field)


def _finite_number(value: Any, field: str) -> float:
    number = _number(value, field)
    if not np.isfinite(number):
        raise WallContactDetailContractError(f"{field} must be finite")
    return number


def _point(value: Any, field: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise WallContactDetailContractError(f"{field} must contain 3 values")
    point = tuple(_finite_number(item, f"{field}[]") for item in value)
    return (point[0], point[1], point[2])


def _points(
    value: Any,
    field: str,
) -> tuple[tuple[float, float, float], ...]:
    if not isinstance(value, list) or not value:
        raise WallContactDetailContractError(
            f"{field} must be a non-empty list"
        )
    return tuple(_point(point, f"{field}[]") for point in value)


__all__ = [
    "SUPPORTED_WALL_FIRST_TOUCH_MODES",
    "WALL_FIRST_TOUCH_MODE_INTERRUPT",
    "WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS",
    "WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_FIRST_SESSION",
    "WALL_CONTACT_HARD_MAX_FORCE_N",
    "WALL_CONTACT_SESSION_END_CLEAR_TICKS_B2",
    "WALL_CONTACT_SESSION_END_CLEAR_TICKS_DEFAULT",
    "WORKTOOL_WALL_CONTACT_DETAIL_PREFIX",
    "WORKTOOL_WALL_CONTACT_DETAIL_SCHEMA",
    "WORKTOOL_WALL_CONTACT_COMPONENTS",
    "WORKTOOL_WALL_CONTACT_WALL_NAMES",
    "WallContactDetailContractError",
    "WallContactFirstSessionService",
    "WallContactGateResult",
    "WorktoolWallContactDetail",
    "WorktoolWallContactPair",
    "parse_worktool_wall_contact_detail",
    "validate_wall_first_touch_mode",
    "validate_wall_high_force_threshold",
    "validate_wall_contact_session_end_clear_ticks",
]
