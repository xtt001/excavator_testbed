from __future__ import annotations

import importlib
import importlib.util


def _torch_performance_module():
    spec = importlib.util.find_spec("testbed.runtime.torch_performance")
    assert spec is not None
    return importlib.import_module("testbed.runtime.torch_performance")


def test_train_torch_performance_defaults_keep_training_throughput() -> None:
    torch_performance = _torch_performance_module()

    config = torch_performance.train_torch_performance_config({})

    assert config.cudnn_benchmark is True
    assert config.allow_tf32 is True
    assert config.matmul_precision == "high"


def test_eval_torch_performance_defaults_disable_tf32_for_reproducible_rollout() -> None:
    torch_performance = _torch_performance_module()

    config = torch_performance.eval_torch_performance_config({})

    assert config.cudnn_benchmark is False
    assert config.allow_tf32 is False
    assert config.matmul_precision == "highest"


def test_torch_performance_config_preserves_explicit_eval_overrides() -> None:
    torch_performance = _torch_performance_module()

    config = torch_performance.eval_torch_performance_config(
        {
            "cudnn_benchmark": True,
            "allow_tf32": True,
            "matmul_precision": "high",
        }
    )

    assert config.cudnn_benchmark is True
    assert config.allow_tf32 is True
    assert config.matmul_precision == "high"


def test_eval_runtime_writes_torch_performance_config_for_resolved_config(
    monkeypatch,
) -> None:
    from testbed.runtime import _eval

    assert hasattr(_eval, "_configure_eval_torch_performance")
    applied = []
    monkeypatch.setattr(
        _eval,
        "configure_torch_performance",
        lambda config, *, device: applied.append((config, device)),
    )
    eval_cfg = {}

    config = _eval._configure_eval_torch_performance(eval_cfg, device="cuda")

    assert config.allow_tf32 is False
    assert eval_cfg["allow_tf32"] is False
    assert eval_cfg["cudnn_benchmark"] is False
    assert eval_cfg["matmul_precision"] == "highest"
    assert applied == [(config, "cuda")]
