"""
Shared object-pose sampling utilities (backend-independent math).
"""

from __future__ import annotations

import numpy as np


def sample_box_pose() -> np.ndarray:
    """Random box pose for single-arm / bimanual tasks."""
    pos = np.random.uniform(
        low=[0.0, 0.4, 0.05],
        high=[0.2, 0.6, 0.05],
    )
    return np.concatenate([pos, [1, 0, 0, 0]])


def sample_box_pose_for_excavator() -> np.ndarray:
    """Random box pose in the excavator work area."""
    pos = np.random.uniform(
        low=[3.4, -1.0, 0.25],
        high=[4.4,  1.0, 0.25],
    )
    return np.concatenate([pos, [1, 0, 0, 0]])


def sample_insertion_pose() -> tuple[np.ndarray, np.ndarray]:
    """Random peg + socket poses for the insertion task."""
    peg_pos = np.random.uniform(low=[0.1, 0.4, 0.05], high=[0.2, 0.6, 0.05])
    socket_pos = np.random.uniform(low=[-0.2, 0.4, 0.05], high=[-0.1, 0.6, 0.05])
    quat = np.array([1, 0, 0, 0])
    return np.concatenate([peg_pos, quat]), np.concatenate([socket_pos, quat])
