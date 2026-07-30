from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from testbed.cli.wall_contact_semantics_experiment import build_parser
from testbed.eval.wall_contact_ab_lineage import (
    WallContactABLineageError,
    build_ab_lineage,
)
from testbed.eval.wall_contact_artifact_io import WallContactArtifactError
from testbed.eval.wall_contact_semantics_experiment import (
    initialize_wall_contact_semantics_experiment,
)
from testbed.eval.wall_contact_source_spec import (
    PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS,
    build_python_source_lineage,
    lock_python_source_lineage,
)


def test_cli_exposes_the_full_evidence_lifecycle() -> None:
    parser = build_parser()
    command_action = next(item for item in parser._actions if item.dest == "command")
    assert set(command_action.choices or {}) == {
        "build-ab-lineage",
        "build-source-spec",
        "initialize",
        "prepare",
        "collect-geometry",
        "collect-replay",
        "collect-ab",
        "finalize",
    }


def test_python_source_lineage_locks_fixed_inventory_and_detects_drift(
    tmp_path: Path,
) -> None:
    for index, relative in enumerate(PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS):
        source = tmp_path / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"# source {index}\n", encoding="utf-8")

    lineage = build_python_source_lineage(repo_root=tmp_path)
    references, aggregate_sha = lock_python_source_lineage(
        lineage,
        expected_repo_root=tmp_path,
    )

    assert [item["relative_path"] for item in references] == list(
        PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS
    )
    assert aggregate_sha == lineage["lineage_aggregate_sha256"]

    drifted = tmp_path / PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS[0]
    drifted.write_text("# drift\n", encoding="utf-8")
    with pytest.raises(
        WallContactArtifactError,
        match="python_lineage_file_0_sha256_drift",
    ):
        lock_python_source_lineage(
            lineage,
            expected_repo_root=tmp_path,
        )


def test_initialize_writes_failure_manifest_inside_unique_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "wall_contact_semantics_recovery_v1"
    kwargs = {
        "rollout_jsonl_path": tmp_path / "missing.jsonl",
        "planner_trace_path": tmp_path / "missing_trace.json",
        "target_episode_id": "episode_168",
        "target_raw_fields_sha256": "d" * 64,
        "target_cycle_index": 1,
        "full_source_dir": tmp_path,
        "split_path": tmp_path / "missing_split.yaml",
        "dig_primitives_dir": tmp_path,
        "execution_library_path": tmp_path / "missing_execution.json",
        "pose_library_path": tmp_path / "missing_pose.json",
        "legacy_sweep_path": tmp_path / "missing_sweep.json",
        "unity_repo_root": tmp_path,
        "contact_monitor_code_paths": [],
        "base_config_path": tmp_path / "missing_base.yaml",
        "output_root": root,
    }
    result = initialize_wall_contact_semantics_experiment(**kwargs)
    assert result["status"] == "blocked"
    assert (root / "experiment_manifest.json").is_file()
    with pytest.raises(FileExistsError):
        initialize_wall_contact_semantics_experiment(**kwargs)


def test_ab_lineage_uses_the_row_before_first_target_dig(
    tmp_path: Path,
) -> None:
    raw_sha = "d" * 64
    env = np.zeros(107, dtype=np.float64)
    env[28:31] = [1.0, 2.0, 3.0]
    env[39:45] = [0.01] * 6
    env[97] = 1234.0

    def row(
        *,
        t: int,
        step_id: int,
        skill: str,
        qpos: list[float],
        cycle: int,
    ) -> dict[str, object]:
        return {
            "t": t,
            "step_id": step_id,
            "skill_name": skill,
            "primitive_cycle_index": cycle,
            "qpos": qpos,
            "qvel": [0.01] * 4,
            "env_state": env.tolist(),
            "coverage_execution_exemplar_id": ("episode_168" if skill == "dig" else ""),
            "coverage_execution_raw_fields_sha256": (raw_sha if skill == "dig" else ""),
        }

    rollout = tmp_path / "rollout.jsonl"
    rows = [
        row(t=0, step_id=1, skill="return", qpos=[0.0] * 4, cycle=0),
        row(
            t=602,
            step_id=603,
            skill="return",
            qpos=[0.2] * 4,
            cycle=1,
        ),
        row(t=603, step_id=604, skill="dig", qpos=[0.9] * 4, cycle=1),
    ]
    rollout.write_text(
        "".join(json.dumps(item) + "\n" for item in rows),
        encoding="utf-8",
    )
    trace = tmp_path / "planner_trace.json"
    trace.write_text(
        json.dumps(
            {
                "coverage_decision_trace": [
                    {
                        "event": "select_actual_tuple_execution_candidate",
                        "cycle_index": 0,
                        "corridor_id": 1_000_168,
                        "exemplar_id": "episode_168",
                        "raw_fields_sha256": raw_sha,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "lineage"
    manifest = build_ab_lineage(
        rollout_jsonl_path=rollout,
        planner_trace_path=trace,
        target_episode_id="episode_168",
        target_raw_fields_sha256=raw_sha,
        target_cycle_index=1,
        output_dir=output,
    )

    handoff = json.loads(Path(manifest["frozen_target_handoff"]["path"]).read_text())
    reset = json.loads(Path(manifest["expected_reset_state"]["path"]).read_text())
    assert handoff["handoff_t"] == 602
    assert handoff["first_dig_t"] == 603
    assert handoff["selection_event_cycle_index"] == 0
    assert handoff["qpos"] == [0.2] * 4
    assert handoff["corridor_id"] == 1_000_168
    assert reset["reset_t"] == 0
    assert reset["qpos"] == [0.0] * 4
    assert reset["checkpoint_semantics"] == "first_post_reset_control_step"
    with pytest.raises(FileExistsError):
        build_ab_lineage(
            rollout_jsonl_path=rollout,
            planner_trace_path=trace,
            target_episode_id="episode_168",
            target_raw_fields_sha256=raw_sha,
            target_cycle_index=1,
            output_dir=output,
        )
    trace_payload = json.loads(trace.read_text())
    trace_payload["coverage_decision_trace"][0]["cycle_index"] = 1
    trace.write_text(json.dumps(trace_payload), encoding="utf-8")
    with pytest.raises(
        WallContactABLineageError,
        match="target_planner_selection_cycle_drift",
    ):
        build_ab_lineage(
            rollout_jsonl_path=rollout,
            planner_trace_path=trace,
            target_episode_id="episode_168",
            target_raw_fields_sha256=raw_sha,
            target_cycle_index=1,
            output_dir=tmp_path / "wrong_cycle",
        )
    with pytest.raises(
        WallContactABLineageError,
        match="target_planner_lineage_not_unique",
    ):
        build_ab_lineage(
            rollout_jsonl_path=rollout,
            planner_trace_path=trace,
            target_episode_id="episode_168",
            target_raw_fields_sha256="e" * 64,
            target_cycle_index=1,
            output_dir=tmp_path / "wrong_lineage",
        )
