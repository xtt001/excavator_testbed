"""
AGXSimBackend — SimBackend implementation backed by the AGXUnity socket bridge.

This is the ONLY file in the testbed that knows about AGX specifics.
Everything above this layer (runner, recorder, evaluator) uses SimBackend.

Observation dict returned by reset() and step():
──────────────────────────────────────────────────
{
    "qpos":      np.ndarray (3,)  float32  [boom, stick, bucket] position_norm
    "qvel":      np.ndarray (4,)  float32  [swing, boom, stick, bucket] speed
    "env_state": np.ndarray (M,)  float32  includes mass_in_bucket at known index
    "images": {
        "fpv":   np.ndarray (H, W, 3) uint8  (None if image_format=NONE)
    }
}

Timestep-like object (AGXTimestep):
    .observation  → dict above
    .reward       → float
    .done         → bool  (always False in V0, evaluator decides)
    .info         → dict  (step_id, sim_time_ns etc.)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.backends.base import SimBackend
from testbed.backends.agx.client import AGXSimClient
from testbed.backends.agx.protocol import (
    ACTION_DIM,
    ImageFormat,
    ResetReq,
    StepReq,
)

log = logging.getLogger(__name__)


# ─── Timestep container ──────────────────────────────────────────────────────

@dataclass
class AGXTimestep:
    """Return type of AGXSimBackend.step() / .reset()."""
    observation: dict[str, Any]
    reward:      float = 0.0
    done:        bool  = False
    info:        dict[str, Any] = field(default_factory=dict)


# ─── Backend ─────────────────────────────────────────────────────────────────

class AGXSimBackend(SimBackend):
    """
    SimBackend backed by AGXUnity over TCP.

    Parameters
    ----------
    host         Unity machine IP / hostname.
    port         Unity bridge port.
    timeout      Socket timeout (seconds).
    auto_connect If True, connect on first reset() call automatically.
    """

    def __init__(
        self,
        host:         str   = "127.0.0.1",
        port:         int   = 9000,
        timeout:      float = 10.0,
        auto_connect: bool  = True,
    ) -> None:
        self._client = AGXSimClient(host=host, port=port, timeout=timeout)
        self._auto_connect  = auto_connect
        self._connected     = False
        self._step_id       = 0
        self._dt:           float = 0.02
        self._control_hz:   float = 50.0
        self._info:         dict  = {}

    # ─── SimBackend interface ─────────────────────────────────────────────────

    def reset(self, seed: int | None = None) -> AGXTimestep:
        """
        Connect (if needed), send RESET, and return the first observation.

        The first observation is obtained by sending a zero-action STEP
        immediately after reset so we have a valid obs to hand to the policy.
        """
        if not self._connected:
            self._client.connect()
            self._connected = True
            try:
                info = self._client.get_info()
                self._info = info.raw
                log.info("AGX capabilities: %s", self._info)
            except Exception as exc:
                log.warning("GET_INFO failed (non-fatal): %s", exc)

        req = ResetReq(
            seed=seed if seed is not None else -1,
            reset_terrain=True,
            reset_pose=True,
        )
        resp = self._client.reset(req)
        self._dt         = resp.dt
        self._control_hz = resp.control_hz
        self._step_id    = 0

        # Get first observation via a zero-action step
        zero = np.zeros(ACTION_DIM, dtype=np.float32)
        ts = self._do_step(zero)
        return ts

    def step(self, action: np.ndarray) -> AGXTimestep:
        """Apply action and return next observation."""
        return self._do_step(action.astype(np.float32))

    def render(self, camera_id: str = "fpv", height: int = 480, width: int = 640) -> np.ndarray:
        """
        Return the most recently received fpv frame.
        AGX delivers images inline with STEP_RESP so this is a pass-through.
        """
        log.warning("AGXSimBackend.render() called outside step loop — no fresh frame")
        return np.zeros((height, width, 3), dtype=np.uint8)

    @property
    def dt(self) -> float:
        return self._dt

    @property
    def max_reward(self) -> float:
        # V0: reward is computed in evaluator, not in env
        return 1.0

    def set_initial_object_pose(self, pose: np.ndarray) -> None:
        # AGX terrain is reset via RESET_REQ; per-object pose not in V0 API
        log.warning("set_initial_object_pose() is not supported by AGXSimBackend in V0")

    # ─── Connection lifecycle ─────────────────────────────────────────────────

    def connect(self) -> None:
        """Explicitly connect (optional — reset() auto-connects if needed)."""
        if not self._connected:
            self._client.connect()
            self._connected = True

    def close(self) -> None:
        """Close the socket connection."""
        self._client.close()
        self._connected = False

    def __enter__(self) -> "AGXSimBackend":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _do_step(self, action: np.ndarray) -> AGXTimestep:
        req = StepReq(
            step_id=self._step_id,
            action=action,
            client_time_ns=time.time_ns(),
        )
        resp = self._client.step(req)
        self._step_id += 1

        obs = self._build_obs(resp)
        info = {
            "step_id":  resp.step_id,
            "image_fmt": resp.image_fmt.name,
        }
        return AGXTimestep(observation=obs, reward=resp.reward, done=False, info=info)

    @staticmethod
    def _build_obs(resp) -> dict[str, Any]:
        images: dict[str, np.ndarray | None] = {}
        if resp.image is not None:
            images["fpv"] = resp.image
        return {
            "qpos":      resp.qpos,       # (3,) float32
            "qvel":      resp.qvel,       # (4,) float32
            "env_state": resp.env_state,  # (M,) float32
            "images":    images,
        }

    # ─── Accessors ────────────────────────────────────────────────────────────

    @property
    def step_id(self) -> int:
        """Current step counter (monotonically increasing within an episode)."""
        return self._step_id

    @property
    def backend_info(self) -> dict:
        """GET_INFO response from the last connect."""
        return self._info
