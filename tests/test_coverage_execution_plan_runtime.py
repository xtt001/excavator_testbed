from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from testbed.eval.coverage_replan_replay import (
    COVERAGE_EXECUTION_PREFLIGHT_FILENAME,
    _hydrate_pre_contact_state,
    _production_static_config,
    _read_hdf5_observation,
    _read_jsonl_step,
    build_coverage_execution_preflight,
)
from testbed.planner.primitive.coverage.config import (
    CoverageExecutionLibraryConfig,
)
from testbed.planner.primitive.coverage.selection_runtime import (
    PrimitiveCoverageSelectionRuntime,
    PrimitiveCoverageSelectionRuntimePorts,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.coverage.wall_safety import (
    NoWallSafeCorridorError,
)
from testbed.planner.primitive.facts.capabilities import (
    PrimitiveObservationFacts,
)

_LIBRARY = Path(
    "/data/pingfan/excavator_testbed_data/"
    "yulong_strict18_terrain_residual_v0/qc/"
    "strict_train_coverage_execution_library_v1_1.json"
)
_LIBRARY_SHA256 = (
    "b47e69be47f6da7d0a5fa0c168170ab771af3823269167f8b2ce64374da91614"
)
_FAILURE_ROOT = Path(
    "/data/pingfan/excavator_testbed_runs/eval/"
    "yulong_strict18_terrain_residual_v0/"
    "functional_10cycle_a0_wall_safe_1x10_v1/results"
)
_ROLLOUT_HDF5 = _FAILURE_ROOT / "hdf5_rollouts/episode_0.hdf5"
_ROLLOUT_JSONL = _FAILURE_ROOT / "rollouts/rollout_000.jsonl"
_RESOLVED_CONFIG = _FAILURE_ROOT / "eval_resolved_config.yaml"
_HAS_FROZEN_EVIDENCE = all(
    path.is_file()
    for path in (
        _LIBRARY,
        _ROLLOUT_HDF5,
        _ROLLOUT_JSONL,
        _RESOLVED_CONFIG,
    )
)


def _runtime(
    *,
    library_sha256: str = _LIBRARY_SHA256,
) -> tuple[
    PrimitiveCoverageSelectionRuntime,
    CoverageRuntimeState,
    dict,
]:
    config = yaml.safe_load(_RESOLVED_CONFIG.read_text(encoding="utf-8"))
    config = copy.deepcopy(config)
    config["policy"]["dig_cut_planner"]["coverage"][
        "actual_tuple_execution_library"
    ] = {
        "enabled": True,
        "path": str(_LIBRARY),
        "artifact_sha256": library_sha256,
        "mode": "exact_k1",
        "missing_contract": "fail_closed",
        "hard_bottom_margin_m": 0.02,
    }
    static_config = _production_static_config(config)
    state = CoverageRuntimeState()
    events: list[dict] = []
    runtime = PrimitiveCoverageSelectionRuntime.from_ports(
        PrimitiveCoverageSelectionRuntimePorts(
            state=state,
            static_config=static_config,
            cycle_index=lambda: 5,
            observation_facts=lambda obs: PrimitiveObservationFacts.from_obs(
                obs,
                action_dim=4,
            ),
            maybe_reopen_pass=lambda _obs, _reason: False,
            request_terminal_stop=lambda reason: state.set_terminal_stop(
                requested=True,
                reason=str(reason),
            ),
            record_decision_event=lambda event, **kwargs: events.append(
                {
                    "event": str(event),
                    "extra": dict(kwargs.get("extra", {}) or {}),
                }
            ),
        )
    )
    runtime.ensure_coverage_corridors()
    _hydrate_pre_contact_state(
        state,
        _read_jsonl_step(_ROLLOUT_JSONL, 2935),
    )
    state.mark_depth_exhausted_physical_cell(5)
    return (
        runtime,
        state,
        _read_hdf5_observation(_ROLLOUT_HDF5, 2987),
    )


@pytest.mark.skipif(
    not _HAS_FROZEN_EVIDENCE,
    reason="strict-18 frozen production replay evidence is unavailable",
)
def test_production_runtime_selects_episode168_as_one_exact_tuple() -> None:
    runtime, state, observation = _runtime()
    library = json.loads(_LIBRARY.read_text(encoding="utf-8"))
    expected = next(
        item
        for item in library["records"]
        if item["exemplar_id"] == "episode_168"
    )

    corridor, raw_fields = runtime.select_next_coverage_plan(
        observation,
        update_state=True,
    )

    assert corridor.corridor_id == 1_000_168
    assert corridor.cell_id == 1
    assert raw_fields == expected["raw_fields"]
    assert state.coverage_active_execution_exemplar_id == "episode_168"
    assert state.coverage_active_effect_outcome_cell_id == 1
    assert state.coverage_active_return_envelope_cell_id == 0
    assert state.coverage_active_execution_raw_fields == expected["raw_fields"]
    assert state.coverage_active_execution_tail_plane_depth_reserve_m == (
        pytest.approx(0.0034275054931640625)
    )
    assert state.coverage_active_execution_trace[
        "live_swept_physical_cell_ids"
    ] == [1, 3]
    assert state.coverage_active_execution_trace[
        "wall_minimum_clearance_m"
    ] == pytest.approx(0.3736593339760881)
    assert state.coverage_active_execution_trace[
        "planned_hard_bottom_budget_after_tail_m"
    ] == pytest.approx(0.06074000895023346)
    assert sum(
        item["status"] == "selected"
        for item in state.coverage_candidate_scores
    ) == 1
    assert len(state.coverage_candidate_scores) <= 6
    assert state.coverage_active_execution_trace[
        "coverage_execution_candidate_trace_total_count"
    ] == 374
    assert "coverage_candidate_scores" not in (
        state.coverage_active_execution_trace
    )


@pytest.mark.skipif(
    not _HAS_FROZEN_EVIDENCE,
    reason="strict-18 frozen production replay evidence is unavailable",
)
def test_first_dig_equal_state_tie_keeps_a0_nearest_entry_semantics() -> None:
    config = yaml.safe_load(_RESOLVED_CONFIG.read_text(encoding="utf-8"))
    config = copy.deepcopy(config)
    config["policy"]["dig_cut_planner"]["coverage"][
        "actual_tuple_execution_library"
    ] = {
        "enabled": True,
        "path": str(_LIBRARY),
        "artifact_sha256": _LIBRARY_SHA256,
        "mode": "exact_k1",
        "missing_contract": "fail_closed",
        "hard_bottom_margin_m": 0.02,
    }
    static_config = _production_static_config(config)
    state = CoverageRuntimeState()
    runtime = PrimitiveCoverageSelectionRuntime.from_ports(
        PrimitiveCoverageSelectionRuntimePorts(
            state=state,
            static_config=static_config,
            cycle_index=lambda: 0,
            observation_facts=lambda obs: PrimitiveObservationFacts.from_obs(
                obs,
                action_dim=4,
            ),
            maybe_reopen_pass=lambda _obs, _reason: False,
            request_terminal_stop=lambda _reason: None,
            record_decision_event=lambda _event, **_kwargs: None,
        )
    )

    corridor, _ = runtime.select_next_coverage_plan(
        _read_hdf5_observation(_ROLLOUT_HDF5, 137),
        update_state=True,
    )

    assert corridor.corridor_id == 1_000_024
    assert state.coverage_active_execution_exemplar_id == "episode_24"
    assert state.coverage_active_effect_outcome_cell_id == 3
    assert state.coverage_active_execution_trace[
        "live_swept_physical_cell_ids"
    ] == [0, 1, 2, 3]
    assert state.coverage_active_execution_trace[
        "wall_minimum_clearance_m"
    ] == pytest.approx(0.6455139167289208)


@pytest.mark.skipif(
    not _HAS_FROZEN_EVIDENCE,
    reason="strict-18 frozen production replay evidence is unavailable",
)
def test_execution_library_sha_mismatch_fails_closed_without_median_fallback() -> None:
    runtime, state, observation = _runtime(library_sha256="0" * 64)

    with pytest.raises(
        NoWallSafeCorridorError,
        match="execution_library_sha256_mismatch",
    ):
        runtime.select_next_coverage_plan(observation, update_state=True)

    assert state.coverage_active_execution_exemplar_id == ""
    assert state.coverage_active_execution_raw_fields == {}


def test_disabled_execution_library_keeps_legacy_runtime_contract() -> None:
    config = CoverageExecutionLibraryConfig.from_mapping(None)

    assert config == replace(config, enabled=False)


@pytest.mark.skipif(
    not _HAS_FROZEN_EVIDENCE,
    reason="strict-18 frozen production replay evidence is unavailable",
)
def test_no_overwrite_preflight_locks_initial_and_replan_exact_tuples(
    tmp_path: Path,
) -> None:
    config = yaml.safe_load(_RESOLVED_CONFIG.read_text(encoding="utf-8"))
    config = copy.deepcopy(config)
    config["policy"]["dig_cut_planner"]["coverage"][
        "actual_tuple_execution_library"
    ] = {
        "enabled": True,
        "path": str(_LIBRARY),
        "artifact_sha256": _LIBRARY_SHA256,
        "mode": "exact_k1",
        "missing_contract": "fail_closed",
        "hard_bottom_margin_m": 0.02,
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    artifact = build_coverage_execution_preflight(
        rollout_hdf5_path=_ROLLOUT_HDF5,
        rollout_jsonl_path=_ROLLOUT_JSONL,
        resolved_config_path=config_path,
        output_dir=tmp_path / "preflight",
        initial_dig_step_id=137,
        pre_contact_step_id=2935,
        replan_step_id=2987,
        depth_exhausted_physical_cell_id=5,
    )

    assert artifact["status"] == "passed"
    assert artifact["initial_selection"]["selected_candidate"][
        "source_exemplar_id"
    ] == "episode_24"
    assert artifact["corrected_replan"]["selected_candidate"][
        "source_exemplar_id"
    ] == "episode_168"
    assert (
        tmp_path / "preflight" / COVERAGE_EXECUTION_PREFLIGHT_FILENAME
    ).is_file()
