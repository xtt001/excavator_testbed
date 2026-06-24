"""Coverage report and decision-event composition runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.coverage.config import PrimitiveCoverageStaticConfig
from testbed.planner.primitive.coverage.selection import (
    CoverageCorridorState,
    CoverageSelectionService,
)
from testbed.planner.primitive.coverage.reports import (
    CoverageBucketSnapshot,
    CoverageReportConfig,
    CoverageReportService,
    CoverageReportState,
    CoverageSummaryReportStatus,
    CoverageTraceReportStatus,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState


@dataclass(frozen=True)
class PrimitiveCoverageReportRuntimePorts:
    """Typed dependencies for coverage report and decision-event assembly."""

    state: CoverageRuntimeState
    static_config: PrimitiveCoverageStaticConfig
    cycle_index: Callable[[], int]
    skill_name: Callable[[], str]
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]
    selection_service: Callable[[], CoverageSelectionService]


@dataclass(frozen=True)
class PrimitiveCoverageReportRuntime:
    """Own coverage report config/state/event composition."""

    ports: PrimitiveCoverageReportRuntimePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveCoverageReportRuntimePorts,
    ) -> "PrimitiveCoverageReportRuntime":
        return cls(ports=ports)

    @staticmethod
    def report_service() -> CoverageReportService:
        return CoverageReportService()

    def report_config(self) -> CoverageReportConfig:
        return self.ports.static_config.report_config()

    def report_state(self) -> CoverageReportState:
        state = self.ports.state
        return CoverageReportState(
            cycle_index=int(self.ports.cycle_index()),
            skill_name=str(self.ports.skill_name()),
            active_corridor_id=int(state.coverage_active_corridor_id),
            last_selected_corridor_id=int(state.coverage_last_selected_corridor_id),
            last_selected_cell_id=int(
                self.corridor_cell_id_by_id(state.coverage_last_selected_corridor_id)
            ),
            last_selected_row_id=int(
                self.corridor_row_id_by_id(state.coverage_last_selected_corridor_id)
            ),
            depleted_count=int(self.depleted_count()),
            pass_index=int(state.coverage_pass_index),
            global_low_productivity_streak=int(
                state.coverage_global_low_productivity_streak
            ),
            terminal_stop_requested=bool(state.coverage_terminal_stop_requested),
            terminal_stop_reason=str(state.coverage_terminal_stop_reason),
        )

    def bucket_snapshot(self, obs: dict[str, Any]) -> CoverageBucketSnapshot:
        return self.report_service().bucket_snapshot(self.ports.observation_facts(obs))

    def record_decision_event(
        self,
        event: str,
        *,
        obs: dict[str, Any] | None = None,
        corridor: CoverageCorridorState | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.ports.state.coverage_decision_trace.append(
            self.report_service().decision_event(
                str(event),
                state=self.report_state(),
                corridor=None if corridor is None else self.corridor_to_debug(corridor),
                bucket=None if obs is None else self.bucket_snapshot(obs),
                extra=dict(extra or {}),
            )
        )

    def debug_fields(self) -> dict[str, Any]:
        return self.report_service().debug_fields_from_state(
            self.ports.state,
            config=self.report_config(),
            selection_service=self.ports.selection_service(),
        )

    def summary_status(self) -> CoverageSummaryReportStatus:
        return self.report_service().summary_status_from_state(
            self.ports.state,
            config=self.report_config(),
        )

    def trace_status(self) -> CoverageTraceReportStatus:
        return self.report_service().trace_status_from_state(
            self.ports.state,
            config=self.report_config(),
            selection_service=self.ports.selection_service(),
        )

    def all_depleted(self) -> bool:
        return self.ports.state.all_depleted()

    def active_corridor(self) -> CoverageCorridorState | None:
        return self.ports.state.active_corridor()

    def corridor_by_id(self, corridor_id: int) -> CoverageCorridorState | None:
        return self.ports.state.corridor_by_id(corridor_id)

    def active_corridor_score(self) -> float:
        corridor = self.active_corridor()
        return float("nan") if corridor is None else float(corridor.score)

    def active_value(self, name: str) -> float:
        corridor = self.active_corridor()
        if corridor is None:
            return float("nan")
        return float(getattr(corridor, name, float("nan")))

    def active_cell_id(self) -> int:
        corridor = self.active_corridor()
        if corridor is None:
            return -1
        return int(self.ports.selection_service().cell_id(corridor))

    def corridor_cell_id_by_id(self, corridor_id: int) -> int:
        corridor = self.corridor_by_id(corridor_id)
        if corridor is None:
            return -1
        return int(self.ports.selection_service().cell_id(corridor))

    def corridor_row_id_by_id(self, corridor_id: int) -> int:
        corridor = self.corridor_by_id(corridor_id)
        if corridor is None:
            return -1
        return int(self.ports.selection_service().corridor_row_id(corridor))

    def depleted_count(self) -> int:
        return self.ports.state.depleted_count()

    def corridor_to_debug(
        self,
        corridor: CoverageCorridorState,
    ) -> dict[str, float | int | str]:
        selection_service = self.ports.selection_service()
        return self.report_service().corridor_to_debug(
            corridor,
            attempt_limit=selection_service.corridor_attempt_limit(corridor),
            cell_confidence=selection_service.cell_confidence(corridor),
        )


__all__ = [
    "PrimitiveCoverageReportRuntime",
    "PrimitiveCoverageReportRuntimePorts",
]
