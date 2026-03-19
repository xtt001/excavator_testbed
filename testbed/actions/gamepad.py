"""
JoystickActionSource — maps a gamepad to the AGX V0 action vector.

Action vector layout (V0, length 4):
    [swing_speed_cmd, boom_speed_cmd, stick_speed_cmd, bucket_speed_cmd]

All commands are normalized to [-1, 1] post-deadzone and post-scale.

Default axis mapping (Xbox / generic dual-stick layout):
    axis 0  → swing    (left stick X)
    axis 1  → boom     (left stick Y, inverted)
    axis 3  → stick    (right stick X)
    axis 4  → bucket   (right stick Y, inverted)

Override via the `axis_map` and `invert` config keys.
All tunable values live in teleop_v0.yaml — nothing is hardcoded here.

Requires: pygame (pip install pygame)
"""

from __future__ import annotations

import logging
import time
from typing import Sequence

import numpy as np

from testbed.actions.base import ActionInfo, ActionSource

log = logging.getLogger(__name__)

# V0 action indices (locked — must match protocol.py ACTION_DIM ordering)
IDX_SWING  = 0
IDX_BOOM   = 1
IDX_STICK  = 2
IDX_BUCKET = 3
ACTION_DIM = 4


class JoystickActionSource(ActionSource):
    """
    Reads a gamepad via pygame and produces AGX V0 speed commands.

    Parameters
    ----------
    joystick_id  pygame joystick index (0 = first connected gamepad).
    axis_map     List of 4 pygame axis indices mapped to
                 [swing, boom, stick, bucket] in that order.
    invert       List of 4 booleans; True = negate that axis.
    deadzone     Per-axis deadzone threshold (applied before scale).
                 Scalar applies to all axes; list overrides per-axis.
    scale        Per-axis scale applied after deadzone.
                 Scalar or list of 4.
    clip         Hard clip limit applied last (default 1.0).
    """

    def __init__(
        self,
        joystick_id: int = 0,
        axis_map:    Sequence[int]  = (0, 1, 3, 4),
        invert:      Sequence[bool] = (False, True, False, True),
        deadzone:    float | Sequence[float] = 0.05,
        scale:       float | Sequence[float] = 1.0,
        clip:        float = 1.0,
    ) -> None:
        import pygame  # lazy import — only needed when joystick is used

        self._pygame = pygame
        self.joystick_id = joystick_id
        self.axis_map    = list(axis_map)
        self.invert      = list(invert)

        # Broadcast scalar → per-axis list
        if isinstance(deadzone, (int, float)):
            self._deadzone = [float(deadzone)] * ACTION_DIM
        else:
            self._deadzone = [float(d) for d in deadzone]

        if isinstance(scale, (int, float)):
            self._scale = [float(scale)] * ACTION_DIM
        else:
            self._scale = [float(s) for s in scale]

        self._clip = float(clip)
        self._joystick = None

        self._init_pygame()

    # ── ActionSource interface ────────────────────────────────────────────────

    def reset(self) -> None:
        """Re-pump the event queue; no state to reset for a joystick."""
        self._pygame.event.pump()

    def next_action(self, obs: dict) -> tuple[np.ndarray, ActionInfo]:
        """Read gamepad axes and return a (4,) action vector."""
        self._pygame.event.pump()
        action = np.zeros(ACTION_DIM, dtype=np.float32)

        if self._joystick is None:
            log.warning("No joystick initialised — returning zeros.")
            return action, ActionInfo(source_type="teleop", source_id="joystick_missing")

        t0 = time.perf_counter()
        for out_idx, axis_idx in enumerate(self.axis_map):
            raw = float(self._joystick.get_axis(axis_idx))
            if self.invert[out_idx]:
                raw = -raw
            # deadzone
            dz = self._deadzone[out_idx]
            if abs(raw) < dz:
                raw = 0.0
            else:
                # rescale so output reaches ±1 at full deflection
                raw = (raw - dz * np.sign(raw)) / (1.0 - dz)
            # scale + clip
            raw = np.clip(raw * self._scale[out_idx], -self._clip, self._clip)
            action[out_idx] = raw

        latency_ms = (time.perf_counter() - t0) * 1000.0
        info = ActionInfo(
            source_type="teleop",
            source_id=f"joystick:{self.joystick_id}",
            latency_ms=latency_ms,
        )
        return action, info

    def close(self) -> None:
        """Quit pygame joystick subsystem."""
        try:
            if self._joystick is not None:
                self._joystick.quit()
            self._pygame.joystick.quit()
        except Exception:
            pass

    # ── Init helpers ──────────────────────────────────────────────────────────

    def _init_pygame(self) -> None:
        pg = self._pygame
        if not pg.get_init():
            pg.init()
        if not pg.joystick.get_init():
            pg.joystick.init()

        n = pg.joystick.get_count()
        if n == 0:
            log.error(
                "No joystick/gamepad detected by pygame. "
                "Connect a gamepad and retry."
            )
            return

        if self.joystick_id >= n:
            log.warning(
                "Requested joystick_id=%d but only %d found. Using 0.",
                self.joystick_id, n,
            )
            self.joystick_id = 0

        self._joystick = pg.joystick.Joystick(self.joystick_id)
        self._joystick.init()
        log.info(
            "Joystick ready: [%d] %s  axes=%d",
            self.joystick_id,
            self._joystick.get_name(),
            self._joystick.get_numaxes(),
        )

    @classmethod
    def from_config(cls, cfg: dict) -> "JoystickActionSource":
        """Construct from a flat config dict (e.g. loaded from teleop_v0.yaml)."""
        return cls(
            joystick_id=cfg.get("joystick_id", 0),
            axis_map=cfg.get("axis_map", [0, 1, 3, 4]),
            invert=cfg.get("invert", [False, True, False, True]),
            deadzone=cfg.get("deadzone", 0.05),
            scale=cfg.get("scale", 1.0),
            clip=cfg.get("clip", 1.0),
        )
