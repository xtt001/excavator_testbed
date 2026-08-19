from __future__ import annotations

from pathlib import Path

import pytest

from scripts.planner_architecture_doc_guard import (
    EXPECTED_DOCS,
    PlannerDocGuardError,
    check_architecture_contract,
    check_changed_docs,
    check_doc_inventory,
    check_strict18_goal_following_contract,
)


def _write(path: Path, text: str = "# Doc\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_doc_inventory_accepts_curated_yulong_plus_v2_5_set(tmp_path: Path) -> None:
    for relative_path in EXPECTED_DOCS:
        _write(tmp_path / relative_path)

    check_doc_inventory(tmp_path)


def test_doc_inventory_rejects_unexpected_docs(tmp_path: Path) -> None:
    for relative_path in EXPECTED_DOCS:
        _write(tmp_path / relative_path)
    _write(tmp_path / "docs/current_status_and_plan.md")

    with pytest.raises(PlannerDocGuardError, match="unexpected"):
        check_doc_inventory(tmp_path)


def test_changed_docs_guard_allows_deleting_removed_docs(tmp_path: Path) -> None:
    check_changed_docs(["docs/current_status_and_plan.md"], root=tmp_path)


def test_changed_docs_guard_blocks_recreating_removed_docs(tmp_path: Path) -> None:
    _write(tmp_path / "docs/current_status_and_plan.md")

    with pytest.raises(PlannerDocGuardError, match="unexpected docs"):
        check_changed_docs(["docs/current_status_and_plan.md"], root=tmp_path)


def test_repository_planner_documentation_contract_is_wired() -> None:
    root = Path(__file__).resolve().parents[1]

    check_doc_inventory(root)
    check_architecture_contract(root)


def test_pre_commit_config_wires_doc_inventory_guard() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "planner-doc-inventory-guard" in config
    assert "planner-architecture-doc-contract" in config
    assert "--check-changed-docs" in config
    assert "--check-doc-inventory" in config
    assert "planner-refactor-plan-contract" not in config


def test_git_hooks_pre_commit_fallback_runs_doc_inventory_guards() -> None:
    root = Path(__file__).resolve().parents[1]
    hook = (root / ".githooks/pre-commit").read_text(encoding="utf-8")

    assert "scripts/planner_architecture_doc_guard.py --check-changed-docs" in hook
    assert "scripts/planner_architecture_doc_guard.py --check-architecture-contract" in hook
    assert "scripts/planner_architecture_doc_guard.py --check-doc-inventory" in hook
    assert "--check-plan-contract" not in hook


def test_readme_points_to_curated_docs() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")

    for needle in (
        "docs/strict18_goal_following_roadmap.md",
        "docs/planner_to_act_conceptual_contract.md",
        "docs/planner_current_architecture.md",
        "docs/planner_scheduling_backend_design.md",
        "docs/planner_decision_backend_contract.md",
        "docs/data_processing_hdf5_qc_contract.md",
        "docs/primitive_phase_boundaries.md",
    ):
        assert needle in readme

    assert "docs/current_status_and_plan.md" not in readme
    assert "docs/v2_2_4primitives/phase_boundaries.md" not in readme
    assert "docs/v2_5_design_sketch/" not in readme


def test_strict18_goal_following_contract_requires_current_stage_a_anchors(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "docs/strict18_goal_following_roadmap.md",
        "\n".join(
            (
                "当前唯一授权的实现任务是**阶段 A：冻结 ACT 的目标条件敏感性离线审计**。",
                "ACT 直接输出 4D action",
                "`exact-tuple` 与现有 continuous qpos predictor 是 `diagnostic_legacy`。",
                "teacher_forced_recorded_observation",
                "promotion_eligible=false",
                "阶段 B",
                "阶段 C",
                "阶段 D",
                "阶段 E",
                "阶段 F",
            )
        ),
    )
    _write(
        tmp_path / "docs/planner_to_act_conceptual_contract.md",
        "teacher-forced recorded-observation 下的动作变化，只证明 ACT 读取条件；"
        "不等于 Unity 闭环成功或 production proof。\n",
    )

    check_strict18_goal_following_contract(tmp_path)


def test_strict18_goal_following_contract_rejects_missing_evidence_boundary(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "docs/strict18_goal_following_roadmap.md",
        "\n".join(
            (
                "当前唯一授权的实现任务是**阶段 A：冻结 ACT 的目标条件敏感性离线审计**。",
                "ACT 直接输出 4D action",
                "`exact-tuple` 与现有 continuous qpos predictor 是 `diagnostic_legacy`。",
                "teacher_forced_recorded_observation",
                "promotion_eligible=false",
                "阶段 B",
                "阶段 C",
                "阶段 D",
                "阶段 E",
                "阶段 F",
            )
        ),
    )
    _write(tmp_path / "docs/planner_to_act_conceptual_contract.md", "# Contract\n")

    with pytest.raises(PlannerDocGuardError, match="teacher-forced"):
        check_strict18_goal_following_contract(tmp_path)
