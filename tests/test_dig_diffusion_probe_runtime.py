from __future__ import annotations

from testbed.eval.dig_diffusion_probe_runtime import (
    build_minimal_dp_probe_contract,
    minimal_dp_probe_code_paths,
    run_minimal_dp_probe_dry_run,
)


def test_probe_contract_freezes_seeds_sampler_and_nonpromotion() -> None:
    contract = build_minimal_dp_probe_contract(training_updates=1000)

    assert contract["training_seeds"] == [0, 1, 2]
    assert contract["inference_noise_seeds"] == [100, 101, 102]
    assert contract["data"]["camera_order"] == [
        "stick_up",
        "stick_down",
        "eye_left",
        "eye_right",
    ]
    assert contract["data"]["low_dim_order"] == [
        "qpos",
        "qvel",
        "dig_cut_tokens",
    ]
    assert contract["dispatch"]["temporal_aggregation"] is False
    assert contract["dispatch"]["resample_chunk_every_frame"] is True
    assert contract["dispatch"]["query_dispatched"] == 0
    assert contract["promotion_eligible"] is False
    assert contract["unity_allowed"] is False
    assert contract["reproducibility"] == {
        "allow_tf32": False,
        "cudnn_benchmark": False,
        "cudnn_deterministic": True,
        "deterministic_algorithms": True,
        "matmul_precision": "highest",
        "cublas_workspace_config": ":4096:8",
    }


def test_probe_dry_run_never_trains_or_calls_backend() -> None:
    result = run_minimal_dp_probe_dry_run(training_updates=1000)

    assert result["status"] == "dry_run"
    assert result["training_started"] is False
    assert result["backend_called"] is False
    assert result["unity_started"] is False
    assert result["action_sent"] is False


def test_probe_code_lineage_includes_projection_and_artifact_dependencies() -> None:
    paths = set(minimal_dp_probe_code_paths())

    assert {
        "testbed/eval/dig_goal_action_lineage.py",
        "testbed/eval/dig_receding_horizon_artifacts.py",
        "testbed/eval/dig_receding_horizon_lineage.py",
        "testbed/eval/dig_receding_horizon_metrics.py",
        "testbed/eval/dig_receding_horizon_runtime.py",
    } <= paths
