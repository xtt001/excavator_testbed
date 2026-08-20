from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from testbed.eval import return_temporal_dispatch_validation_runner as runner


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _record(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _clean_code() -> dict[str, object]:
    return {"git_head": "a" * 40, "git_branch": "test", "worktree_clean": True}


def _evaluation() -> dict[str, object]:
    strategy = {
        "strategy": {"strategy_id": "newest_first_100_decay_0p01"},
        "pre_registered_gates": {
            "every_pair_reaches_fixed_80_percent_response": True,
            "quality_is_no_worse_than_legacy": True,
        },
        "passes_pre_registered_selection": True,
        "aggregate": {"response": {"active_frame_fraction": 0.9}},
    }
    return {
        "schema": "return_temporal_dispatch_validation_evaluation_v1",
        "evidence_kind": "teacher_forced_source_disjoint_held_validation",
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "target_stage_a_failures_used": False,
        "runtime_default_changed": False,
        "input_scope": {"target_rollout_input_accepted": False},
        "sample": {"sampled_segment_count": 16},
        "metric_contract": {"required_active_frame_fraction": 0.8},
        "policy_verification": {"all_pairs_passed": True},
        "strategies": {
            "legacy_100_oldest_first_decay_0p01": strategy,
            "newest_first_100_decay_0p01": strategy,
        },
        "selection": {
            "selected_strategy_id": "newest_first_100_decay_0p01",
            "runtime_default_changed": False,
        },
        "interpretation_limit": "shadow only",
    }


def _lineage_fixture(tmp_path: Path) -> tuple[Path, Path]:
    checkpoint = tmp_path / "policy_best.ckpt"
    stats = tmp_path / "dataset_stats.pkl"
    train = tmp_path / "return_train.yaml"
    eval_config = tmp_path / "eval.yaml"
    checkpoint.write_bytes(b"checkpoint")
    stats.write_bytes(b"stats")
    train.write_text("task: {}\n", encoding="utf-8")
    eval_config.write_text(
        yaml.safe_dump({"task": {}, "policy": {}, "eval": {}}), encoding="utf-8"
    )
    manifest = tmp_path / "stability_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "return_goal_response_stability_audit_manifest_v1",
                "status": "completed",
                "diagnostic_only": True,
                "promotion_eligible": False,
                "closed_loop_claim": False,
                "torch_performance": {
                    "allow_tf32": False,
                    "cudnn_benchmark": False,
                    "matmul_precision": "highest",
                },
                "source_lineage": {
                    "return_checkpoint": _record(checkpoint),
                    "return_dataset_stats": _record(stats),
                    "return_training_config": _record(train),
                    "eval_resolved_config": _record(eval_config),
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest, train


def test_runner_writes_no_overwrite_shadow_candidate_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, train = _lineage_fixture(tmp_path)
    split = tmp_path / "split.yaml"
    split.write_text("split: immutable\n", encoding="utf-8")
    dataset = tmp_path / "return"
    dataset.mkdir()
    population = type(
        "Population",
        (),
        {"split_path": str(split), "primitive_dataset_dir": str(dataset)},
    )()
    monkeypatch.setattr(runner, "_clean_code_record", _clean_code)
    monkeypatch.setattr(
        runner,
        "load_strict_return_temporal_dispatch_validation_population",
        lambda **_: population,
    )
    monkeypatch.setattr(
        runner,
        "build_source_balanced_return_temporal_dispatch_sample",
        lambda _: object(),
    )
    monkeypatch.setattr(
        runner,
        "eval_torch_performance_config",
        lambda _: type("Perf", (), {"as_config_dict": lambda self: {
            "allow_tf32": False, "cudnn_benchmark": False, "matmul_precision": "highest"
        }})(),
    )
    monkeypatch.setattr(runner, "configure_torch_performance", lambda *_args, **_kwargs: None)
    output = tmp_path / "dispatch"

    result = runner.run_return_temporal_dispatch_validation_from_file(
        return_training_config_path=train,
        checkpoint_lineage_manifest_path=manifest,
        output_root=output,
        device="cpu",
        evaluation_runner=lambda **_: _evaluation(),
        policy_factory=lambda _label: object(),
    )

    assert result["status"] == "completed"
    assert result["selected_strategy_id"] == "newest_first_100_decay_0p01"
    assert {path.name for path in output.iterdir()} == {
        "manifest.json",
        "candidates.json",
        "validation.json",
        "report.md",
    }
    validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    assert validation["target_stage_a_failures_used"] is False
    with pytest.raises(FileExistsError, match="already exists"):
        runner.run_return_temporal_dispatch_validation_from_file(
            return_training_config_path=train,
            checkpoint_lineage_manifest_path=manifest,
            output_root=output,
            evaluation_runner=lambda **_: _evaluation(),
            policy_factory=lambda _label: object(),
        )


def test_runner_requires_clean_code_before_loading_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        runner,
        "_clean_code_record",
        lambda: {"git_head": "a" * 40, "git_branch": "test", "worktree_clean": False},
    )
    called = False

    def load_population(**_: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("should not run")

    monkeypatch.setattr(runner, "load_strict_return_temporal_dispatch_validation_population", load_population)
    with pytest.raises(RuntimeError, match="clean Git worktree"):
        runner.run_return_temporal_dispatch_validation_from_file(
            return_training_config_path=tmp_path / "missing.yaml",
            checkpoint_lineage_manifest_path=tmp_path / "missing.json",
            output_root=tmp_path / "out",
        )
    assert called is False
