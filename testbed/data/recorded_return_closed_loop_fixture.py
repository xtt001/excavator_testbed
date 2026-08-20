"""Frozen recorded-state fixtures for bounded Return closed-loop diagnostics.

This module owns only immutable data alignment and lineage.  It joins the
published Stage-A v3 Return records back to their source HDF5/JSONL rollout,
binds every action to the preceding observation, and exposes exactly four
pre-registered source states.  It does not load a policy, drive Unity, choose a
dispatch strategy, or decide whether a physical rollout succeeded.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.camera_images import (
    camera_names_from_metadata,
    encoded_frame_to_uint8,
    read_camera_rgb,
)
from testbed.data.recorded_act_replay import (
    RecordedActReplaySegment,
    join_recorded_act_replay_frames,
    split_stable_recorded_act_segments,
)

SCHEMA = "recorded_return_closed_loop_fixture_set_v1"
STAGE_A_MANIFEST_SCHEMA = "act_goal_condition_sensitivity_manifest_v1"
STAGE_A_EVIDENCE_KIND = "teacher_forced_recorded_observation"
RETURN_TOKEN_KEY = "return_start_envelope_tokens_v1"
RETURN_TOKEN_DIM = 18
RETURN_CLOSED_LOOP_ENV_STATE_DIM = 107
RETURN_CLOSED_LOOP_ENV_STATE_CONTRACT = "agx_env_state_v2_4_107"
RETURN_ACTION_ORDER = (
    "swing_speed_cmd",
    "boom_speed_cmd",
    "stick_speed_cmd",
    "bucket_speed_cmd",
)
RETURN_QPOS_ORDER = (
    "swing_position_norm",
    "boom_position_norm",
    "stick_position_norm",
    "bucket_position_norm",
)
RETURN_QVEL_ORDER = (
    "swing_speed",
    "boom_speed",
    "stick_speed",
    "bucket_speed",
)
FROZEN_RETURN_CAMERA_ORDER = (
    "stick_up",
    "stick_down",
    "eye_left",
    "eye_right",
)


@dataclass(frozen=True)
class RecordedReturnFixtureSpec:
    """One pre-registered Stage-A state and its exact alternate condition."""

    fixture_id: str
    evidence_role: str
    source_segment_id: str
    start_action_step_id: int
    observation_step_id: int
    alternate_segment_id: str
    expected_classification: str

    def __post_init__(self) -> None:
        if self.fixture_id not in {"F1", "N1", "F2", "N2"}:
            raise ValueError("fixture_id must be one of F1/N1/F2/N2")
        if self.evidence_role not in {"offline_failed", "offline_normal"}:
            raise ValueError("evidence_role must be offline_failed or offline_normal")
        expected = (
            "goal_response_invalid"
            if self.evidence_role == "offline_failed"
            else "goal_response_plausible"
        )
        if self.expected_classification != expected:
            raise ValueError(
                "fixture evidence role and expected classification disagree"
            )
        if not self.source_segment_id.startswith("return:"):
            raise ValueError("source_segment_id must identify a Return segment")
        if not self.alternate_segment_id.startswith("return:"):
            raise ValueError("alternate_segment_id must identify a Return segment")
        if int(self.start_action_step_id) <= 0:
            raise ValueError("start_action_step_id must be positive")
        if int(self.observation_step_id) != int(self.start_action_step_id) - 1:
            raise ValueError(
                "fixture must use the immediately preceding pre-action observation"
            )


FROZEN_RETURN_FIXTURE_SPECS = (
    RecordedReturnFixtureSpec(
        fixture_id="F1",
        evidence_role="offline_failed",
        source_segment_id="return:898-1043:bb329f176aba",
        start_action_step_id=898,
        observation_step_id=897,
        alternate_segment_id="return:3959-4161:4afcef2eee82",
        expected_classification="goal_response_invalid",
    ),
    RecordedReturnFixtureSpec(
        fixture_id="N1",
        evidence_role="offline_normal",
        source_segment_id="return:3453-3664:bb329f176aba",
        start_action_step_id=3453,
        observation_step_id=3452,
        alternate_segment_id="return:3959-4161:4afcef2eee82",
        expected_classification="goal_response_plausible",
    ),
    RecordedReturnFixtureSpec(
        fixture_id="F2",
        evidence_role="offline_failed",
        source_segment_id="return:3959-4161:4afcef2eee82",
        start_action_step_id=3959,
        observation_step_id=3958,
        alternate_segment_id="return:2323-2534:87aa0fb8c981",
        expected_classification="goal_response_invalid",
    ),
    RecordedReturnFixtureSpec(
        fixture_id="N2",
        evidence_role="offline_normal",
        source_segment_id="return:4437-4633:4afcef2eee82",
        start_action_step_id=4437,
        observation_step_id=4436,
        alternate_segment_id="return:2323-2534:87aa0fb8c981",
        expected_classification="goal_response_plausible",
    ),
)


@dataclass(frozen=True)
class RecordedReturnImageLineage:
    """Content identity for one decoded pre-action RGB camera frame."""

    camera_name: str
    shape: tuple[int, int, int]
    encoded_jpeg_size_bytes: int
    encoded_jpeg_sha256: str
    rgb_sha256: str

    def __post_init__(self) -> None:
        if not self.camera_name:
            raise ValueError("camera_name must be non-empty")
        if len(self.shape) != 3 or self.shape[2] != 3 or min(self.shape) < 1:
            raise ValueError("recorded camera shape must be positive HWC RGB")
        if self.encoded_jpeg_size_bytes < 1:
            raise ValueError("encoded JPEG frame must be non-empty")
        _require_sha256(self.encoded_jpeg_sha256, "encoded JPEG sha256")
        _require_sha256(self.rgb_sha256, "image rgb_sha256")

    def as_dict(self) -> dict[str, Any]:
        return {
            "camera_name": self.camera_name,
            "shape": list(self.shape),
            "dtype": "uint8",
            "encoded_jpeg_size_bytes": int(self.encoded_jpeg_size_bytes),
            "encoded_jpeg_sha256": self.encoded_jpeg_sha256,
            "rgb_sha256": self.rgb_sha256,
        }


@dataclass(frozen=True)
class RecordedReturnInitialObservation:
    """The source observation immediately preceding one Return action."""

    action_step_id: int
    observation_step_id: int
    hdf5_observation_index: int
    qpos: np.ndarray
    qvel: np.ndarray
    env_state: np.ndarray
    image_lineage: tuple[RecordedReturnImageLineage, ...]

    def __post_init__(self) -> None:
        if self.observation_step_id != self.action_step_id - 1:
            raise ValueError("initial observation is not the pre-action observation")
        if self.hdf5_observation_index < 0:
            raise ValueError("hdf5_observation_index must be non-negative")
        object.__setattr__(self, "qpos", _frozen_vector(self.qpos, 4, "qpos"))
        object.__setattr__(self, "qvel", _frozen_vector(self.qvel, 4, "qvel"))
        object.__setattr__(
            self,
            "env_state",
            _frozen_vector(
                self.env_state,
                RETURN_CLOSED_LOOP_ENV_STATE_DIM,
                "env_state",
            ),
        )
        if not self.image_lineage:
            raise ValueError("initial observation must include camera lineage")
        names = [item.camera_name for item in self.image_lineage]
        if len(names) != len(set(names)):
            raise ValueError("initial observation camera lineage contains duplicates")

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_step_id": int(self.action_step_id),
            "observation_step_id": int(self.observation_step_id),
            "hdf5_observation_index": int(self.hdf5_observation_index),
            "qpos": self.qpos.tolist(),
            "qvel": self.qvel.tolist(),
            "env_state": self.env_state.tolist(),
            "image_lineage": [item.as_dict() for item in self.image_lineage],
        }


@dataclass(frozen=True)
class RecordedReturnTargetCondition:
    """One immutable original or alternate Return envelope."""

    target_role: str
    segment_id: str
    token_source: str
    token_sha256: str
    token: np.ndarray

    def __post_init__(self) -> None:
        if self.target_role not in {"original", "alternate"}:
            raise ValueError("target_role must be original or alternate")
        if not self.segment_id.startswith("return:"):
            raise ValueError("target segment must be Return")
        if not self.token_source:
            raise ValueError("target token source must be non-empty")
        token = _frozen_vector(self.token, RETURN_TOKEN_DIM, "Return target token")
        actual_sha = _token_sha256(token)
        if self.token_sha256 != actual_sha:
            raise ValueError("Return target token SHA does not match token values")
        object.__setattr__(self, "token", token)

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_role": self.target_role,
            "segment_id": self.segment_id,
            "token_source": self.token_source,
            "token_sha256": self.token_sha256,
            "model_token_key": RETURN_TOKEN_KEY,
            "token": self.token.tolist(),
        }


@dataclass(frozen=True)
class RecordedReturnClosedLoopFixture:
    """One frozen initial state and its two real recorded target conditions."""

    fixture_id: str
    evidence_role: str
    source_segment_id: str
    expected_classification: str
    initial_observation: RecordedReturnInitialObservation
    original_target: RecordedReturnTargetCondition
    alternate_target: RecordedReturnTargetCondition

    def __post_init__(self) -> None:
        if self.fixture_id not in {"F1", "N1", "F2", "N2"}:
            raise ValueError("fixture_id must be one of F1/N1/F2/N2")
        if self.original_target.target_role != "original":
            raise ValueError("fixture original target role is invalid")
        if self.alternate_target.target_role != "alternate":
            raise ValueError("fixture alternate target role is invalid")
        if self.original_target.segment_id != self.source_segment_id:
            raise ValueError("fixture source segment and original target disagree")
        if self.original_target.token_sha256 == self.alternate_target.token_sha256:
            raise ValueError("fixture original and alternate targets must differ")

    def target(self, target_role: str) -> RecordedReturnTargetCondition:
        if target_role == "original":
            return self.original_target
        if target_role == "alternate":
            return self.alternate_target
        raise KeyError(target_role)

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "evidence_role": self.evidence_role,
            "source_segment_id": self.source_segment_id,
            "expected_classification": self.expected_classification,
            "initial_observation": self.initial_observation.as_dict(),
            "targets": {
                "original": self.original_target.as_dict(),
                "alternate": self.alternate_target.as_dict(),
            },
        }


@dataclass(frozen=True)
class RecordedReturnClosedLoopFixtureSet:
    """JSON-ready immutable lineage for the complete four-state fixture set."""

    schema: str
    camera_names: tuple[str, ...]
    source_lineage: Mapping[str, Any]
    fixtures: tuple[RecordedReturnClosedLoopFixture, ...]

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise ValueError("recorded Return fixture schema mismatch")
        if not self.camera_names or len(self.camera_names) != len(
            set(self.camera_names)
        ):
            raise ValueError("fixture camera order is invalid")
        if [fixture.fixture_id for fixture in self.fixtures] != [
            "F1",
            "N1",
            "F2",
            "N2",
        ]:
            raise ValueError("fixture set must contain F1/N1/F2/N2 in frozen order")
        expected_evidence = (
            ("F1", "offline_failed", "goal_response_invalid"),
            ("N1", "offline_normal", "goal_response_plausible"),
            ("F2", "offline_failed", "goal_response_invalid"),
            ("N2", "offline_normal", "goal_response_plausible"),
        )
        actual_evidence = tuple(
            (
                fixture.fixture_id,
                fixture.evidence_role,
                fixture.expected_classification,
            )
            for fixture in self.fixtures
        )
        if actual_evidence != expected_evidence:
            raise ValueError("fixture set evidence roles/classifications drifted")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "camera_names": list(self.camera_names),
            "source_lineage": dict(self.source_lineage),
            "fixtures": [fixture.as_dict() for fixture in self.fixtures],
        }


def load_frozen_recorded_return_closed_loop_fixture_set(
    *,
    stage_a_v3_root: str | Path,
    camera_names: Sequence[str] = FROZEN_RETURN_CAMERA_ORDER,
) -> RecordedReturnClosedLoopFixtureSet:
    """Load exactly the four published Strict-18 Stage-A v3 Return fixtures."""

    root = Path(stage_a_v3_root).expanduser().resolve(strict=True)
    manifest = _read_mapping(
        (root / "manifest.json").resolve(strict=True),
        "Stage-A v3 manifest",
    )
    _validate_published_stage_a_v3_manifest(manifest)
    return build_recorded_return_closed_loop_fixture_set(
        stage_a_v3_root=root,
        fixture_specs=FROZEN_RETURN_FIXTURE_SPECS,
        camera_names=camera_names,
    )


def build_recorded_return_closed_loop_fixture_set(
    *,
    stage_a_v3_root: str | Path,
    fixture_specs: Sequence[RecordedReturnFixtureSpec],
    camera_names: Sequence[str],
) -> RecordedReturnClosedLoopFixtureSet:
    """Strictly join an explicit fixture specification to immutable source data.

    The configurable spec argument exists for focused contract tests and future
    versioned fixture sets.  Production callers use the frozen wrapper above.
    """

    specs = tuple(fixture_specs)
    if [item.fixture_id for item in specs] != ["F1", "N1", "F2", "N2"]:
        raise ValueError("fixture specs must contain F1/N1/F2/N2 in frozen order")
    names = tuple(str(name) for name in camera_names)
    if not names or len(names) != len(set(names)):
        raise ValueError("camera_names must be a unique non-empty order")
    root = Path(stage_a_v3_root).expanduser().resolve(strict=True)
    manifest_path = (root / "manifest.json").resolve(strict=True)
    return_path = (root / "return.json").resolve(strict=True)
    manifest = _read_mapping(manifest_path, "Stage-A v3 manifest")
    return_payload = _read_mapping(return_path, "Stage-A v3 Return result")
    source_lineage = _mapping(manifest.get("source_lineage"), "source_lineage")
    hdf5_path = _verified_lineage_path(source_lineage, "rollout_hdf5")
    jsonl_path = _verified_lineage_path(source_lineage, "rollout_jsonl")
    _validate_manifest_camera_order(manifest, names)

    frames = join_recorded_act_replay_frames(
        rollout_hdf5_path=hdf5_path,
        rollout_jsonl_path=jsonl_path,
        skills=("return",),
    )
    segments = split_stable_recorded_act_segments(frames)
    segment_by_id = {segment.segment_id: segment for segment in segments}
    if len(segment_by_id) != len(segments):
        raise ValueError("source Return segment inventory contains duplicate ids")
    artifact_records = _artifact_records_by_segment(return_payload)
    jsonl_rows = _read_jsonl(jsonl_path)

    fixtures: list[RecordedReturnClosedLoopFixture] = []
    with h5py.File(hdf5_path, "r") as handle:
        recorded_reset_context = _validate_hdf5_source_contract(handle, names)
        if "observations/env_state" not in handle:
            raise KeyError("source rollout HDF5 is missing observations/env_state")
        for spec in specs:
            segment = _required_segment(segment_by_id, spec.source_segment_id)
            alternate = _required_segment(segment_by_id, spec.alternate_segment_id)
            record = artifact_records.get(spec.source_segment_id)
            if record is None:
                raise ValueError(
                    f"Stage-A v3 is missing fixture segment {spec.source_segment_id}"
                )
            _validate_artifact_pair(
                record, spec=spec, original=segment, alternate=alternate
            )
            frame = segment.frames[0]
            if frame.action_step_id != spec.start_action_step_id:
                raise ValueError("fixture source segment start action step drifted")
            if frame.observation_step_id != spec.observation_step_id:
                raise ValueError("fixture pre-action observation step drifted")
            observation = _read_initial_observation(
                handle=handle,
                rows=jsonl_rows,
                frame=frame,
                camera_names=names,
            )
            fixtures.append(
                RecordedReturnClosedLoopFixture(
                    fixture_id=spec.fixture_id,
                    evidence_role=spec.evidence_role,
                    source_segment_id=spec.source_segment_id,
                    expected_classification=spec.expected_classification,
                    initial_observation=observation,
                    original_target=_target_condition("original", segment),
                    alternate_target=_target_condition("alternate", alternate),
                )
            )

    lineage = {
        "stage_a_v3_manifest": _file_identity(manifest_path),
        "stage_a_v3_return": _file_identity(return_path),
        "rollout_hdf5": _file_identity(hdf5_path),
        "rollout_jsonl": _file_identity(jsonl_path),
        "observation_alignment": "action_step_uses_immediately_preceding_hdf5_observation",
        "model_token_key": RETURN_TOKEN_KEY,
        "recorded_reset_context": recorded_reset_context,
    }
    return RecordedReturnClosedLoopFixtureSet(
        schema=SCHEMA,
        camera_names=names,
        source_lineage=lineage,
        fixtures=tuple(fixtures),
    )


def _read_initial_observation(
    *,
    handle: Any,
    rows: Sequence[Mapping[str, Any]],
    frame: Any,
    camera_names: tuple[str, ...],
) -> RecordedReturnInitialObservation:
    index = int(frame.observation_hdf5_index)
    if int(frame.jsonl_row_index) <= 0 or int(frame.jsonl_row_index) - 1 != index:
        raise ValueError("JSONL/HDF5 pre-action observation indices disagree")
    row = rows[index]
    if (
        _integer(row.get("step_id"), "JSONL observation step_id")
        != frame.observation_step_id
    ):
        raise ValueError("JSONL pre-action observation step id disagrees with HDF5")
    qpos = _frozen_vector(handle["observations/qpos"][index], 4, "HDF5 qpos")
    qvel = _frozen_vector(handle["observations/qvel"][index], 4, "HDF5 qvel")
    env_state = _frozen_vector(
        handle["observations/env_state"][index],
        RETURN_CLOSED_LOOP_ENV_STATE_DIM,
        "HDF5 env_state",
    )
    _require_row_vector(row, "qpos", qpos)
    _require_row_vector(row, "qvel", qvel)
    _require_row_vector(row, "env_state", env_state)
    image_lineage: list[RecordedReturnImageLineage] = []
    for camera_name in camera_names:
        encoded_path = f"observations/encoded_images/{camera_name}"
        if encoded_path not in handle:
            raise ValueError(
                f"recorded camera {camera_name!r} is not stored as encoded JPEG"
            )
        encoded = encoded_frame_to_uint8(handle[encoded_path][index])
        image = np.asarray(read_camera_rgb(handle, camera_name, index), dtype=np.uint8)
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("recorded camera image is not HWC RGB")
        image_lineage.append(
            RecordedReturnImageLineage(
                camera_name=camera_name,
                shape=tuple(int(value) for value in image.shape),
                encoded_jpeg_size_bytes=int(encoded.size),
                encoded_jpeg_sha256=hashlib.sha256(
                    encoded.tobytes(order="C")
                ).hexdigest(),
                rgb_sha256=hashlib.sha256(image.tobytes(order="C")).hexdigest(),
            )
        )
    return RecordedReturnInitialObservation(
        action_step_id=int(frame.action_step_id),
        observation_step_id=int(frame.observation_step_id),
        hdf5_observation_index=index,
        qpos=qpos,
        qvel=qvel,
        env_state=env_state,
        image_lineage=tuple(image_lineage),
    )


def _target_condition(
    role: str,
    segment: RecordedActReplaySegment,
) -> RecordedReturnTargetCondition:
    if segment.model_token_key != RETURN_TOKEN_KEY or segment.token is None:
        raise ValueError("Return fixture segment has no canonical model token")
    if segment.token_sha256 is None or not segment.token_source:
        raise ValueError("Return fixture segment has incomplete token lineage")
    return RecordedReturnTargetCondition(
        target_role=role,
        segment_id=segment.segment_id,
        token_source=segment.token_source,
        token_sha256=segment.token_sha256,
        token=segment.token,
    )


def _validate_artifact_pair(
    record: Mapping[str, Any],
    *,
    spec: RecordedReturnFixtureSpec,
    original: RecordedActReplaySegment,
    alternate: RecordedActReplaySegment,
) -> None:
    recorded_original = _mapping(record.get("segment"), "Stage-A segment")
    recorded_alternate = _mapping(
        record.get("alternate_segment"), "Stage-A alternate segment"
    )
    if str(recorded_original.get("segment_id", "")) != spec.source_segment_id:
        raise ValueError("Stage-A original segment identity drifted")
    if str(recorded_alternate.get("segment_id", "")) != spec.alternate_segment_id:
        raise ValueError("Stage-A alternate segment identity drifted")
    for payload, segment, label in (
        (recorded_original, original, "original"),
        (recorded_alternate, alternate, "alternate"),
    ):
        recorded_sha = str(payload.get("token_sha256", ""))
        if recorded_sha and recorded_sha != segment.token_sha256:
            raise ValueError(f"Stage-A {label} token SHA drifted")
    result = _mapping(record.get("result"), "Stage-A pair result")
    conditions = _mapping(result.get("conditions"), "Stage-A pair conditions")
    alternates = [value for key, value in conditions.items() if key != "recorded_token"]
    if len(alternates) != 1:
        raise ValueError("Stage-A pair must contain exactly one alternate condition")
    alternate_result = _mapping(alternates[0], "Stage-A alternate result")
    if str(alternate_result.get("classification", "")) != spec.expected_classification:
        raise ValueError(
            "Stage-A fixture classification disagrees with frozen specification"
        )


def _artifact_records_by_segment(
    payload: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    if str(payload.get("primitive", "")) != "return":
        raise ValueError("Stage-A primitive result is not Return")
    records = payload.get("segment_pair_records")
    if not isinstance(records, list) or not records:
        raise ValueError("Stage-A Return result has no segment_pair_records")
    result: dict[str, Mapping[str, Any]] = {}
    for raw in records:
        record = _mapping(raw, "Stage-A pair record")
        segment = _mapping(record.get("segment"), "Stage-A segment")
        segment_id = str(segment.get("segment_id", ""))
        if not segment_id or segment_id in result:
            raise ValueError("Stage-A pair segment identity is missing or duplicated")
        result[segment_id] = record
    return result


def _required_segment(
    segments: Mapping[str, RecordedActReplaySegment], segment_id: str
) -> RecordedActReplaySegment:
    try:
        return segments[segment_id]
    except KeyError as exc:
        raise ValueError(
            f"source rollout is missing frozen Return segment {segment_id}"
        ) from exc


def _validate_manifest_camera_order(
    manifest: Mapping[str, Any], names: tuple[str, ...]
) -> None:
    instances = _mapping(manifest.get("inference_instances"), "inference_instances")
    baseline = _mapping(instances.get("baseline_replica_a"), "baseline_replica_a")
    recorded = tuple(str(value) for value in baseline.get("camera_names", ()))
    if recorded != names:
        raise ValueError(
            "requested camera order disagrees with Stage-A inference order"
        )


def _validate_published_stage_a_v3_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema") != STAGE_A_MANIFEST_SCHEMA:
        raise ValueError("Stage-A v3 manifest schema mismatch")
    if manifest.get("status") != "completed":
        raise ValueError("Stage-A v3 manifest is not completed")
    if manifest.get("evidence_kind") != STAGE_A_EVIDENCE_KIND:
        raise ValueError("Stage-A v3 manifest evidence kind mismatch")
    if manifest.get("diagnostic_only") is not True:
        raise ValueError("Stage-A v3 manifest is not diagnostic-only")
    if manifest.get("promotion_eligible") is not False:
        raise ValueError("Stage-A v3 manifest is promotion-eligible")
    if manifest.get("closed_loop_claim") is not False:
        raise ValueError("Stage-A v3 manifest has a closed-loop claim")


def _validate_hdf5_source_contract(
    handle: Any, names: tuple[str, ...]
) -> dict[str, Any]:
    metadata = dict(handle["metadata"].attrs) if "metadata" in handle else {}
    recorded = tuple(camera_names_from_metadata(metadata))
    if recorded != names:
        raise ValueError("requested camera order disagrees with source HDF5 metadata")
    expected_text_orders = {
        "action_order": RETURN_ACTION_ORDER,
        "qpos_order": RETURN_QPOS_ORDER,
        "qvel_order": RETURN_QVEL_ORDER,
    }
    for key, expected in expected_text_orders.items():
        value = _metadata_text(metadata.get(key))
        actual = tuple(item.strip() for item in value.split(",") if item.strip())
        if actual != expected:
            raise ValueError(f"source HDF5 {key} disagrees with frozen order")
    if (
        _metadata_text(metadata.get("env_state_contract_version"))
        != RETURN_CLOSED_LOOP_ENV_STATE_CONTRACT
    ):
        raise ValueError("source HDF5 env_state contract is not 107-D v2.4")
    if _metadata_text(metadata.get("image_format")).lower() != "jpeg":
        raise ValueError("source HDF5 image format is not JPEG")
    scene_id = _metadata_text(metadata.get("unity_scene_id"))
    runtime_build_id = _metadata_text(metadata.get("runtime_build_id"))
    if not scene_id or not runtime_build_id:
        raise ValueError("source HDF5 lacks Unity scene/runtime identity")
    reset_seed = _integer(metadata.get("seed"), "source HDF5 reset seed")
    return {
        "unity_scene_id": scene_id,
        "runtime_build_id": runtime_build_id,
        "reset_seed": reset_seed,
        "soil_preset_id": _metadata_text(metadata.get("soil_preset_id")) or "unknown",
        "env_state_contract_version": RETURN_CLOSED_LOOP_ENV_STATE_CONTRACT,
        "action_order": list(RETURN_ACTION_ORDER),
        "qpos_order": list(RETURN_QPOS_ORDER),
        "qvel_order": list(RETURN_QVEL_ORDER),
        "terrain_observation_dim": RETURN_CLOSED_LOOP_ENV_STATE_DIM,
        "full_terrain_snapshot_recorded": False,
        "deterministic_soil_seed_recorded": False,
        "terrain_restore_evidence": "observable_metrics_only_not_restorable",
    }


def _verified_lineage_path(source: Mapping[str, Any], key: str) -> Path:
    identity = _mapping(source.get(key), key)
    path = Path(str(identity.get("path", ""))).expanduser().resolve(strict=True)
    expected_sha = str(identity.get("sha256", ""))
    _require_sha256(expected_sha, f"{key} sha256")
    if _sha256_file(path) != expected_sha:
        raise ValueError(f"{key} SHA does not match Stage-A source lineage")
    return path


def _require_row_vector(row: Mapping[str, Any], key: str, expected: np.ndarray) -> None:
    actual = _frozen_vector(row.get(key), expected.size, f"JSONL {key}")
    if not np.allclose(actual, expected, rtol=0.0, atol=1.0e-6):
        raise ValueError(f"JSONL/HDF5 pre-action {key} values disagree")


def _read_jsonl(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid rollout JSONL line {line_number}") from exc
        rows.append(_mapping(value, f"rollout JSONL line {line_number}"))
    if not rows:
        raise ValueError("rollout JSONL is empty")
    return rows


def _read_mapping(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    return _mapping(value, label)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _frozen_vector(value: Any, width: int | None, label: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float32).reshape(-1)
    if width is not None and array.shape != (width,):
        raise ValueError(f"{label} must have shape ({width},)")
    if width is None and array.size < 1:
        raise ValueError(f"{label} must be non-empty")
    if not np.isfinite(array).all():
        raise ValueError(f"{label} contains non-finite values")
    array = array.copy()
    array.setflags(write=False)
    return array


def _token_sha256(token: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(token, dtype="<f4").tobytes(order="C")).hexdigest()


def _file_identity(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be lowercase SHA-256")


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    return result


def _metadata_text(value: Any) -> str:
    if isinstance(value, (bytes, np.bytes_)):
        return value.decode("utf-8", errors="strict").strip()
    return str(value).strip() if value is not None else ""


__all__ = [
    "FROZEN_RETURN_CAMERA_ORDER",
    "FROZEN_RETURN_FIXTURE_SPECS",
    "RETURN_ACTION_ORDER",
    "RETURN_CLOSED_LOOP_ENV_STATE_CONTRACT",
    "RETURN_CLOSED_LOOP_ENV_STATE_DIM",
    "RETURN_QPOS_ORDER",
    "RETURN_QVEL_ORDER",
    "RecordedReturnClosedLoopFixture",
    "RecordedReturnClosedLoopFixtureSet",
    "RecordedReturnFixtureSpec",
    "RecordedReturnImageLineage",
    "RecordedReturnInitialObservation",
    "RecordedReturnTargetCondition",
    "build_recorded_return_closed_loop_fixture_set",
    "load_frozen_recorded_return_closed_loop_fixture_set",
]
