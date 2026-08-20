from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from testbed.cli.return_closed_loop_probe import build_parser
from testbed.eval.return_closed_loop_probe import (
    LATEST_CURRENT_STRATEGY_ID,
    LEGACY_STRATEGY_ID,
    ReturnClosedLoopProbeError,
    ReturnClosedLoopSafetyAdapter,
    run_return_closed_loop_probe,
)

CAMERAS = ("stick_up", "stick_down", "eye_left", "eye_right")
ACTION_ORDER = (
    "swing_speed_cmd",
    "boom_speed_cmd",
    "stick_speed_cmd",
    "bucket_speed_cmd",
)
QPOS_ORDER = (
    "swing_position_norm",
    "boom_position_norm",
    "stick_position_norm",
    "bucket_position_norm",
)
QVEL_ORDER = (
    "swing_speed",
    "boom_speed",
    "stick_speed",
    "bucket_speed",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _token(value: float) -> list[float]:
    return np.full(18, value, dtype=np.float32).astype(float).tolist()


def _token_sha(token: list[float]) -> str:
    return hashlib.sha256(np.asarray(token, dtype=np.float32).tobytes()).hexdigest()


def _fixture_set() -> dict[str, Any]:
    fixtures: list[dict[str, Any]] = []
    for index in range(4):
        original = _token(float(index + 1))
        alternate = _token(float(index + 11))
        fixtures.append(
            {
                "fixture_id": f"fixture_{index}",
                "evidence_role": (
                    "offline_failed" if index in {0, 2} else "offline_normal"
                ),
                "source_segment_id": f"return:{index * 100}-{index * 100 + 40}:token",
                "initial_observation": {
                    "action_step_id": index * 100,
                    "observation_step_id": index * 100 - 1,
                    "qpos": [0.5 + index * 0.01, 0.4, 0.3, 0.2],
                    "qvel": [-0.1, 0.05, -0.2, -1.5],
                    "env_state": np.zeros(107, dtype=np.float32).tolist(),
                    "image_lineage": {"camera_names": list(CAMERAS)},
                },
                "targets": {
                    "original": {
                        "target_role": "original",
                        "segment_id": f"original_{index}",
                        "token_source": f"cell_{index}",
                        "token_sha256": _token_sha(original),
                        "token": original,
                    },
                    "alternate": {
                        "target_role": "alternate",
                        "segment_id": f"alternate_{index}",
                        "token_source": f"cell_{index + 1}",
                        "token_sha256": _token_sha(alternate),
                        "token": alternate,
                    },
                },
            }
        )
    return {
        "camera_names": list(CAMERAS),
        "fixtures": fixtures,
        "source_lineage": {
            "stage_a_v3": "immutable",
            "recorded_reset_context": {
                "full_terrain_snapshot_recorded": True,
                "deterministic_soil_seed_recorded": False,
                "terrain_restore_evidence": "full_state_restorable",
            },
        },
    }


def _contract() -> dict[str, Any]:
    arms: list[dict[str, Any]] = []
    for fixture_index in range(4):
        for target_role in ("original", "alternate"):
            for strategy in (LEGACY_STRATEGY_ID, LATEST_CURRENT_STRATEGY_ID):
                arms.append(
                    {
                        "arm_id": f"fixture_{fixture_index}__{target_role}__{strategy}",
                        "fixture_id": f"fixture_{fixture_index}",
                        "target_role": target_role,
                        "dispatch_strategy_id": strategy,
                        "max_steps": 420,
                        "no_retry": True,
                        "allowed_primitive": "return",
                    }
                )
    return {
        "schema": "return_closed_loop_causal_contract_v1",
        "arms": arms,
        "diagnostic_only": True,
        "promotion_eligible": False,
    }


def _runtime_lock(tmp_path: Path) -> dict[str, Any]:
    checkpoint = tmp_path / "return" / "policy_best.ckpt"
    stats = checkpoint.parent / "dataset_stats.pkl"
    training_config = checkpoint.parent / "return.yaml"
    stage_manifest = checkpoint.parent / "stage_a_v3_manifest.json"
    validation = checkpoint.parent / "return_validation.json"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"return-only-checkpoint")
    stats.write_bytes(b"return-only-stats")
    training_config.write_text("task: {}\n", encoding="utf-8")
    stage_manifest.write_text("{}\n", encoding="utf-8")
    validation.write_text("{}\n", encoding="utf-8")
    return {
        "source_sha": "a" * 40,
        "runtime_build_id": "editor:test:agx_env_state_v2_4_107",
        "scene_id": "Assets/TestScene.unity",
        "scene_sha256": "b" * 64,
        "camera_names": list(CAMERAS),
        "action_order": list(ACTION_ORDER),
        "qpos_order": list(QPOS_ORDER),
        "qvel_order": list(QVEL_ORDER),
        "return_checkpoint": {
            "path": str(checkpoint),
            "sha256": _sha256(checkpoint),
        },
        "return_stats": {
            "path": str(stats),
            "sha256": _sha256(stats),
        },
        "return_training_config": {
            "path": str(training_config),
            "sha256": _sha256(training_config),
        },
        "stage_a_v3_manifest": {
            "path": str(stage_manifest),
            "sha256": _sha256(stage_manifest),
        },
        "return_validation": {
            "path": str(validation),
            "sha256": _sha256(validation),
        },
        "unity_worktree_clean": True,
        "unity_source_rebuildable": True,
        "qvel_fixture_application_supported": True,
        "applied_action_telemetry_confirmed": True,
        "atomic_action_limit_telemetry_confirmed": True,
        "full_state_snapshot_restore_supported": True,
        "deterministic_physics_seed_confirmed": True,
        "terrain_state_restore_supported": True,
        "official_handoff_evaluator_confirmed": True,
        "action_discontinuity_threshold": [0.5, 0.5, 0.5, 0.5],
        "qpos_atol": 1.0e-6,
        "qvel_atol": 1.0e-6,
    }


class _Backend:
    def __init__(
        self,
        arm: dict[str, Any],
        *,
        qvel_applied: bool = True,
        action_telemetry: bool = True,
    ) -> None:
        self.arm = arm
        self.qvel_applied = qvel_applied
        self.action_telemetry = action_telemetry
        self.actions: list[np.ndarray] = []
        self.closed = False
        self._obs: dict[str, Any] | None = None

    def get_info(self) -> dict[str, Any]:
        return {
            "runtime_build_id": "editor:test:agx_env_state_v2_4_107",
            "scene_id": "Assets/TestScene.unity",
            "scene_sha256": "b" * 64,
            "camera_names": list(CAMERAS),
            "action_order": list(ACTION_ORDER),
            "qpos_order": list(QPOS_ORDER),
            "qvel_order": list(QVEL_ORDER),
        }

    def prepare_fixture(self, fixture: dict[str, Any]) -> dict[str, Any]:
        initial = fixture["initial_observation"]
        self._obs = {
            "step_id": 0,
            "qpos": np.asarray(initial["qpos"], dtype=np.float32),
            "qvel": np.asarray(initial["qvel"], dtype=np.float32),
            "env_state": np.asarray(initial["env_state"], dtype=np.float32),
            "encoded_images": {name: {"data": b"jpeg"} for name in CAMERAS},
        }
        return {
            "reset_applied": True,
            "qpos_applied": True,
            "qvel_applied": self.qvel_applied,
            "observation": self._obs,
            "warnings": [] if self.qvel_applied else ["qvel_status=ignored"],
        }

    def step(self, action: np.ndarray) -> SimpleNamespace:
        applied = np.asarray(action, dtype=np.float32).copy()
        self.actions.append(applied)
        assert self._obs is not None
        self._obs = {
            **self._obs,
            "step_id": int(self._obs["step_id"]) + 1,
        }
        info = (
            {
                "applied_action": applied,
                "action_limit_intervention": np.zeros(4, dtype=np.bool_),
            }
            if self.action_telemetry
            else {}
        )
        return SimpleNamespace(observation=self._obs, done=False, info=info)

    def close(self) -> None:
        self.closed = True


class _Policy:
    def __init__(self, arm_id: str, calls: dict[str, list[str]]) -> None:
        self.arm_id = arm_id
        self.calls = calls
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1
        self.calls["reset"].append(self.arm_id)

    def predict(self, obs: dict[str, Any]) -> np.ndarray:
        assert np.asarray(obs["return_start_envelope_tokens_v1"]).shape == (18,)
        self.calls["predict"].append(self.arm_id)
        return np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)

    def predict_action_chunk(self, obs: dict[str, Any]) -> SimpleNamespace:
        assert np.asarray(obs["return_start_envelope_tokens_v1"]).shape == (18,)
        self.calls["chunk"].append(self.arm_id)
        return SimpleNamespace(
            first_action=np.asarray([0.4, 0.3, 0.2, 0.1], dtype=np.float32)
        )


class _Safety:
    def __init__(self) -> None:
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1

    def filter_action(self, obs: dict[str, Any], action: np.ndarray, **_: Any) -> Any:
        return SimpleNamespace(
            action=np.asarray(action, dtype=np.float32),
            terminal=False,
            replan=False,
            reason="",
            awaiting_neutral_ack=False,
            neutral_acknowledged=False,
        )


def _git_state(*, clean: bool = True) -> dict[str, Any]:
    return {
        "git_head": "a" * 40,
        "git_branch": "test",
        "worktree_clean": clean,
    }


def test_qvel_unconfirmed_blocks_all_16_arms_before_policy_or_nonzero_action(
    tmp_path: Path,
) -> None:
    backends: list[_Backend] = []
    policy_calls = 0

    def backend_factory(arm: dict[str, Any]) -> _Backend:
        backend = _Backend(
            arm,
            qvel_applied=arm["fixture_id"] != "fixture_2",
        )
        backends.append(backend)
        return backend

    def policy_factory(_: dict[str, Any]) -> _Policy:
        nonlocal policy_calls
        policy_calls += 1
        raise AssertionError("policy must not load after a blocked matrix preflight")

    result = run_return_closed_loop_probe(
        causal_contract=_contract(),
        fixture_set=_fixture_set(),
        runtime_lock=_runtime_lock(tmp_path),
        output_root=tmp_path / "probe",
        execute=True,
        backend_factory=backend_factory,
        policy_factory=policy_factory,
        safety_factory=lambda _: _Safety(),
        handoff_evaluator=lambda _obs, _arm: {"would_handoff": False},
        git_state_provider=_git_state,
    )

    assert result["status"] == "preflight_blocked"
    assert result["nonzero_action_count"] == 0
    assert result["arm_count"] == 16
    assert policy_calls == 0
    assert all(
        not np.any(action)
        for backend in backends
        for action in backend.actions
    )
    assert all(backend.closed for backend in backends)

    root = tmp_path / "probe"
    manifest = json.loads((root / "manifest.json").read_text())
    preflight = json.loads((root / "preflight.json").read_text())
    arms = json.loads((root / "arms.json").read_text())
    assert manifest["status"] == "preflight_blocked"
    assert preflight["qvel_fixture_application_confirmed"] is False
    assert len(arms["arms"]) == 16
    assert {arm["status"] for arm in arms["arms"]} == {"preflight_blocked"}
    assert (root / "report.md").is_file()


def test_execute_uses_only_registered_dispatch_api_and_stops_on_handoff(
    tmp_path: Path,
) -> None:
    backends: list[_Backend] = []
    calls = {"reset": [], "predict": [], "chunk": []}

    def backend_factory(arm: dict[str, Any]) -> _Backend:
        backend = _Backend(arm)
        backends.append(backend)
        return backend

    result = run_return_closed_loop_probe(
        causal_contract=_contract(),
        fixture_set=_fixture_set(),
        runtime_lock=_runtime_lock(tmp_path),
        output_root=tmp_path / "probe",
        execute=True,
        backend_factory=backend_factory,
        policy_factory=lambda arm: _Policy(arm["arm_id"], calls),
        safety_factory=lambda _: _Safety(),
        handoff_evaluator=lambda obs, _arm: {
            "would_handoff": int(obs["step_id"]) >= 2,
        },
        git_state_provider=_git_state,
    )

    assert result["status"] == "completed"
    assert result["arm_count"] == 16
    assert result["nonzero_action_count"] == 32
    assert len(calls["reset"]) == 16
    assert len(set(calls["reset"])) == 16
    assert len(calls["predict"]) == 16
    assert len(calls["chunk"]) == 16

    execution_backends = backends[16:]
    assert len(execution_backends) == 16
    for backend in execution_backends:
        assert len(backend.actions) == 3
        assert np.any(backend.actions[0])
        assert np.any(backend.actions[1])
        assert not np.any(backend.actions[2])
    arm_summaries = list((tmp_path / "probe" / "arms").glob("*/summary.json"))
    traces = list((tmp_path / "probe" / "arms").glob("*/trace.jsonl"))
    assert len(arm_summaries) == 16
    assert len(traces) == 16
    assert {
        json.loads(path.read_text())["termination_reason"]
        for path in arm_summaries
    } == {"would_handoff"}
    legacy_trace = next(
        path
        for path in traces
        if LEGACY_STRATEGY_ID in path.parent.name
    )
    latest_trace = next(
        path
        for path in traces
        if LATEST_CURRENT_STRATEGY_ID in path.parent.name
    )
    legacy_rows = [json.loads(line) for line in legacy_trace.read_text().splitlines()]
    latest_rows = [json.loads(line) for line in latest_trace.read_text().splitlines()]
    assert legacy_rows[1]["temporal_dispatch"]["contributors"] == [
        {
            "age": 1,
            "query_index": 1,
            "source_frame_index": 0,
            "weight": pytest.approx(1.0 / (1.0 + np.exp(-0.01))),
        },
        {
            "age": 0,
            "query_index": 0,
            "source_frame_index": 1,
            "weight": pytest.approx(np.exp(-0.01) / (1.0 + np.exp(-0.01))),
        },
    ]
    assert latest_rows[1]["temporal_dispatch"]["contributors"] == [
        {
            "age": 0,
            "query_index": 0,
            "source_frame_index": 1,
            "weight": 1.0,
        }
    ]
    assert legacy_rows[0]["applied_action"] == pytest.approx(
        legacy_rows[0]["dispatched_action"]
    )
    assert legacy_rows[0]["action_limit_intervention"] == [False] * 4


def test_missing_action_telemetry_blocks_before_policy_or_nonzero_action(
    tmp_path: Path,
) -> None:
    backends: list[_Backend] = []

    def backend_factory(arm: dict[str, Any]) -> _Backend:
        backend = _Backend(arm, action_telemetry=False)
        backends.append(backend)
        return backend

    result = run_return_closed_loop_probe(
        causal_contract=_contract(),
        fixture_set=_fixture_set(),
        runtime_lock=_runtime_lock(tmp_path),
        output_root=tmp_path / "probe",
        execute=True,
        backend_factory=backend_factory,
        policy_factory=lambda _arm: (_ for _ in ()).throw(
            AssertionError("policy must not load without applied-action telemetry")
        ),
        safety_factory=lambda _: _Safety(),
        handoff_evaluator=lambda _obs, _arm: {"would_handoff": False},
        git_state_provider=_git_state,
    )

    assert result["status"] == "preflight_blocked"
    assert result["nonzero_action_count"] == 0
    assert all(not np.any(action) for backend in backends for action in backend.actions)
    preflight = json.loads(
        (tmp_path / "probe" / "preflight.json").read_text()
    )
    assert any(
        "zero_step_applied_action_telemetry_missing" in blocker
        for blocker in preflight["blockers"]
    )


def test_execute_requires_clean_exact_source_and_no_overwrite(tmp_path: Path) -> None:
    factory_calls = 0

    def backend_factory(arm: dict[str, Any]) -> _Backend:
        nonlocal factory_calls
        factory_calls += 1
        return _Backend(arm)

    result = run_return_closed_loop_probe(
        causal_contract=_contract(),
        fixture_set=_fixture_set(),
        runtime_lock=_runtime_lock(tmp_path),
        output_root=tmp_path / "probe",
        execute=True,
        backend_factory=backend_factory,
        policy_factory=lambda arm: _Policy(arm["arm_id"], {"reset": [], "predict": [], "chunk": []}),
        safety_factory=lambda _: _Safety(),
        handoff_evaluator=lambda _obs, _arm: False,
        git_state_provider=lambda: _git_state(clean=False),
    )
    assert result["status"] == "preflight_blocked"
    assert result["nonzero_action_count"] == 0
    assert factory_calls == 0

    with pytest.raises(FileExistsError):
        run_return_closed_loop_probe(
            causal_contract=_contract(),
            fixture_set=_fixture_set(),
            runtime_lock=_runtime_lock(tmp_path),
            output_root=tmp_path / "probe",
            execute=False,
            backend_factory=backend_factory,
            policy_factory=lambda arm: _Policy(
                arm["arm_id"], {"reset": [], "predict": [], "chunk": []}
            ),
            safety_factory=lambda _: _Safety(),
            handoff_evaluator=lambda _obs, _arm: False,
            git_state_provider=_git_state,
        )


def test_contract_rejects_any_matrix_or_horizon_drift(tmp_path: Path) -> None:
    contract = _contract()
    contract["arms"][0]["max_steps"] = 419
    with pytest.raises(ReturnClosedLoopProbeError, match="max_steps"):
        run_return_closed_loop_probe(
            causal_contract=contract,
            fixture_set=_fixture_set(),
            runtime_lock=_runtime_lock(tmp_path),
            output_root=tmp_path / "probe",
            execute=False,
            backend_factory=lambda arm: _Backend(arm),
            policy_factory=lambda arm: _Policy(
                arm["arm_id"], {"reset": [], "predict": [], "chunk": []}
            ),
            safety_factory=lambda _: _Safety(),
            handoff_evaluator=lambda _obs, _arm: False,
            git_state_provider=_git_state,
        )


def test_narrow_safety_adapter_fails_closed_on_nonfinite_collision_and_force() -> None:
    adapter = ReturnClosedLoopSafetyAdapter()
    base = {
        "step_id": 7,
        "qpos": np.zeros(4, dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
        "env_state": np.zeros(107, dtype=np.float32),
    }

    nonfinite = adapter.filter_action(base, [0.0, np.nan, 0.0, 0.0])
    assert nonfinite.terminal is True
    assert nonfinite.reason == "nonfinite_policy_action"
    assert not np.any(nonfinite.action)

    collision_obs = {**base, "env_state": np.zeros(107, dtype=np.float32)}
    collision_obs["env_state"][63] = 1.0
    collision = adapter.filter_action(collision_obs, np.ones(4, dtype=np.float32))
    assert collision.terminal is True
    assert collision.reason == "hard_collision"
    assert not np.any(collision.action)

    force_obs = {**base, "env_state": np.zeros(107, dtype=np.float32)}
    force_obs["env_state"][102] = 100_000.0
    force = adapter.filter_action(force_obs, np.ones(4, dtype=np.float32))
    assert force.terminal is True
    assert force.reason == "contact_force_at_or_above_limit"
    assert not np.any(force.action)


def test_cli_defaults_to_preflight_and_requires_explicit_execute() -> None:
    parser = build_parser()
    common = [
        "--stage-a-v3-root",
        "/stage-a",
        "--return-training-config",
        "/return.yaml",
        "--runtime-lock",
        "/runtime.json",
        "--output-root",
        "/output",
    ]
    assert parser.parse_args(common).execute is False
    assert parser.parse_args([*common, "--execute"]).execute is True
