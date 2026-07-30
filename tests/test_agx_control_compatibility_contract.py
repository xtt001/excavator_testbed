from pathlib import Path

from testbed.backends.agx.protocol import CONTROL_COMPATIBILITY_PROFILES

UNITY_ROOT = Path("/home/pingfan/AGXUnityE85ExcavatorSim")
UNITY_SCRIPTS = (
    UNITY_ROOT
    / "Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts"
)
UNITY_BRIDGE = UNITY_SCRIPTS / "SimulationBridge"
UNITY_CONTROL = UNITY_SCRIPTS / "Control/Execution"


def test_python_and_unity_share_replay_control_compatibility_profile_names() -> None:
    service = (UNITY_BRIDGE / "ReplayControlCompatibilityMode.cs").read_text(
        encoding="utf-8"
    )

    for profile in CONTROL_COMPATIBILITY_PROFILES:
        assert f'"{profile}"' in service


def test_reset_applies_control_profile_and_production_remains_default() -> None:
    protocol = (UNITY_BRIDGE / "AgxSimProtocol.cs").read_text(encoding="utf-8")
    server = (UNITY_BRIDGE / "AgxSimStepAckServer.cs").read_text(encoding="utf-8")
    service = (UNITY_BRIDGE / "ReplayControlCompatibilityMode.cs").read_text(
        encoding="utf-8"
    )

    assert "control_compatibility_profile" in protocol
    assert "ReplayControlCompatibilityMode.TryApply" in server
    assert "string.IsNullOrWhiteSpace( requestedProfile )" in service
    assert "Production" in service


def test_recording_profile_restores_only_the_pre_fix_target_speed_semantics() -> None:
    actuator = (UNITY_CONTROL / "ExcavatorAxisActuators.cs").read_text(
        encoding="utf-8"
    )
    assert "TargetSpeedControlProfile.RecordingPreFixV1" in actuator
    assert "referenceConstraint.GetCurrentSpeed()" in actuator
    assert "m_commandedTargetSpeed" in actuator
    assert "lockAtZeroSpeed" in actuator
