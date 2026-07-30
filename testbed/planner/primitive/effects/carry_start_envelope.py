"""Train-only carry-start envelope gate for normal dig-to-carry handoff."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.handoff_envelope import (
    CARRY_START_ENVELOPE_FEATURE_ORDER,
    CARRY_START_ENVELOPE_SCHEMA,
    STRICT18_CARRY_TRAIN_SAMPLE_COUNT,
    STRICT18_TRAIN_SOURCE_EPISODE_IDS,
    STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
)
from testbed.planner.primitive.facts.capabilities import DigTransitionStatus


@dataclass(frozen=True)
class CarryStartEnvelopeGateConfig:
    """Runtime release contract for one carry-start envelope."""

    enabled: bool = False
    artifact_path: str = ""
    artifact_sha256: str = ""
    hold_steps: int = 3
    max_dig_steps: int = 500

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any] | None,
    ) -> CarryStartEnvelopeGateConfig:
        raw = dict(values or {})
        return cls(
            enabled=bool(raw.get("enabled", False)),
            artifact_path=str(raw.get("artifact_path", "")),
            artifact_sha256=str(raw.get("artifact_sha256", "")),
            hold_steps=int(raw.get("hold_steps", 3)),
            max_dig_steps=int(raw.get("max_dig_steps", 500)),
        )


@dataclass(frozen=True)
class CarryStartEnvelope:
    """Validated ordered bounds loaded from a released JSON artifact."""

    path: Path
    sha256: str
    p01: np.ndarray
    p50: np.ndarray
    p99: np.ndarray
    sample_count: int


@dataclass
class CarryStartEnvelopeGate:
    """Require current expert-start support for three consecutive dig steps."""

    config: CarryStartEnvelopeGateConfig
    envelope: CarryStartEnvelope | None
    _hold_count: int = field(default=0, init=False)
    _last_dig_step_count: int = field(default=-1, init=False)
    _base_ready: bool = field(default=False, init=False)
    _envelope_ready: bool = field(default=False, init=False)
    _timeout: bool = field(default=False, init=False)
    _violations: list[str] = field(default_factory=list, init=False)
    _feature_checks: dict[str, dict[str, float | bool | str]] = field(
        default_factory=dict,
        init=False,
    )

    @classmethod
    def from_config(
        cls,
        config: CarryStartEnvelopeGateConfig,
    ) -> CarryStartEnvelopeGate:
        if int(config.hold_steps) < 1:
            raise ValueError("carry-start envelope hold_steps must be >= 1")
        if int(config.max_dig_steps) < 1:
            raise ValueError("carry-start envelope max_dig_steps must be >= 1")
        envelope = _load_envelope(config) if config.enabled else None
        return cls(config=config, envelope=envelope)

    def reset(self) -> None:
        self._hold_count = 0
        self._last_dig_step_count = -1
        self._base_ready = False
        self._envelope_ready = False
        self._timeout = False
        self._violations = []
        self._feature_checks = {}

    def apply(
        self,
        obs: dict[str, Any],
        status: DigTransitionStatus,
    ) -> DigTransitionStatus:
        """Gate only successful carry handoffs; preserve failure/replan facts."""

        if not self.config.enabled:
            return status
        envelope = self.envelope
        if envelope is None:  # pragma: no cover - construction is fail closed
            raise RuntimeError("enabled carry-start envelope is not loaded")

        step_count = int(status.dig_step_count)
        if (
            self._last_dig_step_count >= 0
            and step_count != self._last_dig_step_count + 1
        ):
            self._hold_count = 0
        self._last_dig_step_count = step_count
        self._base_ready = bool(status.dig_to_carry_ready)

        values = _feature_vector(obs)
        self._feature_checks, self._violations = _check_features(
            values,
            envelope=envelope,
        )
        if self._violations:
            self._hold_count = 0
        else:
            self._hold_count += 1
        self._envelope_ready = bool(
            self._hold_count >= int(self.config.hold_steps)
        )
        self._timeout = bool(
            step_count >= int(self.config.max_dig_steps)
            and not self._envelope_ready
        )
        if self._base_ready and self._envelope_ready and not self._timeout:
            return status
        return replace(
            status,
            dig_to_carry_ready=False,
            dig_to_carry_reason="",
        )

    def timeout_requested(self) -> bool:
        return bool(self.config.enabled and self._timeout)

    def debug_fields(self) -> dict[str, Any]:
        envelope = self.envelope
        return {
            "carry_start_envelope_enabled": bool(self.config.enabled),
            "carry_start_base_ready": bool(self._base_ready),
            "carry_start_envelope_ready": bool(self._envelope_ready),
            "carry_start_envelope_hold_count": int(self._hold_count),
            "carry_start_envelope_hold_steps": int(self.config.hold_steps),
            "carry_start_envelope_max_dig_steps": int(
                self.config.max_dig_steps
            ),
            "carry_start_envelope_timeout": bool(self._timeout),
            "carry_start_envelope_violations": list(self._violations),
            "carry_start_envelope_feature_checks": dict(self._feature_checks),
            "carry_start_envelope_artifact_sha256": (
                "" if envelope is None else str(envelope.sha256)
            ),
            "carry_start_envelope_artifact_path": (
                "" if envelope is None else str(envelope.path)
            ),
        }


def _load_envelope(
    config: CarryStartEnvelopeGateConfig,
) -> CarryStartEnvelope:
    path_text = str(config.artifact_path).strip()
    if not path_text:
        raise ValueError(
            "enabled carry-start envelope requires artifact_path"
        )
    path = Path(path_text).expanduser().resolve(strict=True)
    payload_bytes = path.read_bytes()
    digest = hashlib.sha256(payload_bytes).hexdigest()
    expected_digest = str(config.artifact_sha256).strip().lower()
    if not expected_digest:
        raise ValueError(
            "enabled carry-start envelope requires artifact_sha256"
        )
    if digest != expected_digest:
        raise ValueError(
            "carry-start envelope sha256 mismatch: "
            f"expected={expected_digest}, observed={digest}"
        )
    payload = json.loads(payload_bytes)
    if not isinstance(payload, Mapping):
        raise ValueError("carry-start envelope artifact must be a mapping")
    if str(payload.get("schema", "")) != CARRY_START_ENVELOPE_SCHEMA:
        raise ValueError("carry-start envelope schema mismatch")
    if tuple(payload.get("feature_order", ())) != tuple(
        CARRY_START_ENVELOPE_FEATURE_ORDER
    ):
        raise ValueError("carry-start envelope feature_order mismatch")
    sample_count = int(payload.get("sample_count", -1))
    if sample_count != STRICT18_CARRY_TRAIN_SAMPLE_COUNT:
        raise ValueError(
            "carry-start envelope sample_count must be "
            f"{STRICT18_CARRY_TRAIN_SAMPLE_COUNT}"
        )
    lineage = payload.get("source_lineage")
    if not isinstance(lineage, Mapping):
        raise ValueError("carry-start envelope source_lineage missing")
    train_sources = tuple(
        int(value) for value in lineage.get("train_source_episode_ids", ())
    )
    validation_sources = tuple(
        int(value)
        for value in lineage.get("validation_source_episode_ids", ())
    )
    if any(value in validation_sources for value in train_sources):
        raise ValueError(
            "carry-start envelope validation_source appears in train lineage"
        )
    if train_sources != STRICT18_TRAIN_SOURCE_EPISODE_IDS:
        raise ValueError("carry-start envelope train source allowlist mismatch")
    if validation_sources != STRICT18_VALIDATION_SOURCE_EPISODE_IDS:
        raise ValueError(
            "carry-start envelope validation source allowlist mismatch"
        )
    lineage_text = json.dumps(lineage, sort_keys=True).lower()
    if "partial" in lineage_text or "layered" in lineage_text:
        raise ValueError(
            "carry-start envelope lineage contains partial/layered salvage"
        )

    percentiles = payload.get("percentiles")
    if not isinstance(percentiles, Mapping):
        raise ValueError("carry-start envelope percentiles missing")
    width = len(CARRY_START_ENVELOPE_FEATURE_ORDER)
    arrays: dict[str, np.ndarray] = {}
    for key in ("p01", "p50", "p99"):
        array = np.asarray(percentiles.get(key), dtype=np.float64)
        if array.shape != (width,) or not np.isfinite(array).all():
            raise ValueError(
                f"carry-start envelope {key} must be finite shape ({width},)"
            )
        arrays[key] = array
    if np.any(arrays["p01"] > arrays["p50"]) or np.any(
        arrays["p50"] > arrays["p99"]
    ):
        raise ValueError("carry-start envelope percentile order invalid")
    return CarryStartEnvelope(
        path=path,
        sha256=digest,
        p01=arrays["p01"],
        p50=arrays["p50"],
        p99=arrays["p99"],
        sample_count=sample_count,
    )


def _feature_vector(obs: dict[str, Any]) -> np.ndarray:
    qpos = np.asarray(obs.get("qpos"), dtype=np.float64).reshape(-1)
    qvel = np.asarray(obs.get("qvel"), dtype=np.float64).reshape(-1)
    env_state = np.asarray(obs.get("env_state"), dtype=np.float64).reshape(-1)
    if qpos.size < 4 or qvel.size < 4:
        raise ValueError("carry-start envelope requires qpos/qvel width >= 4")
    if env_state.size <= ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX:
        raise ValueError("carry-start envelope requires env_state width >= 32")
    values = np.concatenate(
        (
            qpos[:4],
            qvel[:4],
            env_state[
                ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX :
                ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX + 3
            ],
            env_state[
                ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX :
                ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX + 1
            ],
            env_state[
                ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX :
                ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX + 1
            ],
        )
    )
    if not np.isfinite(values).all():
        raise ValueError("carry-start envelope observation contains non-finite values")
    return values


def _check_features(
    values: np.ndarray,
    *,
    envelope: CarryStartEnvelope,
) -> tuple[dict[str, dict[str, float | bool | str]], list[str]]:
    checks: dict[str, dict[str, float | bool | str]] = {}
    violations: list[str] = []
    for index, name in enumerate(CARRY_START_ENVELOPE_FEATURE_ORDER):
        value = float(values[index])
        lower = float(envelope.p01[index])
        upper = float(envelope.p99[index])
        if value < lower:
            reason = "below_p01"
        elif value > upper:
            reason = "above_p99"
        else:
            reason = ""
        checks[name] = {
            "value": value,
            "p01": lower,
            "p50": float(envelope.p50[index]),
            "p99": upper,
            "in_range": not bool(reason),
            "violation": reason,
        }
        if reason:
            violations.append(f"{name}:{reason}")
    return checks, violations


__all__ = [
    "CARRY_START_ENVELOPE_FEATURE_ORDER",
    "CarryStartEnvelope",
    "CarryStartEnvelopeGate",
    "CarryStartEnvelopeGateConfig",
]
