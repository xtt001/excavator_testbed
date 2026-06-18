from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable


ACTIVE_PLAN = Path("docs/planner_rollout_evidence_refactor_plan.md")
CHANGE_LOG = Path("docs/planner_rollout_evidence_refactor_log.md")
OLD_ACTIVE_PLAN = Path("docs/primitive_scheduler_service_refactor_plan.md")
HISTORICAL_PLAN = Path(
    "docs/primitive_scheduler_service_refactor_plan_DO_NOT_EXTEND_HISTORY.md"
)
SKILL_PATH = (
    Path.home()
    / ".codex"
    / "skills"
    / "excavator-planner-safe-refactor"
    / "SKILL.md"
)


class PlannerRefactorGuardError(RuntimeError):
    pass


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PlannerRefactorGuardError(f"missing required file: {path}") from exc


def _require(text: str, needle: str, *, path: Path) -> None:
    if needle not in text:
        raise PlannerRefactorGuardError(f"{path} must mention {needle!r}")


def check_historical_file_guard(paths: Iterable[str | Path]) -> None:
    blocked = {
        str(HISTORICAL_PLAN),
        str(OLD_ACTIVE_PLAN),
    }
    touched = {str(Path(path)) for path in paths}
    blocked_touched = sorted(blocked.intersection(touched))
    if blocked_touched:
        raise PlannerRefactorGuardError(
            "historical plan files are closed; do not edit: "
            + ", ".join(blocked_touched)
        )


def check_plan_contract(root: str | Path = ".") -> None:
    root_path = Path(root)
    old_path = root_path / OLD_ACTIVE_PLAN
    if old_path.exists():
        raise PlannerRefactorGuardError(
            f"old active plan path must not exist: {OLD_ACTIVE_PLAN}"
        )

    active_path = root_path / ACTIVE_PLAN
    log_path = root_path / CHANGE_LOG
    historical_path = root_path / HISTORICAL_PLAN
    active = _read(active_path)
    log = _read(log_path)
    historical = _read(historical_path)

    for heading in (
        "# Rollout Evidence Driven Planner Refactor Plan",
        "## First-Principles Reflection Gate",
        "## Rollout Evidence Gate",
        "## New-File Extraction Rule",
        "## Deletion Rule",
    ):
        _require(active, heading, path=active_path)

    for forbidden in ("## Change Record", "## Recent checkpoint", "Landing Record"):
        if forbidden in active:
            raise PlannerRefactorGuardError(
                f"active plan must not contain change records: {forbidden}"
            )

    _require(log, "# Rollout Evidence Driven Planner Refactor Log", path=log_path)
    _require(log, "## Change Record Protocol", path=log_path)
    if "DO_NOT_EXTEND" not in str(HISTORICAL_PLAN):
        raise PlannerRefactorGuardError("historical plan filename must say DO_NOT_EXTEND")
    if "historical" not in historical.lower() or "do not extend" not in historical.lower():
        raise PlannerRefactorGuardError(
            f"{historical_path} must state it is historical and do not extend"
        )


def check_skill_contract(skill_path: str | Path = SKILL_PATH) -> None:
    path = Path(skill_path)
    text = _read(path)
    for needle in (
        "docs/planner_rollout_evidence_refactor_plan.md",
        "docs/planner_rollout_evidence_refactor_log.md",
        "rollout log",
        "first-principles",
    ):
        _require(text.lower(), needle.lower(), path=path)
    if "primitive_scheduler_service_refactor_plan.md first" in text:
        raise PlannerRefactorGuardError(
            "skill must not treat the old primitive scheduler plan as active"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate rollout-evidence-driven planner refactor workflow."
    )
    parser.add_argument(
        "--check-plan-contract",
        action="store_true",
        help="Validate active plan, change log, and historical plan placement.",
    )
    parser.add_argument(
        "--check-historical-files",
        action="store_true",
        help="Reject edits to historical plan paths.",
    )
    parser.add_argument(
        "--check-skill-contract",
        action="store_true",
        help="Validate the planner refactor skill points to the active plan.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root for plan checks.",
    )
    parser.add_argument(
        "--skill-path",
        default=str(SKILL_PATH),
        help="Skill file path for skill contract checks.",
    )
    parser.add_argument("paths", nargs="*", help="Changed paths from pre-commit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not (
        args.check_plan_contract
        or args.check_historical_files
        or args.check_skill_contract
    ):
        parser.error("select at least one check")
    try:
        if args.check_historical_files:
            check_historical_file_guard(args.paths)
        if args.check_plan_contract:
            check_plan_contract(args.root)
        if args.check_skill_contract:
            check_skill_contract(args.skill_path)
    except PlannerRefactorGuardError as exc:
        print(f"planner-refactor-guard: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
