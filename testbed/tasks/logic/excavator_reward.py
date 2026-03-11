"""
Pure excavator phase-reward logic — no physics, no dm_control imports.

This module tracks the multi-stage excavation cycle and returns the
appropriate scalar reward. It is intentionally backend-agnostic so it
can be reused by:
  - MuJoCo task classes (called from get_reward)
  - Evaluator overlays (phase annotation without re-running physics)
  - Future Isaac / AGX backends

Reward table
------------
| Value | Condition                                     | Phase label     |
|-------|-----------------------------------------------|-----------------|
|  0.0  | default                                       | idle            |
|  1.0  | bucket touches target                         | contact         |
|  1.2  | touched but not yet loaded (anti-push reward) | contact_only    |
|  2.0  | loaded and box_z > LOAD_HEIGHT_THRESHOLD      | loaded          |
|  2.8  | loaded + |swing| > DUMP_SWING_THRESHOLD      | swinging        |
|  3.0  | in dump zone + bucket touches tray            | dump_approach   |
|  4.0  | box on tray, bucket clear, box_z < DUMP_Z_MAX | dump_complete   |
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# ─── Thresholds ───────────────────────────────────────────────────────────────

LOAD_HEIGHT_THRESHOLD: float = 0.285   # m — box must be above this to count as loaded
DUMP_SWING_THRESHOLD: float = 1.0      # rad — |swing| must exceed this for dump zone
DUMP_Z_MAX: float = 0.35               # m — box must be below this after dump

# Geom names (must match MJCF)
BUCKET_GEOM = "excavator_bucket"
BOX_GEOM = "red_box"
TRAY_GEOM = "yellow_dump_tray"


# ─── Phase label (for overlays) ───────────────────────────────────────────────

PHASE_LABELS: dict[float, str] = {
    0.0: "idle",
    1.0: "contact",
    1.2: "contact_only",
    2.0: "loaded",
    2.8: "swinging",
    3.0: "dump_approach",
    4.0: "dump_complete",
}


@dataclass
class ExcavatorPhaseTracker:
    """
    Stateful phase tracker for one episode.

    Call reset() at the start of each episode, then update() each timestep.
    """

    _touched_box: bool = field(default=False, init=False)
    _loaded_box: bool = field(default=False, init=False)
    _reached_dump_zone: bool = field(default=False, init=False)
    _dumped_box: bool = field(default=False, init=False)

    def reset(self) -> None:
        self._touched_box = False
        self._loaded_box = False
        self._reached_dump_zone = False
        self._dumped_box = False

    @property
    def current_phase(self) -> str:
        """Human-readable label of the highest phase reached so far."""
        if self._dumped_box:
            return "dump_complete"
        if self._reached_dump_zone:
            return "swinging"
        if self._loaded_box:
            return "loaded"
        if self._touched_box:
            return "contact"
        return "idle"

    def update(
        self,
        contact_pairs: set[tuple[str, str]],
        box_xyz: np.ndarray,
        swing_q: float,
    ) -> float:
        """
        Advance state machine and return current reward.

        Parameters
        ----------
        contact_pairs:
            Set of (geom_a, geom_b) contact tuples for this timestep.
            Must include both orderings, i.e. (a,b) and (b,a).
        box_xyz:
            World-frame position of the box [x, y, z].
        swing_q:
            Current j1_swing joint angle in radians.
        """
        box_z = float(box_xyz[2])

        touch_bucket_box = (BUCKET_GEOM, BOX_GEOM) in contact_pairs
        touch_box_tray = (BOX_GEOM, TRAY_GEOM) in contact_pairs
        touch_bucket_tray = (BUCKET_GEOM, TRAY_GEOM) in contact_pairs

        reward = 0.0

        # Stage 1: Contact
        if touch_bucket_box:
            self._touched_box = True
            reward = max(reward, 1.0)

        # Stage 2: Loaded (box lifted)
        if self._touched_box and box_z > LOAD_HEIGHT_THRESHOLD:
            self._loaded_box = True
            reward = max(reward, 2.0)

        # Stage 3: Swinging to dump zone
        if self._loaded_box and abs(swing_q) > DUMP_SWING_THRESHOLD:
            self._reached_dump_zone = True
            reward = max(reward, 2.8)

        # Stage 4: Dump approach (bucket at tray)
        if self._reached_dump_zone and touch_bucket_tray:
            reward = max(reward, 3.0)

        # Stage 5: Dump complete (box on tray, bucket clear)
        if (
            self._reached_dump_zone
            and touch_box_tray
            and not touch_bucket_box
            and box_z < DUMP_Z_MAX
        ):
            self._dumped_box = True
            reward = max(reward, 4.0)

        # Anti-push: touched but not yet loaded
        if self._touched_box and not self._loaded_box:
            reward = max(reward, 1.2)

        return reward

    def phase_label(self, reward: float) -> str:
        return PHASE_LABELS.get(reward, f"reward_{reward:.1f}")
