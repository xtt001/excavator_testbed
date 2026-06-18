from __future__ import annotations

import importlib

import pytest

from testbed.planner.planner_backend_config import (
    ACTION_TREE_SHADOW_BACKEND,
    LEGACY_FSM_BACKEND,
    NOT_APPLICABLE_BACKEND,
    apply_planner_backend,
    make_planner_backend,
    normalize_planner_backend,
    planner_backend_from_metadata,
    planner_backend_from_policy_config,
)
from testbed.planner.runtime import LegacyStateMachineBackend, PlannerBackend


def test_planner_backend_policy_config_defaults_to_legacy() -> None:
    assert planner_backend_from_policy_config({}) == LEGACY_FSM_BACKEND


def test_planner_backend_policy_config_uses_canonical_key() -> None:
    config = {"planner_backend": "action_tree"}

    assert planner_backend_from_policy_config(config) == ACTION_TREE_SHADOW_BACKEND


def test_planner_backend_policy_config_rejects_not_applicable() -> None:
    with pytest.raises(ValueError, match="Unsupported planner_backend"):
        planner_backend_from_policy_config({"planner_backend": "not_applicable"})


def test_planner_backend_policy_config_rejects_removed_runner_key() -> None:
    with pytest.raises(ValueError, match="primitive_scheduler_runner.*planner_backend"):
        planner_backend_from_policy_config(
            {"primitive_scheduler_runner": "action_tree_shadow"}
        )


def test_planner_backend_metadata_uses_canonical_key() -> None:
    assert planner_backend_from_metadata({"planner_backend": "legacy_fsm"}) == (
        LEGACY_FSM_BACKEND
    )


def test_planner_backend_metadata_accepts_not_applicable() -> None:
    metadata = {"planner_backend": "not_applicable"}

    assert planner_backend_from_metadata(metadata) == NOT_APPLICABLE_BACKEND


def test_planner_backend_metadata_rejects_removed_runner_key() -> None:
    with pytest.raises(ValueError, match="primitive_scheduler_runner.*planner_backend"):
        planner_backend_from_metadata({"primitive_scheduler_runner": "legacy_fsm"})


def test_planner_backend_error_mentions_canonical_key() -> None:
    with pytest.raises(ValueError, match="Unsupported planner_backend"):
        normalize_planner_backend("not_applicable")


def test_apply_planner_backend_keeps_legacy_without_shadow_runner() -> None:
    class Policy:
        pass

    policy = Policy()

    applied = apply_planner_backend(
        policy=policy,
        policy_class="PRIMITIVE_PLANNER_ACT",
        backend=LEGACY_FSM_BACKEND,
    )

    assert applied == LEGACY_FSM_BACKEND
    assert not hasattr(policy, "_primitive_action_tree_runner")
    assert getattr(policy, "_planner_backend") == LEGACY_FSM_BACKEND


def test_make_planner_backend_defaults_to_legacy_runtime_backend() -> None:
    backend = make_planner_backend()

    assert isinstance(backend, LegacyStateMachineBackend)
    assert isinstance(backend, PlannerBackend)
    assert backend.name == LEGACY_FSM_BACKEND


def test_make_planner_backend_accepts_legacy_aliases() -> None:
    assert make_planner_backend("legacy").name == LEGACY_FSM_BACKEND
    assert make_planner_backend("fsm").name == LEGACY_FSM_BACKEND


def test_make_planner_backend_rejects_action_tree_shadow_runtime_backend() -> None:
    with pytest.raises(ValueError, match="action_tree_shadow.*shadow adapter"):
        make_planner_backend(ACTION_TREE_SHADOW_BACKEND)


def test_make_planner_backend_rejects_behavior_tree_experimental_config() -> None:
    with pytest.raises(ValueError, match="Unsupported planner_backend"):
        make_planner_backend("behavior_tree_experimental")


def test_old_primitive_scheduler_runner_module_is_removed() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("testbed.planner.primitive_scheduler_runner")
