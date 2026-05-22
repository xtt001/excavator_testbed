from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from testbed.eval.suite import EvalSuite
from testbed.planner.boundary_detector import (
    BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
    BoundaryDetector,
    BoundaryDetectorConfig,
    QUALIFIED_DIG_START_MODE_CONTACT_DEPTH,
    build_boundary_detector_from_config,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
)
from testbed.planner.corridor_servo import (
    TRANSITION_SUBMODE_WAIT_NEXT_DIG,
    TransitionController,
    WAIT_NEXT_DIG_MODE_SERVO_REENTRY_POSE,
    build_default_entry_corridor_bands,
    normalize_named_entry_corridor_bands,
)
from testbed.planner.fixed_sequence_planner import FixedSequencePlanner
from testbed.policies.hybrid.adapter import HybridPlannerACTPolicy
from testbed.runtime._eval import eval_policy


class _FakeMetrics:
    def __init__(self) -> None:
        self.saved_json: Path | None = None

    def to_json(self, path: Path | str) -> None:
        self.saved_json = Path(path)


class _ConstantWorkPolicy:
    def __init__(self, action: np.ndarray | None = None) -> None:
        self._action = (
            np.asarray(action, dtype=np.float32)
            if action is not None
            else np.zeros(4, dtype=np.float32)
        )

    def reset(self) -> None:
        pass

    def predict(self, _obs) -> np.ndarray:
        return self._action.copy()


class _RecordingWorkPolicy(_ConstantWorkPolicy):
    def __init__(self, action: np.ndarray | None = None) -> None:
        super().__init__(action)
        self.predict_calls = 0
        self.reset_calls = 0
        self.last_obs = None

    def reset(self) -> None:
        self.reset_calls += 1

    def predict(self, _obs) -> np.ndarray:
        self.predict_calls += 1
        self.last_obs = dict(_obs)
        return super().predict(_obs)


def _make_env_state(
    *,
    mass_in_bucket: float = 0.0,
    excavated_mass: float = 0.0,
    mass_in_target_box: float = 0.0,
    deposited_mass: float = 0.0,
    min_distance_to_target: float = 2.0,
    target_horizontal_distance: float | None = None,
    bucket_height_above_target_rim: float = -0.10,
    bucket_over_target_footprint: float = 0.0,
    dump_clearance_ok: float = 0.0,
    collision_count: float = 0.0,
    min_distance_to_dig_area: float = 0.20,
    bucket_depth: float = 0.0,
) -> np.ndarray:
    return np.asarray(
        [
            mass_in_bucket,
            excavated_mass,
            mass_in_target_box,
            deposited_mass,
            min_distance_to_target,
            collision_count,
            0.0,
            min_distance_to_dig_area,
            bucket_depth,
            min_distance_to_target
            if target_horizontal_distance is None
            else target_horizontal_distance,
            bucket_height_above_target_rim,
            bucket_over_target_footprint,
            dump_clearance_ok,
        ],
        dtype=np.float32,
    )


def _make_obs(
    *,
    qpos: np.ndarray | None = None,
    qvel: np.ndarray | None = None,
    env_state: np.ndarray | None = None,
    reward_phase: str = "",
    task_step_successes: list[str] | None = None,
    task_metrics: dict[str, float] | None = None,
) -> dict[str, object]:
    return {
        "qpos": np.asarray(
            qpos if qpos is not None else [0.50, 0.634, 0.523, 0.690],
            dtype=np.float32,
        ),
        "qvel": np.asarray(
            qvel if qvel is not None else [0.0, 0.0, 0.0, 0.0],
            dtype=np.float32,
        ),
        "env_state": (
            np.asarray(env_state, dtype=np.float32)
            if env_state is not None
            else _make_env_state()
        ),
        "reward_phase": reward_phase,
        "task_step_successes": list(task_step_successes or []),
        "task_metrics": dict(task_metrics or {}),
        "images": {},
    }


class Stage2FixedPlannerTests(unittest.TestCase):
    def test_fixed_sequence_planner_saturates_at_last_sector(self) -> None:
        planner = FixedSequencePlanner(["mid", "mid", "mid"])
        self.assertEqual(planner.sector_name_for_cycle(0), "mid")
        self.assertEqual(planner.sector_name_for_cycle(1), "mid")
        self.assertEqual(planner.sector_name_for_cycle(99), "mid")
        self.assertEqual(planner.sector_id_for_cycle(2), 1)


class Stage2CorridorServoTests(unittest.TestCase):
    def test_corridor_band_names_follow_low_swing_left_high_swing_right(self) -> None:
        bands = build_default_entry_corridor_bands()
        self.assertLess(float(bands["left"].center[0]), float(bands["mid"].center[0]))
        self.assertLess(float(bands["mid"].center[0]), float(bands["right"].center[0]))

    def test_legacy_mirrored_named_bands_are_auto_normalized(self) -> None:
        legacy = {
            "left": replace(
                build_default_entry_corridor_bands()["right"],
                name="left",
                sector_id=0,
            ),
            "mid": build_default_entry_corridor_bands()["mid"],
            "right": replace(
                build_default_entry_corridor_bands()["left"],
                name="right",
                sector_id=2,
            ),
        }
        normalized = normalize_named_entry_corridor_bands(legacy)
        self.assertLess(float(normalized["left"].center[0]), float(normalized["mid"].center[0]))
        self.assertLess(float(normalized["mid"].center[0]), float(normalized["right"].center[0]))
        self.assertEqual(normalized["left"].sector_id, 0)
        self.assertEqual(normalized["mid"].sector_id, 1)
        self.assertEqual(normalized["right"].sector_id, 2)

    def test_corridor_align_reaches_wait_next_dig_after_hold(self) -> None:
        controller = TransitionController(
            bands=build_default_entry_corridor_bands(),
            clear_target_max_steps=60,
            corridor_align_max_steps=100,
            wait_next_dig_max_steps=120,
        )
        controller.start_transition(
            target_sector_name="mid",
            env_state=_make_env_state(min_distance_to_target=2.0),
        )

        # clear_target -> corridor_align
        controller.step(
            obs=_make_obs(env_state=_make_env_state(min_distance_to_target=2.0)),
            qualified_dig_start=False,
        )
        output = None
        for _ in range(5):
            output = controller.step(
                obs=_make_obs(
                    qpos=np.asarray([0.50, 0.634, 0.523, 0.690], dtype=np.float32),
                    qvel=np.zeros(4, dtype=np.float32),
                    env_state=_make_env_state(min_distance_to_target=2.0),
                ),
                qualified_dig_start=False,
            )
        assert output is not None
        self.assertEqual(output.action.shape, (4,))
        self.assertEqual(output.submode, TRANSITION_SUBMODE_WAIT_NEXT_DIG)
        self.assertFalse(output.transition_timeout)

    def test_corridor_align_timeout_flags_failure(self) -> None:
        controller = TransitionController(
            bands=build_default_entry_corridor_bands(),
            corridor_align_max_steps=2,
        )
        controller.start_transition(
            target_sector_name="mid",
            env_state=_make_env_state(min_distance_to_target=2.0),
        )
        controller.step(
            obs=_make_obs(env_state=_make_env_state(min_distance_to_target=2.0)),
            qualified_dig_start=False,
        )
        controller.step(
            obs=_make_obs(
                qpos=np.asarray([0.9, 0.9, 0.9, 0.9], dtype=np.float32),
                qvel=np.asarray([0.4, 0.4, 0.4, 0.4], dtype=np.float32),
                env_state=_make_env_state(min_distance_to_target=2.0),
            ),
            qualified_dig_start=False,
        )
        output = controller.step(
            obs=_make_obs(
                qpos=np.asarray([0.9, 0.9, 0.9, 0.9], dtype=np.float32),
                qvel=np.asarray([0.4, 0.4, 0.4, 0.4], dtype=np.float32),
                env_state=_make_env_state(min_distance_to_target=2.0),
            ),
            qualified_dig_start=False,
        )
        self.assertTrue(output.transition_timeout)
        self.assertEqual(output.action.shape, (4,))

    def test_scripted_transition_can_target_near_zero_bucket_qpos(self) -> None:
        controller = TransitionController(
            bands=build_default_entry_corridor_bands(),
            scripted_bucket_qpos_target=0.0,
            action_clip_by_joint=[0.75, 0.35, 0.35, 0.55],
        )
        controller.start_transition(
            target_sector_name="mid",
            env_state=_make_env_state(min_distance_to_target=2.0),
        )

        output = controller.step(
            obs=_make_obs(
                qpos=np.asarray([0.50, 0.634, 0.523, 0.690], dtype=np.float32),
                qvel=np.zeros(4, dtype=np.float32),
                env_state=_make_env_state(min_distance_to_target=2.0),
            ),
            qualified_dig_start=False,
        )

        self.assertEqual(output.action.shape, (4,))
        self.assertLess(float(output.action[3]), -0.50)
        reentry_target = controller.wait_next_dig_reentry_target_qpos("mid")
        self.assertAlmostEqual(float(reentry_target[3]), 0.0)

        for _ in range(5):
            output = controller.step(
                obs=_make_obs(
                    qpos=np.asarray([0.50, 0.634, 0.523, 0.0], dtype=np.float32),
                    qvel=np.zeros(4, dtype=np.float32),
                    env_state=_make_env_state(min_distance_to_target=2.0),
                ),
                qualified_dig_start=False,
            )
        self.assertEqual(output.submode, TRANSITION_SUBMODE_WAIT_NEXT_DIG)


class Stage2BoundaryDetectorTests(unittest.TestCase):
    def test_contact_depth_mode_emits_qds_without_mass_progress(self) -> None:
        progress_detector = BoundaryDetector()
        contact_detector = BoundaryDetector(
            BoundaryDetectorConfig(
                qualified_dig_start_mode=QUALIFIED_DIG_START_MODE_CONTACT_DEPTH
            )
        )
        env_state = _make_env_state(
            mass_in_bucket=0.0,
            excavated_mass=0.0,
            min_distance_to_dig_area=0.04,
            bucket_depth=0.03,
        )
        action = np.zeros(4, dtype=np.float32)
        qpos = np.asarray([0.5, 0.6, 0.5, 0.6], dtype=np.float32)

        self.assertFalse(
            progress_detector.update(
                env_state=env_state,
                action=action,
                qpos=qpos,
                reward_phase="",
                task_step_successes=[],
            ).qualified_dig_start
        )
        self.assertTrue(
            contact_detector.update(
                env_state=env_state,
                action=action,
                qpos=qpos,
                reward_phase="",
                task_step_successes=[],
            ).qualified_dig_start
        )

    def test_dump_start_and_end_detect_even_when_truck_distance_is_large(self) -> None:
        detector = BoundaryDetector()

        detector.update(
            env_state=_make_env_state(),
            action=np.zeros(4, dtype=np.float32),
            qpos=np.asarray([0.5, 0.6, 0.5, 0.6], dtype=np.float32),
            reward_phase="",
            task_step_successes=[],
            task_metrics={},
        )
        detector.update(
            env_state=_make_env_state(
                mass_in_bucket=120.0,
                excavated_mass=10.0,
                min_distance_to_dig_area=0.04,
                bucket_depth=0.03,
            ),
            action=np.zeros(4, dtype=np.float32),
            qpos=np.asarray([0.5, 0.6, 0.5, 0.6], dtype=np.float32),
            reward_phase="good_dig_start",
            task_step_successes=["good_dig_start"],
            task_metrics={},
        )

        dump_start_event = detector.update(
            env_state=_make_env_state(
                mass_in_bucket=80.0,
                excavated_mass=20.0,
                deposited_mass=200.0,
                min_distance_to_target=3.0,
            ),
            action=np.zeros(4, dtype=np.float32),
            qpos=np.asarray([0.26, 0.75, 0.53, 0.12], dtype=np.float32),
            reward_phase="depositing",
            task_step_successes=[],
            task_metrics={
                "delta_deposited_mass_in_target_box_kg": 120.0,
                "success_condition_met": 1.0,
                "success_signal_value": 200.0,
            },
        )
        self.assertTrue(dump_start_event.dump_start)

        dump_end_event = None
        for _ in range(3):
            dump_end_event = detector.update(
                env_state=_make_env_state(
                    mass_in_bucket=0.0,
                    excavated_mass=20.0,
                    deposited_mass=200.0,
                    min_distance_to_target=3.2,
                ),
                action=np.zeros(4, dtype=np.float32),
                qpos=np.asarray([0.26, 0.75, 0.53, 0.12], dtype=np.float32),
                reward_phase="retained_success",
                task_step_successes=[],
                task_metrics={
                    "delta_deposited_mass_in_target_box_kg": 0.0,
                    "success_condition_met": 1.0,
                    "success_signal_value": 200.0,
                },
            )
        assert dump_end_event is not None
        self.assertTrue(dump_end_event.dump_end)

    def test_dump_start_accepts_smooth_cumulative_professional_deposit(self) -> None:
        detector = BoundaryDetector(
            BoundaryDetectorConfig(
                qualified_dig_start_mode=QUALIFIED_DIG_START_MODE_CONTACT_DEPTH,
                target_mass_delta_tol_kg=2.0,
                dump_start_min_cumulative_deposit_delta_kg=5.0,
                residual_bucket_mass_thresh=15.0,
                deposit_plateau_steps=2,
            )
        )
        action = np.zeros(4, dtype=np.float32)
        qpos = np.asarray([0.5, 0.6, 0.5, 0.6], dtype=np.float32)

        first_dig = detector.update(
            env_state=_make_env_state(
                min_distance_to_dig_area=0.04,
                bucket_depth=0.03,
            ),
            action=action,
            qpos=qpos,
        )
        self.assertTrue(first_dig.qualified_dig_start)

        dump_start_event = None
        for deposited_mass in (1.5, 3.0, 4.5, 6.0):
            dump_start_event = detector.update(
                env_state=_make_env_state(
                    mass_in_bucket=20.0,
                    deposited_mass=deposited_mass,
                    min_distance_to_target=0.30,
                    target_horizontal_distance=0.30,
                    bucket_height_above_target_rim=0.70,
                    bucket_over_target_footprint=1.0,
                    dump_clearance_ok=1.0,
                    min_distance_to_dig_area=1.0,
                    bucket_depth=0.0,
                ),
                action=action,
                qpos=qpos,
                task_metrics={
                    "delta_deposited_mass_in_target_box_kg": 1.5,
                    "target_geometry_available": 1.0,
                    "target_horizontal_distance_m": 0.30,
                },
            )

        assert dump_start_event is not None
        self.assertTrue(dump_start_event.dump_start)

        dump_end_event = None
        dump_end_seen = False
        for _ in range(2):
            dump_end_event = detector.update(
                env_state=_make_env_state(
                    mass_in_bucket=0.0,
                    deposited_mass=6.0,
                    min_distance_to_target=0.30,
                    target_horizontal_distance=0.30,
                    bucket_height_above_target_rim=0.70,
                    bucket_over_target_footprint=1.0,
                    dump_clearance_ok=1.0,
                    min_distance_to_dig_area=1.0,
                    bucket_depth=0.0,
                ),
                action=action,
                qpos=qpos,
                task_metrics={
                    "delta_deposited_mass_in_target_box_kg": 0.0,
                    "target_geometry_available": 1.0,
                    "target_horizontal_distance_m": 0.30,
                },
            )
            dump_end_seen = dump_end_seen or bool(dump_end_event.dump_end)

        assert dump_end_event is not None
        self.assertTrue(dump_end_seen)

    def test_v2_4_5_spatial_mass_events_are_causal_and_pre_deposit(self) -> None:
        detector = BoundaryDetector(
            BoundaryDetectorConfig(
                boundary_profile=BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
                qualified_dig_start_mode=QUALIFIED_DIG_START_MODE_CONTACT_DEPTH,
                residual_bucket_mass_thresh=15.0,
                deposit_plateau_steps=1,
                dig_complete_min_bucket_mass_kg=15.0,
                dig_complete_mass_plateau_hold_steps=1,
                dig_complete_departed_hold_steps=1,
                dump_committed_hold_steps=1,
            )
        )
        action = np.zeros(4, dtype=np.float32)
        qpos = np.asarray([0.5, 0.6, 0.5, 0.6], dtype=np.float32)

        def env(
            *,
            mass: float,
            dig_distance: float,
            depth: float,
            deposited_target: float = 0.0,
            deposited_dump_area: float = 0.0,
            outside: float = 9.0,
            relative_x: float = 9.0,
            relative_z: float = 9.0,
            height: float = 0.0,
        ) -> np.ndarray:
            state = np.zeros(64, dtype=np.float32)
            state[ENV_STATE_MASS_IN_BUCKET_IDX] = float(mass)
            state[ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = float(dig_distance)
            state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = float(depth)
            state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = float(deposited_target)
            state[ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX] = float(deposited_dump_area)
            state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = float(outside)
            state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = float(relative_x)
            state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = float(relative_z)
            state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = float(height)
            state[ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 1.0
            return state

        first = detector.update(
            env_state=env(mass=0.0, dig_distance=0.04, depth=0.03),
            action=action,
            qpos=qpos,
        )
        self.assertTrue(first.dig_start)

        detector.update(
            env_state=env(mass=30.0, dig_distance=0.12, depth=0.0),
            action=action,
            qpos=qpos,
        )
        dig_complete = detector.update(
            env_state=env(mass=30.0, dig_distance=0.12, depth=0.0),
            action=action,
            qpos=qpos,
        )
        self.assertTrue(dig_complete.dig_complete)

        committed = detector.update(
            env_state=env(
                mass=30.0,
                dig_distance=0.30,
                depth=0.0,
                outside=0.10,
                relative_x=0.75,
                relative_z=1.20,
                height=0.70,
            ),
            action=action,
            qpos=qpos,
        )
        self.assertTrue(committed.dump_committed_start)
        self.assertTrue(committed.dump_start)
        self.assertFalse(committed.release_onset)

        release = detector.update(
            env_state=env(
                mass=28.5,
                dig_distance=0.30,
                depth=0.0,
                deposited_dump_area=0.6,
                outside=0.10,
                relative_x=0.75,
                relative_z=1.20,
                height=0.70,
            ),
            action=action,
            qpos=qpos,
        )
        self.assertTrue(release.release_onset)
        self.assertFalse(release.dump_complete)

        complete = detector.update(
            env_state=env(
                mass=0.0,
                dig_distance=0.30,
                depth=0.0,
                deposited_dump_area=0.6,
                outside=0.10,
                relative_x=0.75,
                relative_z=1.20,
                height=0.70,
            ),
            action=action,
            qpos=qpos,
        )
        self.assertTrue(complete.dump_complete)
        self.assertTrue(complete.dump_end)

    def test_build_boundary_detector_accepts_boundary_profile_config(self) -> None:
        detector = build_boundary_detector_from_config(
            reward_cfg={"qualified_dig_start_mode": QUALIFIED_DIG_START_MODE_CONTACT_DEPTH},
            boundary_cfg={"profile": BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS},
        )

        self.assertEqual(
            detector.config.boundary_profile,
            BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
        )


class Stage2HybridPolicyTests(unittest.TestCase):
    def _build_policy(
        self,
        *,
        corridor_align_max_steps: int = 100,
        wait_next_dig_max_steps: int = 120,
    ) -> HybridPlannerACTPolicy:
        return HybridPlannerACTPolicy(
            work_policy=_ConstantWorkPolicy(),
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
                corridor_align_max_steps=corridor_align_max_steps,
                wait_next_dig_max_steps=wait_next_dig_max_steps,
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )

    def test_hybrid_policy_switches_work_transition_work(self) -> None:
        policy = self._build_policy()
        policy.reset()

        seq = [
            _make_obs(),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=120.0,
                    excavated_mass=10.0,
                    min_distance_to_dig_area=0.04,
                    bucket_depth=0.03,
                ),
                reward_phase="good_dig_start",
                task_step_successes=["good_dig_start"],
            ),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=140.0,
                    excavated_mass=20.0,
                    deposited_mass=12.0,
                    min_distance_to_target=1.0,
                    min_distance_to_dig_area=0.03,
                    bucket_depth=0.04,
                ),
                reward_phase="depositing",
            ),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=80.0,
                    excavated_mass=20.0,
                    deposited_mass=12.0,
                    min_distance_to_target=2.0,
                ),
            ),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=80.0,
                    excavated_mass=20.0,
                    deposited_mass=12.0,
                    min_distance_to_target=2.0,
                ),
            ),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=80.0,
                    excavated_mass=20.0,
                    deposited_mass=12.0,
                    min_distance_to_target=2.0,
                ),
            ),
            _make_obs(env_state=_make_env_state(min_distance_to_target=2.0)),
            _make_obs(env_state=_make_env_state(min_distance_to_target=2.0)),
            _make_obs(env_state=_make_env_state(min_distance_to_target=2.0)),
            _make_obs(env_state=_make_env_state(min_distance_to_target=2.0)),
            _make_obs(env_state=_make_env_state(min_distance_to_target=2.0)),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=110.0,
                    excavated_mass=30.0,
                    min_distance_to_dig_area=0.04,
                    bucket_depth=0.03,
                ),
                reward_phase="good_dig_start",
                task_step_successes=["good_dig_start"],
            ),
        ]

        for obs in seq[:6]:
            policy.predict(obs)
        state = policy.debug_state()
        self.assertEqual(state["hybrid_mode"], "TRANSITION")
        self.assertEqual(state["transition_submode"], "corridor_align")

        for obs in seq[6:11]:
            policy.predict(obs)
        state = policy.debug_state()
        self.assertEqual(state["hybrid_mode"], "TRANSITION")
        self.assertEqual(state["transition_submode"], "wait_next_dig")

        policy.predict(seq[11])
        state = policy.debug_state()
        self.assertEqual(state["hybrid_mode"], "WORK")
        self.assertTrue(state["transition_completed"])
        self.assertEqual(state["planner_cycle_index"], 1)

    def test_work_target_guard_caps_close_loaded_bucket_dump_action(self) -> None:
        policy = HybridPlannerACTPolicy(
            work_policy=_ConstantWorkPolicy(
                np.asarray([0.01, -0.02, 0.0, -0.80], dtype=np.float32)
            ),
            work_target_guard_enabled=True,
            work_target_guard_distance_m=0.45,
            work_target_guard_min_bucket_mass_kg=300.0,
            work_target_guard_bucket_action_floor=-0.15,
            work_target_guard_boom_action_min=0.08,
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )
        action = policy.predict(
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=1200.0,
                    min_distance_to_target=0.30,
                )
            )
        )

        self.assertAlmostEqual(float(action[1]), 0.08)
        self.assertAlmostEqual(float(action[3]), -0.15)
        self.assertTrue(policy.debug_state()["work_target_guard_active"])
        self.assertEqual(policy.rollout_summary()["work_target_guard_count"], 1)

    def test_work_target_guard_leaves_far_target_action_unchanged(self) -> None:
        raw_action = np.asarray([0.01, -0.02, 0.0, -0.80], dtype=np.float32)
        policy = HybridPlannerACTPolicy(
            work_policy=_ConstantWorkPolicy(raw_action),
            work_target_guard_enabled=True,
            work_target_guard_distance_m=0.45,
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )
        action = policy.predict(
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=1200.0,
                    min_distance_to_target=0.80,
                )
            )
        )

        np.testing.assert_allclose(action, raw_action)
        self.assertFalse(policy.debug_state()["work_target_guard_active"])
        self.assertEqual(policy.rollout_summary()["work_target_guard_count"], 0)

    def test_work_target_guard_soft_caps_loaded_approach_dump_action(self) -> None:
        policy = HybridPlannerACTPolicy(
            work_policy=_ConstantWorkPolicy(
                np.asarray([0.01, -0.02, 0.0, -0.80], dtype=np.float32)
            ),
            work_target_guard_enabled=True,
            work_target_guard_distance_m=0.45,
            work_target_guard_bucket_action_floor=-0.15,
            work_target_guard_boom_action_min=0.08,
            work_target_guard_approach_distance_m=1.25,
            work_target_guard_approach_bucket_action_floor=-0.30,
            work_target_guard_approach_boom_action_min=0.04,
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )
        action = policy.predict(
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=1200.0,
                    min_distance_to_target=0.80,
                )
            )
        )

        self.assertAlmostEqual(float(action[1]), 0.04)
        self.assertAlmostEqual(float(action[3]), -0.30)
        self.assertTrue(policy.debug_state()["work_target_guard_active"])
        self.assertEqual(policy.rollout_summary()["work_target_guard_count"], 1)

    def test_work_target_guard_allows_dump_when_target_clearance_is_ok(self) -> None:
        raw_action = np.asarray([0.01, -0.02, 0.0, -0.80], dtype=np.float32)
        policy = HybridPlannerACTPolicy(
            work_policy=_ConstantWorkPolicy(raw_action),
            work_target_guard_enabled=True,
            work_target_guard_distance_m=0.45,
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )
        action = policy.predict(
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=1200.0,
                    min_distance_to_target=0.20,
                    target_horizontal_distance=0.20,
                    bucket_height_above_target_rim=0.15,
                    bucket_over_target_footprint=1.0,
                    dump_clearance_ok=1.0,
                )
            )
        )

        np.testing.assert_allclose(action, raw_action)
        self.assertFalse(policy.debug_state()["work_target_guard_active"])
        self.assertEqual(policy.rollout_summary()["work_target_guard_count"], 0)

    def test_work_target_guard_rejects_legacy_target_distance_fallback(self) -> None:
        policy = HybridPlannerACTPolicy(
            work_policy=_ConstantWorkPolicy(
                np.asarray([0.01, -0.02, 0.0, -0.80], dtype=np.float32)
            ),
            work_target_guard_enabled=True,
            work_target_guard_distance_m=0.45,
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "target geometry fields"):
            policy.predict(
                _make_obs(
                    env_state=np.asarray(
                        [1200.0, 0.0, 0.0, 0.0, 0.20, 0.0, 0.0, 0.2, 0.0],
                        dtype=np.float32,
                    )
                )
            )

    def test_hybrid_policy_marks_transition_timeout(self) -> None:
        policy = self._build_policy(corridor_align_max_steps=2)
        policy.reset()

        pre_transition = [
            _make_obs(),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=120.0,
                    excavated_mass=10.0,
                    min_distance_to_dig_area=0.04,
                    bucket_depth=0.03,
                ),
                reward_phase="good_dig_start",
                task_step_successes=["good_dig_start"],
            ),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=140.0,
                    excavated_mass=20.0,
                    deposited_mass=12.0,
                    min_distance_to_target=1.0,
                    min_distance_to_dig_area=0.03,
                    bucket_depth=0.04,
                ),
            ),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=80.0,
                    excavated_mass=20.0,
                    deposited_mass=12.0,
                    min_distance_to_target=2.0,
                ),
            ),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=80.0,
                    excavated_mass=20.0,
                    deposited_mass=12.0,
                    min_distance_to_target=2.0,
                ),
            ),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=80.0,
                    excavated_mass=20.0,
                    deposited_mass=12.0,
                    min_distance_to_target=2.0,
                ),
            ),
        ]
        for obs in pre_transition:
            policy.predict(obs)

        policy.predict(
            _make_obs(
                qpos=np.asarray([0.90, 0.90, 0.90, 0.90], dtype=np.float32),
                qvel=np.asarray([0.4, 0.4, 0.4, 0.4], dtype=np.float32),
                env_state=_make_env_state(min_distance_to_target=2.0),
            )
        )
        policy.predict(
            _make_obs(
                qpos=np.asarray([0.90, 0.90, 0.90, 0.90], dtype=np.float32),
                qvel=np.asarray([0.4, 0.4, 0.4, 0.4], dtype=np.float32),
                env_state=_make_env_state(min_distance_to_target=2.0),
            )
        )
        state = policy.debug_state()
        self.assertTrue(state["transition_timeout"])
        self.assertEqual(state["hybrid_mode"], "TRANSITION")

    def test_wait_next_dig_hands_actions_back_to_work_policy(self) -> None:
        work_action = np.asarray([0.11, -0.22, 0.07, -0.03], dtype=np.float32)
        policy = HybridPlannerACTPolicy(
            work_policy=_ConstantWorkPolicy(work_action),
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )
        policy.reset()
        policy.transition_controller.start_transition(
            target_sector_name="mid",
            env_state=_make_env_state(min_distance_to_target=2.0),
        )
        policy._mode = "TRANSITION"  # exercise the Stage-2 handoff path directly
        policy.transition_controller._submode = TRANSITION_SUBMODE_WAIT_NEXT_DIG

        action = policy.predict(
            _make_obs(
                qpos=np.asarray([0.50, 0.634, 0.523, 0.690], dtype=np.float32),
                qvel=np.zeros(4, dtype=np.float32),
                env_state=_make_env_state(min_distance_to_target=2.0),
            )
        )
        np.testing.assert_allclose(action, work_action)

    def test_wait_next_dig_prefers_transition_policy_when_present(self) -> None:
        work_action = np.asarray([0.11, -0.22, 0.07, -0.03], dtype=np.float32)
        transition_action = np.asarray([-0.15, 0.04, -0.08, 0.12], dtype=np.float32)
        policy = HybridPlannerACTPolicy(
            work_policy=_ConstantWorkPolicy(work_action),
            transition_policy=_ConstantWorkPolicy(transition_action),
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )
        policy.reset()
        policy.transition_controller.start_transition(
            target_sector_name="mid",
            env_state=_make_env_state(min_distance_to_target=2.0),
        )
        policy._mode = "TRANSITION"
        policy.transition_controller._submode = TRANSITION_SUBMODE_WAIT_NEXT_DIG

        action = policy.predict(
            _make_obs(
                qpos=np.asarray([0.50, 0.634, 0.523, 0.690], dtype=np.float32),
                qvel=np.zeros(4, dtype=np.float32),
                env_state=_make_env_state(min_distance_to_target=2.0),
            )
        )
        np.testing.assert_allclose(action, transition_action)
        self.assertEqual(
            policy.debug_state()["transition_source"],
            "learned_wait_next_dig_policy",
        )

    def test_wait_next_dig_can_use_servo_reentry_pose_instead_of_work_policy(self) -> None:
        work_action = np.asarray([0.11, -0.22, 0.07, -0.03], dtype=np.float32)
        policy = HybridPlannerACTPolicy(
            work_policy=_ConstantWorkPolicy(work_action),
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
                wait_next_dig_mode=WAIT_NEXT_DIG_MODE_SERVO_REENTRY_POSE,
                wait_next_dig_reentry_template_qpos=[0.50, 0.255, 0.520, 0.0002],
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )
        policy.reset()
        policy.transition_controller.start_transition(
            target_sector_name="left",
            env_state=_make_env_state(min_distance_to_target=2.0),
        )
        policy._mode = "TRANSITION"
        policy.transition_controller._submode = TRANSITION_SUBMODE_WAIT_NEXT_DIG

        action = policy.predict(
            _make_obs(
                qpos=np.asarray([0.68, 0.634, 0.523, 0.690], dtype=np.float32),
                qvel=np.zeros(4, dtype=np.float32),
                env_state=_make_env_state(min_distance_to_target=2.0),
            )
        )
        self.assertEqual(action.shape, (4,))
        self.assertFalse(np.allclose(action, work_action))
        self.assertLess(float(action[1]), 0.0)
        self.assertLess(float(action[3]), 0.0)

    def test_bootstrap_policy_handles_pre_first_dig_then_switches_to_work_policy(self) -> None:
        bootstrap_action = np.asarray([0.31, 0.00, 0.00, -0.11], dtype=np.float32)
        work_action = np.asarray([-0.07, 0.21, 0.05, 0.02], dtype=np.float32)
        bootstrap = _RecordingWorkPolicy(bootstrap_action)
        work = _RecordingWorkPolicy(work_action)
        policy = HybridPlannerACTPolicy(
            work_policy=work,
            bootstrap_policy=bootstrap,
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )
        policy.reset()
        work_reset_calls_before_switch = work.reset_calls

        bootstrap_step = policy.predict(_make_obs())
        np.testing.assert_allclose(bootstrap_step, bootstrap_action)

        dig_start_step = policy.predict(
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=120.0,
                    excavated_mass=10.0,
                    min_distance_to_dig_area=0.04,
                    bucket_depth=0.03,
                ),
                reward_phase="good_dig_start",
                task_step_successes=["good_dig_start"],
            )
        )
        np.testing.assert_allclose(dig_start_step, work_action)
        self.assertEqual(work.reset_calls, work_reset_calls_before_switch + 1)
        self.assertGreaterEqual(bootstrap.predict_calls, 1)
        self.assertGreaterEqual(work.predict_calls, 1)

    def test_work_policy_resets_after_transition_completion(self) -> None:
        work = _RecordingWorkPolicy(np.asarray([0.11, -0.22, 0.07, -0.03], dtype=np.float32))
        policy = HybridPlannerACTPolicy(
            work_policy=work,
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )
        policy.reset()
        policy.transition_controller.start_transition(
            target_sector_name="mid",
            env_state=_make_env_state(min_distance_to_target=2.0),
        )
        policy._mode = "TRANSITION"
        policy.transition_controller._submode = TRANSITION_SUBMODE_WAIT_NEXT_DIG
        policy._prev_action = np.zeros(4, dtype=np.float32)
        policy.boundary_detector.update = lambda **_kwargs: SimpleNamespace(
            qualified_dig_start=True,
            dump_end=False,
            cycle_id=1,
            step_index=10,
            metrics={},
        )

        reset_calls_before_completion = work.reset_calls
        policy.predict(
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=120.0,
                    excavated_mass=30.0,
                    min_distance_to_dig_area=0.04,
                    bucket_depth=0.03,
                ),
                reward_phase="good_dig_start",
                task_step_successes=["good_dig_start"],
            )
        )

        self.assertTrue(policy.debug_state()["transition_completed"])
        self.assertEqual(work.reset_calls, reset_calls_before_completion + 1)

    def test_bootstrap_policy_can_wait_until_loaded_and_clear(self) -> None:
        bootstrap_action = np.asarray([0.31, 0.00, 0.00, -0.11], dtype=np.float32)
        work_action = np.asarray([-0.07, 0.21, 0.05, 0.02], dtype=np.float32)
        bootstrap = _RecordingWorkPolicy(bootstrap_action)
        work = _RecordingWorkPolicy(work_action)
        policy = HybridPlannerACTPolicy(
            work_policy=work,
            bootstrap_policy=bootstrap,
            bootstrap_end_mode="loaded_and_clear",
            bootstrap_end_min_bucket_mass_kg=300.0,
            bootstrap_end_min_distance_to_dig_area_m=0.25,
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )
        policy.reset()

        policy.predict(_make_obs())
        still_bootstrap = policy.predict(
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=180.0,
                    excavated_mass=180.0,
                    min_distance_to_dig_area=0.04,
                    bucket_depth=0.03,
                ),
                reward_phase="good_dig_start",
                task_step_successes=["good_dig_start"],
            )
        )
        np.testing.assert_allclose(still_bootstrap, bootstrap_action)

        candidate_actions = []
        for _ in range(3):
            candidate_actions.append(
                policy.predict(
                    _make_obs(
                        env_state=_make_env_state(
                            mass_in_bucket=450.0,
                            excavated_mass=500.0,
                            min_distance_to_dig_area=0.30,
                            bucket_depth=0.0,
                        ),
                        reward_phase="loading",
                    )
                )
            )
        self.assertTrue(
            any(np.allclose(action, work_action) for action in candidate_actions)
        )
        self.assertGreaterEqual(bootstrap.predict_calls, 2)
        self.assertGreaterEqual(work.predict_calls, 1)

    def test_transition_policy_can_fallback_to_scripted_wait_next_dig(self) -> None:
        transition_action = np.asarray([0.22, 0.00, 0.00, 0.00], dtype=np.float32)
        transition_policy = _RecordingWorkPolicy(transition_action)
        policy = HybridPlannerACTPolicy(
            work_policy=_ConstantWorkPolicy(np.zeros(4, dtype=np.float32)),
            transition_policy=transition_policy,
            transition_enable_fallback=True,
            transition_fallback_local_budget_steps=10,
            transition_fallback_no_progress_steps=1,
            transition_fallback_progress_mass_kg=500.0,
            planner=FixedSequencePlanner(["mid", "mid", "mid"]),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
                wait_next_dig_mode=WAIT_NEXT_DIG_MODE_SERVO_REENTRY_POSE,
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
        )
        policy.reset()
        policy.transition_controller.start_transition(
            target_sector_name="mid",
            env_state=_make_env_state(min_distance_to_target=2.0),
        )
        policy._mode = "TRANSITION"
        policy.transition_controller._submode = TRANSITION_SUBMODE_WAIT_NEXT_DIG
        policy._reset_active_transition_runtime()

        action = policy.predict(
            _make_obs(
                qpos=np.asarray([0.50, 0.634, 0.523, 0.690], dtype=np.float32),
                qvel=np.zeros(4, dtype=np.float32),
                env_state=_make_env_state(min_distance_to_target=2.0),
            )
        )
        self.assertEqual(action.shape, (4,))
        self.assertFalse(np.allclose(action, transition_action))
        debug = policy.debug_state()
        self.assertEqual(
            debug["transition_policy_mode"],
            "learned_fallback_to_scripted",
        )
        self.assertEqual(debug["transition_fallback_count"], 1)
        self.assertEqual(debug["transition_fallback_reason"], "no_progress")
        self.assertEqual(transition_policy.predict_calls, 0)


class Stage2EvalIntegrationTests(unittest.TestCase):
    def test_eval_policy_builds_hybrid_wrapper(self) -> None:
        captured: dict[str, object] = {}
        fake_metrics = _FakeMetrics()

        class FakeSuite:
            def __init__(self, **kwargs) -> None:
                captured["suite_kwargs"] = kwargs

            def run(self):
                return fake_metrics

        def _fake_from_checkpoint(**kwargs):
            captured["work_policy_kwargs"] = kwargs
            return _ConstantWorkPolicy()

        config = {
            "task": {
                "name": "agx_excavation_teleop",
                "scenario_id": "s0_baseline",
                "episode_len": 4000,
            },
            "eval": {
                "save_video": False,
                "results_dir": None,
                "target_cycle_gate": 2,
                "target_cycle_gate_terminal_hold_steps": 25,
            },
            "reward": {
                "target_approach_distance_m": 1.25,
            },
            "policy": {
                "class": "hybrid_planner_act",
                "device": "cpu",
                "work_ckpt_path": "runs/ckpts/agx_excavation_act_v1/policy_best.ckpt",
                "work_ckpt_dir": "runs/ckpts/agx_excavation_act_v1",
                "work_low_dim_keys": ["qpos"],
                "work_safety": {
                    "target_guard_enabled": True,
                    "target_guard_distance_m": 0.45,
                    "target_guard_bucket_action_floor": -0.15,
                    "target_guard_boom_action_min": 0.08,
                    "target_guard_approach_distance_m": 1.25,
                    "target_guard_approach_bucket_action_floor": -0.30,
                    "target_guard_approach_boom_action_min": 0.04,
                },
                "planner": {"sequence": ["mid", "mid", "mid"]},
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config["eval"]["results_dir"] = tmpdir
            with (
                patch("testbed.eval.suite.EvalSuite", FakeSuite),
                patch("testbed.eval.metrics.EvalMetrics.append_to_csv"),
                patch(
                    "testbed.policies.act.adapter.ACTAdapter.from_checkpoint",
                    side_effect=_fake_from_checkpoint,
                ),
            ):
                eval_policy(config)

        suite_kwargs = captured["suite_kwargs"]
        self.assertEqual(suite_kwargs["target_cycle_gate"], 2)
        self.assertEqual(suite_kwargs["target_cycle_gate_terminal_hold_steps"], 25)
        self.assertEqual(suite_kwargs["episode_len"], 4000)
        self.assertEqual(suite_kwargs["camera_names"], ["fpv"])
        self.assertEqual(type(suite_kwargs["policy"]).__name__, "HybridPlannerACTPolicy")
        self.assertEqual(
            suite_kwargs["policy"].planner.sequence,
            ("mid", "mid", "mid"),
        )
        self.assertTrue(suite_kwargs["policy"].work_target_guard_enabled)
        self.assertAlmostEqual(suite_kwargs["policy"].work_target_guard_distance_m, 0.45)
        self.assertAlmostEqual(
            suite_kwargs["policy"].work_target_guard_bucket_action_floor,
            -0.15,
        )
        self.assertAlmostEqual(suite_kwargs["policy"].work_target_guard_boom_action_min, 0.08)
        self.assertAlmostEqual(
            suite_kwargs["policy"].work_target_guard_approach_distance_m,
            1.25,
        )
        self.assertAlmostEqual(
            suite_kwargs["policy"].work_target_guard_approach_bucket_action_floor,
            -0.30,
        )
        self.assertAlmostEqual(
            suite_kwargs["policy"].work_target_guard_approach_boom_action_min,
            0.04,
        )
        self.assertEqual(
            captured["work_policy_kwargs"]["policy_config"]["low_dim_keys"],
            ["qpos"],
        )
        self.assertEqual(captured["work_policy_kwargs"]["policy_config"]["state_dim"], 4)

    def test_eval_policy_builds_optional_bootstrap_policy(self) -> None:
        captured: dict[str, object] = {"from_checkpoint_calls": []}
        fake_metrics = _FakeMetrics()

        class FakeSuite:
            def __init__(self, **kwargs) -> None:
                captured["suite_kwargs"] = kwargs

            def run(self):
                return fake_metrics

        def _fake_from_checkpoint(**kwargs):
            captured["from_checkpoint_calls"].append(kwargs)
            ckpt = str(kwargs["ckpt_path"])
            if "act_v1" in ckpt:
                return _ConstantWorkPolicy(np.asarray([0.1, 0.0, 0.0, 0.0], dtype=np.float32))
            return _ConstantWorkPolicy(np.asarray([0.0, 0.1, 0.0, 0.0], dtype=np.float32))

        config = {
            "task": {
                "name": "agx_excavation_teleop",
                "scenario_id": "s0_truck",
                "episode_len": 4000,
            },
            "eval": {
                "save_video": False,
                "results_dir": None,
            },
            "reward": {
                "target_approach_distance_m": 1.25,
            },
            "policy": {
                "class": "hybrid_planner_act",
                "device": "cpu",
                "work_ckpt_path": "runs/ckpts/agx_excavation_act_v2_1_workskill_qvel_e50/policy_best.ckpt",
                "work_ckpt_dir": "runs/ckpts/agx_excavation_act_v2_1_workskill_qvel_e50",
                "work_low_dim_keys": ["qpos", "qvel"],
                "bootstrap_ckpt_path": "runs/ckpts/agx_excavation_act_v1/policy_best.ckpt",
                "bootstrap_ckpt_dir": "runs/ckpts/agx_excavation_act_v1",
                "bootstrap_low_dim_keys": ["qpos"],
                "planner": {"sequence": ["mid", "mid", "mid"]},
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config["eval"]["results_dir"] = tmpdir
            with (
                patch("testbed.eval.suite.EvalSuite", FakeSuite),
                patch("testbed.eval.metrics.EvalMetrics.append_to_csv"),
                patch(
                    "testbed.policies.act.adapter.ACTAdapter.from_checkpoint",
                    side_effect=_fake_from_checkpoint,
                ),
            ):
                eval_policy(config)

        self.assertEqual(len(captured["from_checkpoint_calls"]), 2)
        suite_policy = captured["suite_kwargs"]["policy"]
        self.assertIsNotNone(suite_policy.bootstrap_policy)
        self.assertEqual(suite_policy.bootstrap_end_mode, "first_qualified_dig_start")

    def test_eval_policy_builds_optional_transition_policy(self) -> None:
        captured: dict[str, object] = {"from_checkpoint_calls": []}
        fake_metrics = _FakeMetrics()

        class FakeSuite:
            def __init__(self, **kwargs) -> None:
                captured["suite_kwargs"] = kwargs

            def run(self):
                return fake_metrics

        def _fake_from_checkpoint(**kwargs):
            captured["from_checkpoint_calls"].append(kwargs)
            ckpt = str(kwargs["ckpt_path"])
            if "transition" in ckpt:
                return _ConstantWorkPolicy(np.asarray([0.0, 0.2, 0.0, 0.0], dtype=np.float32))
            return _ConstantWorkPolicy(np.asarray([0.1, 0.0, 0.0, 0.0], dtype=np.float32))

        config = {
            "task": {
                "name": "agx_excavation_teleop",
                "scenario_id": "s0_truck",
                "episode_len": 4000,
            },
            "eval": {
                "save_video": False,
                "results_dir": None,
            },
            "reward": {
                "target_approach_distance_m": 1.25,
            },
            "policy": {
                "class": "hybrid_planner_act",
                "device": "cpu",
                "work_ckpt_path": "runs/ckpts/agx_excavation_act_v1/policy_best.ckpt",
                "work_ckpt_dir": "runs/ckpts/agx_excavation_act_v1",
                "work_low_dim_keys": ["qpos"],
                "transition_ckpt_path": "runs/ckpts/agx_excavation_act_v2_1_multi_raw_transition_qvel_e50/policy_best.ckpt",
                "transition_ckpt_dir": "runs/ckpts/agx_excavation_act_v2_1_multi_raw_transition_qvel_e50",
                "transition_low_dim_keys": ["qpos", "qvel"],
                "planner": {"sequence": ["mid", "mid", "mid"]},
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config["eval"]["results_dir"] = tmpdir
            with (
                patch("testbed.eval.suite.EvalSuite", FakeSuite),
                patch("testbed.eval.metrics.EvalMetrics.append_to_csv"),
                patch(
                    "testbed.policies.act.adapter.ACTAdapter.from_checkpoint",
                    side_effect=_fake_from_checkpoint,
                ),
            ):
                eval_policy(config)

        self.assertEqual(len(captured["from_checkpoint_calls"]), 2)
        suite_policy = captured["suite_kwargs"]["policy"]
        self.assertIsNotNone(suite_policy.transition_policy)

    def test_eval_policy_passes_transition_fallback_settings(self) -> None:
        captured: dict[str, object] = {"from_checkpoint_calls": []}
        fake_metrics = _FakeMetrics()

        class FakeSuite:
            def __init__(self, **kwargs) -> None:
                captured["suite_kwargs"] = kwargs

            def run(self):
                return fake_metrics

        def _fake_from_checkpoint(**kwargs):
            captured["from_checkpoint_calls"].append(kwargs)
            return _ConstantWorkPolicy(np.asarray([0.0, 0.2, 0.0, 0.0], dtype=np.float32))

        config = {
            "task": {
                "name": "agx_excavation_teleop",
                "scenario_id": "s0_truck",
                "episode_len": 4000,
            },
            "eval": {
                "save_video": False,
                "results_dir": None,
            },
            "reward": {
                "target_approach_distance_m": 1.25,
                "dig_area_touch_tolerance_m": 0.05,
                "dig_below_plane_depth_tolerance_m": 0.02,
            },
            "policy": {
                "class": "hybrid_planner_act",
                "device": "cpu",
                "work_ckpt_path": "runs/ckpts/agx_excavation_act_v1/policy_best.ckpt",
                "work_ckpt_dir": "runs/ckpts/agx_excavation_act_v1",
                "work_low_dim_keys": ["qpos"],
                "transition_ckpt_path": "runs/ckpts/agx_excavation_act_v2_1_multi_raw_transition_qvel_e50/policy_best.ckpt",
                "transition_ckpt_dir": "runs/ckpts/agx_excavation_act_v2_1_multi_raw_transition_qvel_e50",
                "transition_low_dim_keys": ["qpos", "qvel"],
                "transition_enable_fallback": True,
                "transition_fallback_local_budget_steps": 180,
                "transition_fallback_no_progress_steps": 120,
                "transition_fallback_progress_mass_kg": 40.0,
                "planner": {"sequence": ["mid", "mid", "mid"]},
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config["eval"]["results_dir"] = tmpdir
            with (
                patch("testbed.eval.suite.EvalSuite", FakeSuite),
                patch("testbed.eval.metrics.EvalMetrics.append_to_csv"),
                patch(
                    "testbed.policies.act.adapter.ACTAdapter.from_checkpoint",
                    side_effect=_fake_from_checkpoint,
                ),
            ):
                eval_policy(config)

        suite_policy = captured["suite_kwargs"]["policy"]
        self.assertTrue(suite_policy.transition_enable_fallback)
        self.assertEqual(suite_policy.transition_fallback_local_budget_steps, 180)
        self.assertEqual(suite_policy.transition_fallback_no_progress_steps, 120)

    def test_eval_suite_collects_hybrid_logs_and_stops_on_target_cycle_gate(self) -> None:
        class FakePolicy:
            def __init__(self) -> None:
                self._t = 0

            def reset(self) -> None:
                self._t = 0

            def predict(self, _obs) -> np.ndarray:
                self._t += 1
                return np.zeros(4, dtype=np.float32)

            def debug_state(self) -> dict[str, object]:
                return {
                    "hybrid_mode": "TRANSITION",
                    "transition_submode": "corridor_align",
                    "planner_cycle_index": 0,
                    "planner_curr_sector_id": 1,
                    "planner_next_sector_id": 1,
                    "transition_timeout": False,
                    "transition_collision_delta": 0,
                    "corridor_align_steps": self._t,
                    "wait_next_dig_steps": 0,
                    "transition_completed": False,
                    "transition_source": "scripted_band_servo",
                }

            def rollout_summary(self) -> dict[str, object]:
                return {
                    "transition_source": "scripted_band_servo",
                    "transition_timeout_count": 0,
                    "transition_collision_rate": 0.0,
                    "avg_corridor_align_steps": 3.0,
                    "avg_wait_next_dig_steps": 0.0,
                    "completed_transition_count": 1,
                }

        class FakeTimeStep:
            def __init__(self, observation, reward: float, info: dict[str, object]) -> None:
                self.observation = observation
                self.reward = reward
                self.info = info

        class FakeEnv:
            dt = 0.02

            def __init__(self) -> None:
                self._index = 0
                self._states = [
                    _make_env_state(),
                    _make_env_state(
                        mass_in_bucket=120.0,
                        excavated_mass=10.0,
                        min_distance_to_dig_area=0.04,
                        bucket_depth=0.03,
                    ),
                    _make_env_state(
                        mass_in_bucket=140.0,
                        excavated_mass=20.0,
                        deposited_mass=12.0,
                        min_distance_to_target=1.0,
                        min_distance_to_dig_area=0.03,
                        bucket_depth=0.04,
                    ),
                    _make_env_state(
                        mass_in_bucket=80.0,
                        deposited_mass=12.0,
                        min_distance_to_target=2.0,
                    ),
                    _make_env_state(
                        mass_in_bucket=80.0,
                        deposited_mass=12.0,
                        min_distance_to_target=2.0,
                    ),
                    _make_env_state(
                        mass_in_bucket=80.0,
                        deposited_mass=12.0,
                        min_distance_to_target=2.0,
                    ),
                ]

            def reset(self, seed=None):
                self._index = 0
                return FakeTimeStep(
                    observation={
                        "qpos": np.asarray([0.5, 0.634, 0.523, 0.690], dtype=np.float32),
                        "qvel": np.zeros(4, dtype=np.float32),
                        "images": {},
                        "env_state": self._states[0],
                        "step_id": 0,
                        "sim_time_ns": 0,
                    },
                    reward=0.0,
                    info={},
                )

            def step(self, action):
                self._index += 1
                env_state = self._states[min(self._index, len(self._states) - 1)]
                reward_phase = "idle"
                successes: list[str] = []
                if self._index == 1:
                    reward_phase = "good_dig_start"
                    successes = ["good_dig_start"]
                elif self._index == 2:
                    reward_phase = "depositing"
                return FakeTimeStep(
                    observation={
                        "qpos": np.asarray([0.5, 0.634, 0.523, 0.690], dtype=np.float32),
                        "qvel": np.zeros(4, dtype=np.float32),
                        "images": {},
                        "env_state": env_state,
                        "step_id": self._index,
                        "sim_time_ns": self._index * 20_000_000,
                    },
                    reward=1.0,
                    info={
                        "sim_time_ns": self._index * 20_000_000,
                        "reward_phase": reward_phase,
                        "task_success": False,
                        "task_step_successes": successes,
                        "task_step_failures": [],
                        "task_metrics": {},
                        "warnings": [],
                    },
                )

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as tmpdir:
            suite = EvalSuite(
                policy=FakePolicy(),
                task_name="agx_excavation_teleop",
                num_rollouts=1,
                save_video=False,
                results_dir=Path(tmpdir) / "results",
                save_rollout_logs=True,
                rollout_log_dir=Path(tmpdir) / "results" / "rollouts",
                target_cycle_gate=1,
                target_cycle_gate_terminal_hold_steps=0,
            )
            suite.task_def = replace(suite.task_def, episode_len=20)
            suite._make_env = lambda _task: FakeEnv()

            metrics = suite.run()

            self.assertIn("transition_timeout_count", metrics.extra)
            self.assertIn("avg_corridor_align_steps", metrics.extra)
            summary_path = Path(tmpdir) / "results" / "rollouts" / "rollout_000_summary.json"
            manifest_path = Path(tmpdir) / "results" / "rollout_manifest.json"
            with open(summary_path) as f:
                summary = json.load(f)
            with open(manifest_path) as f:
                manifest = json.load(f)
            self.assertEqual(summary["rollout_stop_reason"], "target_cycle_gate_reached")
            self.assertEqual(summary["transition_source"], "scripted_band_servo")
            self.assertIn("hybrid_means", manifest)

    def test_eval_suite_target_cycle_gate_can_wait_for_terminal_hold(self) -> None:
        suite = EvalSuite(
            policy=_ConstantWorkPolicy(),
            task_name="agx_excavation_teleop",
            num_rollouts=1,
            save_video=False,
            save_rollout_logs=False,
            target_cycle_gate=1,
            target_cycle_gate_terminal_hold_steps=3,
        )

        reached_step, stop_reason = suite._target_cycle_gate_stop_reason(
            completed_dump_count=0,
            step_index=9,
            gate_reached_step=None,
        )
        self.assertIsNone(reached_step)
        self.assertIsNone(stop_reason)

        reached_step, stop_reason = suite._target_cycle_gate_stop_reason(
            completed_dump_count=1,
            step_index=10,
            gate_reached_step=None,
        )
        self.assertEqual(reached_step, 10)
        self.assertIsNone(stop_reason)

        reached_step, stop_reason = suite._target_cycle_gate_stop_reason(
            completed_dump_count=1,
            step_index=12,
            gate_reached_step=reached_step,
        )
        self.assertEqual(reached_step, 10)
        self.assertEqual(stop_reason, "target_cycle_gate_terminal_hold_reached")


if __name__ == "__main__":
    unittest.main()
