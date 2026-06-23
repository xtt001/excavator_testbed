from __future__ import annotations

from typing import Any

import pytest

from testbed.planner.primitive_action_dispatch import PrimitiveActionDispatchService
from testbed.planner.primitive_adapter_config import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy
from tests.test_primitive_action_dispatch import _ports


def test_enabled_pre_dig_align_config_fails_fast_after_runtime_removal() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "pre_dig_align runtime execution has been removed; "
            "set pre_dig_align.enabled=false"
        ),
    ):
        PrimitivePlannerAdapterConfigNormalizer.normalize(
            PrimitivePlannerAdapterConfigInputs(
                pre_dig_align={"enabled": True},
            )
        )


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


def test_pre_dig_align_skill_has_no_runtime_action_dispatch() -> None:
    events: list[str] = []
    service = PrimitiveActionDispatchService.from_ports(
        _ports(events, skill_name="pre_dig_align")
    )
    obs: dict[str, Any] = {"qpos": [1.0]}

    with pytest.raises(RuntimeError, match="Unknown primitive skill 'pre_dig_align'."):
        service.dispatch_action(obs)
    assert events == []


def test_policy_no_longer_exposes_pre_dig_align_predicate_facades() -> None:
    removed_names = {
        "_should_pre_dig_align_before_dig",
        "_should_pre_dig_align_after_failed_dig",
    }

    assert removed_names.isdisjoint(PrimitivePlannerACTPolicy.__dict__)
