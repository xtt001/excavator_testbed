from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from testbed.eval.act_support_contract_audit import (
    SUPPORT_CONTRACT_VERSION,
    run_support_contract_audit,
)

FEATURE_ORDER = tuple(
    [f"qpos[{index}]" for index in range(4)]
    + [f"qvel[{index}]" for index in range(4)]
    + ["condition[0]"]
)


@dataclass(frozen=True)
class _Rows:
    feature_order: tuple[str, ...]
    train_features: np.ndarray
    validation_features: np.ndarray
    validation_provenance: dict[str, Any]


@dataclass(frozen=True)
class _Candidate:
    candidate_id: str
    lower: np.ndarray
    upper: np.ndarray
    threshold_rule: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "lower": self.lower,
            "upper": self.upper,
            "threshold_rule": self.threshold_rule,
        }


@dataclass(frozen=True)
class _Assessment:
    frame_in_support: np.ndarray
    threshold: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "frame_in_support": self.frame_in_support,
            "threshold": self.threshold,
        }


@dataclass(frozen=True)
class _OodReference:
    features: np.ndarray
    synthetic_obvious_ood_provenance: dict[str, Any]


def _rows() -> _Rows:
    train = np.asarray(
        [np.full(len(FEATURE_ORDER), value, dtype=np.float64) for value in np.linspace(0.1, 0.9, 20)]
    )
    validation = np.asarray(
        [
            np.full(len(FEATURE_ORDER), 0.2, dtype=np.float64),
            np.full(len(FEATURE_ORDER), 0.4, dtype=np.float64),
            np.full(len(FEATURE_ORDER), 0.6, dtype=np.float64),
            np.full(len(FEATURE_ORDER), 1.2, dtype=np.float64),
        ]
    )
    return _Rows(
        feature_order=FEATURE_ORDER,
        train_features=train,
        validation_features=validation,
        validation_provenance={"source_partition": "held_out_validation"},
    )


def _fitter(rows: _Rows) -> dict[str, _Candidate]:
    width = len(rows.feature_order)
    return {
        "axis_p01_p99_v1": _Candidate(
            "axis_p01_p99_v1",
            np.zeros(width),
            np.ones(width),
            "axis_p01_p99",
        ),
        "joint_regularized_mahalanobis_p99_v2": _Candidate(
            "joint_regularized_mahalanobis_p99_v2",
            np.full(width, -1.0),
            np.full(width, 2.0),
            "regularized_mahalanobis_p99",
        ),
        "axis_p0005_p9995_v2": _Candidate(
            "axis_p0005_p9995_v2",
            np.full(width, -2.0),
            np.full(width, 3.0),
            "axis_p0005_p9995",
        ),
    }


def _assessor(candidate: _Candidate, features: np.ndarray) -> _Assessment:
    matrix = np.asarray(features, dtype=np.float64)
    return _Assessment(
        frame_in_support=np.logical_and(
            matrix >= candidate.lower,
            matrix <= candidate.upper,
        ).all(axis=1),
        threshold=1.0,
    )


def _ood_builder(rows: _Rows) -> _OodReference:
    return _OodReference(
        features=np.full((100, len(rows.feature_order)), 100.0, dtype=np.float64),
        synthetic_obvious_ood_provenance={
            "source": "validation_anchors_fixed_perturbation",
            "target_rollout_used": False,
        },
    )


def _segment(
    primitive: str,
    segment_id: str,
    values: list[float],
) -> SimpleNamespace:
    matrix = np.asarray(
        [np.full(len(FEATURE_ORDER), value, dtype=np.float64) for value in values]
    )
    return SimpleNamespace(
        segment_id=segment_id,
        skill_name=primitive,
        start_action_step_id=10,
        end_action_step_id=10 + len(values) - 1,
        feature_matrix=matrix,
    )


def _inputs() -> tuple[dict[str, _Rows], dict[str, list[SimpleNamespace]]]:
    rows = {"dig": _rows(), "return": _rows()}
    segments = {
        "dig": [_segment("dig", "dig:10-12", [0.4, 0.5, 1.2])],
        "return": [
            _segment("return", "return:20-22/qvel", [0.4, 1.2, 0.6]),
            _segment("return", "return:30-31", [0.3, 0.5]),
        ],
    }
    return rows, segments


def _run(tmp_path: Path, *, output_name: str = "audit") -> dict[str, Any]:
    rows, segments = _inputs()
    return run_support_contract_audit(
        source_lineage={"code_sha": "a" * 40, "stage_a_artifact": "immutable"},
        feature_partitions=rows,
        target_segments=segments,
        output_root=tmp_path / output_name,
        candidate_fitter=_fitter,
        candidate_assessor=_assessor,
        obvious_ood_builder=_ood_builder,
    )


def test_selects_validation_qualified_candidate_and_writes_no_overwrite_artifact(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path)
    output = Path(result["output_root"])

    assert result["status"] == "completed"
    assert result["selected_candidate_by_primitive"] == {
        "dig": "joint_regularized_mahalanobis_p99_v2",
        "return": "joint_regularized_mahalanobis_p99_v2",
    }
    assert {path.name for path in output.iterdir()} == {
        "manifest.json",
        "candidates.json",
        "validation.json",
        "target_diagnosis.json",
        "report.md",
        "plots",
    }
    plots = sorted((output / "plots").glob("return_*.svg"))
    assert len(plots) == 2
    assert all("strict-train v1 p01--p99" in plot.read_text(encoding="utf-8") for plot in plots)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    target = json.loads((output / "target_diagnosis.json").read_text(encoding="utf-8"))
    assert manifest["support_contract_version"] == SUPPORT_CONTRACT_VERSION
    assert manifest["target_rollout_used_for_selection"] is False
    assert len(manifest["artifact_files"]["return_distribution_plots"]) == 2
    dig_v1 = validation["primitives"]["dig"]["candidate_validation"][0]
    assert dig_v1["qualification_status"] == "rejected_validation_coverage"
    assert target["primitives"]["return"]["segments"][0]["interpretation"] == (
        "v1_axis_tail_accepted_by_validation_selected_contract"
    )
    assert target["primitives"]["return"]["segments"][0]["cause_attribution"][
        "dominant_group"
    ] == "mixed"
    assert target["primitives"]["return"]["segments"][0]["recorded_target_trace"][
        "frame_lineage"
    ]["status"] == "preassembled_feature_matrix_no_frame_lineage"

    with pytest.raises(FileExistsError, match="already exists"):
        _run(tmp_path)


def test_fixed_priority_breaks_equal_validation_tie_in_favour_of_joint_rule(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path)
    assert result["selected_candidate_by_primitive"]["dig"] == (
        "joint_regularized_mahalanobis_p99_v2"
    )


def test_no_qualified_candidate_keeps_target_diagnosis_but_does_not_classify_v2(
    tmp_path: Path,
) -> None:
    def no_qualification_fitter(rows: _Rows) -> dict[str, _Candidate]:
        candidates = _fitter(rows)
        return {
            candidate_id: _Candidate(
                candidate.candidate_id,
                candidate.lower,
                np.full_like(candidate.upper, 0.5),
                candidate.threshold_rule,
            )
            for candidate_id, candidate in candidates.items()
        }

    rows, segments = _inputs()
    result = run_support_contract_audit(
        source_lineage={"code_sha": "b" * 40},
        feature_partitions=rows,
        target_segments=segments,
        output_root=tmp_path / "no_selection",
        candidate_fitter=no_qualification_fitter,
        candidate_assessor=_assessor,
        obvious_ood_builder=_ood_builder,
    )
    assert result["status"] == "support_contract_not_selected"
    target = json.loads(
        (tmp_path / "no_selection" / "target_diagnosis.json").read_text(encoding="utf-8")
    )
    selected = target["primitives"]["dig"]["segments"][0]["selected_support_contract"]
    assert selected == {"candidate_id": None, "status": "not_evaluated_no_qualified_candidate"}
    assert len(list((tmp_path / "no_selection" / "plots").glob("return_*.svg"))) == 2


def test_accepts_frame_shaped_segments_and_attributes_qvel_without_target_tuning(
    tmp_path: Path,
) -> None:
    rows = {"dig": _rows(), "return": _rows()}
    qpos = np.full(4, 0.5, dtype=np.float64)
    qvel = np.full(4, 0.5, dtype=np.float64)
    qvel[1] = 1.2
    frames = [
        SimpleNamespace(qpos=qpos, qvel=qvel, token=np.asarray([0.5])),
        SimpleNamespace(qpos=qpos, qvel=qvel, token=np.asarray([0.5])),
    ]
    segments = {
        "dig": [_segment("dig", "dig:frames", [0.5, 0.5])],
        "return": [
            SimpleNamespace(
                segment_id="return:frames",
                skill_name="return",
                start_action_step_id=40,
                end_action_step_id=41,
                frames=frames,
            )
        ],
    }
    result = run_support_contract_audit(
        source_lineage={"code_sha": "c" * 40},
        feature_partitions=rows,
        target_segments=segments,
        output_root=tmp_path / "frame_segments",
        candidate_fitter=_fitter,
        candidate_assessor=_assessor,
        obvious_ood_builder=_ood_builder,
    )
    assert result["status"] == "completed"
    target = json.loads(
        (tmp_path / "frame_segments" / "target_diagnosis.json").read_text(encoding="utf-8")
    )
    attribution = target["primitives"]["return"]["segments"][0]["cause_attribution"]
    assert attribution["dominant_group"] == "qvel"
    assert attribution["groups"]["qvel"]["violating_feature_counts"] == {"qvel[1]": 2}
    trace = target["primitives"]["return"]["segments"][0]["recorded_target_trace"]
    assert trace["qvel_trace"][0][1] == pytest.approx(1.2)
    assert trace["shapes"]["qpos"] == [2, 4]
    assert trace["frame_lineage"]["status"] == "recorded_jsonl_hdf5_pre_action_lineage"
