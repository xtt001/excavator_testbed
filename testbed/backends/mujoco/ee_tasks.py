"""
EE-space task classes for non-excavator robots (vx300s, fairino5).

These mirror ee_sim_env.py from legacy/ but:
  - use clean imports from testbed.backends.mujoco.tasks.*
  - have no top-level IPython.embed calls
  - excavator EE task lives in tasks/excavator.py instead
"""

from __future__ import annotations

import collections

import numpy as np
from dm_control import mujoco as mj_lib
from dm_control.suite import base

from testbed.backends.mujoco.tasks.bimanual import BOX_POSE, _contact_pairs
from testbed.backends.mujoco.tasks.constants import (
    EXCAVATOR_MAIN_JOINTS,
    EXCAVATOR_START_POSE,
    PUPPET_GRIPPER_POSITION_CLOSE,
    START_ARM_POSE,
    START_FAIRINO_POSE,
    START_SINGLE_ARM_POSE,
    puppet_gripper_pos_normalize,
    puppet_gripper_pos_unnormalize,
    puppet_gripper_vel_normalize,
)
from testbed.backends.mujoco.tasks.sampling import sample_box_pose, sample_insertion_pose


# ─── Base EE Task ─────────────────────────────────────────────────────────────

class BimanualViperXEETask(base.Task):
    """Base task for EE-space environments (mocap-driven IK)."""

    def __init__(self, random=None, arm_nums: int = 2, equipment_model: str = "vx300s_bimanual"):
        super().__init__(random=random)
        self.arm_nums = arm_nums
        self.equipment_model = equipment_model

    def _is_excavator(self) -> bool:
        return "excavator_simple" in self.equipment_model

    @staticmethod
    def _joint_qpos_idx(physics, name: str) -> int:
        jid = physics.model.name2id(name, "joint")
        return int(physics.model.jnt_qposadr[jid])

    @staticmethod
    def _joint_qvel_idx(physics, name: str) -> int:
        jid = physics.model.name2id(name, "joint")
        return int(physics.model.jnt_dofadr[jid])

    def before_step(self, action, physics):
        if self.arm_nums == 2:
            a = len(action) // 2
            al, ar = action[:a], action[a:]
            np.copyto(physics.data.mocap_pos[0], al[:3])
            np.copyto(physics.data.mocap_quat[0], al[3:7])
            np.copyto(physics.data.mocap_pos[1], ar[:3])
            np.copyto(physics.data.mocap_quat[1], ar[3:7])
            gl = puppet_gripper_pos_unnormalize(al[7])
            gr = puppet_gripper_pos_unnormalize(ar[7])
            np.copyto(physics.data.ctrl, [gl, -gl, gr, -gr])
        elif self.arm_nums == 1:
            ar = action
            if self._is_excavator():
                if len(ar) == len(EXCAVATOR_MAIN_JOINTS):
                    np.copyto(physics.data.ctrl, ar)
                else:
                    np.copyto(physics.data.mocap_pos[0], ar[:3])
                    np.copyto(physics.data.mocap_quat[0], ar[3:7])
            else:
                np.copyto(physics.data.mocap_pos[0], ar[:3])
                np.copyto(physics.data.mocap_quat[0], ar[3:7])
                gr = puppet_gripper_pos_unnormalize(ar[7])
                np.copyto(physics.data.ctrl, [gr, -gr])

    def initialize_robots(self, physics):
        if self.arm_nums == 2:
            physics.named.data.qpos[:16] = START_ARM_POSE
            np.copyto(physics.data.mocap_pos[0], [-0.31718881, 0.5, 0.29525084])
            np.copyto(physics.data.mocap_quat[0], [1, 0, 0, 0])
            np.copyto(physics.data.mocap_pos[1], [0.31718881, 0.49999888, 0.29525084])
            np.copyto(physics.data.mocap_quat[1], [1, 0, 0, 0])
            np.copyto(
                physics.data.ctrl,
                [PUPPET_GRIPPER_POSITION_CLOSE, -PUPPET_GRIPPER_POSITION_CLOSE,
                 PUPPET_GRIPPER_POSITION_CLOSE, -PUPPET_GRIPPER_POSITION_CLOSE],
            )
        elif self.arm_nums == 1:
            if "vx300s_single" in self.equipment_model:
                physics.named.data.qpos[:8] = START_SINGLE_ARM_POSE
                physics.forward()
                np.copyto(physics.data.mocap_pos[0], [-0.095, 0.50, 0.425])
                np.copyto(physics.data.mocap_quat[0], [1, 0, 0, 0])
            elif "fairino5_single" in self.equipment_model:
                physics.named.data.qpos[:8] = START_FAIRINO_POSE
                physics.forward()
                tcp_pos = physics.named.data.site_xpos["tcp_center"].copy()
                tcp_mat = physics.named.data.site_xmat["tcp_center"].copy()
                tcp_quat = np.zeros(4)
                mj_lib.mju_mat2Quat(tcp_quat, tcp_mat.reshape(9))
                np.copyto(physics.data.mocap_pos[0], tcp_pos)
                np.copyto(physics.data.mocap_quat[0], tcp_quat)
            np.copyto(physics.data.ctrl, [PUPPET_GRIPPER_POSITION_CLOSE, -PUPPET_GRIPPER_POSITION_CLOSE])

    def get_qpos(self, physics) -> np.ndarray:
        raw = physics.data.qpos.copy()
        if self.arm_nums == 2:
            l, r = raw[:8], raw[8:16]
            return np.concatenate(
                [l[:6], [puppet_gripper_pos_normalize(l[6])],
                 r[:6], [puppet_gripper_pos_normalize(r[6])]]
            )
        elif self.arm_nums == 1:
            r = raw[:8]
            return np.concatenate([r[:6], [puppet_gripper_pos_normalize(r[6])]])
        raise NotImplementedError

    def get_qvel(self, physics) -> np.ndarray:
        raw = physics.data.qvel.copy()
        if self.arm_nums == 2:
            l, r = raw[:8], raw[8:16]
            return np.concatenate(
                [l[:6], [puppet_gripper_vel_normalize(l[6])],
                 r[:6], [puppet_gripper_vel_normalize(r[6])]]
            )
        elif self.arm_nums == 1:
            r = raw[:8]
            return np.concatenate([r[:6], [puppet_gripper_vel_normalize(r[6])]])
        raise NotImplementedError

    @staticmethod
    def get_env_state(physics) -> np.ndarray:
        raise NotImplementedError

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
        if self.arm_nums == 2:
            obs["mocap_pose_left"] = np.concatenate(
                [physics.data.mocap_pos[0], physics.data.mocap_quat[0]]
            ).copy()
            obs["mocap_pose_right"] = np.concatenate(
                [physics.data.mocap_pos[1], physics.data.mocap_quat[1]]
            ).copy()
        elif self.arm_nums == 1:
            obs["mocap_pose_right"] = np.concatenate(
                [physics.data.mocap_pos[0], physics.data.mocap_quat[0]]
            ).copy()
        obs["gripper_ctrl"] = physics.data.ctrl.copy()
        return obs

    def get_reward(self, physics) -> float:
        raise NotImplementedError


# ─── Concrete EE task classes ─────────────────────────────────────────────────

class TransferCubeEETask(BimanualViperXEETask):
    def __init__(self, random=None):
        super().__init__(random=random, arm_nums=2)
        self.max_reward = 4

    def initialize_episode(self, physics):
        self.initialize_robots(physics)
        cube_pose = sample_box_pose()
        jid = physics.model.name2id("red_box_joint", "joint")
        np.copyto(physics.data.qpos[jid : jid + 7], cube_pose)
        super().initialize_episode(physics)

    @staticmethod
    def get_env_state(physics):
        return physics.data.qpos.copy()[16:]

    def get_reward(self, physics):
        pairs = _contact_pairs(physics)
        tl = ("red_box", "vx300s_left/10_left_gripper_finger") in pairs
        tr = ("red_box", "vx300s_right/10_right_gripper_finger") in pairs
        tt = ("red_box", "table") in pairs
        r = 0
        if tr: r = 1
        if tr and not tt: r = 2
        if tl: r = 3
        if tl and not tt: r = 4
        return r


class InsertionEETask(BimanualViperXEETask):
    def __init__(self, random=None):
        super().__init__(random=random, arm_nums=2)
        self.max_reward = 4

    def initialize_episode(self, physics):
        self.initialize_robots(physics)
        peg_pose, socket_pose = sample_insertion_pose()
        id2index = lambda j_id: 16 + (j_id - 16) * 7
        peg_id = physics.model.name2id("red_peg_joint", "joint")
        np.copyto(physics.data.qpos[id2index(peg_id) : id2index(peg_id) + 7], peg_pose)
        sock_id = physics.model.name2id("blue_socket_joint", "joint")
        np.copyto(physics.data.qpos[id2index(sock_id) : id2index(sock_id) + 7], socket_pose)
        super().initialize_episode(physics)

    @staticmethod
    def get_env_state(physics):
        return physics.data.qpos.copy()[16:]

    def get_reward(self, physics):
        pairs = _contact_pairs(physics)
        tr = ("red_peg", "vx300s_right/10_right_gripper_finger") in pairs
        tl = any(
            (f"socket-{i}", "vx300s_left/10_left_gripper_finger") in pairs for i in range(1, 5)
        )
        pt = ("red_peg", "table") in pairs
        st = any(("socket-" + str(i), "table") in pairs for i in range(1, 5))
        ps = any(("red_peg", f"socket-{i}") in pairs for i in range(1, 5))
        pin = ("red_peg", "pin") in pairs
        r = 0
        if tl and tr: r = 1
        if tl and tr and not pt and not st: r = 2
        if ps and not pt and not st: r = 3
        if pin: r = 4
        return r


class LiftingCubeEETask(BimanualViperXEETask):
    def __init__(self, random=None, arm_nums: int = 1, equipment_model: str = "vx300s_single"):
        super().__init__(random=random, arm_nums=arm_nums, equipment_model=equipment_model)
        self.max_reward = 4

    def initialize_episode(self, physics):
        self.initialize_robots(physics)
        cube_pose = sample_box_pose()
        jid = physics.model.name2id("red_box_joint", "joint")
        np.copyto(physics.data.qpos[jid : jid + 7], cube_pose)
        super().initialize_episode(physics)

    @staticmethod
    def get_env_state(physics):
        return physics.data.qpos.copy()[8:]

    def get_reward(self, physics):
        pairs = _contact_pairs(physics)
        tr = ("red_box", "vx300s_right/10_right_gripper_finger") in pairs
        tt = ("red_box", "table") in pairs or ("table", "red_box") in pairs
        ty = ("red_box", "yellow_tray") in pairs or ("yellow_tray", "red_box") in pairs
        r = 0
        if tr: r = 1
        if tr and not tt: r = 2
        if tr and ty: r = 3
        if not tr and ty: r = 4
        return r
