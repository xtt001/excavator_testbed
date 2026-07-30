from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from testbed.data.coverage_return_transitions import (
    COVERAGE_RETURN_TRANSITION_LIBRARY_SCHEMA,
    RETURN_START_FACTS_FEATURE_ORDER,
    RETURN_START_REACHABILITY_PROFILE,
    build_coverage_return_transition_library,
)

DATA_ROOT = Path(
    "/data/pingfan/excavator_testbed_data/"
    "yulong_strict18_terrain_residual_v0"
)
RETURN_PRIMITIVES = DATA_ROOT / "primitives_copy/return"
RETURN_SPLIT = DATA_ROOT / "splits/return_source_split.yaml"
DIG_PRIMITIVES = DATA_ROOT / "primitives_copy/dig"
DIG_SPLIT = DATA_ROOT / "splits/dig_source_split.yaml"
EXECUTION_LIBRARY = (
    DATA_ROOT / "qc/strict_train_coverage_execution_library_v1_1.json"
)
HAS_STRICT_INPUTS = all(
    path.is_dir() if path.suffix == "" else path.is_file()
    for path in (
        RETURN_PRIMITIVES,
        RETURN_SPLIT,
        DIG_PRIMITIVES,
        DIG_SPLIT,
        EXECUTION_LIBRARY,
    )
)


def _build(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    output = tmp_path / "strict_train_coverage_return_transition_library_v1.json"
    returned = build_coverage_return_transition_library(
        return_primitives_dir=RETURN_PRIMITIVES,
        return_split_path=RETURN_SPLIT,
        dig_primitives_dir=DIG_PRIMITIVES,
        dig_split_path=DIG_SPLIT,
        execution_library_path=EXECUTION_LIBRARY,
        output_path=output,
    )
    assert returned == output.resolve()
    return output, json.loads(output.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def strict_artifact(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, object]:
    _, artifact = _build(tmp_path_factory.mktemp("return_transitions"))
    return artifact


@pytest.mark.skipif(
    not HAS_STRICT_INPUTS,
    reason="strict-18 materialized return/dig inputs are unavailable",
)
def test_return_transition_library_pairs_gold_returns_to_exact_dig_tuples(
    strict_artifact: dict[str, object],
) -> None:
    artifact = strict_artifact

    assert artifact["schema"] == COVERAGE_RETURN_TRANSITION_LIBRARY_SCHEMA
    assert artifact["status"] == "completed"
    assert artifact["coverage_tuple_sample_count"] == 374
    assert artifact["gold_return_sample_count"] == 358
    assert artifact["paired_post_return_tuple_count"] == 353
    assert artifact["post_return_ineligible_tuple_count"] == 21
    assert artifact["cycle0_only_tuple_count"] == 16
    assert artifact["non_gold_return_pair_required_count"] == 5

    source_contract = artifact["source_contract"]
    assert source_contract == {
        "primitive_name": "return",
        "training_tier": "gold",
        "primitive_storage_mode": "copy",
        "return_start_envelope_schema": "return_start_envelope_tokens_v1",
        "return_start_envelope_token_dim": 18,
        "return_start_facts_schema": "return_start_facts_11d_v1",
        "return_start_facts_dim": 11,
    }
    assert artifact["feature_contract"]["order"] == list(
        RETURN_START_FACTS_FEATURE_ORDER
    )

    lineage = artifact["source_lineage"]
    assert lineage["partition"] == "train"
    assert lineage["train_source_episode_ids"] == [
        3,
        6,
        7,
        8,
        9,
        13,
        16,
        19,
        23,
        24,
        25,
        27,
        28,
        29,
        30,
        32,
    ]
    assert lineage["validation_source_episode_ids"] == [33, 34]
    assert lineage["validation_rows_read"] == 0
    assert lineage["non_gold_return_rows_read"] == 0
    assert lineage["partial_layered_salvage_input_views_allowed"] is False

    return_split = yaml.safe_load(RETURN_SPLIT.read_text(encoding="utf-8"))
    official_return_ids = {int(value) for value in return_split["train_ids"]}
    records = artifact["records"]
    assert len(records) == 374
    paired_return_ids = {
        int(record["paired_return_primitive_episode_id"])
        for record in records
        if record["eligibility"]["post_return"]
    }
    assert paired_return_ids <= official_return_ids
    assert len(paired_return_ids) == 353
    assert not {
        int(record["source_episode_id"]) for record in records
    }.intersection({33, 34})

    episode_168 = next(
        record for record in records if record["exemplar_id"] == "episode_168"
    )
    assert episode_168["source_episode_id"] == 24
    assert episode_168["source_cycle_id"] == 1
    assert episode_168["raw_fields_sha256"] == (
        "c167e087f3d41f6db8fe0ad260d5f72c3440b6fab9115fdf55959feacc50991c"
    )
    assert episode_168["eligibility"] == {
        "cycle0": True,
        "post_return": True,
        "reason": "gold_return_transition_pair",
    }
    assert episode_168["paired_return_exemplar_id"] == "episode_158"
    assert episode_168["paired_return_primitive_episode_id"] == 158
    assert episode_168["paired_return_source_cycle_id"] == 0
    assert len(episode_168["return_start_facts_11d"]) == 11
    assert len(episode_168["expert_return_handoff_facts_11d"]) == 11
    assert len(episode_168["expert_dig_start_facts_11d"]) == 11
    assert episode_168["exact_return_start_envelope_tokens_v1"][7:11] == (
        pytest.approx(
            [
                0.5238704085350037,
                0.5414266586303711,
                0.3050084114074707,
                0.3927854895591736,
            ]
        )
    )
    assert episode_168["exact_return_start_envelope_valid_mask"] == [1] * 18
    assert episode_168["expert_return_handoff_facts_11d"][:4] == pytest.approx(
        episode_168["exact_return_start_envelope_tokens_v1"][7:11]
    )
    assert episode_168["expert_dig_start_facts_11d"][:4] == pytest.approx(
        [
            0.5237389802932739,
            0.5639864206314087,
            0.3050016462802887,
            0.42423126101493835,
        ]
    )


@pytest.mark.skipif(
    not HAS_STRICT_INPUTS,
    reason="strict-18 materialized return/dig inputs are unavailable",
)
def test_return_start_reachability_contract_uses_train_only_loo_thresholds(
    strict_artifact: dict[str, object],
) -> None:
    artifact = strict_artifact
    distance = artifact["distance_contract"]

    assert distance["profile"] == RETURN_START_REACHABILITY_PROFILE
    assert distance["calibration_sample_count"] == 358
    assert distance["normalization"]["method"] == "p01_p99_range"
    assert len(distance["normalization"]["p01"]) == 11
    assert len(distance["normalization"]["p99"]) == 11
    assert len(distance["normalization"]["scale"]) == 11
    assert distance["runtime_reference"] == (
        "selected_tuple.return_start_facts_11d"
    )
    assert distance["acceptance"] == "rms_pass AND linf_pass"
    assert distance["metrics"]["rms"]["nearest_neighbor_selection"] == (
        "independent_leave_one_out"
    )
    assert distance["metrics"]["linf"]["nearest_neighbor_selection"] == (
        "independent_leave_one_out"
    )
    assert distance["metrics"]["rms"]["loo_p99_threshold"] == pytest.approx(
        0.2242876880450012
    )
    assert distance["metrics"]["linf"]["loo_p99_threshold"] == pytest.approx(
        0.4098004328849277
    )

    source_lock = artifact["source_lock"]
    assert source_lock["execution_library_sha256"] == hashlib.sha256(
        EXECUTION_LIBRARY.read_bytes()
    ).hexdigest()
    assert source_lock["dig_source_split_sha256"] == hashlib.sha256(
        DIG_SPLIT.read_bytes()
    ).hexdigest()
    assert source_lock["return_source_split_sha256"] == hashlib.sha256(
        RETURN_SPLIT.read_bytes()
    ).hexdigest()


@pytest.mark.skipif(
    not HAS_STRICT_INPUTS,
    reason="strict-18 materialized return/dig inputs are unavailable",
)
def test_return_transition_library_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "return_transitions.json"
    output.write_text("occupied", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build_coverage_return_transition_library(
            return_primitives_dir=RETURN_PRIMITIVES,
            return_split_path=RETURN_SPLIT,
            dig_primitives_dir=DIG_PRIMITIVES,
            dig_split_path=DIG_SPLIT,
            execution_library_path=EXECUTION_LIBRARY,
            output_path=output,
        )
