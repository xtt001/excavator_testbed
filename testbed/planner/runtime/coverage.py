"""Coverage-specific runtime-effect projections."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol

from testbed.planner.runtime.contracts import PlannerRuntimeEffect

if TYPE_CHECKING:
    from testbed.planner.dig_coverage.models import CoverageActionResult

REQUEST_COVERAGE_TERMINAL_STOP_EFFECT = "request_coverage_terminal_stop"


class CoverageTerminalStopRequester(Protocol):
    def __call__(self, reason: str, *, replace: bool = False) -> None:
        """Apply a coverage terminal-stop request through an adapter."""


def project_coverage_action_result(
    result: "CoverageActionResult",
) -> tuple[PlannerRuntimeEffect, ...]:
    """Project deferred coverage side effects into backend-neutral effects."""

    reason = str(result.terminal_stop_reason or "")
    if not reason:
        return ()
    return (
        PlannerRuntimeEffect(
            REQUEST_COVERAGE_TERMINAL_STOP_EFFECT,
            {
                "reason": reason,
                "replace": bool(result.terminal_stop_replace),
            },
        ),
    )


def apply_coverage_runtime_effects(
    effects: Iterable[PlannerRuntimeEffect],
    *,
    request_coverage_terminal_stop: CoverageTerminalStopRequester,
) -> None:
    """Apply coverage runtime effects through adapter-owned side effects."""

    for effect in effects:
        if effect.effect_type != REQUEST_COVERAGE_TERMINAL_STOP_EFFECT:
            raise ValueError(
                f"Unsupported coverage runtime effect {effect.effect_type!r}."
            )
        request_coverage_terminal_stop(
            str(effect.payload["reason"]),
            replace=bool(effect.payload.get("replace", False)),
        )


__all__ = [
    "REQUEST_COVERAGE_TERMINAL_STOP_EFFECT",
    "CoverageTerminalStopRequester",
    "apply_coverage_runtime_effects",
    "project_coverage_action_result",
]
