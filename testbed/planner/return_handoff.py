"""Return-to-dig handoff gate service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from testbed.contracts.primitive_tokens import (
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX,
    RETURN_START_ENVELOPE_TOKEN_DIM,
)
from testbed.planner.primitive_decisions import PrimitiveBoundaryFacts
from testbed.planner.return_start_envelope import (
    ReturnStartEnvelopeConfig,
    ReturnStartEnvelopeState,
    return_to_dig_start_envelope_ready,
)
from testbed.planner.snapshots import PlannerSnapshot


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


class ReturnToDigHandoffGateService:
    """Evaluate return-to-dig gates without owning scheduler state."""

    def __init__(self, config: ReturnToDigHandoffConfig | None = None) -> None:
        self.config = config or ReturnToDigHandoffConfig()

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
    target = context.entry_target
    pose = snapshot.view.bucket_dig_area_pose
    if target is None or pose is None:
        return float("nan")
    err_x = float(pose[0]) - float(target[0])
    err_z = float(pose[2]) - float(target[1])
    error = float(np.hypot(err_x, err_z))
    if not np.isfinite(error):
        return float("nan")
    return error


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
