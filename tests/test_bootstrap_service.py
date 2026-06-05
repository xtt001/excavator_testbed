from __future__ import annotations

import numpy as np
import pytest

from testbed.planner.bootstrap import (
    BootstrapConfig,
    BootstrapFacts,
    BootstrapService,
)


def _config(**overrides: object) -> BootstrapConfig:
    values = {
        "action_dim": 4,
        "end_mode": "scripted_qpos",
        "end_min_bucket_mass_kg": 300.0,
        "end_min_distance_to_dig_area_m": 0.25,
        "scripted_target_qpos": np.asarray([0.5, 0.6, 0.2, 0.1], dtype=np.float32),
        "scripted_kp": 2.0,
        "scripted_kd": 0.25,
        "scripted_action_clip": [0.75, 0.35, 0.35, 0.55],
        "scripted_action_signs": np.ones(4, dtype=np.float32),
        "scripted_qpos_tolerance": 0.02,
        "scripted_qvel_abs_max": 0.08,
        "scripted_hold_steps": 2,
        "scripted_max_steps": 5,
    }
    values.update(overrides)
    return BootstrapConfig(**values)


def _facts(**overrides: object) -> BootstrapFacts:
    values = {
        "qpos": np.asarray([0.5, 0.6, 0.2, 0.1], dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
    }
    values.update(overrides)
    return BootstrapFacts(**values)


def test_scripted_target_reached_updates_hold_count() -> None:
    service = BootstrapService()
    config = _config(scripted_hold_steps=2)

    first = service.scripted_target_reached(_facts(hold_count=0), config)
    second = service.scripted_target_reached(_facts(hold_count=first.hold_count), config)
    reset = service.scripted_target_reached(
        _facts(
            qpos=np.asarray([0.7, 0.6, 0.2, 0.1], dtype=np.float32),
            hold_count=second.hold_count,
        ),
        config,
    )

    assert not first.ready
    assert first.hold_count == 1
    assert second.ready
    assert second.hold_count == 2
    assert not reset.ready
    assert reset.hold_count == 0


def test_scripted_timeout_preserves_hold_count_and_requests_increment() -> None:
    service = BootstrapService()
    config = _config(scripted_hold_steps=3, scripted_max_steps=2)

    decision = service.should_end(
        _facts(hold_count=1, step_count=2),
        config,
    )

    assert decision.should_end
    assert decision.timeout_increment
    assert decision.hold_count == 2


def test_learned_bootstrap_gates_require_policy_presence() -> None:
    service = BootstrapService()

    assert not service.should_end(
        _facts(
            bootstrap_policy_present=False,
            qualified_dig_start=True,
        ),
        _config(end_mode="first_qualified_dig_start", scripted_target_qpos=None),
    ).should_end
    assert service.should_end(
        _facts(
            bootstrap_policy_present=True,
            qualified_dig_start=True,
        ),
        _config(end_mode="first_qualified_dig_start", scripted_target_qpos=None),
    ).should_end
    assert service.should_end(
        _facts(
            bootstrap_policy_present=True,
            mass_in_bucket_kg=300.0,
            min_distance_to_dig_area_m=0.25,
        ),
        _config(end_mode="loaded_and_clear", scripted_target_qpos=None),
    ).should_end


def test_scripted_action_matches_pd_control_and_action_signs() -> None:
    service = BootstrapService()
    config = _config(
        scripted_kp=2.0,
        scripted_kd=0.25,
        scripted_action_signs=np.asarray([1.0, -1.0, 1.0, 1.0], dtype=np.float32),
    )

    action = service.scripted_action(
        _facts(
            qpos=np.asarray([0.4, 0.7, 0.1, 0.2], dtype=np.float32),
            qvel=np.asarray([0.1, -0.1, 0.0, 0.2], dtype=np.float32),
        ),
        config,
    )

    np.testing.assert_allclose(
        action,
        np.asarray([0.175, 0.175, 0.2, -0.25], dtype=np.float32),
        atol=1e-6,
    )


def test_scripted_action_requires_target_qpos() -> None:
    service = BootstrapService()

    with pytest.raises(RuntimeError, match="scripted bootstrap"):
        service.scripted_action(
            _facts(),
            _config(scripted_target_qpos=None),
        )
