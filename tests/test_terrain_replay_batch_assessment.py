from __future__ import annotations

import json
from pathlib import Path

import tomllib

from testbed.cli.terrain_replay_batch_assessment import main as cli_main
from testbed.eval.terrain_replay_batch_assessment import (
    build_replay_batch_assessment,
)


def _gate(
    episode_id: str,
    *,
    passed: bool,
    source_cycles: int,
    effect_cycles: int,
    grade: str,
) -> dict[str, object]:
    return {
        "schema": "terrain_replay_pilot_gate_v2",
        "status": "present",
        "required_source_episode_id": episode_id,
        "pass": passed,
        "process_integrity_pass": True,
        "episode_semantic_pass": passed,
        "semantic_grade": grade,
        "source_complete_cycle_count": source_cycles,
        "effect_usable_source_cycle_count": effect_cycles,
        "variance_tier_counts": {"A": 2, "B": 4, "C": 2},
        "failed_checks": [] if passed else ["semantic_pass_repeat_count_below_minimum"],
        "validation_errors": [],
    }


def test_batch_assessment_separates_source_act_semantic_and_effect_counts() -> None:
    result = build_replay_batch_assessment(
        [
            _gate(
                "episode_28",
                passed=True,
                source_cycles=27,
                effect_cycles=20,
                grade="B",
            ),
            _gate(
                "episode_29",
                passed=False,
                source_cycles=33,
                effect_cycles=25,
                grade="C",
            ),
        ],
        source_cycle_records=[
            {
                "source_episode_id": "episode_28",
                "cycle_id": index,
                "act_training_eligible": True,
                "replay_candidate": True,
            }
            for index in range(27)
        ]
        + [
            {
                "source_episode_id": "episode_29",
                "cycle_id": index,
                "act_training_eligible": index != 0,
                "replay_candidate": True,
            }
            for index in range(33)
        ]
        + [
            {
                "source_episode_id": "episode_29",
                "cycle_id": 33,
                "act_training_eligible": True,
                "replay_candidate": False,
            }
        ],
        expected_episode_ids=["episode_28", "episode_29"],
    )

    assert result["schema"] == "terrain_replay_batch_assessment_v1"
    assert result["status"] == "present"
    assert result["semantic_usable_episode_count"] == 1
    assert result["semantic_rejected_episode_count"] == 1
    assert result["source_replay_candidate_cycle_count"] == 60
    assert result["source_act_training_eligible_cycle_count"] == 60
    assert result["semantic_replay_usable_source_cycle_count"] == 27
    # Stable local effects and strict episode-admitted effects stay separate.
    assert result["effect_relabel_process_stable_source_cycle_count"] == 45
    assert result["effect_relabel_strict_source_cycle_count"] == 20
    assert result["effect_relabel_strict_fraction_of_semantic_cycles"] == 20 / 27
    assert result["grade_counts"] == {"A": 0, "B": 1, "C": 1}


def test_batch_assessment_reports_missing_or_duplicate_episode_gates() -> None:
    gate = _gate(
        "episode_28",
        passed=True,
        source_cycles=27,
        effect_cycles=20,
        grade="B",
    )
    result = build_replay_batch_assessment(
        [gate, gate],
        source_cycle_records=[
            {
                "source_episode_id": "episode_28",
                "cycle_id": index,
                "act_training_eligible": True,
                "replay_candidate": True,
            }
            for index in range(27)
        ],
        expected_episode_ids=["episode_28", "episode_29"],
    )

    assert result["status"] == "invalid_batch_assessment"
    assert set(result["validation_errors"]) == {
        "duplicate gate for episode_28",
        "missing gate for episode_29",
    }


def test_batch_assessment_rejects_invalid_gate_or_source_cycle_mismatch() -> None:
    gate = _gate(
        "episode_28",
        passed=False,
        source_cycles=2,
        effect_cycles=0,
        grade="C",
    )
    gate["status"] = "invalid_inputs"
    result = build_replay_batch_assessment(
        [gate],
        source_cycle_records=[
            {
                "source_episode_id": "episode_28",
                "cycle_id": 0,
                "act_training_eligible": True,
                "replay_candidate": True,
            }
        ],
        expected_episode_ids=["episode_28"],
    )

    assert result["status"] == "invalid_batch_assessment"
    assert set(result["validation_errors"]) == {
        "gate for episode_28 has status invalid_inputs",
        "gate/source replay cycle count mismatch for episode_28: 2 != 1",
    }


def test_batch_assessment_cli_writes_no_overwrite_report(tmp_path) -> None:
    gate_path = tmp_path / "episode_28_gate.json"
    selection_path = tmp_path / "selection.jsonl"
    eligibility_path = tmp_path / "eligibility.jsonl"
    output_path = tmp_path / "batch.json"
    gate_path.write_text(
        json.dumps(
            _gate(
                "episode_28",
                passed=True,
                source_cycles=1,
                effect_cycles=1,
                grade="A",
            )
        ),
        encoding="utf-8",
    )
    selection_path.write_text(
        json.dumps(
            {
                "source_episode_id": "episode_28",
                "cycle_id": 0,
                "act_training_eligible": True,
                "replay_candidate": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    eligibility_path.write_text(
        selection_path.read_text(encoding="utf-8")
        + json.dumps(
            {
                "source_episode_id": "episode_28",
                "cycle_id": 1,
                "act_training_eligible": True,
                "replay_candidate": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rc = cli_main(
        [
            "--gate-json",
            str(gate_path),
            "--selection-manifest",
            str(selection_path),
            "--cycle-eligibility-jsonl",
            str(eligibility_path),
            "--output-json",
            str(output_path),
        ]
    )

    assert rc == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "present"
    assert report["source_replay_candidate_cycle_count"] == 1
    assert report["source_act_training_eligible_cycle_count"] == 2


def test_batch_assessment_cli_entrypoint_registered() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"][
        "tb-terrain-replay-batch-assessment"
    ] == "testbed.cli.terrain_replay_batch_assessment:main"
