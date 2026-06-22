from __future__ import annotations

from dataclasses import fields
from typing import Any

import numpy as np

from testbed.planner.primitive_capability_provider import (
    PrimitiveFSMCapabilityProvider,
    PrimitiveFSMCapabilityProviderPorts,
)


class _BoundaryEvent:
    def __init__(
        self,
        *,
        dig_complete: bool = False,
        dump_complete: bool = False,
        next_dig_entry_ready: bool = False,
        metrics: dict[str, float] | None = None,
    ) -> None:
        self.dig_complete = dig_complete
        self.dump_complete = dump_complete
        self.next_dig_entry_ready = next_dig_entry_ready
        self.metrics = metrics


def _obs(
    *,
    mass_in_bucket_kg: float = 0.0,
    deposited_mass_in_target_box_kg: float = 0.0,
    min_distance_to_dig_area_m: float = 0.0,
    bucket_depth_below_dig_area_plane_m: float = 0.0,
    target_metrics: bool = False,
) -> dict[str, Any]:
    task_metrics: dict[str, float] = {
        "mass_in_bucket_kg": mass_in_bucket_kg,
        "deposited_mass_in_target_box_kg": deposited_mass_in_target_box_kg,
        "min_distance_to_dig_area_m": min_distance_to_dig_area_m,
        "bucket_depth_below_dig_area_plane_m": bucket_depth_below_dig_area_plane_m,
    }
    if target_metrics:
        task_metrics.update(
            {
                "target_geometry_available": 1.0,
                "target_horizontal_distance_m": 0.25,
                "bucket_height_above_target_rim_m": 1.0,
                "bucket_over_target_footprint_mask": 1.0,
                "dump_clearance_ok_mask": 1.0,
                "bucket_dump_area_relative_x_m": 0.0,
                "bucket_dump_area_relative_z_m": 0.0,
                "bucket_dump_area_footprint_outside_distance_m": 0.0,
            }
        )
    return {
        "qpos": np.asarray([0.0, 0.0], dtype=np.float32),
        "qvel": np.asarray([0.0, 0.0], dtype=np.float32),
        "task_metrics": task_metrics,
    }


def _ports(
    *,
    calls: list[str] | None = None,
    semantic_boundary_profile_active: bool = False,
    return_state: dict[str, bool] | None = None,
    dig_reason_sink: list[str] | None = None,
) -> PrimitiveFSMCapabilityProviderPorts:
    calls = calls if calls is not None else []
    return_state = return_state if return_state is not None else {
        "seen": False,
        "entry": False,
        "start": False,
    }
    dig_reason_sink = dig_reason_sink if dig_reason_sink is not None else []

    def refresh_return_handoff_state(obs: dict[str, Any]) -> None:
        calls.append("refresh_return_handoff_state")
        return_state["seen"] = True
        return_state["entry"] = True
        return_state["start"] = True

    def read_return_flag(name: str) -> bool:
        calls.append(name)
        return bool(return_state[name])

    return PrimitiveFSMCapabilityProviderPorts(
        action_dim=2,
        semantic_boundary_profile_active=lambda: semantic_boundary_profile_active,
        coverage_terminal_stop_requested=False,
        dig_step_count=12,
        dig_mass_plateau_count=3,
        dig_to_carry_min_distance_to_dig_area_m=0.5,
        dig_to_carry_min_bucket_mass_kg=20.0,
        dig_to_carry_target_bucket_mass_kg=20.0,
        dig_to_carry_mass_plateau_enabled=True,
        dig_to_carry_mass_plateau_min_bucket_mass_kg=5.0,
        dig_to_carry_mass_plateau_hold_steps=3,
        dig_to_carry_mass_plateau_min_steps=5,
        dump_ready_min_bucket_mass_kg=10.0,
        dig_bad_replan_enabled=True,
        dig_bad_replan_max_steps=10,
        dig_bad_replan_min_bucket_mass_kg=3.0,
        dig_exit_guard_enabled=True,
        dig_exit_guard_min_steps=10,
        dig_exit_guard_min_bucket_mass_kg=3.0,
        dig_exit_guard_overshoot_m=0.65,
        dig_exit_overshoot_m=lambda obs: 0.7,
        set_dig_to_carry_reason=lambda reason: dig_reason_sink.append(reason),
        coverage_cycle_start_deposit_kg=2.0,
        dump_ready_hold_count=1,
        dump_ready_hold_steps=2,
        dump_ready_min_height_above_rim_m=0.5,
        dump_ready_require_over_footprint=True,
        dump_ready_require_clearance=True,
        dump_ready_max_horizontal_distance_m=1.0,
        dump_ready_position_mode="footprint_or_dump_area_relative",
        dump_ready_max_dump_area_footprint_outside_distance_m=0.25,
        dump_ready_min_dump_area_relative_x_m=-1.0,
        dump_ready_max_dump_area_relative_x_m=1.0,
        dump_ready_min_dump_area_relative_z_m=-1.0,
        dump_ready_max_dump_area_relative_z_m=1.0,
        dump_ready_near_window_enabled=False,
        dump_ready_near_window_x_tolerance_m=0.0,
        dump_ready_near_window_z_tolerance_m=0.0,
        dump_ready_near_window_outside_tolerance_m=0.0,
        dump_ready_near_window_require_over_footprint=True,
        dump_done_max_bucket_mass_kg=1.0,
        dump_done_min_deposit_delta_kg=2.0,
        dump_done_use_boundary_event=True,
        dump_start_deposited_mass_kg=4.0,
        dump_done_hold_count=0,
        dump_done_hold_steps=1,
        refresh_return_handoff_state=refresh_return_handoff_state,
        return_next_dig_event_seen=lambda: read_return_flag("seen"),
        return_entry_close=lambda: read_return_flag("entry"),
        return_start_envelope_ready=lambda: read_return_flag("start"),
        pre_dig_align_before_dig=lambda: False,
        return_to_dig_start_envelope_direct_handoff_enabled=True,
        return_to_dig_start_envelope_gate_enabled=True,
        return_to_dig_shallow_guard_enabled=True,
        return_to_dig_max_bucket_mass_kg=1.0,
        return_to_dig_touch_tolerance_m=0.5,
        return_to_dig_min_depth_m=-0.1,
        return_to_dig_max_depth_m=0.5,
        return_to_dig_max_entry_error_m=0.1,
    )


def test_provider_dig_status_projects_observation_without_reason_mirror() -> None:
    reasons: list[str] = []
    provider = PrimitiveFSMCapabilityProvider(
        ports=_ports(dig_reason_sink=reasons)
    )

    status = provider.dig_transition_status(
        _obs(mass_in_bucket_kg=25.0, min_distance_to_dig_area_m=1.0),
        boundary_event=None,
    )

    assert status.dig_step_count == 12
    assert status.mass_in_bucket_kg == 25.0
    assert status.min_distance_to_dig_area_m == 1.0
    assert status.dig_to_carry_ready is True
    assert status.dig_to_carry_reason == "loaded"
    assert reasons == []

    provider.sync_dig_transition_reason(status)

    assert reasons == ["loaded"]


def test_provider_sync_dig_transition_reason_writes_empty_reason_mirror() -> None:
    reasons: list[str] = []
    provider = PrimitiveFSMCapabilityProvider(
        ports=_ports(dig_reason_sink=reasons)
    )

    status = provider.dig_transition_status(
        _obs(mass_in_bucket_kg=0.0, min_distance_to_dig_area_m=1.0),
        boundary_event=None,
    )
    provider.sync_dig_transition_reason(status)

    assert status.dig_to_carry_reason == ""
    assert reasons == [""]


def test_provider_carry_and_dump_status_share_observation_projection() -> None:
    provider = PrimitiveFSMCapabilityProvider(ports=_ports())

    carry = provider.carry_transition_status(
        _obs(
            mass_in_bucket_kg=25.0,
            deposited_mass_in_target_box_kg=7.0,
            target_metrics=True,
        ),
        boundary_event=None,
    )
    dump = provider.dump_transition_status(
        _obs(mass_in_bucket_kg=0.5, deposited_mass_in_target_box_kg=10.0),
        boundary_event=None,
    )

    assert carry.deposit_delta_since_cycle_start_kg == 5.0
    assert carry.ready_to_dump is True
    assert carry.carry_to_dump_reason == "target_ready"
    assert dump.deposit_delta_since_dump_start_kg == 6.0
    assert dump.ready_to_return is True
    assert dump.coverage_completion_reason == "dump_mass_low"


def test_provider_refresh_return_transition_state_refreshes_handoff_cache() -> None:
    calls: list[str] = []
    return_state = {"seen": False, "entry": False, "start": False}
    provider = PrimitiveFSMCapabilityProvider(
        ports=_ports(calls=calls, return_state=return_state)
    )
    obs = _obs(
        mass_in_bucket_kg=0.5,
        min_distance_to_dig_area_m=0.1,
        bucket_depth_below_dig_area_plane_m=0.0,
    )

    provider.refresh_return_transition_state(obs)

    assert calls == ["refresh_return_handoff_state"]
    assert return_state == {"seen": True, "entry": True, "start": True}


def test_provider_return_status_read_is_read_only_without_explicit_refresh() -> None:
    calls: list[str] = []
    return_state = {"seen": False, "entry": False, "start": False}
    provider = PrimitiveFSMCapabilityProvider(
        ports=_ports(calls=calls, return_state=return_state)
    )

    status = provider.return_transition_status(
        _obs(
            mass_in_bucket_kg=0.5,
            min_distance_to_dig_area_m=0.1,
            bucket_depth_below_dig_area_plane_m=0.0,
        ),
        boundary_event=None,
    )

    assert "refresh_return_handoff_state" not in calls
    assert calls == ["seen", "entry", "start"]
    assert status.completed_transition is False
    assert status.switch_reason == ""


def test_provider_return_status_after_explicit_refresh_matches_old_result() -> None:
    calls: list[str] = []
    return_state = {"seen": False, "entry": False, "start": False}
    provider = PrimitiveFSMCapabilityProvider(
        ports=_ports(calls=calls, return_state=return_state)
    )
    obs = _obs(
        mass_in_bucket_kg=0.5,
        min_distance_to_dig_area_m=0.1,
        bucket_depth_below_dig_area_plane_m=0.0,
    )

    provider.refresh_return_transition_state(obs)
    status = provider.return_transition_status(obs, boundary_event=None)

    assert calls == [
        "refresh_return_handoff_state",
        "seen",
        "entry",
        "start",
    ]
    assert status.completed_transition is True
    assert status.switch_reason == "return_to_dig_next_dig_entry_ready"


def test_provider_ports_do_not_accept_planner_or_policy_self() -> None:
    field_names = {field.name for field in fields(PrimitiveFSMCapabilityProviderPorts)}

    assert "self" not in field_names
    assert "planner" not in field_names
    assert "policy" not in field_names
