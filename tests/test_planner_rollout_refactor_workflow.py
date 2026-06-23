from __future__ import annotations

from pathlib import Path

import pytest

from scripts.planner_refactor_guard import (
    PlannerRefactorGuardError,
    check_historical_file_guard,
    check_plan_contract,
    check_skill_contract,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_plan_contract_requires_separate_plan_log_and_no_legacy_plan_files(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "docs/planner_rollout_evidence_refactor_plan.md",
        "\n".join(
            [
                "# Rollout Evidence Driven Planner Refactor Plan",
                "## Priority Rule",
                "## Baseline Architecture Reconstruction Gate",
                "## First-Principles Reflection Gate",
                "## Rollout Evidence Gate",
                "## New-File Extraction Rule",
                "## Parking And Reclassification Rule",
                "## Delegated Executor Callback Rule",
                "## Three-Iteration Reflection Rule",
                "send_message_to_thread",
                "three-iteration reflection",
                "docs/planner_baseline_architecture_map.md",
                "branch baseline",
            ]
        ),
    )
    _write(
        tmp_path / "docs/planner_rollout_evidence_refactor_log.md",
        "\n".join(
            [
                "# Rollout Evidence Driven Planner Refactor Log",
                "## Change Record Protocol",
                "## Records",
            ]
        ),
    )
    _write(
        tmp_path / "docs/planner_baseline_architecture_map.md",
        "\n".join(
            [
                "# Planner Baseline Architecture Map",
                "branch baseline",
                "Do not record round-by-round changes here.",
                "```mermaid",
                "flowchart TD",
                "```",
            ]
        ),
    )
    _write(
        tmp_path / "docs/planner_current_code_architecture_plan.md",
        "\n".join(
            [
                "# Planner Current-Code Architecture Plan",
                "## Current Code Reality",
                "## Primitive Planner Responsibility Map",
                "## Evidence-Based Retention Matrix",
                "## Legacy Parking Catalog",
                "## Verification Matrix",
            ]
        ),
    )
    check_plan_contract(tmp_path)


def test_plan_contract_rejects_old_active_plan_path(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs/primitive_scheduler_service_refactor_plan.md",
        "# Old active-looking plan\n",
    )

    with pytest.raises(PlannerRefactorGuardError, match="legacy plan"):
        check_plan_contract(tmp_path)


def test_plan_contract_rejects_renamed_historical_plan_file(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs/planner_rollout_evidence_refactor_plan.md",
        "\n".join(
            [
                "# Rollout Evidence Driven Planner Refactor Plan",
                "## Priority Rule",
                "## Baseline Architecture Reconstruction Gate",
                "## First-Principles Reflection Gate",
                "## Rollout Evidence Gate",
                "## New-File Extraction Rule",
                "## Parking And Reclassification Rule",
            ]
        ),
    )
    _write(
        tmp_path / "docs/planner_rollout_evidence_refactor_log.md",
        "# Rollout Evidence Driven Planner Refactor Log\n\n## Change Record Protocol\n",
    )
    _write(
        tmp_path
        / "docs/primitive_scheduler_service_refactor_plan_DO_NOT_EXTEND_HISTORY.md",
        "# Historical Plan\n",
    )

    with pytest.raises(PlannerRefactorGuardError, match="legacy plan"):
        check_plan_contract(tmp_path)


def test_plan_contract_rejects_change_records_in_active_plan(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs/planner_rollout_evidence_refactor_plan.md",
        "\n".join(
            [
                "# Rollout Evidence Driven Planner Refactor Plan",
                "## Priority Rule",
                "## Baseline Architecture Reconstruction Gate",
                "## First-Principles Reflection Gate",
                "## Rollout Evidence Gate",
                "## New-File Extraction Rule",
                "## Parking And Reclassification Rule",
                "## Delegated Executor Callback Rule",
                "## Three-Iteration Reflection Rule",
                "send_message_to_thread",
                "three-iteration reflection",
                "## Change Record 2026-06-18",
            ]
        ),
    )
    _write(
        tmp_path / "docs/planner_rollout_evidence_refactor_log.md",
        "# Rollout Evidence Driven Planner Refactor Log\n\n## Change Record Protocol\n",
    )
    _write(
        tmp_path / "docs/planner_baseline_architecture_map.md",
        "\n".join(
            [
                "# Planner Baseline Architecture Map",
                "branch baseline",
                "Do not record round-by-round changes here.",
                "```mermaid",
                "flowchart TD",
                "```",
            ]
        ),
    )
    _write(
        tmp_path / "docs/planner_current_code_architecture_plan.md",
        "\n".join(
            [
                "# Planner Current-Code Architecture Plan",
                "## Current Code Reality",
                "## Primitive Planner Responsibility Map",
                "## Evidence-Based Retention Matrix",
                "## Legacy Parking Catalog",
                "## Verification Matrix",
            ]
        ),
    )
    with pytest.raises(PlannerRefactorGuardError, match="change records"):
        check_plan_contract(tmp_path)


def test_historical_file_guard_allows_deleting_absent_legacy_plan(tmp_path: Path) -> None:
    check_historical_file_guard(
        ["docs/primitive_scheduler_service_refactor_plan_DO_NOT_EXTEND_HISTORY.md"],
        root=tmp_path,
    )


def test_historical_file_guard_blocks_recreating_legacy_plan(tmp_path: Path) -> None:
    _write(
        tmp_path
        / "docs/primitive_scheduler_service_refactor_plan_DO_NOT_EXTEND_HISTORY.md",
        "# Historical Plan\n",
    )

    with pytest.raises(PlannerRefactorGuardError, match="historical plan"):
        check_historical_file_guard(
            ["docs/primitive_scheduler_service_refactor_plan_DO_NOT_EXTEND_HISTORY.md"],
            root=tmp_path,
        )


def test_skill_contract_points_to_rollout_evidence_plan(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "\n".join(
            [
                "---",
                "name: excavator-planner-safe-refactor",
                "description: Use for rollout-evidence-driven planner refactors.",
                "---",
                "# Excavator Planner Safe Refactor",
                "Read docs/planner_rollout_evidence_refactor_plan.md first.",
                "Keep docs/planner_rollout_evidence_refactor_log.md separate.",
                "Update docs/planner_baseline_architecture_map.md before migration.",
                "Read docs/planner_current_code_architecture_plan.md before migration.",
                "Use real rollout log evidence before extracting code.",
                "Reconstruct the branch baseline architecture first.",
                "Run the first-principles reflection gate every round.",
                "The primary goal is refactoring and abstraction.",
            ]
        ),
        encoding="utf-8",
    )

    check_skill_contract(skill)


def test_repository_rollout_refactor_contract_is_wired() -> None:
    root = Path(__file__).resolve().parents[1]

    check_plan_contract(root)
    check_skill_contract(
        Path.home()
        / ".codex"
        / "skills"
        / "excavator-planner-safe-refactor"
        / "SKILL.md"
    )


def test_pre_commit_config_wires_planner_refactor_hooks() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    for hook_id in (
        "planner-refactor-history-guard",
        "planner-refactor-plan-contract",
        "planner-refactor-skill-contract",
    ):
        assert hook_id in config


def test_git_hooks_pre_commit_fallback_runs_planner_refactor_guards() -> None:
    root = Path(__file__).resolve().parents[1]
    hook = (root / ".githooks/pre-commit").read_text(encoding="utf-8")

    assert "scripts/planner_refactor_guard.py --check-plan-contract" in hook
    assert "scripts/planner_refactor_guard.py --check-skill-contract" in hook
    assert "scripts/planner_refactor_guard.py --check-historical-files" in hook


def test_goal_prompt_exists_for_rollout_evidence_goal_mode() -> None:
    root = Path(__file__).resolve().parents[1]
    prompt = (
        root / "docs/prompts/planner_rollout_evidence_goal_prompt.md"
    ).read_text(encoding="utf-8")

    assert "Long-running Goal" in prompt
    assert "$excavator-planner-safe-refactor" in prompt
    assert "rollout log" in prompt.lower()
    assert "first-principles" in prompt.lower()
    assert "branch baseline" in prompt.lower()
    assert "docs/planner_baseline_architecture_map.md" in prompt
    assert "docs/planner_current_code_architecture_plan.md" in prompt
    assert "send_message_to_thread" in prompt
    assert "target lock" in prompt
    assert "TDD red" in prompt
    assert "git status after" in prompt
    assert "HEAD after" in prompt
    assert "three-iteration reflection" in prompt
    assert "primitive_scheduler_service_refactor_plan" not in prompt


def test_architecture_map_template_exists_separate_from_plan() -> None:
    root = Path(__file__).resolve().parents[1]
    architecture_map = (
        root / "docs/planner_baseline_architecture_map.md"
    ).read_text(encoding="utf-8")

    assert "# Planner Baseline Architecture Map" in architecture_map
    assert "branch baseline" in architecture_map.lower()
    assert "```mermaid" in architecture_map
    assert "Do not record round-by-round changes here" in architecture_map


def test_current_code_architecture_plan_exists_as_source_of_truth() -> None:
    root = Path(__file__).resolve().parents[1]
    current_code_plan = (
        root / "docs/planner_current_code_architecture_plan.md"
    ).read_text(encoding="utf-8")

    assert "# Planner Current-Code Architecture Plan" in current_code_plan
    assert "## Current Code Reality" in current_code_plan
    assert "## Primitive Planner Responsibility Map" in current_code_plan
    assert "## Evidence-Based Retention Matrix" in current_code_plan
    assert "## Legacy Parking Catalog" in current_code_plan
    assert "## Verification Matrix" in current_code_plan
