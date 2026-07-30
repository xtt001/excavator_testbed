"""Fail-closed consumption of Unity-generated conservative 3D sweep evidence."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np

COVERAGE_WORKTOOL_SWEEP_LIBRARY_SCHEMA = (
    "coverage_worktool_sweep_library_v1"
)
UNITY_KINEMATIC_CONVEX_COVER_WORKTOOL_SWEEP_PROFILE = (
    "unity_kinematic_convex_cover_worktool_sweep_v1"
)
WORKTOOL_3D_CLEARANCE_BELOW_MINIMUM = (
    "worktool_3d_clearance_below_minimum"
)
WORKTOOL_3D_GEOMETRY_MISSING = "worktool_3d_geometry_missing"
NO_3D_WALL_SAFE_CORRIDOR_REASON = "no_3d_wall_safe_corridor"
CALIBRATED_ACT_TRACKING_MARGIN_M = 0.05
CALIBRATED_HARD_CLEARANCE_M = 0.24
CALIBRATED_POSE_INTERPOLATION_BOUND_M = 0.01
TRACKING_CALIBRATION_PROFILE = (
    "episode_168_bounded_live_wall_clearance_loss_v1"
)
TRACKING_CALIBRATION_ARTIFACT_SCHEMA = (
    "expert_act_tracking_margin_recommendation_v2"
)
TRACKING_CALIBRATION_ARTIFACT_SHA256 = (
    "1a2164c345b60fdae6c211b2152fd3d22246282615857edea6785a90283e025e"
)
_QPOS_ORDER = (
    "swing_position_norm",
    "boom_position_norm",
    "stick_position_norm",
    "bucket_position_norm",
)
_LINK_NAMES = frozenset({"boom", "stick", "bucket"})
_WALL_NAMES = frozenset(
    {
        "Dig_XMin_Board",
        "Dig_XMax_Board",
        "Dig_ZMin_Board",
        "Dig_ZMax_Board",
    }
)


class CoverageWorktoolSweepContractError(ValueError):
    """Raised when a configured companion artifact cannot be trusted."""


@dataclass(frozen=True)
class CoverageWorktoolSweepConfig:
    """Central exact contract for the final 3D wall-clearance gate."""

    enabled: bool = False
    profile: str = UNITY_KINEMATIC_CONVEX_COVER_WORKTOOL_SWEEP_PROFILE
    hard_clearance_m: float = CALIBRATED_HARD_CLEARANCE_M
    act_tracking_margin_m: float = CALIBRATED_ACT_TRACKING_MARGIN_M
    pose_interpolation_bound_m: float = (
        CALIBRATED_POSE_INTERPOLATION_BOUND_M
    )
    artifact_path: str = ""
    artifact_sha256: str = ""
    execution_library_sha256: str = ""
    pose_library_sha256: str = ""
    missing_contract: str = "fail_closed"

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any] | None,
    ) -> CoverageWorktoolSweepConfig:
        mapping = dict(values or {})
        config = cls(
            enabled=bool(mapping.get("enabled", False)),
            profile=str(
                mapping.get(
                    "profile",
                    UNITY_KINEMATIC_CONVEX_COVER_WORKTOOL_SWEEP_PROFILE,
                )
            ).strip(),
            hard_clearance_m=float(
                mapping.get(
                    "hard_clearance_m",
                    CALIBRATED_HARD_CLEARANCE_M,
                )
            ),
            act_tracking_margin_m=float(
                mapping.get(
                    "act_tracking_margin_m",
                    CALIBRATED_ACT_TRACKING_MARGIN_M,
                )
            ),
            pose_interpolation_bound_m=float(
                mapping.get(
                    "pose_interpolation_bound_m",
                    CALIBRATED_POSE_INTERPOLATION_BOUND_M,
                )
            ),
            artifact_path=str(mapping.get("artifact_path", "")).strip(),
            artifact_sha256=str(
                mapping.get("artifact_sha256", "")
            ).strip().lower(),
            execution_library_sha256=str(
                mapping.get("execution_library_sha256", "")
            ).strip().lower(),
            pose_library_sha256=str(
                mapping.get("pose_library_sha256", "")
            ).strip().lower(),
            missing_contract=str(
                mapping.get("missing_contract", "fail_closed")
            ).strip(),
        )
        config.validate()
        return config

    def validate(self) -> None:
        numeric = (
            self.hard_clearance_m,
            self.act_tracking_margin_m,
            self.pose_interpolation_bound_m,
        )
        if not all(math.isfinite(float(value)) for value in numeric):
            raise ValueError(
                "coverage worktool_sweep_3d margins must be finite"
            )
        if any(float(value) < 0.0 for value in numeric):
            raise ValueError(
                "coverage worktool_sweep_3d margins must be non-negative"
            )
        if self.missing_contract != "fail_closed":
            raise ValueError(
                "coverage worktool_sweep_3d missing_contract must be "
                "'fail_closed'"
            )
        if not self.enabled:
            return
        if (
            self.profile
            != UNITY_KINEMATIC_CONVEX_COVER_WORKTOOL_SWEEP_PROFILE
        ):
            raise ValueError(
                "coverage worktool_sweep_3d profile must be "
                f"{UNITY_KINEMATIC_CONVEX_COVER_WORKTOOL_SWEEP_PROFILE!r}"
            )
        if not self.artifact_path:
            raise ValueError(
                "coverage worktool_sweep_3d enabled=true requires artifact_path"
            )
        for name, value in (
            ("artifact_sha256", self.artifact_sha256),
            ("execution_library_sha256", self.execution_library_sha256),
            ("pose_library_sha256", self.pose_library_sha256),
        ):
            _validate_sha256(value, label=f"worktool_sweep_3d.{name}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "profile": str(self.profile),
            "hard_clearance_m": float(self.hard_clearance_m),
            "act_tracking_margin_m": float(self.act_tracking_margin_m),
            "pose_interpolation_bound_m": float(
                self.pose_interpolation_bound_m
            ),
            "artifact_path": str(self.artifact_path),
            "artifact_sha256": str(self.artifact_sha256),
            "execution_library_sha256": str(
                self.execution_library_sha256
            ),
            "pose_library_sha256": str(self.pose_library_sha256),
            "missing_contract": str(self.missing_contract),
        }


@dataclass(frozen=True)
class CoverageWorktoolSweepEvaluation:
    """One immutable 3D gate decision and its closest-distance witness."""

    profile: str
    eligible: bool
    rejection_reason: str
    exemplar_id: str
    raw_fields_sha256: str
    artifact_sha256: str
    sampled_convex_cover_clearance_m: float
    pose_interpolation_margin_m: float
    act_tracking_margin_m: float
    live_start_displacement_bound_m: float
    effective_clearance_m: float
    hard_clearance_m: float
    closest_link_name: str = ""
    closest_shape_name: str = ""
    closest_wall_name: str = ""
    closest_pose_index: int = -1
    closest_qpos: tuple[float, ...] = ()
    closest_worktool_point_world_m: tuple[float, ...] = ()
    closest_wall_point_world_m: tuple[float, ...] = ()

    @classmethod
    def invalid(
        cls,
        *,
        config: CoverageWorktoolSweepConfig,
        exemplar_id: str,
        raw_fields_sha256: str,
    ) -> CoverageWorktoolSweepEvaluation:
        return cls(
            profile=str(config.profile),
            eligible=False,
            rejection_reason=WORKTOOL_3D_GEOMETRY_MISSING,
            exemplar_id=str(exemplar_id),
            raw_fields_sha256=str(raw_fields_sha256),
            artifact_sha256=str(config.artifact_sha256),
            sampled_convex_cover_clearance_m=-1.0,
            pose_interpolation_margin_m=float(
                config.pose_interpolation_bound_m
            ),
            act_tracking_margin_m=float(config.act_tracking_margin_m),
            live_start_displacement_bound_m=-1.0,
            effective_clearance_m=-1.0,
            hard_clearance_m=float(config.hard_clearance_m),
        )

    def as_trace_fields(self) -> dict[str, Any]:
        return {
            "worktool_sweep_3d_profile": str(self.profile),
            "worktool_sweep_3d_eligible": int(self.eligible),
            "worktool_sweep_3d_rejection_reason": str(
                self.rejection_reason
            ),
            "worktool_sweep_3d_artifact_sha256": str(
                self.artifact_sha256
            ),
            "worktool_sweep_3d_sampled_convex_cover_clearance_m": float(
                self.sampled_convex_cover_clearance_m
            ),
            "worktool_sweep_3d_pose_interpolation_margin_m": float(
                self.pose_interpolation_margin_m
            ),
            "worktool_sweep_3d_act_tracking_margin_m": float(
                self.act_tracking_margin_m
            ),
            "worktool_sweep_3d_live_start_displacement_bound_m": float(
                self.live_start_displacement_bound_m
            ),
            "worktool_sweep_3d_effective_clearance_m": float(
                self.effective_clearance_m
            ),
            "worktool_sweep_3d_hard_clearance_m": float(
                self.hard_clearance_m
            ),
            "worktool_sweep_3d_closest_link": str(
                self.closest_link_name
            ),
            "worktool_sweep_3d_closest_shape": str(
                self.closest_shape_name
            ),
            "worktool_sweep_3d_closest_wall": str(
                self.closest_wall_name
            ),
            "worktool_sweep_3d_closest_pose_index": int(
                self.closest_pose_index
            ),
            "worktool_sweep_3d_closest_qpos": list(self.closest_qpos),
            "worktool_sweep_3d_closest_worktool_point_world_m": list(
                self.closest_worktool_point_world_m
            ),
            "worktool_sweep_3d_closest_wall_point_world_m": list(
                self.closest_wall_point_world_m
            ),
        }


@dataclass(frozen=True)
class _LinkSweep:
    link_name: str
    sampled_clearance_m: float
    joint_motion_radius_m: tuple[float, ...]
    closest: MappingProxyType[str, Any]
    wall_sweeps: tuple[_WallSweep, ...]


@dataclass(frozen=True)
class _WallSweep:
    wall_name: str
    sampled_clearance_m: float
    closest: MappingProxyType[str, Any]


@dataclass(frozen=True)
class _SweepRecord:
    exemplar_id: str
    raw_fields_sha256: str
    exemplar_start_qpos: tuple[float, ...]
    geometry_valid: bool
    link_sweeps: tuple[_LinkSweep, ...]


@dataclass(frozen=True)
class CoverageWorktoolSweepService:
    """Evaluate per-exemplar Unity clearance with a live-start motion bound."""

    config: CoverageWorktoolSweepConfig
    raw_range_rad: tuple[float, ...]
    records: MappingProxyType[str, _SweepRecord]

    @classmethod
    def from_config(
        cls,
        config: CoverageWorktoolSweepConfig,
    ) -> CoverageWorktoolSweepService:
        if not config.enabled:
            raise CoverageWorktoolSweepContractError(
                "worktool_sweep_3d_runtime_disabled"
            )
        path = Path(config.artifact_path).expanduser().resolve()
        if not path.is_file():
            raise CoverageWorktoolSweepContractError(
                f"worktool_sweep_3d_artifact_missing:{path}"
            )
        payload = path.read_bytes()
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if actual_sha256 != config.artifact_sha256:
            raise CoverageWorktoolSweepContractError(
                "worktool_sweep_3d_artifact_sha256_mismatch:"
                f"expected={config.artifact_sha256}:actual={actual_sha256}"
            )
        try:
            artifact = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise CoverageWorktoolSweepContractError(
                f"worktool_sweep_3d_json:{exc}"
            ) from exc
        raw_range, records = _parse_artifact(artifact, config=config)
        return cls(
            config=config,
            raw_range_rad=raw_range,
            records=MappingProxyType(records),
        )

    def evaluate(
        self,
        *,
        exemplar_id: str,
        raw_fields_sha256: str,
        live_start_qpos: Any,
    ) -> CoverageWorktoolSweepEvaluation:
        exemplar = str(exemplar_id)
        raw_sha = str(raw_fields_sha256).strip().lower()
        record = self.records.get(exemplar)
        if (
            record is None
            or record.raw_fields_sha256 != raw_sha
            or not record.geometry_valid
            or not record.link_sweeps
        ):
            return CoverageWorktoolSweepEvaluation.invalid(
                config=self.config,
                exemplar_id=exemplar,
                raw_fields_sha256=raw_sha,
            )
        qpos = _validated_live_qpos(live_start_qpos)
        if qpos is None:
            return CoverageWorktoolSweepEvaluation.invalid(
                config=self.config,
                exemplar_id=exemplar,
                raw_fields_sha256=raw_sha,
            )

        evaluated: list[tuple[float, float, _LinkSweep]] = []
        raw_delta = np.abs(
            np.asarray(qpos, dtype=np.float64)
            - np.asarray(record.exemplar_start_qpos, dtype=np.float64)
        ) * np.asarray(self.raw_range_rad, dtype=np.float64)
        for link in record.link_sweeps:
            radii = np.asarray(
                link.joint_motion_radius_m,
                dtype=np.float64,
            )
            start_bound = float(
                np.sum(
                    2.0
                    * radii
                    * np.sin(np.minimum(raw_delta, math.pi) * 0.5)
                )
            )
            effective = float(
                link.sampled_clearance_m
                - self.config.pose_interpolation_bound_m
                - self.config.act_tracking_margin_m
                - start_bound
            )
            evaluated.append((effective, start_bound, link))
        effective, start_bound, closest_link = min(
            evaluated,
            key=lambda item: (item[0], item[2].link_name),
        )
        eligible = bool(
            effective + 1.0e-12 >= float(self.config.hard_clearance_m)
        )
        closest = closest_link.closest
        return CoverageWorktoolSweepEvaluation(
            profile=str(self.config.profile),
            eligible=eligible,
            rejection_reason=(
                ""
                if eligible
                else WORKTOOL_3D_CLEARANCE_BELOW_MINIMUM
            ),
            exemplar_id=exemplar,
            raw_fields_sha256=raw_sha,
            artifact_sha256=str(self.config.artifact_sha256),
            sampled_convex_cover_clearance_m=float(
                closest_link.sampled_clearance_m
            ),
            pose_interpolation_margin_m=float(
                self.config.pose_interpolation_bound_m
            ),
            act_tracking_margin_m=float(
                self.config.act_tracking_margin_m
            ),
            live_start_displacement_bound_m=float(start_bound),
            effective_clearance_m=float(effective),
            hard_clearance_m=float(self.config.hard_clearance_m),
            closest_link_name=str(closest_link.link_name),
            closest_shape_name=str(closest.get("shape_name", "")),
            closest_wall_name=str(closest.get("wall_name", "")),
            closest_pose_index=int(closest.get("pose_index", -1)),
            closest_qpos=_finite_tuple(closest.get("qpos", ()), expected=4),
            closest_worktool_point_world_m=_finite_tuple(
                closest.get("worktool_point_world_m", ()),
                expected=3,
            ),
            closest_wall_point_world_m=_finite_tuple(
                closest.get("wall_point_world_m", ()),
                expected=3,
            ),
        )


def _parse_artifact(
    value: Any,
    *,
    config: CoverageWorktoolSweepConfig,
) -> tuple[tuple[float, ...], dict[str, _SweepRecord]]:
    if not isinstance(value, Mapping):
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_root_not_mapping"
        )
    if (
        str(value.get("schema", ""))
        != COVERAGE_WORKTOOL_SWEEP_LIBRARY_SCHEMA
        or str(value.get("status", "")) != "completed"
        or str(value.get("profile", "")) != config.profile
    ):
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_schema_status_profile"
        )
    source_lock = value.get("source_lock")
    if not isinstance(source_lock, Mapping):
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_source_lock_missing"
        )
    if (
        str(source_lock.get("execution_library_sha256", "")).lower()
        != config.execution_library_sha256
        or str(source_lock.get("pose_library_sha256", "")).lower()
        != config.pose_library_sha256
    ):
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_source_sha_drift"
        )
    for required in (
        "scene_sha256",
        "prefab_sha256",
        "normalization_sha256",
        "predictor_code_sha256",
    ):
        _validate_sha256(
            source_lock.get(required),
            label=f"source_lock.{required}",
            error_type=CoverageWorktoolSweepContractError,
        )
    meshes = source_lock.get("mesh_sha256")
    if not isinstance(meshes, Mapping) or set(meshes) != _LINK_NAMES:
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_mesh_lock_missing"
        )
    for link_name, digest in meshes.items():
        _validate_sha256(
            digest,
            label=f"mesh_sha256.{link_name}",
            error_type=CoverageWorktoolSweepContractError,
        )

    qpos_contract = value.get("qpos_contract")
    if not isinstance(qpos_contract, Mapping):
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_qpos_contract_missing"
        )
    if tuple(qpos_contract.get("order", ())) != _QPOS_ORDER:
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_qpos_order"
        )
    if tuple(qpos_contract.get("normalized_min", ())) != (0.0,) * 4 or tuple(
        qpos_contract.get("normalized_max", ())
    ) != (1.0,) * 4:
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_qpos_normalized_range"
        )
    raw_range = _finite_tuple(
        qpos_contract.get("raw_range_rad", ()),
        expected=4,
    )
    if any(value <= 0.0 for value in raw_range):
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_qpos_raw_range"
        )

    records_value = value.get("records")
    if not isinstance(records_value, Sequence) or isinstance(
        records_value,
        (str, bytes),
    ):
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_records_missing"
        )
    records: dict[str, _SweepRecord] = {}
    for raw_record in records_value:
        record = _parse_record(raw_record)
        if record.exemplar_id in records:
            raise CoverageWorktoolSweepContractError(
                f"worktool_sweep_3d_duplicate:{record.exemplar_id}"
            )
        records[record.exemplar_id] = record
    if int(value.get("sample_count", -1)) != len(records):
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_sample_count"
        )
    return raw_range, records


def _parse_record(value: Any) -> _SweepRecord:
    if not isinstance(value, Mapping):
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_record_not_mapping"
        )
    primitive_id = int(value.get("primitive_episode_id", -1))
    exemplar_id = str(value.get("exemplar_id", ""))
    if primitive_id < 0 or exemplar_id != f"episode_{primitive_id}":
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_exemplar_identity"
        )
    raw_fields_sha256 = _validate_sha256(
        value.get("raw_fields_sha256"),
        label="record.raw_fields_sha256",
        error_type=CoverageWorktoolSweepContractError,
    )
    _validate_sha256(
        value.get("pose_path_sha256"),
        label="record.pose_path_sha256",
        error_type=CoverageWorktoolSweepContractError,
    )
    exemplar_start_qpos = _finite_tuple(
        value.get("exemplar_start_qpos", ()),
        expected=4,
    )
    if any(item < 0.0 or item > 1.0 for item in exemplar_start_qpos):
        raise CoverageWorktoolSweepContractError(
            "worktool_sweep_3d_exemplar_start_qpos_range"
        )
    geometry_valid = bool(value.get("geometry_valid", False))
    sweeps: list[_LinkSweep] = []
    if geometry_valid:
        raw_sweeps = value.get("link_sweeps")
        if not isinstance(raw_sweeps, Sequence) or isinstance(
            raw_sweeps,
            (str, bytes),
        ):
            raise CoverageWorktoolSweepContractError(
                "worktool_sweep_3d_link_sweeps_missing"
            )
        for raw_link in raw_sweeps:
            if not isinstance(raw_link, Mapping):
                raise CoverageWorktoolSweepContractError(
                    "worktool_sweep_3d_link_sweep_not_mapping"
                )
            link_name = str(raw_link.get("link_name", ""))
            if link_name not in _LINK_NAMES:
                raise CoverageWorktoolSweepContractError(
                    "worktool_sweep_3d_link_name"
                )
            sampled = float(
                raw_link.get(
                    "sampled_convex_cover_clearance_m",
                    float("nan"),
                )
            )
            if not math.isfinite(sampled) or sampled < 0.0:
                raise CoverageWorktoolSweepContractError(
                    "worktool_sweep_3d_sampled_clearance"
                )
            radii = _finite_tuple(
                raw_link.get("joint_motion_radius_m", ()),
                expected=4,
            )
            if any(radius < 0.0 for radius in radii):
                raise CoverageWorktoolSweepContractError(
                    "worktool_sweep_3d_joint_motion_radius"
                )
            closest = raw_link.get("closest")
            if not isinstance(closest, Mapping):
                raise CoverageWorktoolSweepContractError(
                    "worktool_sweep_3d_closest_witness"
                )
            raw_wall_sweeps = raw_link.get("wall_sweeps")
            if not isinstance(raw_wall_sweeps, Sequence) or isinstance(
                raw_wall_sweeps,
                (str, bytes),
            ):
                raise CoverageWorktoolSweepContractError(
                    "worktool_sweep_3d_wall_sweeps_missing"
                )
            wall_sweeps: list[_WallSweep] = []
            for raw_wall in raw_wall_sweeps:
                if not isinstance(raw_wall, Mapping):
                    raise CoverageWorktoolSweepContractError(
                        "worktool_sweep_3d_wall_sweeps_not_mapping"
                    )
                wall_name = str(raw_wall.get("wall_name", ""))
                wall_sampled = float(
                    raw_wall.get(
                        "sampled_convex_cover_clearance_m",
                        float("nan"),
                    )
                )
                wall_closest = raw_wall.get("closest")
                if (
                    wall_name not in _WALL_NAMES
                    or not math.isfinite(wall_sampled)
                    or wall_sampled < 0.0
                    or not isinstance(wall_closest, Mapping)
                    or str(wall_closest.get("link_name", ""))
                    != link_name
                    or str(wall_closest.get("wall_name", ""))
                    != wall_name
                ):
                    raise CoverageWorktoolSweepContractError(
                        "worktool_sweep_3d_wall_sweeps_invalid"
                    )
                wall_sweeps.append(
                    _WallSweep(
                        wall_name=wall_name,
                        sampled_clearance_m=wall_sampled,
                        closest=MappingProxyType(dict(wall_closest)),
                    )
                )
            if {item.wall_name for item in wall_sweeps} != _WALL_NAMES:
                raise CoverageWorktoolSweepContractError(
                    "worktool_sweep_3d_wall_sweeps_require_four_walls"
                )
            sweeps.append(
                _LinkSweep(
                    link_name=link_name,
                    sampled_clearance_m=sampled,
                    joint_motion_radius_m=radii,
                    closest=MappingProxyType(dict(closest)),
                    wall_sweeps=tuple(wall_sweeps),
                )
            )
        if {item.link_name for item in sweeps} != _LINK_NAMES:
            raise CoverageWorktoolSweepContractError(
                "worktool_sweep_3d_requires_boom_stick_bucket"
            )
    return _SweepRecord(
        exemplar_id=exemplar_id,
        raw_fields_sha256=raw_fields_sha256,
        exemplar_start_qpos=exemplar_start_qpos,
        geometry_valid=geometry_valid,
        link_sweeps=tuple(sweeps),
    )


def _validated_live_qpos(value: Any) -> tuple[float, ...] | None:
    try:
        result = _finite_tuple(value, expected=4)
    except (TypeError, ValueError):
        return None
    if any(item < 0.0 or item > 1.0 for item in result):
        return None
    return result


def _finite_tuple(value: Any, *, expected: int) -> tuple[float, ...]:
    if isinstance(value, (str, bytes, Mapping)):
        raise TypeError("value must be a numeric sequence")
    try:
        result = tuple(float(item) for item in value)
    except TypeError as exc:
        raise TypeError("value must be a numeric sequence") from exc
    if len(result) != expected or not all(
        math.isfinite(item) for item in result
    ):
        raise ValueError(
            f"expected {expected} finite values, got {result!r}"
        )
    return result


def _validate_sha256(
    value: Any,
    *,
    label: str,
    error_type: type[Exception] = ValueError,
) -> str:
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise error_type(f"{label} must be a lowercase SHA256")
    return digest


__all__ = [
    "CALIBRATED_ACT_TRACKING_MARGIN_M",
    "CALIBRATED_HARD_CLEARANCE_M",
    "CALIBRATED_POSE_INTERPOLATION_BOUND_M",
    "COVERAGE_WORKTOOL_SWEEP_LIBRARY_SCHEMA",
    "NO_3D_WALL_SAFE_CORRIDOR_REASON",
    "TRACKING_CALIBRATION_ARTIFACT_SCHEMA",
    "TRACKING_CALIBRATION_ARTIFACT_SHA256",
    "TRACKING_CALIBRATION_PROFILE",
    "UNITY_KINEMATIC_CONVEX_COVER_WORKTOOL_SWEEP_PROFILE",
    "WORKTOOL_3D_CLEARANCE_BELOW_MINIMUM",
    "WORKTOOL_3D_GEOMETRY_MISSING",
    "CoverageWorktoolSweepConfig",
    "CoverageWorktoolSweepContractError",
    "CoverageWorktoolSweepEvaluation",
    "CoverageWorktoolSweepService",
]
