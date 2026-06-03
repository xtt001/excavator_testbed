"""ACT trainer variant that consumes graph observations."""

from __future__ import annotations

import torch

from testbed.policies.act.trainer import ACTTrainer
from testbed.policies.act_graph.adapter import ACTGraphAdapter


class ACTGraphTrainer(ACTTrainer):
    """Offline trainer for the graph-conditioned ACT branch."""

    adapter_cls = ACTGraphAdapter

    @staticmethod
    def _forward(
        data,
        adapter: ACTGraphAdapter,
        amp_enabled: bool = False,
        amp_dtype: torch.dtype | None = None,
    ) -> dict:
        image_data, proprio_data, graph_data, action_data, is_pad = data
        image_data = image_data.to(adapter.device)
        proprio_data = proprio_data.to(adapter.device)
        action_data = action_data.to(adapter.device)
        is_pad = is_pad.to(adapter.device)
        with ACTTrainer._autocast_context(adapter.device, amp_enabled, amp_dtype):
            return adapter.forward_loss(
                proprio_data,
                graph_data,
                image_data,
                action_data,
                is_pad,
            )
