from __future__ import annotations

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.boundary_detector import (
    BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
    QUALIFIED_DIG_START_MODE_CONTACT_DEPTH,
    BoundaryDetector,
    BoundaryDetectorConfig,
    build_boundary_detector_from_config,
)
from testbed.planner.primitive.decision.backends.legacy_fsm import (
    LegacyFSMCarryBranch,
    LegacyFSMCarryConfig,
)
from testbed.planner.primitive.decision.contracts import (
    CompleteCoverageDumpEffect,
    SetReturnOrDirectHandoffEffect,
    SwitchSkillEffect,
)
from testbed.planner.primitive.facts.capabilities import CarryTransitionStatus


def _detector(*, release_ownership_enabled: bool) -> BoundaryDetector:
    return BoundaryDetector(
        BoundaryDetectorConfig(
            boundary_profile=BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
            qualified_dig_start_mode=QUALIFIED_DIG_START_MODE_CONTACT_DEPTH,
            residual_bucket_mass_thresh=15.0,
            deposit_plateau_steps=1,
            dig_complete_min_bucket_mass_kg=15.0,
            dig_complete_mass_plateau_hold_steps=1,
            dig_complete_departed_hold_steps=1,
            dump_committed_min_relative_z_m=0.45,
            dump_committed_hold_steps=1,
            dump_committed_stable_window_steps=1,
            release_onset_dump_ownership_diagnostic_enabled=(
                release_ownership_enabled
            ),
        )
    )


def _state(
    *,
    mass: float,
    dig_distance: float,
    depth: float,
    deposited: float = 0.0,
    outside: float = 9.0,
    relative_x: float = 9.0,
    relative_z: float = 9.0,
    height: float = 0.0,
    over_footprint: float = 0.0,
) -> np.ndarray:
    state = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    state[ENV_STATE_MASS_IN_BUCKET_IDX] = mass
    state[ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = dig_distance
    state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = depth
    state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = deposited
    state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = outside
    state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = relative_x
    state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = relative_z
    state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = height
    state[ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX] = over_footprint
    return state


def _prime_completed_dig(detector: BoundaryDetector) -> None:
    action = np.zeros(4, dtype=np.float32)
    qpos = np.full(4, 0.5, dtype=np.float32)
    detector.update(
        env_state=_state(mass=0.0, dig_distance=0.04, depth=0.03),
        action=action,
        qpos=qpos,
    )
    detector.update(
        env_state=_state(mass=30.0, dig_distance=0.12, depth=0.0),
        action=action,
        qpos=qpos,
    )
    complete = detector.update(
        env_state=_state(mass=30.0, dig_distance=0.12, depth=0.0),
        action=action,
        qpos=qpos,
    )
    assert complete.dig_complete is True


def _release_tick(
    detector: BoundaryDetector,
    *,
    deposited_gain: float,
    outside: float = 0.0,
    over_footprint: float = 1.0,
):
    return detector.update(
        env_state=_state(
            mass=29.0,
            dig_distance=0.30,
            depth=0.0,
            deposited=deposited_gain,
            outside=outside,
            relative_x=0.60,
            relative_z=0.20,
            height=0.70,
            over_footprint=over_footprint,
        ),
        action=np.zeros(4, dtype=np.float32),
        qpos=np.full(4, 0.5, dtype=np.float32),
        task_metrics={
            "delta_mass_in_bucket_kg": -1.0,
            "delta_deposited_mass_in_target_box_kg": deposited_gain,
        },
    )


def test_release_evidence_can_lock_dump_ownership_diagnostically() -> None:
    detector = _detector(release_ownership_enabled=True)
    _prime_completed_dig(detector)

    event = _release_tick(detector, deposited_gain=1.0)

    assert event.dump_start is True
    assert event.dump_committed_start is False
    assert event.release_onset is True


def test_release_ownership_is_disabled_by_default() -> None:
    detector = _detector(release_ownership_enabled=False)
    _prime_completed_dig(detector)

    event = _release_tick(detector, deposited_gain=1.0)

    assert event.dump_start is False
    assert event.dump_committed_start is False
    assert event.release_onset is False


def test_release_ownership_requires_real_deposit_not_bucket_drop_alone() -> None:
    detector = _detector(release_ownership_enabled=True)
    _prime_completed_dig(detector)

    event = _release_tick(detector, deposited_gain=0.0)

    assert event.dump_start is False
    assert event.release_onset is False


def test_release_ownership_requires_unload_region() -> None:
    detector = _detector(release_ownership_enabled=True)
    _prime_completed_dig(detector)

    event = _release_tick(
        detector,
        deposited_gain=1.0,
        outside=0.60,
        over_footprint=0.0,
    )

    assert event.dump_start is False
    assert event.release_onset is False


def test_dump_ownership_has_priority_over_carry_release_safety() -> None:
    status = CarryTransitionStatus(
        mass_in_bucket_kg=10.0,
        deposited_mass_in_target_box_kg=20.0,
        deposit_delta_since_cycle_start_kg=10.0,
        semantic_boundary_profile_active=True,
        dump_committed_event=False,
        release_onset_event=True,
        dump_complete_event=False,
        legacy_dump_start_event=False,
        carry_release_safety_done=True,
        dump_ready=False,
        next_dump_ready_hold_count=3,
        ready_to_dump=True,
        carry_to_dump_reason="release_onset_boundary",
        carry_to_return_reason="carry_to_return_release_safety",
    )
    branch = LegacyFSMCarryBranch(
        LegacyFSMCarryConfig(carry_skill_name="carry")
    )

    effects = branch._effects_for_status(status)

    switch = next(effect for effect in effects if isinstance(effect, SwitchSkillEffect))
    assert switch.target_skill_name == "dump"
    assert switch.switch_reason == "carry_to_dump_release_onset_boundary"
    assert not any(
        isinstance(effect, SetReturnOrDirectHandoffEffect) for effect in effects
    )
    assert not any(isinstance(effect, CompleteCoverageDumpEffect) for effect in effects)


def test_boundary_config_parses_release_ownership_diagnostic_flag() -> None:
    default = build_boundary_detector_from_config(
        boundary_cfg={"profile": BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS}
    )
    enabled = build_boundary_detector_from_config(
        boundary_cfg={
            "profile": BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
            "release_onset_dump_ownership_diagnostic_enabled": True,
        }
    )

    assert (
        default.config.release_onset_dump_ownership_diagnostic_enabled is False
    )
    assert (
        enabled.config.release_onset_dump_ownership_diagnostic_enabled is True
    )
