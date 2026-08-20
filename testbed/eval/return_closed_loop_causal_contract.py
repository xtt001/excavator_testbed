"""Fail-closed contract and pure metrics for a bounded Return causal probe.

The contract deliberately stops at the Return-to-Dig handoff boundary.  It
pre-registers the complete 4-state x 2-target x 2-dispatch matrix, but does not
run Unity, load ACT, tune a threshold, or promote a dispatch implementation.
The latest-current-chunk path is a hard diagnostic control: every dispatched
action must be ``predict_action_chunk(obs).first_action`` from a newly inferred
chunk at that frame, with no temporal cache contribution.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any

import numpy as np

from testbed.data.recorded_return_closed_loop_fixture import (
    RETURN_TOKEN_DIM,
    RecordedReturnClosedLoopFixtureSet,
    RecordedReturnInitialObservation,
)

SCHEMA = "return_closed_loop_causal_contract_v1"
EVIDENCE_KIND = "bounded_unity_return_closed_loop_causal_diagnostic"

LEGACY_TEMPORAL_DISPATCH = "legacy_100_oldest_first_decay_0p01"
LATEST_CURRENT_CHUNK_DIAGNOSTIC = "latest_current_chunk_diagnostic"

# Existing runtime contract: PrimitivePlannerConfig.return_max_steps.
RETURN_CLOSED_LOOP_MAX_STEPS = 420
# Existing normalized action protocol bound; touching the bound is recorded,
# while exceeding it invalidates action quality.
RETURN_ACTION_ABS_LIMIT = 1.0
# Reuses SafetyInterlockConfig.stuck_bucket_tip_max_displacement_m.  It is not
# selected from the two offline failures.
RETURN_TRAJECTORY_SEPARATION_MIN_M = 0.02
# Reuses the existing continuous-goal handoff hold of three ticks so a one-frame
# pose spike cannot count as a causal trajectory split.
RETURN_TRAJECTORY_SEPARATION_HOLD_FRAMES = 3
# Serialization/equality tolerance already used by recorded replay alignment.
# This is not a physical success tolerance and may not be relaxed from results.
RETURN_FIXTURE_FLOAT_ATOL = 1.0e-6

FORBIDDEN_PRIMITIVES = ("dig", "carry", "dump")


@dataclass(frozen=True)
class ReturnClosedLoopDispatchStrategy:
    """One pre-registered action-dispatch implementation."""

    strategy_id: str
    dispatch_api: str
    temporal_aggregation_enabled: bool
    diagnostic_only: bool
    promotion_eligible: bool
    runtime_default: bool
    interpretation: str

    def as_dict(self) -> dict[str, Any]:
        return _dataclass_json_dict(self)


@dataclass(frozen=True)
class ReturnTargetEnvelope:
    """Direct, tolerance-free interpretation of one frozen 18-D token."""

    long_norm: float
    short_norm: float
    depth_center_m: float
    tip_radius: float
    depth_min_m: float
    depth_max_m: float
    contact_required_by_token: bool
    qpos_center: tuple[float, float, float, float]
    qpos_half_width: tuple[float, float, float, float]
    qvel_abs_max: float
    qpos_valid: bool
    spatial_depth_valid: bool

    def as_dict(self) -> dict[str, Any]:
        return _dataclass_json_dict(self)


@dataclass(frozen=True)
class ReturnClosedLoopArm:
    """One immutable cell in the 16-arm causal matrix."""

    arm_id: str
    fixture_id: str
    fixture_evidence_role: str
    source_segment_id: str
    observation_step_id: int
    target_role: str
    target_segment_id: str
    target_token_sha256: str
    target_envelope: ReturnTargetEnvelope
    dispatch_strategy_id: str
    allowed_primitive: str = "return"
    forbidden_primitives: tuple[str, ...] = FORBIDDEN_PRIMITIVES
    max_steps: int = RETURN_CLOSED_LOOP_MAX_STEPS
    no_retry: bool = True

    def as_dict(self) -> dict[str, Any]:
        return _dataclass_json_dict(self)


@dataclass(frozen=True)
class ReturnClosedLoopCausalContract:
    """JSON-ready pre-registration for the bounded experiment."""

    schema: str
    evidence_kind: str
    source_fixture_schema: str
    source_lineage: Mapping[str, Any]
    dispatch_strategies: Mapping[str, ReturnClosedLoopDispatchStrategy]
    arms: tuple[ReturnClosedLoopArm, ...]
    runtime_default_changed: bool = False
    diagnostic_only: bool = True
    promotion_eligible: bool = False
    closed_loop_claim_scope: str = "bounded_return_only"
    dig_execution_permitted: bool = False
    official_handoff_evaluator_required: bool = True

    def __post_init__(self) -> None:
        if self.schema != SCHEMA or self.evidence_kind != EVIDENCE_KIND:
            raise ValueError("Return closed-loop contract identity mismatch")
        strategies = dict(self.dispatch_strategies)
        expected_ids = {LEGACY_TEMPORAL_DISPATCH, LATEST_CURRENT_CHUNK_DIAGNOSTIC}
        if set(strategies) != expected_ids:
            raise ValueError("contract must contain exactly the two frozen dispatches")
        if len(self.arms) != 16 or len({arm.arm_id for arm in self.arms}) != 16:
            raise ValueError("contract must contain exactly 16 unique arms")
        if self.runtime_default_changed:
            raise ValueError("bounded diagnostic must not change the runtime default")
        if not self.diagnostic_only or self.promotion_eligible:
            raise ValueError("bounded experiment evidence boundary is invalid")
        if self.dig_execution_permitted:
            raise ValueError("bounded Return experiment must stop before Dig")
        if not self.official_handoff_evaluator_required:
            raise ValueError("official Return handoff evaluator must not be bypassed")
        object.__setattr__(self, "dispatch_strategies", MappingProxyType(strategies))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evidence_kind": self.evidence_kind,
            "diagnostic_only": self.diagnostic_only,
            "promotion_eligible": self.promotion_eligible,
            "closed_loop_claim_scope": self.closed_loop_claim_scope,
            "runtime_default_changed": self.runtime_default_changed,
            "dig_execution_permitted": self.dig_execution_permitted,
            "official_handoff_evaluator_required": (
                self.official_handoff_evaluator_required
            ),
            "official_handoff_result_source": (
                "ReturnStartEnvelopeGateService_plus_"
                "ReturnHandoffReadinessService_injected_by_runner"
            ),
            "source_fixture_schema": self.source_fixture_schema,
            "source_lineage": _json_ready(self.source_lineage),
            "dispatch_strategies": {
                key: value.as_dict() for key, value in self.dispatch_strategies.items()
            },
            "arm_count": len(self.arms),
            "arms": [arm.as_dict() for arm in self.arms],
            "fixed_numeric_contract": {
                "max_steps": RETURN_CLOSED_LOOP_MAX_STEPS,
                "action_abs_limit": RETURN_ACTION_ABS_LIMIT,
                "trajectory_separation_min_m": (RETURN_TRAJECTORY_SEPARATION_MIN_M),
                "trajectory_separation_hold_frames": (
                    RETURN_TRAJECTORY_SEPARATION_HOLD_FRAMES
                ),
                "fixture_float_atol": RETURN_FIXTURE_FLOAT_ATOL,
                "threshold_selection_used_probe_results": False,
            },
        }


def build_return_closed_loop_causal_contract(
    fixture_set: RecordedReturnClosedLoopFixtureSet,
) -> ReturnClosedLoopCausalContract:
    """Build the exact 4 x 2 x 2 matrix without inspecting probe outcomes."""

    strategies = {
        LEGACY_TEMPORAL_DISPATCH: ReturnClosedLoopDispatchStrategy(
            strategy_id=LEGACY_TEMPORAL_DISPATCH,
            dispatch_api="predict.legacy_temporal_aggregation",
            temporal_aggregation_enabled=True,
            diagnostic_only=False,
            promotion_eligible=False,
            runtime_default=True,
            interpretation="current production-default comparison baseline",
        ),
        LATEST_CURRENT_CHUNK_DIAGNOSTIC: ReturnClosedLoopDispatchStrategy(
            strategy_id=LATEST_CURRENT_CHUNK_DIAGNOSTIC,
            dispatch_api="predict_action_chunk.first_action_each_frame",
            temporal_aggregation_enabled=False,
            diagnostic_only=True,
            promotion_eligible=False,
            runtime_default=False,
            interpretation=(
                "causal diagnostic only; bypasses temporal contributors and "
                "must never be inferred by disabling aggregation on predict()"
            ),
        ),
    }
    arms: list[ReturnClosedLoopArm] = []
    for fixture in fixture_set.fixtures:
        for target_role in ("original", "alternate"):
            target = fixture.target(target_role)
            envelope = return_target_envelope_from_token(target.token)
            for strategy_id in (
                LEGACY_TEMPORAL_DISPATCH,
                LATEST_CURRENT_CHUNK_DIAGNOSTIC,
            ):
                arms.append(
                    ReturnClosedLoopArm(
                        arm_id=f"{fixture.fixture_id}__{target_role}__{strategy_id}",
                        fixture_id=fixture.fixture_id,
                        fixture_evidence_role=fixture.evidence_role,
                        source_segment_id=fixture.source_segment_id,
                        observation_step_id=(
                            fixture.initial_observation.observation_step_id
                        ),
                        target_role=target_role,
                        target_segment_id=target.segment_id,
                        target_token_sha256=target.token_sha256,
                        target_envelope=envelope,
                        dispatch_strategy_id=strategy_id,
                    )
                )
    return ReturnClosedLoopCausalContract(
        schema=SCHEMA,
        evidence_kind=EVIDENCE_KIND,
        source_fixture_schema=fixture_set.schema,
        source_lineage=fixture_set.source_lineage,
        dispatch_strategies=strategies,
        arms=tuple(arms),
    )


@dataclass(frozen=True)
class ReturnFixtureApplicationCapabilities:
    """Receiver capabilities that must be true before an arm may move."""

    full_reset_applied: bool
    qpos_actual_applied: bool
    qvel_actual_applied: bool
    observable_terrain_available: bool
    camera_observation_available: bool
    scene_actual_applied: bool = False
    physics_seed_actual_applied: bool = False
    terrain_state_actual_applied: bool = False
    terrain_restore_mode: str = "unsupported_observable_only"

    def failures(self) -> tuple[str, ...]:
        restore_mode_valid = self.terrain_restore_mode in {
            "full_terrain_snapshot",
            "deterministic_soil_seed",
        }
        checks = (
            (self.full_reset_applied, "full_reset_not_actual_applied"),
            (self.scene_actual_applied, "scene_not_actual_applied"),
            (self.physics_seed_actual_applied, "physics_seed_not_actual_applied"),
            (self.qpos_actual_applied, "qpos_not_actual_applied"),
            (self.qvel_actual_applied, "qvel_not_actual_applied"),
            (
                self.terrain_state_actual_applied,
                "terrain_state_not_actual_applied",
            ),
            (
                restore_mode_valid,
                "terrain_restore_unsupported_observable_only",
            ),
            (
                self.observable_terrain_available,
                "observable_terrain_unavailable",
            ),
            (
                self.camera_observation_available,
                "camera_observation_unavailable",
            ),
        )
        return tuple(reason for passed, reason in checks if not passed)

    def as_dict(self) -> dict[str, Any]:
        return {
            "full_reset_applied": self.full_reset_applied,
            "scene_actual_applied": self.scene_actual_applied,
            "physics_seed_actual_applied": self.physics_seed_actual_applied,
            "qpos_actual_applied": self.qpos_actual_applied,
            "qvel_actual_applied": self.qvel_actual_applied,
            "terrain_state_actual_applied": self.terrain_state_actual_applied,
            "terrain_restore_mode": self.terrain_restore_mode,
            "observable_terrain_available": self.observable_terrain_available,
            "camera_observation_available": self.camera_observation_available,
        }


@dataclass(frozen=True)
class ReturnFixtureAppliedState:
    """State read back from Unity after applying a frozen fixture."""

    qpos: np.ndarray
    qvel: np.ndarray
    env_state: np.ndarray
    image_rgb_sha256: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "qpos", _frozen_vector(self.qpos, 4, "applied qpos"))
        object.__setattr__(self, "qvel", _frozen_vector(self.qvel, 4, "applied qvel"))
        object.__setattr__(
            self,
            "env_state",
            _frozen_vector(self.env_state, 107, "applied env_state"),
        )
        image_hashes = {
            str(key): str(value) for key, value in self.image_rgb_sha256.items()
        }
        for value in image_hashes.values():
            _require_sha256(value, "applied image RGB SHA")
        object.__setattr__(self, "image_rgb_sha256", MappingProxyType(image_hashes))

    def as_dict(self) -> dict[str, Any]:
        return {
            "qpos": self.qpos.tolist(),
            "qvel": self.qvel.tolist(),
            "env_state": self.env_state.tolist(),
            "image_rgb_sha256": dict(self.image_rgb_sha256),
        }


@dataclass(frozen=True)
class ReturnFixtureMatchAssessment:
    matched: bool
    failures: tuple[str, ...]
    max_abs_qpos_error: float | None
    max_abs_qvel_error: float | None
    max_abs_env_state_error: float | None
    image_lineage_matched: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "failures": list(self.failures),
            "max_abs_qpos_error": self.max_abs_qpos_error,
            "max_abs_qvel_error": self.max_abs_qvel_error,
            "max_abs_env_state_error": self.max_abs_env_state_error,
            "image_lineage_matched": self.image_lineage_matched,
            "float_atol": RETURN_FIXTURE_FLOAT_ATOL,
        }


def assess_return_fixture_match(
    *,
    reference: RecordedReturnInitialObservation,
    applied: ReturnFixtureAppliedState,
    capabilities: ReturnFixtureApplicationCapabilities,
) -> ReturnFixtureMatchAssessment:
    """Fail closed unless the requested fixture was actually applied and read back."""

    failures = list(capabilities.failures())
    qpos_error = _max_abs_error(reference.qpos, applied.qpos)
    qvel_error = _max_abs_error(reference.qvel, applied.qvel)
    env_error = _max_abs_error(reference.env_state, applied.env_state)
    if qpos_error > RETURN_FIXTURE_FLOAT_ATOL:
        failures.append("qpos_readback_mismatch")
    if qvel_error > RETURN_FIXTURE_FLOAT_ATOL:
        failures.append("qvel_readback_mismatch")
    if env_error > RETURN_FIXTURE_FLOAT_ATOL:
        failures.append("env_state_readback_mismatch")
    expected_images = {
        item.camera_name: item.rgb_sha256 for item in reference.image_lineage
    }
    image_match = dict(applied.image_rgb_sha256) == expected_images
    if not image_match:
        failures.append("camera_rgb_lineage_mismatch")
    return ReturnFixtureMatchAssessment(
        matched=not failures,
        failures=tuple(failures),
        max_abs_qpos_error=qpos_error,
        max_abs_qvel_error=qvel_error,
        max_abs_env_state_error=env_error,
        image_lineage_matched=image_match,
    )


def return_target_envelope_from_token(token: Any) -> ReturnTargetEnvelope:
    """Parse the canonical token without adding an outcome-selected tolerance."""

    values = _frozen_vector(token, RETURN_TOKEN_DIM, "Return target token")
    if values[16] <= 0.5 or values[17] <= 0.5:
        raise ValueError(
            "Return target token must have valid qpos and spatial contracts"
        )
    if values[3] < 0.0:
        raise ValueError("Return target tip radius must be non-negative")
    if values[4] > values[5]:
        raise ValueError("Return target depth bounds are reversed")
    if np.any(values[11:15] < 0.0):
        raise ValueError("Return target qpos half-widths must be non-negative")
    if values[15] < 0.0:
        raise ValueError("Return target qvel limit must be non-negative")
    return ReturnTargetEnvelope(
        long_norm=float(values[0]),
        short_norm=float(values[1]),
        depth_center_m=float(values[2]),
        tip_radius=float(values[3]),
        depth_min_m=float(values[4]),
        depth_max_m=float(values[5]),
        contact_required_by_token=bool(values[6] > 0.5),
        qpos_center=tuple(float(value) for value in values[7:11]),
        qpos_half_width=tuple(float(value) for value in values[11:15]),
        qvel_abs_max=float(values[15]),
        qpos_valid=True,
        spatial_depth_valid=True,
    )


@dataclass(frozen=True)
class ReturnTargetEnvelopeAssessment:
    entered: bool
    failed_checks: tuple[str, ...]
    spatial_distance: float
    depth_error_from_center_m: float
    qpos_abs_error: tuple[float, float, float, float]
    qvel_abs_max: float
    assessment_kind: str = "direct_token_geometry_only"
    official_handoff_ready: None = None
    official_gate_required: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "entered": self.entered,
            "direct_token_geometry_entered": self.entered,
            "failed_checks": list(self.failed_checks),
            "spatial_distance": self.spatial_distance,
            "depth_error_from_center_m": self.depth_error_from_center_m,
            "qpos_abs_error": list(self.qpos_abs_error),
            "qvel_abs_max": self.qvel_abs_max,
            "assessment_kind": self.assessment_kind,
            "official_handoff_ready": self.official_handoff_ready,
            "official_gate_required": self.official_gate_required,
            "evidence_boundary": (
                "does_not_apply_runtime_spatial_depth_qpos_tolerances_or_"
                "strict_config_require_contact"
            ),
        }


def assess_return_target_envelope(
    *,
    envelope: ReturnTargetEnvelope,
    long_norm: float,
    short_norm: float,
    local_depth_m: float,
    qpos: Any,
    qvel: Any,
    dig_contact: bool,
) -> ReturnTargetEnvelopeAssessment:
    """Evaluate the pre-registered target envelope as a pure function."""

    scalars = np.asarray([long_norm, short_norm, local_depth_m], dtype=np.float64)
    if not np.isfinite(scalars).all():
        raise ValueError("Return target spatial/depth observation is non-finite")
    qpos_values = _frozen_vector(qpos, 4, "Return target qpos")
    qvel_values = _frozen_vector(qvel, 4, "Return target qvel")
    spatial_distance = float(
        np.hypot(long_norm - envelope.long_norm, short_norm - envelope.short_norm)
    )
    qpos_error = np.abs(
        qpos_values - np.asarray(envelope.qpos_center, dtype=np.float32)
    )
    qvel_abs_max = float(np.max(np.abs(qvel_values)))
    failures: list[str] = []
    if spatial_distance > envelope.tip_radius:
        failures.append("tip_radius")
    if not envelope.depth_min_m <= local_depth_m <= envelope.depth_max_m:
        failures.append("local_depth")
    if np.any(qpos_error > np.asarray(envelope.qpos_half_width, dtype=np.float32)):
        failures.append("qpos")
    if qvel_abs_max > envelope.qvel_abs_max:
        failures.append("qvel_abs_max")
    if envelope.contact_required_by_token and not bool(dig_contact):
        failures.append("dig_contact")
    return ReturnTargetEnvelopeAssessment(
        entered=not failures,
        failed_checks=tuple(failures),
        spatial_distance=spatial_distance,
        depth_error_from_center_m=abs(local_depth_m - envelope.depth_center_m),
        qpos_abs_error=tuple(float(value) for value in qpos_error),
        qvel_abs_max=qvel_abs_max,
    )


@dataclass(frozen=True)
class ReturnTrajectorySeparation:
    separated: bool
    first_separation_frame: int | None
    max_bucket_tip_distance_m: float
    common_frame_count: int
    required_distance_m: float = RETURN_TRAJECTORY_SEPARATION_MIN_M
    required_hold_frames: int = RETURN_TRAJECTORY_SEPARATION_HOLD_FRAMES

    def as_dict(self) -> dict[str, Any]:
        return _dataclass_json_dict(self)


def measure_return_trajectory_separation(
    original_bucket_tip_xyz_m: Any,
    alternate_bucket_tip_xyz_m: Any,
) -> ReturnTrajectorySeparation:
    """Find the first sustained physical split between two target trajectories."""

    original = _finite_matrix(original_bucket_tip_xyz_m, 3, "original trajectory")
    alternate = _finite_matrix(alternate_bucket_tip_xyz_m, 3, "alternate trajectory")
    common = min(len(original), len(alternate))
    if common < 1:
        raise ValueError("Return trajectories have no common frames")
    distances = np.linalg.norm(original[:common] - alternate[:common], axis=1)
    first: int | None = None
    required = RETURN_TRAJECTORY_SEPARATION_HOLD_FRAMES
    over = distances >= RETURN_TRAJECTORY_SEPARATION_MIN_M
    for index in range(0, common - required + 1):
        if bool(np.all(over[index : index + required])):
            first = index
            break
    return ReturnTrajectorySeparation(
        separated=first is not None,
        first_separation_frame=first,
        max_bucket_tip_distance_m=float(np.max(distances)),
        common_frame_count=common,
    )


@dataclass(frozen=True)
class ReturnActionContinuityAssessment:
    action_dim: int
    frame_count: int
    boundary_touch_count: int
    boundary_exceed_count: int
    discontinuity_count: int
    max_abs_action_by_axis: tuple[float, ...]
    mean_abs_delta_by_axis: tuple[float, ...]
    p95_abs_delta_by_axis: tuple[float, ...]
    max_abs_delta_by_axis: tuple[float, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = _dataclass_json_dict(self)
        payload["action_abs_limit"] = RETURN_ACTION_ABS_LIMIT
        return payload


def assess_return_action_continuity(
    actions: Any,
    *,
    discontinuity_threshold: Any,
) -> ReturnActionContinuityAssessment:
    """Record normalized action bounds and pre-registered per-axis jumps."""

    values = _finite_matrix(actions, None, "Return actions")
    if values.shape[1] < 1:
        raise ValueError("Return actions must have at least one axis")
    threshold = _frozen_vector(
        discontinuity_threshold,
        values.shape[1],
        "action discontinuity threshold",
    )
    if np.any(threshold <= 0.0):
        raise ValueError("action discontinuity thresholds must be positive")
    absolute = np.abs(values)
    deltas = np.abs(np.diff(values, axis=0))
    if deltas.shape[0]:
        mean_delta = np.mean(deltas, axis=0)
        p95_delta = np.percentile(deltas, 95, axis=0)
        max_delta = np.max(deltas, axis=0)
    else:
        mean_delta = np.zeros(values.shape[1], dtype=np.float32)
        p95_delta = np.zeros(values.shape[1], dtype=np.float32)
        max_delta = np.zeros(values.shape[1], dtype=np.float32)
    discontinuities = (
        int(np.count_nonzero(np.any(deltas > threshold, axis=1)))
        if deltas.shape[0]
        else 0
    )
    return ReturnActionContinuityAssessment(
        action_dim=int(values.shape[1]),
        frame_count=int(values.shape[0]),
        boundary_touch_count=int(np.count_nonzero(absolute >= RETURN_ACTION_ABS_LIMIT)),
        boundary_exceed_count=int(np.count_nonzero(absolute > RETURN_ACTION_ABS_LIMIT)),
        discontinuity_count=discontinuities,
        max_abs_action_by_axis=tuple(
            float(value) for value in np.max(absolute, axis=0)
        ),
        mean_abs_delta_by_axis=tuple(float(value) for value in mean_delta),
        p95_abs_delta_by_axis=tuple(float(value) for value in p95_delta),
        max_abs_delta_by_axis=tuple(float(value) for value in max_delta),
    )


@dataclass(frozen=True)
class ReturnSafetyFacts:
    """Observed terminal and integrity facts for one bounded arm."""

    forbidden_primitive_dispatched: bool = False
    retry_attempted: bool = False
    input_lineage_valid: bool = True
    fixture_match_valid: bool = True
    finite_observations: bool = True
    finite_actions: bool = True
    target_token_held_constant: bool = True
    dispatch_strategy_held_constant: bool = True
    hard_safety_stop: bool = False
    collision_detected: bool = False
    handoff_would_fire: bool = False
    timeout_reached: bool = False
    neutral_requested: bool = False
    neutral_acknowledged: bool = False
    run_completed: bool = True
    step_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ReturnSafetyClassification:
    classification: str
    safe: bool
    valid_artifact: bool
    reasons: tuple[str, ...]
    dig_executed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return _dataclass_json_dict(self)


def classify_return_closed_loop_safety(
    facts: ReturnSafetyFacts,
) -> ReturnSafetyClassification:
    """Classify one completed arm with integrity failures taking priority."""

    invalid_reasons: list[str] = []
    integrity_checks = (
        (facts.forbidden_primitive_dispatched, "forbidden_primitive_dispatched"),
        (facts.retry_attempted, "retry_attempted"),
        (not facts.input_lineage_valid, "input_lineage_invalid"),
        (not facts.fixture_match_valid, "fixture_match_invalid"),
        (not facts.finite_observations, "nonfinite_observation"),
        (not facts.finite_actions, "nonfinite_action"),
        (not facts.target_token_held_constant, "target_token_drift"),
        (
            not facts.dispatch_strategy_held_constant,
            "dispatch_strategy_drift",
        ),
        (facts.step_count < 0, "negative_step_count"),
        (facts.step_count > RETURN_CLOSED_LOOP_MAX_STEPS, "step_limit_exceeded"),
        (not facts.run_completed, "run_incomplete"),
    )
    invalid_reasons.extend(reason for failed, reason in integrity_checks if failed)
    terminal_requires_neutral = bool(
        facts.run_completed
        or facts.neutral_requested
        or facts.hard_safety_stop
        or facts.collision_detected
        or facts.handoff_would_fire
        or facts.timeout_reached
    )
    if terminal_requires_neutral and not (
        facts.neutral_requested and facts.neutral_acknowledged
    ):
        invalid_reasons.append("neutral_ack_missing")
    if invalid_reasons:
        return ReturnSafetyClassification(
            classification="artifact_invalid",
            safe=False,
            valid_artifact=False,
            reasons=tuple(invalid_reasons),
        )
    if facts.hard_safety_stop or facts.collision_detected:
        reasons = tuple(
            reason
            for present, reason in (
                (facts.hard_safety_stop, "hard_safety_stop"),
                (facts.collision_detected, "collision_detected"),
            )
            if present
        )
        return ReturnSafetyClassification(
            classification="hard_safety_stop",
            safe=False,
            valid_artifact=True,
            reasons=reasons,
        )
    if facts.handoff_would_fire:
        return ReturnSafetyClassification(
            classification="bounded_return_handoff_observed",
            safe=True,
            valid_artifact=True,
            reasons=("return_to_dig_handoff_would_fire_but_dig_not_dispatched",),
        )
    if facts.timeout_reached:
        return ReturnSafetyClassification(
            classification="bounded_return_timeout",
            safe=True,
            valid_artifact=True,
            reasons=("return_step_limit_reached_then_neutral",),
        )
    return ReturnSafetyClassification(
        classification="bounded_return_stopped_without_handoff",
        safe=True,
        valid_artifact=True,
        reasons=("bounded_return_stopped_then_neutral",),
    )


def _finite_matrix(value: Any, width: int | None, label: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float32)
    if array.ndim != 2 or array.shape[0] < 1:
        raise ValueError(f"{label} must be a non-empty matrix")
    if width is not None and array.shape[1] != width:
        raise ValueError(f"{label} must have width {width}")
    if not np.isfinite(array).all():
        raise ValueError(f"{label} contains non-finite values")
    return array


def _frozen_vector(value: Any, width: int, label: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float32).reshape(-1)
    if array.shape != (width,):
        raise ValueError(f"{label} must have shape ({width},)")
    if not np.isfinite(array).all():
        raise ValueError(f"{label} contains non-finite values")
    array = array.copy()
    array.setflags(write=False)
    return array


def _max_abs_error(expected: np.ndarray, actual: np.ndarray) -> float:
    if expected.shape != actual.shape:
        return float("inf")
    return float(
        np.max(np.abs(expected.astype(np.float64) - actual.astype(np.float64)))
    )


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be lowercase SHA-256")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _dataclass_json_dict(value: Any) -> dict[str, Any]:
    return dict(_json_ready(asdict(value)))
