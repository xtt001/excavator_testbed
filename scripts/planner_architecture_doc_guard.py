from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

YULONG_DOCS = frozenset(
    {
        "docs/checklist_train.md",
        "docs/data_processing_hdf5_qc_contract.md",
        "docs/large_scene_simulation_training_requirements.md",
        "docs/llm_planner_closed_loop_terrain_conclusion.md",
        "docs/llm_planner_prework.md",
        "docs/oracle_terrain_residual_planner_v0_plan.md",
        "docs/planner_to_act_conceptual_contract.md",
        "docs/primitive_phase_boundaries.md",
        "docs/project_history_v1_to_now.md",
        "docs/training_setup.md",
        "docs/v1_to_v2_3_exploration_path.md",
        "docs/v2_1_failure_retrospective.md",
        "docs/v2_2_pro_operator_data_collection_plan.md",
        "docs/v2_4_5_spatial_mass_ownership.md",
        "docs/v2_4plan.md",
    }
)

REFACTOR_DOCS = frozenset(
    {
        "docs/planner_current_architecture.md",
        "docs/planner_decision_backend_contract.md",
        "docs/planner_scheduling_backend_design.md",
        "docs/planner_primitive_interface_standard.md",
        "docs/v2_5_rollout_issue_record_2026_06_30.md",
    }
)

EXPECTED_DOCS = frozenset(YULONG_DOCS | REFACTOR_DOCS)

REMOVED_DOC_FRAGMENTS = (
    "docs/planner_current_code_architecture_plan.md",
    "docs/planner_baseline_architecture_map.md",
    "docs/planner_rollout_evidence_refactor_plan.md",
    "docs/planner_rollout_evidence_refactor_log.md",
    "docs/planner_evidence_trace_tool.md",
    "docs/planner_evidence_reports",
    "docs/prompts/planner_rollout_evidence_goal_prompt.md",
    "docs/refactor_history/planner",
    "docs/codex/skills",
    "docs/current_status_and_plan.md",
    "docs/v2_1_plan",
    "docs/v2_2_4primitives",
    "docs/v2_5_design_sketch",
)


class PlannerDocGuardError(RuntimeError):
    pass


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PlannerDocGuardError(f"missing required file: {path}") from exc


def _require(text: str, needle: str, *, path: Path) -> None:
    if needle not in text:
        raise PlannerDocGuardError(f"{path} must mention {needle!r}")


def _docs_files(root: Path) -> set[str]:
    docs_root = root / "docs"
    if not docs_root.exists():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in docs_root.rglob("*")
        if path.is_file()
    }


def check_doc_inventory(root: str | Path = ".") -> None:
    root_path = Path(root)
    actual = _docs_files(root_path)
    missing = sorted(EXPECTED_DOCS - actual)
    unexpected = sorted(actual - EXPECTED_DOCS)
    if missing or unexpected:
        parts: list[str] = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if unexpected:
            parts.append("unexpected: " + ", ".join(unexpected))
        raise PlannerDocGuardError("docs inventory mismatch; " + " | ".join(parts))


def check_changed_docs(
    paths: Iterable[str | Path] | None = None,
    *,
    root: str | Path = ".",
) -> None:
    root_path = Path(root)
    changed = [Path(path).as_posix() for path in paths or []]
    unexpected_existing = sorted(
        path
        for path in changed
        if path.startswith("docs/")
        and path not in EXPECTED_DOCS
        and (root_path / path).exists()
    )
    if unexpected_existing:
        raise PlannerDocGuardError(
            "unexpected docs must not be recreated: "
            + ", ".join(unexpected_existing)
        )


def check_architecture_contract(root: str | Path = ".") -> None:
    root_path = Path(root)
    architecture_path = root_path / "docs/planner_current_architecture.md"
    decision_backend_path = root_path / "docs/planner_decision_backend_contract.md"
    scheduling_path = root_path / "docs/planner_scheduling_backend_design.md"
    interface_path = root_path / "docs/planner_primitive_interface_standard.md"
    rollout_path = root_path / "docs/v2_5_rollout_issue_record_2026_06_30.md"

    architecture = _read(architecture_path)
    decision_backend = _read(decision_backend_path)
    scheduling = _read(scheduling_path)
    interface = _read(interface_path)
    rollout = _read(rollout_path)

    for needle in (
        "active current planner architecture entry point",
        "default legacy FSM backendified with focused services",
        "behavior-tree shadow backend",
        "DecisionTraceRecord",
        "backend-neutral decision platform",
    ):
        _require(architecture, needle, path=architecture_path)

    for needle in (
        "active decision-backend architecture and extension contract",
        "default legacy FSM backendified with focused services",
        "DecisionTraceRecord",
        "DecisionProposalValidator",
        "behavior_tree_shadow",
        "LLM Or VLM Planner Integration Rules",
        "legacy_fsm",
    ):
        _require(decision_backend, needle, path=decision_backend_path)

    for needle in (
        "active design guide for future scheduling/decision backends",
        "PrimitiveDecisionRuntime",
        "behavior_tree_shadow",
        "VLM payload",
        "Design documents are not production import contracts",
    ):
        _require(scheduling, needle, path=scheduling_path)

    for needle in (
        "active interface target and implementation standard",
        "default legacy FSM backendified with focused services",
        "docs/planner_decision_backend_contract.md",
        "docs/v2_5_rollout_issue_record_2026_06_30.md",
    ):
        _require(interface, needle, path=interface_path)

    for needle in (
        "V2.5 Rollout",
        "aggregate TX24",
        "success=true",
        "completed_dump_count=10",
    ):
        _require(rollout, needle, path=rollout_path)

    for path in (architecture_path, decision_backend_path, scheduling_path, interface_path):
        text = _read(path)
        for removed in REMOVED_DOC_FRAGMENTS:
            if removed in text:
                raise PlannerDocGuardError(
                    f"{path} points at removed documentation: {removed}"
                )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the curated YuLong + V2.5 planner documentation set."
    )
    parser.add_argument(
        "--check-doc-inventory",
        action="store_true",
        help="Validate that docs/ contains only the curated documentation set.",
    )
    parser.add_argument(
        "--check-changed-docs",
        action="store_true",
        help="Reject recreated docs outside the curated set.",
    )
    parser.add_argument(
        "--check-architecture-contract",
        action="store_true",
        help="Validate current planner architecture and V2.5 documentation anchors.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root for documentation checks.",
    )
    parser.add_argument("paths", nargs="*", help="Changed paths from pre-commit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not (
        args.check_doc_inventory
        or args.check_changed_docs
        or args.check_architecture_contract
    ):
        parser.error("select at least one check")
    try:
        if args.check_changed_docs:
            check_changed_docs(args.paths, root=args.root)
        if args.check_doc_inventory:
            check_doc_inventory(args.root)
        if args.check_architecture_contract:
            check_architecture_contract(args.root)
    except PlannerDocGuardError as exc:
        print(f"planner-doc-guard: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
