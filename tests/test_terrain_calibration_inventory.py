import json

from testbed.eval.terrain_calibration_inventory import (
    build_gold_sample_calibration_inventory,
)


REQUIRED_FIELDS = [
    "candidate_id",
    "expected_removed_volume_m3",
    "payload_volume_m3",
    "success",
]
SPLIT_KEYS = ["episode_id", "rollout_id"]


def test_gold_sample_calibration_inventory_counts_records_fields_and_splits(tmp_path):
    (tmp_path / "records.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "candidate_id": "cut_candidate_a",
                        "expected_removed_volume_m3": 0.03,
                        "payload_volume_m3": 0.02,
                        "success": True,
                        "episode_id": "episode_a",
                    }
                ),
                json.dumps(
                    {
                        "candidate_id": "cut_candidate_b",
                        "expected_removed_volume_m3": 0.04,
                        "success": False,
                        "episode_id": "episode_b",
                    }
                ),
                json.dumps(
                    {
                        "candidate_id": "cut_candidate_c",
                        "expected_removed_volume_m3": 0.05,
                        "payload_volume_m3": 0.04,
                        "success": True,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "records.json").write_text(
        json.dumps(
            [
                {
                    "candidate_id": "cut_candidate_d",
                    "expected_removed_volume_m3": 0.02,
                    "payload_volume_m3": 0.015,
                    "success": True,
                    "rollout_id": "rollout_001",
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "summary.json").write_text(
        json.dumps({"status": "metadata_only", "record_count": 4}),
        encoding="utf-8",
    )
    (tmp_path / "notes.txt").write_text("not calibration records", encoding="utf-8")

    inventory = build_gold_sample_calibration_inventory(
        [tmp_path],
        required_fields=REQUIRED_FIELDS,
        episode_split_key_candidates=SPLIT_KEYS,
    )

    assert inventory["status"] == "present"
    assert inventory["schema"] == "terrain_gold_sample_calibration_inventory_v1"
    assert inventory["source"] == "explicit_gold_sample_calibration_inventory"
    assert inventory["offline_only"] is True
    assert inventory["source_count"] == 4
    assert inventory["supported_source_count"] == 3
    assert inventory["unsupported_source_count"] == 1
    assert inventory["total_record_count"] == 4
    assert inventory["usable_record_count"] == 2
    assert inventory["field_summary"] == {
        "required_fields": REQUIRED_FIELDS,
        "field_presence_counts": {
            "candidate_id": 4,
            "expected_removed_volume_m3": 4,
            "payload_volume_m3": 3,
            "success": 4,
        },
        "missing_required_field_counts": {
            "candidate_id": 0,
            "expected_removed_volume_m3": 0,
            "payload_volume_m3": 1,
            "success": 0,
        },
        "records_missing_any_required_field_count": 1,
    }
    assert inventory["observed_field_catalog"] == {
        "total_observed_field_count": 6,
        "sort_order": "field_ascending",
        "field_presence_counts": [
            {"field": "candidate_id", "record_count": 4},
            {"field": "episode_id", "record_count": 2},
            {"field": "expected_removed_volume_m3", "record_count": 4},
            {"field": "payload_volume_m3", "record_count": 3},
            {"field": "rollout_id", "record_count": 1},
            {"field": "success", "record_count": 4},
        ],
    }
    assert inventory["schema_gap_summary"] == {
        "required_fields_absent_from_all_records": [],
        "required_fields_partially_present": ["payload_volume_m3"],
        "required_fields_present_in_all_records": [
            "candidate_id",
            "expected_removed_volume_m3",
            "success",
        ],
        "split_key_candidates_absent_from_all_records": [],
        "split_key_candidates_present_in_records": ["episode_id", "rollout_id"],
        "total_record_count": 4,
        "usable_record_count": 2,
        "records_missing_any_required_field_count": 1,
        "records_with_any_split_key_count": 3,
        "usable_record_implication": "some_records_usable_for_explicit_required_fields_and_split_keys",
    }
    assert inventory["split_summary"] == {
        "episode_split_key_candidates": SPLIT_KEYS,
        "detected_split_keys": ["episode_id", "rollout_id"],
        "records_with_any_split_key_count": 3,
        "split_key_presence_counts": {"episode_id": 2, "rollout_id": 1},
        "distinct_split_group_counts": {"episode_id": 2, "rollout_id": 1},
    }
    assert inventory["missing_provenance"] == {
        "official_sample_schema_status": "not_defined",
        "calibrated_effect_model_status": "not_fit",
        "capability_model_status": "not_fit",
        "episode_split_semantics_status": "explicit_candidates_only",
        "label_semantics_status": "explicit_required_fields_only",
        "production_integration_status": "not_integrated",
    }
    assert "selected" not in inventory
    assert "pass" not in inventory


def test_gold_sample_calibration_inventory_stays_present_when_no_records_are_usable(tmp_path):
    path = tmp_path / "records.jsonl"
    path.write_text(
        json.dumps(
            {
                "candidate_id": "cut_candidate_a",
                "expected_removed_volume_m3": 0.03,
            }
        ),
        encoding="utf-8",
    )

    inventory = build_gold_sample_calibration_inventory(
        [path],
        required_fields=REQUIRED_FIELDS,
        episode_split_key_candidates=SPLIT_KEYS,
    )

    assert inventory["status"] == "present"
    assert inventory["total_record_count"] == 1
    assert inventory["usable_record_count"] == 0
    assert inventory["field_summary"]["missing_required_field_counts"] == {
        "candidate_id": 0,
        "expected_removed_volume_m3": 0,
        "payload_volume_m3": 1,
        "success": 1,
    }
    assert inventory["observed_field_catalog"]["field_presence_counts"] == [
        {"field": "candidate_id", "record_count": 1},
        {"field": "expected_removed_volume_m3", "record_count": 1},
    ]
    assert inventory["schema_gap_summary"] == {
        "required_fields_absent_from_all_records": [
            "payload_volume_m3",
            "success",
        ],
        "required_fields_partially_present": [],
        "required_fields_present_in_all_records": [
            "candidate_id",
            "expected_removed_volume_m3",
        ],
        "split_key_candidates_absent_from_all_records": ["episode_id", "rollout_id"],
        "split_key_candidates_present_in_records": [],
        "total_record_count": 1,
        "usable_record_count": 0,
        "records_missing_any_required_field_count": 1,
        "records_with_any_split_key_count": 0,
        "usable_record_implication": "no_usable_records_for_explicit_required_fields_and_split_keys",
    }
    assert inventory["split_summary"]["records_with_any_split_key_count"] == 0
    assert inventory["source_summaries"][0]["usable_record_count"] == 0


def test_gold_sample_calibration_inventory_reports_input_validation_statuses(tmp_path):
    missing_path = tmp_path / "missing.jsonl"

    assert (
        build_gold_sample_calibration_inventory(
            [],
            required_fields=REQUIRED_FIELDS,
            episode_split_key_candidates=SPLIT_KEYS,
        )["status"]
        == "no_sources"
    )
    assert (
        build_gold_sample_calibration_inventory(
            [missing_path],
            required_fields=REQUIRED_FIELDS,
            episode_split_key_candidates=SPLIT_KEYS,
        )["status"]
        == "invalid_source_paths"
    )
    assert (
        build_gold_sample_calibration_inventory(
            [tmp_path],
            required_fields=[],
            episode_split_key_candidates=SPLIT_KEYS,
        )["status"]
        == "invalid_required_fields"
    )
    assert (
        build_gold_sample_calibration_inventory(
            [tmp_path],
            required_fields=REQUIRED_FIELDS,
            episode_split_key_candidates=[],
        )["status"]
        == "invalid_split_keys"
    )


def test_gold_sample_calibration_inventory_reports_no_supported_sources(tmp_path):
    (tmp_path / "notes.txt").write_text("unsupported", encoding="utf-8")

    inventory = build_gold_sample_calibration_inventory(
        [tmp_path],
        required_fields=REQUIRED_FIELDS,
        episode_split_key_candidates=SPLIT_KEYS,
    )

    assert inventory["status"] == "no_supported_sources"
    assert inventory["source_count"] == 1
    assert inventory["supported_source_count"] == 0
    assert inventory["unsupported_source_count"] == 1
    assert inventory["source_summaries"][0]["status"] == "unsupported_source"


def test_gold_sample_calibration_inventory_preserves_parser_errors(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{not valid json}\n", encoding="utf-8")

    inventory = build_gold_sample_calibration_inventory(
        [path],
        required_fields=REQUIRED_FIELDS,
        episode_split_key_candidates=SPLIT_KEYS,
    )

    assert inventory["status"] == "present"
    assert inventory["supported_source_count"] == 1
    assert inventory["total_record_count"] == 0
    assert inventory["usable_record_count"] == 0
    assert inventory["source_summaries"][0]["status"] == "parse_error"
    assert inventory["source_summaries"][0]["parser_errors"]
