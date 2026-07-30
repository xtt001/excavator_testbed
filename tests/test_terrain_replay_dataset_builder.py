from __future__ import annotations

import json
from pathlib import Path

import pytest

from testbed.cli.build_terrain_replay_dataset import build_parser
from testbed.data.terrain_replay_dataset import sha256_file
from testbed.eval.terrain_replay_dataset_builder import (
    _collect_selected_manifest,
    _smoke_failures_are_semantic_only,
    _write_json_atomic,
    initialize_run_root,
    ordered_replay_episode_ids,
    resolve_dataset_build_status,
    run_attempt_sequence,
)
from testbed.eval.terrain_replay_run_contract import (
    DEFAULT_OUTPUT_ROOT,
    RUN_CONTRACT_SCHEMA,
    replay_control_profile_for_episode,
)


def test_attempt_sequence_stops_at_first_pass() -> None:
    called: list[int] = []

    def run(attempt_index: int) -> dict[str, object]:
        called.append(attempt_index)
        return {
            "attempt_id": f"attempt_{attempt_index:02d}",
            "pass": attempt_index >= 2,
        }

    result = run_attempt_sequence(run_attempt=run, max_attempts=5)

    assert called == [0, 1, 2]
    assert result["status"] == "selected"
    assert result["selected_attempt_id"] == "attempt_02"


def test_attempt_sequence_exhausts_after_five_failures() -> None:
    called: list[int] = []

    def run(attempt_index: int) -> dict[str, object]:
        called.append(attempt_index)
        return {"attempt_id": f"attempt_{attempt_index:02d}", "pass": False}

    result = run_attempt_sequence(run_attempt=run, max_attempts=5)

    assert called == [0, 1, 2, 3, 4]
    assert result["status"] == "exhausted_no_pass"
    assert result["selected_attempt_id"] is None


def test_run_root_is_no_overwrite_and_resume_contract_is_exact(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    contract = {"schema": "test", "config_sha256": "abc", "episode_ids": [1, 2]}

    first = initialize_run_root(output_root=output, contract=contract, resume=False)
    assert first["resumed"] is False

    with pytest.raises(FileExistsError, match="no-overwrite"):
        initialize_run_root(output_root=output, contract=contract, resume=False)

    resumed = initialize_run_root(output_root=output, contract=contract, resume=True)
    assert resumed["resumed"] is True

    with pytest.raises(ValueError, match="run contract mismatch"):
        initialize_run_root(
            output_root=output,
            contract={**contract, "config_sha256": "changed"},
            resume=True,
        )

    stored = json.loads((output / "run_contract.json").read_text())
    assert stored == contract


def test_episode_order_keeps_smokes_first_and_risk_last() -> None:
    ordered = ordered_replay_episode_ids()
    assert ordered[:3] == (28, 1, 19)
    assert ordered[-3:] == (9, 16, 20)
    assert len(ordered) == 24
    assert len(set(ordered)) == 24


def test_corrected_calibration_replay_uses_a_new_run_contract_root() -> None:
    assert RUN_CONTRACT_SCHEMA == "terrain_replay_selected_dataset_run_contract_v3"
    assert DEFAULT_OUTPUT_ROOT.name.endswith(
        "_cycle_action_calibrated_replay_selected_control_compatible_v2"
    )


def test_replay_control_profile_routes_pre_and_post_sources_separately() -> None:
    assert replay_control_profile_for_episode(19) == "recording_pre_fix_v1"
    assert replay_control_profile_for_episode(28) == "production"
    with pytest.raises(ValueError, match="fixed 24-source inventory"):
        replay_control_profile_for_episode(22)


def test_representative_smoke_failure_is_not_reported_as_hard_contract_error() -> None:
    status = resolve_dataset_build_status(
        batch_stop={
            "reason": "representative_smoke_exhausted",
            "episode_ids": [1, 19],
        },
        stop_after_smokes=True,
        all_episodes_selected=False,
    )

    assert status == "halted_representative_smoke_failure"


def test_continue_after_smoke_failure_flag_is_explicit() -> None:
    args = build_parser().parse_args(
        ["--resume", "--continue-after-smoke-semantic-failure"]
    )

    assert args.resume is True
    assert args.continue_after_smoke_semantic_failure is True


def test_smoke_override_accepts_only_technical_pass_semantic_failures(
    tmp_path: Path,
) -> None:
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(
        json.dumps(
            {
                "pass": False,
                "process_integrity_pass": True,
                "semantic_attempt_pass": False,
                "hdf5_audit_pass": True,
                "failed_checks": ["semantic_attempt_failed"],
                "validation_errors": [],
            }
        ),
        encoding="utf-8",
    )
    episode_result = {
        "source_episode_id": "episode_1",
        "status": "exhausted_no_pass",
        "attempt_count": 5,
        "attempts": [
            {
                "process_returncode": 0,
                "hard_contract_errors": [],
                "gate_path": str(gate_path),
            }
            for _ in range(5)
        ],
    }

    assert _smoke_failures_are_semantic_only([episode_result], [1]) is True

    bad_gate = json.loads(gate_path.read_text(encoding="utf-8"))
    bad_gate["hdf5_audit_pass"] = False
    gate_path.write_text(json.dumps(bad_gate), encoding="utf-8")

    assert _smoke_failures_are_semantic_only([episode_result], [1]) is False


def test_selected_manifest_rewrites_attempt_path_to_final_hdf5(
    tmp_path: Path,
) -> None:
    selected = tmp_path / "selected_full_hdf5" / "episode_28.hdf5"
    selected.parent.mkdir(parents=True)
    selected.write_bytes(b"selected")
    record_path = (
        tmp_path / "attempts" / "episode_28" / "attempt_00" / "selected_record.json"
    )
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps(
            {
                "source_episode_id": "episode_28",
                "selected_hdf5_path": str(selected),
                "sha256": sha256_file(selected),
                "lineage": {
                    "replay_path": str(
                        record_path.parent / "recorded" / "episode_0.hdf5"
                    )
                },
            }
        ),
        encoding="utf-8",
    )

    rows = _collect_selected_manifest(tmp_path, [])

    assert rows[0]["lineage"]["replay_path"] == str(selected.resolve())


def test_builder_atomic_writer_remains_available_after_attempt_extraction(
    tmp_path: Path,
) -> None:
    target = tmp_path / "payload.json"

    _write_json_atomic(target, {"status": "ok"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"status": "ok"}
