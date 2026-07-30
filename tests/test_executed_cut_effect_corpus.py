from __future__ import annotations

import json
from pathlib import Path

import pytest

import testbed.cli.build_executed_cut_effect_samples as cli_module
import testbed.eval.executed_cut_effect_corpus as corpus_module
from testbed.cli.build_executed_cut_effect_samples import main as cli_main
from testbed.eval.executed_cut_effect_corpus import (
    build_executed_cut_effect_corpus,
    load_strict_replay_manifest,
    write_executed_cut_effect_corpus,
)


def _write_view_manifest(root: Path, rows: list[dict]) -> None:
    root.mkdir(parents=True)
    (root / "view_manifest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _manifest_row(root: Path, episode_id: str, evidence_kind: str) -> dict:
    wrapper = root / f"{episode_id}.hdf5"
    wrapper.touch()
    return {
        "schema": "terrain_replay_composite_episode_v1",
        "source_episode_id": episode_id,
        "evidence_kind": evidence_kind,
        "wrapper_path": str(wrapper),
    }


def test_strict_manifest_rejects_partial_salvage_rows(tmp_path: Path) -> None:
    root = tmp_path / "combined"
    root.mkdir()
    rows = [
        _manifest_row(root, "episode_3", "strict_parent_selected_replay"),
        _manifest_row(root, "episode_4", "partial_salvage_addition"),
    ]
    (root / "view_manifest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="partial_salvage_addition"):
        load_strict_replay_manifest(root)


def test_corpus_builder_uses_manifest_wrappers_and_writes_no_overwrite_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "combined"
    root.mkdir()
    rows = [
        _manifest_row(root, "episode_3", "strict_parent_selected_replay"),
        _manifest_row(root, "episode_9", "strict_salvage_addition"),
    ]
    (root / "view_manifest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    def fake_builder(path: Path, **_: object) -> dict:
        episode_id = path.stem
        return {
            "status": "present",
            "episode_id": episode_id,
            "eligible_cycle_count": 1,
            "record_count": 1,
            "rejected_eligible_cycle_count": 0,
            "skipped_ineligible_cycle_count": 0,
            "rejections": [],
            "records": [
                {
                    "schema": "executed_cut_silver_sample_v1",
                    "episode_id": episode_id,
                    "cycle_id": 0,
                    "executed_cut": {
                        "actual_surface_penetration_peak_m": 0.2,
                        "length_m": 0.75,
                        "entry_x_m": 0.1,
                        "entry_z_m": -0.2,
                        "exit_x_m": 0.6,
                        "exit_z_m": -0.2,
                        "direction_x": 1.0,
                        "direction_z": 0.0,
                    },
                }
            ],
        }

    monkeypatch.setattr(
        corpus_module,
        "build_executed_cut_silver_samples_from_hdf5",
        fake_builder,
    )
    corpus = build_executed_cut_effect_corpus(root, expected_episode_count=2)
    records_path = tmp_path / "samples.jsonl"
    manifest_path = tmp_path / "samples_manifest.json"

    written = write_executed_cut_effect_corpus(
        corpus,
        records_jsonl_path=records_path,
        manifest_json_path=manifest_path,
    )

    assert corpus["status"] == "present"
    assert corpus["episode_count"] == 2
    assert corpus["record_count"] == 2
    assert corpus["strict_evidence_kind_counts"] == {
        "strict_parent_selected_replay": 1,
        "strict_salvage_addition": 1,
    }
    assert corpus["capability_model_status"] == "rule_only_due_to_class_imbalance"
    assert (
        corpus["strict_cut_support_envelope"]["source"]
        == "strict_replay_p01_p99"
    )
    assert corpus["strict_cut_support_envelope"]["fields"]["cut_length_m"] == [
        0.75,
        0.75,
    ]
    assert written["status"] == "present"
    assert len(records_path.read_text(encoding="utf-8").splitlines()) == 2
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["record_count"] == 2

    second = write_executed_cut_effect_corpus(
        corpus,
        records_jsonl_path=records_path,
        manifest_json_path=manifest_path,
    )
    assert second["status"] == "output_path_already_exists"


def test_corpus_cli_keeps_the_strict_episode_count_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_build(source_root: Path, **kwargs: object) -> dict:
        captured["source_root"] = source_root
        captured.update(kwargs)
        return {"schema": "executed_cut_silver_corpus_v1", "status": "present"}

    def fake_write(corpus: dict, **kwargs: object) -> dict:
        captured["corpus"] = corpus
        captured.update(kwargs)
        return {"status": "present", "record_count": 439}

    monkeypatch.setattr(cli_module, "build_executed_cut_effect_corpus", fake_build)
    monkeypatch.setattr(cli_module, "write_executed_cut_effect_corpus", fake_write)

    exit_code = cli_main(
        [
            "--source-root",
            str(tmp_path / "strict"),
            "--expected-episode-count",
            "18",
            "--records-jsonl",
            str(tmp_path / "samples.jsonl"),
            "--manifest-json",
            str(tmp_path / "manifest.json"),
        ]
    )

    assert exit_code == 0
    assert captured["expected_episode_count"] == 18
    assert captured["effective_move_min_volume_m3"] is None
