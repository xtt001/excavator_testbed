"""Return-to-dig handoff gate service."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import (
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX,
    RETURN_START_ENVELOPE_TOKEN_DIM,
)
from testbed.planner import return_to_dig_transition as _return_transition
from testbed.planner.primitive_decisions import PrimitiveBoundaryFacts
from testbed.planner.return_start_envelope import (
    ReturnStartEnvelopeConfig,
    ReturnStartEnvelopeState,
    normalize_plane_depth_mode,
    resolve_return_start_envelope_cell_id,
    return_start_envelope_gate_prior_context,
    return_start_envelope_token_has_gate_bounds,
    return_to_dig_start_envelope_ready,
)
from testbed.planner.snapshots import PlannerSnapshot

ReturnDirectHandoffAttemptConfig = _return_transition.ReturnDirectHandoffAttemptConfig
ReturnDirectHandoffAttemptFacts = _return_transition.ReturnDirectHandoffAttemptFacts
ReturnDirectHandoffAttemptOutcome = _return_transition.ReturnDirectHandoffAttemptOutcome
ReturnDirectHandoffAttemptRequest = _return_transition.ReturnDirectHandoffAttemptRequest
ReturnDirectHandoffRuntimeProjection = (
    _return_transition.ReturnDirectHandoffRuntimeProjection
)
ReturnToDigTransitionCompletion = _return_transition.ReturnToDigTransitionCompletion
ReturnToDigTransitionCompletionConfig = (
    _return_transition.ReturnToDigTransitionCompletionConfig
)
ReturnToDigTransitionCompletionFacts = (
    _return_transition.ReturnToDigTransitionCompletionFacts
)
ReturnToDigTransitionCompletionRequest = (
    _return_transition.ReturnToDigTransitionCompletionRequest
)
ReturnToDigTransitionConfig = _return_transition.ReturnToDigTransitionConfig
ReturnToDigTransitionCounterUpdate = (
    _return_transition.ReturnToDigTransitionCounterUpdate
)
ReturnToDigTransitionFacts = _return_transition.ReturnToDigTransitionFacts
ReturnToDigTransitionOutcome = _return_transition.ReturnToDigTransitionOutcome
ReturnToDigTransitionRequest = _return_transition.ReturnToDigTransitionRequest
ReturnToDigTransitionRuntimeProjection = (
    _return_transition.ReturnToDigTransitionRuntimeProjection
)
ReturnToDigTransitionService = _return_transition.ReturnToDigTransitionService


@dataclass(frozen=True)
class ReturnToDigPlannerConfig:
    return_to_dig_shallow_guard_enabled: bool
    return_to_dig_max_bucket_mass_kg: float
    return_to_dig_touch_tolerance_m: float
    return_to_dig_min_depth_m: float
    return_to_dig_max_depth_m: float
    return_to_dig_max_entry_error_m: float | None
    return_to_dig_start_envelope_gate_enabled: bool
    return_to_dig_start_envelope_spatial_tolerance: float
    return_to_dig_start_envelope_depth_tolerance_m: float
    return_to_dig_start_envelope_local_depth_tolerance_m: float
    return_to_dig_start_envelope_plane_depth_tolerance_m: float
    return_to_dig_start_envelope_plane_depth_mode: str
    return_to_dig_start_envelope_qpos_tolerance: float
    return_to_dig_start_envelope_require_contact: bool
    return_to_dig_start_envelope_direct_handoff_enabled: bool
    return_max_steps: int

    def planner_items(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self.__dict__.items())


RETURN_TO_DIG_CONFIG_KEYS: tuple[str, ...] = (
    "return_to_dig_shallow_guard_enabled",
    "return_to_dig_max_bucket_mass_kg",
    "return_to_dig_touch_tolerance_m",
    "return_to_dig_min_depth_m",
    "return_to_dig_max_depth_m",
    "return_to_dig_max_entry_error_m",
    "return_to_dig_start_envelope_gate_enabled",
    "return_to_dig_start_envelope_spatial_tolerance",
    "return_to_dig_start_envelope_depth_tolerance_m",
    "return_to_dig_start_envelope_local_depth_tolerance_m",
    "return_to_dig_start_envelope_plane_depth_tolerance_m",
    "return_to_dig_start_envelope_plane_depth_mode",
    "return_to_dig_start_envelope_qpos_tolerance",
    "return_to_dig_start_envelope_require_contact",
    "return_to_dig_start_envelope_direct_handoff_enabled",
    "return_max_steps",
)


@dataclass(frozen=True)
class ReturnToDigHandoffConfig:
    shallow_guard_enabled: bool = False
    max_bucket_mass_kg: float = 2.0
    touch_tolerance_m: float = 0.05
    min_depth_m: float = 0.015
    max_depth_m: float = 0.12
    max_entry_error_m: float | None = None
    start_envelope_gate_enabled: bool = False
    direct_handoff_enabled: bool = False


RETURN_TO_DIG_HANDOFF_CONFIG_FIELDS: tuple[tuple[str, str], ...] = (
    ("shallow_guard_enabled", "return_to_dig_shallow_guard_enabled"),
    ("max_bucket_mass_kg", "return_to_dig_max_bucket_mass_kg"),
    ("touch_tolerance_m", "return_to_dig_touch_tolerance_m"),
    ("min_depth_m", "return_to_dig_min_depth_m"),
    ("max_depth_m", "return_to_dig_max_depth_m"),
    ("max_entry_error_m", "return_to_dig_max_entry_error_m"),
    ("start_envelope_gate_enabled", "return_to_dig_start_envelope_gate_enabled"),
    (
        "direct_handoff_enabled",
        "return_to_dig_start_envelope_direct_handoff_enabled",
    ),
)


def build_return_to_dig_handoff_config_from_mapping(
    values: Mapping[str, Any],
) -> ReturnToDigHandoffConfig:
    return ReturnToDigHandoffConfig(
        shallow_guard_enabled=values["shallow_guard_enabled"],
        max_bucket_mass_kg=values["max_bucket_mass_kg"],
        touch_tolerance_m=values["touch_tolerance_m"],
        min_depth_m=values["min_depth_m"],
        max_depth_m=values["max_depth_m"],
        max_entry_error_m=values["max_entry_error_m"],
        start_envelope_gate_enabled=values["start_envelope_gate_enabled"],
        direct_handoff_enabled=values["direct_handoff_enabled"],
    )


@dataclass(frozen=True)
class ReturnToDigHandoffContext:
    entry_target: tuple[float, float] | None
    envelope_token: Any
    envelope_config: ReturnStartEnvelopeConfig
    prior_lower: np.ndarray | None = None
    prior_upper: np.ndarray | None = None
    prior_mapping: dict[str, object] | None = None
    use_prior_spatial_bounds: bool = True
    use_prior_qpos_bounds: bool = True


def build_return_to_dig_handoff_context(
    *,
    entry_target: tuple[float, float] | None,
    envelope_token: Any,
    envelope_config: ReturnStartEnvelopeConfig,
    dig_cut_prior: Mapping[str, Any] | None,
    cell_id: int | None,
    use_prior_spatial_bounds: bool = True,
    use_prior_qpos_bounds: bool = True,
) -> ReturnToDigHandoffContext:
    token = np.asarray(envelope_token, dtype=np.float32).reshape(-1)
    prior_context = return_start_envelope_gate_prior_context(
        token=token,
        dig_cut_prior=dig_cut_prior,
        config=envelope_config,
        cell_id=cell_id,
    )
    return ReturnToDigHandoffContext(
        entry_target=entry_target,
        envelope_token=token,
        envelope_config=envelope_config,
        prior_lower=prior_context.lower,
        prior_upper=prior_context.upper,
        prior_mapping=prior_context.prior_mapping,
        use_prior_spatial_bounds=bool(use_prior_spatial_bounds),
        use_prior_qpos_bounds=bool(use_prior_qpos_bounds),
    )


def build_return_to_dig_handoff_context_from_runtime(
    *,
    entry_target: tuple[float, float] | None,
    envelope_token: Any,
    envelope_config: ReturnStartEnvelopeConfig,
    dig_cut_prior: Mapping[str, Any] | None,
    pending_corridor_id: int | None,
    corridor_cell_id_resolver: Callable[[int], int | None] | None = None,
    use_prior_spatial_bounds: bool = True,
    use_prior_qpos_bounds: bool = True,
) -> ReturnToDigHandoffContext:
    token = np.asarray(envelope_token, dtype=np.float32).reshape(-1)
    cell_id = None
    if return_start_envelope_token_has_gate_bounds(token, envelope_config):
        corridor_id = None if pending_corridor_id is None else int(pending_corridor_id)
        corridor_cell_id = (
            None
            if corridor_id is None or corridor_cell_id_resolver is None
            else corridor_cell_id_resolver(corridor_id)
        )
        cell_id = resolve_return_start_envelope_cell_id(
            corridor_id=corridor_id,
            corridor_cell_id=corridor_cell_id,
        )
    return build_return_to_dig_handoff_context(
        entry_target=entry_target,
        envelope_token=token,
        envelope_config=envelope_config,
        dig_cut_prior=dig_cut_prior,
        cell_id=cell_id,
        use_prior_spatial_bounds=use_prior_spatial_bounds,
        use_prior_qpos_bounds=use_prior_qpos_bounds,
    )


@dataclass(frozen=True)
class ReturnNextDigEntryTargetConfig:
    next_cycle_offset: int = 1


@dataclass(frozen=True)
class ReturnNextDigEntryTargetFacts:
    cycle_index: int
    pending_dig_cut_cycle_id: int
    pending_dig_cut_raw_fields: Mapping[str, float | int] | None = None
    active_corridor_entry_target: tuple[float, float] | None = None


def build_return_next_dig_entry_target_facts(
    *,
    cycle_index: int,
    pending_dig_cut_cycle_id: int,
    pending_dig_cut_raw_fields: Mapping[str, float | int] | None = None,
    active_corridor_entry_target: tuple[float, float] | None = None,
) -> ReturnNextDigEntryTargetFacts:
    entry_target = (
        None
        if active_corridor_entry_target is None
        else (
            float(active_corridor_entry_target[0]),
            float(active_corridor_entry_target[1]),
        )
    )
    return ReturnNextDigEntryTargetFacts(
        cycle_index=int(cycle_index),
        pending_dig_cut_cycle_id=int(pending_dig_cut_cycle_id),
        pending_dig_cut_raw_fields=pending_dig_cut_raw_fields,
        active_corridor_entry_target=entry_target,
    )


def build_return_next_dig_entry_target_facts_from_runtime(
    *,
    cycle_index: int,
    pending_dig_cut_cycle_id: int,
    pending_dig_cut_raw_fields: Mapping[str, float | int] | None = None,
    active_corridor: Any | None = None,
) -> ReturnNextDigEntryTargetFacts:
    active_entry_target = (
        None
        if active_corridor is None
        else (
            float(active_corridor.entry_x_m),
            float(active_corridor.entry_z_m),
        )
    )
    return build_return_next_dig_entry_target_facts(
        cycle_index=cycle_index,
        pending_dig_cut_cycle_id=pending_dig_cut_cycle_id,
        pending_dig_cut_raw_fields=pending_dig_cut_raw_fields,
        active_corridor_entry_target=active_entry_target,
    )


@dataclass(frozen=True)
class ReturnNextDigEntryTargetResolution:
    entry_target: tuple[float, float] | None
    source: str
    fallback_reason: str = ""


@dataclass(frozen=True)
class ReturnToDigEntryErrorFacts:
    entry_target: tuple[float, float] | None
    bucket_dig_area_pose: tuple[float, float, float] | None


@dataclass(frozen=True)
class ReturnToDigHandoffDecision:
    entry_error_m: float
    entry_close: bool
    envelope_state: ReturnStartEnvelopeState
    handoff_ready: bool
    direct_handoff_ready: bool
    shallow_guard_ready: bool
    next_dig_event_ready: bool
    checks: Mapping[str, Any] = field(default_factory=dict)
    debug: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReturnToDigHandoffStatusState:
    entry_error_m: float
    entry_close: bool
    next_dig_event_seen: bool
    start_envelope_ready: bool
    start_envelope_error: float
    start_envelope_checks: Mapping[str, Any] = field(default_factory=dict)


RETURN_TO_DIG_HANDOFF_STATUS_FIELDS: tuple[tuple[str, str], ...] = (
    ("entry_error_m", "_return_to_dig_entry_error_m"),
    ("entry_close", "_return_to_dig_entry_close_state"),
    ("next_dig_event_seen", "_return_next_dig_event_seen"),
    ("start_envelope_ready", "_return_to_dig_start_envelope_ready_state"),
    ("start_envelope_error", "_return_to_dig_start_envelope_error"),
    ("start_envelope_checks", "_return_to_dig_start_envelope_checks"),
)


def build_return_to_dig_handoff_status_state_from_mapping(
    values: Mapping[str, Any],
) -> ReturnToDigHandoffStatusState:
    return ReturnToDigHandoffStatusState(
        entry_error_m=float(values["entry_error_m"]),
        entry_close=bool(values["entry_close"]),
        next_dig_event_seen=bool(values["next_dig_event_seen"]),
        start_envelope_ready=bool(values["start_envelope_ready"]),
        start_envelope_error=float(values["start_envelope_error"]),
        start_envelope_checks=dict(values["start_envelope_checks"]),
    )


@dataclass(frozen=True)
class ReturnToDigHandoffStatusSnapshot:
    max_entry_error_m: float | None
    entry_error_m: float
    entry_close: bool
    next_dig_event_seen: bool
    start_envelope_gate_enabled: bool
    start_envelope_direct_handoff_enabled: bool
    start_envelope_ready: bool
    start_envelope_plane_depth_mode: str
    start_envelope_local_depth_tolerance_m: float
    start_envelope_error: float
    start_envelope_checks: Mapping[str, Any] = field(default_factory=dict)


def build_return_to_dig_config_from_mapping(
    values: Mapping[str, Any],
) -> ReturnToDigPlannerConfig:
    return build_return_to_dig_config(
        **{key: values[key] for key in RETURN_TO_DIG_CONFIG_KEYS}
    )


def build_return_to_dig_config(
    *,
    return_to_dig_shallow_guard_enabled: bool,
    return_to_dig_max_bucket_mass_kg: float,
    return_to_dig_touch_tolerance_m: float,
    return_to_dig_min_depth_m: float,
    return_to_dig_max_depth_m: float,
    return_to_dig_max_entry_error_m: object,
    return_to_dig_start_envelope_gate_enabled: bool,
    return_to_dig_start_envelope_spatial_tolerance: float,
    return_to_dig_start_envelope_depth_tolerance_m: float,
    return_to_dig_start_envelope_local_depth_tolerance_m: float,
    return_to_dig_start_envelope_plane_depth_tolerance_m: float,
    return_to_dig_start_envelope_plane_depth_mode: object,
    return_to_dig_start_envelope_qpos_tolerance: float,
    return_to_dig_start_envelope_require_contact: bool,
    return_to_dig_start_envelope_direct_handoff_enabled: bool,
    return_max_steps: int,
) -> ReturnToDigPlannerConfig:
    return ReturnToDigPlannerConfig(
        return_to_dig_shallow_guard_enabled=bool(
            return_to_dig_shallow_guard_enabled
        ),
        return_to_dig_max_bucket_mass_kg=float(return_to_dig_max_bucket_mass_kg),
        return_to_dig_touch_tolerance_m=float(return_to_dig_touch_tolerance_m),
        return_to_dig_min_depth_m=float(return_to_dig_min_depth_m),
        return_to_dig_max_depth_m=float(return_to_dig_max_depth_m),
        return_to_dig_max_entry_error_m=_optional_float(
            return_to_dig_max_entry_error_m
        ),
        return_to_dig_start_envelope_gate_enabled=bool(
            return_to_dig_start_envelope_gate_enabled
        ),
        return_to_dig_start_envelope_spatial_tolerance=float(
            return_to_dig_start_envelope_spatial_tolerance
        ),
        return_to_dig_start_envelope_depth_tolerance_m=float(
            return_to_dig_start_envelope_depth_tolerance_m
        ),
        return_to_dig_start_envelope_local_depth_tolerance_m=float(
            return_to_dig_start_envelope_local_depth_tolerance_m
        ),
        return_to_dig_start_envelope_plane_depth_tolerance_m=float(
            return_to_dig_start_envelope_plane_depth_tolerance_m
        ),
        return_to_dig_start_envelope_plane_depth_mode=normalize_plane_depth_mode(
            return_to_dig_start_envelope_plane_depth_mode
        ),
        return_to_dig_start_envelope_qpos_tolerance=float(
            return_to_dig_start_envelope_qpos_tolerance
        ),
        return_to_dig_start_envelope_require_contact=bool(
            return_to_dig_start_envelope_require_contact
        ),
        return_to_dig_start_envelope_direct_handoff_enabled=bool(
            return_to_dig_start_envelope_direct_handoff_enabled
        ),
        return_max_steps=int(return_max_steps),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"", "none", "null"}:
        return None
    return float(value)


class ReturnNextDigEntryTargetResolver:
    """Resolve the next dig entry target from return handoff facts."""

    def __init__(
        self,
        config: ReturnNextDigEntryTargetConfig | None = None,
    ) -> None:
        self.config = config or ReturnNextDigEntryTargetConfig()

    def resolve(
        self,
        facts: ReturnNextDigEntryTargetFacts,
        config: ReturnNextDigEntryTargetConfig | None = None,
    ) -> ReturnNextDigEntryTargetResolution:
        cfg = config or self.config
        raw_fields = facts.pending_dig_cut_raw_fields
        pending_cycle_matches = (
            raw_fields is not None
            and int(facts.pending_dig_cut_cycle_id)
            == int(facts.cycle_index) + int(cfg.next_cycle_offset)
        )
        if pending_cycle_matches:
            entry_x = float(raw_fields.get("operator_entry_x_m", float("nan")))
            entry_z = float(raw_fields.get("operator_entry_z_m", float("nan")))
            if np.isfinite(entry_x) and np.isfinite(entry_z):
                return ReturnNextDigEntryTargetResolution(
                    entry_target=(entry_x, entry_z),
                    source="pending_return_target",
                )
            fallback_reason = "non_finite_pending_entry"
        elif raw_fields is None:
            fallback_reason = "missing_pending_entry"
        else:
            fallback_reason = "stale_pending_entry"

        active_target = facts.active_corridor_entry_target
        if active_target is not None:
            return ReturnNextDigEntryTargetResolution(
                entry_target=(float(active_target[0]), float(active_target[1])),
                source="active_coverage_corridor",
                fallback_reason=fallback_reason,
            )
        return ReturnNextDigEntryTargetResolution(
            entry_target=None,
            source="none",
            fallback_reason=fallback_reason,
        )


class ReturnToDigHandoffGateService:
    """Evaluate return-to-dig gates without owning scheduler state."""

    def __init__(self, config: ReturnToDigHandoffConfig | None = None) -> None:
        self.config = config or ReturnToDigHandoffConfig()

    @staticmethod
    def initial_runtime_state() -> ReturnToDigHandoffStatusState:
        return ReturnToDigHandoffStatusState(
            entry_error_m=float("nan"),
            entry_close=True,
            next_dig_event_seen=False,
            start_envelope_ready=True,
            start_envelope_error=float("nan"),
            start_envelope_checks={},
        )

    @staticmethod
    def entry_error(facts: ReturnToDigEntryErrorFacts) -> float:
        target = facts.entry_target
        pose = facts.bucket_dig_area_pose
        if target is None or pose is None:
            return float("nan")
        bucket_x, _, bucket_z = pose
        entry_x, entry_z = target
        if not all(
            np.isfinite(value)
            for value in (bucket_x, bucket_z, entry_x, entry_z)
        ):
            return float("nan")
        return float(
            np.hypot(
                float(bucket_x) - float(entry_x),
                float(bucket_z) - float(entry_z),
            )
        )

    @staticmethod
    def status_snapshot(
        *,
        handoff_config: ReturnToDigHandoffConfig,
        envelope_config: ReturnStartEnvelopeConfig,
        state: ReturnToDigHandoffStatusState,
    ) -> ReturnToDigHandoffStatusSnapshot:
        return ReturnToDigHandoffStatusSnapshot(
            max_entry_error_m=handoff_config.max_entry_error_m,
            entry_error_m=float(state.entry_error_m),
            entry_close=bool(state.entry_close),
            next_dig_event_seen=bool(state.next_dig_event_seen),
            start_envelope_gate_enabled=bool(handoff_config.start_envelope_gate_enabled),
            start_envelope_direct_handoff_enabled=bool(
                handoff_config.direct_handoff_enabled
            ),
            start_envelope_ready=bool(state.start_envelope_ready),
            start_envelope_plane_depth_mode=str(envelope_config.plane_depth_mode),
            start_envelope_local_depth_tolerance_m=float(
                envelope_config.local_depth_tolerance_m
            ),
            start_envelope_error=float(state.start_envelope_error),
            start_envelope_checks=dict(state.start_envelope_checks),
        )

    @staticmethod
    def runtime_state_from_decision(
        decision: ReturnToDigHandoffDecision,
        *,
        next_dig_event_seen: bool,
    ) -> ReturnToDigHandoffStatusState:
        return ReturnToDigHandoffStatusState(
            entry_error_m=float(decision.entry_error_m),
            entry_close=bool(decision.entry_close),
            next_dig_event_seen=bool(next_dig_event_seen),
            start_envelope_ready=bool(decision.envelope_state.ready),
            start_envelope_error=float(decision.envelope_state.error),
            start_envelope_checks=dict(decision.envelope_state.checks),
        )

    def evaluate(
        self,
        snapshot: PlannerSnapshot,
        boundary_facts: PrimitiveBoundaryFacts,
        context: ReturnToDigHandoffContext,
        *,
        config: ReturnToDigHandoffConfig | None = None,
        handoff_ready_override: bool | None = None,
    ) -> ReturnToDigHandoffDecision:
        cfg = config or self.config
        entry_error = _entry_error(snapshot, context)
        entry_close = _entry_close(entry_error, cfg.max_entry_error_m)
        envelope_state = self._start_envelope_state(snapshot, context)
        handoff_ready = bool(entry_close and envelope_state.ready)
        ready_for_direct = (
            bool(handoff_ready)
            if handoff_ready_override is None
            else bool(handoff_ready_override)
        )
        direct_ready = bool(
            cfg.direct_handoff_enabled
            and cfg.start_envelope_gate_enabled
            and ready_for_direct
            and snapshot.view.mass_in_bucket_kg <= cfg.max_bucket_mass_kg
        )
        shallow_ready = _shallow_guard_ready(
            snapshot=snapshot,
            boundary_facts=boundary_facts,
            config=cfg,
            entry_close=entry_close,
        )
        next_dig_event = bool(
            boundary_facts.next_dig_entry_ready or boundary_facts.qualified_dig_start
        )
        checks = {
            "entry_close": bool(entry_close),
            "entry_error_m": float(entry_error),
            "start_envelope_ready": bool(envelope_state.ready),
            "direct_handoff_ready": bool(direct_ready),
            "shallow_guard_ready": bool(shallow_ready),
            "next_dig_event_ready": bool(next_dig_event),
        }
        return ReturnToDigHandoffDecision(
            entry_error_m=float(entry_error),
            entry_close=bool(entry_close),
            envelope_state=envelope_state,
            handoff_ready=bool(handoff_ready),
            direct_handoff_ready=bool(direct_ready),
            shallow_guard_ready=bool(shallow_ready),
            next_dig_event_ready=bool(next_dig_event),
            checks=checks,
            debug={"start_envelope_checks": dict(envelope_state.checks)},
        )

    def _start_envelope_state(
        self,
        snapshot: PlannerSnapshot,
        context: ReturnToDigHandoffContext,
    ) -> ReturnStartEnvelopeState:
        token = np.asarray(context.envelope_token, dtype=np.float32).reshape(-1)
        config = context.envelope_config
        kwargs = {
            "config": config,
            "env_state": snapshot.view.env_state,
            "qpos": snapshot.view.qpos,
            "action_dim": snapshot.view.action_dim,
        }
        if not config.gate_enabled or token.shape[0] != RETURN_START_ENVELOPE_TOKEN_DIM:
            return return_to_dig_start_envelope_ready(token, **kwargs)
        if (
            float(token[RETURN_ENVELOPE_QPOS_VALID_IDX]) <= 0.5
            and float(token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX]) <= 0.5
        ):
            return return_to_dig_start_envelope_ready(token, **kwargs)
        return return_to_dig_start_envelope_ready(
            token,
            **kwargs,
            lower=context.prior_lower,
            upper=context.prior_upper,
            prior_mapping=context.prior_mapping,
            use_prior_spatial_bounds=context.use_prior_spatial_bounds,
            use_prior_qpos_bounds=context.use_prior_qpos_bounds,
        )


def _entry_error(
    snapshot: PlannerSnapshot,
    context: ReturnToDigHandoffContext,
) -> float:
    return ReturnToDigHandoffGateService.entry_error(
        ReturnToDigEntryErrorFacts(
            entry_target=context.entry_target,
            bucket_dig_area_pose=snapshot.view.bucket_dig_area_pose,
        )
    )


def _entry_close(entry_error_m: float, max_entry_error_m: float | None) -> bool:
    if max_entry_error_m is None:
        return True
    if not np.isfinite(entry_error_m):
        return True
    return bool(float(entry_error_m) <= float(max_entry_error_m))


def _shallow_guard_ready(
    *,
    snapshot: PlannerSnapshot,
    boundary_facts: PrimitiveBoundaryFacts,
    config: ReturnToDigHandoffConfig,
    entry_close: bool,
) -> bool:
    if not config.shallow_guard_enabled:
        return False
    metrics = getattr(boundary_facts.raw_event, "metrics", {}) or {}
    mass = _metric_or(metrics, "mass_in_bucket_kg", snapshot.view.mass_in_bucket_kg)
    distance = _metric_or(
        metrics,
        "min_distance_to_dig_area_m",
        snapshot.view.min_distance_to_dig_area_m,
    )
    depth = _metric_or(
        metrics,
        "bucket_depth_below_dig_area_plane_m",
        snapshot.view.bucket_depth_below_dig_area_plane_m,
    )
    entry_guard_ready = bool(config.max_entry_error_m is not None and entry_close)
    return bool(
        mass <= config.max_bucket_mass_kg
        and distance <= config.touch_tolerance_m
        and depth >= config.min_depth_m
        and (depth <= config.max_depth_m or entry_guard_ready)
    )


def _metric_or(metrics: Mapping[str, Any], key: str, fallback: float) -> float:
    try:
        return float(metrics.get(key, fallback))
    except (TypeError, ValueError):
        return float(fallback)
