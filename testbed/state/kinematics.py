"""
MuJoCo site-based forward kinematics (Option A: minimal, working).

All FK is resolved via named *sites* defined in the MJCF XML files.
This keeps the kinematics layer thin — no symbolic Jacobians needed for Step0.

Public API
----------
get_site_pose(physics, site_name) → (pos, mat)
get_ee_pose(physics, robot)       → (pos, mat)   convenience wrapper
"""

from __future__ import annotations

import numpy as np

# ─── Site names registry ──────────────────────────────────────────────────────

# Map robot variant name → EE site defined in its MJCF
_ROBOT_EE_SITE: dict[str, str] = {
    "vx300s_right":        "right/gripper_control",
    "vx300s_left":         "left/gripper_control",
    "vx300s_single":       "right/gripper_control",
    "fairino5_single":     "tcp_center",
    "fairino5_right":      "tcp_center",
    "excavator_simple":    "bucket_tip",
}

# Excavator bucket tip (MJCF site)
BUCKET_TIP_SITE = "bucket_tip"

# Gripper control points for vx300s
RIGHT_GRIPPER_SITE = "right/gripper_control"
LEFT_GRIPPER_SITE  = "left/gripper_control"


# ─── Core FK ─────────────────────────────────────────────────────────────────

def get_site_pose(physics, site_name: str) -> tuple[np.ndarray, np.ndarray]:
    """
    Return position and rotation matrix of a named site.

    Parameters
    ----------
    physics    dm_control Physics object (env.physics or env._physics).
    site_name  Name of the site as declared in the MJCF file.

    Returns
    -------
    pos : (3,)   XYZ position in world frame.
    mat : (3, 3) Rotation matrix in world frame.
    """
    pos = physics.named.data.site_xpos[site_name].copy()          # (3,)
    mat = physics.named.data.site_xmat[site_name].copy().reshape(3, 3)  # (3, 3)
    return pos, mat


def get_site_pos(physics, site_name: str) -> np.ndarray:
    """Return only the position of a named site. Convenience shortcut."""
    return physics.named.data.site_xpos[site_name].copy()


def get_ee_pose(physics, robot: str) -> tuple[np.ndarray, np.ndarray]:
    """
    Return EE pose for a named robot variant.

    Parameters
    ----------
    physics  dm_control Physics object.
    robot    Robot variant key (see _ROBOT_EE_SITE).

    Returns
    -------
    pos : (3,)   XYZ position.
    mat : (3, 3) Rotation matrix.

    Raises
    ------
    KeyError  if `robot` is not registered.
    """
    site = _ROBOT_EE_SITE[robot]
    return get_site_pose(physics, site)


# ─── Multi-arm helper ─────────────────────────────────────────────────────────

def get_both_ee_poses(
    physics,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """
    Return poses for both arms of a bimanual setup.

    Returns
    -------
    {"right": (pos, mat), "left": (pos, mat)}
    """
    return {
        "right": get_site_pose(physics, RIGHT_GRIPPER_SITE),
        "left":  get_site_pose(physics, LEFT_GRIPPER_SITE),
    }


# ─── Jacobian stub (Step1+) ───────────────────────────────────────────────────

def get_site_jacobian(
    physics, site_name: str
) -> tuple[np.ndarray, np.ndarray]:
    """
    Return translational and rotational Jacobians for a named site.

    Wraps MuJoCo's mj_jacSite. Returns:
      jacp : (3, nv)   translational Jacobian
      jacr : (3, nv)   rotational Jacobian

    NOTE: This is provided for future use (IK, impedance control).
          Step0 policies do not call it.
    """
    nv = physics.model.nv
    jacp = np.zeros((3, nv))
    jacr = np.zeros((3, nv))
    site_id = physics.model.name2id(site_name, "site")
    physics.model.mj_jacSite(physics.data, jacp, jacr, site_id)  # type: ignore[attr-defined]
    return jacp, jacr
