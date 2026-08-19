from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np
import pytest
import yaml

from testbed.eval import act_goal_condition_sensitivity_runner as runner


class _Policy:
    def __init__(self, primitive: str) -> None:
        self._cache = 0.0
        self._primitive = primitive

    def reset(self) -> None:
        self._cache = 0.0

    def _condition_value(self, obs: dict[str, np.ndarray]) -> float:
        key = {
            "dig": "dig_cut_tokens",
            "return": "return_start_envelope_tokens_v1",
        }.get(self._primitive)
        if key is not None and key in obs:
            return float(np.asarray(obs[key], dtype=np.float32)[0])
        return 0.0

    def predict_action_chunk(self, obs: dict[str, np.ndarray]):
        action = np.asarray([self._condition_value(obs) * 0.2, 0.0], dtype=np.float32)
        return SimpleNamespace(actions=np.stack((action, action), axis=0))

    def predict(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        action = np.asarray(
            [self._condition_value(obs) * 0.2 + self._cache, 0.0],
            dtype=np.float32,
        )
        self._cache += 0.1
        return action


def _segment(
    *,
    primitive: str,
    token: float | None,
    start_step: int,
) -> SimpleNamespace:
    model_key = {
        "dig": "dig_cut_tokens",
        "return": "return_start_envelope_tokens_v1",
    }.get(primitive)
    token_dim = 10 if primitive == "dig" else 18
    token_array = None if token is None else np.full(token_dim, token, dtype=np.float32)
    frames = tuple(
        SimpleNamespace(
            action_step_id=start_step + index,
            observation_step_id=start_step + index - 1,
            action=np.asarray(
                [(0.0 if token is None else token * 0.2) + 0.1 * index, 0.0],
                dtype=np.float32,
            ),
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            token=token_array,
            model_token_key=model_key,
            policy_dispatched=True,
        )
        for index in range(3)
    )
    token_sha = None if token is None else f"{primitive}-{token}".replace(".", "_")
    return SimpleNamespace(
        skill_name=primitive,
        model_token_key=model_key,
        token=token_array,
        token_source="recorded_real_token" if token is not None else None,
        token_sha256=token_sha,
        frames=frames,
        start_action_step_id=start_step,
        end_action_step_id=start_step + 2,
        primitive_cycle_indices=(0,),
        frame_count=3,
        segment_id=f"{primitive}:{start_step}-{start_step + 2}:{token_sha or 'unconditioned'}",
    )


def _source_root(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "source"
    (source / "rollouts").mkdir(parents=True)
    (source / "hdf5_rollouts").mkdir()
    (source / "rollouts" / "rollout_000.jsonl").write_text("{}\n", encoding="utf-8")
    with h5py.File(source / "hdf5_rollouts" / "episode_0.hdf5", "w"):
        pass
    checkpoints = tmp_path / "checkpoints"
    policy: dict[str, object] = {
        "act_params": {},
        "dig_low_dim_keys": ["qpos", "qvel", "dig_cut_tokens"],
        "return_low_dim_keys": ["qpos", "qvel", "return_start_envelope_tokens_v1"],
        "carry_low_dim_keys": ["qpos", "qvel"],
        "dump_low_dim_keys": ["qpos", "qvel"],
    }
    for primitive in ("dig", "return", "carry", "dump"):
        directory = checkpoints / primitive
        directory.mkdir(parents=True)
        checkpoint = directory / "policy_best.ckpt"
        checkpoint.write_bytes(f"{primitive}-checkpoint".encode())
        (directory / "dataset_stats.pkl").write_bytes(f"{primitive}-stats".encode())
        policy[f"{primitive}_ckpt_path"] = str(checkpoint)
    (source / "eval_resolved_config.yaml").write_text(
        yaml.safe_dump(
            {
                "task": {
                    "camera_names": ["fpv"],
                    "equipment_model": "yulong",
                    "episode_len": 10,
                },
                "policy": policy,
                "eval": {},
            }
        ),
        encoding="utf-8",
    )
    commit = "a" * 40
    (source / "eval_run_metadata.json").write_text(
        json.dumps({"repo_snapshots": {"repo_a": {"commit": commit}}}),
        encoding="utf-8",
    )
    train = tmp_path / "train.yaml"
    train.write_text(yaml.safe_dump({"task": {}, "train": {}}), encoding="utf-8")
    return source, train, checkpoints


def _install_clean_synthetic_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    oos_dig_alternates: bool,
) -> None:
    segments = [
        _segment(primitive="dig", token=0.0, start_step=10),
        _segment(primitive="dig", token=1.0, start_step=20),
        _segment(primitive="return", token=0.0, start_step=30),
        _segment(primitive="return", token=1.0, start_step=40),
        _segment(primitive="carry", token=None, start_step=50),
        _segment(primitive="dump", token=None, start_step=60),
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
    monkeypatch.setattr(runner, "join_recorded_act_replay_frames", lambda **_kwargs: [])
    monkeypatch.setattr(runner, "split_stable_recorded_act_segments", lambda _frames: segments)
    monkeypatch.setattr(
        runner,
        "select_deterministic_alternate_segment",
        lambda *, segments, baseline: next(
            item for item in segments if item.token_sha256 != baseline.token_sha256
        ),
    )
    monkeypatch.setattr(runner, "_strict_train_support", lambda *_args, **_kwargs: support)

    def assessor(_support):
        def assess(condition, segment):
            primitive = (
                segment.get("primitive", "")
                if isinstance(segment, dict)
                else getattr(segment, "skill_name", "")
            )
            is_dig_alternate = (
                oos_dig_alternates
                and primitive == "dig"
                and float(np.asarray(condition["token"])[0]) == 1.0
            )
            return {"status": "out_of_support" if is_dig_alternate else "supported"}

        return assess

    monkeypatch.setattr(runner, "_support_assessor", assessor)
    monkeypatch.setattr(
        runner,
        "read_recorded_act_observation",
        lambda **kwargs: {
            "qpos": kwargs["frame"].qpos,
            "qvel": kwargs["frame"].qvel,
            **(
                {}
                if kwargs["frame"].model_token_key is None
                else {kwargs["frame"].model_token_key: kwargs["frame"].token}
            ),
            "image_fpv": np.zeros((3, 2, 2), dtype=np.float32),
        },
    )
    monkeypatch.setattr(
        runner,
        "_configure_eval_torch_performance",
        lambda *_args, **_kwargs: SimpleNamespace(as_config_dict=lambda: {"allow_tf32": False}),
    )
    monkeypatch.setattr(
        runner,
        "_clean_code_record",
        lambda: {"git_head": "b" * 40, "git_branch": "test", "worktree_clean": True},
    )


def _factory_builder(primitive: str, _policy_cfg: dict[str, object]):
    return lambda _condition, _replica_id: _Policy(primitive)


def _action_std() -> dict[str, np.ndarray]:
    return {
        primitive: np.asarray([1.0, 1.0], dtype=np.float32)
        for primitive in ("dig", "return", "carry", "dump")
    }


def test_runner_rejects_dirty_worktree_before_reading_or_loading_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    loaded = False

    def should_not_load(*_args, **_kwargs):
        nonlocal loaded
        loaded = True
        raise AssertionError("policy/data loading must not happen on a dirty worktree")

    monkeypatch.setattr(
        runner,
        "_clean_code_record",
        lambda: {"git_head": "x", "git_branch": "test", "worktree_clean": False},
    )
    monkeypatch.setattr(runner, "_source_paths", should_not_load)

    with pytest.raises(RuntimeError, match="clean Git worktree"):
        runner.run_act_goal_condition_sensitivity_audit(
            source_results_root=source,
            dig_training_config_path=tmp_path / "dig.yaml",
            return_training_config_path=tmp_path / "return.yaml",
            output_root=tmp_path / "out",
            policy_factory_builder=_factory_builder,
            action_std_by_primitive=_action_std(),
        )
    assert loaded is False
    assert not (tmp_path / "out").exists()


def test_runner_writes_six_files_with_lineage_oos_precedence_and_isolation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, train, _checkpoints = _source_root(tmp_path)
    _install_clean_synthetic_dependencies(monkeypatch, oos_dig_alternates=True)

    result = runner.run_act_goal_condition_sensitivity_audit(
        source_results_root=source,
        dig_training_config_path=train,
        return_training_config_path=train,
        output_root=tmp_path / "act_goal_condition_sensitivity_v1",
        device="cpu",
        policy_factory_builder=_factory_builder,
        action_std_by_primitive=_action_std(),
    )

    assert result["status"] == "completed"
    output = Path(result["output_root"])
    assert sorted(path.name for path in output.iterdir()) == [
        "baseline.json",
        "carry_dump_isolation.json",
        "dig.json",
        "manifest.json",
        "report.md",
        "return.json",
    ]
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_lineage"]["artifact_repo_commit"] == "a" * 40
    assert set(manifest["source_lineage"]["checkpoints_and_stats"]) == {
        "dig",
        "return",
        "carry",
        "dump",
    }
    assert manifest["primitive_aggregate_classification"]["dig"] == "out_of_support"
    assert manifest["primitive_aggregate_classification"]["return"] == (
        "goal_response_plausible"
    )
    isolation = json.loads((output / "carry_dump_isolation.json").read_text())
    assert isolation["status"] == "completed"
    for primitive in ("carry", "dump"):
        assert isolation["checks"][primitive]["comparison"]["passed"] is True
        assert isolation["checks"][primitive]["extraneous_dig_token"][
            "injected_input_key"
        ] == "dig_cut_tokens"
