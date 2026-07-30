"""Policy-boundary loader for released box-emptying planning artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from testbed.eval.planned_cut_execution_cascade import (
    load_planned_cut_effect_cascade,
)
from testbed.planner.box_emptying.artifacts import (
    load_box_emptying_artifact_manifest,
)
from testbed.planner.box_emptying.online_provider import (
    BoxEmptyingResidualPlanService,
)


def build_box_emptying_residual_plan_service(
    config: Mapping[str, Any],
) -> BoxEmptyingResidualPlanService:
    """Load the one explicitly released planned-effect route."""

    manifest_path = config.get("effect_artifact_manifest_path")
    if not isinstance(manifest_path, (str, Path)) or not str(manifest_path).strip():
        raise ValueError(
            "box_emptying.effect_artifact_manifest_path is required"
        )
    manifest = load_box_emptying_artifact_manifest(manifest_path)
    predictor = load_planned_cut_effect_cascade(
        manifest.planned_effect_artifact_path,
        device=str(config.get("effect_device", "cpu")),
    )
    planner = dict(config.get("planner", {}) or {})
    known_failures = planner.get("known_failure_candidate_ids", ()) or ()
    if isinstance(known_failures, (str, bytes)):
        raise ValueError("known_failure_candidate_ids must be a sequence")
    return BoxEmptyingResidualPlanService(
        record_predictor=predictor,
        support_envelope=manifest.support_envelope,
        payload_intent_kg=float(planner.get("payload_intent_kg", 60.0)),
        cut_length_m=float(planner.get("cut_length_m", 0.75)),
        bucket_width_m=float(planner.get("bucket_width_m", 0.70)),
        wall_inset_m=float(planner.get("wall_inset_m", 0.30)),
        known_failure_candidate_ids=frozenset(
            str(value) for value in known_failures
        ),
    )


__all__ = ["build_box_emptying_residual_plan_service"]
