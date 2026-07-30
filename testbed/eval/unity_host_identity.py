"""Fail-closed identity proof for the external AGX Unity host."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from testbed.backends.agx.protocol import (
    ACTION_ORDER_V2,
    QPOS_ORDER_V2,
    QVEL_ORDER_V2,
    AgxSimClient,
)
from testbed.data.schema import (
    ENV_STATE_CONTRACT_VERSION_V2_4,
    ENV_STATE_ORDER_V2_4,
)
from testbed.eval.unity_contact_observe_only_report import (
    UnityContactObserveOnlyReportError,
)

UNITY_HOST_EVIDENCE_SCHEMA = "agx_unity_get_info_v1"
FACTORY_FLOOR_CONTACT_CAPABILITY_WARNING = (
    "worktool_factory_floor_contact_detail_capability_v1:ready"
)


def probe_agx_unity_host(agx: Mapping[str, Any]) -> dict[str, Any]:
    """Read the live host identity before an exactly-once attempt is consumed."""

    client = AgxSimClient(
        host=str(agx.get("host", "")),
        port=_strict_int(agx.get("port"), "agx.port"),
        timeout_s=float(agx.get("timeout", 0.0)),
    )
    try:
        info = client.get_info()
    finally:
        client.close()
    return {
        "schema": UNITY_HOST_EVIDENCE_SCHEMA,
        "host": str(agx.get("host", "")),
        "port": int(agx.get("port", -1)),
        "protocol_version": str(info.protocol_version),
        "runtime_build_id": str(info.runtime_build_id),
        "env_state_contract_version": str(
            info.env_state_contract_version
        ),
        "action_order": list(info.action_order),
        "qpos_order": list(info.qpos_order),
        "qvel_order": list(info.qvel_order),
        "env_state_order": list(info.env_state_order),
        "camera_names": list(info.camera_names),
        "warnings": list(info.warnings),
    }


def validate_unity_host_evidence(
    value: Any,
    *,
    agx: Mapping[str, Any],
) -> dict[str, Any]:
    """Require the exact v2/107D/four-camera editor runtime contract."""

    if not isinstance(value, Mapping):
        raise UnityContactObserveOnlyReportError(
            "unity_host_get_info_must_be_mapping"
        )
    evidence = dict(value)
    expected = {
        "schema": UNITY_HOST_EVIDENCE_SCHEMA,
        "host": str(agx.get("host", "")),
        "port": _strict_int(agx.get("port"), "agx.port"),
        "protocol_version": "agx-sim/v2",
        "env_state_contract_version": ENV_STATE_CONTRACT_VERSION_V2_4,
        "action_order": list(ACTION_ORDER_V2),
        "qpos_order": list(QPOS_ORDER_V2),
        "qvel_order": list(QVEL_ORDER_V2),
        "env_state_order": list(ENV_STATE_ORDER_V2_4),
        "camera_names": [
            "stick_up",
            "stick_down",
            "eye_left",
            "eye_right",
        ],
        "warnings": [FACTORY_FLOOR_CONTACT_CAPABILITY_WARNING],
    }
    for field, expected_value in expected.items():
        if evidence.get(field) != expected_value:
            raise UnityContactObserveOnlyReportError(
                f"unity_host_identity_invalid:{field}"
            )
    runtime_build_id = evidence.get("runtime_build_id")
    if (
        not isinstance(runtime_build_id, str)
        or not runtime_build_id.strip()
        or not runtime_build_id.endswith(
            f":{ENV_STATE_CONTRACT_VERSION_V2_4}"
        )
    ):
        raise UnityContactObserveOnlyReportError(
            "unity_host_identity_invalid:runtime_build_id"
        )
    return {
        **expected,
        "runtime_build_id": runtime_build_id,
    }


def _strict_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UnityContactObserveOnlyReportError(
            f"{label}_must_be_int"
        )
    return value


__all__ = [
    "FACTORY_FLOOR_CONTACT_CAPABILITY_WARNING",
    "UNITY_HOST_EVIDENCE_SCHEMA",
    "probe_agx_unity_host",
    "validate_unity_host_evidence",
]
