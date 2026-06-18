from __future__ import annotations

import unittest

from testbed.policies.act.detr.models.detr_vae import _resolve_action_dim
from testbed.runtime._eval import _resolve_low_dim_state_dim as resolve_eval_state_dim
from testbed.runtime._train import _resolve_low_dim_state_dim as resolve_train_state_dim


class TestEquipmentDimensions(unittest.TestCase):
    def test_yulong_uses_four_axis_agx_dimensions(self) -> None:
        self.assertEqual(_resolve_action_dim("yulong"), 4)
        self.assertEqual(resolve_train_state_dim(["qpos", "qvel"], "yulong"), 8)
        self.assertEqual(resolve_eval_state_dim(["qpos", "qvel"], "yulong"), 8)
        self.assertEqual(
            resolve_train_state_dim(
                ["qpos", "qvel", "cell_entry_tokens"], "yulong"
            ),
            18,
        )
        self.assertEqual(
            resolve_eval_state_dim(
                ["qpos", "qvel", "cell_entry_tokens"], "yulong"
            ),
            18,
        )
