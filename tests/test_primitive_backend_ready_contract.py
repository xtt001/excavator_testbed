from __future__ import annotations

import ast
from importlib import import_module
from pathlib import Path


PRIMITIVE_PACKAGE = Path(__file__).resolve().parents[1] / "testbed/planner/primitive"


def test_backend_ready_production_import_contracts_are_available() -> None:
    decision_context = import_module("testbed.planner.primitive.decision.context")
    decision_contracts = import_module("testbed.planner.primitive.decision.contracts")
    decision_runtime = import_module("testbed.planner.primitive.decision.runtime")
    backend_contracts = import_module(
        "testbed.planner.primitive.decision.backends.legacy_fsm"
    )
    backend_facts = import_module("testbed.planner.primitive.facts.backend")
    decision_facts = import_module("testbed.planner.primitive.facts.decision")
    backend_input = import_module("testbed.planner.primitive.decision.input")
    requested_effects = import_module("testbed.planner.primitive.effects.requested")

    assert decision_context.PrimitiveDecisionContext.__name__ == (
        "PrimitiveDecisionContext"
    )
    assert decision_contracts.PrimitiveDecisionResult.__name__ == (
        "PrimitiveDecisionResult"
    )
    assert decision_contracts.RequestedPlannerEffect.__name__ == (
        "RequestedPlannerEffect"
    )
    assert decision_contracts.SwitchSkillEffect.__name__ == "SwitchSkillEffect"
    assert decision_runtime.PrimitiveDecisionRuntime.__name__ == (
        "PrimitiveDecisionRuntime"
    )
    assert decision_runtime.PrimitiveDecisionRuntimePorts.__name__ == (
        "PrimitiveDecisionRuntimePorts"
    )
    assert backend_contracts.PrimitiveDecisionBackend.__name__ == (
        "PrimitiveDecisionBackend"
    )
    assert backend_contracts.PrimitiveCompatibilityDecisionBackend.__name__ == (
        "PrimitiveCompatibilityDecisionBackend"
    )
    assert backend_contracts.PrimitiveDecisionBackendFactory.__name__ == (
        "PrimitiveDecisionBackendFactory"
    )
    assert backend_facts.PrimitiveBackendFactsSource.__name__ == (
        "PrimitiveBackendFactsSource"
    )
    assert backend_facts.PrimitiveBackendFactsPorts.__name__ == (
        "PrimitiveBackendFactsPorts"
    )
    assert decision_facts.PrimitiveDecisionFacts.__name__ == (
        "PrimitiveDecisionFacts"
    )
    assert backend_input.PrimitiveBackendDecisionInput.__name__ == (
        "PrimitiveBackendDecisionInput"
    )
    assert backend_input.PrimitiveBackendDecisionInputBuilder.__name__ == (
        "PrimitiveBackendDecisionInputBuilder"
    )
    assert requested_effects.RequestedEffectApplier.__name__ == (
        "RequestedEffectApplier"
    )
    assert requested_effects.RequestedEffectApplierPorts.__name__ == (
        "RequestedEffectApplierPorts"
    )


def test_primitive_lane_modules_do_not_depend_on_policy_shell() -> None:
    forbidden_imports = {
        "testbed.policies.hybrid.primitive_planner",
        "testbed.policies.hybrid",
    }
    forbidden_text = (
        "PrimitivePlannerACTPolicy",
        "planner_self",
        "policy_self",
        "blackboard",
        "callback bag",
    )
    offenders: list[str] = []

    for path in sorted(PRIMITIVE_PACKAGE.rglob("*.py")):
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in forbidden_imports:
                    offenders.append(f"{path}:{node.lineno}:{module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_imports:
                        offenders.append(f"{path}:{node.lineno}:{alias.name}")
        for text in forbidden_text:
            if text in source:
                offenders.append(f"{path}:{text}")

    assert offenders == []


def test_backend_design_doc_is_not_a_production_import_api() -> None:
    design_doc = (
        Path(__file__).resolve().parents[1]
        / "docs/planner_scheduling_backend_design.md"
    ).read_text()

    assert "active design guide for future scheduling/decision backends" in design_doc
    assert "Design documents are not production import contracts" in design_doc
