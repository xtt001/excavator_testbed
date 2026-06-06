"""Return-target dig-cut build result projection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReturnTargetDigCutBuildResultConfig:
    source_prefix: str


@dataclass(frozen=True)
class ReturnTargetDigCutBuildContext:
    source_prefix: str
    builder_kind: str
    planner_mode: str


@dataclass(frozen=True)
class ReturnTargetDigCutBuildCallbacks:
    conservative_pose_plan: Callable[[], Any]
    operator_prior_parts: Callable[
        [],
        tuple[Any, dict[str, float | int], object, object],
    ]
    coverage_plan: Callable[[], tuple[Any, int]]


@dataclass(frozen=True)
class ReturnTargetDigCutBuildFacts:
    token: Any
    raw_fields: dict[str, float | int]
    source_suffix: str
    fallback_reason: str = ""
    corridor_id: int = -1


@dataclass(frozen=True)
class ReturnTargetDigCutBuildResult:
    token: Any
    raw_fields: dict[str, float | int]
    source: str
    fallback_reason: str
    corridor_id: int

    def legacy_tuple(self) -> tuple[Any, dict[str, float | int], str, str, int]:
        return (
            self.token,
            self.raw_fields,
            self.source,
            self.fallback_reason,
            self.corridor_id,
        )


class ReturnTargetDigCutBuildService:
    """Project return-target dig-cut builder outputs into legacy payloads."""

    @staticmethod
    def context(
        *,
        source_prefix: object,
        builder_kind: object,
        planner_mode: object,
    ) -> ReturnTargetDigCutBuildContext:
        return ReturnTargetDigCutBuildContext(
            source_prefix=str(source_prefix),
            builder_kind=str(builder_kind),
            planner_mode=str(planner_mode),
        )

    @staticmethod
    def result(
        *,
        config: ReturnTargetDigCutBuildResultConfig,
        facts: ReturnTargetDigCutBuildFacts,
    ) -> ReturnTargetDigCutBuildResult:
        return ReturnTargetDigCutBuildResult(
            token=facts.token,
            raw_fields=facts.raw_fields,
            source=f"{config.source_prefix}_{facts.source_suffix}",
            fallback_reason=str(facts.fallback_reason),
            corridor_id=int(facts.corridor_id),
        )

    @staticmethod
    def result_from_parts(
        context: ReturnTargetDigCutBuildContext,
        *,
        token: Any,
        raw_fields: dict[str, float | int],
        source_suffix: object,
        fallback_reason: object = "",
        corridor_id: object = -1,
    ) -> ReturnTargetDigCutBuildResult:
        return ReturnTargetDigCutBuildService.result(
            config=ReturnTargetDigCutBuildResultConfig(
                source_prefix=context.source_prefix
            ),
            facts=ReturnTargetDigCutBuildFacts(
                token=token,
                raw_fields=raw_fields,
                source_suffix=str(source_suffix),
                fallback_reason=str(fallback_reason),
                corridor_id=int(corridor_id),
            ),
        )

    @staticmethod
    def result_from_plan(
        context: ReturnTargetDigCutBuildContext,
        plan: Any,
        *,
        corridor_id: object = -1,
    ) -> ReturnTargetDigCutBuildResult:
        return ReturnTargetDigCutBuildService.result_from_parts(
            context,
            token=plan.token,
            raw_fields=plan.raw_fields,
            source_suffix=plan.source,
            fallback_reason=plan.fallback_reason,
            corridor_id=corridor_id,
        )

    @staticmethod
    def result_from_callbacks(
        context: ReturnTargetDigCutBuildContext,
        callbacks: ReturnTargetDigCutBuildCallbacks,
    ) -> ReturnTargetDigCutBuildResult:
        builder_kind = str(context.builder_kind)
        if builder_kind == "conservative_pose":
            return ReturnTargetDigCutBuildService.result_from_plan(
                context,
                callbacks.conservative_pose_plan(),
                corridor_id=-1,
            )
        if builder_kind == "operator_prior":
            token, raw_fields, source, fallback_reason = (
                callbacks.operator_prior_parts()
            )
            return ReturnTargetDigCutBuildService.result_from_parts(
                context,
                token=token,
                raw_fields=raw_fields,
                source_suffix=source,
                fallback_reason=fallback_reason,
                corridor_id=-1,
            )
        if builder_kind == "operator_prior_coverage":
            plan, corridor_id = callbacks.coverage_plan()
            return ReturnTargetDigCutBuildService.result_from_plan(
                context,
                plan,
                corridor_id=corridor_id,
            )
        raise ValueError(
            f"Unsupported dig_cut_planner mode {context.planner_mode!r}."
        )
