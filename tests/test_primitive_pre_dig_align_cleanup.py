from __future__ import annotations

from typing import Any

from testbed.planner.primitive.config.adapter import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
)
from testbed.planner.primitive.execution.action_dispatch import (
    PrimitiveActionDispatchService,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy
from tests.test_primitive_action_dispatch import _ports


def test_enabled_pre_dig_align_config_is_opt_in_runtime_configuration() -> None:
    state = PrimitivePlannerAdapterConfigNormalizer.normalize(
        PrimitivePlannerAdapterConfigInputs(
            pre_dig_align={
                "enabled": True,
                "controlled_dims": [1, 0, 1, 0],
                "bucket_target_qpos": -0.25,
            },
        )
    )
    updates = state.as_policy_field_updates()

    assert updates["pre_dig_align_cfg"]["enabled"] is True
    assert updates["pre_dig_align_enabled"] is True
    assert updates["pre_dig_align_controlled_dims"].tolist() == [
        True,
        False,
        True,
        False,
    ]
    assert updates["pre_dig_align_bucket_target_qpos"] == -0.25


def test_disabled_pre_dig_align_config_keeps_public_report_schema_inputs() -> None:
    state = PrimitivePlannerAdapterConfigNormalizer.normalize(
        PrimitivePlannerAdapterConfigInputs(
            pre_dig_align={
                "enabled": False,
                "controlled_dims": [1, 0, 1, 0],
                "bucket_target_qpos": -0.25,
            },
        )
    )
    updates = state.as_policy_field_updates()

    assert updates["pre_dig_align_cfg"]["enabled"] is False
    assert updates["pre_dig_align_enabled"] is False
    assert updates["pre_dig_align_controlled_dims"].tolist() == [
        True,
        False,
        True,
        False,
    ]
    assert updates["pre_dig_align_bucket_target_qpos"] == -0.25


def test_pre_dig_align_skill_dispatches_runtime_action_without_policy_lookup() -> None:
    events: list[str] = []
    service = PrimitiveActionDispatchService.from_ports(
        _ports(events, skill_name="pre_dig_align")
    )
    obs: dict[str, Any] = {"qpos": [1.0]}

    action = service.dispatch_action(obs)

    assert action.tolist() == [4.0, 3.0, 2.0, 1.0]
    assert events == ["pre_dig_align_action"]


def test_policy_no_longer_exposes_pre_dig_align_predicate_facades() -> None:
    removed_names = {
        "_should_pre_dig_align_before_dig",
        "_should_pre_dig_align_after_failed_dig",
    }

    assert removed_names.isdisjoint(PrimitivePlannerACTPolicy.__dict__)
