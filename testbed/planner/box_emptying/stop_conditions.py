"""Central box-emptying success and bounded-stop conditions."""

from __future__ import annotations

from dataclasses import dataclass

from testbed.planner.box_emptying.contracts import TerrainBoxResidual


@dataclass(frozen=True)
class CycleOutcome:
    payload_kg: float
    stable_net_removed_volume_m3: float


@dataclass(frozen=True)
class StopDecision:
    stop: bool
    reason: str = ""
    dump_before_stop: bool = False


class BoxEmptyingStopController:
    def __init__(
        self,
        *,
        empty_fraction: float = 0.05,
        empty_hold_observations: int = 3,
        low_payload_kg: float = 15.0,
        low_progress_m3: float = 0.005,
        ineffective_limit: int = 3,
        max_cycles: int = 120,
    ) -> None:
        self.empty_fraction = float(empty_fraction)
        self.empty_hold_observations = int(empty_hold_observations)
        self.low_payload_kg = float(low_payload_kg)
        self.low_progress_m3 = float(low_progress_m3)
        self.ineffective_limit = int(ineffective_limit)
        self.max_cycles = int(max_cycles)
        self.reset()

    def reset(self) -> None:
        self._empty_hold = 0
        self._ineffective_streak = 0
        self._cycle_count = 0

    def observe_residual(
        self,
        residual: TerrainBoxResidual,
        *,
        payload_kg: float,
    ) -> StopDecision:
        if not residual.valid:
            raise ValueError("terrain residual is invalid")
        # Unity serializes this scalar as float32; treat its representation of
        # the exact configured threshold as inclusive.
        if residual.remaining_fraction <= self.empty_fraction + 1.0e-6:
            self._empty_hold += 1
        else:
            self._empty_hold = 0
        if self._empty_hold < self.empty_hold_observations:
            return StopDecision(stop=False)
        if float(payload_kg) >= self.low_payload_kg:
            return StopDecision(
                stop=False,
                reason="empty_box_dump_pending",
                dump_before_stop=True,
            )
        return StopDecision(
            stop=True,
            reason="empty_box_5pct_three_observations",
        )

    def record_cycle(self, outcome: CycleOutcome) -> StopDecision:
        self._cycle_count += 1
        ineffective = bool(
            float(outcome.payload_kg) < self.low_payload_kg
            and float(outcome.stable_net_removed_volume_m3) < self.low_progress_m3
        )
        self._ineffective_streak = (
            self._ineffective_streak + 1 if ineffective else 0
        )
        if self._ineffective_streak >= self.ineffective_limit:
            return StopDecision(
                stop=True,
                reason="three_consecutive_ineffective",
            )
        if self._cycle_count >= self.max_cycles:
            return StopDecision(stop=True, reason="maximum_120_cycles")
        return StopDecision(stop=False)

    @staticmethod
    def runtime_failure(reason: str) -> StopDecision:
        if reason not in {"wall_contact", "stuck", "timeout"}:
            raise ValueError(f"unsupported runtime failure reason {reason!r}")
        return StopDecision(stop=True, reason=reason)


__all__ = [
    "BoxEmptyingStopController",
    "CycleOutcome",
    "StopDecision",
]
