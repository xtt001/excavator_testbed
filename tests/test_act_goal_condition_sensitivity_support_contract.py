from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from testbed.eval import act_goal_condition_sensitivity_support_contract as binding

RETURN_CANDIDATE = "joint_regularized_mahalanobis_p99_v2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _fixture(tmp_path: Path, *, support_status: str = "support_contract_not_selected") -> dict[str, Path]:
    source = tmp_path / "results"
    (source / "rollouts").mkdir(parents=True)
    (source / "hdf5_rollouts").mkdir()
    source_paths = {
        "eval_resolved_config": source / "eval_resolved_config.yaml",
        "eval_run_metadata": source / "eval_run_metadata.json",
        "rollout_jsonl": source / "rollouts" / "rollout_000.jsonl",
        "rollout_hdf5": source / "hdf5_rollouts" / "episode_0.hdf5",
    }
    for name, path in source_paths.items():
        path.write_text(f"{name}\n", encoding="utf-8")
    dig_config = tmp_path / "dig.yaml"
    return_config = tmp_path / "return.yaml"
    dig_config.write_text("dig\n", encoding="utf-8")
    return_config.write_text("return\n", encoding="utf-8")

    stage = tmp_path / "stage_a_v1"
    stage.mkdir()
    for name in ("baseline.json", "dig.json", "return.json"):
        (stage / name).write_text("{}\n", encoding="utf-8")
    stage_manifest = {
        "schema": "act_goal_condition_sensitivity_manifest_v1",
        "status": "completed",
        "evidence_kind": "teacher_forced_recorded_observation",
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "source_lineage": {
            "source_results_root": str(source.resolve()),
            **{name: _record(path) for name, path in source_paths.items()},
        },
    }
    _write_json(stage / "manifest.json", stage_manifest)

    support = tmp_path / "support_contract_v2_audit"
    support.mkdir()
    (support / "candidates.json").write_text("{}\n", encoding="utf-8")
    support_lineage = {
        "source_results_root": str(source.resolve()),
        **{name: _record(path) for name, path in source_paths.items()},
        "stage_a_manifest": _record(stage / "manifest.json"),
        "stage_a_baseline": _record(stage / "baseline.json"),
        "stage_a_dig": _record(stage / "dig.json"),
        "stage_a_return": _record(stage / "return.json"),
        "dig_training_config": _record(dig_config),
        "return_training_config": _record(return_config),
    }
    support_manifest = {
        "schema": "act_support_contract_audit_manifest_v1",
        "support_contract_version": "support_contract_v2",
        "status": support_status,
        "evidence_kind": "teacher_forced_recorded_observation",
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "target_rollout_used_for_selection": False,
        "selected_candidate_by_primitive": {
            "dig": None,
            "return": RETURN_CANDIDATE,
        },
        "selection_status_by_primitive": {
            "dig": "no_qualified_candidate",
            "return": "selected",
        },
        "source_lineage": support_lineage,
    }
    _write_json(support / "manifest.json", support_manifest)
    return {
        "source": source,
        "stage": stage,
        "support": support,
        "dig_config": dig_config,
        "return_config": return_config,
    }


def _run(
    paths: dict[str, Path],
    *,
    output_root: Path,
    candidate_calls: list[dict[str, Any]] | None = None,
    runner_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    candidate_calls = candidate_calls if candidate_calls is not None else []
    runner_calls = runner_calls if runner_calls is not None else []

    def candidate_loader(**kwargs: Any) -> SimpleNamespace:
        candidate_calls.append(dict(kwargs))
        return SimpleNamespace(candidate_id=RETURN_CANDIDATE)

    def assessor_builder(candidate: SimpleNamespace):
        assert candidate.candidate_id == RETURN_CANDIDATE
        return lambda _condition, _segment: {"status": "supported"}

    def stage_a_runner(**kwargs: Any) -> dict[str, Any]:
        runner_calls.append(dict(kwargs))
        return {
            "status": "completed",
            "output_root": str(kwargs["output_root"]),
            "manifest": {"schema": "act_goal_condition_sensitivity_manifest_v1"},
        }

    return binding.run_primitive_scoped_stage_a_support_audit(
        source_results_root=paths["source"],
        stage_a_v1_output_root=paths["stage"],
        support_audit_output_root=paths["support"],
        dig_training_config_path=paths["dig_config"],
        return_training_config_path=paths["return_config"],
        output_root=output_root,
        device="cpu",
        frozen_candidate_loader=candidate_loader,
        support_assessor_builder=assessor_builder,
        stage_a_runner=stage_a_runner,
    )


def test_binds_selected_return_v2_when_global_support_status_is_not_selected(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path, support_status="support_contract_not_selected")
    candidate_calls: list[dict[str, Any]] = []
    runner_calls: list[dict[str, Any]] = []

    result = _run(
        paths,
        output_root=tmp_path / "stage_a_mixed_support_v2",
        candidate_calls=candidate_calls,
        runner_calls=runner_calls,
    )

    assert result["status"] == "completed"
    assert candidate_calls == [
        {
            "candidates_json_path": paths["support"] / "candidates.json",
            "primitive": "return",
            "candidate_id": RETURN_CANDIDATE,
        }
    ]
    assert len(runner_calls) == 1
    call = runner_calls[0]
    assert set(call["support_assessors_by_primitive"]) == {"return"}
    assert set(call["support_lineage_by_primitive"]) == {"return"}
    assert call["support_lineage_by_primitive"]["return"] == {
        "support_contract_version": "support_contract_v2",
        "candidate_id": RETURN_CANDIDATE,
        "support_audit_status": "support_contract_not_selected",
        "support_audit_manifest": _record(paths["support"] / "manifest.json"),
        "support_audit_candidates": _record(paths["support"] / "candidates.json"),
    }
    assert result["primitive_scoped_support_binding"]["dig"] == {
        "support_contract_version": "support_contract_v1",
        "candidate_id": "axis_p01_p99_v1",
        "binding": "default_stage_a_runner_support",
    }
    assert result["primitive_scoped_support_binding"]["return"]["candidate_id"] == (
        RETURN_CANDIDATE
    )


def test_rejects_support_lineage_mismatch_before_candidate_or_stage_runner(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    manifest_path = paths["support"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_lineage"]["stage_a_return"]["sha256"] = "0" * 64
    _write_json(manifest_path, manifest)
    candidate_calls: list[dict[str, Any]] = []
    runner_calls: list[dict[str, Any]] = []

    with pytest.raises(binding.PrimitiveScopedSupportBindingError, match="SHA mismatch"):
        _run(
            paths,
            output_root=tmp_path / "new_stage_a",
            candidate_calls=candidate_calls,
            runner_calls=runner_calls,
        )
    assert candidate_calls == []
    assert runner_calls == []


def test_requires_independently_selected_return_and_allowed_audit_status(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path, support_status="artifact_invalid")

    with pytest.raises(binding.PrimitiveScopedSupportBindingError, match="cannot bind"):
        _run(paths, output_root=tmp_path / "new_stage_a")

    paths = _fixture(tmp_path / "missing_return")
    manifest_path = paths["support"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["selected_candidate_by_primitive"]["return"] = None
    _write_json(manifest_path, manifest)
    with pytest.raises(binding.PrimitiveScopedSupportBindingError, match="selected Return"):
        _run(paths, output_root=tmp_path / "missing_return" / "new_stage_a")


def test_output_root_must_be_new_and_outside_immutable_evidence(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError, match="already exists"):
        _run(paths, output_root=existing)
    with pytest.raises(binding.PrimitiveScopedSupportBindingError, match="distinct"):
        _run(paths, output_root=paths["stage"] / "nested_new_root")
