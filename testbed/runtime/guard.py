"""
Safety guard stub (Step1+).

The guard's job is to intercept actions before they are sent to the
environment and:
  • Clip joint velocities to safe limits.
  • Halt if a collision is predicted or a joint limit is about to be exceeded.
  • Log guard trigger events so the evaluator can report `guard_trigger_rate`.

This file is intentionally left as a no-op stub for Step0.
Replace the body of ActionGuard.check() with real logic when needed.
"""

from __future__ import annotations

import numpy as np


class ActionGuard:
    """
    Intercepts actions before env.step().

    Parameters
    ----------
    joint_limits    (2, N) array — [[lower], [upper]] joint position limits.
    vel_limit       Maximum absolute joint velocity (rad/s).
    """

    def __init__(
        self,
        joint_limits: np.ndarray | None = None,
        vel_limit: float = float("inf"),
    ):
        self.joint_limits  = joint_limits
        self.vel_limit     = vel_limit
        self.trigger_count = 0

    def check(
        self,
        action: np.ndarray,
        current_qpos: np.ndarray | None = None,
    ) -> tuple[np.ndarray, bool]:
        """
        Validate and (optionally) clip an action.

        Parameters
        ----------
        action       Raw action from policy.
        current_qpos Current joint positions (for velocity limiting).

        Returns
        -------
        (safe_action, triggered)
          safe_action : (possibly clipped) action array.
          triggered   : True if any guard rule fired.
        """
        # ── STUB: pass-through ────────────────────────────────────────────
        # TODO(Step1): implement joint limit clipping, velocity saturation,
        #              and collision pre-checks.
        return action.copy(), False

    @property
    def trigger_rate(self) -> float:
        """Guard trigger rate (requires caller to track total steps)."""
        return 0.0  # stub
