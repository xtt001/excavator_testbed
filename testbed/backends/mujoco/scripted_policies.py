"""
Scripted demo policies for data collection.

These are NOT learnable policies — they are hard-coded waypoint trajectories
used only to generate HDF5 demonstration data. They live in the backend layer
because they are tightly coupled to EE-space environment observations.

Policy → Testbed role mapping:
  PickAndTransferPolicy         sim_transfer_cube    vx300s_bimanual
  InsertionPolicy               sim_insertion        vx300s_bimanual
  LiftingAndMovingPolicy        sim_lifting_cube     vx300s/fairino
  ExcavatorJointSpaceDigDumpPolicy  sim_lifting_cube excavator_simple
"""

from __future__ import annotations

import numpy as np
from pyquaternion import Quaternion

# ─── Base ─────────────────────────────────────────────────────────────────────

class BasePolicy:
    def __init__(self, inject_noise: bool = False):
        self.inject_noise = inject_noise
        self.step_count = 0
        self.left_trajectory: list | None = None
        self.right_trajectory: list | None = None
        self.curr_left_waypoint = None
        self.curr_right_waypoint = None

    def generate_trajectory(self, ts_first):
        raise NotImplementedError

    @staticmethod
    def interpolate(curr, next_wp, t):
        frac = (t - curr["t"]) / (next_wp["t"] - curr["t"])
        xyz = curr["xyz"] + (next_wp["xyz"] - curr["xyz"]) * frac
        quat = curr["quat"] + (next_wp["quat"] - curr["quat"]) * frac
        grip = curr["gripper"] + (next_wp["gripper"] - curr["gripper"]) * frac
        return xyz, quat, grip

    def __call__(self, ts):
        if self.step_count == 0:
            self.generate_trajectory(ts)

        if self.left_trajectory is not None:
            if self.left_trajectory[0]["t"] == self.step_count:
                self.curr_left_waypoint = self.left_trajectory.pop(0)
            lx, lq, lg = self.interpolate(
                self.curr_left_waypoint, self.left_trajectory[0], self.step_count
            )

        if self.right_trajectory is not None:
            if self.right_trajectory[0]["t"] == self.step_count:
                self.curr_right_waypoint = self.right_trajectory.pop(0)
            rx, rq, rg = self.interpolate(
                self.curr_right_waypoint, self.right_trajectory[0], self.step_count
            )

        if self.inject_noise:
            scale = 0.01
            if self.left_trajectory is not None:
                lx = lx + np.random.uniform(-scale, scale, lx.shape)
            if self.right_trajectory is not None:
                rx = rx + np.random.uniform(-scale, scale, rx.shape)

        self.step_count += 1
        if self.left_trajectory is not None:
            return np.concatenate([lx, lq, [lg], rx, rq, [rg]])
        return np.concatenate([rx, rq, [rg]])


# ─── Transfer Cube ────────────────────────────────────────────────────────────

class PickAndTransferPolicy(BasePolicy):
    def generate_trajectory(self, ts_first):
        init_right = ts_first.observation["mocap_pose_right"]
        init_left = ts_first.observation["mocap_pose_left"]
        box_xyz = np.array(ts_first.observation["env_state"][:3])

        gpq = Quaternion(init_right[3:]) * Quaternion(axis=[0, 1, 0], degrees=-60)
        meet_lq = Quaternion(axis=[1, 0, 0], degrees=90)
        meet = np.array([0, 0.5, 0.25])

        self.left_trajectory = [
            {"t": 0,   "xyz": init_left[:3],                       "quat": init_left[3:],    "gripper": 0},
            {"t": 100, "xyz": meet + [-0.1, 0, -0.02],             "quat": meet_lq.elements, "gripper": 1},
            {"t": 260, "xyz": meet + [0.02, 0, -0.02],             "quat": meet_lq.elements, "gripper": 1},
            {"t": 310, "xyz": meet + [0.02, 0, -0.02],             "quat": meet_lq.elements, "gripper": 0},
            {"t": 360, "xyz": meet + [-0.1, 0, -0.02],             "quat": np.array([1, 0, 0, 0]), "gripper": 0},
            {"t": 400, "xyz": meet + [-0.1, 0, -0.02],             "quat": np.array([1, 0, 0, 0]), "gripper": 0},
        ]
        self.right_trajectory = [
            {"t": 0,   "xyz": init_right[:3],                      "quat": init_right[3:],   "gripper": 0},
            {"t": 90,  "xyz": box_xyz + [0, 0, 0.08],              "quat": gpq.elements,     "gripper": 1},
            {"t": 130, "xyz": box_xyz + [0, 0, -0.015],            "quat": gpq.elements,     "gripper": 1},
            {"t": 170, "xyz": box_xyz + [0, 0, -0.015],            "quat": gpq.elements,     "gripper": 0},
            {"t": 200, "xyz": meet + [0.05, 0, 0],                 "quat": gpq.elements,     "gripper": 0},
            {"t": 220, "xyz": meet,                                 "quat": gpq.elements,     "gripper": 0},
            {"t": 310, "xyz": meet,                                 "quat": gpq.elements,     "gripper": 1},
            {"t": 360, "xyz": meet + [0.1, 0, 0],                  "quat": gpq.elements,     "gripper": 1},
            {"t": 400, "xyz": meet + [0.1, 0, 0],                  "quat": gpq.elements,     "gripper": 1},
        ]


# ─── Insertion ────────────────────────────────────────────────────────────────

class InsertionPolicy(BasePolicy):
    def generate_trajectory(self, ts_first):
        ir = ts_first.observation["mocap_pose_right"]
        il = ts_first.observation["mocap_pose_left"]
        env = np.array(ts_first.observation["env_state"])
        peg_xyz, sock_xyz = env[:3], env[7:10]

        grq = Quaternion(ir[3:]) * Quaternion(axis=[0, 1, 0], degrees=-60)
        glq = Quaternion(ir[3:]) * Quaternion(axis=[0, 1, 0], degrees=60)
        meet = np.array([0, 0.5, 0.15])
        lift = 0.00715

        self.left_trajectory = [
            {"t": 0,   "xyz": il[:3],                    "quat": il[3:],      "gripper": 0},
            {"t": 120, "xyz": sock_xyz + [0, 0, 0.08],   "quat": glq.elements,"gripper": 1},
            {"t": 170, "xyz": sock_xyz + [0, 0, -0.03],  "quat": glq.elements,"gripper": 1},
            {"t": 220, "xyz": sock_xyz + [0, 0, -0.03],  "quat": glq.elements,"gripper": 0},
            {"t": 285, "xyz": meet + [-0.1, 0, 0],       "quat": glq.elements,"gripper": 0},
            {"t": 340, "xyz": meet + [-0.05, 0, 0],      "quat": glq.elements,"gripper": 0},
            {"t": 400, "xyz": meet + [-0.05, 0, 0],      "quat": glq.elements,"gripper": 0},
        ]
        self.right_trajectory = [
            {"t": 0,   "xyz": ir[:3],                    "quat": ir[3:],      "gripper": 0},
            {"t": 120, "xyz": peg_xyz + [0, 0, 0.08],   "quat": grq.elements,"gripper": 1},
            {"t": 170, "xyz": peg_xyz + [0, 0, -0.03],  "quat": grq.elements,"gripper": 1},
            {"t": 220, "xyz": peg_xyz + [0, 0, -0.03],  "quat": grq.elements,"gripper": 0},
            {"t": 285, "xyz": meet + [0.1, 0, lift],    "quat": grq.elements,"gripper": 0},
            {"t": 340, "xyz": meet + [0.05, 0, lift],   "quat": grq.elements,"gripper": 0},
            {"t": 400, "xyz": meet + [0.05, 0, lift],   "quat": grq.elements,"gripper": 0},
        ]


# ─── Lifting & Moving (single arm) ───────────────────────────────────────────

class LiftingAndMovingPolicy(BasePolicy):
    def generate_trajectory(self, ts_first):
        ir = ts_first.observation["mocap_pose_right"]
        box_xyz = np.array(ts_first.observation["env_state"][:3])

        gpq = Quaternion(ir[3:]) * Quaternion(axis=[1, 0, 0], degrees=-30)
        tray = np.array([0.4, 0.85, 0.06])

        self.right_trajectory = [
            {"t": 0,   "xyz": ir[:3],                   "quat": ir[3:],     "gripper": 0},
            {"t": 50,  "xyz": box_xyz + [0, 0, 0.08],   "quat": gpq.elements,"gripper": 1},
            {"t": 70,  "xyz": box_xyz + [0, 0, -0.015], "quat": gpq.elements,"gripper": 1},
            {"t": 100, "xyz": box_xyz + [0, 0, -0.015], "quat": gpq.elements,"gripper": 0},
            {"t": 140, "xyz": box_xyz + [0, 0, 0.10],   "quat": gpq.elements,"gripper": 0},
            {"t": 300, "xyz": tray + [0, 0, 0.06],      "quat": gpq.elements,"gripper": 0},
            {"t": 320, "xyz": tray + [0, 0, 0.03],      "quat": gpq.elements,"gripper": 0},
            {"t": 350, "xyz": tray + [0, 0, 0.03],      "quat": gpq.elements,"gripper": 1},
            {"t": 370, "xyz": tray + [0, 0, 0.06],      "quat": gpq.elements,"gripper": 1},
            {"t": 400, "xyz": ir[:3],                   "quat": ir[3:],     "gripper": 1},
        ]


# ─── Excavator joint-space (direct sim) ──────────────────────────────────────

class ExcavatorJointSpaceDigDumpPolicy:
    """
    Direct joint-space excavation policy with distance-adaptive waypoints.
    Semi-closed-loop: advances past the hold phase once box_z > threshold.
    """

    _R_NEAR, _R_FAR = 3.4, 4.6
    _LOAD_NEAR   = np.array([ 0.05,  0.10, -0.95])
    _LOAD_FAR    = np.array([-0.23,  0.48, -0.80])
    _SECURE_NEAR = np.array([-0.05, -0.05, -0.55])
    _SECURE_FAR  = np.array([-0.30,  0.32, -0.40])
    _LIFT_NEAR   = np.array([ 0.08, -0.05, -1.20])
    _LIFT_FAR    = np.array([-0.18,  0.28, -1.05])
    _CARRY_NEAR  = np.array([ 0.05,  0.00, -1.30])
    _CARRY_FAR   = np.array([-0.20,  0.36, -1.18])

    def __init__(self, inject_noise: bool = False):
        self.inject_noise = inject_noise
        self.step_count = 0
        self.waypoints: list | None = None
        self.curr_waypoint = None
        self._phase = "init"

    @staticmethod
    def _interp(curr, nxt, t):
        frac = (t - curr["t"]) / (nxt["t"] - curr["t"])
        return curr["qpos"] + (nxt["qpos"] - curr["qpos"]) * frac

    def _build_waypoints(self, ts_first):
        box_xyz = np.array(ts_first.observation["env_state"][:3])
        r = np.sqrt(box_xyz[0] ** 2 + box_xyz[1] ** 2)
        alpha = np.clip((r - self._R_NEAR) / (self._R_FAR - self._R_NEAR), 0.0, 1.0)

        dig_swing = np.clip(
            np.arctan2(box_xyz[1], max(box_xyz[0], 0.2)) - 0.15, -1.2, 1.2
        )
        dump_swing = -1.90
        start_q = np.array(ts_first.observation["qpos"]).copy()

        def lerp(near, far): return near + (far - near) * alpha

        load_bsb   = lerp(self._LOAD_NEAR,   self._LOAD_FAR)
        secure_bsb = lerp(self._SECURE_NEAR, self._SECURE_FAR)
        lift_bsb   = lerp(self._LIFT_NEAR,   self._LIFT_FAR)
        carry_bsb  = lerp(self._CARRY_NEAR,  self._CARRY_FAR)

        def pose(sw, bsb): return np.array([sw, bsb[0], bsb[1], bsb[2]])

        load_pose   = pose(dig_swing - 0.26, load_bsb)
        secure_pose = pose(dig_swing - 0.30, secure_bsb)
        lift_pose   = pose(dig_swing - 0.28, lift_bsb)
        carry_pose  = pose(dig_swing - 0.32, carry_bsb)
        approach_pose = np.array([
            (start_q[0] + load_pose[0]) * 0.5,
            (start_q[1] + load_pose[1]) * 0.5,
            (start_q[2] + load_pose[2]) * 0.5,
            start_q[3],
        ])
        lbk = carry_bsb[2]

        self.waypoints = [
            {"t": 0,   "qpos": start_q,     "phase": "approach"},
            {"t": 40,  "qpos": approach_pose,"phase": "approach"},
            {"t": 80,  "qpos": load_pose,    "phase": "hold_for_load"},
            {"t": 185, "qpos": load_pose,    "phase": "hold_end"},
            {"t": 235, "qpos": secure_pose,  "phase": "secure"},
            {"t": 275, "qpos": lift_pose,    "phase": "lift"},
            {"t": 305, "qpos": carry_pose,   "phase": "carry"},
            {"t": 332, "qpos": np.array([dump_swing+0.55,-0.18, 0.40, lbk]), "phase": "transport"},
            {"t": 354, "qpos": np.array([dump_swing+0.28,-0.14, 0.46, lbk]), "phase": "transport"},
            {"t": 370, "qpos": np.array([dump_swing+0.12,-0.08, 0.54, lbk]), "phase": "transport"},
            {"t": 378, "qpos": np.array([dump_swing, -0.02, 0.62,-0.55]),    "phase": "dump"},
            {"t": 388, "qpos": np.array([dump_swing, -0.05, 0.68,-0.20]),    "phase": "dump"},
            {"t": 394, "qpos": np.array([dump_swing, -0.08, 0.72, 0.10]),    "phase": "dump"},
            {"t": 398, "qpos": np.array([dump_swing+0.08,-0.06,0.62, 0.30]),"phase": "retreat"},
            {"t": 400, "qpos": start_q,      "phase": "done"},
        ]

    def _advance_to_phase(self, target: str):
        while self.waypoints and self.waypoints[0].get("phase") != target:
            self.waypoints.pop(0)
        self.curr_waypoint = {
            "t": self.step_count,
            "qpos": self.curr_waypoint["qpos"].copy(),
            "phase": self._phase,
        }
        self._phase = target

    def __call__(self, ts):
        if self.step_count == 0:
            self._build_waypoints(ts)
            self.curr_waypoint = self.waypoints.pop(0)
            self._phase = self.curr_waypoint.get("phase", "approach")

        if self._phase == "hold_for_load":
            box_z = ts.observation["env_state"][2]
            if box_z > 0.30 and self.waypoints:
                self._advance_to_phase("secure")

        if self.waypoints and self.waypoints[0]["t"] <= self.step_count:
            self.curr_waypoint = self.waypoints.pop(0)
            self._phase = self.curr_waypoint.get("phase", self._phase)

        if not self.waypoints:
            self.step_count += 1
            return self.curr_waypoint["qpos"].copy()

        action = self._interp(self.curr_waypoint, self.waypoints[0], self.step_count)
        if self.inject_noise:
            action = action + np.random.uniform(-0.01, 0.01, size=action.shape)
        self.step_count += 1
        return action
