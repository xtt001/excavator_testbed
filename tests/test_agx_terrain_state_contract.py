from __future__ import annotations

import io
import re
from pathlib import Path

import numpy as np
import pytest

from testbed.backends.agx.protocol import (
    _pack_bool,
    _pack_string,
    _pack_string_array,
    decode_get_info_response,
)
from testbed.data.schema import (
    ENV_STATE_ORDER_V2_2,
    ENV_STATE_ORDER_V2_3,
    ENV_STATE_ORDER_V2_4,
    ENV_STATE_V2_3_DIM,
    ENV_STATE_V2_4_DIM,
)


def _get_info_v2_payload() -> bytes:
    payload = io.BytesIO()
    payload.write(_pack_bool(True))
    payload.write(_pack_string(""))
    payload.write(_pack_string("agx-sim/v2"))
    payload.write(np.float32(0.02).astype("<f4").tobytes())
    payload.write(np.float32(50.0).astype("<f4").tobytes())
    payload.write(_pack_string("actuator_speed_cmd"))
    payload.write(_pack_string_array(["a0", "a1", "a2", "a3"]))
    payload.write(_pack_string_array(["q0", "q1", "q2", "q3"]))
    payload.write(_pack_string_array(["v0", "v1", "v2", "v3"]))
    payload.write(_pack_string_array(ENV_STATE_ORDER_V2_4))
    payload.write(_pack_string("agx_env_state_v2_4_107"))
    payload.write(_pack_string("unity-test-build"))
    payload.write(_pack_string("terrain_state_grid_3x2_v1"))
    payload.write(_pack_string("grid_depth_integral"))
    payload.write(_pack_string_array([]))
    payload.write(_pack_bool(True))
    payload.write(_pack_bool(False))
    payload.write((0).to_bytes(4, "little", signed=True))
    payload.write(_pack_string_array([]))
    return payload.getvalue()


def test_env_state_v2_3_is_an_append_only_89d_contract() -> None:
    assert ENV_STATE_V2_3_DIM == 89
    assert len(ENV_STATE_ORDER_V2_3) == 89
    assert ENV_STATE_ORDER_V2_3[: len(ENV_STATE_ORDER_V2_2)] == ENV_STATE_ORDER_V2_2


def test_env_state_v2_4_is_an_append_only_107d_live_contract() -> None:
    assert ENV_STATE_V2_4_DIM == 107
    assert len(ENV_STATE_ORDER_V2_4) == 107
    assert ENV_STATE_ORDER_V2_4[:ENV_STATE_V2_3_DIM] == ENV_STATE_ORDER_V2_3


def test_get_info_v2_exposes_terrain_provenance() -> None:
    info = decode_get_info_response(_get_info_v2_payload())

    assert info.protocol_version == "agx-sim/v2"
    assert info.env_state_contract_version == "agx_env_state_v2_4_107"
    assert info.runtime_build_id == "unity-test-build"
    assert info.terrain_state_contract_version == "terrain_state_grid_3x2_v1"
    assert info.terrain_volume_source == "grid_depth_integral"


def test_unity_env_state_order_matches_python_contract() -> None:
    unity_source = Path(
        "/home/pingfan/AGXUnityE85ExcavatorSim/Assets/AGXUnity_Excavator/"
        "AGXUnity_Excavator_Assets/Scripts/SimulationBridge/AgxSimStepAckServer.cs"
    )
    if not unity_source.exists():
        pytest.skip("Unity repository is not available")
    text = unity_source.read_text(encoding="utf-8")
    match = re.search(
        r"payload\.env_state_order\s*=\s*new\[\]\s*\{(?P<body>.*?)\n\s*\};",
        text,
        flags=re.DOTALL,
    )
    assert match is not None
    names = tuple(re.findall(r'"([a-zA-Z0-9_]+)"', match.group("body")))
    assert names == ENV_STATE_ORDER_V2_4


def test_unity_editor_runtime_build_id_rejects_all_zero_build_guid() -> None:
    unity_source = Path(
        "/home/pingfan/AGXUnityE85ExcavatorSim/Assets/AGXUnity_Excavator/"
        "AGXUnity_Excavator_Assets/Scripts/SimulationBridge/AgxSimStepAckServer.cs"
    )
    if not unity_source.exists():
        pytest.skip("Unity repository is not available")
    text = unity_source.read_text(encoding="utf-8")

    assert "runtime_build_id = ResolveRuntimeBuildId()" in text
    assert "buildGuid.Trim( '0' ).Length > 0" in text
    assert "Application.unityVersion" in text
    assert "AgxSimProtocolConstants.EnvStateContractVersion" in text
