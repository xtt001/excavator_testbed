"""
Excavator tasks for MuJoCo.

Joint-space task (used by SimBackend for training/eval):
    ExcavatorLiftingCubeTask

EE-space task (used by EESimBackend for scripted demo collection):
    ExcavatorLiftingCubeEETask

The reward / phase logic is implemented here because it requires live
physics state (contact pairs, qpos). The *pure* phase-state machine
that needs no physics lives in testbed/tasks/logic/excavator_reward.py.
"""

from __future__ import annotations

import collections

import numpy as np
from dm_control.suite import base

from testbed.backends.mujoco.tasks.bimanual import BOX_POSE, _contact_pairs
from testbed.backends.mujoco.tasks.constants import (
    EXCAVATOR_MAIN_JOINTS,
    EXCAVATOR_START_POSE,
)
from testbed.tasks.logic.excavator_reward import ExcavatorPhaseTracker

# ─── Joint-space task (SimBackend) ────────────────────────────────────────────

class ExcavatorLiftingCubeTask(base.Task):
    """
    4-DOF excavator joint-space task.
    action = [swing, boom, stick, bucket]  (rad)
    """

    def __init__(self, random=None):
        super().__init__(random=random)
        self.max_reward = 4
        self._tracker = ExcavatorPhaseTracker()

    # dm_control interface ────────────────────────────────────────────────────

    def before_step(self, action, physics):
        if len(action) != len(EXCAVATOR_MAIN_JOINTS):
            raise ValueError(
                f"Excavator action must be {len(EXCAVATOR_MAIN_JOINTS)}-D, got {len(action)}"
            )
        np.copyto(physics.data.ctrl, action)

    def initialize_episode(self, physics):
        self._tracker.reset()
        with physics.reset_context():
            for joint_name, val in zip(EXCAVATOR_MAIN_JOINTS, EXCAVATOR_START_POSE):
                physics.named.data.qpos[joint_name] = val
            np.copyto(physics.data.ctrl, EXCAVATOR_START_POSE)
            assert BOX_POSE[0] is not None
            box_jid = physics.model.name2id("red_box_joint", "joint")
            box_idx = physics.model.jnt_qposadr[box_jid]
            physics.data.qpos[box_idx : box_idx + 7] = BOX_POSE[0]
        physics.forward()
        super().initialize_episode(physics)

    def get_qpos(self, physics) -> np.ndarray:
        indices = [
            physics.model.jnt_qposadr[physics.model.name2id(j, "joint")]
            for j in EXCAVATOR_MAIN_JOINTS
        ]
        return physics.data.qpos[indices].copy()

    def get_qvel(self, physics) -> np.ndarray:
        indices = [
            physics.model.jnt_dofadr[physics.model.name2id(j, "joint")]
            for j in EXCAVATOR_MAIN_JOINTS
        ]
        return physics.data.qvel[indices].copy()

    @staticmethod
    def get_env_state(physics) -> np.ndarray:
        box_jid = physics.model.name2id("red_box_joint", "joint")
        box_idx = physics.model.jnt_qposadr[box_jid]
        return physics.data.qpos[box_idx:].copy()

    def get_observation(self, physics) -> dict:
        obs = collections.OrderedDict()
        obs["qpos"] = self.get_qpos(physics)
        obs["qvel"] = self.get_qvel(physics)
        obs["env_state"] = self.get_env_state(physics)
        obs["images"] = {
            "top": physics.render(height=480, width=640, camera_id="top"),
            "angle": physics.render(height=480, width=640, camera_id="angle"),
            "vis": physics.render(height=480, width=640, camera_id="front_close"),
        }
        return obs

    def get_reward(self, physics) -> float:
        pairs = _contact_pairs(physics)
        box_state = self.get_env_state(physics)
        swing_q = float(physics.named.data.qpos["j1_swing"])
        return self._tracker.update(
            contact_pairs=pairs,
            box_xyz=box_state[:3],
            swing_q=swing_q,
        )


# ─── EE-space task (EESimBackend, scripted collection only) ───────────────────

class ExcavatorLiftingCubeEETask(base.Task):
    """
    EE-space excavator task for scripted demo collection.
    Inherits from base.Task directly (not BimanualViperXEETask) to keep
    excavator-specific logic explicit and avoid deep inheritance confusion.
    """

    def __init__(self, random=None):
        super().__init__(random=random)
        self.max_reward = 4
        self._tracker = ExcavatorPhaseTracker()

    # ── Robot initialisation ─────────────────────────────────────────────────

    def _init_robots(self, physics):
        for joint_name, val in zip(EXCAVATOR_MAIN_JOINTS, EXCAVATOR_START_POSE):
            physics.named.data.qpos[joint_name] = val
        physics.forward()
        np.copyto(physics.data.mocap_pos[0], np.array([4.8, 0.0, 0.45]))
        np.copyto(physics.data.mocap_quat[0], [1, 0, 0, 0])
        np.copyto(physics.data.ctrl, EXCAVATOR_START_POSE)

    def initialize_episode(self, physics):
        self._tracker.reset()
        self._init_robots(physics)
        from testbed.backends.mujoco.tasks.sampling import sample_box_pose_for_excavator
        cube_pose = sample_box_pose_for_excavator()
        box_jid = physics.model.name2id("red_box_joint", "joint")
        np.copyto(physics.data.qpos[box_jid : box_jid + 7], cube_pose)
        super().initialize_episode(physics)

    # ── Action dispatch ───────────────────────────────────────────────────────

    def before_step(self, action, physics):
        if len(action) == len(EXCAVATOR_MAIN_JOINTS):
            # joint-space action (ExcavatorJointSpaceDigDumpPolicy)
            np.copyto(physics.data.ctrl, action)
        else:
            # EE-space action: [x, y, z, qw, qx, qy, qz]
            np.copyto(physics.data.mocap_pos[0], action[:3])
            np.copyto(physics.data.mocap_quat[0], action[3:7])

    # ── Observation ───────────────────────────────────────────────────────────

    @staticmethod
    def _get_joint_idx(physics, joint_name: str, kind: str) -> int:
        jid = physics.model.name2id(joint_name, "joint")
        return int(physics.model.jnt_qposadr[jid] if kind == "qpos" else physics.model.jnt_dofadr[jid])

    def _get_excavator_qpos(self, physics) -> np.ndarray:
        idx = [self._get_joint_idx(physics, j, "qpos") for j in EXCAVATOR_MAIN_JOINTS]
        return physics.data.qpos[idx].copy()

    def _get_excavator_qvel(self, physics) -> np.ndarray:
        idx = [self._get_joint_idx(physics, j, "qvel") for j in EXCAVATOR_MAIN_JOINTS]
        return physics.data.qvel[idx].copy()

    @staticmethod
    def get_env_state(physics) -> np.ndarray:
        box_jid = physics.model.name2id("red_box_joint", "joint")
        box_idx = physics.model.jnt_qposadr[box_jid]
        return physics.data.qpos[box_idx:].copy()

    def get_observation(self, physics) -> dict:
        obs = collections.OrderedDict()
        obs["qpos"] = self._get_excavator_qpos(physics)
        obs["qvel"] = self._get_excavator_qvel(physics)
        obs["env_state"] = self.get_env_state(physics)
        obs["images"] = {
            "top": physics.render(height=480, width=640, camera_id="top"),
            "angle": physics.render(height=480, width=640, camera_id="angle"),
            "vis": physics.render(height=480, width=640, camera_id="front_close"),
        }
        # mocap pose used by scripted policies
        obs["mocap_pose_right"] = np.concatenate(
            [physics.data.mocap_pos[0], physics.data.mocap_quat[0]]
        ).copy()
        obs["gripper_ctrl"] = physics.data.ctrl.copy()
        return obs

    def get_reward(self, physics) -> float:
        pairs = _contact_pairs(physics)
        box_state = self.get_env_state(physics)
        swing_q = float(physics.named.data.qpos["j1_swing"])
        return self._tracker.update(
            contact_pairs=pairs,
            box_xyz=box_state[:3],
            swing_q=swing_q,
        )
