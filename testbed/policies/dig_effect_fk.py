"""Differentiable fixed-tooth forward kinematics from a frozen Unity artifact."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

FIXED_TIP_FK_ARTIFACT_SCHEMA = "fixed_tip_fk_artifact_v1"
FIXED_TIP_CANDIDATE_ID = "bucket_center_tooth_leading_edge_midpoint_v0_1"
QPOS_ORDER = ("swing", "boom", "stick", "bucket")


@dataclass(frozen=True)
class FixedTipFKFixture:
    normalized_qpos: tuple[float, float, float, float]
    fixed_tip_dig_area_xyz_m: tuple[float, float, float]


@dataclass(frozen=True)
class FixedTipFKContract:
    path: Path
    raw_qpos_min_rad: np.ndarray
    raw_qpos_max_rad: np.ndarray
    reference_normalized_qpos: np.ndarray
    reference_raw_qpos_rad: np.ndarray
    joint_direction_signs: np.ndarray
    joint_anchor_world_m: np.ndarray
    joint_axis_world: np.ndarray
    bucket_link_reference_world: np.ndarray
    fixed_tip_in_bucket_link_m: np.ndarray
    dig_area_world_to_local: np.ndarray
    fixtures: tuple[FixedTipFKFixture, ...]
    source_lock: dict[str, Any]


def load_fixed_tip_fk_artifact(path: str | Path) -> FixedTipFKContract:
    """Load and fail closed on a complete fixed-tooth FK contract."""
    resolved = Path(path).expanduser().resolve(strict=True)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixed tip FK artifact must contain an object")
    if payload.get("schema") != FIXED_TIP_FK_ARTIFACT_SCHEMA:
        raise ValueError(f"schema must be {FIXED_TIP_FK_ARTIFACT_SCHEMA}")
    if payload.get("status") != "completed":
        raise ValueError("fixed tip FK artifact must be completed")
    if payload.get("candidate_id") != FIXED_TIP_CANDIDATE_ID:
        raise ValueError("fixed tooth candidate identity mismatch")
    if tuple(payload.get("qpos_order", ())) != QPOS_ORDER:
        raise ValueError("fixed tip FK qpos order mismatch")

    raw_min = _vector(payload, "raw_qpos_min_rad", 4)
    raw_max = _vector(payload, "raw_qpos_max_rad", 4)
    reference_normalized = _vector(payload, "reference_normalized_qpos", 4)
    reference_raw = _vector(payload, "reference_raw_qpos_rad", 4)
    signs = _vector(payload, "joint_direction_signs", 4)
    anchors = _matrix(payload, "joint_anchor_world_m", (4, 3))
    axes = _matrix(payload, "joint_axis_world", (4, 3))
    bucket_world = _matrix(payload, "bucket_link_reference_world", (4, 4))
    tip_local = _vector(payload, "fixed_tip_in_bucket_link_m", 3)
    world_to_local = _matrix(payload, "dig_area_world_to_local", (4, 4))
    if np.any(raw_max <= raw_min):
        raise ValueError("raw qpos ranges must be increasing")
    if np.any(reference_normalized < 0.0) or np.any(reference_normalized > 1.0):
        raise ValueError("reference normalized qpos must be in [0, 1]")
    if not np.allclose(np.abs(signs), 1.0, atol=1.0e-6, rtol=0.0):
        raise ValueError("joint direction signs must be +/-1")
    axis_norm = np.linalg.norm(axes, axis=1)
    if not np.allclose(axis_norm, 1.0, atol=1.0e-5, rtol=0.0):
        raise ValueError("joint axes must be unit vectors")
    _validate_homogeneous(bucket_world, "bucket_link_reference_world")
    _validate_homogeneous(world_to_local, "dig_area_world_to_local")

    raw_fixtures = payload.get("fixtures")
    if not isinstance(raw_fixtures, list) or not raw_fixtures:
        raise ValueError("fixed tip FK artifact requires fixtures")
    fixtures: list[FixedTipFKFixture] = []
    for index, value in enumerate(raw_fixtures):
        if not isinstance(value, dict):
            raise ValueError(f"fixture {index} must be an object")
        qpos = _finite_array(
            value.get("normalized_qpos"), (4,), f"fixture {index} qpos"
        )
        tip = _finite_array(
            value.get("fixed_tip_dig_area_xyz_m"),
            (3,),
            f"fixture {index} tip",
        )
        if np.any(qpos < 0.0) or np.any(qpos > 1.0):
            raise ValueError(f"fixture {index} qpos must be in [0, 1]")
        fixtures.append(
            FixedTipFKFixture(
                normalized_qpos=tuple(float(item) for item in qpos),
                fixed_tip_dig_area_xyz_m=tuple(float(item) for item in tip),
            )
        )
    source_lock = payload.get("source_lock")
    if not isinstance(source_lock, dict) or not source_lock:
        raise ValueError("fixed tip FK artifact requires source_lock")
    return FixedTipFKContract(
        path=resolved,
        raw_qpos_min_rad=raw_min,
        raw_qpos_max_rad=raw_max,
        reference_normalized_qpos=reference_normalized,
        reference_raw_qpos_rad=reference_raw,
        joint_direction_signs=signs,
        joint_anchor_world_m=anchors,
        joint_axis_world=axes,
        bucket_link_reference_world=bucket_world,
        fixed_tip_in_bucket_link_m=tip_local,
        dig_area_world_to_local=world_to_local,
        fixtures=tuple(fixtures),
        source_lock=dict(source_lock),
    )


class DifferentiableFixedTipFK(torch.nn.Module):
    """Torch implementation of Unity's inert shadow-FK rotation chain."""

    def __init__(self, contract: FixedTipFKContract) -> None:
        super().__init__()
        self.contract = contract
        for name in (
            "raw_qpos_min_rad",
            "raw_qpos_max_rad",
            "reference_raw_qpos_rad",
            "joint_direction_signs",
            "joint_anchor_world_m",
            "joint_axis_world",
            "bucket_link_reference_world",
            "fixed_tip_in_bucket_link_m",
            "dig_area_world_to_local",
        ):
            self.register_buffer(
                name,
                torch.as_tensor(getattr(contract, name), dtype=torch.float32),
            )

    def forward(self, normalized_qpos: torch.Tensor) -> torch.Tensor:
        if normalized_qpos.shape[-1] != 4:
            raise ValueError("fixed tip FK requires qpos[...,4]")
        if not torch.is_floating_point(normalized_qpos):
            raise TypeError("fixed tip FK qpos must be floating point")
        original_shape = normalized_qpos.shape[:-1]
        qpos = normalized_qpos.reshape(-1, 4)
        raw = self.raw_qpos_min_rad + qpos * (
            self.raw_qpos_max_rad - self.raw_qpos_min_rad
        )
        delta = (raw - self.reference_raw_qpos_rad) * self.joint_direction_signs
        batch = qpos.shape[0]
        bucket = self.bucket_link_reference_world.unsqueeze(0).expand(batch, -1, -1)
        anchors = self.joint_anchor_world_m.unsqueeze(0).expand(batch, -1, -1)
        axes = self.joint_axis_world.unsqueeze(0).expand(batch, -1, -1)
        for joint_index in range(4):
            rotation = _axis_angle_rotation(axes[:, joint_index], delta[:, joint_index])
            around = _rotation_about_point(rotation, anchors[:, joint_index])
            bucket = around @ bucket
            if joint_index + 1 < 4:
                tail = anchors[:, joint_index + 1 :]
                ones = torch.ones(
                    (*tail.shape[:-1], 1), dtype=tail.dtype, device=tail.device
                )
                anchors = torch.cat(
                    (
                        anchors[:, : joint_index + 1],
                        (around[:, None] @ torch.cat((tail, ones), dim=-1)[..., None])[
                            ..., :3, 0
                        ],
                    ),
                    dim=1,
                )
                axes = torch.cat(
                    (
                        axes[:, : joint_index + 1],
                        (rotation[:, None] @ axes[:, joint_index + 1 :, :, None])[
                            ..., 0
                        ],
                    ),
                    dim=1,
                )
        tip_h = torch.cat(
            (
                self.fixed_tip_in_bucket_link_m,
                self.fixed_tip_in_bucket_link_m.new_ones(1),
            )
        )
        tip_world = (bucket @ tip_h[None, :, None])[:, :, 0]
        tip_local = (self.dig_area_world_to_local[None] @ tip_world[:, :, None])[
            :, :3, 0
        ]
        return tip_local.reshape(*original_shape, 3)

    def validate_fixtures(self, *, max_error_m: float = 0.002) -> dict[str, Any]:
        if not math.isfinite(max_error_m) or max_error_m < 0.0:
            raise ValueError("max_error_m must be finite and non-negative")
        qpos = torch.tensor(
            [value.normalized_qpos for value in self.contract.fixtures],
            dtype=torch.float32,
            device=self.raw_qpos_min_rad.device,
        )
        expected = torch.tensor(
            [value.fixed_tip_dig_area_xyz_m for value in self.contract.fixtures],
            dtype=torch.float32,
            device=self.raw_qpos_min_rad.device,
        )
        with torch.no_grad():
            predicted = self(qpos)
            errors = torch.linalg.vector_norm(predicted - expected, dim=-1)
        maximum = float(errors.max().cpu())
        return {
            "passed": maximum <= float(max_error_m),
            "fixture_count": len(self.contract.fixtures),
            "max_error_m": maximum,
            "error_by_fixture_m": errors.cpu().tolist(),
            "limit_m": float(max_error_m),
        }


def _axis_angle_rotation(axis: torch.Tensor, angle: torch.Tensor) -> torch.Tensor:
    x, y, z = axis.unbind(dim=-1)
    zeros = torch.zeros_like(x)
    skew = torch.stack(
        (
            zeros,
            -z,
            y,
            z,
            zeros,
            -x,
            -y,
            x,
            zeros,
        ),
        dim=-1,
    ).reshape(-1, 3, 3)
    identity = torch.eye(3, dtype=axis.dtype, device=axis.device).expand(
        axis.shape[0], -1, -1
    )
    sin = torch.sin(angle)[:, None, None]
    cos = torch.cos(angle)[:, None, None]
    return identity + sin * skew + (1.0 - cos) * (skew @ skew)


def _rotation_about_point(rotation: torch.Tensor, point: torch.Tensor) -> torch.Tensor:
    batch = rotation.shape[0]
    result = torch.eye(4, dtype=rotation.dtype, device=rotation.device).repeat(
        batch, 1, 1
    )
    result[:, :3, :3] = rotation
    result[:, :3, 3] = point - (rotation @ point[:, :, None])[:, :, 0]
    return result


def _vector(payload: dict[str, Any], key: str, length: int) -> np.ndarray:
    return _finite_array(payload.get(key), (length,), key)


def _matrix(payload: dict[str, Any], key: str, shape: tuple[int, int]) -> np.ndarray:
    return _finite_array(payload.get(key), shape, key)


def _finite_array(value: Any, shape: tuple[int, ...], label: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(f"{label} must have finite shape {shape}")
    return array.astype(np.float32)


def _validate_homogeneous(value: np.ndarray, label: str) -> None:
    if not np.allclose(value[3], [0.0, 0.0, 0.0, 1.0], atol=1.0e-6, rtol=0.0):
        raise ValueError(f"{label} is not a homogeneous transform")


__all__ = [
    "FIXED_TIP_CANDIDATE_ID",
    "FIXED_TIP_FK_ARTIFACT_SCHEMA",
    "DifferentiableFixedTipFK",
    "FixedTipFKContract",
    "FixedTipFKFixture",
    "load_fixed_tip_fk_artifact",
]
