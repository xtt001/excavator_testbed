from __future__ import annotations

import inspect
import json
from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_DIM
import testbed.planner.primitive.config.adapter as adapter_config
from testbed.planner.primitive.config.adapter import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
    PrimitivePlannerAdapterConfigState,
)
from testbed.planner.primitive.decision.backends.legacy_capability_provider import (
    PrimitiveFSMCapabilityProviderConfig,
)
from testbed.planner.primitive.effects.return_handoff import (
    ReturnHandoffReadinessConfig,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


_POLICY_HELPER_FACADE_NAMES = {
    "_scripted_bootstrap_target_reached",
    "_align_vector",
    "_optional_align_vector",
    "_optional_float",
    "_validate_dig_cut_planner_config",
    "_load_dig_cut_prior",
    "_raw_fields_in_prior_range",
    "_normalize_plane_depth_mode",
    "_normalize_failed_dig_replan_skill",
    "_coverage_candidate_builder",
    "_normalize_goal_sequence",
    "_dig_depth_profile_token_from_prior_mapping",
    "_unpack_return_target_token_plan",
    "_return_start_envelope_token_from_prior_mapping",
}


def _prior_payload() -> dict[str, object]:
    return {
        "prior_id": "test_prior",
        "token_order": [f"t{i}" for i in range(DIG_CUT_TOKEN_DIM)],
        "fields": {},
    }


def _write_prior(path: Path, payload: dict[str, object] | None = None) -> Path:
    path.write_text(json.dumps(payload or _prior_payload()), encoding="utf-8")
    return path


def _normalize(
    inputs: PrimitivePlannerAdapterConfigInputs | None = None,
) -> PrimitivePlannerAdapterConfigState:
    return PrimitivePlannerAdapterConfigNormalizer.normalize(
        inputs or PrimitivePlannerAdapterConfigInputs()
    )


def test_default_config_normalizes_legacy_defaults_and_vector_helpers() -> None:
    state = _normalize()
    updates = state.as_policy_field_updates()

    assert updates["bootstrap_end_mode"] == "disabled"
    assert updates["dig_to_carry_target_bucket_mass_kg"] == updates[
        "dig_to_carry_min_bucket_mass_kg"
    ]
    assert updates["dig_to_carry_mass_plateau_hold_steps"] == 25
    assert updates["dig_bad_replan_max_steps"] == 180
    assert updates["dump_ready_hold_steps"] == 3
    assert updates["action_dim"] == 4
    assert updates["primitive_checkpoint_paths"] == {}
    assert updates["goal_sequence"] == ()
    assert updates["dig_cut_planner_mode"] == "conservative_pose"
    assert updates["dig_cut_prior"] == {}
    assert updates["return_to_dig_max_entry_error_m"] is None
    assert adapter_config.optional_float("none") is None
    assert adapter_config.optional_float("null") is None
    assert adapter_config.optional_float("") is None
    vector = adapter_config.align_vector(
        None,
        default=[1, 2, 3, 4],
        action_dim=4,
    )
    assert vector.dtype == np.float32
    assert vector.tolist() == [1.0, 2.0, 3.0, 4.0]
    optional = adapter_config.optional_align_vector("1,2,3,4", action_dim=4)
    assert optional is not None
    assert optional.dtype == np.float32
    assert optional.tolist() == [1.0, 2.0, 3.0, 4.0]


def test_normalizer_exposes_fsm_capability_provider_config() -> None:
    state = _normalize(
        PrimitivePlannerAdapterConfigInputs(
            action_dim=4,
            dig_to_carry_min_bucket_mass_kg=123.0,
            dig_to_carry_target_bucket_mass_kg=None,
            dig_to_carry_mass_plateau_hold_steps=0,
            dig_to_carry_mass_plateau_min_steps=0,
            dump_ready_min_bucket_mass_kg=77.0,
            return_to_dig_start_envelope_gate_enabled=True,
        )
    )

    config = state.fsm_capability_provider_config

    assert isinstance(config, PrimitiveFSMCapabilityProviderConfig)
    assert config.action_dim == 4
    assert config.dig_to_carry_min_bucket_mass_kg == 123.0
    assert config.dig_to_carry_target_bucket_mass_kg == 123.0
    assert config.dig_to_carry_mass_plateau_hold_steps == 1
    assert config.dig_to_carry_mass_plateau_min_steps == 1
    assert config.dump_ready_min_bucket_mass_kg == 77.0
    assert config.return_to_dig_start_envelope_gate_enabled is True
    assert state.as_policy_field_updates()["dig_to_carry_target_bucket_mass_kg"] == 123.0


def test_normalizer_exposes_return_handoff_readiness_config() -> None:
    state = _normalize(
        PrimitivePlannerAdapterConfigInputs(
            action_dim=4,
            return_target_planner={"enabled": True},
            return_to_dig_max_entry_error_m=0.31,
            return_to_dig_max_bucket_mass_kg=9.5,
            return_to_dig_start_envelope_direct_handoff_enabled=True,
            return_to_dig_start_envelope_gate_enabled=True,
            return_to_dig_start_envelope_spatial_tolerance=0.12,
            return_to_dig_start_envelope_depth_tolerance_m=0.07,
            return_to_dig_start_envelope_local_depth_tolerance_m=0.006,
            return_to_dig_start_envelope_plane_depth_tolerance_m=0.009,
            return_to_dig_start_envelope_plane_depth_mode="p50_floor",
            return_to_dig_start_envelope_qpos_tolerance=0.05,
            return_to_dig_start_envelope_require_contact=False,
        )
    )

    config = state.return_handoff_readiness_config

    assert isinstance(config, ReturnHandoffReadinessConfig)
    assert config.return_target_planner_enabled is True
    assert config.max_entry_error_m == 0.31
    assert config.max_bucket_mass_kg == 9.5
    assert config.start_envelope_direct_handoff_enabled is True
    assert config.start_envelope_gate.enabled is True
    assert config.start_envelope_gate.action_dim == 4
    assert config.start_envelope_gate.spatial_tolerance == 0.12
    assert config.start_envelope_gate.depth_tolerance_m == 0.07
    assert config.start_envelope_gate.local_depth_tolerance_m == 0.006
    assert config.start_envelope_gate.plane_depth_tolerance_m == 0.009
    assert config.start_envelope_gate.plane_depth_mode == "p50_floor"
    assert config.start_envelope_gate.qpos_tolerance == 0.05
    assert config.start_envelope_gate.require_contact is False
    assert (
        state.as_policy_field_updates()[
            "return_to_dig_start_envelope_direct_handoff_enabled"
        ]
        is True
    )


def test_pre_dig_align_enabled_config_normalizes_opt_in_runtime_fields() -> None:
    state = _normalize(
        PrimitivePlannerAdapterConfigInputs(
            pre_dig_align={
                "enabled": True,
                "first_dig_only": True,
                "replan_after_failed_dig": True,
                "controlled_dims": [1, 0, 1, 0],
                "bucket_target_qpos": -0.2,
            },
        )
    )
    updates = state.as_policy_field_updates()

    assert updates["pre_dig_align_cfg"]["enabled"] is True
    assert updates["pre_dig_align_enabled"] is True
    assert updates["pre_dig_align_first_dig_only"] is True
    assert updates["pre_dig_align_replan_after_failed_dig"] is True
    assert updates["pre_dig_align_controlled_dims"].tolist() == [
        True,
        False,
        True,
        False,
    ]
    assert updates["pre_dig_align_bucket_target_qpos"] == -0.2


def test_disabled_pre_dig_align_config_remains_report_schema_compatible() -> None:
    state = _normalize(
        PrimitivePlannerAdapterConfigInputs(
            pre_dig_align={
                "enabled": False,
                "first_dig_only": True,
                "replan_after_failed_dig": True,
                "controlled_dims": [1, 0, 1, 0],
                "bucket_target_qpos": -0.2,
            },
        )
    )
    updates = state.as_policy_field_updates()

    assert updates["pre_dig_align_cfg"]["enabled"] is False
    assert updates["pre_dig_align_enabled"] is False
    assert updates["pre_dig_align_first_dig_only"] is True
    assert updates["pre_dig_align_replan_after_failed_dig"] is True
    assert updates["pre_dig_align_controlled_dims"].tolist() == [
        True,
        False,
        True,
        False,
    ]
    assert updates["pre_dig_align_bucket_target_qpos"] == -0.2


def test_cell_entry_enabled_config_fails_fast_after_runtime_removal() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "cell_entry primitive planner runtime has been removed; "
            "set cell_entry.enabled=false"
        ),
    ):
        _normalize(
            PrimitivePlannerAdapterConfigInputs(
                cell_entry_enabled=True,
            )
        )


def test_disabled_cell_entry_config_remains_report_schema_compatible() -> None:
    state = _normalize(
        PrimitivePlannerAdapterConfigInputs(
            cell_entry_enabled=False,
            cell_entry_grid={"half_long_m": 2.0, "half_short_m": 1.0},
            cell_entry_low_productivity_payload_gain_kg=75.0,
        )
    )
    updates = state.as_policy_field_updates()

    assert updates["cell_entry_enabled"] is False
    assert updates["cell_entry_grid"].half_long_m == 2.0
    assert updates["cell_entry_grid"].half_short_m == 1.0
    assert updates["cell_entry_planner"] is not None
    assert updates["cell_entry_auditor"].low_productivity_payload_gain_kg == 75.0


def test_dig_cut_prior_loading_validates_token_order(tmp_path: Path) -> None:
    assert adapter_config.load_dig_cut_prior("") == {}

    prior_path = _write_prior(tmp_path / "prior.json")
    state = _normalize(
        PrimitivePlannerAdapterConfigInputs(
            dig_cut_planner={
                "mode": "operator_prior",
                "prior_path": str(prior_path),
            }
        )
    )
    assert state.as_policy_field_updates()["dig_cut_prior_id"] == "test_prior"

    bad_prior = dict(_prior_payload())
    bad_prior["token_order"] = ["too_short"]
    bad_path = _write_prior(tmp_path / "bad_prior.json", bad_prior)
    with pytest.raises(ValueError, match="has invalid token_order length"):
        adapter_config.load_dig_cut_prior(str(bad_path))


def test_residual_cut_intent_dig_cut_planner_mode_does_not_require_prior_path() -> None:
    state = _normalize(
        PrimitivePlannerAdapterConfigInputs(
            dig_cut_planner={
                "mode": "residual_cut_intent",
            }
        )
    )
    updates = state.as_policy_field_updates()

    assert updates["dig_cut_planner_mode"] == "residual_cut_intent"
    assert updates["dig_cut_prior_path"] == ""
    assert updates["dig_cut_prior"] == {}
    assert updates["dig_cut_hold_token_until_skill_exit"] is False


@pytest.mark.parametrize(
    ("dig_cut_planner", "match"),
    [
        ({"mode": "not_real"}, "Unsupported dig_cut_planner mode 'not_real'"),
        (
            {"mode": "operator_prior"},
            "operator_prior dig_cut_planner requires prior_path",
        ),
        (
            {
                "coverage": {
                    "candidate_layout": "not_real",
                }
            },
            "Unsupported coverage.candidate_layout 'not_real'",
        ),
        (
            {
                "dig_depth_profile": {
                    "source": "not_real",
                }
            },
            "Unsupported dig_depth_profile.source 'not_real'",
        ),
        (
            {
                "dig_depth_profile": {
                    "source": "prior_profile",
                    "required": True,
                    "allow_live_fallback": True,
                }
            },
            "dig_depth_profile.source='prior_profile' requires prior_path",
        ),
    ],
)
def test_dig_planner_validation_preserves_error_shapes(
    dig_cut_planner: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        _normalize(PrimitivePlannerAdapterConfigInputs(dig_cut_planner=dig_cut_planner))


def test_prior_profile_required_live_fallback_conflict_message(
    tmp_path: Path,
) -> None:
    prior = _prior_payload()
    prior["dig_depth_profile_cells"] = {}
    prior_path = _write_prior(tmp_path / "prior_with_profiles.json", prior)

    with pytest.raises(
        ValueError,
        match=(
            "dig_depth_profile.required=true must set "
            "allow_live_fallback=false"
        ),
    ):
        _normalize(
            PrimitivePlannerAdapterConfigInputs(
                dig_cut_planner={
                    "mode": "operator_prior",
                    "prior_path": str(prior_path),
                    "dig_depth_profile": {
                        "source": "prior_profile",
                        "required": True,
                        "allow_live_fallback": True,
                    },
                }
            )
        )


def test_plane_depth_and_failed_replan_validation_preserves_error_shapes() -> None:
    with pytest.raises(
        ValueError,
        match="return_to_dig_start_envelope_plane_depth_mode must be one of",
    ):
        _normalize(
            PrimitivePlannerAdapterConfigInputs(
                return_to_dig_start_envelope_plane_depth_mode="bad_mode"
            )
        )
    with pytest.raises(
        ValueError,
        match="dig_failed_replan_next_skill must be 'dig' or 'stop'",
    ):
        _normalize(
            PrimitivePlannerAdapterConfigInputs(
                dig_failed_replan_next_skill="carry"
            )
        )


def test_state_exemplar_path_disabled_and_relative_path_resolution(
    tmp_path: Path,
) -> None:
    assert _normalize().as_policy_field_updates()["coverage_state_exemplars_by_cell"] == {}

    exemplars_path = tmp_path / "state_exemplars.json"
    exemplars_path.write_text(
        json.dumps(
            {
                "exemplars": [
                    {
                        "cell_id": 2,
                        "exemplar_id": "cell2_a",
                        "raw_fields": {"operator_entry_x_m": 0.1},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    prior_path = _write_prior(tmp_path / "prior.json")
    state = _normalize(
        PrimitivePlannerAdapterConfigInputs(
            dig_cut_planner={
                "mode": "operator_prior_coverage",
                "prior_path": str(prior_path),
                "coverage": {
                    "state_conditioned_exemplars": {
                        "enabled": True,
                        "path": "state_exemplars.json",
                    }
                },
            }
        )
    )

    exemplars_by_cell = state.as_policy_field_updates()[
        "coverage_state_exemplars_by_cell"
    ]
    assert exemplars_by_cell[2][0]["exemplar_id"] == "cell2_a"


def test_policy_no_longer_exposes_test_only_helper_facades() -> None:
    assert _POLICY_HELPER_FACADE_NAMES.isdisjoint(
        PrimitivePlannerACTPolicy.__dict__
    )


def test_policy_config_state_apply_uses_normalized_state() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    config = _normalize().fsm_capability_provider_config
    state = PrimitivePlannerAdapterConfigState(
        {
            "action_dim": 4,
            "dig_cut_planner_mode": "conservative_pose",
        },
        fsm_capability_provider_config=config,
    )
    policy._apply_adapter_config_state(state)
    assert policy.action_dim == 4
    assert policy.dig_cut_planner_mode == "conservative_pose"
    assert policy._fsm_capability_provider_config is config

    assert adapter_config.optional_float("123.0") == 123.0
    assert adapter_config.align_vector(
        [1, 2, 3],
        default=[0, 0, 0],
        action_dim=3,
    ).tolist() == [1.0, 2.0, 3.0]


def test_policy_init_uses_config_normalizer_boundary() -> None:
    source = inspect.getsource(PrimitivePlannerACTPolicy.__init__)

    assert "PrimitivePlannerAdapterConfigInputs" in source
    assert "PrimitivePlannerAdapterConfigNormalizer" in source
    assert "_apply_adapter_config_state" in source
    assert "CellGridSpec(**" not in source
    assert "_validate_dig_cut_planner_config()" not in source


def test_config_dataclass_boundary_does_not_receive_planner_self() -> None:
    for cls in (
        PrimitivePlannerAdapterConfigInputs,
        PrimitivePlannerAdapterConfigState,
    ):
        names = {field.name for field in fields(cls)}
        assert "planner" not in names
        assert "self" not in names
