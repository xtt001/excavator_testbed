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
from testbed.planner import primitive_config
from testbed.planner import return_handoff as return_handoff_module
from testbed.planner import return_to_dig_transition as return_transition_module
from testbed.planner.primitive_decisions import primitive_boundary_facts_from_event
from testbed.planner.return_handoff import (
    RETURN_TO_DIG_CONFIG_KEYS,
    RETURN_TO_DIG_HANDOFF_CONFIG_FIELDS,
    RETURN_TO_DIG_HANDOFF_STATUS_FIELDS,
    ReturnNextDigEntryTargetFacts,
    ReturnNextDigEntryTargetResolver,
    ReturnToDigEntryErrorFacts,
    ReturnToDigHandoffConfig,
    ReturnToDigHandoffContext,
    ReturnToDigHandoffGateService,
    ReturnToDigHandoffStatusState,
    ReturnToDigPlannerConfig,
    build_return_next_dig_entry_target_facts,
    build_return_next_dig_entry_target_facts_from_runtime,
    build_return_to_dig_config,
    build_return_to_dig_config_from_mapping,
    build_return_to_dig_handoff_config_from_mapping,
    build_return_to_dig_handoff_context,
    build_return_to_dig_handoff_context_from_runtime,
    build_return_to_dig_handoff_status_state_from_mapping,
)
from testbed.planner.return_start_envelope import (
    ReturnStartEnvelopeConfig,
    normalize_plane_depth_mode,
    return_start_envelope_gate_prior_context,
)
from testbed.planner.return_to_dig_transition import (
    ReturnDirectHandoffAttemptConfig,
    ReturnDirectHandoffAttemptFacts,
    ReturnDirectHandoffAttemptOutcome,
    ReturnDirectHandoffRuntimeProjection,
    ReturnToDigTransitionCompletionConfig,
    ReturnToDigTransitionCompletionFacts,
    ReturnToDigTransitionCompletionRequest,
    ReturnToDigTransitionConfig,
    ReturnToDigTransitionCounterUpdate,
    ReturnToDigTransitionFacts,
    ReturnToDigTransitionOutcome,
    ReturnToDigTransitionRuntimeProjection,
    ReturnToDigTransitionService,
)
from testbed.planner.snapshots import build_planner_snapshot


def test_return_handoff_reexports_return_transition_service_for_compatibility() -> None:
    assert (
        return_handoff_module.ReturnToDigTransitionService
        is return_transition_module.ReturnToDigTransitionService
    )
    assert (
        return_handoff_module.ReturnDirectHandoffAttemptFacts
        is return_transition_module.ReturnDirectHandoffAttemptFacts
    )
    assert (
        return_handoff_module.ReturnToDigTransitionCompletion
        is return_transition_module.ReturnToDigTransitionCompletion
    )
    assert (
        return_handoff_module.ReturnToDigTransitionCompletionRequest
        is return_transition_module.ReturnToDigTransitionCompletionRequest
    )


def test_return_to_dig_config_builder_is_domain_source_of_truth() -> None:
    values = {
        "return_to_dig_shallow_guard_enabled": True,
        "return_to_dig_max_bucket_mass_kg": 2.5,
        "return_to_dig_touch_tolerance_m": 0.15,
        "return_to_dig_min_depth_m": 0.03,
        "return_to_dig_max_depth_m": 0.18,
        "return_to_dig_max_entry_error_m": "0.55",
        "return_to_dig_start_envelope_gate_enabled": True,
        "return_to_dig_start_envelope_spatial_tolerance": 0.20,
        "return_to_dig_start_envelope_depth_tolerance_m": 0.07,
        "return_to_dig_start_envelope_local_depth_tolerance_m": 0.006,
        "return_to_dig_start_envelope_plane_depth_tolerance_m": 0.025,
        "return_to_dig_start_envelope_plane_depth_mode": "median-floor",
        "return_to_dig_start_envelope_qpos_tolerance": 0.08,
        "return_to_dig_start_envelope_require_contact": False,
        "return_to_dig_start_envelope_direct_handoff_enabled": True,
        "return_max_steps": 12,
        "ignored": object(),
    }

    assert primitive_config.RETURN_TO_DIG_CONFIG_KEYS is RETURN_TO_DIG_CONFIG_KEYS
    assert primitive_config.build_return_to_dig_config is build_return_to_dig_config
    assert (
        primitive_config.build_return_to_dig_config_from_mapping
        is build_return_to_dig_config_from_mapping
    )
    assert primitive_config.normalize_plane_depth_mode is normalize_plane_depth_mode
    assert build_return_to_dig_config_from_mapping(values) == (
        ReturnToDigPlannerConfig(
            return_to_dig_shallow_guard_enabled=True,
            return_to_dig_max_bucket_mass_kg=2.5,
            return_to_dig_touch_tolerance_m=0.15,
            return_to_dig_min_depth_m=0.03,
            return_to_dig_max_depth_m=0.18,
            return_to_dig_max_entry_error_m=0.55,
            return_to_dig_start_envelope_gate_enabled=True,
            return_to_dig_start_envelope_spatial_tolerance=0.20,
            return_to_dig_start_envelope_depth_tolerance_m=0.07,
            return_to_dig_start_envelope_local_depth_tolerance_m=0.006,
            return_to_dig_start_envelope_plane_depth_tolerance_m=0.025,
            return_to_dig_start_envelope_plane_depth_mode="p50_floor",
            return_to_dig_start_envelope_qpos_tolerance=0.08,
            return_to_dig_start_envelope_require_contact=False,
            return_to_dig_start_envelope_direct_handoff_enabled=True,
            return_max_steps=12,
        )
    )


def test_return_to_dig_handoff_config_mapping_preserves_runtime_projection() -> None:
    values = {
        "shallow_guard_enabled": 1,
        "max_bucket_mass_kg": "2.5",
        "touch_tolerance_m": "0.15",
        "min_depth_m": "0.03",
        "max_depth_m": "0.18",
        "max_entry_error_m": "0.55",
        "start_envelope_gate_enabled": 1,
        "direct_handoff_enabled": 0,
        "ignored": object(),
    }

    config = build_return_to_dig_handoff_config_from_mapping(values)

    assert {key for key, _ in RETURN_TO_DIG_HANDOFF_CONFIG_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert config == ReturnToDigHandoffConfig(
        shallow_guard_enabled=1,
        max_bucket_mass_kg="2.5",
        touch_tolerance_m="0.15",
        min_depth_m="0.03",
        max_depth_m="0.18",
        max_entry_error_m="0.55",
        start_envelope_gate_enabled=1,
        direct_handoff_enabled=0,
    )


def test_next_dig_entry_target_prefers_pending_next_cycle_raw_fields() -> None:
    service = ReturnNextDigEntryTargetResolver()

    resolution = service.resolve(
        ReturnNextDigEntryTargetFacts(
            cycle_index=4,
            pending_dig_cut_cycle_id=5,
            pending_dig_cut_raw_fields={
                "operator_entry_x_m": 1.25,
                "operator_entry_z_m": -0.75,
            },
            active_corridor_entry_target=(9.0, 9.5),
        )
    )

    assert resolution.entry_target == pytest.approx((1.25, -0.75))
    assert resolution.source == "pending_return_target"
    assert resolution.fallback_reason == ""


def test_build_return_next_dig_entry_target_facts_projects_legacy_inputs() -> None:
    raw_fields = {"operator_entry_x_m": 1.25, "operator_entry_z_m": -0.75}

    facts = build_return_next_dig_entry_target_facts(
        cycle_index=np.int64(4),
        pending_dig_cut_cycle_id=np.int64(5),
        pending_dig_cut_raw_fields=raw_fields,
        active_corridor_entry_target=(np.float64(0.40), np.float64(0.80)),
    )

    assert facts.cycle_index == 4
    assert facts.pending_dig_cut_cycle_id == 5
    assert facts.pending_dig_cut_raw_fields is raw_fields
    assert facts.active_corridor_entry_target == pytest.approx((0.40, 0.80))


def test_build_return_next_dig_entry_target_facts_from_runtime_projects_corridor() -> None:
    raw_fields = {"operator_entry_x_m": 1.25, "operator_entry_z_m": -0.75}
    corridor = type(
        "_Corridor",
        (),
        {"entry_x_m": np.float64(0.40), "entry_z_m": np.float64(0.80)},
    )()

    facts = build_return_next_dig_entry_target_facts_from_runtime(
        cycle_index=np.int64(4),
        pending_dig_cut_cycle_id=np.int64(5),
        pending_dig_cut_raw_fields=raw_fields,
        active_corridor=corridor,
    )

    assert facts == ReturnNextDigEntryTargetFacts(
        cycle_index=4,
        pending_dig_cut_cycle_id=5,
        pending_dig_cut_raw_fields=raw_fields,
        active_corridor_entry_target=(0.40, 0.80),
    )


def test_build_return_to_dig_handoff_context_projects_prior_context() -> None:
    token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64)
    token[RETURN_ENVELOPE_QPOS_VALID_IDX] = 1.0
    token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] = 1.0
    lower = np.linspace(-0.5, 0.5, RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    upper = lower + 1.0
    prior = {
        "return_start_envelope_cells": [
            {
                "cell_id": 4,
                "source_count": 2,
                "source_fraction": 0.5,
                "token_median": token.astype(np.float32),
                "token_p05": lower,
                "token_p95": upper,
            }
        ],
        "return_start_envelope_global": {"token_median": token.astype(np.float32)},
    }
    config = ReturnStartEnvelopeConfig(
        gate_enabled=True,
        use_cell_prior=True,
        min_source_count=2,
        min_source_fraction=0.25,
    )

    expected = return_start_envelope_gate_prior_context(
        token=token,
        dig_cut_prior=prior,
        config=config,
        cell_id=4,
    )
    context = build_return_to_dig_handoff_context(
        entry_target=(0.40, 0.80),
        envelope_token=token,
        envelope_config=config,
        dig_cut_prior=prior,
        cell_id=4,
        use_prior_spatial_bounds=False,
        use_prior_qpos_bounds=True,
    )

    assert context.entry_target == pytest.approx((0.40, 0.80))
    assert context.envelope_token.dtype == np.float32
    np.testing.assert_allclose(context.envelope_token, token.astype(np.float32))
    assert context.envelope_config is config
    assert context.prior_mapping == expected.prior_mapping
    np.testing.assert_allclose(context.prior_lower, expected.lower)
    np.testing.assert_allclose(context.prior_upper, expected.upper)
    assert context.use_prior_spatial_bounds is False
    assert context.use_prior_qpos_bounds is True


def test_build_return_to_dig_handoff_context_from_runtime_resolves_cell_lazily() -> None:
    token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float64)
    token[RETURN_ENVELOPE_QPOS_VALID_IDX] = 1.0
    token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] = 1.0
    lower = np.linspace(-0.5, 0.5, RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    upper = lower + 1.0
    prior = {
        "return_start_envelope_cells": [
            {
                "cell_id": 4,
                "source_count": 2,
                "source_fraction": 0.5,
                "token_median": token.astype(np.float32),
                "token_p05": lower,
                "token_p95": upper,
            }
        ],
        "return_start_envelope_global": {"token_median": token.astype(np.float32)},
    }
    config = ReturnStartEnvelopeConfig(
        gate_enabled=True,
        use_cell_prior=True,
        min_source_count=2,
        min_source_fraction=0.25,
    )
    resolver_calls: list[int] = []

    def resolver(corridor_id: int) -> int:
        resolver_calls.append(int(corridor_id))
        return 4

    context = build_return_to_dig_handoff_context_from_runtime(
        entry_target=(0.40, 0.80),
        envelope_token=token,
        envelope_config=config,
        dig_cut_prior=prior,
        pending_corridor_id=7,
        corridor_cell_id_resolver=resolver,
        use_prior_spatial_bounds=False,
        use_prior_qpos_bounds=True,
    )

    assert resolver_calls == [7]
    assert context.entry_target == pytest.approx((0.40, 0.80))
    assert context.envelope_token.dtype == np.float32
    assert context.prior_mapping is not None
    assert context.prior_mapping["cell_id"] == 4
    np.testing.assert_allclose(context.prior_lower, lower)
    np.testing.assert_allclose(context.prior_upper, upper)
    assert context.use_prior_spatial_bounds is False
    assert context.use_prior_qpos_bounds is True

    invalid_context = build_return_to_dig_handoff_context_from_runtime(
        entry_target=(0.40, 0.80),
        envelope_token=np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32),
        envelope_config=config,
        dig_cut_prior=prior,
        pending_corridor_id=7,
        corridor_cell_id_resolver=lambda _corridor_id: (_ for _ in ()).throw(
            AssertionError("resolver must not be called without gate bounds")
        ),
    )
    assert invalid_context.prior_mapping is None
    assert invalid_context.prior_lower is None
    assert invalid_context.prior_upper is None


@pytest.mark.parametrize(
    ("pending_cycle_id", "raw_fields", "fallback_reason"),
    [
        (
            4,
            {"operator_entry_x_m": 1.25, "operator_entry_z_m": -0.75},
            "stale_pending_entry",
        ),
        (
            5,
            {"operator_entry_x_m": 1.25},
            "non_finite_pending_entry",
        ),
        (
            5,
            {"operator_entry_x_m": np.nan, "operator_entry_z_m": -0.75},
            "non_finite_pending_entry",
        ),
        (
            5,
            {"operator_entry_x_m": 1.25, "operator_entry_z_m": np.inf},
            "non_finite_pending_entry",
        ),
    ],
)
def test_next_dig_entry_target_falls_back_to_active_corridor(
    pending_cycle_id: int,
    raw_fields: dict[str, float],
    fallback_reason: str,
) -> None:
    service = ReturnNextDigEntryTargetResolver()

    resolution = service.resolve(
        ReturnNextDigEntryTargetFacts(
            cycle_index=4,
            pending_dig_cut_cycle_id=pending_cycle_id,
            pending_dig_cut_raw_fields=raw_fields,
            active_corridor_entry_target=(0.40, 0.80),
        )
    )

    assert resolution.entry_target == pytest.approx((0.40, 0.80))
    assert resolution.source == "active_coverage_corridor"
    assert resolution.fallback_reason == fallback_reason


def test_next_dig_entry_target_returns_none_without_pending_or_corridor() -> None:
    service = ReturnNextDigEntryTargetResolver()

    resolution = service.resolve(
        ReturnNextDigEntryTargetFacts(
            cycle_index=4,
            pending_dig_cut_cycle_id=-1,
            pending_dig_cut_raw_fields=None,
            active_corridor_entry_target=None,
        )
    )

    assert resolution.entry_target is None
    assert resolution.source == "none"
    assert resolution.fallback_reason == "missing_pending_entry"


def test_entry_error_from_pose_uses_bucket_xz_and_entry_xz() -> None:
    error = ReturnToDigHandoffGateService.entry_error(
        ReturnToDigEntryErrorFacts(
            entry_target=(0.0, 0.0),
            bucket_dig_area_pose=(0.3, 99.0, 0.4),
        )
    )

    assert error == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("entry_target", "bucket_pose"),
    [
        (None, (0.3, 0.0, 0.4)),
        ((0.0, 0.0), None),
        ((np.nan, 0.0), (0.3, 0.0, 0.4)),
        ((0.0, np.inf), (0.3, 0.0, 0.4)),
        ((0.0, 0.0), (np.nan, 0.0, 0.4)),
        ((0.0, 0.0), (0.3, 0.0, np.inf)),
    ],
)
def test_entry_error_from_pose_returns_nan_for_missing_or_non_finite_values(
    entry_target: tuple[float, float] | None,
    bucket_pose: tuple[float, float, float] | None,
) -> None:
    error = ReturnToDigHandoffGateService.entry_error(
        ReturnToDigEntryErrorFacts(
            entry_target=entry_target,
            bucket_dig_area_pose=bucket_pose,
        )
    )

    assert np.isnan(error)


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


def test_runtime_state_from_decision_projects_status_without_latch_change() -> None:
    service = ReturnToDigHandoffGateService()
    decision = service.evaluate(
        _snapshot(qpos=[0.90, 0.60, 0.20, 0.10]),
        primitive_boundary_facts_from_event(None),
        _context(
            envelope_token=_ready_token(),
            envelope_config=ReturnStartEnvelopeConfig(
                gate_enabled=True,
                require_contact=True,
                plane_depth_mode="range",
            ),
        ),
        config=ReturnToDigHandoffConfig(
            max_entry_error_m=0.25,
            start_envelope_gate_enabled=True,
        ),
    )

    state = service.runtime_state_from_decision(
        decision,
        next_dig_event_seen=True,
    )

    assert state.entry_error_m == pytest.approx(decision.entry_error_m)
    assert state.entry_close is decision.entry_close
    assert state.next_dig_event_seen is True
    assert state.start_envelope_ready is decision.envelope_state.ready
    assert state.start_envelope_error == pytest.approx(decision.envelope_state.error)
    assert state.start_envelope_checks == decision.envelope_state.checks
    assert state.start_envelope_checks is not decision.envelope_state.checks


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


def test_status_snapshot_projects_handoff_and_start_envelope_state() -> None:
    checks = {"qpos_0": {"ok": False, "error": 0.12}}
    snapshot = ReturnToDigHandoffGateService.status_snapshot(
        handoff_config=ReturnToDigHandoffConfig(
            max_entry_error_m=0.25,
            start_envelope_gate_enabled=True,
            direct_handoff_enabled=True,
        ),
        envelope_config=ReturnStartEnvelopeConfig(
            gate_enabled=True,
            plane_depth_mode="target_band",
            local_depth_tolerance_m=0.007,
        ),
        state=ReturnToDigHandoffStatusState(
            entry_error_m=0.30,
            entry_close=False,
            next_dig_event_seen=True,
            start_envelope_ready=False,
            start_envelope_error=0.12,
            start_envelope_checks=checks,
        ),
    )
    checks["mutated"] = True

    assert snapshot.max_entry_error_m == pytest.approx(0.25)
    assert snapshot.entry_error_m == pytest.approx(0.30)
    assert snapshot.entry_close is False
    assert snapshot.next_dig_event_seen is True
    assert snapshot.start_envelope_gate_enabled is True
    assert snapshot.start_envelope_direct_handoff_enabled is True
    assert snapshot.start_envelope_ready is False
    assert snapshot.start_envelope_plane_depth_mode == "target_band"
    assert snapshot.start_envelope_local_depth_tolerance_m == pytest.approx(0.007)
    assert snapshot.start_envelope_error == pytest.approx(0.12)
    assert snapshot.start_envelope_checks == {"qpos_0": {"ok": False, "error": 0.12}}


def test_handoff_status_state_mapping_preserves_runtime_projection() -> None:
    checks = {"qpos": True}
    values = {
        "entry_error_m": "0.45",
        "entry_close": 1,
        "next_dig_event_seen": 0,
        "start_envelope_ready": 1,
        "start_envelope_error": "0.08",
        "start_envelope_checks": checks,
        "ignored": object(),
    }

    state = build_return_to_dig_handoff_status_state_from_mapping(values)
    checks["qpos"] = False

    assert {key for key, _ in RETURN_TO_DIG_HANDOFF_STATUS_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert state == ReturnToDigHandoffStatusState(
        entry_error_m=0.45,
        entry_close=True,
        next_dig_event_seen=False,
        start_envelope_ready=True,
        start_envelope_error=0.08,
        start_envelope_checks={"qpos": True},
    )


def test_initial_runtime_state_preserves_legacy_reset_defaults() -> None:
    state = ReturnToDigHandoffGateService.initial_runtime_state()
    other_state = ReturnToDigHandoffGateService.initial_runtime_state()

    assert isinstance(state, ReturnToDigHandoffStatusState)
    assert np.isnan(state.entry_error_m)
    assert state.entry_close is True
    assert state.next_dig_event_seen is False
    assert state.start_envelope_ready is True
    assert np.isnan(state.start_envelope_error)
    assert state.start_envelope_checks == {}

    state.start_envelope_checks["mutated"] = True
    assert other_state.start_envelope_checks == {}


def test_return_transition_prioritizes_next_event_over_direct_and_shallow() -> None:
    outcome = ReturnToDigTransitionService.classify(
        ReturnToDigTransitionFacts(
            handoff_ready=True,
            next_dig_event_ready=True,
            next_dig_event_seen=False,
            direct_handoff_ready=True,
            shallow_guard_ready=True,
        ),
        ReturnToDigTransitionConfig(legacy_shallow_guard_enabled=True),
    )

    assert outcome.action == "next_dig_event"
    assert outcome.next_dig_event_seen is True
    assert outcome.switch_reason("dig") == "return_to_dig_next_dig_entry_ready"
    assert (
        outcome.switch_reason("pre_dig_align")
        == "return_to_pre_dig_align_next_dig_entry_ready"
    )


def test_return_transition_latches_next_event_until_handoff_ready() -> None:
    waiting = ReturnToDigTransitionService.classify(
        ReturnToDigTransitionFacts(
            handoff_ready=False,
            next_dig_event_ready=True,
            next_dig_event_seen=False,
            direct_handoff_ready=False,
            shallow_guard_ready=True,
        ),
        ReturnToDigTransitionConfig(legacy_shallow_guard_enabled=True),
    )

    assert waiting.action == "wait"
    assert waiting.next_dig_event_seen is True
    assert waiting.switch_reason("dig") == ""

    ready = ReturnToDigTransitionService.classify(
        ReturnToDigTransitionFacts(
            handoff_ready=True,
            next_dig_event_ready=False,
            next_dig_event_seen=waiting.next_dig_event_seen,
            direct_handoff_ready=False,
            shallow_guard_ready=False,
        ),
        ReturnToDigTransitionConfig(legacy_shallow_guard_enabled=True),
    )

    assert ready.action == "next_dig_event"
    assert ready.switch_reason("dig") == "return_to_dig_next_dig_entry_ready"


def test_return_transition_direct_handoff_precedes_legacy_shallow_guard() -> None:
    outcome = ReturnToDigTransitionService.classify(
        ReturnToDigTransitionFacts(
            handoff_ready=True,
            next_dig_event_ready=False,
            next_dig_event_seen=False,
            direct_handoff_ready=True,
            shallow_guard_ready=True,
        ),
        ReturnToDigTransitionConfig(legacy_shallow_guard_enabled=True),
    )

    assert outcome.action == "direct_handoff"
    assert outcome.next_dig_event_seen is False
    assert outcome.switch_reason("dig") == "return_to_dig_start_envelope_ready"


def test_return_transition_shallow_guard_requires_legacy_profile_and_handoff() -> None:
    legacy = ReturnToDigTransitionService.classify(
        ReturnToDigTransitionFacts(
            handoff_ready=True,
            next_dig_event_ready=False,
            next_dig_event_seen=False,
            direct_handoff_ready=False,
            shallow_guard_ready=True,
        ),
        ReturnToDigTransitionConfig(legacy_shallow_guard_enabled=True),
    )
    semantic = ReturnToDigTransitionService.classify(
        ReturnToDigTransitionFacts(
            handoff_ready=True,
            next_dig_event_ready=False,
            next_dig_event_seen=False,
            direct_handoff_ready=False,
            shallow_guard_ready=True,
        ),
        ReturnToDigTransitionConfig(legacy_shallow_guard_enabled=False),
    )
    no_handoff = ReturnToDigTransitionService.classify(
        ReturnToDigTransitionFacts(
            handoff_ready=False,
            next_dig_event_ready=False,
            next_dig_event_seen=False,
            direct_handoff_ready=False,
            shallow_guard_ready=True,
        ),
        ReturnToDigTransitionConfig(legacy_shallow_guard_enabled=True),
    )

    assert legacy.action == "shallow_guard"
    assert legacy.switch_reason("dig") == "return_to_dig_shallow_entry_guard"
    assert semantic.action == "wait"
    assert no_handoff.action == "wait"


def test_return_transition_counter_update_projects_counter_suggestions() -> None:
    outcome = ReturnToDigTransitionOutcome(
        action="next_dig_event",
        reason_suffix="next_dig_entry_ready",
        next_dig_event_seen=True,
    )
    wait = ReturnToDigTransitionOutcome(
        action="wait",
        reason_suffix="",
        next_dig_event_seen=True,
    )

    update = ReturnToDigTransitionService.transition_counter_update(outcome)
    waiting = ReturnToDigTransitionService.transition_counter_update(wait)

    assert update == ReturnToDigTransitionCounterUpdate(
        should_transition=True,
        completed_transition_increment=1,
        cycle_index_increment=1,
    )
    assert waiting == ReturnToDigTransitionCounterUpdate(should_transition=False)


def test_return_transition_runtime_projection_combines_latch_and_counter_update() -> None:
    outcome = ReturnToDigTransitionOutcome(
        action="next_dig_event",
        reason_suffix="next_dig_entry_ready",
        next_dig_event_seen=True,
    )
    wait = ReturnToDigTransitionOutcome(
        action="wait",
        reason_suffix="",
        next_dig_event_seen=True,
    )

    projection = ReturnToDigTransitionService.transition_runtime_projection(outcome)
    waiting = ReturnToDigTransitionService.transition_runtime_projection(wait)

    assert projection == ReturnToDigTransitionRuntimeProjection(
        next_dig_event_seen=True,
        should_transition=True,
        completed_transition_increment=1,
        cycle_index_increment=1,
    )
    assert waiting == ReturnToDigTransitionRuntimeProjection(
        next_dig_event_seen=True,
        should_transition=False,
    )


def test_return_transition_completion_projects_next_skill_and_reason() -> None:
    outcome = ReturnToDigTransitionOutcome(
        action="next_dig_event",
        reason_suffix="next_dig_entry_ready",
        next_dig_event_seen=True,
    )
    dig = ReturnToDigTransitionService.transition_completion(
        outcome,
        ReturnToDigTransitionCompletionFacts(pre_dig_align_before_dig=False),
    )
    aligned = ReturnToDigTransitionService.transition_completion(
        outcome,
        ReturnToDigTransitionCompletionFacts(pre_dig_align_before_dig=True),
        ReturnToDigTransitionCompletionConfig(
            pre_dig_align_skill_name="pre_dig_align",
        ),
    )

    assert dig.should_transition is True
    assert dig.next_skill == "dig"
    assert dig.switch_reason == "return_to_dig_next_dig_entry_ready"
    assert aligned.should_transition is True
    assert aligned.next_skill == "pre_dig_align"
    assert (
        aligned.switch_reason == "return_to_pre_dig_align_next_dig_entry_ready"
    )


def test_return_transition_completion_request_projects_facts_and_config() -> None:
    request = ReturnToDigTransitionService.completion_request(
        pre_dig_align_before_dig=1,
        dig_skill_name="dig_skill",
        pre_dig_align_skill_name="align_skill",
    )

    assert request == ReturnToDigTransitionCompletionRequest(
        facts=ReturnToDigTransitionCompletionFacts(
            pre_dig_align_before_dig=True,
        ),
        config=ReturnToDigTransitionCompletionConfig(
            dig_skill_name="dig_skill",
            pre_dig_align_skill_name="align_skill",
        ),
    )


def test_return_transition_completion_waits_without_skill_projection() -> None:
    transition = ReturnToDigTransitionService.transition_completion(
        ReturnToDigTransitionOutcome(
            action="wait",
            reason_suffix="",
            next_dig_event_seen=True,
        ),
        ReturnToDigTransitionCompletionFacts(pre_dig_align_before_dig=True),
    )
    direct_attempt = ReturnToDigTransitionService.direct_handoff_completion(
        ReturnDirectHandoffAttemptOutcome(action="wait"),
        ReturnToDigTransitionCompletionFacts(pre_dig_align_before_dig=True),
    )

    assert transition.should_transition is False
    assert transition.next_skill == ""
    assert transition.switch_reason == ""
    assert direct_attempt.should_transition is False
    assert direct_attempt.next_skill == ""
    assert direct_attempt.switch_reason == ""


def test_return_transition_request_skips_direct_when_next_event_is_ready() -> None:
    request = ReturnToDigTransitionService.transition_request(
        handoff_ready=True,
        boundary_event=type(
            "_Boundary",
            (),
            {"next_dig_entry_ready": True},
        )(),
        previous_next_dig_event_seen=False,
        semantic_boundary_profile_active=False,
    )

    assert request.should_check_direct_handoff is False
    assert request.should_check_shallow_guard(False) is False
    assert request.config.legacy_shallow_guard_enabled is True
    assert request.facts == ReturnToDigTransitionFacts(
        handoff_ready=True,
        next_dig_event_ready=True,
        next_dig_event_seen=False,
        direct_handoff_ready=False,
        shallow_guard_ready=False,
    )


def test_return_transition_request_skips_direct_when_latched_event_can_handoff() -> None:
    request = ReturnToDigTransitionService.transition_request(
        handoff_ready=True,
        boundary_event=None,
        previous_next_dig_event_seen=True,
        semantic_boundary_profile_active=True,
    )

    assert request.should_check_direct_handoff is False
    assert request.should_check_shallow_guard(False) is False
    assert request.config.legacy_shallow_guard_enabled is True
    assert request.facts.next_dig_event_ready is False
    assert request.facts.next_dig_event_seen is True


def test_return_transition_request_gates_direct_and_legacy_shallow_guard() -> None:
    legacy = ReturnToDigTransitionService.transition_request(
        handoff_ready=True,
        boundary_event=None,
        previous_next_dig_event_seen=False,
        semantic_boundary_profile_active=False,
    )

    assert legacy.should_check_direct_handoff is True
    assert legacy.should_check_shallow_guard(direct_handoff_ready=True) is False
    assert legacy.should_check_shallow_guard(direct_handoff_ready=False) is True
    facts = legacy.facts_with_gate_results(
        direct_handoff_ready=False,
        shallow_guard_ready=True,
    )
    assert facts == ReturnToDigTransitionFacts(
        handoff_ready=True,
        next_dig_event_ready=False,
        next_dig_event_seen=False,
        direct_handoff_ready=False,
        shallow_guard_ready=True,
    )

    semantic = ReturnToDigTransitionService.transition_request(
        handoff_ready=True,
        boundary_event=type(
            "_Boundary",
            (),
            {"qualified_dig_start": False},
        )(),
        previous_next_dig_event_seen=False,
        semantic_boundary_profile_active=True,
    )

    assert semantic.should_check_direct_handoff is True
    assert semantic.config.legacy_shallow_guard_enabled is False
    assert semantic.should_check_shallow_guard(False) is False


@pytest.mark.parametrize(
    "facts",
    [
        ReturnDirectHandoffAttemptFacts(
            active_skill_name="dump",
            return_target_planner_enabled=True,
            direct_handoff_enabled=True,
        ),
        ReturnDirectHandoffAttemptFacts(
            active_skill_name="return",
            return_target_planner_enabled=False,
            direct_handoff_enabled=True,
        ),
        ReturnDirectHandoffAttemptFacts(
            active_skill_name="return",
            return_target_planner_enabled=True,
            direct_handoff_enabled=False,
        ),
    ],
)
def test_return_direct_handoff_attempt_skips_before_gate_when_guards_fail(
    facts: ReturnDirectHandoffAttemptFacts,
) -> None:
    outcome = ReturnToDigTransitionService.direct_handoff_attempt(
        facts,
        ReturnDirectHandoffAttemptConfig(),
    )

    assert outcome.action == "skip"
    assert outcome.should_prepare_return_target is False
    assert outcome.should_evaluate_handoff is False
    assert outcome.switch_reason("dig") == ""


def test_return_direct_handoff_attempt_requests_handoff_gate_after_guards() -> None:
    outcome = ReturnToDigTransitionService.direct_handoff_attempt(
        ReturnDirectHandoffAttemptFacts(
            active_skill_name="return",
            return_target_planner_enabled=True,
            direct_handoff_enabled=True,
        ),
        ReturnDirectHandoffAttemptConfig(),
    )

    assert outcome.action == "evaluate"
    assert outcome.should_prepare_return_target is True
    assert outcome.should_evaluate_handoff is True
    assert outcome.switch_reason("dig") == ""


def test_return_direct_handoff_attempt_request_projects_guards_and_gate_facts() -> None:
    skipped = ReturnToDigTransitionService.direct_handoff_attempt_request(
        active_skill_name="dump",
        return_target_planner_enabled=True,
        direct_handoff_enabled=True,
    )

    assert skipped.outcome.action == "skip"
    assert skipped.should_prepare_return_target is False
    assert skipped.should_evaluate_handoff is False

    request = ReturnToDigTransitionService.direct_handoff_attempt_request(
        active_skill_name="return",
        return_target_planner_enabled=True,
        direct_handoff_enabled=True,
    )

    assert request.facts == ReturnDirectHandoffAttemptFacts(
        active_skill_name="return",
        return_target_planner_enabled=True,
        direct_handoff_enabled=True,
    )
    assert request.config == ReturnDirectHandoffAttemptConfig()
    assert request.outcome.action == "evaluate"
    assert request.should_prepare_return_target is True
    assert request.should_evaluate_handoff is True
    assert request.facts_with_gate_results(
        handoff_ready=True,
        direct_handoff_ready=False,
    ) == ReturnDirectHandoffAttemptFacts(
        active_skill_name="return",
        return_target_planner_enabled=True,
        direct_handoff_enabled=True,
        handoff_evaluated=True,
        handoff_ready=True,
        direct_handoff_ready=False,
    )


@pytest.mark.parametrize(
    ("handoff_ready", "direct_handoff_ready"),
    [(False, False), (False, True), (True, False)],
)
def test_return_direct_handoff_attempt_waits_until_handoff_and_direct_gate_ready(
    handoff_ready: bool,
    direct_handoff_ready: bool,
) -> None:
    outcome = ReturnToDigTransitionService.direct_handoff_attempt(
        ReturnDirectHandoffAttemptFacts(
            active_skill_name="return",
            return_target_planner_enabled=True,
            direct_handoff_enabled=True,
            handoff_evaluated=True,
            handoff_ready=handoff_ready,
            direct_handoff_ready=direct_handoff_ready,
        ),
        ReturnDirectHandoffAttemptConfig(),
    )

    assert outcome.action == "wait"
    assert outcome.should_prepare_return_target is False
    assert outcome.should_evaluate_handoff is False
    assert outcome.switch_reason("dig") == ""


def test_return_direct_handoff_attempt_returns_start_envelope_reason() -> None:
    outcome = ReturnToDigTransitionService.direct_handoff_attempt(
        ReturnDirectHandoffAttemptFacts(
            active_skill_name="return",
            return_target_planner_enabled=True,
            direct_handoff_enabled=True,
            handoff_evaluated=True,
            handoff_ready=True,
            direct_handoff_ready=True,
        ),
        ReturnDirectHandoffAttemptConfig(),
    )

    assert outcome.action == "direct_handoff"
    assert outcome.switch_reason("dig") == "return_to_dig_start_envelope_ready"
    assert (
        outcome.switch_reason("pre_dig_align")
        == "return_to_pre_dig_align_start_envelope_ready"
    )

    completion = ReturnToDigTransitionService.direct_handoff_completion(
        outcome,
        ReturnToDigTransitionCompletionFacts(pre_dig_align_before_dig=True),
        ReturnToDigTransitionCompletionConfig(
            pre_dig_align_skill_name="pre_dig_align",
        ),
    )
    assert completion.should_transition is True
    assert completion.next_skill == "pre_dig_align"
    assert completion.switch_reason == "return_to_pre_dig_align_start_envelope_ready"
    assert ReturnToDigTransitionService.direct_handoff_counter_update(
        outcome
    ) == ReturnToDigTransitionCounterUpdate(
        should_transition=True,
        completed_transition_increment=1,
        cycle_index_increment=1,
    )
    assert ReturnToDigTransitionService.direct_handoff_runtime_projection(
        outcome
    ) == ReturnDirectHandoffRuntimeProjection(
        should_transition=True,
        completed_transition_increment=1,
        cycle_index_increment=1,
    )
    assert ReturnToDigTransitionService.direct_handoff_runtime_projection(
        ReturnDirectHandoffAttemptOutcome(action="wait")
    ) == ReturnDirectHandoffRuntimeProjection(should_transition=False)


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
