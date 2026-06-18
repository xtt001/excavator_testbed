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


def test_plan_contract_requires_separate_plan_log_and_historical_filename(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "docs/planner_rollout_evidence_refactor_plan.md",
        "\n".join(
            [
                "# Rollout Evidence Driven Planner Refactor Plan",
                "## First-Principles Reflection Gate",
                "## Rollout Evidence Gate",
                "## New-File Extraction Rule",
                "## Deletion Rule",
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
        tmp_path
        / "docs/primitive_scheduler_service_refactor_plan_DO_NOT_EXTEND_HISTORY.md",
        "# Historical Plan\n\nStatus: historical / do not extend.\n",
    )

    check_plan_contract(tmp_path)


def test_plan_contract_rejects_old_active_plan_path(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs/primitive_scheduler_service_refactor_plan.md",
        "# Old active-looking plan\n",
    )

    with pytest.raises(PlannerRefactorGuardError, match="old active plan path"):
        check_plan_contract(tmp_path)


def test_plan_contract_rejects_change_records_in_active_plan(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs/planner_rollout_evidence_refactor_plan.md",
        "\n".join(
            [
                "# Rollout Evidence Driven Planner Refactor Plan",
                "## First-Principles Reflection Gate",
                "## Rollout Evidence Gate",
                "## New-File Extraction Rule",
                "## Deletion Rule",
                "## Change Record 2026-06-18",
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
        "# Historical Plan\n\nStatus: historical / do not extend.\n",
    )

    with pytest.raises(PlannerRefactorGuardError, match="change records"):
        check_plan_contract(tmp_path)


def test_historical_file_guard_blocks_future_edits_to_do_not_extend_plan() -> None:
    with pytest.raises(PlannerRefactorGuardError, match="historical plan"):
        check_historical_file_guard(
            [
                "docs/primitive_scheduler_service_refactor_plan_DO_NOT_EXTEND_HISTORY.md"
            ]
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
                "Use real rollout log evidence before extracting code.",
                "Run the first-principles reflection gate every round.",
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
