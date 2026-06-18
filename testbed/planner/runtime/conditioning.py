"""Typed policy-observation conditioning state for planner runtime."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from testbed.planner.dig_cut_plan import DigCutRuntimeState
from testbed.planner.dig_depth_profile import DigDepthProfileRuntimeState
from testbed.planner.policy_observation import PolicyObservationAssembly
from testbed.planner.return_target_plan import ReturnTargetConditioningRuntimeState
from testbed.planner.return_target_plan import ReturnTargetPlanService


@dataclass(frozen=True, slots=True)
class PlannerConditioningState:
    """Planner-owned token runtime state used before low-level ACT dispatch."""

    cell_entry_token_injected: bool = False
    dig_cut: DigCutRuntimeState | None = None
    dig_depth_profile: DigDepthProfileRuntimeState | None = None
    return_target: ReturnTargetConditioningRuntimeState | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cell_entry_token_injected",
            bool(self.cell_entry_token_injected),
        )
        object.__setattr__(
            self,
            "dig_cut",
            self.dig_cut or _default_dig_cut_state(),
        )
        object.__setattr__(
            self,
            "dig_depth_profile",
            self.dig_depth_profile or _default_dig_depth_profile_state(),
        )
        object.__setattr__(
            self,
            "return_target",
            self.return_target or _default_return_target_state(),
        )

    def with_cell_entry_token_injected(
        self,
        token_injected: object,
    ) -> PlannerConditioningState:
        """Return a snapshot with updated cell-entry injection state."""

        return replace(self, cell_entry_token_injected=bool(token_injected))

    def with_dig_cut_runtime_state(
        self,
        state: DigCutRuntimeState,
    ) -> PlannerConditioningState:
        """Return a snapshot with updated dig-cut token state."""

        return replace(self, dig_cut=_copy_dig_cut_state(state))

    def with_dig_cut_updates(self, **updates: object) -> PlannerConditioningState:
        """Return a snapshot with selected dig-cut token fields updated."""

        return replace(self, dig_cut=replace(self.dig_cut, **updates))

    def with_dig_depth_profile_runtime_state(
        self,
        state: DigDepthProfileRuntimeState,
    ) -> PlannerConditioningState:
        """Return a snapshot with updated dig-depth-profile token state."""

        return replace(self, dig_depth_profile=_copy_dig_depth_profile_state(state))

    def with_dig_depth_profile_updates(
        self,
        **updates: object,
    ) -> PlannerConditioningState:
        """Return a snapshot with selected dig-depth-profile fields updated."""

        return replace(
            self,
            dig_depth_profile=replace(self.dig_depth_profile, **updates),
        )

    def with_return_target_conditioning_state(
        self,
        state: ReturnTargetConditioningRuntimeState,
    ) -> PlannerConditioningState:
        """Return a snapshot with updated return-target conditioning state."""

        return replace(self, return_target=_copy_return_target_state(state))

    def with_return_target_updates(
        self,
        **updates: object,
    ) -> PlannerConditioningState:
        """Return a snapshot with selected return-target fields updated."""

        return replace(
            self,
            return_target=replace(self.return_target, **updates),
        )

    def with_policy_observation_assembly(
        self,
        assembly: PolicyObservationAssembly,
    ) -> PlannerConditioningState:
        """Return a snapshot after policy-observation assembly injection flags."""

        return PlannerConditioningState(
            cell_entry_token_injected=assembly.cell_entry_token_injected,
            dig_cut=replace(
                self.dig_cut,
                token_injected=assembly.dig_cut_token_injected,
            ),
            dig_depth_profile=replace(
                self.dig_depth_profile,
                token_injected=assembly.dig_depth_profile_token_injected,
            ),
            return_target=replace(
                self.return_target,
                target_token_injected=assembly.return_target_token_injected,
                relocate_token_injected=assembly.return_relocate_token_injected,
                start_envelope_token_injected=(
                    assembly.return_start_envelope_token_injected
                ),
            ),
        )


def _copy_dig_cut_state(state: DigCutRuntimeState | None) -> DigCutRuntimeState:
    state = state or _default_dig_cut_state()
    return DigCutRuntimeState(
        tokens=np.asarray(state.tokens, dtype=np.float32).copy(),
        token_injected=bool(state.token_injected),
        planned_cycle_id=int(state.planned_cycle_id),
        token_source=str(state.token_source),
        fallback_reason=str(state.fallback_reason),
        token_in_prior_p10_p90=bool(state.token_in_prior_p10_p90),
    )


def _copy_dig_depth_profile_state(
    state: DigDepthProfileRuntimeState | None,
) -> DigDepthProfileRuntimeState:
    state = state or _default_dig_depth_profile_state()
    return DigDepthProfileRuntimeState(
        tokens=np.asarray(state.tokens, dtype=np.float32).copy(),
        token_injected=bool(state.token_injected),
        token_source=str(state.token_source),
        fallback_reason=str(state.fallback_reason),
    )


def _copy_return_target_state(
    state: ReturnTargetConditioningRuntimeState | None,
) -> ReturnTargetConditioningRuntimeState:
    state = state or _default_return_target_state()
    return ReturnTargetConditioningRuntimeState(
        target_tokens=np.asarray(state.target_tokens, dtype=np.float32).copy(),
        target_token_injected=bool(state.target_token_injected),
        target_token_source=str(state.target_token_source),
        target_fallback_reason=str(state.target_fallback_reason),
        relocate_tokens=np.asarray(state.relocate_tokens, dtype=np.float32).copy(),
        relocate_token_injected=bool(state.relocate_token_injected),
        start_envelope_tokens=np.asarray(
            state.start_envelope_tokens,
            dtype=np.float32,
        ).copy(),
        start_envelope_token_injected=bool(state.start_envelope_token_injected),
        start_envelope_token_source=str(state.start_envelope_token_source),
        start_envelope_use_prior_spatial_bounds=bool(
            state.start_envelope_use_prior_spatial_bounds,
        ),
        start_envelope_use_prior_qpos_bounds=bool(
            state.start_envelope_use_prior_qpos_bounds,
        ),
        planned_cycle_id=int(state.planned_cycle_id),
        pending_dig_cut_cycle_id=int(state.pending_dig_cut_cycle_id),
        pending_dig_cut_corridor_id=int(state.pending_dig_cut_corridor_id),
        pending_dig_cut_raw_fields=_copy_optional_mapping(
            state.pending_dig_cut_raw_fields
        ),
        pending_dig_cut_tokens=_copy_optional_float_array(
            state.pending_dig_cut_tokens
        ),
        pending_dig_depth_profile_tokens=_copy_optional_float_array(
            state.pending_dig_depth_profile_tokens
        ),
        pending_dig_state_exemplar_ids=tuple(state.pending_dig_state_exemplar_ids),
        pending_dig_state_exemplar_distance=float(
            state.pending_dig_state_exemplar_distance,
        ),
    )


def _default_dig_cut_state() -> DigCutRuntimeState:
    from testbed.planner.dig_cut_plan import DigCutPlanService

    return DigCutPlanService.initial_runtime_state()


def _default_dig_depth_profile_state() -> DigDepthProfileRuntimeState:
    from testbed.planner.dig_depth_profile import DigDepthProfileService

    return DigDepthProfileService.initial_runtime_state()


def _default_return_target_state() -> ReturnTargetConditioningRuntimeState:
    return ReturnTargetPlanService.initial_conditioning_state()


def _copy_optional_mapping(
    values: dict[str, float | int] | None,
) -> dict[str, float | int] | None:
    if values is None:
        return None
    return dict(values)


def _copy_optional_float_array(values: Any | None) -> np.ndarray | None:
    if values is None:
        return None
    return np.asarray(values, dtype=np.float32).copy()
