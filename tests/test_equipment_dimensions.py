from __future__ import annotations

import unittest

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.data.v2_1 import GOAL_TOKEN_DIM
from testbed.policies.act.detr.models.detr_vae import _resolve_action_dim
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM
from testbed.runtime._eval import _resolve_low_dim_state_dim as resolve_eval_state_dim
from testbed.runtime._train import _resolve_low_dim_state_dim as resolve_train_state_dim


class TestEquipmentDimensions(unittest.TestCase):
    def test_yulong_uses_four_axis_agx_dimensions(self) -> None:
        self.assertEqual(_resolve_action_dim("yulong"), 4)
        self.assertEqual(resolve_train_state_dim(["qpos", "qvel"], "yulong"), 8)
        self.assertEqual(resolve_eval_state_dim(["qpos", "qvel"], "yulong"), 8)

    def test_train_and_eval_cover_supported_yulong_low_dim_keys(self) -> None:
        cases = [
            (["qpos"], 4),
            (["qvel"], 4),
            (["qpos", "qvel"], 8),
            (["qpos", "qvel", "goal_tokens"], 8 + GOAL_TOKEN_DIM),
            (
                ["qpos", "qvel", "cell_entry_tokens"],
                8 + CELL_ENTRY_TOKEN_DIM,
            ),
            (["qpos", "qvel", "dig_cut_tokens"], 8 + DIG_CUT_TOKEN_DIM),
            (
                ["qpos", "qvel", "dig_depth_profile_tokens_v1"],
                8 + DIG_DEPTH_PROFILE_TOKEN_DIM,
            ),
            (
                ["qpos", "qvel", "return_target_tokens"],
                8 + RETURN_TARGET_TOKEN_DIM,
            ),
            (
                ["qpos", "qvel", "return_relocate_tokens_v1"],
                8 + RETURN_TARGET_TOKEN_DIM,
            ),
            (
                ["qpos", "qvel", "return_start_envelope_tokens_v1"],
                8 + RETURN_START_ENVELOPE_TOKEN_DIM,
            ),
            (
                [
                    "qpos",
                    "qvel",
                    "dig_cut_tokens",
                    "dig_depth_profile_tokens_v1",
                ],
                8 + DIG_CUT_TOKEN_DIM + DIG_DEPTH_PROFILE_TOKEN_DIM,
            ),
        ]

        for low_dim_keys, expected_dim in cases:
            with self.subTest(low_dim_keys=low_dim_keys):
                self.assertEqual(
                    resolve_train_state_dim(low_dim_keys, "yulong"),
                    expected_dim,
                )
                self.assertEqual(
                    resolve_eval_state_dim(low_dim_keys, "yulong"),
                    expected_dim,
                )

    def test_train_and_eval_reject_unsupported_low_dim_keys(self) -> None:
        for resolver in (resolve_train_state_dim, resolve_eval_state_dim):
            with self.subTest(resolver=resolver.__module__):
                with self.assertRaises(KeyError):
                    resolver(["qpos", "unknown_tokens"], "yulong")

    def test_yulong_cell_entry_state_dim_uses_token_source_of_truth(self) -> None:
        self.assertEqual(
            resolve_train_state_dim(
                ["qpos", "qvel", "cell_entry_tokens"], "yulong"
            ),
            8 + CELL_ENTRY_TOKEN_DIM,
        )
        self.assertEqual(
            resolve_eval_state_dim(
                ["qpos", "qvel", "cell_entry_tokens"], "yulong"
            ),
            8 + CELL_ENTRY_TOKEN_DIM,
        )
