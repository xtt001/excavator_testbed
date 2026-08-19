from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np
import pytest
import yaml

from testbed.eval import act_goal_condition_sensitivity_isolation as _isolation
from testbed.eval import act_goal_condition_sensitivity_runner as _runner
from testbed.eval.act_goal_condition_sensitivity import (
    ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA,
    ACT_GOAL_CONDITION_SENSITIVITY_RESULTS_SCHEMA,
    _response_threshold,
    derive_replica_tolerance,
    evaluate_goal_condition_sensitivity_segment,
    write_goal_condition_sensitivity_artifact,
)


class _FakePolicy:
    def __init__(
        self,
        *,
        response_scale: float,
        replica_offset: float = 0.0,
        partial_response: bool = False,
    ) -> None:
        self.response_scale = response_scale
        self.replica_offset = replica_offset
        self.partial_response = partial_response
        self.reset_calls = 0
        self.predict_calls = 0
        self.chunk_calls = 0
        self._cache = 0

    def reset(self) -> None:
        self.reset_calls += 1
        self._cache = 0

    def predict_action_chunk(self, obs: dict[str, np.ndarray]):
        self.chunk_calls += 1
        token = float(np.asarray(obs["goal_token"], dtype=np.float32)[0])
        action = np.asarray(
            [token * self.response_scale + self.replica_offset, 0.0],
            dtype=np.float32,
        )
        return type(
            "Chunk",
            (),
            {"actions": np.stack((action, action + 0.01), axis=0)},
        )()

    def predict(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        self.predict_calls += 1
        token = float(np.asarray(obs["goal_token"], dtype=np.float32)[0])
        response = token * self.response_scale
        if self.partial_response and self._cache >= 0.2:
            response = 0.0
        action = np.asarray(
            [response + self.replica_offset + self._cache, 0.0],
            dtype=np.float32,
        )
        self._cache += 0.1
        return action


def _segment(*, frame_count: int = 5) -> dict[str, object]:
    baseline_actions = [[0.1 * index, 0.0] for index in range(frame_count)]
    return {
        "primitive": "dig",
        "segment_id": "dig-cycle-1",
        "condition_input_key": "goal_token",
        "frames": [
            {
                "action_step_id": 100 + index,
                "observation_step_id": 99 + index,
                "observation": {
                    "qpos": np.asarray([index, 0.0], dtype=np.float32),
                    "goal_token": np.asarray([0.0], dtype=np.float32),
                },
                "recorded_action": np.asarray(action, dtype=np.float32),
                "non_target_input_sha256": f"frame-{index}",
            }
            for index, action in enumerate(baseline_actions)
        ],
    }


def _conditions(
    *,
    support: str = "supported",
    baseline_support: str = "supported",
) -> list[dict[str, object]]:
    return [
        {
            "condition_id": "recorded",
            "token": np.asarray([0.0], dtype=np.float32),
            "support_status": baseline_support,
        },
        {
            "condition_id": "alternate_real_token",
            "token": np.asarray([1.0], dtype=np.float32),
            "support_status": support,
            "provenance": {"kind": "recorded_real_token"},
        },
    ]


def _factory(
    *,
    alternate_response: float = 0.2,
    baseline_replica_offset: float = 0.0,
    alternate_replica_offset: float = 0.0,
    partial_response: bool = False,
):
    policies: list[_FakePolicy] = []

    def build(condition: dict[str, object], _replica_id: str) -> _FakePolicy:
        response = alternate_response if condition["condition_id"] != "recorded" else 0.0
        offset = (
            baseline_replica_offset
            if condition["condition_id"] == "recorded"
            else alternate_replica_offset
        )
        policy = _FakePolicy(
            response_scale=response,
            replica_offset=offset if _replica_id.endswith("replica_b") else 0.0,
            partial_response=partial_response,
        )
        policies.append(policy)
        return policy

    return build, policies


def _action_std() -> np.ndarray:
    return np.asarray([1.0, 1.0], dtype=np.float32)


def test_runs_independent_policy_replicas_and_records_three_anchor_chunks() -> None:
    factory, policies = _factory()

    result = evaluate_goal_condition_sensitivity_segment(
        segment=_segment(),
        conditions=_conditions(),
        policy_factory=factory,
        action_std=_action_std(),
    )

    alternate = result["conditions"]["alternate_real_token"]
    assert result["status"] == "completed"
    assert alternate["classification"] == "goal_response_plausible"
    assert alternate["response_gate"] == {
        "action_std_fraction": 0.05,
        "responsive_frame_fraction": 1.0,
        "required_responsive_frame_fraction": 0.8,
        "anchor_count": 3,
        "responsive_anchor_count": 3,
        "passed": True,
    }
    assert [item["frame_index"] for item in alternate["anchor_chunk_deltas"]] == [0, 2, 4]
    assert len(policies) == 4
    assert len({id(policy) for policy in policies}) == 4
    assert all(policy.reset_calls == 1 for policy in policies)
    assert all(policy.predict_calls == 5 for policy in policies)
    assert policies[0].chunk_calls == 3
    assert policies[1].chunk_calls == 3
    assert policies[2].chunk_calls == 3
    assert policies[3].chunk_calls == 3


def test_replica_tolerance_is_derived_before_counterfactual_execution() -> None:
    factory, _ = _factory(baseline_replica_offset=0.00001)

    result = evaluate_goal_condition_sensitivity_segment(
        segment=_segment(),
        conditions=_conditions(),
        policy_factory=factory,
        action_std=_action_std(),
    )

    assert result["status"] == "completed"
    assert result["artifact_validity"]["replica_tolerance"]["source"] == (
        "two_baseline_replicas"
    )
    assert result["artifact_validity"]["replica_tolerance"][
        "replica_noise_cap_axis"
    ][0] > 0.0
    assert result["artifact_validity"]["replica_tolerance"][
        "dispatched_tolerance_axis"
    ][0] == pytest.approx(0.0001, abs=1.0e-8)
    assert result["conditions"]["alternate_real_token"]["classification"] == (
        "goal_response_plausible"
    )


def test_saved_action_failure_makes_artifact_invalid_without_classification() -> None:
    factory, _ = _factory()
    segment = _segment()
    frames = list(segment["frames"])
    frames[1] = {**frames[1], "recorded_action": np.asarray([99.0, 0.0])}
    segment = {**segment, "frames": frames}

    result = evaluate_goal_condition_sensitivity_segment(
        segment=segment,
        conditions=_conditions(),
        policy_factory=factory,
        action_std=_action_std(),
    )

    assert result["status"] == "artifact_invalid"
    assert result["artifact_validity"]["saved_action_alignment"]["passed"] is False
    assert "classification" not in result["conditions"]["alternate_real_token"]


def test_replica_tolerance_helper_is_registered_from_both_baselines() -> None:
    tolerance = derive_replica_tolerance(
        baseline_a_chunks=np.asarray([[[0.0, 0.0], [0.0, 0.0]]]),
        baseline_b_chunks=np.asarray([[[0.02, 0.0], [0.02, 0.0]]]),
        baseline_a_actions=np.asarray([[0.0, 0.0]]),
        baseline_b_actions=np.asarray([[0.01, 0.0]]),
        action_std=np.asarray([10.0, 0.0]),
    )
    assert tolerance["source"] == "two_baseline_replicas"
    assert tolerance["replica_noise_cap_axis"] == pytest.approx([0.05, 1.0e-6])
    assert tolerance["chunk_max_abs_delta_axis"][0] == pytest.approx(0.02)
    assert tolerance["dispatched_tolerance_axis"][0] == pytest.approx(0.1)


def test_response_threshold_never_drops_below_baseline_tolerance() -> None:
    threshold = _response_threshold(
        baseline_tolerance=np.asarray([0.01, 1.0e-6], dtype=np.float32),
        action_std=np.asarray([0.1, 0.5], dtype=np.float32),
    )

    np.testing.assert_allclose(threshold, [0.01, 0.025])


def test_support_precedes_response_and_insensitive_precedes_plausible() -> None:
    factory, _ = _factory(alternate_response=0.2)
    out_of_support = evaluate_goal_condition_sensitivity_segment(
        segment=_segment(),
        conditions=_conditions(support="out_of_support"),
        policy_factory=factory,
        action_std=_action_std(),
    )
    assert out_of_support["conditions"]["alternate_real_token"]["classification"] == (
        "out_of_support"
    )

    factory, _ = _factory(alternate_response=0.2)
    baseline_out_of_support = evaluate_goal_condition_sensitivity_segment(
        segment=_segment(),
        conditions=_conditions(baseline_support="out_of_support"),
        policy_factory=factory,
        action_std=_action_std(),
    )
    assert baseline_out_of_support["conditions"][
        "alternate_real_token"
    ]["classification"] == "out_of_support"

    factory, _ = _factory(alternate_response=0.0)
    insensitive = evaluate_goal_condition_sensitivity_segment(
        segment=_segment(),
        conditions=_conditions(),
        policy_factory=factory,
        action_std=_action_std(),
    )
    assert insensitive["conditions"]["alternate_real_token"]["classification"] == (
        "goal_insensitive"
    )

    factory, _ = _factory(alternate_response=0.2, partial_response=True)
    inconsistent = evaluate_goal_condition_sensitivity_segment(
        segment=_segment(),
        conditions=_conditions(),
        policy_factory=factory,
        action_std=_action_std(),
    )
    assert inconsistent["conditions"]["alternate_real_token"]["classification"] == (
        "goal_response_invalid"
    )

    factory, _ = _factory(alternate_response=0.2, alternate_replica_offset=0.02)
    unstable = evaluate_goal_condition_sensitivity_segment(
        segment=_segment(),
        conditions=_conditions(),
        policy_factory=factory,
        action_std=_action_std(),
    )
    assert unstable["status"] == "completed"
    assert unstable["conditions"]["alternate_real_token"]["classification"] == (
        "goal_response_invalid"
    )
    assert unstable["conditions"]["alternate_real_token"]["replica_validity"][
        "passed"
    ] is False


def test_carry_dump_isolation_failure_makes_artifact_invalid() -> None:
    factory, _ = _factory()
    isolation_invalid = evaluate_goal_condition_sensitivity_segment(
        segment={**_segment(), "primitive": "carry", "condition_input_key": None},
        conditions=_conditions(),
        policy_factory=factory,
        action_std=_action_std(),
        isolation_check=lambda _segment, _conditions: {
            "passed": False,
            "reason": "cut_goal_injected_into_carry",
        },
    )
    assert isolation_invalid["status"] == "artifact_invalid"
    assert "classification" not in isolation_invalid["conditions"]["alternate_real_token"]


def test_no_overwrite_writer_emits_manifest_and_results(tmp_path: Path) -> None:
    factory, _ = _factory()
    result = evaluate_goal_condition_sensitivity_segment(
        segment=_segment(),
        conditions=_conditions(),
        policy_factory=factory,
        action_std=_action_std(),
    )
    destination = tmp_path / "act_goal_condition_sensitivity_v1"

    manifest = write_goal_condition_sensitivity_artifact(
        output_root=destination,
        manifest={
            "schema": ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA,
            "status": "completed",
            "evidence_kind": "teacher_forced_recorded_observation",
            "diagnostic_only": True,
            "promotion_eligible": False,
        },
        baseline={"schema": "act_goal_condition_sensitivity_baseline_v1"},
        dig=result,
        return_=result,
        carry_dump_isolation={"schema": "act_goal_condition_sensitivity_isolation_v1"},
        report_markdown="# Stage A\n",
    )

    assert manifest["schema"] == ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA
    assert manifest["evidence_kind"] == "teacher_forced_recorded_observation"
    assert manifest["diagnostic_only"] is True
    assert manifest["promotion_eligible"] is False
    saved = json.loads((destination / "dig.json").read_text())
    assert saved["schema"] == ACT_GOAL_CONDITION_SENSITIVITY_RESULTS_SCHEMA
    assert sorted(path.name for path in destination.iterdir()) == [
        "baseline.json",
        "carry_dump_isolation.json",
        "dig.json",
        "manifest.json",
        "report.md",
        "return.json",
    ]
    with pytest.raises(FileExistsError):
        write_goal_condition_sensitivity_artifact(
            output_root=destination,
            manifest={"schema": ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA},
            baseline={},
            dig={},
            return_={},
            carry_dump_isolation={},
            report_markdown="",
        )


def test_preflight_failures_are_artifact_invalid_without_classification() -> None:
    factory, _ = _factory()
    too_short = evaluate_goal_condition_sensitivity_segment(
        segment=_segment(frame_count=2),
        conditions=_conditions(),
        policy_factory=factory,
        action_std=_action_std(),
    )
    assert too_short["status"] == "artifact_invalid"
    assert "classification" not in too_short["conditions"]["alternate_real_token"]

    factory, _ = _factory()
    unknown_support = evaluate_goal_condition_sensitivity_segment(
        segment=_segment(),
        conditions=_conditions(support="maybe"),
        policy_factory=factory,
        action_std=_action_std(),
    )
    assert unknown_support["status"] == "artifact_invalid"
    assert "classification" not in unknown_support["conditions"]["alternate_real_token"]


class _RunnerPolicy:
    def __init__(self) -> None:
        self._cache = 0.0

    def reset(self) -> None:
        self._cache = 0.0

    def predict_action_chunk(self, obs: dict[str, np.ndarray]):
        token = _runner_token(obs)
        action = np.asarray([token * 0.2, 0.0], dtype=np.float32)
        return SimpleNamespace(actions=np.stack((action, action), axis=0))

    def predict(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        token = _runner_token(obs)
        action = np.asarray([token * 0.2 + self._cache, 0.0], dtype=np.float32)
        self._cache += 0.1
        return action


def _runner_token(obs: dict[str, np.ndarray]) -> float:
    for key in ("dig_cut_tokens", "return_start_envelope_tokens_v1"):
        if key in obs:
            return float(np.asarray(obs[key])[0])
    raise AssertionError("runner observation lacks a token")


def _runner_segment(
    *,
    primitive: str,
    token: float,
    start_step: int,
) -> SimpleNamespace:
    model_key = (
        "dig_cut_tokens"
        if primitive == "dig"
        else "return_start_envelope_tokens_v1"
    )
    token_dim = 10 if primitive == "dig" else 18
    frames = tuple(
        SimpleNamespace(
            action_step_id=start_step + index,
            observation_step_id=start_step + index - 1,
            action=np.asarray([token * 0.2 + 0.1 * index, 0.0], dtype=np.float32),
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            token=np.full(token_dim, token, dtype=np.float32),
            model_token_key=model_key,
            policy_dispatched=True,
        )
        for index in range(3)
    )
    token_sha = f"{primitive}-{token}".replace(".", "_")
    return SimpleNamespace(
        skill_name=primitive,
        model_token_key=model_key,
        token=np.full(token_dim, token, dtype=np.float32),
        token_source="recorded_real_token",
        token_sha256=token_sha,
        frames=frames,
        start_action_step_id=start_step,
        end_action_step_id=start_step + 2,
        primitive_cycle_indices=(0,),
        frame_count=3,
        segment_id=f"{primitive}:{start_step}:{token_sha}",
    )


def test_high_level_runner_uses_data_segments_and_writes_exact_six_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    (source / "rollouts").mkdir(parents=True)
    (source / "hdf5_rollouts").mkdir()
    (source / "rollouts" / "rollout_000.jsonl").write_text("{}\n")
    (source / "eval_run_metadata.json").write_text(
        json.dumps({"repo_snapshots": {"repo_a": {"commit": "a" * 40}}})
    )
    with h5py.File(source / "hdf5_rollouts" / "episode_0.hdf5", "w"):
        pass
    eval_config = {
        "task": {"camera_names": ["fpv"], "equipment_model": "yulong", "episode_len": 10},
        "policy": {
            "act_params": {},
            "dig_low_dim_keys": ["qpos", "qvel", "dig_cut_tokens"],
            "return_low_dim_keys": ["qpos", "qvel", "return_start_envelope_tokens_v1"],
            "carry_low_dim_keys": ["qpos", "qvel"],
            "dump_low_dim_keys": ["qpos", "qvel"],
        },
        "eval": {},
    }
    (source / "eval_resolved_config.yaml").write_text(yaml.safe_dump(eval_config))
    train_config = tmp_path / "train.yaml"
    train_config.write_text(yaml.safe_dump({"task": {}, "train": {}}))
    segments = [
        _runner_segment(primitive="dig", token=0.0, start_step=10),
        _runner_segment(primitive="dig", token=1.0, start_step=20),
        _runner_segment(primitive="return", token=0.0, start_step=30),
        _runner_segment(primitive="return", token=1.0, start_step=40),
    ]
    support = SimpleNamespace(
        feature_order=("qpos[0]",),
        p01=np.asarray([-1.0], dtype=np.float32),
        p99=np.asarray([1.0], dtype=np.float32),
        train_source_episode_ids=(3,),
        validation_source_episode_ids=(33,),
        total_step_count=1,
        kept_step_count=1,
        masked_step_count=0,
    )

    monkeypatch.setattr(_runner, "join_recorded_act_replay_frames", lambda **_kwargs: [])
    monkeypatch.setattr(_runner, "split_stable_recorded_act_segments", lambda _frames: segments)
    monkeypatch.setattr(
        _runner,
        "select_deterministic_alternate_segment",
        lambda *, segments, baseline: next(
            segment for segment in segments if segment.token_sha256 != baseline.token_sha256
        ),
    )
    monkeypatch.setattr(_runner, "_strict_train_support", lambda *_args, **_kwargs: support)
    monkeypatch.setattr(
        _runner,
        "_support_assessor",
        lambda _support: lambda _condition, _segment: {"status": "supported"},
    )
    monkeypatch.setattr(
        _runner,
        "read_recorded_act_observation",
        lambda **kwargs: {
            "qpos": kwargs["frame"].qpos,
            "qvel": kwargs["frame"].qvel,
            kwargs["frame"].model_token_key: kwargs["frame"].token,
            "image_fpv": np.zeros((3, 2, 2), dtype=np.float32),
        },
    )
    monkeypatch.setattr(
        _runner,
        "_configure_eval_torch_performance",
        lambda *_args, **_kwargs: SimpleNamespace(as_config_dict=lambda: {"allow_tf32": False}),
    )
    monkeypatch.setattr(
        _runner,
        "_clean_code_record",
        lambda: {"git_head": "b" * 40, "git_branch": "test", "worktree_clean": True},
    )
    monkeypatch.setattr(
        _runner,
        "run_carry_dump_isolation",
        lambda **_kwargs: {
            "schema": "act_goal_condition_sensitivity_isolation_v1",
            "status": "completed",
            "checks": {},
        },
    )

    def factory_builder(_primitive: str, _policy_cfg: dict[str, object]):
        return lambda _condition, _replica_id: _RunnerPolicy()

    result = _runner.run_act_goal_condition_sensitivity_audit(
        source_results_root=source,
        dig_training_config_path=train_config,
        return_training_config_path=train_config,
        output_root=tmp_path / "act_goal_condition_sensitivity_v1",
        device="cpu",
        policy_factory_builder=factory_builder,
        action_std_by_primitive={
            "dig": np.asarray([1.0, 1.0], dtype=np.float32),
            "return": np.asarray([1.0, 1.0], dtype=np.float32),
            "carry": np.asarray([1.0, 1.0], dtype=np.float32),
            "dump": np.asarray([1.0, 1.0], dtype=np.float32),
        },
    )

    assert result["status"] == "completed"
    root = Path(result["output_root"])
    assert sorted(path.name for path in root.iterdir()) == [
        "baseline.json",
        "carry_dump_isolation.json",
        "dig.json",
        "manifest.json",
        "report.md",
        "return.json",
    ]
    assert json.loads((root / "dig.json").read_text())["aggregate"]["segment_pair_count"] == 2
    assert json.loads((root / "return.json").read_text())["aggregate"]["segment_pair_count"] == 2


class _IsolationPolicy:
    def __init__(self, *, responds_to_extra: bool) -> None:
        self.responds_to_extra = responds_to_extra
        self._cache = 0.0

    def reset(self) -> None:
        self._cache = 0.0

    def _action(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        extra = 0.2 if self.responds_to_extra and "dig_cut_tokens" in obs else 0.0
        return np.asarray([self._cache + extra, 0.0], dtype=np.float32)

    def predict_action_chunk(self, obs: dict[str, np.ndarray]):
        action = self._action(obs)
        return SimpleNamespace(actions=np.stack((action, action), axis=0))

    def predict(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        action = self._action(obs)
        self._cache += 0.1
        return action


def _isolation_segment(primitive: str, *, token: float | None = None) -> SimpleNamespace:
    token_value = None if token is None else np.full(10, token, dtype=np.float32)
    frames = tuple(
        SimpleNamespace(
            action_step_id=10 + index,
            observation_step_id=9 + index,
            action=np.asarray([0.1 * index, 0.0], dtype=np.float32),
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
        )
        for index in range(3)
    )
    return SimpleNamespace(
        skill_name=primitive,
        model_token_key="dig_cut_tokens" if primitive == "dig" else None,
        token=token_value,
        token_source="recorded" if primitive == "dig" else None,
        token_sha256="d" * 64 if primitive == "dig" else None,
        frames=frames,
        start_action_step_id=10,
        end_action_step_id=12,
        primitive_cycle_indices=(0,),
        frame_count=3,
        segment_id=f"{primitive}:10-12",
    )


def test_carry_dump_isolation_replays_extra_real_dig_token() -> None:
    segments = [
        _isolation_segment("dig", token=1.0),
        _isolation_segment("carry"),
        _isolation_segment("dump"),
    ]
    policy_cfg = {
        "carry_low_dim_keys": ["qpos", "qvel"],
        "dump_low_dim_keys": ["qpos", "qvel"],
    }

    def run(*, responds_to_extra: bool) -> dict[str, object]:
        return _isolation.run_carry_dump_isolation(
            policy_cfg=policy_cfg,
            segments=segments,
            dig_segments=[segments[0]],
            policy_factory_builder=lambda _primitive, _cfg: (
                lambda _condition, _replica_id: _IsolationPolicy(
                    responds_to_extra=responds_to_extra
                )
            ),
            observation_reader=lambda frame: {
                "qpos": frame.qpos,
                "qvel": frame.qvel,
                "image_fpv": np.zeros((3, 2, 2), dtype=np.float32),
            },
            action_std_by_primitive={
                "carry": np.asarray([1.0, 1.0], dtype=np.float32),
                "dump": np.asarray([1.0, 1.0], dtype=np.float32),
            },
        )

    inert = run(responds_to_extra=False)
    assert inert["status"] == "completed"
    assert inert["checks"]["carry"]["comparison"]["passed"] is True
    assert inert["checks"]["dump"]["extraneous_dig_token"]["injected_input_key"] == (
        "dig_cut_tokens"
    )

    coupled = run(responds_to_extra=True)
    assert coupled["status"] == "artifact_invalid"
    assert coupled["checks"]["carry"]["comparison"]["passed"] is False
