from __future__ import annotations

import json
from pathlib import Path

from testbed.cli.planner_evidence import main


def test_planner_evidence_cli_classifies_rollout_jsonl(tmp_path: Path) -> None:
    rollout_path = tmp_path / "rollout.jsonl"
    rollout_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "t": 0,
                        "step_id": 1,
                        "skill_name": "bootstrap",
                        "skill_switch_reason": "",
                        "action": [0.0, 0.0, 0.0, 0.0],
                        "goal_tokens": [0.0, 1.0],
                        "transition_timeout": False,
                        "transition_completed": False,
                    }
                ),
                json.dumps(
                    {
                        "t": 1,
                        "step_id": 2,
                        "skill_name": "dig",
                        "skill_switch_reason": "pre_dig_align_to_dig_ready",
                        "action": [0.0, 0.1, 0.0, -0.2],
                        "goal_tokens": [0.0, 1.0],
                        "dig_cut_token_injected": True,
                        "dig_cut_token_source": "coverage_corridor",
                        "coverage_corridor_id": 2,
                        "dig_step_count": 1,
                        "dig_best_mass_kg": 12.5,
                        "transition_timeout": False,
                        "transition_completed": False,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_json = tmp_path / "report.json"
    output_md = tmp_path / "report.md"
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "primitive_final_skill": "dig",
                "primitive_cycle_index": 1,
                "completed_transition_count": 1,
                "coverage_terminal_stop_requested": 0,
            }
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "classify",
            "--rollout-jsonl",
            str(rollout_path),
            "--rollout-summary",
            str(summary_path),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ]
    )

    assert rc == 0
    report = json.loads(output_json.read_text(encoding="utf-8"))
    by_id = {row["capability_id"]: row for row in report["rows"]}
    assert by_id["execution.predict_tick"]["classification"] == "confirmed-live"
    assert by_id["token.dig_cut"]["classification"] == "confirmed-live"
    assert by_id["coverage.corridor"]["classification"] == "confirmed-live"
    assert by_id["metric.dig_progress"]["classification"] == "support-live"
    assert by_id["report.rollout_summary"]["classification"] == "report-only"
    assert "Planner Evidence Classification Report" in output_md.read_text(
        encoding="utf-8"
    )
