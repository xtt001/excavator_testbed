from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from testbed.eval import act_support_contract_audit_runner as runner


def test_runner_rejects_dirty_worktree_before_source_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    touched = False

    def unexpected(*_args, **_kwargs):
        nonlocal touched
        touched = True
        raise AssertionError("source reads must not run with dirty code")

    monkeypatch.setattr(
        runner,
        "_clean_code_record",
        lambda: {"git_head": "x", "git_branch": "test", "worktree_clean": False},
    )
    monkeypatch.setattr(runner, "_source_paths", unexpected)

    with pytest.raises(RuntimeError, match="clean Git worktree"):
        runner.run_support_contract_audit_from_files(
            source_results_root=tmp_path,
            stage_a_output_root=tmp_path,
            dig_training_config_path=tmp_path / "dig.yaml",
            return_training_config_path=tmp_path / "return.yaml",
            output_root=tmp_path / "out",
        )
    assert touched is False


def test_runner_requires_stage_a_lineage_to_match_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "rollouts").mkdir(parents=True)
    (source / "hdf5_rollouts").mkdir()
    for path in (
        source / "eval_resolved_config.yaml",
        source / "eval_run_metadata.json",
        source / "rollouts" / "rollout_000.jsonl",
        source / "hdf5_rollouts" / "episode_0.hdf5",
    ):
        path.write_text("{}\n", encoding="utf-8")
    stage = tmp_path / "stage"
    stage.mkdir()
    for name in ("baseline.json", "dig.json", "return.json"):
        (stage / name).write_text("{}\n", encoding="utf-8")
    (stage / "manifest.json").write_text(
        json.dumps(
            {
                "schema": runner.STAGE_A_MANIFEST_SCHEMA,
                "status": "completed",
                "evidence_kind": runner.EVIDENCE_KIND,
                "diagnostic_only": True,
                "promotion_eligible": False,
                "source_lineage": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="lineage mismatch"):
        runner._validate_stage_a_manifest(
            json.loads((stage / "manifest.json").read_text()),
            source_paths=runner._source_paths(source),
        )


def test_alignment_contract_preserves_recorded_metadata_without_guessing_units(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hdf5_path = tmp_path / "episode.hdf5"
    import h5py

    with h5py.File(hdf5_path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.attrs["qpos_order"] = "swing_position_norm,boom_position_norm"
        metadata.attrs["qvel_order"] = "swing_speed,boom_speed"
        metadata.attrs["camera_names"] = "stick_up,stick_down,eye_left,eye_right"
    result = runner._alignment_and_field_contract(
        hdf5_path,
        target_segments={"dig": [SimpleNamespace()], "return": [SimpleNamespace(), SimpleNamespace()]},
    )
    assert result["qpos_order"].startswith("swing_position_norm")
    assert result["qvel_order"].startswith("swing_speed")
    assert "units" not in result
    assert result["target_segment_counts"] == {"dig": 1, "return": 2}


def test_support_input_lineage_records_the_exact_split_hash(tmp_path: Path) -> None:
    split = tmp_path / "split.yaml"
    split.write_text("train_ids: []\n", encoding="utf-8")

    rows = SimpleNamespace(
        split_path=str(split),
        as_dict=lambda: {"skill_name": "return", "validation_row_count": 4},
    )

    lineage = runner._support_input_lineage({"return": rows})

    assert lineage["return"]["skill_name"] == "return"
    assert lineage["return"]["split_sha256"] == runner._sha256(split)
