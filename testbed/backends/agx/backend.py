"""
SimBackend adapter for the Unity AGX step-ack server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.backends.base import SimBackend
from testbed.backends.agx.protocol import AgxSimClient, GetInfoResponse, StepResponse


@dataclass
class AgxTimeStep:
    observation: dict[str, Any]
    reward: float = 0.0


class AgxSimBackend(SimBackend):
    """
    Thin socket-backed SimBackend for the Unity project.

    Current Unity RESET responses do not include an observation payload, so
    reset() performs RESET followed by one zero-action STEP to obtain the first
    usable observation for the testbed.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5057,
        *,
        timeout_s: float = 5.0,
    ) -> None:
        self._client = AgxSimClient(host=host, port=port, timeout_s=timeout_s)
        self._info: GetInfoResponse | None = None
        self._next_step_id = 0
        self._last_obs: dict[str, Any] | None = None

    def close(self) -> None:
        self._client.close()

    def get_info(self) -> GetInfoResponse:
        if self._info is None:
            self._info = self._client.get_info()
        return self._info

    def reset(self, seed: int | None = None) -> Any:
        info = self.get_info()
        reset_response = self._client.reset(seed=0 if seed is None else int(seed))
        self._next_step_id = 0
        ts = self._step_with_id(
            step_id=self._next_step_id,
            action=np.zeros(len(info.action_order), dtype=np.float32),
        )
        self._next_step_id += 1
        ts.observation["reset_applied"] = reset_response.reset_applied
        ts.observation["reset_warnings"] = list(reset_response.warnings)
        return ts

    def step(self, action: np.ndarray) -> Any:
        ts = self._step_with_id(step_id=self._next_step_id, action=action)
        self._next_step_id += 1
        return ts

    def render(self, camera_id: str, height: int = 480, width: int = 640) -> np.ndarray:
        if self._last_obs is None:
            raise RuntimeError("No observation available yet; call reset() first.")

        image = self._last_obs.get("images", {}).get(camera_id)
        if image is None:
            raise KeyError(f"Camera {camera_id!r} not found in latest observation.")

        if image.shape[:2] == (height, width):
            return image.copy()

        import cv2

        return cv2.resize(image, (width, height), interpolation=cv2.INTER_LINEAR)

    @property
    def dt(self) -> float:
        return float(self.get_info().dt)

    @property
    def max_reward(self) -> float:
        return 0.0

    def set_initial_object_pose(self, pose: np.ndarray) -> None:
        raise NotImplementedError(
            "Unity AGX backend does not support direct object-pose injection."
        )

    def _step_with_id(self, step_id: int, action: np.ndarray) -> AgxTimeStep:
        response = self._client.step(step_id=step_id, action=action)
        obs = self._obs_from_step_response(response)
        self._last_obs = obs
        return AgxTimeStep(observation=obs, reward=float(response.reward))

    def _obs_from_step_response(self, response: StepResponse) -> dict[str, Any]:
        image = response.decode_rgb_image()
        images = {"fpv": image.copy()} if image is not None else {}

        return {
            "qpos": response.qpos.astype(np.float32, copy=True),
            "qvel": response.qvel.astype(np.float32, copy=True),
            "images": images,
            "env_state": response.env_state.astype(np.float32, copy=True),
            "step_id": int(response.step_id),
            "sim_time_ns": int(response.sim_time_ns),
            "image_format": response.image_format,
            "warnings": list(response.warnings),
        }
