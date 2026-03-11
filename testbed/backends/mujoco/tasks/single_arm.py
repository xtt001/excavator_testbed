"""
Single-arm tasks: LiftingCube for vx300s_single and fairino5_single.
"""

from __future__ import annotations

import collections

import numpy as np
from dm_control.suite import base

from testbed.backends.mujoco.tasks.bimanual import BimanualViperXTask, BOX_POSE, _contact_pairs
from testbed.backends.mujoco.tasks.constants import (
    START_FAIRINO_POSE,
    START_SINGLE_ARM_POSE,
)


class LiftingCubeTask(BimanualViperXTask):
    """Single-arm cube lifting task for vx300s_single / fairino5_single."""

    def __init__(self, random=None, equipment_model: str = "vx300s_single"):
        super().__init__(random=random, arm_nums=1)
        self.max_reward = 4
        self.equipment_model = equipment_model

    def initialize_episode(self, physics):
        if "fairino5_single" in self.equipment_model:
            start_pose = START_FAIRINO_POSE
        elif "vx300s_single" in self.equipment_model:
            start_pose = START_SINGLE_ARM_POSE
        else:
            raise ValueError(f"Unknown equipment_model: {self.equipment_model}")

        with physics.reset_context():
            physics.named.data.qpos[:8] = start_pose
            np.copyto(physics.data.ctrl, start_pose)
            assert BOX_POSE[0] is not None
            physics.named.data.qpos[-7:] = BOX_POSE[0]
        physics.forward()
        super(BimanualViperXTask, self).initialize_episode(physics)

    @staticmethod
    def get_env_state(physics):
        return physics.data.qpos.copy()[8:]

    def get_reward(self, physics):
        pairs = _contact_pairs(physics)
        touch_right = ("red_box", "vx300s_right/10_right_gripper_finger") in pairs
        touch_table = ("red_box", "table") in pairs or ("table", "red_box") in pairs
        touch_tray = ("red_box", "yellow_tray") in pairs or ("yellow_tray", "red_box") in pairs

        r = 0
        if touch_right:
            r = 1
        if touch_right and not touch_table:
            r = 2
        if touch_right and touch_tray:
            r = 3
        if not touch_right and touch_tray:
            r = 4
        return r
