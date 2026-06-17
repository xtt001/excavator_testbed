from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

import testbed.planner.dig_coverage.facade as coverage_facade
from testbed.planner.dig_coverage.facade import DigCoverageMixin
from testbed.planner.dig_coverage.models import CoverageActionResult
from testbed.planner.runtime import PlannerRuntimeEffect
from testbed.planner.runtime.coverage import (
    apply_coverage_runtime_effects,
    project_coverage_action_result,
)


def test_runtime_coverage_module_imports_without_dig_coverage_package_cycle() -> None:
    script = textwrap.dedent(
        """
        from testbed.planner.runtime.coverage import (
            apply_coverage_runtime_effects,
            project_coverage_action_result,
        )
        print(apply_coverage_runtime_effects.__name__)
        print(project_coverage_action_result.__name__)
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.splitlines() == [
        "apply_coverage_runtime_effects",
        "project_coverage_action_result",
    ]


def test_coverage_action_without_terminal_stop_has_no_runtime_effects() -> None:
    result = CoverageActionResult()

    assert project_coverage_action_result(result) == ()


def test_coverage_terminal_stop_action_projects_to_runtime_effect() -> None:
    result = CoverageActionResult(
        terminal_stop_reason="dig_area_depleted",
        terminal_stop_replace=True,
    )

    effects = project_coverage_action_result(result)

    assert len(effects) == 1
    effect = effects[0]
    assert effect.effect_type == "request_coverage_terminal_stop"
    assert dict(effect.payload) == {
        "reason": "dig_area_depleted",
        "replace": True,
    }


def test_coverage_runtime_effect_payload_preserves_false_replace_flag() -> None:
    result = CoverageActionResult(
        terminal_stop_reason="low_productivity_consecutive",
        terminal_stop_replace=False,
    )

    effects = project_coverage_action_result(result)

    assert [effect.effect_type for effect in effects] == [
        "request_coverage_terminal_stop"
    ]
    assert dict(effects[0].payload) == {
        "reason": "low_productivity_consecutive",
        "replace": False,
    }


def test_apply_coverage_runtime_effects_requests_terminal_stop_in_order() -> None:
    calls: list[tuple[str, bool]] = []
    effects = (
        PlannerRuntimeEffect(
            "request_coverage_terminal_stop",
            {"reason": "first", "replace": False},
        ),
        PlannerRuntimeEffect(
            "request_coverage_terminal_stop",
            {"reason": "second", "replace": True},
        ),
    )

    apply_coverage_runtime_effects(
        effects,
        request_coverage_terminal_stop=lambda reason, *, replace=False: calls.append(
            (reason, bool(replace))
        ),
    )

    assert calls == [("first", False), ("second", True)]


def test_dig_coverage_mixin_applies_action_result_via_runtime_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _CoverageActionResultAdapter()
    result = CoverageActionResult(
        terminal_stop_reason="ignored_by_projection_test",
        terminal_stop_replace=True,
    )
    projected = (
        PlannerRuntimeEffect(
            "request_coverage_terminal_stop",
            {"reason": "projected_reason", "replace": False},
        ),
    )
    calls: list[tuple[str, object]] = []

    def project(applied_result: CoverageActionResult):
        calls.append(("project", applied_result))
        return projected

    def apply_effects(effects, *, request_coverage_terminal_stop):
        calls.append(("apply", effects))
        request_coverage_terminal_stop("projected_reason", replace=False)

    monkeypatch.setattr(
        coverage_facade,
        "project_coverage_action_result",
        project,
        raising=False,
    )
    monkeypatch.setattr(
        coverage_facade,
        "apply_coverage_runtime_effects",
        apply_effects,
        raising=False,
    )

    adapter._apply_coverage_action_result(result)

    assert calls == [("project", result), ("apply", projected)]
    assert adapter.terminal_stop_requests == [("projected_reason", False)]


class _CoverageActionResultAdapter(DigCoverageMixin):
    def __init__(self) -> None:
        self.terminal_stop_requests: list[tuple[str, bool]] = []

    def _request_coverage_terminal_stop(
        self,
        reason: str,
        *,
        replace: bool = False,
    ) -> None:
        self.terminal_stop_requests.append((reason, bool(replace)))
