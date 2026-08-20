"""Public ACT stream replay and verification for Return dispatch validation.

This focused module owns the stateful part of the offline validation: build
independent policy streams, reset each once at a held segment entrance, query
raw chunks through the public ACT API, and verify reconstruction/replicas.  It
does not select a temporal strategy or write an artifact.
"""

from __future__ import annotations

import math
import weakref
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from testbed.data.return_temporal_dispatch_validation import (
    ReturnTemporalDispatchFrame,
    ReturnValidationCounterfactualPair,
)
from testbed.eval.temporal_dispatch_contract import (
    TemporalDispatchMetricContract,
    TemporalDispatchStrategy,
    reconstruct_temporal_dispatch,
)

PUBLIC_LEGACY_RECONSTRUCTION_TOLERANCE = 1.0e-6
REPLICA_STABILITY_TOLERANCE = 1.0e-6

PolicyFactory = Callable[[str], Any]
ObservationReader = Callable[[ReturnTemporalDispatchFrame], Mapping[str, Any]]
PolicyDescriber = Callable[[Any], Mapping[str, Any]]


class ReturnTemporalDispatchValidationEvaluationError(ValueError):
    """Raised when source-disjoint temporal-dispatch evidence is unsafe."""


def replay_return_temporal_dispatch_pair(
    *,
    pair: ReturnValidationCounterfactualPair,
    token_key: str,
    policy_factory: PolicyFactory,
    observation_reader: ObservationReader,
    policy_describer: PolicyDescriber,
    metric_contract: TemporalDispatchMetricContract,
    legacy_strategy: TemporalDispatchStrategy,
) -> dict[str, Any]:
    """Collect and verify independent baseline/alternate public ACT streams.

    The policy factory must yield a fresh temporal state for each call.  Four
    streams are collected: baseline/alternate primary replicas and matching
    independent replicas.  Returned arrays remain in-memory for the caller's
    strategy metrics and are intentionally excluded from ``verification``.
    """

    streams: dict[str, dict[str, Any]] = {}
    for condition, token in (
        ("baseline", pair.baseline_segment.token),
        ("alternate", pair.alternate_token),
    ):
        for replica in ("primary", "replica"):
            name = f"{condition}_{replica}"
            streams[name] = _collect_public_stream(
                label=f"{pair.pair_id}:{name}",
                frames=pair.baseline_segment.frames,
                token_key=token_key,
                token=token,
                policy_factory=policy_factory,
                observation_reader=observation_reader,
                policy_describer=policy_describer,
            )
    signature = _validate_policy_streams(streams, metric_contract)
    _validate_independent_factory_instances(streams)
    reconstruction = _validate_legacy_reconstruction(streams, legacy_strategy)
    replicas = _validate_replicas(streams)
    return {
        "pair": pair,
        "streams": streams,
        "policy_signature": signature,
        "verification": {
            "pair_id": pair.pair_id,
            "baseline_segment_id": pair.baseline_segment.segment_id,
            "frame_count": len(pair.baseline_segment.frames),
            "independent_factory_streams": sorted(streams),
            "independent_factory_instances": True,
            "reset_invocations_by_evaluator": {name: 1 for name in sorted(streams)},
            "legacy_public_predict_reconstruction": reconstruction,
            "replica_stability": replicas,
            "action_scale": {
                "strict_train_action_scale": _floats(metric_contract.action_scale),
                "policy_normalization_action_std": signature["action_std"],
                "dimension_matches": True,
                "replicas_match": True,
            },
        },
    }


def _collect_public_stream(
    *,
    label: str,
    frames: Sequence[ReturnTemporalDispatchFrame],
    token_key: str,
    token: np.ndarray,
    policy_factory: PolicyFactory,
    observation_reader: ObservationReader,
    policy_describer: PolicyDescriber,
) -> dict[str, Any]:
    policy = policy_factory(label)
    if policy is None:
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return temporal policy factory returned no policy"
        )
    try:
        reset = getattr(policy, "reset", None)
        predict_chunk = getattr(policy, "predict_action_chunk", None)
        predict = getattr(policy, "predict", None)
        if not callable(reset) or not callable(predict_chunk) or not callable(predict):
            raise ReturnTemporalDispatchValidationEvaluationError(
                "Return temporal policy must expose reset(), predict_action_chunk(), and predict()"
            )
        description = _mapping(policy_describer(policy), "public policy description")
        reset()
        chunks: list[np.ndarray] = []
        dispatched_actions: list[np.ndarray] = []
        for index, frame in enumerate(frames):
            observation = dict(
                _mapping(observation_reader(frame), "Return held observation")
            )
            observation[token_key] = np.asarray(token, dtype=np.float32).copy()
            chunk = _public_chunk_actions(
                predict_chunk(observation), label=f"{label} raw chunk {index}"
            )
            action = _finite_vector(
                predict(observation), f"{label} dispatched action {index}"
            )
            if action.shape != (chunk.shape[1],) or (
                chunks and chunk.shape != chunks[0].shape
            ):
                raise ReturnTemporalDispatchValidationEvaluationError(
                    "Return public action/chunk shape changed within a segment"
                )
            chunks.append(chunk)
            dispatched_actions.append(action)
        if not chunks:
            raise ReturnTemporalDispatchValidationEvaluationError(
                "Return temporal replay segment has no observations"
            )
        try:
            instance_reference: weakref.ReferenceType[Any] | None = weakref.ref(policy)
        except TypeError:
            instance_reference = None
        return {
            "description": description,
            "chunks": np.stack(chunks, axis=0),
            "dispatched_actions": np.stack(dispatched_actions, axis=0),
            "factory_instance_reference": instance_reference,
        }
    finally:
        del policy


def _public_chunk_actions(value: Any, *, label: str) -> np.ndarray:
    actions = getattr(value, "actions", getattr(value, "action_chunk", None))
    array = _finite_array(actions, label, ndim=2)
    if array.shape[0] < 1 or array.shape[1] < 1:
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return public action chunk must contain query and action dimensions"
        )
    return array


def _validate_policy_streams(
    streams: Mapping[str, Mapping[str, Any]],
    metric_contract: TemporalDispatchMetricContract,
) -> dict[str, Any]:
    expected_names = {
        "baseline_primary",
        "baseline_replica",
        "alternate_primary",
        "alternate_replica",
    }
    if set(streams) != expected_names:
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return replay did not create four independent policy streams"
        )
    signatures = {
        name: _policy_signature(stream["description"], metric_contract)
        for name, stream in streams.items()
    }
    first = signatures["baseline_primary"]
    chunk_shape = streams["baseline_primary"]["chunks"].shape
    if (
        any(signature != first for signature in signatures.values())
        or chunk_shape[1:] != (first["num_queries"], metric_contract.action_dim)
        or any(stream["chunks"].shape != chunk_shape for stream in streams.values())
    ):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "policy temporal contract, action scale, or chunk shape is unstable"
        )
    return first


def _validate_independent_factory_instances(
    streams: Mapping[str, Mapping[str, Any]],
) -> None:
    """Reject a factory that reuses one live policy cache across conditions."""

    live_instances = [
        reference()
        for stream in streams.values()
        if (reference := stream.get("factory_instance_reference")) is not None
    ]
    live_instances = [item for item in live_instances if item is not None]
    if len({id(item) for item in live_instances}) != len(live_instances):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return policy factory reused one live instance across independent streams"
        )


def _policy_signature(
    description: Mapping[str, Any], metric_contract: TemporalDispatchMetricContract
) -> dict[str, Any]:
    temporal = _mapping(
        description.get("temporal_aggregation"), "policy temporal contract"
    )
    expected = {
        "enabled": True,
        "num_queries": 100,
        "window": 100,
        "weight_order": "legacy_oldest_first",
        "decay": 0.01,
    }
    for key, expected_value in expected.items():
        actual = temporal.get(key)
        matches = (
            isinstance(actual, (int, float))
            and math.isclose(float(actual), 0.01, rel_tol=0.0, abs_tol=0.0)
            if key == "decay"
            else actual == expected_value
        )
        if not matches:
            raise ReturnTemporalDispatchValidationEvaluationError(
                "loaded Return policy does not use frozen legacy temporal aggregation"
            )
    action_dim = _integer(description.get("action_dim"), "policy action dimension")
    mean = _finite_vector(description.get("action_mean"), "policy action mean")
    std = _finite_vector(
        description.get("action_std"), "policy action standard deviation"
    )
    if (
        action_dim != metric_contract.action_dim
        or mean.shape != (action_dim,)
        or std.shape != mean.shape
        or np.any(std <= 0.0)
    ):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "policy action normalization disagrees with strict-train action scale"
        )
    return {
        "temporal_aggregation": expected,
        "num_queries": int(temporal["num_queries"]),
        "action_dim": action_dim,
        "action_mean": _floats(mean),
        "action_std": _floats(std),
    }


def _validate_legacy_reconstruction(
    streams: Mapping[str, Mapping[str, Any]], legacy: TemporalDispatchStrategy
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, stream in streams.items():
        trace = reconstruct_temporal_dispatch(
            chunks=stream["chunks"], strategy=legacy, reset_frame_indices=(0,)
        )
        difference = np.max(
            np.abs(np.asarray(stream["dispatched_actions"]) - trace.actions), axis=0
        )
        if np.any(difference > PUBLIC_LEGACY_RECONSTRUCTION_TOLERANCE):
            raise ReturnTemporalDispatchValidationEvaluationError(
                "legacy public predict reconstruction differs from raw public chunks"
            )
        result[name] = {"passed": True, "max_abs_error_axis": _floats(difference)}
    return result


def _validate_replicas(streams: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for condition in ("baseline", "alternate"):
        primary = streams[f"{condition}_primary"]
        replica = streams[f"{condition}_replica"]
        chunk_error = np.max(
            np.abs(np.asarray(primary["chunks"]) - np.asarray(replica["chunks"])),
            axis=(0, 1),
        )
        action_error = np.max(
            np.abs(
                np.asarray(primary["dispatched_actions"])
                - np.asarray(replica["dispatched_actions"])
            ),
            axis=0,
        )
        if np.any(chunk_error > REPLICA_STABILITY_TOLERANCE) or np.any(
            action_error > REPLICA_STABILITY_TOLERANCE
        ):
            raise ReturnTemporalDispatchValidationEvaluationError(
                "Return temporal replica stability exceeds the frozen tolerance"
            )
        result[condition] = {
            "passed": True,
            "raw_chunk_max_abs_error_axis": _floats(chunk_error),
            "legacy_dispatched_max_abs_error_axis": _floats(action_error),
        }
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReturnTemporalDispatchValidationEvaluationError(
            f"{label} must be a mapping"
        )
    return value


def _finite_array(value: Any, label: str, *, ndim: int) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise ReturnTemporalDispatchValidationEvaluationError(
            f"{label} must be numeric"
        ) from exc
    if result.ndim != ndim or not np.isfinite(result).all():
        raise ReturnTemporalDispatchValidationEvaluationError(
            f"{label} must be finite {ndim}D"
        )
    return result


def _finite_vector(value: Any, label: str) -> np.ndarray:
    return _finite_array(value, label, ndim=1)


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ReturnTemporalDispatchValidationEvaluationError(
            f"{label} must be an integer"
        )
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReturnTemporalDispatchValidationEvaluationError(
            f"{label} must be an integer"
        ) from exc
    if result < 1 or result != value:
        raise ReturnTemporalDispatchValidationEvaluationError(
            f"{label} must be positive"
        )
    return result


def _floats(values: Any) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float64).reshape(-1)]


__all__ = [
    "PUBLIC_LEGACY_RECONSTRUCTION_TOLERANCE",
    "REPLICA_STABILITY_TOLERANCE",
    "ObservationReader",
    "PolicyDescriber",
    "PolicyFactory",
    "ReturnTemporalDispatchValidationEvaluationError",
    "replay_return_temporal_dispatch_pair",
]
