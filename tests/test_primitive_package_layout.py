from __future__ import annotations

import importlib.util


def test_decision_facts_package_imports_backend_ready_contracts() -> None:
    from testbed.planner.primitive.decision.backends.legacy_capability_provider import (
        PrimitiveFSMCapabilityProvider,
        PrimitiveFSMCapabilityProviderConfig,
    )
    from testbed.planner.primitive.decision.backends.legacy_fsm import (
        LegacyFSMDecisionBackendFactory,
        LegacyFSMDecisionBackendFactoryPorts,
        PrimitiveCompatibilityDecisionBackend,
        PrimitiveDecisionBackend,
        PrimitiveDecisionBackendFactory,
    )
    from testbed.planner.primitive.decision.capabilities import (
        PrimitiveDecisionCapabilities,
        PrimitiveDecisionCompatibilityActions,
    )
    from testbed.planner.primitive.decision.context import PrimitiveDecisionContext
    from testbed.planner.primitive.decision.contracts import (
        PrimitiveDecisionResult,
        SwitchSkillEffect,
    )
    from testbed.planner.primitive.decision.input import (
        PrimitiveBackendDecisionInput,
        PrimitiveBackendDecisionInputBuilder,
    )
    from testbed.planner.primitive.decision.runtime import (
        LEGACY_FSM_DECISION_BACKEND_NAME,
        PrimitiveDecisionRuntime,
        PrimitiveDecisionRuntimePorts,
    )
    from testbed.planner.primitive.facts.backend import (
        PrimitiveBackendFactsSource,
    )
    from testbed.planner.primitive.facts.decision import PrimitiveDecisionFacts

    assert LEGACY_FSM_DECISION_BACKEND_NAME == "legacy_fsm"
    assert PrimitiveDecisionRuntime.__name__ == "PrimitiveDecisionRuntime"
    assert PrimitiveDecisionRuntimePorts.__name__ == "PrimitiveDecisionRuntimePorts"
    assert PrimitiveDecisionBackend.__name__ == "PrimitiveDecisionBackend"
    assert (
        PrimitiveCompatibilityDecisionBackend.__name__
        == "PrimitiveCompatibilityDecisionBackend"
    )
    assert PrimitiveDecisionBackendFactory.__name__ == "PrimitiveDecisionBackendFactory"
    assert (
        LegacyFSMDecisionBackendFactory.__name__
        == "LegacyFSMDecisionBackendFactory"
    )
    assert (
        LegacyFSMDecisionBackendFactoryPorts.__name__
        == "LegacyFSMDecisionBackendFactoryPorts"
    )
    assert (
        PrimitiveFSMCapabilityProvider.__name__
        == "PrimitiveFSMCapabilityProvider"
    )
    assert (
        PrimitiveFSMCapabilityProviderConfig.__name__
        == "PrimitiveFSMCapabilityProviderConfig"
    )
    assert PrimitiveDecisionCapabilities.__name__ == "PrimitiveDecisionCapabilities"
    assert (
        PrimitiveDecisionCompatibilityActions.__name__
        == "PrimitiveDecisionCompatibilityActions"
    )
    assert PrimitiveDecisionContext.__name__ == "PrimitiveDecisionContext"
    assert PrimitiveDecisionResult.__name__ == "PrimitiveDecisionResult"
    assert SwitchSkillEffect.__name__ == "SwitchSkillEffect"
    assert PrimitiveBackendDecisionInput.__name__ == "PrimitiveBackendDecisionInput"
    assert (
        PrimitiveBackendDecisionInputBuilder.__name__
        == "PrimitiveBackendDecisionInputBuilder"
    )
    assert PrimitiveBackendFactsSource.__name__ == "PrimitiveBackendFactsSource"
    assert PrimitiveDecisionFacts.__name__ == "PrimitiveDecisionFacts"


def test_effects_package_imports_requested_and_return_handoff_contracts() -> None:
    from testbed.planner.primitive.effects.requested import (
        PrimitiveRequestedEffectRuntime,
        PrimitiveRequestedEffectRuntimePorts,
        RequestedEffectApplier,
        RequestedEffectApplierPorts,
    )
    from testbed.planner.primitive.effects.return_handoff import (
        ReturnDirectHandoffEffectService,
        ReturnHandoffReadinessConfig,
        ReturnHandoffReadinessService,
    )
    from testbed.planner.primitive.effects.return_handoff_runtime import (
        PrimitiveReturnHandoffRuntime,
        PrimitiveReturnHandoffRuntimePorts,
    )

    assert (
        PrimitiveRequestedEffectRuntime.__name__
        == "PrimitiveRequestedEffectRuntime"
    )
    assert (
        PrimitiveRequestedEffectRuntimePorts.__name__
        == "PrimitiveRequestedEffectRuntimePorts"
    )
    assert RequestedEffectApplier.__name__ == "RequestedEffectApplier"
    assert RequestedEffectApplierPorts.__name__ == "RequestedEffectApplierPorts"
    assert (
        ReturnDirectHandoffEffectService.__name__
        == "ReturnDirectHandoffEffectService"
    )
    assert ReturnHandoffReadinessConfig.__name__ == "ReturnHandoffReadinessConfig"
    assert ReturnHandoffReadinessService.__name__ == "ReturnHandoffReadinessService"
    assert PrimitiveReturnHandoffRuntime.__name__ == "PrimitiveReturnHandoffRuntime"
    assert (
        PrimitiveReturnHandoffRuntimePorts.__name__
        == "PrimitiveReturnHandoffRuntimePorts"
    )


def test_internal_only_effect_root_modules_are_not_importable() -> None:
    def old_root_module(suffix: str) -> str:
        return f"testbed.planner.primitive_{suffix}"

    assert importlib.util.find_spec(old_root_module("effects")) is None
    assert importlib.util.find_spec(old_root_module("return_handoff")) is None
    assert importlib.util.find_spec(old_root_module("return_handoff_runtime")) is None


def test_token_package_imports_token_contracts_and_runtimes() -> None:
    from testbed.planner.primitive.token.dig_planning import (
        PrimitiveDigTokenPlanningPorts,
        PrimitiveDigTokenPlanningService,
    )
    from testbed.planner.primitive.token.observation_runtime import (
        PrimitiveTokenObservationRuntime,
        PrimitiveTokenObservationRuntimePorts,
    )
    from testbed.planner.primitive.token.planning_runtime import (
        PrimitiveTokenPlanningRuntime,
        PrimitiveTokenPlanningRuntimePorts,
    )
    from testbed.planner.primitive.token.return_planning import (
        PrimitiveReturnTokenPlanningPorts,
        PrimitiveReturnTokenPlanningService,
    )
    from testbed.planner.primitive.token.runtime import (
        PrimitiveTokenRuntimeCoordinator,
        PrimitiveTokenRuntimePorts,
        ReturnStartEnvelopeTokenBuilder,
    )
    from testbed.planner.primitive.token.state import (
        PrimitiveTokenReportStatus,
        PrimitiveTokenRuntimeState,
    )
    from testbed.planner.primitive.token.status import TokenStatus
    from testbed.planner.primitive.token.tokens import (
        DigCutTokenPlanner,
        GoalTokenProvider,
        ReturnTargetTokenPlanner,
    )

    assert GoalTokenProvider.__name__ == "GoalTokenProvider"
    assert DigCutTokenPlanner.__name__ == "DigCutTokenPlanner"
    assert ReturnTargetTokenPlanner.__name__ == "ReturnTargetTokenPlanner"
    assert PrimitiveTokenRuntimeState.__name__ == "PrimitiveTokenRuntimeState"
    assert PrimitiveTokenReportStatus.__name__ == "PrimitiveTokenReportStatus"
    assert TokenStatus.__name__ == "TokenStatus"
    assert (
        PrimitiveTokenRuntimeCoordinator.__name__
        == "PrimitiveTokenRuntimeCoordinator"
    )
    assert PrimitiveTokenRuntimePorts.__name__ == "PrimitiveTokenRuntimePorts"
    assert (
        ReturnStartEnvelopeTokenBuilder.__name__
        == "ReturnStartEnvelopeTokenBuilder"
    )
    assert (
        PrimitiveTokenObservationRuntime.__name__
        == "PrimitiveTokenObservationRuntime"
    )
    assert (
        PrimitiveTokenObservationRuntimePorts.__name__
        == "PrimitiveTokenObservationRuntimePorts"
    )
    assert PrimitiveTokenPlanningRuntime.__name__ == "PrimitiveTokenPlanningRuntime"
    assert (
        PrimitiveTokenPlanningRuntimePorts.__name__
        == "PrimitiveTokenPlanningRuntimePorts"
    )
    assert (
        PrimitiveDigTokenPlanningService.__name__
        == "PrimitiveDigTokenPlanningService"
    )
    assert (
        PrimitiveDigTokenPlanningPorts.__name__
        == "PrimitiveDigTokenPlanningPorts"
    )
    assert (
        PrimitiveReturnTokenPlanningService.__name__
        == "PrimitiveReturnTokenPlanningService"
    )
    assert (
        PrimitiveReturnTokenPlanningPorts.__name__
        == "PrimitiveReturnTokenPlanningPorts"
    )


def test_internal_only_token_root_modules_are_not_importable() -> None:
    def old_root_module(suffix: str) -> str:
        return f"testbed.planner.primitive_{suffix}"

    for suffix in (
        "tokens",
        "token_state",
        "token_status",
        "token_runtime",
        "token_observation_runtime",
        "token_planning_runtime",
        "dig_token_planning",
        "return_token_planning",
    ):
        assert importlib.util.find_spec(old_root_module(suffix)) is None


def test_coverage_report_compatibility_package_imports_contracts() -> None:
    from testbed.planner.primitive.compatibility.cell_entry import (
        PrimitiveCellEntryCompatibilityRuntimeState,
        PrimitiveCellEntryReportStatus,
    )
    from testbed.planner.primitive.compatibility.pre_dig_align import (
        PrimitivePreDigAlignCompatibilityRuntimeState,
        PrimitivePreDigAlignReportStatus,
    )
    from testbed.planner.primitive.coverage.effect_runtime import (
        PrimitiveCoverageEffectRuntime,
        PrimitiveCoverageEffectRuntimePorts,
    )
    from testbed.planner.primitive.coverage.effects import (
        CoverageEffectRuntimeCoordinator,
        CoverageRuntimeService,
    )
    from testbed.planner.primitive.coverage.exemplars import (
        CoverageStateExemplarPlanner,
    )
    from testbed.planner.primitive.coverage.facts import (
        CoveragePlanningFactService,
    )
    from testbed.planner.primitive.coverage.report_runtime import (
        PrimitiveCoverageReportRuntime,
        PrimitiveCoverageReportRuntimePorts,
    )
    from testbed.planner.primitive.coverage.reports import (
        CoverageReportService,
        CoverageSummaryReportStatus,
        CoverageTraceReportStatus,
    )
    from testbed.planner.primitive.coverage.selection import (
        CoverageCorridorState,
        CoverageSelectionService,
    )
    from testbed.planner.primitive.coverage.selection_runtime import (
        PrimitiveCoverageSelectionRuntime,
        PrimitiveCoverageSelectionRuntimePorts,
    )
    from testbed.planner.primitive.coverage.state import CoverageRuntimeState
    from testbed.planner.primitive.coverage.status import CoverageStatus
    from testbed.planner.primitive.report.debug_report import (
        PrimitiveDebugReportBuilder,
    )
    from testbed.planner.primitive.report.planner_trace import (
        PrimitivePlannerTraceBuilder,
    )
    from testbed.planner.primitive.report.rollout_summary import (
        PrimitiveRolloutSummaryBuilder,
    )
    from testbed.planner.primitive.report.runtime import (
        PrimitiveReportCompositionRuntime,
        PrimitiveReportRuntime,
    )

    assert CoverageCorridorState.__name__ == "CoverageCorridorState"
    assert CoverageSelectionService.__name__ == "CoverageSelectionService"
    assert CoverageRuntimeState.__name__ == "CoverageRuntimeState"
    assert CoverageStatus.__name__ == "CoverageStatus"
    assert CoveragePlanningFactService.__name__ == "CoveragePlanningFactService"
    assert PrimitiveCoverageSelectionRuntime.__name__ == (
        "PrimitiveCoverageSelectionRuntime"
    )
    assert PrimitiveCoverageSelectionRuntimePorts.__name__ == (
        "PrimitiveCoverageSelectionRuntimePorts"
    )
    assert CoverageEffectRuntimeCoordinator.__name__ == (
        "CoverageEffectRuntimeCoordinator"
    )
    assert CoverageRuntimeService.__name__ == "CoverageRuntimeService"
    assert PrimitiveCoverageEffectRuntime.__name__ == (
        "PrimitiveCoverageEffectRuntime"
    )
    assert PrimitiveCoverageEffectRuntimePorts.__name__ == (
        "PrimitiveCoverageEffectRuntimePorts"
    )
    assert CoverageReportService.__name__ == "CoverageReportService"
    assert CoverageSummaryReportStatus.__name__ == "CoverageSummaryReportStatus"
    assert CoverageTraceReportStatus.__name__ == "CoverageTraceReportStatus"
    assert PrimitiveCoverageReportRuntime.__name__ == (
        "PrimitiveCoverageReportRuntime"
    )
    assert PrimitiveCoverageReportRuntimePorts.__name__ == (
        "PrimitiveCoverageReportRuntimePorts"
    )
    assert CoverageStateExemplarPlanner.__name__ == "CoverageStateExemplarPlanner"
    assert PrimitiveDebugReportBuilder.__name__ == "PrimitiveDebugReportBuilder"
    assert PrimitiveRolloutSummaryBuilder.__name__ == (
        "PrimitiveRolloutSummaryBuilder"
    )
    assert PrimitivePlannerTraceBuilder.__name__ == "PrimitivePlannerTraceBuilder"
    assert PrimitiveReportRuntime.__name__ == "PrimitiveReportRuntime"
    assert PrimitiveReportCompositionRuntime.__name__ == (
        "PrimitiveReportCompositionRuntime"
    )
    assert PrimitiveCellEntryCompatibilityRuntimeState.__name__ == (
        "PrimitiveCellEntryCompatibilityRuntimeState"
    )
    assert PrimitiveCellEntryReportStatus.__name__ == (
        "PrimitiveCellEntryReportStatus"
    )
    assert PrimitivePreDigAlignCompatibilityRuntimeState.__name__ == (
        "PrimitivePreDigAlignCompatibilityRuntimeState"
    )
    assert PrimitivePreDigAlignReportStatus.__name__ == (
        "PrimitivePreDigAlignReportStatus"
    )


def test_internal_only_coverage_report_compatibility_roots_are_not_importable() -> None:
    def old_root_module(suffix: str) -> str:
        return f"testbed.planner.primitive_{suffix}"

    for suffix in (
        "coverage",
        "coverage_state",
        "coverage_status",
        "coverage_facts",
        "coverage_selection_runtime",
        "coverage_updates",
        "coverage_effect_runtime",
        "coverage_reports",
        "coverage_report_runtime",
        "coverage_exemplars",
        "report_runtime",
        "debug_report",
        "rollout_summary",
        "planner_trace",
        "cell_entry_state",
        "pre_dig_align_state",
    ):
        assert importlib.util.find_spec(old_root_module(suffix)) is None


def test_config_shell_execution_facts_observation_package_imports_contracts() -> None:
    from testbed.planner.primitive.config.adapter import (
        PrimitivePlannerAdapterConfigInputs,
        PrimitivePlannerAdapterConfigNormalizer,
    )
    from testbed.planner.primitive.execution.action_dispatch import (
        PrimitiveActionDispatchService,
    )
    from testbed.planner.primitive.execution.boundary_event import (
        PrimitiveBoundaryEventRuntimeService,
    )
    from testbed.planner.primitive.execution.cycle_state import (
        PrimitiveCycleRuntimeState,
    )
    from testbed.planner.primitive.execution.dig_progress import (
        PrimitiveDigProgressRuntimeService,
    )
    from testbed.planner.primitive.execution.dig_recovery import (
        PrimitiveDigRecoveryService,
    )
    from testbed.planner.primitive.execution.reset_lifecycle import (
        PrimitiveResetLifecycleService,
    )
    from testbed.planner.primitive.execution.return_state import (
        PrimitiveReturnRuntimeState,
    )
    from testbed.planner.primitive.execution.runtime import (
        PrimitiveExecutionDriver,
        PrimitiveExecutionRuntime,
        PrimitiveTickPreparation,
    )
    from testbed.planner.primitive.execution.scripted_bootstrap import (
        PrimitiveScriptedBootstrapRuntimeService,
    )
    from testbed.planner.primitive.execution.skill_lifecycle import (
        PrimitiveSkillLifecycleService,
    )
    from testbed.planner.primitive.execution.state import (
        PrimitiveExecutionRuntimeState,
    )
    from testbed.planner.primitive.execution.tick_finalization import (
        PrimitiveTickFinalizationRuntime,
    )
    from testbed.planner.primitive.facts.capabilities import (
        PrimitiveObservationFacts,
    )
    from testbed.planner.primitive.facts.observation import (
        PrimitivePolicyObservationAssembler,
    )
    from testbed.planner.primitive.shell.runtime_kernel import (
        PrimitivePlannerPublicRuntime,
        PrimitivePlannerRuntimeKernel,
    )

    assert (
        PrimitivePlannerAdapterConfigInputs.__name__
        == "PrimitivePlannerAdapterConfigInputs"
    )
    assert (
        PrimitivePlannerAdapterConfigNormalizer.__name__
        == "PrimitivePlannerAdapterConfigNormalizer"
    )
    assert PrimitivePlannerRuntimeKernel.__name__ == "PrimitivePlannerRuntimeKernel"
    assert PrimitivePlannerPublicRuntime.__name__ == "PrimitivePlannerPublicRuntime"
    assert PrimitiveExecutionRuntime.__name__ == "PrimitiveExecutionRuntime"
    assert PrimitiveExecutionDriver.__name__ == "PrimitiveExecutionDriver"
    assert PrimitiveTickPreparation.__name__ == "PrimitiveTickPreparation"
    assert PrimitiveExecutionRuntimeState.__name__ == "PrimitiveExecutionRuntimeState"
    assert PrimitiveCycleRuntimeState.__name__ == "PrimitiveCycleRuntimeState"
    assert PrimitiveReturnRuntimeState.__name__ == "PrimitiveReturnRuntimeState"
    assert PrimitiveResetLifecycleService.__name__ == "PrimitiveResetLifecycleService"
    assert PrimitiveTickFinalizationRuntime.__name__ == (
        "PrimitiveTickFinalizationRuntime"
    )
    assert PrimitiveActionDispatchService.__name__ == "PrimitiveActionDispatchService"
    assert PrimitiveBoundaryEventRuntimeService.__name__ == (
        "PrimitiveBoundaryEventRuntimeService"
    )
    assert PrimitiveDigProgressRuntimeService.__name__ == (
        "PrimitiveDigProgressRuntimeService"
    )
    assert PrimitiveDigRecoveryService.__name__ == "PrimitiveDigRecoveryService"
    assert PrimitiveSkillLifecycleService.__name__ == "PrimitiveSkillLifecycleService"
    assert PrimitiveScriptedBootstrapRuntimeService.__name__ == (
        "PrimitiveScriptedBootstrapRuntimeService"
    )
    assert PrimitiveObservationFacts.__name__ == "PrimitiveObservationFacts"
    assert PrimitivePolicyObservationAssembler.__name__ == (
        "PrimitivePolicyObservationAssembler"
    )


def test_internal_only_config_shell_execution_facts_observation_roots_are_not_importable() -> None:
    def old_root_module(suffix: str) -> str:
        return f"testbed.planner.primitive_{suffix}"

    for suffix in (
        "adapter_config",
        "runtime_kernel",
        "execution",
        "execution_state",
        "cycle_state",
        "return_state",
        "reset_lifecycle",
        "tick_finalization",
        "action_dispatch",
        "boundary_event",
        "dig_progress",
        "dig_recovery",
        "skill_lifecycle",
        "scripted_bootstrap",
        "capabilities",
        "observation",
    ):
        assert importlib.util.find_spec(old_root_module(suffix)) is None
