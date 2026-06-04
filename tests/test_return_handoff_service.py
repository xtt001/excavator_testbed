from __future__ import annotations

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import (
    RETURN_ENVELOPE_CONTACT_FLAG_IDX,
    RETURN_ENVELOPE_DEPTH_CENTER_IDX,
    RETURN_ENVELOPE_DEPTH_MAX_IDX,
    RETURN_ENVELOPE_DEPTH_MIN_IDX,
    RETURN_ENVELOPE_LONG_NORM_IDX,
    RETURN_ENVELOPE_QPOS_CENTER_SLICE,
    RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE,
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_ENVELOPE_QVEL_ABS_MAX_IDX,
    RETURN_ENVELOPE_SHORT_NORM_IDX,
    RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX,
    RETURN_ENVELOPE_TIP_RADIUS_IDX,
    RETURN_START_ENVELOPE_TOKEN_DIM,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
)
from testbed.planner.primitive_decisions import primitive_boundary_facts_from_event
from testbed.planner.return_handoff import (
    ReturnToDigHandoffConfig,
    ReturnToDigHandoffContext,
    ReturnToDigHandoffGateService,
)
from testbed.planner.return_start_envelope import ReturnStartEnvelopeConfig
from testbed.planner.snapshots import build_planner_snapshot


def test_entry_error_close_and_non_finite_fallback() -> None:
    service = ReturnToDigHandoffGateService()
    config = ReturnToDigHandoffConfig(max_entry_error_m=0.50)

    close = service.evaluate(
        _snapshot(bucket_pose=(0.3, 0.0, 0.39)),
        primitive_boundary_facts_from_event(None),
        _context(entry_target=(0.0, 0.0)),
        config=config,
    )
    assert close.entry_error_m == pytest.approx(0.49203658)
    assert close.entry_close is True

    far = service.evaluate(
        _snapshot(bucket_pose=(1.0, 0.0, 0.0)),
        primitive_boundary_facts_from_event(None),
        _context(entry_target=(0.0, 0.0)),
        config=config,
    )
    assert far.entry_close is False

    permissive = service.evaluate(
        _snapshot(bucket_pose=None),
        primitive_boundary_facts_from_event(None),
        _context(entry_target=(0.0, 0.0)),
        config=config,
    )
    assert not np.isfinite(permissive.entry_error_m)
    assert permissive.entry_close is True


def test_start_envelope_gate_ready_fail_and_missing_token_fallback() -> None:
    service = ReturnToDigHandoffGateService()
    config = ReturnToDigHandoffConfig(start_envelope_gate_enabled=True)
    envelope_config = ReturnStartEnvelopeConfig(
        gate_enabled=True,
        require_contact=True,
        plane_depth_mode="range",
    )

    ready = service.evaluate(
        _snapshot(qpos=[0.50, 0.60, 0.20, 0.10]),
        primitive_boundary_facts_from_event(None),
        _context(envelope_token=_ready_token(), envelope_config=envelope_config),
        config=config,
    )
    assert ready.envelope_state.ready is True
    assert ready.envelope_state.error == pytest.approx(0.0)

    failed = service.evaluate(
        _snapshot(qpos=[0.90, 0.60, 0.20, 0.10]),
        primitive_boundary_facts_from_event(None),
        _context(envelope_token=_ready_token(), envelope_config=envelope_config),
        config=config,
    )
    assert failed.envelope_state.ready is False
    assert failed.envelope_state.checks["qpos_0"]["ok"] is False

    missing = service.evaluate(
        _snapshot(qpos=[0.90, 0.60, 0.20, 0.10]),
        primitive_boundary_facts_from_event(None),
        _context(
            envelope_token=np.asarray([0.0], dtype=np.float32),
            envelope_config=envelope_config,
        ),
        config=config,
    )
    assert missing.envelope_state.ready is True
    assert missing.envelope_state.checks["missing_token"] is True


def test_direct_handoff_requires_flag_gate_handoff_ready_and_low_mass() -> None:
    service = ReturnToDigHandoffGateService()
    context = _context()
    facts = primitive_boundary_facts_from_event(None)

    assert (
        service.evaluate(
            _snapshot(mass=0.0),
            facts,
            context,
            config=ReturnToDigHandoffConfig(
                direct_handoff_enabled=False,
                start_envelope_gate_enabled=True,
                max_bucket_mass_kg=2.0,
            ),
            handoff_ready_override=True,
        ).direct_handoff_ready
        is False
    )
    assert (
        service.evaluate(
            _snapshot(mass=0.0),
            facts,
            context,
            config=ReturnToDigHandoffConfig(
                direct_handoff_enabled=True,
                start_envelope_gate_enabled=False,
                max_bucket_mass_kg=2.0,
            ),
            handoff_ready_override=True,
        ).direct_handoff_ready
        is False
    )
    assert (
        service.evaluate(
            _snapshot(mass=0.0),
            facts,
            context,
            config=ReturnToDigHandoffConfig(
                direct_handoff_enabled=True,
                start_envelope_gate_enabled=True,
                max_bucket_mass_kg=2.0,
            ),
            handoff_ready_override=True,
        ).direct_handoff_ready
        is True
    )
    assert (
        service.evaluate(
            _snapshot(mass=3.0),
            facts,
            context,
            config=ReturnToDigHandoffConfig(
                direct_handoff_enabled=True,
                start_envelope_gate_enabled=True,
                max_bucket_mass_kg=2.0,
            ),
            handoff_ready_override=True,
        ).direct_handoff_ready
        is False
    )
    assert (
        service.evaluate(
            _snapshot(mass=0.0),
            facts,
            context,
            config=ReturnToDigHandoffConfig(
                direct_handoff_enabled=True,
                start_envelope_gate_enabled=True,
                max_bucket_mass_kg=2.0,
            ),
            handoff_ready_override=False,
        ).direct_handoff_ready
        is False
    )


def test_shallow_guard_matches_mass_distance_depth_and_entry_close_logic() -> None:
    service = ReturnToDigHandoffGateService()
    config = ReturnToDigHandoffConfig(
        shallow_guard_enabled=True,
        max_bucket_mass_kg=2.0,
        touch_tolerance_m=0.05,
        min_depth_m=0.02,
        max_depth_m=0.12,
        max_entry_error_m=0.05,
    )
    context = _context(entry_target=(0.0, 0.0))

    ready = service.evaluate(
        _snapshot(mass=1.0, distance=0.04, plane_depth=0.03),
        primitive_boundary_facts_from_event(None),
        context,
        config=config,
    )
    assert ready.shallow_guard_ready is True

    high_mass = service.evaluate(
        _snapshot(mass=3.0, distance=0.04, plane_depth=0.03),
        primitive_boundary_facts_from_event(None),
        context,
        config=config,
    )
    assert high_mass.shallow_guard_ready is False

    deep_but_entry_close = service.evaluate(
        _snapshot(mass=1.0, distance=0.04, plane_depth=0.20),
        primitive_boundary_facts_from_event(None),
        context,
        config=config,
    )
    assert deep_but_entry_close.shallow_guard_ready is True

    no_entry_guard = service.evaluate(
        _snapshot(mass=1.0, distance=0.04, plane_depth=0.20),
        primitive_boundary_facts_from_event(None),
        _context(entry_target=(1.0, 1.0)),
        config=config,
    )
    assert no_entry_guard.shallow_guard_ready is False

    metrics_override = type(
        "_Event",
        (),
        {
            "metrics": {
                "mass_in_bucket_kg": 1.0,
                "min_distance_to_dig_area_m": 0.04,
                "bucket_depth_below_dig_area_plane_m": 0.03,
            }
        },
    )()
    override_ready = service.evaluate(
        _snapshot(mass=3.0, distance=1.0, plane_depth=0.0),
        primitive_boundary_facts_from_event(metrics_override),
        context,
        config=config,
    )
    assert override_ready.shallow_guard_ready is True


def _context(
    *,
    entry_target: tuple[float, float] | None = (0.0, 0.0),
    envelope_token: np.ndarray | None = None,
    envelope_config: ReturnStartEnvelopeConfig | None = None,
) -> ReturnToDigHandoffContext:
    return ReturnToDigHandoffContext(
        entry_target=entry_target,
        envelope_token=_ready_token() if envelope_token is None else envelope_token,
        envelope_config=envelope_config or ReturnStartEnvelopeConfig(gate_enabled=False),
        use_prior_spatial_bounds=False,
        use_prior_qpos_bounds=False,
    )


def _snapshot(
    *,
    mass: float = 0.0,
    distance: float = 0.0,
    plane_depth: float = 0.08,
    local_depth: float = 0.10,
    contact: float = 1.0,
    qpos: list[float] | None = None,
    bucket_pose: tuple[float, float, float] | None = (0.0, 0.0, 0.0),
):
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = float(mass)
    env_state[ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = float(distance)
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = float(plane_depth)
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = float(local_depth)
    env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = float(contact)
    env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = 0.25
    env_state[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = 0.40
    if bucket_pose is not None:
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = float(bucket_pose[0])
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = float(bucket_pose[1])
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = float(bucket_pose[2])
    else:
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = np.nan
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = np.nan
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = np.nan
    return build_planner_snapshot(
        {
            "env_state": env_state,
            "qpos": np.asarray(qpos or [0.50, 0.60, 0.20, 0.10], dtype=np.float32),
            "qvel": np.zeros(4, dtype=np.float32),
        },
        active_skill="return",
        cycle_index=0,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )


def _ready_token() -> np.ndarray:
    token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    token[RETURN_ENVELOPE_LONG_NORM_IDX] = 0.25
    token[RETURN_ENVELOPE_SHORT_NORM_IDX] = 0.40
    token[RETURN_ENVELOPE_DEPTH_CENTER_IDX] = 0.10
    token[RETURN_ENVELOPE_DEPTH_MIN_IDX] = 0.08
    token[RETURN_ENVELOPE_DEPTH_MAX_IDX] = 0.12
    token[RETURN_ENVELOPE_TIP_RADIUS_IDX] = 0.20
    token[RETURN_ENVELOPE_CONTACT_FLAG_IDX] = 1.0
    token[RETURN_ENVELOPE_QPOS_CENTER_SLICE] = np.asarray(
        [0.50, 0.60, 0.20, 0.10],
        dtype=np.float32,
    )
    token[RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE] = np.asarray(
        [0.05, 0.05, 0.05, 0.05],
        dtype=np.float32,
    )
    token[RETURN_ENVELOPE_QPOS_VALID_IDX] = 1.0
    token[RETURN_ENVELOPE_QVEL_ABS_MAX_IDX] = 0.0
    token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] = 1.0
    return token
