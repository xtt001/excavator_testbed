from __future__ import annotations

import numpy as np
import pytest

from testbed.planner.primitive_token_status import TokenStatus


def test_token_status_freezes_current_token_arrays() -> None:
    dig_cut_tokens = np.asarray([1.0, 2.0, 3.0], dtype=np.float32)
    return_target_tokens = [4.0, 5.0]

    status = TokenStatus.from_inputs(
        dig_cut_token_dim=3,
        dig_cut_tokens=dig_cut_tokens,
        return_target_token_dim=2,
        return_target_tokens=return_target_tokens,
    )

    dig_cut_tokens[0] = 99.0
    return_target_tokens[0] = 88.0

    np.testing.assert_allclose(status.dig_cut.tokens, [1.0, 2.0, 3.0])
    np.testing.assert_allclose(status.return_target.tokens, [4.0, 5.0])
    with pytest.raises(ValueError):
        status.dig_cut.tokens[0] = 7.0


def test_token_status_records_sources_fallbacks_and_injected_flags() -> None:
    status = TokenStatus.from_inputs(
        cell_entry_enabled=False,
        cell_entry_token_injected=False,
        cell_entry_token_dim=6,
        dig_cut_token_injected=True,
        dig_cut_token_dim=10,
        dig_cut_token_source="pending_return_target",
        dig_cut_fallback_reason="",
        dig_cut_token_in_prior_p10_p90=True,
        dig_depth_profile_token_injected=True,
        dig_depth_profile_token_dim=12,
        dig_depth_profile_source="prior_profile",
        dig_depth_profile_required=True,
        dig_depth_profile_token_source="qc6_state_conditioned_exemplar",
        dig_depth_profile_fallback_reason="",
        return_target_token_injected=True,
        return_target_token_dim=10,
        return_target_token_source="return_target_corridor_0",
        return_target_fallback_reason="",
        return_relocate_token_injected=True,
        return_relocate_token_dim=10,
        return_relocate_token_source="return_target_corridor_0",
        return_start_envelope_token_injected=True,
        return_start_envelope_token_dim=18,
        return_start_envelope_token_source="return_start_envelope_corridor_0",
    )

    assert status.cell_entry_enabled is False
    assert status.cell_entry.injected is False
    assert status.cell_entry.dim == 6
    assert status.dig_cut.injected is True
    assert status.dig_cut.source == "pending_return_target"
    assert status.dig_cut.fallback_reason == ""
    assert status.dig_cut.in_prior_p10_p90 is True
    assert status.dig_depth_profile.source == "qc6_state_conditioned_exemplar"
    assert status.dig_depth_profile_source == "prior_profile"
    assert status.dig_depth_profile_required is True
    assert status.return_target.source == "return_target_corridor_0"
    assert status.return_relocate.source == "return_target_corridor_0"
    assert status.return_start_envelope.source == "return_start_envelope_corridor_0"


def test_token_status_exports_legacy_debug_fields_without_renaming() -> None:
    status = TokenStatus.from_inputs(
        cell_entry_enabled=True,
        cell_entry_token_injected=False,
        cell_entry_token_dim=6,
        dig_cut_token_injected=True,
        dig_cut_token_dim=3,
        dig_cut_token_source="operator_prior_coverage",
        dig_cut_tokens=[1.0, 2.0, 3.0],
        dig_cut_fallback_reason="fallback detail",
        dig_cut_token_in_prior_p10_p90=False,
        dig_depth_profile_token_injected=True,
        dig_depth_profile_token_dim=2,
        dig_depth_profile_source="prior_profile",
        dig_depth_profile_required=False,
        dig_depth_profile_token_source="qc6_dig_depth_profile_global",
        dig_depth_profile_tokens=[4.0, 5.0],
        dig_depth_profile_fallback_reason="",
        return_target_token_injected=True,
        return_target_token_dim=2,
        return_target_token_source="return_target",
        return_target_tokens=[6.0, 7.0],
        return_target_fallback_reason="",
        return_relocate_token_injected=True,
        return_relocate_token_dim=2,
        return_relocate_token_source="return_target",
        return_relocate_tokens=[8.0, 9.0],
        return_start_envelope_token_injected=True,
        return_start_envelope_token_dim=2,
        return_start_envelope_token_source="return_start_envelope",
        return_start_envelope_tokens=[10.0, 11.0],
    )

    debug_fields = status.to_debug_fields()

    assert debug_fields["cell_entry_enabled"] is True
    assert debug_fields["cell_entry_token_injected"] is False
    assert debug_fields["cell_entry_token_dim"] == 6
    assert debug_fields["dig_cut_token_injected"] is True
    assert debug_fields["dig_cut_token_dim"] == 3
    assert debug_fields["dig_cut_token_source"] == "operator_prior_coverage"
    assert debug_fields["dig_cut_tokens"] == [1.0, 2.0, 3.0]
    assert debug_fields["token_in_prior_p10_p90"] is False
    assert debug_fields["dig_cut_token_in_prior_p10_p90"] is False
    assert debug_fields["fallback_reason"] == "fallback detail"
    assert debug_fields["dig_cut_fallback_reason"] == "fallback detail"
    assert debug_fields["dig_depth_profile_token_injected"] is True
    assert debug_fields["dig_depth_profile_token_dim"] == 2
    assert debug_fields["dig_depth_profile_source"] == "prior_profile"
    assert debug_fields["dig_depth_profile_required"] is False
    assert (
        debug_fields["dig_depth_profile_token_source"]
        == "qc6_dig_depth_profile_global"
    )
    assert debug_fields["dig_depth_profile_tokens"] == [4.0, 5.0]
    assert debug_fields["return_target_token_injected"] is True
    assert debug_fields["return_target_token_dim"] == 2
    assert debug_fields["return_target_token_source"] == "return_target"
    assert debug_fields["return_target_tokens"] == [6.0, 7.0]
    assert debug_fields["return_relocate_token_injected"] is True
    assert debug_fields["return_relocate_token_dim"] == 2
    assert debug_fields["return_relocate_token_source"] == "return_target"
    assert debug_fields["return_relocate_tokens"] == [8.0, 9.0]
    assert debug_fields["return_start_envelope_token_injected"] is True
    assert debug_fields["return_start_envelope_token_dim"] == 2
    assert (
        debug_fields["return_start_envelope_token_source"]
        == "return_start_envelope"
    )
    assert debug_fields["return_start_envelope_tokens"] == [10.0, 11.0]
