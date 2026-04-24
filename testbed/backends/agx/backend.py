"""
SimBackend adapter for the Unity AGX step-ack server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.backends.base import SimBackend
from testbed.backends.agx.protocol import (
    AgxProtocolError,
    AgxSimClient,
    GetInfoResponse,
    StepResponse,
)
from testbed.tasks.logic.excavator_reward import (
    AGX_DEPOSITED_MASS_IN_TARGET_BOX,
    AGX_EXCAVATED_MASS,
    AGX_MASS_IN_BUCKET,
    AGX_MASS_IN_TARGET_BOX,
    AGX_MIN_DISTANCE_TO_DIG_AREA,
    AGX_MIN_DISTANCE_TO_TARGET,
    AGX_TARGET_CONTACT_MAX_NORMAL_FORCE_N,
    AGX_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE,
    AGX_TARGET_HARD_COLLISION_COUNT,
    AgxExcavationRewardTracker,
    get_agx_excavation_mission,
)


@dataclass
class AgxTimeStep:
    observation: dict[str, Any]
    reward: float = 0.0
    done: bool = False
    info: dict[str, Any] = field(default_factory=dict)


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
        task_name: str = "agx_excavation_teleop",
        timeout_s: float | None = None,
        timeout: float | None = None,
        reset_terrain: bool = True,
        reset_pose: bool = True,
        scenario_id: str | None = None,
        reward_overrides: dict[str, Any] | None = None,
    ) -> None:
        if timeout_s is None:
            timeout_s = 5.0 if timeout is None else float(timeout)
        self._client = AgxSimClient(host=host, port=port, timeout_s=timeout_s)
        self._info: GetInfoResponse | None = None
        self._next_step_id = 0
        self._last_obs: dict[str, Any] | None = None
        self._reset_terrain = bool(reset_terrain)
        self._reset_pose = bool(reset_pose)
        self._scenario_id = None if scenario_id in (None, "") else str(scenario_id)
        self._task_name = str(task_name)
        self._reward_overrides = dict(reward_overrides or {})
        self._mission = None
        self._reward_tracker: AgxExcavationRewardTracker | None = None

    def close(self) -> None:
        self._client.close()

    def get_info(self) -> GetInfoResponse:
        if self._info is None:
            self._info = self._call_with_resync(
                self._client.get_info,
                action_name="get_info",
            )
        if self._reward_tracker is None:
            env_state_order = getattr(
                self._info,
                "env_state_order",
                (
                    AGX_MASS_IN_BUCKET,
                    AGX_EXCAVATED_MASS,
                    AGX_MASS_IN_TARGET_BOX,
                    AGX_DEPOSITED_MASS_IN_TARGET_BOX,
                    AGX_MIN_DISTANCE_TO_TARGET,
                    AGX_TARGET_HARD_COLLISION_COUNT,
                    AGX_TARGET_CONTACT_MAX_NORMAL_FORCE_N,
                    AGX_MIN_DISTANCE_TO_DIG_AREA,
                    AGX_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE,
                ),
            )
            self._mission = get_agx_excavation_mission(
                self._task_name,
                **self._reward_overrides,
            )
            self._reward_tracker = AgxExcavationRewardTracker(
                mission=self._mission,
                env_state_order=env_state_order,
            )
        return self._info

    def reset(
        self,
        seed: int | None = None,
        *,
        reset_terrain: bool | None = None,
        reset_pose: bool | None = None,
        scenario_id: str | None = None,
    ) -> Any:
        info = self.get_info()
        if self._reward_tracker is not None:
            self._reward_tracker.reset()
        reset_response = self._call_with_resync(
            lambda: self._client.reset(
                seed=0 if seed is None else int(seed),
                reset_terrain=self._reset_terrain if reset_terrain is None else bool(reset_terrain),
                reset_pose=self._reset_pose if reset_pose is None else bool(reset_pose),
                scenario_id=self._scenario_id if scenario_id is None else scenario_id,
            ),
            action_name="reset",
        )
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
        self.get_info()
        return float(self._mission.max_reward) if self._mission is not None else 0.0

    def set_initial_object_pose(self, pose: np.ndarray) -> None:
        raise NotImplementedError(
            "Unity AGX backend does not support direct object-pose injection."
        )

    def _step_with_id(self, step_id: int, action: np.ndarray) -> AgxTimeStep:
        self.get_info()
        response = self._client.step(step_id=step_id, action=action)
        obs = self._obs_from_step_response(response)
        self._last_obs = obs
        reward = float(response.reward)
        reward_phase = "unity_raw"
        task_success = False
        task_step_successes: list[str] = []
        task_step_failures: list[str] = []
        task_metrics: dict[str, float] = {}

        if self._reward_tracker is not None:
            step_result = self._reward_tracker.update(response.env_state)
            reward = float(step_result.reward)
            reward_phase = step_result.phase_label
            task_success = bool(step_result.success)
            task_step_successes = list(step_result.step_successes)
            task_step_failures = list(step_result.step_failures)
            task_metrics = dict(step_result.metrics)
            obs["reward_phase"] = reward_phase
            obs["task_success"] = task_success
            obs["task_step_successes"] = list(task_step_successes)
            obs["task_step_failures"] = list(task_step_failures)
            obs["task_metrics"] = dict(task_metrics)

        info = {
            "step_id": int(response.step_id),
            "sim_time_ns": int(response.sim_time_ns),
            "image_format": response.image_format,
            "warnings": list(response.warnings),
            "raw_reward_unity": float(response.reward),
            "reward_phase": reward_phase,
            "task_success": task_success,
            "task_step_successes": list(task_step_successes),
            "task_step_failures": list(task_step_failures),
            "task_metrics": dict(task_metrics),
        }
        return AgxTimeStep(
            observation=obs,
            reward=reward,
            done=False,
            info=info,
        )

    def _call_with_resync(self, fn, *, action_name: str):
        try:
            return fn()
        except AgxProtocolError as exc:
            if "unexpected response type" not in str(exc):
                raise
            self._client.close()
            if action_name == "get_info":
                self._info = None
            return fn()

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


AGXSimBackend = AgxSimBackend
AGXTimestep = AgxTimeStep
