from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from testbed.planner.boundary_detector import build_boundary_detector_from_config
from testbed.planner.corridor_servo import (
    TransitionController,
    build_default_entry_corridor_bands,
)
from testbed.planner.rule_planner import RuleTaskPlanner
from testbed.planner.scenario_manifest import resolve_scenario_manifest
from testbed.planner.types import (
    BELIEF_STATE_ACTIVE,
    BELIEF_STATE_CANDIDATE,
    CycleSummary,
)
from testbed.policies.hybrid.adapter import HybridPlannerACTPolicy
from testbed.runtime._eval import eval_policy


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


def _make_env_state(
    *,
    mass_in_bucket: float = 0.0,
    excavated_mass: float = 0.0,
    mass_in_target_box: float = 0.0,
    deposited_mass: float = 0.0,
    min_distance_to_target: float = 2.0,
    collision_count: float = 0.0,
    target_contact_force_n: float = 0.0,
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
            target_contact_force_n,
            min_distance_to_dig_area,
            bucket_depth,
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


class Stage4RulePlannerTests(unittest.TestCase):
    def test_reset_builds_initial_mid_active_belief(self) -> None:
        planner = RuleTaskPlanner(manifest=resolve_scenario_manifest("s0_truck"))
        planner.reset("s0_truck")
        belief = planner.current_belief()
        self.assertEqual(belief.scenario_id, "s0_truck")
        self.assertEqual(len(belief.sectors), 3)
        self.assertEqual(belief.sectors[1].state, BELIEF_STATE_ACTIVE)
        self.assertEqual(belief.sectors[0].state, BELIEF_STATE_CANDIDATE)
        self.assertEqual(belief.sectors[2].state, BELIEF_STATE_CANDIDATE)

    def test_replan_updates_belief_and_prefers_frontier_sector(self) -> None:
        planner = RuleTaskPlanner(manifest=resolve_scenario_manifest("s0_truck"))
        planner.reset("s0_truck")
        last_cycle = CycleSummary(
            cycle_id=0,
            curr_src_sector_id=1,
            next_src_sector_id=1,
            fill_peak_kg=320.0,
            deposit_delta_kg=340.0,
            peak_bucket_depth_m=0.08,
            collision_count_delta=0,
            target_contact_max_force_n=0.0,
            qualified_dig=True,
            cycle_success=True,
        )
        next_goal = planner.replan_at_cycle_boundary(last_cycle)
        belief = planner.current_belief()
        self.assertGreaterEqual(belief.sectors[1].achieved_depth_proxy_m, 0.08)
        self.assertLessEqual(belief.sectors[1].remaining_depth_proxy_m, 0.01)
        self.assertEqual(next_goal.curr_src_sector_id, 0)
        self.assertEqual(next_goal.next_entry_corridor_id, 0)
        self.assertEqual(len(planner.planner_trace()["replans"]), 1)


class Stage4HybridPolicyTests(unittest.TestCase):
    def test_hybrid_policy_triggers_rule_replan_after_transition(self) -> None:
        policy = HybridPlannerACTPolicy(
            work_policy=_ConstantWorkPolicy(),
            planner=RuleTaskPlanner(manifest=resolve_scenario_manifest("s0_truck")),
            transition_controller=TransitionController(
                bands=build_default_entry_corridor_bands(),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg={"target_approach_distance_m": 1.25},
                success_cfg={"residual_bucket_mass_thresh": 100.0},
                pause_action_eps=0.05,
            ),
            scenario_id="s0_truck",
        )
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
                    target_contact_force_n=12.0,
                ),
                reward_phase="depositing",
            ),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=80.0,
                    deposited_mass=12.0,
                    min_distance_to_target=2.0,
                ),
            ),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=80.0,
                    deposited_mass=12.0,
                    min_distance_to_target=2.0,
                ),
            ),
            _make_obs(
                env_state=_make_env_state(
                    mass_in_bucket=80.0,
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

        for obs in seq:
            policy.predict(obs)
        state = policy.debug_state()
        self.assertGreaterEqual(policy.rollout_summary()["planner_replan_count"], 1)
        self.assertEqual(state["planner_next_sector_id"], 0)
        self.assertEqual(state["planner_current_depth_class"], 1)
        self.assertEqual(state["planner_next_depth_class"], 2)
        self.assertGreaterEqual(len(policy.planner_trace().get("replans", [])), 1)


class Stage4EvalIntegrationTests(unittest.TestCase):
    def test_eval_policy_builds_rule_planner_hybrid(self) -> None:
        captured: dict[str, object] = {}

        class FakeSuite:
            def __init__(self, **kwargs) -> None:
                captured["suite_kwargs"] = kwargs

            def run(self):
                class _Metrics:
                    def to_json(self, _path):
                        return None

                return _Metrics()

        def _fake_from_checkpoint(**_kwargs):
            return _ConstantWorkPolicy()

        config = {
            "task": {
                "name": "agx_excavation_teleop",
                "scenario_id": "s0_truck",
                "episode_len": 4000,
            },
            "eval": {
                "save_video": False,
                "results_dir": None,
                "target_cycle_gate": 2,
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
                "planner": {"kind": "rule", "manifest_id": "s0_truck"},
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
        self.assertEqual(type(suite_policy).__name__, "HybridPlannerACTPolicy")
        self.assertEqual(type(suite_policy.planner).__name__, "RuleTaskPlanner")


if __name__ == "__main__":
    unittest.main()
