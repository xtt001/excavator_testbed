from __future__ import annotations

from pathlib import Path

import pytest

from scripts.planner_architecture_doc_guard import (
    EXPECTED_DOCS,
    PlannerDocGuardError,
    check_architecture_contract,
    check_changed_docs,
    check_doc_inventory,
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
