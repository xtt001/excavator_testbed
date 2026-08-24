from __future__ import annotations

from dataclasses import replace

import pytest

from testbed.eval.dig_effect_neutral import DigNeutralStep
from testbed.eval.dig_effect_ports import DigZeroHandshake
from testbed.eval.dig_effect_state import (
    ACTION_DIM,
    CONTACT_FORCE_LIMIT_N,
    PREFLIGHT_TICKS,
    DigAtomicDiagnostics,
    DigEffectPhase,
    DigEffectStateMachine,
    DigEffectTick,
    canonical_token_sha256,
)


def test_mapping_adapters_do_not_truthify_non_boolean_safety_fields() -> None:
    handshake = {
        "observation": {},
        "sidecar_complete": "false",
        "diagnostics_enabled": True,
        "received_normalized_action": [0.0] * 4,
        "clamped_normalized_action": [0.0] * 4,
        "final_target_speed": [0.0] * 4,
        "limiter_active": False,
        "request_step_id": 0,
        "response_step_id": 0,
        "sim_time_ns": 0,
        "token_sha256": "a" * 64,
        "lineage_sha256": "b" * 64,
    }
    with pytest.raises(TypeError):
        DigZeroHandshake.from_mapping(handshake)

    neutral = dict(handshake)
    neutral.pop("observation")
    with pytest.raises(TypeError):
        DigNeutralStep.from_mapping(neutral)


def _tick(**overrides: object) -> DigEffectTick:
    values: dict[str, object] = {
        "sidecar_complete": True,
        "diagnostics_enabled": True,
        "token_sha256": "a" * 64,
        "lineage_sha256": "b" * 64,
        "tick_id": 1,
        "request_step_id": 1,
        "response_step_id": 1,
        "sim_time_ns": 1,
        "received_normalized_action": (0.0,) * ACTION_DIM,
        "clamped_normalized_action": (0.0,) * ACTION_DIM,
        "final_target_speed": (0.0,) * ACTION_DIM,
        "soft_limit_axes": (False,) * ACTION_DIM,
        "acceleration_limited_axes": (False,) * ACTION_DIM,
        "soil_contact": False,
        "wall_contact": False,
        "floor_contact": False,
        "hard_collision": False,
        "forbidden_contact": False,
        "unknown_contact": False,
        "max_force_n": 0.0,
        "nonfinite": False,
        "clamped": False,
        "stuck": False,
        "timeout": False,
    }
    values.update(overrides)
    return DigEffectTick(diagnostics=DigAtomicDiagnostics(**values))


def _machine() -> DigEffectStateMachine:
    token = (0.0,) * 10
    machine = DigEffectStateMachine()
    machine.prepare(token=token, token_sha256=canonical_token_sha256(token))
    for index in range(PREFLIGHT_TICKS):
        tick = _tick()
        machine.observe_preflight_tick(
            replace(
                tick,
                diagnostics=replace(
                    tick.diagnostics,  # type: ignore[arg-type]
                    tick_id=index + 1,
                    request_step_id=index + 1,
                    response_step_id=index + 1,
                    sim_time_ns=index + 1,
                ),
            )
        )
    machine.finish_preflight(True)
    machine.begin_run()
    return machine


@pytest.mark.parametrize(
    ("tick", "reason"),
    [
        (_tick(wall_contact=True), "wall_contact"),
        (_tick(floor_contact=True), "floor_contact"),
        (_tick(hard_collision=True), "hard_collision"),
        (_tick(forbidden_contact=True), "forbidden_contact"),
        (_tick(unknown_contact=True), "unknown_contact"),
        (
            _tick(max_force_n=CONTACT_FORCE_LIMIT_N),
            "force_at_or_above_100000n",
        ),
        (_tick(nonfinite=True), "nonfinite"),
        (
            _tick(
                clamped=True,
                received_normalized_action=(0.1, 0.0, 0.0, 0.0),
                clamped_normalized_action=(0.0,) * ACTION_DIM,
            ),
            "clamp",
        ),
        (_tick(soft_limit_axes=(True, False, False, False)), "soft_limit"),
        (_tick(stuck=True), "stuck"),
        (_tick(timeout=True), "timeout"),
    ],
)
def test_state_machine_stops_all_safety_events_but_not_soil(
    tick: DigEffectTick,
    reason: str,
) -> None:
    machine = _machine()
    assert machine.observe_run_tick(_tick(soil_contact=True)).continue_run is True

    decision = machine.observe_run_tick(tick)

    assert decision.continue_run is False
    assert decision.neutral_required is True
    assert decision.reason == reason
    machine.acknowledge_neutral(True)
    assert machine.phase is DigEffectPhase.REPORT


def test_missing_atomic_diagnostics_is_never_an_implicit_all_clear() -> None:
    token = (0.0,) * 10
    machine = DigEffectStateMachine()
    machine.prepare(token=token, token_sha256=canonical_token_sha256(token))

    decision = machine.observe_preflight_tick(DigEffectTick())

    assert decision.continue_run is False
    assert decision.neutral_required is True
    assert decision.reason == "preflight:atomic_diagnostics_missing"


def test_completion_is_derived_from_contact_exit_not_backend_flag() -> None:
    machine = _machine()
    assert machine.observe_run_tick(_tick(soil_contact=True)).continue_run
    assert machine.observe_run_tick(_tick(soil_contact=False)).continue_run
    assert machine.observe_run_tick(_tick(soil_contact=False)).continue_run
    decision = machine.observe_run_tick(_tick(soil_contact=False))

    assert decision.reason == "soil_exit_confirmed_3_clear_ticks"
    assert decision.successful is True
