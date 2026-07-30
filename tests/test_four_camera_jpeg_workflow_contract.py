from __future__ import annotations

from pathlib import Path
import re

import cv2
import numpy as np
import pytest
import yaml

from testbed.data.camera_images import observation_camera_rgb


ROOT = Path(__file__).resolve().parents[1]
UNITY_ROOT = ROOT.parents[1] / "AGXUnityE85ExcavatorSim"
CAMERAS = ["stick_up", "stick_down", "eye_left", "eye_right"]


def _jpeg(rgb: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return encoded.tobytes()


def test_observation_video_helper_supports_raw_and_encoded_without_mutation() -> None:
    raw = np.arange(6 * 8 * 3, dtype=np.uint8).reshape(6, 8, 3)
    np.testing.assert_array_equal(
        observation_camera_rgb({"images": {"fpv": raw}}, "fpv"),
        raw,
    )

    encoded_bytes = _jpeg(raw)
    observation = {
        "encoded_images": {
            "stick_up": {
                "encoding": "jpeg",
                "shape": raw.shape,
                "data": encoded_bytes,
            }
        }
    }
    decoded = observation_camera_rgb(observation, "stick_up")
    assert decoded.shape == raw.shape
    assert decoded.dtype == np.uint8
    assert observation["encoded_images"]["stick_up"]["data"] is encoded_bytes

    with pytest.raises(KeyError, match="eye_left"):
        observation_camera_rgb(observation, "eye_left")


def test_current_four_camera_teleop_config_has_locked_order_and_new_identifiers() -> None:
    config_path = ROOT / "testbed/configs/teleop_yulong_v2_2_pro_full_task_four_camera_jpeg.yaml"
    payload = yaml.safe_load(config_path.read_text())
    assert payload["task"]["camera_names"] == CAMERAS
    assert "four_camera_jpeg" in payload["task"]["dataset_dir"]
    assert "four_camera_jpeg" in payload["task"]["param_version"]
    assert "four_camera_jpeg" in payload["task"]["recording_mode"]
    metadata = payload["teleop"]["metadata"]
    assert "four_camera_jpeg" in metadata["session_id"]
    assert metadata["recording_protocol_version"].endswith("jpeg_hdf5_v1")

    historical = yaml.safe_load(
        (ROOT / "testbed/configs/teleop_yulong_v2_2_pro_full_task.yaml").read_text()
    )
    assert historical["task"]["camera_names"] == ["fpv"]


def test_replay_eval_and_contract_use_shared_first_camera_preview_semantics() -> None:
    replay_source = (ROOT / "testbed/cli/replay.py").read_text()
    eval_source = (ROOT / "testbed/eval/suite.py").read_text()
    assert "preview_camera_name = camera_names[0]" in replay_source
    assert "observation_camera_rgb(obs_before, preview_camera_name)" in replay_source
    assert "cam0 = task.camera_names[0]" in eval_source
    assert "observation_camera_rgb(ts.observation, cam0)" in eval_source

    contract = (ROOT / "docs/data_processing_hdf5_qc_contract.md").read_text()
    for anchor in (
        "stick_up,stick_down,eye_left,eye_right",
        "/observations/encoded_images/<camera>",
        "image_format=jpeg",
        "MJPEG-style",
        "decode/re-encode",
        "旧 `/observations/images/fpv`",
    ):
        assert anchor in contract


@pytest.mark.skipif(not UNITY_ROOT.exists(), reason="paired Unity checkout is unavailable")
def test_unity_recording_cameras_are_capture_only() -> None:
    installer = (
        UNITY_ROOT
        / "Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/Editor/"
        "CodexRecordingCameraInstallUtility.cs"
    ).read_text()
    assert "camera.enabled = false;" in installer

    scene = (
        UNITY_ROOT / "Assets/AGXUnity_Excavator/AGXUnity_Excavator.unity"
    ).read_text()
    for camera_file_id in (310168436, 887245339, 1182187709, 1923403587):
        block = re.search(
            rf"--- !u!20 &{camera_file_id}\nCamera:\n(?P<body>.*?)(?=\n--- !u!)",
            scene,
            flags=re.DOTALL,
        )
        assert block is not None
        assert "m_Enabled: 0" in block.group("body")


@pytest.mark.skipif(not UNITY_ROOT.exists(), reason="paired Unity checkout is unavailable")
def test_unity_jpeg_capture_reuses_resources_without_gpu_reupload() -> None:
    capture = (
        UNITY_ROOT
        / "Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/SimulationBridge/"
        "AgxSimJpegCameraCapture.cs"
    ).read_text()
    assert "EnsureCaptureResources" in capture
    assert "ReleaseCaptureResources" in capture
    assert "readback.Apply" not in capture


@pytest.mark.skipif(not UNITY_ROOT.exists(), reason="paired Unity checkout is unavailable")
def test_unity_step_debug_logging_does_not_force_log_telemetry_warnings() -> None:
    server = (
        UNITY_ROOT
        / "Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/SimulationBridge/"
        "AgxSimStepAckServer.cs"
    ).read_text()
    record_step = server.split("private void RecordStepResponseDebug", 1)[1].split(
        "private void RecordCommonResponseDebug", 1
    )[0]
    assert "payload.warnings != null && payload.warnings.Length > 0" not in record_step
    assert "var forceLog = !payload.success || !string.IsNullOrEmpty( payload.error );" in record_step


@pytest.mark.skipif(not UNITY_ROOT.exists(), reason="paired Unity checkout is unavailable")
def test_unity_step_server_wakes_when_a_response_is_ready() -> None:
    server = (
        UNITY_ROOT
        / "Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/SimulationBridge/"
        "AgxSimStepAckServer.cs"
    ).read_text()
    assert "new AutoResetEvent( false )" in server
    assert "m_serverWakeSignal.WaitOne( 1 );" in server

    queue_response = server.split("private void QueueResponse", 1)[1].split(
        "private bool TryFlushPendingResponses", 1
    )[0]
    assert "m_serverWakeSignal.Set();" in queue_response


@pytest.mark.skipif(not UNITY_ROOT.exists(), reason="paired Unity checkout is unavailable")
def test_unity_step_server_parks_machine_before_first_client_request() -> None:
    server = (
        UNITY_ROOT
        / "Assets/AGXUnity_Excavator/AGXUnity_Excavator_Assets/Scripts/SimulationBridge/"
        "AgxSimStepAckServer.cs"
    ).read_text()
    acquire = server.split("private void AcquireServingControl", 1)[1].split(
        "private void RestoreServingControl", 1
    )[0]
    assert "simulation.AutoSteppingMode = Simulation.AutoSteppingModes.Disabled;" in acquire
    assert "m_machineController.StopMotion();" in acquire

    on_enable = server.split("private void OnEnable", 1)[1].split(
        "private void OnDisable", 1
    )[0]
    assert "AcquireServingControl();" in on_enable

    on_disable = server.split("private void OnDisable", 1)[1].split(
        "private void OnDestroy", 1
    )[0]
    assert "RestoreServingControl();" in on_disable
