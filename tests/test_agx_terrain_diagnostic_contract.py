from pathlib import Path

from testbed.backends.agx.protocol import TERRAIN_DIAGNOSTIC_MODES

UNITY_ROOT = Path("/home/pingfan/AGXUnityE85ExcavatorSim")
UNITY_BRIDGE = (
    UNITY_ROOT
    / "Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/SimulationBridge"
)
UNITY_EXPERIMENT = (
    UNITY_ROOT
    / "Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/Experiment"
)


def test_python_and_unity_share_terrain_diagnostic_mode_names() -> None:
    service = (UNITY_BRIDGE / "ReplayTerrainDiagnosticMode.cs").read_text(
        encoding="utf-8"
    )

    for mode in TERRAIN_DIAGNOSTIC_MODES:
        assert f'"{mode}"' in service


def test_unity_reset_protocol_applies_diagnostic_mode_after_reset() -> None:
    protocol = (UNITY_BRIDGE / "AgxSimProtocol.cs").read_text(encoding="utf-8")
    server = (UNITY_BRIDGE / "AgxSimStepAckServer.cs").read_text(encoding="utf-8")
    service = (UNITY_BRIDGE / "ReplayTerrainDiagnosticMode.cs").read_text(
        encoding="utf-8"
    )

    assert "diagnostic_terrain_mode" in protocol
    assert "ReplayTerrainDiagnosticMode.TryApply" in server
    assert "diagnostic_terrain_mode:" in service


def test_bucket_contact_diagnostics_report_max_force_external_shape() -> None:
    monitor = (UNITY_EXPERIMENT / "BucketContactForceMonitor.cs").read_text(
        encoding="utf-8"
    )
    server = (UNITY_BRIDGE / "AgxSimStepAckServer.cs").read_text(encoding="utf-8")

    assert "BucketContactMaxExternalShapeName" in monitor
    assert "max_external_shape=" in server
