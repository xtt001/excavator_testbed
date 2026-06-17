"""Compatibility-only 5P primitive planner shell."""

from __future__ import annotations

from typing import Any

from testbed.planner.boundary_detector import BoundaryDetector
from testbed.planner.dump_lifecycle import (
    DumpLifecycleRuntimeStatusSnapshot,
    DumpLifecycleRuntimeStatusState,
)
from testbed.planner.primitive_debug import (
    PrimitiveDebugStateSnapshotConfig,
    PrimitiveDebugStateSnapshotFacts,
    PrimitivePlannerDebugState,
    build_primitive_debug_state_snapshot_from_runtime,
)
from testbed.policies.base import Policy, register_policy
from testbed.policies.hybrid.adapter import HYBRID_MODE_TRANSITION, HYBRID_MODE_WORK
from testbed.policies.hybrid.primitive_planner import (
    BOOTSTRAP_SKILL_NAME,
    PrimitivePlannerACTPolicy,
)

PRIMITIVE_SKILL_NAMES_5P = ("dig", "carry", "approach_dump", "dump_release", "return")
PRIMITIVE_SKILL_IDS_5P = {
    name: index for index, name in enumerate(PRIMITIVE_SKILL_NAMES_5P)
}


@register_policy("primitive_planner_act_5p")
class PrimitivePlannerACT5PPolicy(PrimitivePlannerACTPolicy):
    """Scripted V2.2 planner over dig/carry/approach_dump/dump_release/return.

    The upper model should provide low-frequency task intent only. This planner
    owns high-frequency primitive boundary decisions from relative geometry,
    bucket mass, clearance, and V2.1 boundary events.
    """

    def __init__(
        self,
        *,
        dig_policy: Policy,
        first_dig_policy: Policy | None = None,
        carry_policy: Policy,
        approach_dump_policy: Policy,
        dump_release_policy: Policy,
        return_policy: Policy,
        boundary_detector: BoundaryDetector,
        bootstrap_policy: Policy | None = None,
        bootstrap_end_mode: str = "disabled",
        bootstrap_end_min_bucket_mass_kg: float = 300.0,
        bootstrap_end_min_distance_to_dig_area_m: float = 0.25,
        dig_to_carry_min_bucket_mass_kg: float = 300.0,
        dig_to_carry_min_distance_to_dig_area_m: float = 0.0,
        dig_to_carry_target_bucket_mass_kg: float | None = None,
        dig_to_carry_mass_plateau_enabled: bool = False,
        dig_to_carry_mass_plateau_min_bucket_mass_kg: float = 20.0,
        dig_to_carry_mass_plateau_epsilon_kg: float = 1.0,
        dig_to_carry_mass_plateau_hold_steps: int = 25,
        dig_to_carry_mass_plateau_min_steps: int = 80,
        dig_bad_replan_enabled: bool = False,
        dig_bad_replan_max_steps: int = 180,
        dig_bad_replan_min_bucket_mass_kg: float = 15.0,
        dig_exit_guard_enabled: bool = False,
        dig_exit_guard_min_steps: int = 80,
        dig_exit_guard_overshoot_m: float = 0.65,
        dig_exit_guard_min_bucket_mass_kg: float = 20.0,
        dig_failed_replan_next_skill: str = "dig",
        approach_ready_min_bucket_mass_kg: float = 150.0,
        approach_ready_max_horizontal_distance_m: float | None = 1.25,
        approach_ready_min_height_above_rim_m: float = -0.20,
        approach_ready_require_clearance: bool = True,
        approach_ready_hold_steps: int = 3,
        dump_release_ready_min_bucket_mass_kg: float = 150.0,
        dump_release_ready_min_height_above_rim_m: float = 0.45,
        dump_release_ready_require_over_footprint: bool = True,
        dump_release_ready_require_clearance: bool = True,
        dump_release_ready_max_horizontal_distance_m: float | None = 0.60,
        dump_release_ready_position_mode: str = "footprint_or_dump_area_relative",
        dump_release_ready_max_dump_area_footprint_outside_distance_m: float | None = 0.05,
        dump_release_ready_min_dump_area_relative_x_m: float | None = None,
        dump_release_ready_max_dump_area_relative_x_m: float | None = None,
        dump_release_ready_min_dump_area_relative_z_m: float | None = None,
        dump_release_ready_max_dump_area_relative_z_m: float | None = None,
        dump_release_ready_hold_steps: int = 3,
        dump_ready_near_window_enabled: bool = False,
        dump_ready_near_window_x_tolerance_m: float = 0.05,
        dump_ready_near_window_z_tolerance_m: float = 0.05,
        dump_ready_near_window_outside_tolerance_m: float = 0.0,
        dump_ready_near_window_require_over_footprint: bool = True,
        dump_done_max_bucket_mass_kg: float = 100.0,
        dump_done_min_deposit_delta_kg: float = 10.0,
        dump_done_hold_steps: int = 30,
        dump_done_use_boundary_event: bool = True,
        return_to_dig_shallow_guard_enabled: bool = False,
        return_to_dig_max_bucket_mass_kg: float = 15.0,
        return_to_dig_touch_tolerance_m: float = 0.05,
        return_to_dig_min_depth_m: float = 0.02,
        return_to_dig_max_depth_m: float = 0.12,
        return_to_dig_max_entry_error_m: float | None = None,
        return_to_dig_start_envelope_gate_enabled: bool = False,
        return_to_dig_start_envelope_spatial_tolerance: float = 0.10,
        return_to_dig_start_envelope_depth_tolerance_m: float = 0.08,
        return_to_dig_start_envelope_local_depth_tolerance_m: float = 0.005,
        return_to_dig_start_envelope_plane_depth_tolerance_m: float = 0.05,
        return_to_dig_start_envelope_plane_depth_mode: str = "range",
        return_to_dig_start_envelope_qpos_tolerance: float = 0.04,
        return_to_dig_start_envelope_require_contact: bool = True,
        return_to_dig_start_envelope_direct_handoff_enabled: bool = False,
        return_max_steps: int = 420,
        action_dim: int = 4,
        primitive_checkpoint_paths: dict[str, str] | None = None,
        goal_sequence: list[str] | tuple[str, ...] | None = None,
        goal_scenario_id: str = "s0_truck",
        goal_depth_norm: float = 1.0,
        goal_dump_target_norm: float = 1.0,
        cell_entry_enabled: bool = False,
        cell_entry_grid: dict[str, Any] | None = None,
        cell_entry_low_productivity_payload_gain_kg: float = 100.0,
        dig_cut_planner: dict[str, Any] | None = None,
        return_target_planner: dict[str, Any] | None = None,
        pre_dig_align: dict[str, Any] | None = None,
    ) -> None:
        self.approach_dump_policy = approach_dump_policy
        self.dump_release_policy = dump_release_policy
        self.approach_ready_min_bucket_mass_kg = float(approach_ready_min_bucket_mass_kg)
        self.approach_ready_max_horizontal_distance_m = (
            None
            if approach_ready_max_horizontal_distance_m is None
            else float(approach_ready_max_horizontal_distance_m)
        )
        self.approach_ready_min_height_above_rim_m = float(
            approach_ready_min_height_above_rim_m
        )
        self.approach_ready_require_clearance = bool(approach_ready_require_clearance)
        self.approach_ready_hold_steps = max(1, int(approach_ready_hold_steps))
        self._approach_ready_hold_count = 0
        self._dump_release_ready_hold_count = 0
        super().__init__(
            dig_policy=dig_policy,
            first_dig_policy=first_dig_policy,
            carry_policy=carry_policy,
            dump_policy=dump_release_policy,
            return_policy=return_policy,
            boundary_detector=boundary_detector,
            bootstrap_policy=bootstrap_policy,
            bootstrap_end_mode=bootstrap_end_mode,
            bootstrap_end_min_bucket_mass_kg=bootstrap_end_min_bucket_mass_kg,
            bootstrap_end_min_distance_to_dig_area_m=(
                bootstrap_end_min_distance_to_dig_area_m
            ),
            dig_to_carry_min_bucket_mass_kg=dig_to_carry_min_bucket_mass_kg,
            dig_to_carry_min_distance_to_dig_area_m=(
                dig_to_carry_min_distance_to_dig_area_m
            ),
            dig_to_carry_target_bucket_mass_kg=dig_to_carry_target_bucket_mass_kg,
            dig_to_carry_mass_plateau_enabled=dig_to_carry_mass_plateau_enabled,
            dig_to_carry_mass_plateau_min_bucket_mass_kg=(
                dig_to_carry_mass_plateau_min_bucket_mass_kg
            ),
            dig_to_carry_mass_plateau_epsilon_kg=(
                dig_to_carry_mass_plateau_epsilon_kg
            ),
            dig_to_carry_mass_plateau_hold_steps=(
                dig_to_carry_mass_plateau_hold_steps
            ),
            dig_to_carry_mass_plateau_min_steps=dig_to_carry_mass_plateau_min_steps,
            dig_bad_replan_enabled=dig_bad_replan_enabled,
            dig_bad_replan_max_steps=dig_bad_replan_max_steps,
            dig_bad_replan_min_bucket_mass_kg=dig_bad_replan_min_bucket_mass_kg,
            dig_exit_guard_enabled=dig_exit_guard_enabled,
            dig_exit_guard_min_steps=dig_exit_guard_min_steps,
            dig_exit_guard_overshoot_m=dig_exit_guard_overshoot_m,
            dig_exit_guard_min_bucket_mass_kg=dig_exit_guard_min_bucket_mass_kg,
            dig_failed_replan_next_skill=dig_failed_replan_next_skill,
            dump_ready_min_bucket_mass_kg=dump_release_ready_min_bucket_mass_kg,
            dump_ready_min_height_above_rim_m=(
                dump_release_ready_min_height_above_rim_m
            ),
            dump_ready_require_over_footprint=(
                dump_release_ready_require_over_footprint
            ),
            dump_ready_require_clearance=dump_release_ready_require_clearance,
            dump_ready_max_horizontal_distance_m=(
                dump_release_ready_max_horizontal_distance_m
            ),
            dump_ready_position_mode=dump_release_ready_position_mode,
            dump_ready_max_dump_area_footprint_outside_distance_m=(
                dump_release_ready_max_dump_area_footprint_outside_distance_m
            ),
            dump_ready_min_dump_area_relative_x_m=(
                dump_release_ready_min_dump_area_relative_x_m
            ),
            dump_ready_max_dump_area_relative_x_m=(
                dump_release_ready_max_dump_area_relative_x_m
            ),
            dump_ready_min_dump_area_relative_z_m=(
                dump_release_ready_min_dump_area_relative_z_m
            ),
            dump_ready_max_dump_area_relative_z_m=(
                dump_release_ready_max_dump_area_relative_z_m
            ),
            dump_ready_hold_steps=dump_release_ready_hold_steps,
            dump_ready_near_window_enabled=dump_ready_near_window_enabled,
            dump_ready_near_window_x_tolerance_m=(
                dump_ready_near_window_x_tolerance_m
            ),
            dump_ready_near_window_z_tolerance_m=(
                dump_ready_near_window_z_tolerance_m
            ),
            dump_ready_near_window_outside_tolerance_m=(
                dump_ready_near_window_outside_tolerance_m
            ),
            dump_ready_near_window_require_over_footprint=(
                dump_ready_near_window_require_over_footprint
            ),
            dump_done_max_bucket_mass_kg=dump_done_max_bucket_mass_kg,
            dump_done_min_deposit_delta_kg=dump_done_min_deposit_delta_kg,
            dump_done_hold_steps=dump_done_hold_steps,
            dump_done_use_boundary_event=dump_done_use_boundary_event,
            return_to_dig_shallow_guard_enabled=(
                return_to_dig_shallow_guard_enabled
            ),
            return_to_dig_max_bucket_mass_kg=return_to_dig_max_bucket_mass_kg,
            return_to_dig_touch_tolerance_m=return_to_dig_touch_tolerance_m,
            return_to_dig_min_depth_m=return_to_dig_min_depth_m,
            return_to_dig_max_depth_m=return_to_dig_max_depth_m,
            return_to_dig_max_entry_error_m=return_to_dig_max_entry_error_m,
            return_to_dig_start_envelope_gate_enabled=(
                return_to_dig_start_envelope_gate_enabled
            ),
            return_to_dig_start_envelope_spatial_tolerance=(
                return_to_dig_start_envelope_spatial_tolerance
            ),
            return_to_dig_start_envelope_depth_tolerance_m=(
                return_to_dig_start_envelope_depth_tolerance_m
            ),
            return_to_dig_start_envelope_local_depth_tolerance_m=(
                return_to_dig_start_envelope_local_depth_tolerance_m
            ),
            return_to_dig_start_envelope_plane_depth_tolerance_m=(
                return_to_dig_start_envelope_plane_depth_tolerance_m
            ),
            return_to_dig_start_envelope_plane_depth_mode=(
                return_to_dig_start_envelope_plane_depth_mode
            ),
            return_to_dig_start_envelope_qpos_tolerance=(
                return_to_dig_start_envelope_qpos_tolerance
            ),
            return_to_dig_start_envelope_require_contact=(
                return_to_dig_start_envelope_require_contact
            ),
            return_to_dig_start_envelope_direct_handoff_enabled=(
                return_to_dig_start_envelope_direct_handoff_enabled
            ),
            return_max_steps=return_max_steps,
            action_dim=action_dim,
            primitive_checkpoint_paths=primitive_checkpoint_paths,
            goal_sequence=goal_sequence,
            goal_scenario_id=goal_scenario_id,
            goal_depth_norm=goal_depth_norm,
            goal_dump_target_norm=goal_dump_target_norm,
            cell_entry_enabled=cell_entry_enabled,
            cell_entry_grid=cell_entry_grid,
            cell_entry_low_productivity_payload_gain_kg=(
                cell_entry_low_productivity_payload_gain_kg
            ),
            dig_cut_planner=dig_cut_planner,
            return_target_planner=return_target_planner,
            pre_dig_align=pre_dig_align,
        )
        self.dump_release_ready_hold_steps = self.dump_ready_hold_steps

    def reset(self) -> None:
        self._approach_ready_hold_count = 0
        self._dump_release_ready_hold_count = 0
        super().reset()
        self._approach_ready_hold_count = 0
        self._dump_release_ready_hold_count = 0
        self._debug_state = self._make_debug_state(
            transition_timeout=False,
            transition_completed=False,
        )

    def _maybe_switch_skill(self, *, obs: dict, boundary_event: Any | None) -> None:
        if self._skill_name == BOOTSTRAP_SKILL_NAME:
            if self._should_end_bootstrap(obs=obs, boundary_event=boundary_event):
                next_skill = (
                    "dig"
                    if self.bootstrap_end_mode
                    in {"first_qualified_dig_start", "scripted_qpos"}
                    else "carry"
                )
                self._set_skill(next_skill, f"bootstrap_to_{next_skill}")
            return

        if self._skill_name == "dig":
            if self._dig_to_carry_ready(obs=obs, boundary_event=boundary_event):
                self._set_skill("carry", "dig_to_carry_loaded")
            return

        if self._skill_name == "carry":
            if self._approach_ready(obs):
                self._approach_ready_hold_count += 1
            else:
                self._approach_ready_hold_count = 0
            if self._approach_ready_hold_count >= self.approach_ready_hold_steps:
                self._set_skill("approach_dump", "carry_to_approach_dump_region_ready")
            return

        if self._skill_name == "approach_dump":
            if self._dump_ready(obs):
                self._dump_release_ready_hold_count += 1
            else:
                self._dump_release_ready_hold_count = 0
            if self._dump_release_ready_hold_count >= self.dump_ready_hold_steps:
                self._dump_start_deposited_mass_kg = self._deposited_mass(obs)
                self._set_skill("dump_release", "approach_dump_to_dump_release_ready")
            return

        if self._skill_name == "dump_release":
            if (
                self.dump_done_use_boundary_event
                and boundary_event is not None
                and bool(getattr(boundary_event, "dump_end", False))
            ):
                self._set_skill("return", "dump_release_to_return_dump_end")
                return
            if self._dump_done(obs):
                self._dump_done_hold_count += 1
            else:
                self._dump_done_hold_count = 0
            if self._dump_done_hold_count >= self.dump_done_hold_steps:
                self._set_skill("return", "dump_release_to_return_mass_low")
            return

        if self._skill_name == "return":
            if boundary_event is not None and bool(
                getattr(boundary_event, "qualified_dig_start", False)
            ):
                self._completed_transition_count += 1
                self._cycle_index += 1
                self._set_skill("dig", "return_to_dig_qualified_dig_start")
                return
            if self._return_to_dig_direct_handoff_ready(obs):
                self._completed_transition_count += 1
                self._cycle_index += 1
                self._set_skill("dig", "return_to_dig_start_envelope_ready")
                return
            if self._return_to_dig_shallow_guard_ready(
                obs=obs,
                boundary_event=boundary_event,
            ):
                self._completed_transition_count += 1
                self._cycle_index += 1
                self._set_skill("dig", "return_to_dig_shallow_entry_guard")

    def _set_skill(self, skill_name: str, reason: str) -> None:
        if skill_name == self._skill_name:
            return
        self._skill_name = str(skill_name)
        self._switch_reason = str(reason)
        self._active_policy().reset()
        if skill_name == "carry":
            self._approach_ready_hold_count = 0
        elif skill_name == "approach_dump":
            self._dump_release_ready_hold_count = 0
        elif skill_name == "dump_release":
            self._dump_done_hold_count = 0
        elif skill_name == "return":
            self._return_step_count = 0
        elif skill_name == "dig":
            self._approach_ready_hold_count = 0
            self._dump_release_ready_hold_count = 0
            self._dump_done_hold_count = 0
        if skill_name != "dig":
            self._clear_dig_cut_plan()

    def _approach_ready(self, obs: dict) -> bool:
        return self.dump_lifecycle_gate.approach_ready(
            self._dump_lifecycle_facts(obs),
            self._dump_lifecycle_config(),
        )

    def _active_policy(self) -> Policy:
        if self._skill_name == BOOTSTRAP_SKILL_NAME:
            if self.bootstrap_policy is None:
                raise RuntimeError("bootstrap skill is active but bootstrap_policy is None.")
            return self.bootstrap_policy
        if self._skill_name == "dig":
            if self._first_dig_policy_active():
                if self.first_dig_policy is None:
                    raise RuntimeError("first dig policy is active but missing.")
                return self.first_dig_policy
            return self.dig_policy
        if self._skill_name == "carry":
            return self.carry_policy
        if self._skill_name == "approach_dump":
            return self.approach_dump_policy
        if self._skill_name == "dump_release":
            return self.dump_release_policy
        if self._skill_name == "return":
            return self.return_policy
        raise RuntimeError(f"Unknown primitive skill {self._skill_name!r}.")

    def _all_policies(self) -> list[Policy]:
        policies = [
            self.dig_policy,
            self.carry_policy,
            self.approach_dump_policy,
            self.dump_release_policy,
            self.return_policy,
        ]
        if self.bootstrap_policy is not None:
            policies.append(self.bootstrap_policy)
        if self.first_dig_policy is not None:
            policies.append(self.first_dig_policy)
        return policies

    def _dump_lifecycle_runtime_status_snapshot(
        self,
    ) -> DumpLifecycleRuntimeStatusSnapshot:
        return self.dump_lifecycle_gate.runtime_status_snapshot(
            DumpLifecycleRuntimeStatusState(
                ready_hold_count=int(self._dump_release_ready_hold_count),
                done_hold_count=int(self._dump_done_hold_count),
            )
        )

    def _make_debug_state(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> PrimitivePlannerDebugState:
        dump_status = self._dump_lifecycle_runtime_status_snapshot()
        return build_primitive_debug_state_snapshot_from_runtime(
            config=PrimitiveDebugStateSnapshotConfig(
                skill_ids=PRIMITIVE_SKILL_IDS_5P,
                transition_skill_names=("return",),
                transition_hybrid_mode=HYBRID_MODE_TRANSITION,
                work_hybrid_mode=HYBRID_MODE_WORK,
                primitive_checkpoint_paths=self.primitive_checkpoint_paths,
            ),
            facts=PrimitiveDebugStateSnapshotFacts(
                skill_name=str(self._skill_name),
                skill_switch_reason=str(self._switch_reason),
                first_dig_policy_active=self._first_dig_policy_active(),
                transition_timeout=bool(transition_timeout),
                transition_completed=bool(transition_completed),
                completed_transition_count=int(self._completed_transition_count),
                transition_timeout_count=int(self._transition_timeout_count),
                dump_ready_hold_count=int(dump_status.ready_hold_count),
                dump_done_hold_count=int(dump_status.done_hold_count),
                primitive_cycle_index=int(self._cycle_index),
                approach_ready_hold_count=int(self._approach_ready_hold_count),
                dump_release_ready_hold_count=int(dump_status.ready_hold_count),
            ),
        )
