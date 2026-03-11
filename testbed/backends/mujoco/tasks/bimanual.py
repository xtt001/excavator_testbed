"""
Bimanual ViperX tasks: TransferCube and Insertion.
"""

from __future__ import annotations

import collections

import numpy as np
from dm_control.suite import base

from testbed.backends.mujoco.tasks.constants import (
    PUPPET_GRIPPER_POSITION_CLOSE,
    START_ARM_POSE,
    puppet_gripper_pos_normalize,
    puppet_gripper_pos_unnormalize,
    puppet_gripper_vel_normalize,
)


# Global mutable pose slot — set before env.reset() via MuJoCoBackend
BOX_POSE: list = [None]


class BimanualViperXTask(base.Task):
    """Base task for bi-manual (or single-arm) ViperX robots."""

    def __init__(self, random=None, arm_nums: int = 2):
        super().__init__(random=random)
        self.arm_nums = arm_nums

    def before_step(self, action, physics):
        if self.arm_nums == 2:
            left_arm_action = action[:6]
            right_arm_action = action[7 : 7 + 6]
            left_grip = puppet_gripper_pos_unnormalize(action[6])
            right_grip = puppet_gripper_pos_unnormalize(action[7 + 6])
            env_action = np.concatenate(
                [left_arm_action, [left_grip, -left_grip], right_arm_action, [right_grip, -right_grip]]
            )
            super().before_step(env_action, physics)
        elif self.arm_nums == 1:
            right_arm_action = action[:6]
            right_grip = puppet_gripper_pos_unnormalize(action[6])
            env_action = np.concatenate([right_arm_action, [right_grip, -right_grip]])
            super().before_step(env_action, physics)

    def initialize_episode(self, physics):
        super().initialize_episode(physics)

    def get_qpos(self, physics):
        raw = physics.data.qpos.copy()
        if self.arm_nums == 2:
            left = raw[:8]
            right = raw[8:16]
            return np.concatenate(
                [left[:6], [puppet_gripper_pos_normalize(left[6])],
                 right[:6], [puppet_gripper_pos_normalize(right[6])]]
            )
        elif self.arm_nums == 1:
            right = raw[:8]
            return np.concatenate([right[:6], [puppet_gripper_pos_normalize(right[6])]])
        raise NotImplementedError

    def get_qvel(self, physics):
        raw = physics.data.qvel.copy()
        if self.arm_nums == 2:
            left = raw[:8]
            right = raw[8:16]
            return np.concatenate(
                [left[:6], [puppet_gripper_vel_normalize(left[6])],
                 right[:6], [puppet_gripper_vel_normalize(right[6])]]
            )
        elif self.arm_nums == 1:
            right = raw[:8]
            return np.concatenate([right[:6], [puppet_gripper_vel_normalize(right[6])]])
        raise NotImplementedError

    @staticmethod
    def get_env_state(physics):
        raise NotImplementedError

    def get_observation(self, physics):
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

    def get_reward(self, physics):
        raise NotImplementedError


# ─── Transfer Cube ────────────────────────────────────────────────────────────

class TransferCubeTask(BimanualViperXTask):
    def __init__(self, random=None):
        super().__init__(random=random, arm_nums=2)
        self.max_reward = 4

    def initialize_episode(self, physics):
        with physics.reset_context():
            physics.named.data.qpos[:16] = START_ARM_POSE
            np.copyto(physics.data.ctrl, START_ARM_POSE)
            assert BOX_POSE[0] is not None
            physics.named.data.qpos[-7:] = BOX_POSE[0]
        super().initialize_episode(physics)

    @staticmethod
    def get_env_state(physics):
        return physics.data.qpos.copy()[16:]

    def get_reward(self, physics):
        pairs = _contact_pairs(physics)
        touch_left = ("red_box", "vx300s_left/10_left_gripper_finger") in pairs
        touch_right = ("red_box", "vx300s_right/10_right_gripper_finger") in pairs
        touch_table = ("red_box", "table") in pairs
        r = 0
        if touch_right:
            r = 1
        if touch_right and not touch_table:
            r = 2
        if touch_left:
            r = 3
        if touch_left and not touch_table:
            r = 4
        return r


# ─── Insertion ────────────────────────────────────────────────────────────────

class InsertionTask(BimanualViperXTask):
    def __init__(self, random=None):
        super().__init__(random=random, arm_nums=2)
        self.max_reward = 4

    def initialize_episode(self, physics):
        with physics.reset_context():
            physics.named.data.qpos[:16] = START_ARM_POSE
            np.copyto(physics.data.ctrl, START_ARM_POSE)
            assert BOX_POSE[0] is not None
            physics.named.data.qpos[-7 * 2 :] = BOX_POSE[0]
        super().initialize_episode(physics)

    @staticmethod
    def get_env_state(physics):
        return physics.data.qpos.copy()[16:]

    def get_reward(self, physics):
        pairs = _contact_pairs(physics)
        touch_right = ("red_peg", "vx300s_right/10_right_gripper_finger") in pairs
        touch_left = any(
            (f"socket-{i}", "vx300s_left/10_left_gripper_finger") in pairs for i in range(1, 5)
        )
        peg_table = ("red_peg", "table") in pairs
        socket_table = any(("socket-" + str(i), "table") in pairs for i in range(1, 5))
        peg_socket = any(("red_peg", f"socket-{i}") in pairs for i in range(1, 5))
        pin_touched = ("red_peg", "pin") in pairs

        r = 0
        if touch_left and touch_right:
            r = 1
        if touch_left and touch_right and not peg_table and not socket_table:
            r = 2
        if peg_socket and not peg_table and not socket_table:
            r = 3
        if pin_touched:
            r = 4
        return r


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _contact_pairs(physics) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for i in range(physics.data.ncon):
        g1 = physics.model.id2name(physics.data.contact[i].geom1, "geom")
        g2 = physics.model.id2name(physics.data.contact[i].geom2, "geom")
        pairs.add((g1, g2))
        pairs.add((g2, g1))
    return pairs
