"""Pre-registered source-balanced held-Return replay sampling.

The full source-disjoint Return validation population is intentionally retained
by :mod:`return_temporal_dispatch_validation` as immutable evidence.  A
policy-replay evaluator can be much more expensive, though, so this module
freezes a smaller, source-balanced subset before any temporal strategy outcome
is observed.  It has no target rollout, checkpoint, window, weight, score, or
strategy input.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from testbed.data.return_temporal_dispatch_validation import (
    ReturnTemporalDispatchSegment,
    ReturnTemporalDispatchValidationError,
    ReturnTemporalDispatchValidationPopulation,
    ReturnValidationCounterfactualPair,
    build_return_validation_counterfactual_pairs,
)

RETURN_TEMPORAL_DISPATCH_SAMPLE_SCHEMA = "return_temporal_dispatch_sample_v1"
RETURN_TEMPORAL_DISPATCH_MAX_SEGMENTS_PER_VALIDATION_SOURCE = 8


@dataclass(frozen=True)
class ReturnTemporalDispatchSourceSample:
    """One held-validation source's fixed available and sampled segment counts."""

    source_episode_id: int
    available_segment_count: int
    sampled_segment_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_episode_id": self.source_episode_id,
            "available_segment_count": self.available_segment_count,
            "sampled_segment_count": len(self.sampled_segment_ids),
            "sampled_segment_ids": list(self.sampled_segment_ids),
        }


@dataclass(frozen=True)
class ReturnTemporalDispatchValidationSample:
    """The immutable smaller held-validation population for policy replay.

    Its response coverage is deliberately scoped to ``sampled_segments``.  It
    must never be described as coverage of all held validation segments.
    """

    schema: str
    max_segments_per_validation_source: int
    all_held_validation_segment_count: int
    source_samples: tuple[ReturnTemporalDispatchSourceSample, ...]
    sampled_segments: tuple[ReturnTemporalDispatchSegment, ...]
    counterfactual_pairs: tuple[ReturnValidationCounterfactualPair, ...]

    @property
    def sampled_source_episode_ids(self) -> tuple[int, ...]:
        return tuple(item.source_episode_id for item in self.source_samples)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "target_rollout_used_for_selection": False,
            "max_segments_per_validation_source": self.max_segments_per_validation_source,
            "all_held_validation_segment_count": self.all_held_validation_segment_count,
            "sampled_held_validation_segment_count": len(self.sampled_segments),
            "source_selection": (
                "per_held_source_stable_segment_sort_evenly_spaced_up_to_fixed_max_8"
            ),
            "counterfactual_token_pool": "sampled_held_validation_real_tokens_only",
            "coverage_scope": "frozen_sampled_held_validation_segments_only",
            "source_samples": [item.as_dict() for item in self.source_samples],
            "sampled_segment_ids": [item.segment_id for item in self.sampled_segments],
            "counterfactual_pair_count": len(self.counterfactual_pairs),
        }


def build_source_balanced_return_temporal_dispatch_sample(
    population: ReturnTemporalDispatchValidationPopulation,
) -> ReturnTemporalDispatchValidationSample:
    """Freeze up to eight evenly-spaced segments for each held validation source.

    Pair selection is then recomputed from *only* the sampled held segments.
    This prevents an unseen full-validation token from influencing the replay
    population and makes the stated coverage boundary exact.
    """

    segments_by_source: dict[int, list[ReturnTemporalDispatchSegment]] = {
        source_episode_id: []
        for source_episode_id in population.validation_source_episode_ids
    }
    for segment in population.validation_segments:
        try:
            segments_by_source[segment.source_episode_id].append(segment)
        except KeyError as exc:
            raise ReturnTemporalDispatchValidationError(
                "held Return segment lies outside the validation source split"
            ) from exc
    source_samples: list[ReturnTemporalDispatchSourceSample] = []
    sampled: list[ReturnTemporalDispatchSegment] = []
    for source_episode_id in population.validation_source_episode_ids:
        available = tuple(
            sorted(segments_by_source[source_episode_id], key=_stable_segment_sort_key)
        )
        if not available:
            raise ReturnTemporalDispatchValidationError(
                f"held Return validation source {source_episode_id} has no stable segments"
            )
        selected = _evenly_spaced_segments(available)
        source_samples.append(
            ReturnTemporalDispatchSourceSample(
                source_episode_id=source_episode_id,
                available_segment_count=len(available),
                sampled_segment_ids=tuple(item.segment_id for item in selected),
            )
        )
        sampled.extend(selected)
    frozen_segments = tuple(sorted(sampled, key=_stable_segment_sort_key))
    sampled_population = replace(population, validation_segments=frozen_segments)
    pairs = build_return_validation_counterfactual_pairs(sampled_population)
    _validate_sample(
        population=population,
        source_samples=source_samples,
        sampled_segments=frozen_segments,
        pairs=pairs,
    )
    return ReturnTemporalDispatchValidationSample(
        schema=RETURN_TEMPORAL_DISPATCH_SAMPLE_SCHEMA,
        max_segments_per_validation_source=(
            RETURN_TEMPORAL_DISPATCH_MAX_SEGMENTS_PER_VALIDATION_SOURCE
        ),
        all_held_validation_segment_count=len(population.validation_segments),
        source_samples=tuple(source_samples),
        sampled_segments=frozen_segments,
        counterfactual_pairs=pairs,
    )


def _evenly_spaced_segments(
    segments: tuple[ReturnTemporalDispatchSegment, ...],
) -> tuple[ReturnTemporalDispatchSegment, ...]:
    if len(segments) <= RETURN_TEMPORAL_DISPATCH_MAX_SEGMENTS_PER_VALIDATION_SOURCE:
        return segments
    positions = np.linspace(
        0,
        len(segments) - 1,
        num=RETURN_TEMPORAL_DISPATCH_MAX_SEGMENTS_PER_VALIDATION_SOURCE,
        dtype=np.int64,
    )
    if len(set(int(value) for value in positions)) != len(positions):
        raise AssertionError("fixed Return sample positions are unexpectedly duplicated")
    return tuple(segments[int(index)] for index in positions)


def _validate_sample(
    *,
    population: ReturnTemporalDispatchValidationPopulation,
    source_samples: list[ReturnTemporalDispatchSourceSample],
    sampled_segments: tuple[ReturnTemporalDispatchSegment, ...],
    pairs: tuple[ReturnValidationCounterfactualPair, ...],
) -> None:
    if len(source_samples) != len(population.validation_source_episode_ids):
        raise AssertionError("Return source-balanced sample omitted a validation source")
    if any(
        item.available_segment_count < len(item.sampled_segment_ids)
        or len(item.sampled_segment_ids)
        > RETURN_TEMPORAL_DISPATCH_MAX_SEGMENTS_PER_VALIDATION_SOURCE
        for item in source_samples
    ):
        raise AssertionError("Return source-balanced sample exceeds its fixed maximum")
    sampled_ids = tuple(item.segment_id for item in sampled_segments)
    if len(sampled_ids) != len(set(sampled_ids)):
        raise ReturnTemporalDispatchValidationError("Return sampled segment ids are duplicated")
    if len(pairs) != len(sampled_segments):
        raise AssertionError("Return sampled pairs do not cover exactly the sampled segments")
    if {pair.baseline_segment.segment_id for pair in pairs} != set(sampled_ids):
        raise AssertionError("Return sampled pair baselines differ from sampled segments")
    sampled_sources = {item.source_episode_id for item in sampled_segments}
    if not sampled_sources <= set(population.validation_source_episode_ids):
        raise ReturnTemporalDispatchValidationError("Return sampled segment leaves held validation")
    if any(pair.alternate_token_source_episode_id not in sampled_sources for pair in pairs):
        raise ReturnTemporalDispatchValidationError(
            "Return sampled alternate token was not drawn from sampled held validation"
        )


def _stable_segment_sort_key(segment: ReturnTemporalDispatchSegment) -> tuple[int, int, str]:
    return (
        segment.primitive_episode_id,
        segment.frames[0].action_index,
        segment.segment_id,
    )


__all__ = [
    "RETURN_TEMPORAL_DISPATCH_MAX_SEGMENTS_PER_VALIDATION_SOURCE",
    "RETURN_TEMPORAL_DISPATCH_SAMPLE_SCHEMA",
    "ReturnTemporalDispatchSourceSample",
    "ReturnTemporalDispatchValidationSample",
    "build_source_balanced_return_temporal_dispatch_sample",
]
