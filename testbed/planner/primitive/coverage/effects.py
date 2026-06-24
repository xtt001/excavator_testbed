"""Coverage completion and rejection state updates for primitive planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from testbed.planner.primitive.coverage.selection import (
    CoverageCorridorState,
    CoverageSelectionService,
)

if TYPE_CHECKING:
    from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
    from testbed.planner.primitive.coverage.state import CoverageRuntimeState
    from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState


@dataclass(frozen=True)
class CoverageUpdateConfig:
    prior_fields: dict[str, Any]
    use_env_removed_depth: bool
    low_productivity_payload_kg: float
    low_productivity_deposit_kg: float
    deplete_after_low_streak: int
    min_remaining_depth_m: float
    belief_depleted_score: float
    belief_gain_scale: float


@dataclass(frozen=True)
class CoverageCompletionFacts:
    payload_gain_kg: float
    effective_deposit_delta_kg: float
    remaining_depth_m: float
    reason: str
    attempt_limit: int
    completed_dump_count: int
    global_low_productivity_streak: int


@dataclass(frozen=True)
class CoverageRejectionFacts:
    payload_gain_kg: float
    effective_deposit_delta_kg: float
    remaining_depth_m: float
    reason: str
    attempt_limit: int
    global_low_productivity_streak: int
    active_state_exemplar_ids: tuple[str, ...]


@dataclass(frozen=True)
class CoverageUpdateResult:
    payload_gain_kg: float
    effective_deposit_delta_kg: float
    remaining_depth_m: float
    final_reason: str
    low_productivity: bool
    completed_dump_count: int
    global_low_productivity_streak: int
    counted_attempt: int
    rejected_state_exemplar_ids: tuple[str, ...] = ()


class CoverageUpdateService:
    """Apply completion and rejection state updates to a coverage corridor."""

    def __init__(self, config: CoverageUpdateConfig) -> None:
        self.config = config

    @staticmethod
    def record_dig_payload(current_payload_gain_kg: float, bucket_mass_kg: float) -> float:
        return max(float(current_payload_gain_kg), float(bucket_mass_kg))

    def complete_dump(
        self,
        corridor: CoverageCorridorState,
        facts: CoverageCompletionFacts,
    ) -> CoverageUpdateResult:
        payload_gain = max(float(facts.payload_gain_kg), 0.0)
        effective_deposit = max(float(facts.effective_deposit_delta_kg), 0.0)
        remaining_depth = float(facts.remaining_depth_m)
        low_productivity = (
            payload_gain < self.config.low_productivity_payload_kg
            or effective_deposit < self.config.low_productivity_deposit_kg
        )
        corridor.attempts += 1
        corridor.last_payload_gain_kg = float(payload_gain)
        corridor.last_effective_deposit_delta_kg = float(effective_deposit)
        corridor.last_remaining_depth_m = float(remaining_depth)
        corridor.last_reason = str(facts.reason)
        self.update_belief(
            corridor,
            payload_gain_kg=payload_gain,
            effective_deposit_delta_kg=effective_deposit,
        )
        completed_dump_count = int(facts.completed_dump_count) + 1

        if low_productivity:
            corridor.low_productivity_streak += 1
            global_low_productivity_streak = (
                int(facts.global_low_productivity_streak) + 1
            )
        else:
            corridor.low_productivity_streak = 0
            global_low_productivity_streak = 0

        if corridor.low_productivity_streak >= self.config.deplete_after_low_streak:
            corridor.depleted = True
            corridor.last_reason = "low_productivity_consecutive"
        remaining_depth_available = bool(
            self.config.use_env_removed_depth
            and np.isfinite(remaining_depth)
            and float(remaining_depth) >= self.config.min_remaining_depth_m
        )
        if corridor.attempts >= int(facts.attempt_limit) and not remaining_depth_available:
            corridor.depleted = True
            corridor.last_reason = "attempt_limit_reached"
        if (
            np.isfinite(remaining_depth)
            and remaining_depth < self.config.min_remaining_depth_m
        ):
            corridor.depleted = True
            corridor.last_reason = "remaining_depth_below_threshold"
        if (
            not self.config.use_env_removed_depth
            and corridor.belief_coverage >= self.config.belief_depleted_score
        ):
            corridor.depleted = True
            corridor.last_reason = "belief_coverage_complete"

        return CoverageUpdateResult(
            payload_gain_kg=float(payload_gain),
            effective_deposit_delta_kg=float(effective_deposit),
            remaining_depth_m=float(remaining_depth),
            final_reason=str(corridor.last_reason),
            low_productivity=bool(low_productivity),
            completed_dump_count=int(completed_dump_count),
            global_low_productivity_streak=int(global_low_productivity_streak),
            counted_attempt=1,
        )

    def reject_corridor(
        self,
        corridor: CoverageCorridorState,
        facts: CoverageRejectionFacts,
    ) -> CoverageUpdateResult:
        payload_gain = max(float(facts.payload_gain_kg), 0.0)
        effective_deposit = max(float(facts.effective_deposit_delta_kg), 0.0)
        remaining_depth = float(facts.remaining_depth_m)
        rejected_ids = tuple(
            exemplar_id for exemplar_id in facts.active_state_exemplar_ids if exemplar_id
        )
        corridor.last_payload_gain_kg = float(payload_gain)
        corridor.last_effective_deposit_delta_kg = float(effective_deposit)
        corridor.last_remaining_depth_m = float(remaining_depth)
        corridor.last_reason = str(facts.reason)

        if str(facts.reason) == "align_entry_gap_timeout":
            return CoverageUpdateResult(
                payload_gain_kg=float(payload_gain),
                effective_deposit_delta_kg=float(effective_deposit),
                remaining_depth_m=float(remaining_depth),
                final_reason=str(corridor.last_reason),
                low_productivity=False,
                completed_dump_count=0,
                global_low_productivity_streak=int(
                    facts.global_low_productivity_streak
                ),
                counted_attempt=0,
                rejected_state_exemplar_ids=rejected_ids,
            )

        corridor.attempts += 1
        corridor.low_productivity_streak += 1
        self.update_belief(
            corridor,
            payload_gain_kg=payload_gain,
            effective_deposit_delta_kg=effective_deposit,
        )
        global_low_productivity_streak = int(facts.global_low_productivity_streak) + 1
        if (
            corridor.low_productivity_streak >= self.config.deplete_after_low_streak
            or corridor.attempts >= int(facts.attempt_limit)
        ):
            corridor.depleted = True
        return CoverageUpdateResult(
            payload_gain_kg=float(payload_gain),
            effective_deposit_delta_kg=float(effective_deposit),
            remaining_depth_m=float(remaining_depth),
            final_reason=str(corridor.last_reason),
            low_productivity=True,
            completed_dump_count=0,
            global_low_productivity_streak=int(global_low_productivity_streak),
            counted_attempt=1,
            rejected_state_exemplar_ids=rejected_ids,
        )

    def update_belief(
        self,
        corridor: CoverageCorridorState,
        *,
        payload_gain_kg: float,
        effective_deposit_delta_kg: float,
    ) -> None:
        if self.config.use_env_removed_depth:
            return
        fields = dict(self.config.prior_fields)
        payload_p50 = max(
            CoverageSelectionService.prior_percentile(fields, "payload_gain_kg", "p50"),
            1.0,
        )
        deposit_p50 = max(
            CoverageSelectionService.prior_percentile(
                fields,
                "effective_deposit_delta_kg",
                "p50",
            ),
            1.0,
        )
        payload_score = float(np.clip(float(payload_gain_kg) / payload_p50, 0.0, 1.5))
        deposit_score = float(
            np.clip(float(effective_deposit_delta_kg) / deposit_p50, 0.0, 1.5)
        )
        gain = self.config.belief_gain_scale * max(payload_score, deposit_score)
        if gain <= 0.0:
            return
        corridor.belief_coverage = float(
            np.clip(float(corridor.belief_coverage) + gain, 0.0, 1.5)
        )


@dataclass(frozen=True)
class CoverageRuntimeConfig:
    multi_pass_enabled: bool
    use_env_removed_depth: bool
    multi_pass_max_passes: int
    multi_pass_min_remaining_depth_m: float


@dataclass(frozen=True)
class CoverageReopenFacts:
    reason: str
    pass_index: int
    terminal_stop_requested: bool
    remaining_depth_by_corridor_id: dict[int, float]


@dataclass(frozen=True)
class CoverageReopenResult:
    reopened: bool
    reason: str
    pass_index: int
    active_corridor_id: int
    global_low_productivity_streak: int
    clear_rejected_state_exemplar_ids: bool
    max_passes: int
    min_remaining_depth_m: float
    reopened_corridors: list[dict[str, float | int | str]]


@dataclass(frozen=True)
class CoverageTerminalFacts:
    reason: str
    replace: bool
    terminal_stop_requested: bool
    terminal_stop_reason: str


@dataclass(frozen=True)
class CoverageTerminalResult:
    terminal_stop_requested: bool
    terminal_stop_reason: str
    record_event: bool


@dataclass(frozen=True)
class CoverageEffectFactService:
    """Project coverage effect facts from focused runtime state and observation facts."""

    state: CoverageRuntimeState
    cycle_state: PrimitiveCycleRuntimeState
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]
    remaining_depth: Callable[[dict[str, Any], CoverageCorridorState], float]
    corridor_attempt_limit: Callable[[CoverageCorridorState], int]

    def mass_in_bucket_kg(self, obs: dict[str, Any]) -> float:
        return float(self.observation_facts(obs).mass_in_bucket_kg)

    def completion_facts(
        self,
        obs: dict[str, Any],
        corridor: CoverageCorridorState,
        *,
        reason: str,
    ) -> CoverageCompletionFacts:
        observation = self.observation_facts(obs)
        return CoverageCompletionFacts(
            payload_gain_kg=max(
                float(self.state.coverage_current_payload_gain_kg),
                0.0,
            ),
            effective_deposit_delta_kg=max(
                0.0,
                float(observation.deposited_mass_in_target_box_kg)
                - float(self.state.coverage_cycle_start_deposit_kg),
            ),
            remaining_depth_m=float(self.remaining_depth(obs, corridor)),
            reason=str(reason),
            attempt_limit=int(self.corridor_attempt_limit(corridor)),
            completed_dump_count=int(self.state.coverage_completed_dump_count),
            global_low_productivity_streak=int(
                self.state.coverage_global_low_productivity_streak
            ),
        )

    def rejection_facts(
        self,
        obs: dict[str, Any],
        corridor: CoverageCorridorState,
        *,
        reason: str,
    ) -> CoverageRejectionFacts:
        observation = self.observation_facts(obs)
        return CoverageRejectionFacts(
            payload_gain_kg=max(
                float(self.state.coverage_current_payload_gain_kg),
                float(self.cycle_state.dig_best_mass_kg),
                float(observation.mass_in_bucket_kg),
                0.0,
            ),
            effective_deposit_delta_kg=max(
                0.0,
                float(observation.deposited_mass_in_target_box_kg)
                - float(self.state.coverage_cycle_start_deposit_kg),
            ),
            remaining_depth_m=float(self.remaining_depth(obs, corridor)),
            reason=str(reason),
            attempt_limit=int(self.corridor_attempt_limit(corridor)),
            global_low_productivity_streak=int(
                self.state.coverage_global_low_productivity_streak
            ),
            active_state_exemplar_ids=tuple(
                str(exemplar_id)
                for exemplar_id in self.state.coverage_active_state_exemplar_ids
            ),
        )

    def reopen_facts(
        self,
        obs: dict[str, Any],
        corridors: list[CoverageCorridorState],
        *,
        reason: str,
    ) -> CoverageReopenFacts:
        return CoverageReopenFacts(
            reason=str(reason),
            pass_index=int(self.state.coverage_pass_index),
            terminal_stop_requested=bool(self.state.coverage_terminal_stop_requested),
            remaining_depth_by_corridor_id={
                int(corridor.corridor_id): float(self.remaining_depth(obs, corridor))
                for corridor in corridors
            },
        )

    def terminal_facts(
        self,
        reason: str,
        *,
        replace: bool,
    ) -> CoverageTerminalFacts:
        return CoverageTerminalFacts(
            reason=str(reason),
            replace=bool(replace),
            terminal_stop_requested=bool(self.state.coverage_terminal_stop_requested),
            terminal_stop_reason=str(self.state.coverage_terminal_stop_reason),
        )


class CoverageRuntimeService:
    """Gate coverage reopen and terminal-stop requests without trace side effects."""

    def __init__(self, config: CoverageRuntimeConfig) -> None:
        self.config = config

    def maybe_reopen_pass(
        self,
        corridors: list[CoverageCorridorState],
        facts: CoverageReopenFacts,
    ) -> CoverageReopenResult:
        threshold = float(self.config.multi_pass_min_remaining_depth_m)
        blocked_result = CoverageReopenResult(
            reopened=False,
            reason=str(facts.reason),
            pass_index=int(facts.pass_index),
            active_corridor_id=-1,
            global_low_productivity_streak=0,
            clear_rejected_state_exemplar_ids=False,
            max_passes=int(self.config.multi_pass_max_passes),
            min_remaining_depth_m=float(threshold),
            reopened_corridors=[],
        )
        if not self.config.multi_pass_enabled:
            return blocked_result
        if facts.terminal_stop_requested:
            return blocked_result
        if not self.config.use_env_removed_depth:
            return blocked_result
        if not corridors or not all(corridor.depleted for corridor in corridors):
            return blocked_result
        if int(facts.pass_index) + 1 >= int(self.config.multi_pass_max_passes):
            return blocked_result

        reopened: list[dict[str, float | int | str]] = []
        for corridor in corridors:
            remaining_depth = float(
                facts.remaining_depth_by_corridor_id.get(
                    int(corridor.corridor_id),
                    float("nan"),
                )
            )
            if not (np.isfinite(remaining_depth) and remaining_depth >= threshold):
                corridor.last_remaining_depth_m = float(remaining_depth)
                continue
            reopened.append(
                {
                    "corridor_id": int(corridor.corridor_id),
                    "cell_id": int(CoverageSelectionService.cell_id(corridor)),
                    "previous_attempts": int(corridor.attempts),
                    "previous_low_productivity_streak": int(
                        corridor.low_productivity_streak
                    ),
                    "previous_reason": str(corridor.last_reason),
                    "remaining_depth_m": float(remaining_depth),
                }
            )
            corridor.depleted = False
            corridor.attempts = 0
            corridor.low_productivity_streak = 0
            corridor.last_remaining_depth_m = float(remaining_depth)
            corridor.last_reason = f"multi_pass_reopened:{facts.reason}"

        if not reopened:
            return blocked_result
        return CoverageReopenResult(
            reopened=True,
            reason=str(facts.reason),
            pass_index=int(facts.pass_index) + 1,
            active_corridor_id=-1,
            global_low_productivity_streak=0,
            clear_rejected_state_exemplar_ids=True,
            max_passes=int(self.config.multi_pass_max_passes),
            min_remaining_depth_m=float(threshold),
            reopened_corridors=reopened,
        )

    @staticmethod
    def request_terminal_stop(
        facts: CoverageTerminalFacts,
    ) -> CoverageTerminalResult:
        if facts.terminal_stop_requested and not facts.replace:
            return CoverageTerminalResult(
                terminal_stop_requested=True,
                terminal_stop_reason=str(facts.terminal_stop_reason),
                record_event=False,
            )
        return CoverageTerminalResult(
            terminal_stop_requested=True,
            terminal_stop_reason=str(facts.reason),
            record_event=True,
        )


@dataclass
class CoverageEffectRuntimePorts:
    """Shell ports used by the coverage effect runtime coordinator."""

    state: CoverageRuntimeState
    cycle_state: PrimitiveCycleRuntimeState
    coverage_mode: Callable[[], str]
    coverage_update_service: Callable[[], CoverageUpdateService]
    coverage_runtime_service: Callable[[], CoverageRuntimeService]
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]
    remaining_depth: Callable[[dict[str, Any], CoverageCorridorState], float]
    corridor_attempt_limit: Callable[[CoverageCorridorState], int]
    record_decision_event: Callable[..., None]
    coverage_global_low_productivity_stop: Callable[[], int]
    coverage_low_productivity_payload_kg: Callable[[], float]
    coverage_low_productivity_deposit_kg: Callable[[], float]


@dataclass(frozen=True)
class CoverageEffectRuntimeCoordinator:
    """Coordinate coverage requested-effect runtime updates and trace events."""

    ports: CoverageEffectRuntimePorts
    coverage_modes: tuple[str, ...] = (
        "operator_prior_coverage",
        "operator_prior_sweep_belief",
    )

    @classmethod
    def from_ports(
        cls,
        ports: CoverageEffectRuntimePorts,
    ) -> "CoverageEffectRuntimeCoordinator":
        return cls(ports=ports)

    def complete_dig(self, obs: dict[str, Any]) -> None:
        if not self._coverage_mode_enabled():
            return
        ports = self.ports
        facts = self._facts()
        payload_gain = ports.coverage_update_service().record_dig_payload(
            float(ports.state.coverage_current_payload_gain_kg),
            facts.mass_in_bucket_kg(obs),
        )
        ports.state.set_current_payload_gain_kg(float(payload_gain))

    def complete_dump(self, obs: dict[str, Any], *, reason: str) -> None:
        if not self._coverage_mode_enabled():
            return
        ports = self.ports
        corridor = ports.state.active_corridor()
        if corridor is None:
            return
        result = ports.coverage_update_service().complete_dump(
            corridor,
            self._facts().completion_facts(obs, corridor, reason=str(reason)),
        )
        ports.state.set_last_payload_gain_kg(float(result.payload_gain_kg))
        ports.state.set_last_effective_deposit_delta_kg(
            float(result.effective_deposit_delta_kg)
        )
        ports.state.set_completed_dump_count(int(result.completed_dump_count))
        ports.state.set_global_low_productivity_streak(
            int(result.global_low_productivity_streak)
        )
        ports.record_decision_event(
            "complete_dump",
            obs=obs,
            corridor=corridor,
            extra={
                "reason": str(reason),
                "final_reason": str(result.final_reason),
                "payload_gain_kg": float(result.payload_gain_kg),
                "effective_deposit_delta_kg": float(
                    result.effective_deposit_delta_kg
                ),
                "remaining_depth_m": float(result.remaining_depth_m),
                "low_productivity": int(result.low_productivity),
                "completed_dump_count": int(result.completed_dump_count),
            },
        )
        if self._all_depleted():
            if not self.maybe_reopen_pass(obs, reason="complete_all_depleted"):
                self.request_terminal_stop("dig_area_depleted")
        elif int(result.global_low_productivity_streak) >= int(
            ports.coverage_global_low_productivity_stop()
        ):
            self.request_terminal_stop("low_productivity_consecutive")
        if (
            result.low_productivity
            and float(result.payload_gain_kg)
            < float(ports.coverage_low_productivity_payload_kg())
            and float(result.effective_deposit_delta_kg)
            >= float(ports.coverage_low_productivity_deposit_kg())
        ):
            self.request_terminal_stop("physics_artifact_suspected")

    def reject_active_corridor(self, obs: dict[str, Any], *, reason: str) -> None:
        if not self._coverage_mode_enabled():
            return
        ports = self.ports
        corridor = ports.state.active_corridor()
        if corridor is None:
            return
        result = ports.coverage_update_service().reject_corridor(
            corridor,
            self._facts().rejection_facts(obs, corridor, reason=str(reason)),
        )
        ports.state.update_rejected_state_exemplar_ids(
            tuple(result.rejected_state_exemplar_ids)
        )
        ports.state.set_last_payload_gain_kg(float(result.payload_gain_kg))
        ports.state.set_last_effective_deposit_delta_kg(
            float(result.effective_deposit_delta_kg)
        )
        ports.state.set_global_low_productivity_streak(
            int(result.global_low_productivity_streak)
        )
        ports.record_decision_event(
            "reject_corridor",
            obs=obs,
            corridor=corridor,
            extra={
                "reason": str(reason),
                "payload_gain_kg": float(result.payload_gain_kg),
                "effective_deposit_delta_kg": float(
                    result.effective_deposit_delta_kg
                ),
                "remaining_depth_m": float(result.remaining_depth_m),
                "counted_attempt": int(result.counted_attempt),
            },
        )
        if not result.counted_attempt:
            return
        if self._all_depleted():
            if not self.maybe_reopen_pass(obs, reason="reject_all_depleted"):
                self.request_terminal_stop("dig_area_depleted")
        elif int(result.global_low_productivity_streak) >= int(
            ports.coverage_global_low_productivity_stop()
        ):
            self.request_terminal_stop("low_productivity_consecutive")

    def maybe_reopen_pass(self, obs: dict[str, Any], *, reason: str) -> bool:
        ports = self.ports
        corridors = ports.state.coverage_corridors
        result = ports.coverage_runtime_service().maybe_reopen_pass(
            corridors,
            self._facts().reopen_facts(obs, corridors, reason=str(reason)),
        )
        if not result.reopened:
            return False
        ports.state.set_coverage_pass_index(int(result.pass_index))
        ports.state.set_active_corridor_id(int(result.active_corridor_id))
        ports.state.set_global_low_productivity_streak(
            int(result.global_low_productivity_streak)
        )
        if result.clear_rejected_state_exemplar_ids:
            ports.state.clear_rejected_state_exemplar_ids()
        ports.record_decision_event(
            "reopen_coverage_pass",
            obs=obs,
            extra={
                "reason": str(result.reason),
                "pass_index": int(result.pass_index),
                "max_passes": int(result.max_passes),
                "min_remaining_depth_m": float(result.min_remaining_depth_m),
                "reopened_corridors": list(result.reopened_corridors),
            },
        )
        return True

    def request_terminal_stop(self, reason: str, *, replace: bool = False) -> None:
        ports = self.ports
        result = ports.coverage_runtime_service().request_terminal_stop(
            self._facts().terminal_facts(str(reason), replace=bool(replace))
        )
        if not result.record_event:
            return
        ports.state.set_terminal_stop(
            requested=bool(result.terminal_stop_requested),
            reason=str(result.terminal_stop_reason),
        )
        ports.record_decision_event(
            "terminal_stop",
            corridor=ports.state.active_corridor(),
            extra={"reason": str(result.terminal_stop_reason)},
        )

    def _coverage_mode_enabled(self) -> bool:
        return str(self.ports.coverage_mode()) in set(self.coverage_modes)

    def _all_depleted(self) -> bool:
        return self.ports.state.all_depleted()

    def _facts(self) -> CoverageEffectFactService:
        ports = self.ports
        return CoverageEffectFactService(
            state=ports.state,
            cycle_state=ports.cycle_state,
            observation_facts=ports.observation_facts,
            remaining_depth=ports.remaining_depth,
            corridor_attempt_limit=ports.corridor_attempt_limit,
        )


__all__ = [
    "CoverageEffectRuntimeCoordinator",
    "CoverageEffectFactService",
    "CoverageEffectRuntimePorts",
    "CoverageCompletionFacts",
    "CoverageReopenFacts",
    "CoverageReopenResult",
    "CoverageRejectionFacts",
    "CoverageRuntimeConfig",
    "CoverageRuntimeService",
    "CoverageTerminalFacts",
    "CoverageTerminalResult",
    "CoverageUpdateConfig",
    "CoverageUpdateResult",
    "CoverageUpdateService",
]
