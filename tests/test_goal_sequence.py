from __future__ import annotations

import numpy as np
import pytest

from testbed.data.v2_1 import build_goal_tokens
from testbed.eval.suite import EvalSuite, LIVE_GOAL_SECTOR_IDS
from testbed.planner import fixed_sequence_planner, primitive_config, types
from testbed.planner.goal_sequence import (
    GOAL_SEQUENCE_CONFIG_KEYS,
    GOAL_SECTOR_ID_TO_NAME,
    GOAL_SECTOR_NAME_TO_ID,
    GoalSequenceConfig,
    GoalSequenceFacts,
    GoalSequencePlannerConfig,
    GoalSequenceService,
    build_goal_sequence_planner_config,
    build_goal_sequence_planner_config_from_mapping,
    normalize_goal_sequence,
)


def test_goal_sector_mapping_is_shared_source_of_truth() -> None:
    assert GOAL_SECTOR_NAME_TO_ID == {"left": 0, "mid": 1, "right": 2}
    assert GOAL_SECTOR_ID_TO_NAME == {0: "left", 1: "mid", 2: "right"}
    assert primitive_config.PRIMITIVE_GOAL_SECTOR_IDS is GOAL_SECTOR_NAME_TO_ID
    assert fixed_sequence_planner.SECTOR_NAME_TO_ID is GOAL_SECTOR_NAME_TO_ID
    assert types.SECTOR_NAME_TO_ID is GOAL_SECTOR_NAME_TO_ID
    assert LIVE_GOAL_SECTOR_IDS is GOAL_SECTOR_NAME_TO_ID


def test_normalize_goal_sequence_preserves_primitive_error_text() -> None:
    assert normalize_goal_sequence(None) == ()
    assert normalize_goal_sequence(["left", "mid", "right"]) == (0, 1, 2)
    assert normalize_goal_sequence([0, 2]) == (0, 2)

    with pytest.raises(
        ValueError,
        match="Unknown primitive goal sector 'front'. Expected left, mid, or right.",
    ):
        normalize_goal_sequence(["front"])
    with pytest.raises(
        ValueError,
        match="Primitive goal sector id must be 0, 1, or 2, got 3.",
    ):
        normalize_goal_sequence([3])


def test_goal_sequence_planner_config_coerces_legacy_init_fields() -> None:
    config = build_goal_sequence_planner_config(
        goal_sequence=["right", "left"],
        goal_scenario_id=123,
        goal_depth_norm="0.75",
        goal_dump_target_norm=2,
    )

    assert config == GoalSequencePlannerConfig(
        goal_sequence=(2, 0),
        goal_scenario_id="123",
        goal_depth_norm=0.75,
        goal_dump_target_norm=2.0,
    )
    assert config.planner_items() == (
        ("goal_sequence", (2, 0)),
        ("goal_scenario_id", "123"),
        ("goal_depth_norm", 0.75),
        ("goal_dump_target_norm", 2.0),
    )


def test_goal_sequence_planner_config_from_mapping_key_boundary() -> None:
    values = {
        "goal_sequence": [1, 2],
        "goal_scenario_id": "s1",
        "goal_depth_norm": 0.5,
        "goal_dump_target_norm": "1.5",
        "ignored": object(),
    }

    assert GOAL_SEQUENCE_CONFIG_KEYS == (
        "goal_sequence",
        "goal_scenario_id",
        "goal_depth_norm",
        "goal_dump_target_norm",
    )
    expected = GoalSequencePlannerConfig(
        goal_sequence=(1, 2),
        goal_scenario_id="s1",
        goal_depth_norm=0.5,
        goal_dump_target_norm=1.5,
    )
    assert build_goal_sequence_planner_config_from_mapping(values) == expected


def test_eval_live_goal_sequence_preserves_live_error_text() -> None:
    assert EvalSuite._normalize_live_goal_sequence(["left", "right"]) == (0, 2)

    with pytest.raises(
        ValueError,
        match="Unknown live goal sector 'front'. Expected left, mid, or right.",
    ):
        EvalSuite._normalize_live_goal_sequence(["front"])
    with pytest.raises(
        ValueError,
        match="Live goal sector id must be 0, 1, or 2, got 3.",
    ):
        EvalSuite._normalize_live_goal_sequence([3])


def test_goal_sequence_service_builds_legacy_goal_tokens() -> None:
    service = GoalSequenceService()
    sequence = normalize_goal_sequence(["mid", "left", "right"])

    result = service.tokens_for_cycle(
        sequence=sequence,
        facts=GoalSequenceFacts(cycle_index=0),
        config=GoalSequenceConfig(
            scenario_id="s0_truck",
            depth_norm=1.0,
            dump_target_norm=1.0,
        ),
    )

    assert result.curr_sector_id == 1
    assert result.next_sector_id == 0
    assert result.tokens is not None
    np.testing.assert_allclose(
        result.tokens,
        build_goal_tokens(
            "s0_truck",
            curr_sector_id=1,
            curr_cut_depth_norm=1.0,
            next_sector_id=0,
            next_cut_depth_norm=1.0,
            dst_target_norm=1.0,
            has_lookahead=True,
        ),
    )


def test_goal_sequence_service_saturates_current_and_drops_missing_lookahead() -> None:
    service = GoalSequenceService()
    sequence = normalize_goal_sequence(["mid", "left"])

    assert service.sector_id_for_cycle(sequence=sequence, cycle_index=-1) == 1
    assert service.sector_id_for_cycle(sequence=sequence, cycle_index=99) == 0
    assert service.next_sector_id(sequence=sequence, cycle_index=1) == -1

    result = service.tokens_for_cycle(
        sequence=sequence,
        facts=GoalSequenceFacts(cycle_index=1),
        config=GoalSequenceConfig(
            scenario_id="s0_truck",
            depth_norm=1.0,
            dump_target_norm=1.0,
        ),
    )

    assert result.curr_sector_id == 0
    assert result.next_sector_id == -1
    assert result.tokens is not None
    np.testing.assert_allclose(result.tokens[4:7], np.zeros(3, dtype=np.float32))
