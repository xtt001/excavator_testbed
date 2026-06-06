from __future__ import annotations

import numpy as np

from testbed.contracts.low_dim import CELL_ENTRY_TOKEN_KEY, GOAL_TOKEN_KEY
from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_KEY,
    DIG_DEPTH_PROFILE_TOKEN_KEY,
    RETURN_RELOCATE_TOKEN_KEY,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_TARGET_TOKEN_KEY,
)
from testbed.planner.policy_observation import (
    DIG_CONDITIONING_TOKEN_GATE_FACT_FIELDS,
    POLICY_OBSERVATION_REQUEST_FACT_FIELDS,
    DigConditioningObservationTokenGateFacts,
    PolicyObservationAssembler,
    PolicyObservationRequestConfig,
    PolicyObservationRequestFacts,
    PolicyObservationTokens,
    build_dig_conditioning_token_gate_facts_from_mapping,
    build_policy_observation_request_facts_from_mapping,
)


def test_no_tokens_returns_original_observation_without_injection_flags() -> None:
    obs = {"qpos": np.zeros(4, dtype=np.float32)}

    assembly = PolicyObservationAssembler().assemble(obs, PolicyObservationTokens())

    assert assembly.obs is obs
    assert not assembly.cell_entry_token_injected
    assert not assembly.dig_cut_token_injected
    assert not assembly.dig_depth_profile_token_injected
    assert not assembly.return_target_token_injected
    assert not assembly.return_relocate_token_injected
    assert not assembly.return_start_envelope_token_injected


def test_goal_only_token_copies_observation_without_debug_injection_flags() -> None:
    obs = {"qpos": np.zeros(4, dtype=np.float32)}
    goal_tokens = np.arange(10, dtype=np.float32)

    assembly = PolicyObservationAssembler().assemble(
        obs,
        PolicyObservationTokens(goal_tokens=goal_tokens),
    )

    assert assembly.obs is not obs
    assert GOAL_TOKEN_KEY not in obs
    assert assembly.obs[GOAL_TOKEN_KEY] is goal_tokens
    assert not assembly.cell_entry_token_injected
    assert not assembly.dig_cut_token_injected
    assert not assembly.dig_depth_profile_token_injected
    assert not assembly.return_target_token_injected
    assert not assembly.return_relocate_token_injected
    assert not assembly.return_start_envelope_token_injected


def test_all_policy_tokens_are_merged_with_matching_injection_flags() -> None:
    obs = {"qpos": np.zeros(4, dtype=np.float32)}
    tokens = PolicyObservationTokens(
        goal_tokens=np.full(10, 1.0, dtype=np.float32),
        cell_entry_tokens=np.full(10, 2.0, dtype=np.float32),
        dig_cut_tokens=np.full(10, 3.0, dtype=np.float32),
        dig_depth_profile_tokens=np.full(12, 4.0, dtype=np.float32),
        return_target_tokens=np.full(10, 5.0, dtype=np.float32),
        return_relocate_tokens=np.full(10, 6.0, dtype=np.float32),
        return_start_envelope_tokens=np.full(18, 7.0, dtype=np.float32),
    )

    assembly = PolicyObservationAssembler().assemble(obs, tokens)

    assert assembly.obs is not obs
    assert set(obs) == {"qpos"}
    assert assembly.obs[GOAL_TOKEN_KEY] is tokens.goal_tokens
    assert assembly.obs[CELL_ENTRY_TOKEN_KEY] is tokens.cell_entry_tokens
    assert assembly.obs[DIG_CUT_TOKEN_KEY] is tokens.dig_cut_tokens
    assert assembly.obs[DIG_DEPTH_PROFILE_TOKEN_KEY] is tokens.dig_depth_profile_tokens
    assert assembly.obs[RETURN_TARGET_TOKEN_KEY] is tokens.return_target_tokens
    assert assembly.obs[RETURN_RELOCATE_TOKEN_KEY] is tokens.return_relocate_tokens
    assert (
        assembly.obs[RETURN_START_ENVELOPE_TOKEN_KEY]
        is tokens.return_start_envelope_tokens
    )
    assert assembly.cell_entry_token_injected
    assert assembly.dig_cut_token_injected
    assert assembly.dig_depth_profile_token_injected
    assert assembly.return_target_token_injected
    assert assembly.return_relocate_token_injected
    assert assembly.return_start_envelope_token_injected


def test_token_request_enables_dig_path_tokens_only_for_dig_skill() -> None:
    request = PolicyObservationAssembler().token_request(
        PolicyObservationRequestFacts(
            active_skill="dig",
            cell_entry_enabled=True,
            dig_cut_planner_enabled=True,
            return_target_planner_enabled=True,
        )
    )

    assert request.goal_tokens
    assert request.cell_entry_tokens
    assert request.dig_cut_tokens
    assert request.dig_depth_profile_tokens
    assert not request.return_target_tokens
    assert not request.return_relocate_tokens
    assert not request.return_start_envelope_tokens


def test_request_facts_mapping_preserves_planner_field_projection() -> None:
    bootstrap_policy = object()
    values = {
        "active_skill": "dig",
        "cell_entry_enabled": 1,
        "dig_cut_planner_enabled": 1,
        "coverage_terminal_stop_requested": 0,
        "bootstrap_policy": bootstrap_policy,
        "return_target_planner_enabled": 1,
        "ignored": object(),
    }

    facts = build_policy_observation_request_facts_from_mapping(values)

    assert {key for key, _ in POLICY_OBSERVATION_REQUEST_FACT_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert facts.active_skill == "dig"
    assert facts.cell_entry_enabled is True
    assert facts.dig_cut_planner_enabled is True
    assert facts.coverage_terminal_stop_requested is False
    assert facts.bootstrap_policy_present is True
    assert facts.return_target_planner_enabled is True
    assert not build_policy_observation_request_facts_from_mapping(
        {**values, "bootstrap_policy": None}
    ).bootstrap_policy_present


def test_token_request_from_mapping_matches_fact_request_gate() -> None:
    bootstrap_policy = object()
    values = {
        "active_skill": "bootstrap",
        "cell_entry_enabled": 1,
        "dig_cut_planner_enabled": 1,
        "coverage_terminal_stop_requested": 0,
        "bootstrap_policy": bootstrap_policy,
        "return_target_planner_enabled": 1,
    }
    config = PolicyObservationRequestConfig(
        dig_skill_name="dig",
        return_skill_name="return",
        bootstrap_skill_name="bootstrap",
    )
    assembler = PolicyObservationAssembler()

    request = assembler.token_request_from_mapping(values, config)
    expected = assembler.token_request(
        build_policy_observation_request_facts_from_mapping(values),
        config,
    )

    assert request == expected


def test_token_request_enables_return_conditioning_only_for_return_skill() -> None:
    request = PolicyObservationAssembler().token_request(
        PolicyObservationRequestFacts(
            active_skill="return",
            cell_entry_enabled=True,
            dig_cut_planner_enabled=True,
            return_target_planner_enabled=True,
        )
    )

    assert request.goal_tokens
    assert not request.cell_entry_tokens
    assert not request.dig_cut_tokens
    assert not request.dig_depth_profile_tokens
    assert request.return_target_tokens
    assert request.return_relocate_tokens
    assert request.return_start_envelope_tokens


def test_token_request_allows_bootstrap_dig_cut_only_when_policy_exists() -> None:
    assembler = PolicyObservationAssembler()

    absent = assembler.token_request(
        PolicyObservationRequestFacts(
            active_skill="bootstrap",
            dig_cut_planner_enabled=True,
            bootstrap_policy_present=False,
        )
    )
    present = assembler.token_request(
        PolicyObservationRequestFacts(
            active_skill="bootstrap",
            dig_cut_planner_enabled=True,
            bootstrap_policy_present=True,
        )
    )

    assert absent.goal_tokens
    assert not absent.dig_cut_tokens
    assert not absent.dig_depth_profile_tokens
    assert present.goal_tokens
    assert present.dig_cut_tokens
    assert present.dig_depth_profile_tokens


def test_token_request_terminal_stop_reuses_dig_tokens_only_for_dig_skill() -> None:
    assembler = PolicyObservationAssembler()

    dig = assembler.token_request(
        PolicyObservationRequestFacts(
            active_skill="dig",
            dig_cut_planner_enabled=True,
            coverage_terminal_stop_requested=True,
            bootstrap_policy_present=True,
        )
    )
    bootstrap = assembler.token_request(
        PolicyObservationRequestFacts(
            active_skill="bootstrap",
            dig_cut_planner_enabled=True,
            coverage_terminal_stop_requested=True,
            bootstrap_policy_present=True,
        )
    )

    assert dig.dig_cut_tokens
    assert dig.dig_depth_profile_tokens
    assert not bootstrap.dig_cut_tokens
    assert not bootstrap.dig_depth_profile_tokens


def test_dig_conditioning_token_gate_preserves_terminal_stop_behavior() -> None:
    assembler = PolicyObservationAssembler()

    disabled = assembler.dig_conditioning_token_gate(
        DigConditioningObservationTokenGateFacts(
            token_requested=False,
            active_skill="dig",
            coverage_terminal_stop_requested=True,
        )
    )
    terminal_dig = assembler.dig_conditioning_token_gate(
        DigConditioningObservationTokenGateFacts(
            token_requested=True,
            active_skill="dig",
            coverage_terminal_stop_requested=True,
        )
    )
    terminal_return = assembler.dig_conditioning_token_gate(
        DigConditioningObservationTokenGateFacts(
            token_requested=True,
            active_skill="return",
            coverage_terminal_stop_requested=True,
        )
    )
    normal = assembler.dig_conditioning_token_gate(
        DigConditioningObservationTokenGateFacts(
            token_requested=True,
            active_skill="bootstrap",
            coverage_terminal_stop_requested=False,
        )
    )

    assert not disabled.return_token
    assert not disabled.should_build_plan
    assert terminal_dig.return_token
    assert not terminal_dig.should_build_plan
    assert not terminal_return.return_token
    assert not terminal_return.should_build_plan
    assert normal.return_token
    assert normal.should_build_plan


def test_dig_conditioning_token_gate_facts_mapping_preserves_projection() -> None:
    values = {
        "active_skill": 123,
        "coverage_terminal_stop_requested": 1,
        "ignored": object(),
    }

    facts = build_dig_conditioning_token_gate_facts_from_mapping(
        values,
        token_requested=np.int64(0),
    )

    assert {key for key, _ in DIG_CONDITIONING_TOKEN_GATE_FACT_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert facts.token_requested is False
    assert facts.active_skill == "123"
    assert facts.coverage_terminal_stop_requested is True


def test_dig_conditioning_token_gate_from_mapping_matches_fact_gate() -> None:
    assembler = PolicyObservationAssembler()
    values = {
        "active_skill": "return",
        "coverage_terminal_stop_requested": 1,
        "ignored": object(),
    }

    decision = assembler.dig_conditioning_token_gate_from_mapping(
        values,
        token_requested=True,
        config=PolicyObservationRequestConfig(dig_skill_name="dig"),
    )
    expected = assembler.dig_conditioning_token_gate(
        build_dig_conditioning_token_gate_facts_from_mapping(
            values,
            token_requested=True,
        ),
        PolicyObservationRequestConfig(dig_skill_name="dig"),
    )

    assert {key for key, _ in DIG_CONDITIONING_TOKEN_GATE_FACT_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert decision == expected
    assert not decision.return_token
    assert not decision.should_build_plan
