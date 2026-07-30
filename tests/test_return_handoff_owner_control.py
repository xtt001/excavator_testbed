from __future__ import annotations

from testbed.planner.primitive.config.adapter import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
)
from testbed.planner.primitive.effects.return_handoff import (
    ReturnStartEnvelopeGateConfig,
)
from testbed.planner.primitive.effects.return_handoff_owner_control import (
    ReturnStartEnvelopeOwnerControlConfig,
    ReturnStartEnvelopeOwnerControlService,
)


def _base_gate() -> ReturnStartEnvelopeGateConfig:
    return ReturnStartEnvelopeGateConfig(
        enabled=True,
        action_dim=4,
        spatial_tolerance=0.10,
        depth_tolerance_m=0.08,
        local_depth_tolerance_m=0.005,
        plane_depth_tolerance_m=0.0,
        plane_depth_mode="p50_floor",
        qpos_tolerance=0.04,
        require_contact=True,
    )


def test_owner_override_is_inert_before_seven_completed_dumps() -> None:
    config = ReturnStartEnvelopeOwnerControlConfig.from_box_emptying_mapping(
        {
            "return_start_envelope_owner_control": {
                "enabled": True,
                "diagnostic_only": True,
                "min_completed_dump_count": 7,
                "contact_owner": "token",
                "depth_owner": "runtime_prior_p05_p95",
            }
        }
    )
    service = ReturnStartEnvelopeOwnerControlService(config)

    decision = service.resolve(
        base_gate=_base_gate(),
        completed_dump_count=6,
    )

    assert decision.active is False
    assert decision.gate_config == _base_gate()
    assert decision.log_fields["completed_dump_count"] == 6
    assert decision.log_fields["min_completed_dump_count"] == 7


def test_owner_override_activates_at_seven_without_threshold_changes() -> None:
    config = ReturnStartEnvelopeOwnerControlConfig.from_box_emptying_mapping(
        {
            "return_start_envelope_owner_control": {
                "enabled": True,
                "diagnostic_only": True,
                "min_completed_dump_count": 7,
                "contact_owner": "token",
                "depth_owner": "runtime_prior_p05_p95",
            }
        }
    )
    decision = ReturnStartEnvelopeOwnerControlService(config).resolve(
        base_gate=_base_gate(),
        completed_dump_count=7,
    )

    assert decision.active is True
    assert decision.gate_config.require_contact is False
    assert decision.gate_config.plane_depth_mode == "range"
    assert decision.gate_config.spatial_tolerance == 0.10
    assert decision.gate_config.depth_tolerance_m == 0.08
    assert decision.gate_config.local_depth_tolerance_m == 0.005
    assert decision.gate_config.plane_depth_tolerance_m == 0.0
    assert decision.gate_config.qpos_tolerance == 0.04
    assert decision.log_fields["contact_owner"] == "token"
    assert decision.log_fields["depth_owner"] == "runtime_prior_p05_p95"


def test_enabled_owner_override_requires_diagnostic_marker() -> None:
    try:
        ReturnStartEnvelopeOwnerControlConfig.from_box_emptying_mapping(
            {
                "return_start_envelope_owner_control": {
                    "enabled": True,
                    "diagnostic_only": False,
                    "min_completed_dump_count": 7,
                }
            }
        )
    except ValueError as exc:
        assert "diagnostic_only=true" in str(exc)
    else:
        raise AssertionError("enabled non-diagnostic owner override accepted")


def test_adapter_wires_request_local_owner_control_into_handoff_config() -> None:
    state = PrimitivePlannerAdapterConfigNormalizer.normalize(
        PrimitivePlannerAdapterConfigInputs(
            box_emptying={
                "enabled": False,
                "safety_enabled": True,
                "return_start_envelope_owner_control": {
                    "enabled": True,
                    "diagnostic_only": True,
                    "min_completed_dump_count": 7,
                    "contact_owner": "token",
                    "depth_owner": "runtime_prior_p05_p95",
                },
            }
        )
    )

    readiness = state.return_handoff_readiness_config
    assert readiness is not None
    assert readiness.start_envelope_owner_control.enabled is True
    assert (
        readiness.start_envelope_owner_control.min_completed_dump_count == 7
    )
    assert state.field_updates[
        "return_start_envelope_owner_control_enabled"
    ] is True
