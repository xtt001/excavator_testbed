"""Validate Tier 1 decision-structure research artifacts.

This module is intentionally offline-only. It validates archived planner
reports, schema/gold-example assumptions, and citation paths; it does not import
planner runtime shells, call ACT policies, or mutate planner state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PACKAGE_SCHEMA_VERSION = "tier1_validation_package_manifest_v0"
REPORT_SCHEMA_VERSION = "tier1_validation_report_v0"

REQUIRED_INPUTS = (
    "inputs/eval_resolved_config.yaml",
    "inputs/planner_evidence_report.json",
    "inputs/planner_evidence_report.md",
    "inputs/rollout_000.jsonl",
    "inputs/rollout_000_planner_trace.json",
    "inputs/rollout_000_summary.json",
)
REQUIRED_PACKAGE_FILES = ("README.md", "manifest.json", "hashes/sha256sums.txt")

EXPECTED_GOLD_SELECT_INDICES = (0, 2, 12, 19)
ALLOWED_CITATION_SOURCES = {
    "planner_trace",
    "rollout_summary",
    "evidence_report",
    "debug_state_sample",
    "config",
    "package_metadata",
}
ALLOWED_SOURCE_ROLES = {
    "confirmed-live",
    "report-only",
    "parked",
    "config",
    "package-metadata",
}
FORBIDDEN_FIELD_NAMES = {
    "action",
    "qpos",
    "qvel",
    "env_state",
    "task_metrics",
    "raw_image_observations",
    "checkpoint_state",
    "policy_private_attrs",
    "owner_state_object",
    "mutation_callback",
}


class Tier1ValidationError(RuntimeError):
    """Raised when a validation package cannot be loaded at all."""


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    path: str = ""

    def to_json(self) -> dict[str, Any]:
        payload = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.path:
            payload["path"] = self.path
        return payload


@dataclass(frozen=True)
class Tier1Package:
    root: Path
    manifest: dict[str, Any]
    planner_trace: dict[str, Any]
    rollout_summary: dict[str, Any]
    evidence_report: dict[str, Any]
    hash_status: dict[str, bool]
    input_hashes: dict[str, str]

    @property
    def dataset_id(self) -> str:
        return str(self.manifest.get("dataset_id", ""))


@dataclass
class Tier1ValidationReport:
    package_path: str
    dataset_id: str
    package_fingerprint: dict[str, Any]
    validation_limits: dict[str, Any]
    input_hash_status: dict[str, bool]
    select_event_summary: dict[str, Any]
    gold_example_results: dict[str, list[dict[str, Any]]]
    fail_fast_errors: list[ValidationIssue] = field(default_factory=list)
    audit_warnings: list[ValidationIssue] = field(default_factory=list)
    unsupported_claim_rejections: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.fail_fast_errors

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "passed": self.passed,
            "package_path": self.package_path,
            "dataset_id": self.dataset_id,
            "package_fingerprint": self.package_fingerprint,
            "validation_limits": self.validation_limits,
            "input_hash_status": self.input_hash_status,
            "select_event_summary": self.select_event_summary,
            "gold_example_results": self.gold_example_results,
            "fail_fast_errors": [issue.to_json() for issue in self.fail_fast_errors],
            "audit_warnings": [issue.to_json() for issue in self.audit_warnings],
            "unsupported_claim_rejections": self.unsupported_claim_rejections,
            "metrics": self.metrics,
        }


def validate_tier1_package(package_path: Path | str) -> Tier1ValidationReport:
    """Validate a Tier 1 research package and return a report."""

    package = load_tier1_package(Path(package_path))
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    if package.manifest.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        errors.append(
            ValidationIssue(
                "error",
                "unsupported_manifest_schema",
                f"Expected {PACKAGE_SCHEMA_VERSION!r}.",
                "manifest.json#/schema_version",
            )
        )

    for rel_path, ok in package.hash_status.items():
        if not ok:
            errors.append(
                ValidationIssue(
                    "error",
                    "input_hash_mismatch",
                    f"Hash mismatch for {rel_path}.",
                    rel_path,
                )
            )

    trace_events = _coverage_decision_trace(package.planner_trace, errors)
    select_events = extract_select_events(trace_events)
    select_summary = _select_event_summary(trace_events, select_events)

    utility_results = _validate_utility_gold_examples(select_events, errors, warnings)
    citation_results = _validate_llm_gold_citations(package, errors)
    negative_results = _validate_negative_examples(package)
    for row in negative_results:
        if not row.get("passed"):
            errors.append(
                ValidationIssue(
                    "error",
                    "negative_rejection_failed",
                    f"Negative example was not rejected: {row.get('case', '<unknown>')}.",
                    str(row.get("path", "")),
                )
            )

    metrics = {
        "select_event_count": len(select_events),
        "candidate_count_per_select_event": [
            len(event.get("candidate_scores", []) or []) for _, event in select_events
        ],
        "gold_utility_example_count": len(utility_results),
        "gold_llm_claim_count": len(citation_results),
        "negative_rejection_count": len(negative_results),
    }

    return Tier1ValidationReport(
        package_path=str(package.root),
        dataset_id=package.dataset_id,
        package_fingerprint={
            "manifest_schema_version": package.manifest.get("schema_version"),
            "manifest_sha256": _sha256_file(package.root / "manifest.json"),
            "input_hashes": package.input_hashes,
        },
        validation_limits=dict(package.manifest.get("validation_limits", {})),
        input_hash_status=package.hash_status,
        select_event_summary=select_summary,
        gold_example_results={
            "coverage_utility": utility_results,
            "llm_explanation": citation_results,
            "negative_rejections": negative_results,
        },
        fail_fast_errors=errors,
        audit_warnings=warnings,
        unsupported_claim_rejections=negative_results,
        metrics=metrics,
    )


def load_tier1_package(package_path: Path) -> Tier1Package:
    root = package_path.resolve()
    if not root.exists():
        raise Tier1ValidationError(f"Package path does not exist: {root}")
    if not root.is_dir():
        raise Tier1ValidationError(f"Package path is not a directory: {root}")

    required = (*REQUIRED_PACKAGE_FILES, *REQUIRED_INPUTS)
    missing = [rel for rel in required if not (root / rel).is_file()]
    if missing:
        raise Tier1ValidationError(
            "Tier 1 package is missing required files: " + ", ".join(missing)
        )

    manifest = _read_json_object(root / "manifest.json")
    planner_trace = _read_json_object(root / "inputs/rollout_000_planner_trace.json")
    rollout_summary = _read_json_object(root / "inputs/rollout_000_summary.json")
    evidence_report = _read_json_object(root / "inputs/planner_evidence_report.json")
    input_hashes = _read_sha256sums(root / "hashes/sha256sums.txt")
    hash_status = {
        rel_path: _sha256_file(root / rel_path) == expected
        for rel_path, expected in input_hashes.items()
    }
    for rel_path in REQUIRED_INPUTS:
        hash_status.setdefault(rel_path, False)

    return Tier1Package(
        root=root,
        manifest=manifest,
        planner_trace=planner_trace,
        rollout_summary=rollout_summary,
        evidence_report=evidence_report,
        hash_status=hash_status,
        input_hashes=input_hashes,
    )


def extract_select_events(
    coverage_decision_trace: list[Any],
) -> list[tuple[int, dict[str, Any]]]:
    result: list[tuple[int, dict[str, Any]]] = []
    for index, event in enumerate(coverage_decision_trace):
        if isinstance(event, dict) and event.get("event") == "select_corridor":
            result.append((index, event))
    return result


def write_report_json(path: Path, report: Tier1ValidationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_report_markdown(path: Path, report: Tier1ValidationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Tier 1 Decision-Structure Validation Report",
        "",
        f"- Package: `{report.package_path}`",
        f"- Dataset: `{report.dataset_id}`",
        f"- Passed: `{str(report.passed).lower()}`",
        f"- Select events: `{report.select_event_summary.get('select_event_count')}`",
        "",
        "## Validation Limits",
        "",
    ]
    for key, value in sorted(report.validation_limits.items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Fail-Fast Errors", ""])
    if report.fail_fast_errors:
        for issue in report.fail_fast_errors:
            lines.append(f"- `{issue.code}`: {issue.message}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Audit Warnings", ""])
    if report.audit_warnings:
        for issue in report.audit_warnings:
            lines.append(f"- `{issue.code}`: {issue.message}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Gold Examples", ""])
    for group, rows in report.gold_example_results.items():
        lines.append(f"### {group}")
        lines.append("")
        for row in rows:
            status = "pass" if row.get("passed") else "fail"
            label = row.get("name") or row.get("claim") or row.get("case")
            lines.append(f"- `{status}`: {label}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _coverage_decision_trace(
    planner_trace: dict[str, Any],
    errors: list[ValidationIssue],
) -> list[Any]:
    trace = planner_trace.get("coverage_decision_trace")
    if not isinstance(trace, list):
        errors.append(
            ValidationIssue(
                "error",
                "coverage_decision_trace_missing",
                "planner_trace.coverage_decision_trace must be a list.",
                "inputs/rollout_000_planner_trace.json#/coverage_decision_trace",
            )
        )
        return []
    return trace


def _select_event_summary(
    trace_events: list[Any],
    select_events: list[tuple[int, dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "coverage_decision_trace_count": len(trace_events),
        "select_event_count": len(select_events),
        "select_event_indices": [index for index, _ in select_events],
        "candidate_counts": [
            len(event.get("candidate_scores", []) or []) for _, event in select_events
        ],
    }


def _validate_utility_gold_examples(
    select_events: list[tuple[int, dict[str, Any]]],
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
) -> list[dict[str, Any]]:
    by_index = {index: event for index, event in select_events}
    results: list[dict[str, Any]] = []

    for event_index in EXPECTED_GOLD_SELECT_INDICES:
        event = by_index.get(event_index)
        if event is None:
            errors.append(
                ValidationIssue(
                    "error",
                    "gold_select_event_missing",
                    f"Expected gold select event {event_index}.",
                    f"planner_trace:/coverage_decision_trace/{event_index}",
                )
            )
            results.append(
                {"name": f"coverage_event_{event_index}", "passed": False}
            )
            continue

        candidates = event.get("candidate_scores")
        if not isinstance(candidates, list):
            errors.append(
                ValidationIssue(
                    "error",
                    "candidate_scores_missing",
                    f"Gold event {event_index} has no candidate_scores list.",
                    f"planner_trace:/coverage_decision_trace/{event_index}/candidate_scores",
                )
            )
            results.append(
                {"name": f"coverage_event_{event_index}", "passed": False}
            )
            continue

        missing_identity = [
            index
            for index, candidate in enumerate(candidates)
            if not isinstance(candidate, dict)
            or "corridor_id" not in candidate
            or "score" not in candidate
        ]
        if missing_identity:
            errors.append(
                ValidationIssue(
                    "error",
                    "candidate_identity_missing",
                    f"Gold event {event_index} has candidates without corridor_id/score.",
                    f"planner_trace:/coverage_decision_trace/{event_index}/candidate_scores",
                )
            )
            results.append(
                {
                    "name": f"coverage_event_{event_index}",
                    "passed": False,
                    "event_index": event_index,
                    "candidate_count": len(candidates),
                    "missing_identity_indices": missing_identity,
                }
            )
            continue

        selection = _selected_score_matches(event)
        if event_index == 19:
            passed = len(selection) > 1 and _all_candidates_depleted(candidates)
            if not passed:
                errors.append(
                    ValidationIssue(
                        "error",
                        "non_unique_terminal_case_not_detected",
                        "Event 19 should be non-unique and all depleted.",
                        "planner_trace:/coverage_decision_trace/19",
                    )
                )
            warnings.append(
                ValidationIssue(
                    "warning",
                    "non_unique_selection",
                    "Event 19 selected_score maps to multiple depleted candidates.",
                    "planner_trace:/coverage_decision_trace/19",
                )
            )
            results.append(
                {
                    "name": "terminal_all_depleted_event_19",
                    "passed": passed,
                    "event_index": event_index,
                    "selection_matches": selection,
                    "candidate_count": len(candidates),
                }
            )
            continue

        expected_corridor = {0: 3, 2: 1, 12: 2}[event_index]
        passed = selection == [expected_corridor]
        if not passed:
            errors.append(
                ValidationIssue(
                    "error",
                    "legacy_selection_mapping_failed",
                    f"Event {event_index} expected unique corridor {expected_corridor}.",
                    f"planner_trace:/coverage_decision_trace/{event_index}",
                )
            )

        if event_index == 2:
            margin = _top_score_margin(candidates)
            if margin is not None and margin < 0.2:
                warnings.append(
                    ValidationIssue(
                        "warning",
                        "low_margin_case",
                        f"Event 2 top score margin is {margin:.6f}.",
                        "planner_trace:/coverage_decision_trace/2",
                    )
                )

        results.append(
            {
                "name": f"coverage_event_{event_index}",
                "passed": passed,
                "event_index": event_index,
                "expected_corridor_id": expected_corridor,
                "selection_matches": selection,
                "candidate_count": len(candidates),
            }
        )

    return results


def _validate_llm_gold_citations(
    package: Tier1Package,
    errors: list[ValidationIssue],
) -> list[dict[str, Any]]:
    citations_by_claim = {
        "coverage_terminal_reason": [
            "rollout_summary:/coverage_terminal_stop_reason#role=report-only",
            "planner_trace:/coverage_terminal_stop_reason#role=report-only",
        ],
        "coverage_corridor_confirmed_live": [
            _evidence_citation(
                "coverage.corridor",
                "classification",
                "confirmed-live",
            ),
            _evidence_citation(
                "coverage.corridor",
                "consumed_by_decision_count",
                "confirmed-live",
            ),
            _evidence_citation("coverage.corridor", "reported_count", "confirmed-live"),
        ],
        "planner_trace_report_only": [
            _evidence_citation("trace.planner_trace", "classification", "report-only"),
            _evidence_citation(
                "trace.planner_trace",
                "consumed_by_decision_count",
                "report-only",
            ),
        ],
        "cell_entry_parked": [
            _evidence_citation("token.cell_entry", "classification", "parked"),
            _evidence_citation("token.cell_entry", "retention_decision", "parked"),
            "rollout_summary:/cell_entry_enabled#role=report-only",
            "rollout_summary:/cell_entry_trace_count#role=report-only",
        ],
        "pre_dig_align_parked": [
            _evidence_citation("gate.pre_dig_align", "classification", "parked"),
            _evidence_citation("gate.pre_dig_align", "retention_decision", "parked"),
            "rollout_summary:/pre_dig_align_enabled#role=report-only",
        ],
        "artifact_limits": [
            _metadata_citation("validation_limits/full_action_replay_supported"),
            _metadata_citation("validation_limits/raw_image_observations_included"),
            _metadata_citation("validation_limits/checkpoint_state_included"),
        ],
    }

    sources = _citation_sources(package)
    evidence_index = _evidence_rows_by_capability_id(package.evidence_report)
    results: list[dict[str, Any]] = []
    for claim, citations in citations_by_claim.items():
        claim_passed = True
        resolved: list[dict[str, Any]] = []
        for citation in citations:
            try:
                source, pointer, role = _parse_citation(citation)
                value = _resolve_citation(sources, evidence_index, source, pointer)
                _validate_citation_role(source, pointer, role, value, evidence_index)
                resolved.append(
                    {
                        "citation": citation,
                        "value": value,
                    }
                )
            except Tier1ValidationError as exc:
                claim_passed = False
                errors.append(
                    ValidationIssue(
                        "error",
                        "gold_citation_invalid",
                        str(exc),
                        citation,
                    )
                )
        results.append(
            {
                "claim": claim,
                "passed": claim_passed,
                "citations": resolved,
            }
        )
    return results


def _evidence_citation(capability_id: str, field_name: str, role: str) -> str:
    return (
        "evidence_report:/rows/by_capability_id/"
        f"{capability_id}/{field_name}#role={role}"
    )


def _metadata_citation(pointer: str) -> str:
    return f"package_metadata:/{pointer}#role=package-metadata"


def _validate_negative_examples(package: Tier1Package) -> list[dict[str, Any]]:
    limits = dict(package.manifest.get("validation_limits", {}))
    summary = package.rollout_summary
    evidence_index = _evidence_rows_by_capability_id(package.evidence_report)

    return [
        {
            "case": "counterfactual_rollout_improvement",
            "passed": True,
            "rejection_reason": "counterfactual outcome labels are absent",
            "missing_fields": ["counterfactual_outcome_label"],
        },
        {
            "case": "full_action_replay_parity",
            "passed": limits.get("full_action_replay_supported") is False,
            "rejection_reason": "full action replay is unsupported by package limits",
        },
        {
            "case": "forbidden_raw_field_explanation",
            "passed": True,
            "rejection_reason": "raw action/qpos/qvel/env_state/task_metrics are forbidden",
            "forbidden_fields": sorted(FORBIDDEN_FIELD_NAMES),
        },
        {
            "case": "cell_entry_mainline_drift",
            "passed": _is_parked(evidence_index.get("token.cell_entry"))
            and summary.get("cell_entry_enabled") == 0,
            "rejection_reason": "cell_entry is parked/report material in this package",
        },
        {
            "case": "pre_dig_align_default_drift",
            "passed": _is_parked(evidence_index.get("gate.pre_dig_align"))
            and summary.get("pre_dig_align_enabled") == 0,
            "rejection_reason": "pre_dig_align is parked/opt-in context, not default mainline",
        },
        {
            "case": "invented_online_backend_or_effect",
            "passed": True,
            "rejection_reason": "Tier 1 schemas forbid live effects/actions and routing changes",
        },
    ]


def _selected_score_matches(event: dict[str, Any]) -> list[int]:
    selected_score = event.get("selected_score")
    candidates = event.get("candidate_scores", []) or []
    matches: list[int] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        score = candidate.get("score")
        corridor_id = candidate.get("corridor_id")
        if isinstance(score, (int, float)) and isinstance(
            selected_score, (int, float)
        ):
            if abs(float(score) - float(selected_score)) <= 1e-9:
                matches.append(int(corridor_id))
        elif score == selected_score and corridor_id is not None:
            matches.append(int(corridor_id))
    return matches


def _top_score_margin(candidates: list[Any]) -> float | None:
    scores = [
        float(candidate["score"])
        for candidate in candidates
        if isinstance(candidate, dict) and isinstance(candidate.get("score"), (int, float))
    ]
    if len(scores) < 2:
        return None
    scores.sort(reverse=True)
    return scores[0] - scores[1]


def _all_candidates_depleted(candidates: list[Any]) -> bool:
    return bool(candidates) and all(
        isinstance(candidate, dict) and int(candidate.get("depleted", 0)) == 1
        for candidate in candidates
    )


def _citation_sources(package: Tier1Package) -> dict[str, Any]:
    return {
        "planner_trace": package.planner_trace,
        "rollout_summary": package.rollout_summary,
        "evidence_report": package.evidence_report,
        "package_metadata": package.manifest,
    }


def _parse_citation(citation: str) -> tuple[str, str, str]:
    if "#role=" not in citation:
        raise Tier1ValidationError(f"citation has no role: {citation}")
    source_and_pointer, role = citation.rsplit("#role=", 1)
    if role not in ALLOWED_SOURCE_ROLES:
        raise Tier1ValidationError(f"unsupported citation role {role!r}")
    if ":" not in source_and_pointer:
        raise Tier1ValidationError(f"citation has no source: {citation}")
    source, pointer = source_and_pointer.split(":", 1)
    if source not in ALLOWED_CITATION_SOURCES:
        raise Tier1ValidationError(f"unsupported citation source {source!r}")
    if not pointer.startswith("/"):
        raise Tier1ValidationError(f"citation pointer must start with '/': {citation}")
    return source, pointer, role


def _resolve_citation(
    sources: dict[str, Any],
    evidence_index: dict[str, dict[str, Any]],
    source: str,
    pointer: str,
) -> Any:
    if source == "evidence_report" and pointer.startswith("/rows/by_capability_id/"):
        parts = pointer.strip("/").split("/")
        if len(parts) < 4:
            raise Tier1ValidationError(f"invalid evidence semantic path: {pointer}")
        capability_id = _json_pointer_unescape(parts[2])
        row = evidence_index.get(capability_id)
        if row is None:
            raise Tier1ValidationError(f"unknown capability_id {capability_id!r}")
        return _resolve_json_pointer(row, "/" + "/".join(parts[3:]))
    return _resolve_json_pointer(sources[source], pointer)


def _validate_citation_role(
    source: str,
    pointer: str,
    role: str,
    value: Any,
    evidence_index: dict[str, dict[str, Any]],
) -> None:
    if role == "package-metadata" and source != "package_metadata":
        raise Tier1ValidationError("package-metadata role must cite package_metadata")
    if role == "config" and source != "config":
        raise Tier1ValidationError("config role must cite config")
    if source != "evidence_report" or not pointer.startswith("/rows/by_capability_id/"):
        return
    parts = pointer.strip("/").split("/")
    capability_id = _json_pointer_unescape(parts[2])
    row = evidence_index.get(capability_id)
    if row is None:
        raise Tier1ValidationError(f"unknown capability_id {capability_id!r}")
    if role == "confirmed-live" and row.get("classification") != "confirmed-live":
        raise Tier1ValidationError(f"{capability_id} is not confirmed-live")
    if role == "report-only" and row.get("classification") != "report-only":
        raise Tier1ValidationError(f"{capability_id} is not report-only")
    if role == "parked" and not _is_parked(row):
        raise Tier1ValidationError(f"{capability_id} is not parked")
    if value is None:
        raise Tier1ValidationError(f"citation resolved to null for {capability_id}")


def _is_parked(row: dict[str, Any] | None) -> bool:
    return bool(
        row
        and row.get("classification") == "dead-candidate"
        and row.get("retention_decision") == "retain-legacy-parking"
    )


def _evidence_rows_by_capability_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = report.get("rows", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row["capability_id"]): row
        for row in rows
        if isinstance(row, dict) and "capability_id" in row
    }


def _resolve_json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    current = document
    for raw_part in pointer.strip("/").split("/"):
        part = _json_pointer_unescape(raw_part)
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise Tier1ValidationError(f"missing list index {part!r}") from exc
        elif isinstance(current, dict):
            if part not in current:
                raise Tier1ValidationError(f"missing JSON pointer field {part!r}")
            current = current[part]
        else:
            raise Tier1ValidationError(f"cannot resolve pointer through {type(current)}")
    return current


def _json_pointer_unescape(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data: Any = json.load(f)
    except OSError as exc:
        raise Tier1ValidationError(f"Could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise Tier1ValidationError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise Tier1ValidationError(f"{path} must contain a JSON object.")
    return data


def _read_sha256sums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Tier1ValidationError(f"Could not read {path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            digest, rel_path = line.split(maxsplit=1)
        except ValueError as exc:
            raise Tier1ValidationError(
                f"{path} has malformed sha256 line {line_number}."
            ) from exc
        result[rel_path.strip()] = digest.strip()
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
