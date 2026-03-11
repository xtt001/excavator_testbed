"""
Shared constants and helper utilities for MuJoCo tasks.

These replace the flat constants.py in legacy/. Values are kept identical
so that existing MJCF assets and HDF5 data remain compatible.
"""

from __future__ import annotations

import numpy as np

# ─── Time ─────────────────────────────────────────────────────────────────────
DT: float = 0.02  # 50 Hz control

# ─── vx300s bimanual / single ─────────────────────────────────────────────────
JOINT_NAMES = ["waist", "shoulder", "elbow", "forearm_roll", "wrist_angle", "wrist_rotate"]

START_ARM_POSE = [
    0, -0.96, 1.16, 0, -0.3, 0, 0.02239, -0.02239,   # left arm + gripper
    0, -0.96, 1.16, 0, -0.3, 0, 0.02239, -0.02239,   # right arm + gripper
]
START_SINGLE_ARM_POSE = [0, -0.96, 1.16, 0, -0.3, 0, 0.02239, -0.02239]

# ─── Fairino FR5 ──────────────────────────────────────────────────────────────
START_FAIRINO_POSE = [0, -1.5708, 1.5708, -1.5708, -1.5708, 0, 0.057, -0.057]

# ─── Excavator ────────────────────────────────────────────────────────────────
EXCAVATOR_MAIN_JOINTS = ("j1_swing", "j2_boom", "j3_stick", "j4_bucket")
EXCAVATOR_START_POSE = np.array([0.0, -0.25, -0.5, -0.5])

# ─── Gripper limits ───────────────────────────────────────────────────────────
MASTER_GRIPPER_POSITION_OPEN = 0.02417
MASTER_GRIPPER_POSITION_CLOSE = 0.01244
PUPPET_GRIPPER_POSITION_OPEN = 0.05800
PUPPET_GRIPPER_POSITION_CLOSE = 0.01844

MASTER_GRIPPER_JOINT_OPEN = 0.3083
MASTER_GRIPPER_JOINT_CLOSE = -0.6842
PUPPET_GRIPPER_JOINT_OPEN = 1.4910
PUPPET_GRIPPER_JOINT_CLOSE = -0.6213

# ─── Normalisation helpers ────────────────────────────────────────────────────

def puppet_gripper_pos_normalize(x: float) -> float:
    return (x - PUPPET_GRIPPER_POSITION_CLOSE) / (
        PUPPET_GRIPPER_POSITION_OPEN - PUPPET_GRIPPER_POSITION_CLOSE
    )


def puppet_gripper_pos_unnormalize(x: float) -> float:
    return x * (PUPPET_GRIPPER_POSITION_OPEN - PUPPET_GRIPPER_POSITION_CLOSE) + PUPPET_GRIPPER_POSITION_CLOSE


def puppet_gripper_vel_normalize(x: float) -> float:
    """Velocity normalization — mirrors legacy PUPPET_GRIPPER_VELOCITY_NORMALIZE_FN."""
    return x / (PUPPET_GRIPPER_POSITION_OPEN - PUPPET_GRIPPER_POSITION_CLOSE)


def master_gripper_pos_normalize(x: float) -> float:
    return (x - MASTER_GRIPPER_POSITION_CLOSE) / (
        MASTER_GRIPPER_POSITION_OPEN - MASTER_GRIPPER_POSITION_CLOSE
    )


def master_gripper_pos_unnormalize(x: float) -> float:
    return x * (MASTER_GRIPPER_POSITION_OPEN - MASTER_GRIPPER_POSITION_CLOSE) + MASTER_GRIPPER_POSITION_CLOSE


def master2puppet_position(x: float) -> float:
    return puppet_gripper_pos_unnormalize(master_gripper_pos_normalize(x))
