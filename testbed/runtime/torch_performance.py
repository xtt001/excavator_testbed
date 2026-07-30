"""Torch backend performance and reproducibility settings for runtime commands."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import torch


@dataclass(frozen=True)
class TorchPerformanceConfig:
    """Resolved torch backend knobs for train/eval runtime commands."""

    cudnn_benchmark: bool
    allow_tf32: bool
    matmul_precision: str

    def as_config_dict(self) -> dict[str, bool | str]:
        return {
            "cudnn_benchmark": bool(self.cudnn_benchmark),
            "allow_tf32": bool(self.allow_tf32),
            "matmul_precision": str(self.matmul_precision),
        }


def train_torch_performance_config(
    train_cfg: Mapping[str, Any],
) -> TorchPerformanceConfig:
    """Resolve train defaults that preserve the existing throughput-oriented path."""

    return _resolve_torch_performance_config(
        train_cfg,
        default_cudnn_benchmark=True,
        default_allow_tf32=True,
        default_matmul_precision="high",
    )


def eval_torch_performance_config(
    eval_cfg: Mapping[str, Any],
) -> TorchPerformanceConfig:
    """Resolve eval defaults that prioritize reproducible rollout behavior."""

    return _resolve_torch_performance_config(
        eval_cfg,
        default_cudnn_benchmark=False,
        default_allow_tf32=False,
        default_matmul_precision="highest",
    )


def configure_torch_performance(
    config: TorchPerformanceConfig,
    *,
    device: str,
) -> None:
    """Apply torch backend settings when the requested runtime device is CUDA."""

    if not str(device).startswith("cuda") or not torch.cuda.is_available():
        return
    torch.backends.cudnn.benchmark = bool(config.cudnn_benchmark)
    allow_tf32 = bool(config.allow_tf32)
    torch.backends.cuda.matmul.allow_tf32 = allow_tf32
    torch.backends.cudnn.allow_tf32 = allow_tf32
    precision = str(config.matmul_precision)
    if precision:
        torch.set_float32_matmul_precision(precision)


def _resolve_torch_performance_config(
    cfg: Mapping[str, Any],
    *,
    default_cudnn_benchmark: bool,
    default_allow_tf32: bool,
    default_matmul_precision: str,
) -> TorchPerformanceConfig:
    return TorchPerformanceConfig(
        cudnn_benchmark=bool(cfg.get("cudnn_benchmark", default_cudnn_benchmark)),
        allow_tf32=bool(cfg.get("allow_tf32", default_allow_tf32)),
        matmul_precision=str(cfg.get("matmul_precision", default_matmul_precision)),
    )


__all__ = [
    "TorchPerformanceConfig",
    "configure_torch_performance",
    "eval_torch_performance_config",
    "train_torch_performance_config",
]
