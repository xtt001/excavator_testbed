from __future__ import annotations

import json

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import DIG_CUT_TOKEN_DIM
from testbed.planner.primitive_config import (
    align_vector,
    load_dig_cut_prior,
    normalize_failed_dig_replan_skill,
    normalize_goal_sequence,
    normalize_plane_depth_mode,
    optional_align_vector,
    optional_float,
    validate_dig_cut_planner_config,
)


def test_normalize_plane_depth_mode_aliases_and_errors() -> None:
    assert normalize_plane_depth_mode(None) == "range"
    assert normalize_plane_depth_mode("legacy") == "range"
    assert normalize_plane_depth_mode("p05-p95") == "range"
    assert normalize_plane_depth_mode("median_floor") == "p50_floor"
    assert normalize_plane_depth_mode("target-floor") == "p50_floor"
    assert normalize_plane_depth_mode("median_band") == "target_band"

    with pytest.raises(
        ValueError,
        match="return_to_dig_start_envelope_plane_depth_mode must be one of",
    ):
        normalize_plane_depth_mode("unknown")


def test_normalize_failed_dig_replan_skill_aliases_and_errors() -> None:
    assert normalize_failed_dig_replan_skill(None) == "dig"
    assert normalize_failed_dig_replan_skill("same-dig") == "dig"
    assert normalize_failed_dig_replan_skill("new_dig") == "dig"
    assert normalize_failed_dig_replan_skill("fail_fast") == "stop"
    assert normalize_failed_dig_replan_skill("terminal-stop") == "stop"

    with pytest.raises(
        ValueError,
        match="dig_failed_replan_next_skill must be 'dig' or 'stop'",
    ):
        normalize_failed_dig_replan_skill("carry")


def test_optional_and_align_vector_helpers_match_planner_facade_semantics() -> None:
    np.testing.assert_allclose(
        align_vector(None, default=[1.0, 2.0, 3.0, 4.0], action_dim=4),
        np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32),
    )
    np.testing.assert_allclose(
        align_vector([0.0, 0.1, 0.2, 0.3], default=[1.0, 2.0, 3.0, 4.0], action_dim=4),
        np.asarray([0.0, 0.1, 0.2, 0.3], dtype=np.float32),
    )
    assert optional_align_vector(None, action_dim=4) is None
    assert optional_align_vector("none", action_dim=4) is None
    np.testing.assert_allclose(
        optional_align_vector("0, 1, 2, 3", action_dim=4),
        np.asarray([0.0, 1.0, 2.0, 3.0], dtype=np.float32),
    )
    assert optional_float(None) is None
    assert optional_float("null") is None
    assert optional_float("1.25") == pytest.approx(1.25)


def test_load_dig_cut_prior_validates_token_order(tmp_path) -> None:
    valid_path = tmp_path / "prior.json"
    valid_path.write_text(
        json.dumps({"prior_id": "unit", "token_order": list(range(DIG_CUT_TOKEN_DIM))}),
        encoding="utf-8",
    )

    assert load_dig_cut_prior("") == {}
    assert load_dig_cut_prior(str(valid_path))["prior_id"] == "unit"

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps({"token_order": [0]}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid token_order length"):
        load_dig_cut_prior(str(invalid_path))


def test_validate_dig_cut_planner_config_preserves_error_cases() -> None:
    _validate()
    _validate(dig_cut_planner_enabled=False, dig_cut_planner_mode="unsupported")

    with pytest.raises(ValueError, match="Unsupported dig_cut_planner mode"):
        _validate(dig_cut_planner_mode="unsupported")
    with pytest.raises(ValueError, match="operator_prior dig_cut_planner requires prior_path"):
        _validate(dig_cut_planner_mode="operator_prior", dig_cut_prior_path="")
    with pytest.raises(ValueError, match="Unsupported coverage.candidate_layout"):
        _validate(coverage_candidate_layout="unknown")
    with pytest.raises(ValueError, match="Unsupported dig_depth_profile.source"):
        _validate(dig_depth_profile_source="unknown")
    with pytest.raises(
        ValueError,
        match="dig_depth_profile.source='prior_profile' requires prior_path",
    ):
        _validate(dig_depth_profile_source="prior_profile", dig_cut_prior_path="")
    with pytest.raises(
        ValueError,
        match="requires dig_depth_profile_cells in the dig cut prior",
    ):
        _validate(dig_depth_profile_source="prior_profile", dig_cut_prior={})
    with pytest.raises(
        ValueError,
        match="dig_depth_profile.required=true must set allow_live_fallback=false",
    ):
        _validate(
            dig_depth_profile_source="prior_profile",
            dig_cut_prior={"dig_depth_profile_cells": []},
            dig_depth_profile_required=True,
            dig_depth_profile_allow_live_fallback=True,
        )


def test_normalize_goal_sequence_accepts_names_and_ids() -> None:
    assert normalize_goal_sequence(None) == ()
    assert normalize_goal_sequence(["left", "mid", "right"]) == (0, 1, 2)
    assert normalize_goal_sequence([0, 2]) == (0, 2)

    with pytest.raises(ValueError, match="Unknown primitive goal sector"):
        normalize_goal_sequence(["front"])
    with pytest.raises(ValueError, match="Primitive goal sector id must be 0, 1, or 2"):
        normalize_goal_sequence([3])


def _validate(**overrides: object) -> None:
    defaults = {
        "dig_cut_planner_enabled": True,
        "dig_cut_planner_mode": "conservative_pose",
        "dig_cut_prior_path": "prior.json",
        "coverage_candidate_layout": "percentile_grid",
        "dig_depth_profile_source": "live_plan",
        "dig_cut_prior": {"dig_depth_profile_cells": []},
        "dig_depth_profile_required": False,
        "dig_depth_profile_allow_live_fallback": False,
    }
    defaults.update(overrides)
    validate_dig_cut_planner_config(**defaults)
