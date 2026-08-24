"""Pure phase and safety state for isolated Dig effect experiments."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

ACTION_DIM = 4
DIG_TOKEN_DIM = 10
PREFLIGHT_TICKS = 100
EVIDENCE_TICKS = 250
CONTACT_FORCE_LIMIT_N = 100_000.0
ARM_ORDER = ("original", "alternate")
ZERO_ACTION = (0.0,) * ACTION_DIM


class DigEffectRuntimeError(RuntimeError):
    """Base error for the isolated runtime boundary."""


class PhaseGuardError(DigEffectRuntimeError):
    """Raised when a phase-owned operation is called out of order."""


class RuntimeContractError(DigEffectRuntimeError):
    """Raised when an injected adapter violates its narrow protocol."""


class DigEffectPhase(str, Enum):
    PREPARE = "prepare"
    PREFLIGHT = "preflight"
    RUN = "run"
    REPORT = "report"
    COMPLETE = "complete"


@dataclass(frozen=True)
class DigAtomicDiagnostics:
    """Mandatory atomic sidecar for one shadow or evidence response."""

    sidecar_complete: bool
    diagnostics_enabled: bool
    token_sha256: str
    lineage_sha256: str
    tick_id: int
    request_step_id: int
    response_step_id: int
    sim_time_ns: int
    received_normalized_action: tuple[float, ...]
    clamped_normalized_action: tuple[float, ...]
    final_target_speed: tuple[float, ...]
    soft_limit_axes: tuple[bool, ...]
    acceleration_limited_axes: tuple[bool, ...]
    soil_contact: bool
    wall_contact: bool
    floor_contact: bool
    hard_collision: bool
    forbidden_contact: bool
    unknown_contact: bool
    max_force_n: float
    nonfinite: bool
    clamped: bool
    stuck: bool
    timeout: bool

    def __post_init__(self) -> None:
        for name in (
            "sidecar_complete",
            "diagnostics_enabled",
            "soil_contact",
            "wall_contact",
            "floor_contact",
            "hard_collision",
            "forbidden_contact",
            "unknown_contact",
            "nonfinite",
            "clamped",
            "stuck",
            "timeout",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be boolean")
        for name in (
            "received_normalized_action",
            "clamped_normalized_action",
            "final_target_speed",
        ):
            values = _float_tuple(getattr(self, name))
            if len(values) != ACTION_DIM:
                raise ValueError(f"{name} must have four axes")
            object.__setattr__(self, name, values)
        for name in ("soft_limit_axes", "acceleration_limited_axes"):
            values = tuple(getattr(self, name))
            if len(values) != ACTION_DIM or any(
                not isinstance(value, bool) for value in values
            ):
                raise ValueError(f"{name} must have four boolean axes")
            object.__setattr__(self, name, values)

    def as_dict(self) -> dict[str, Any]:
        return {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> DigAtomicDiagnostics:
        required = tuple(cls.__dataclass_fields__)
        missing = tuple(name for name in required if name not in value)
        if missing:
            raise ValueError(
                "atomic diagnostics missing required fields: " + ",".join(missing)
            )
        return cls(
            sidecar_complete=_strict_bool(value["sidecar_complete"]),
            diagnostics_enabled=_strict_bool(value["diagnostics_enabled"]),
            token_sha256=str(value["token_sha256"]),
            lineage_sha256=str(value["lineage_sha256"]),
            tick_id=int(value["tick_id"]),
            request_step_id=int(value["request_step_id"]),
            response_step_id=int(value["response_step_id"]),
            sim_time_ns=int(value["sim_time_ns"]),
            received_normalized_action=tuple(value["received_normalized_action"]),
            clamped_normalized_action=tuple(value["clamped_normalized_action"]),
            final_target_speed=tuple(value["final_target_speed"]),
            soft_limit_axes=tuple(value["soft_limit_axes"]),
            acceleration_limited_axes=tuple(value["acceleration_limited_axes"]),
            soil_contact=_strict_bool(value["soil_contact"]),
            wall_contact=_strict_bool(value["wall_contact"]),
            floor_contact=_strict_bool(value["floor_contact"]),
            hard_collision=_strict_bool(value["hard_collision"]),
            forbidden_contact=_strict_bool(value["forbidden_contact"]),
            unknown_contact=_strict_bool(value["unknown_contact"]),
            max_force_n=float(value["max_force_n"]),
            nonfinite=_strict_bool(value["nonfinite"]),
            clamped=_strict_bool(value["clamped"]),
            stuck=_strict_bool(value["stuck"]),
            timeout=_strict_bool(value["timeout"]),
        )


@dataclass(frozen=True)
class DigEffectTick:
    """One response; missing diagnostics is unsafe, never an all-clear."""

    diagnostics: DigAtomicDiagnostics | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "diagnostics": (
                self.diagnostics.as_dict() if self.diagnostics is not None else None
            ),
            "payload": _jsonable(self.payload),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> DigEffectTick:
        payload = value.get("payload", {})
        if not isinstance(payload, Mapping):
            raise ValueError("tick payload must be a mapping")
        diagnostics_raw = value.get("diagnostics")
        diagnostics = (
            DigAtomicDiagnostics.from_mapping(diagnostics_raw)
            if isinstance(diagnostics_raw, Mapping)
            else None
        )
        return cls(diagnostics=diagnostics, payload=dict(payload))


@dataclass(frozen=True)
class DigControlDecision:
    continue_run: bool
    neutral_required: bool
    reason: str = ""
    successful: bool = False


class DigEffectStateMachine:
    """Pure phase, horizon, and safety state for one arm."""

    def __init__(self) -> None:
        self._phase = DigEffectPhase.PREPARE
        self._token_sha256 = ""
        self._preflight_tick_count = 0
        self._evidence_tick_count = 0
        self._preflight_closed = False
        self._soil_contact_seen = False
        self._soil_contact_active = False
        self._post_contact_clear_ticks = 0
        self._attempt_consumed = False
        self._terminal_trigger = ""
        self._stop_reason = ""
        self._terminal_success = False
        self._neutral_acknowledged = False

    @property
    def phase(self) -> DigEffectPhase:
        return self._phase

    @property
    def terminal_trigger(self) -> str:
        return self._terminal_trigger

    def prepare(self, *, token: Sequence[float], token_sha256: str) -> None:
        self._require(DigEffectPhase.PREPARE)
        if canonical_token_sha256(token) != token_sha256:
            raise RuntimeContractError("token_sha_mismatch_during_prepare")
        self._token_sha256 = token_sha256
        self._phase = DigEffectPhase.PREFLIGHT

    def observe_preflight_tick(self, tick: DigEffectTick) -> DigControlDecision:
        self._require(DigEffectPhase.PREFLIGHT)
        if self._preflight_closed or self._terminal_trigger:
            raise PhaseGuardError("preflight already reached a terminal boundary")
        if self._preflight_tick_count >= PREFLIGHT_TICKS:
            raise PhaseGuardError("preflight already consumed 100 ticks")
        self._preflight_tick_count += 1
        reason = safety_stop_reason(tick)
        if reason:
            self._terminal_trigger = f"preflight:{reason}"
            return DigControlDecision(False, True, self._terminal_trigger)
        return DigControlDecision(True, False)

    def abort_preflight(self, reason: str) -> DigControlDecision:
        self._require(DigEffectPhase.PREFLIGHT)
        if self._terminal_trigger:
            raise PhaseGuardError("preflight already reached a terminal boundary")
        self._terminal_trigger = f"preflight:{reason}"
        return DigControlDecision(False, True, self._terminal_trigger)

    def finish_preflight(self, neutral_acknowledged: bool) -> None:
        self._require(DigEffectPhase.PREFLIGHT)
        self._neutral_acknowledged = bool(neutral_acknowledged)
        if self._terminal_trigger:
            self._stop_reason = (
                self._terminal_trigger
                if self._neutral_acknowledged
                else "preflight_neutral_ack_missing"
            )
            self._phase = DigEffectPhase.REPORT
            return
        if self._preflight_tick_count != PREFLIGHT_TICKS:
            raise PhaseGuardError("preflight requires exactly 100 ticks")
        if not self._neutral_acknowledged:
            self._terminal_trigger = "preflight_neutral_ack_missing"
            self._stop_reason = self._terminal_trigger
            self._phase = DigEffectPhase.REPORT
            return
        self._preflight_closed = True

    def fail_preflight_without_backend(self, reason: str) -> None:
        self._require(DigEffectPhase.PREFLIGHT)
        self._terminal_trigger = f"preflight_startup_failed:{reason}"
        self._stop_reason = self._terminal_trigger
        self._phase = DigEffectPhase.REPORT

    def cancel_before_run(self, reason: str) -> None:
        self._require(DigEffectPhase.PREFLIGHT)
        self._terminal_trigger = str(reason)
        self._stop_reason = str(reason)
        self._phase = DigEffectPhase.REPORT

    def begin_run(self) -> None:
        self._require(DigEffectPhase.PREFLIGHT)
        if self._preflight_tick_count != PREFLIGHT_TICKS or not self._preflight_closed:
            raise PhaseGuardError("run requires a closed 100-tick preflight")
        self._neutral_acknowledged = False
        self._phase = DigEffectPhase.RUN

    def consume_attempt(self) -> None:
        self._require(DigEffectPhase.RUN)
        if self._attempt_consumed:
            raise PhaseGuardError("arm opportunity was already consumed")
        self._attempt_consumed = True

    def observe_run_tick(self, tick: DigEffectTick) -> DigControlDecision:
        self._require(DigEffectPhase.RUN)
        if not self._attempt_consumed:
            self._attempt_consumed = True
        if self._terminal_trigger:
            raise PhaseGuardError("terminal event already requires neutral")
        if self._evidence_tick_count >= EVIDENCE_TICKS:
            raise PhaseGuardError("evidence horizon already exhausted")
        self._evidence_tick_count += 1
        diagnostics = tick.diagnostics
        self._soil_contact_seen = self._soil_contact_seen or bool(
            diagnostics and diagnostics.soil_contact
        )
        reason = safety_stop_reason(tick)
        if reason:
            return self._trigger(reason, successful=False)
        if diagnostics is not None:
            if diagnostics.soil_contact:
                self._soil_contact_active = True
                self._post_contact_clear_ticks = 0
            elif self._soil_contact_active:
                self._post_contact_clear_ticks += 1
                if self._post_contact_clear_ticks == 3:
                    return self._trigger(
                        "soil_exit_confirmed_3_clear_ticks", successful=True
                    )
        if self._evidence_tick_count == EVIDENCE_TICKS:
            return self._trigger("evidence_timeout_250_ticks", successful=False)
        return DigControlDecision(True, False)

    def abort(self, reason: str) -> DigControlDecision:
        self._require(DigEffectPhase.RUN)
        if self._terminal_trigger:
            raise PhaseGuardError("terminal event already requires neutral")
        return self._trigger(str(reason), successful=False)

    def fail_without_backend(self, reason: str, *, invalid: bool = False) -> None:
        self._require(DigEffectPhase.RUN)
        self._terminal_trigger = str(reason)
        self._stop_reason = f"invalid:{reason}" if invalid else str(reason)
        self._terminal_success = False
        self._phase = DigEffectPhase.REPORT

    def acknowledge_neutral(self, acknowledged: bool) -> None:
        self._require(DigEffectPhase.RUN)
        if not self._terminal_trigger:
            raise PhaseGuardError("neutral acknowledgement requires a terminal event")
        self._neutral_acknowledged = bool(acknowledged)
        if acknowledged:
            self._stop_reason = self._terminal_trigger
        else:
            self._stop_reason = "neutral_ack_missing"
            self._terminal_success = False
        self._phase = DigEffectPhase.REPORT

    def mark_report_failure(self, reason: str, *, invalid: bool = False) -> None:
        self._require(DigEffectPhase.REPORT)
        self._terminal_success = False
        self._stop_reason = f"invalid:{reason}" if invalid else str(reason)

    def report_fields(self) -> dict[str, Any]:
        self._require(DigEffectPhase.REPORT)
        if self._stop_reason.startswith("invalid:"):
            status = "invalid"
            stop_reason = self._stop_reason.removeprefix("invalid:")
        elif (
            self._stop_reason.startswith("preflight:")
            or self._stop_reason.startswith("preflight_startup_failed:")
            or self._stop_reason
            in {"paired_preflight_blocked", "preflight_neutral_ack_missing"}
        ):
            status = "preflight_blocked"
            stop_reason = self._stop_reason
        elif self._terminal_success and self._neutral_acknowledged:
            status = "passed"
            stop_reason = self._stop_reason
        else:
            status = "failed"
            stop_reason = self._stop_reason
        return {
            "status": status,
            "attempt_consumed": self._attempt_consumed,
            "preflight_tick_count": self._preflight_tick_count,
            "evidence_tick_count": self._evidence_tick_count,
            "soil_contact_seen": self._soil_contact_seen,
            "terminal_trigger": self._terminal_trigger,
            "stop_reason": stop_reason,
            "neutral_acknowledged": self._neutral_acknowledged,
            "token_sha256": self._token_sha256,
        }

    def _trigger(self, reason: str, *, successful: bool) -> DigControlDecision:
        self._terminal_trigger = reason
        self._terminal_success = successful
        return DigControlDecision(False, True, reason, successful)

    def _require(self, expected: DigEffectPhase) -> None:
        if self._phase is not expected:
            raise PhaseGuardError(
                f"phase guard expected={expected.value} actual={self._phase.value}"
            )


def canonical_token_sha256(token: Sequence[float]) -> str:
    values = _float_tuple(token)
    if len(values) != DIG_TOKEN_DIM or not all(math.isfinite(v) for v in values):
        raise ValueError("Dig token must be finite and 10D")
    payload = json.dumps(list(values), allow_nan=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def safety_stop_reason(tick: DigEffectTick) -> str:
    diagnostics = tick.diagnostics
    if diagnostics is None:
        return "atomic_diagnostics_missing"
    if not diagnostics.sidecar_complete or not diagnostics.diagnostics_enabled:
        return "atomic_diagnostics_incomplete"
    if diagnostics.nonfinite or not math.isfinite(float(diagnostics.max_force_n)):
        return "nonfinite"
    if diagnostics.unknown_contact:
        return "unknown_contact"
    if diagnostics.forbidden_contact:
        return "forbidden_contact"
    if diagnostics.wall_contact:
        return "wall_contact"
    if diagnostics.floor_contact:
        return "floor_contact"
    if diagnostics.hard_collision:
        return "hard_collision"
    if float(diagnostics.max_force_n) >= CONTACT_FORCE_LIMIT_N:
        return "force_at_or_above_100000n"
    if diagnostics.clamped:
        return "clamp"
    if any(diagnostics.soft_limit_axes):
        return "soft_limit"
    if diagnostics.stuck:
        return "stuck"
    if diagnostics.timeout:
        return "timeout"
    return ""


def _float_tuple(value: Any) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("token must be a numeric sequence")
    try:
        return tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise ValueError("token must be a numeric sequence") from exc


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_jsonable(item) for item in value]
    tolist = getattr(value, "tolist", None)
    return _jsonable(tolist()) if callable(tolist) else value


def _strict_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise TypeError("atomic diagnostic boolean field must be boolean")
    return value


__all__ = [
    "ACTION_DIM",
    "ARM_ORDER",
    "CONTACT_FORCE_LIMIT_N",
    "DIG_TOKEN_DIM",
    "EVIDENCE_TICKS",
    "PREFLIGHT_TICKS",
    "ZERO_ACTION",
    "DigAtomicDiagnostics",
    "DigControlDecision",
    "DigEffectPhase",
    "DigEffectRuntimeError",
    "DigEffectStateMachine",
    "DigEffectTick",
    "PhaseGuardError",
    "RuntimeContractError",
    "canonical_token_sha256",
    "safety_stop_reason",
]
