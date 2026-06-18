"""Coverage completion and rejection state updates for primitive planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive_coverage import (
    CoverageCorridorState,
    CoverageSelectionService,
)


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


__all__ = [
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
