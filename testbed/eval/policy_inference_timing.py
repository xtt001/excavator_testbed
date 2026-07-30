"""Small, reusable wall-clock timing boundary for live policy inference."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import numpy as np


class PredictPolicy(Protocol):
    def predict(self, obs: dict[str, Any]) -> np.ndarray: ...


def timed_policy_predict(
    policy: PredictPolicy,
    obs: Mapping[str, Any],
    *,
    monotonic: Callable[[], float] = time.perf_counter,
) -> tuple[np.ndarray, float]:
    """Return the action and end-to-end ``Policy.predict`` wall time in ms."""

    started = monotonic()
    action = policy.predict(dict(obs))
    elapsed_ms = (monotonic() - started) * 1000.0
    if not np.isfinite(elapsed_ms) or elapsed_ms < 0.0:
        raise RuntimeError("policy_inference_latency_invalid")
    return np.asarray(action, dtype=np.float32), float(elapsed_ms)


__all__ = ["timed_policy_predict"]
