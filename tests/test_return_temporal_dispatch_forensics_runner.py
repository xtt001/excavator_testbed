from __future__ import annotations

import json
from pathlib import Path

import pytest

from testbed.eval import return_temporal_dispatch_forensics_runner as runner


def _clean_code() -> dict[str, object]:
    return {"git_head": "a" * 40, "git_branch": "test", "worktree_clean": True}


def _result() -> dict[str, object]:
    return {
        "schema": "return_temporal_dispatch_forensics_v1",
        "status": "completed",
        "evidence_kind": "teacher_forced_recorded_observation",
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "segments": [
            {
                "segment_id": "return:1-2:test",
                "forensic_ranking": {
                    "latest_response_suppressed_frame_count": 2,
                    "suppression_mechanism_summary": {
                        "historical_net_opposes_latest_response_frame_count": 1,
                        "latest_weight_dilution_without_net_opposition_frame_count": 1,
                        "latest_query_weight_min": 0.01,
                        "latest_query_weight_max": 0.02,
                    },
                },
            }
        ],
    }


def test_runner_writes_no_overwrite_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stability = tmp_path / "stability"
    stability.mkdir()
    (stability / "manifest.json").write_text("{}\n", encoding="utf-8")
    (stability / "return_segments.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(runner, "_clean_code_record", _clean_code)
    output = tmp_path / "forensics"

    result = runner.run_return_temporal_dispatch_forensics_artifact(
        return_stability_output_root=stability,
        output_root=output,
        device="cpu",
        replay_runner=lambda **_: _result(),
    )

    assert result["status"] == "completed"
    assert {path.name for path in output.iterdir()} == {
        "manifest.json",
        "forensics.json",
        "report.md",
    }
    payload = json.loads((output / "forensics.json").read_text(encoding="utf-8"))
    assert payload["promotion_eligible"] is False
    assert "历史净反向" in (output / "report.md").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError, match="already exists"):
        runner.run_return_temporal_dispatch_forensics_artifact(
            return_stability_output_root=stability,
            output_root=output,
            replay_runner=lambda **_: _result(),
        )


def test_runner_rejects_dirty_worktree_before_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        runner,
        "_clean_code_record",
        lambda: {"git_head": "a" * 40, "git_branch": "test", "worktree_clean": False},
    )
    called = False

    def replay(**_: object) -> dict[str, object]:
        nonlocal called
        called = True
        return _result()

    with pytest.raises(RuntimeError, match="clean Git worktree"):
        runner.run_return_temporal_dispatch_forensics_artifact(
            return_stability_output_root=tmp_path,
            output_root=tmp_path / "out",
            replay_runner=replay,
        )
    assert called is False
