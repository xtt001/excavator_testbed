import json

from testbed.eval.terrain_calibration_extraction import (
    build_explicit_calibration_record_extraction,
)


FIELD_MAPPING = {
    "telemetry_time_s": "t",
    "telemetry_step_id": "step_id",
    "telemetry_label": "label",
    "telemetry_source_id": "source_id",
}
REQUIRED_OUTPUT_FIELDS = [
    "telemetry_time_s",
    "telemetry_step_id",
    "telemetry_label",
]
SPLIT_KEYS = ["telemetry_source_id"]


def test_explicit_calibration_extraction_maps_only_requested_fields(tmp_path):
    path = tmp_path / "records.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "t": 1.25,
                        "step_id": 10,
                        "label": "dig",
                        "source_id": "episode_a",
                        "ignored_raw": "not carried",
                    }
                ),
                json.dumps(
                    {
                        "t": 2.5,
                        "step_id": 11,
                        "label": "dump",
                        "source_id": "episode_b",
                        "mass_in_bucket_kg": 3.0,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    extraction = build_explicit_calibration_record_extraction(
        [path],
        field_mapping=FIELD_MAPPING,
        required_output_fields=REQUIRED_OUTPUT_FIELDS,
        episode_split_key_candidates=SPLIT_KEYS,
    )

    assert extraction["status"] == "present"
    assert extraction["schema"] == "terrain_explicit_calibration_record_extraction_v1"
    assert extraction["source"] == "explicit_calibration_record_extraction"
    assert extraction["offline_only"] is True
    assert extraction["source_count"] == 1
    assert extraction["supported_source_count"] == 1
    assert extraction["unsupported_source_count"] == 0
    assert extraction["total_source_record_count"] == 2
    assert extraction["extracted_record_count"] == 2
    assert extraction["usable_extracted_record_count"] == 2
    assert extraction["mapping_summary"] == {
        "mapping_kind": "caller_provided_explicit_raw_field_mapping",
        "no_inference": True,
        "output_to_raw_field_mapping": [
            {"output_field": "telemetry_label", "raw_field": "label"},
            {"output_field": "telemetry_source_id", "raw_field": "source_id"},
            {"output_field": "telemetry_step_id", "raw_field": "step_id"},
            {"output_field": "telemetry_time_s", "raw_field": "t"},
        ],
        "mapped_output_fields": [
            "telemetry_label",
            "telemetry_source_id",
            "telemetry_step_id",
            "telemetry_time_s",
        ],
        "mapped_raw_fields": ["label", "source_id", "step_id", "t"],
    }
    assert extraction["extracted_records"] == [
        {
            "telemetry_label": "dig",
            "telemetry_source_id": "episode_a",
            "telemetry_step_id": 10,
            "telemetry_time_s": 1.25,
        },
        {
            "telemetry_label": "dump",
            "telemetry_source_id": "episode_b",
            "telemetry_step_id": 11,
            "telemetry_time_s": 2.5,
        },
    ]
    assert extraction["missing_output_field_summary"] == {
        "required_output_fields": REQUIRED_OUTPUT_FIELDS,
        "output_field_presence_counts": {
            "telemetry_time_s": 2,
            "telemetry_step_id": 2,
            "telemetry_label": 2,
        },
        "missing_required_output_field_counts": {
            "telemetry_time_s": 0,
            "telemetry_step_id": 0,
            "telemetry_label": 0,
        },
        "records_missing_any_required_output_field_count": 0,
    }
    assert extraction["split_summary"] == {
        "episode_split_key_candidates": SPLIT_KEYS,
        "detected_split_keys": ["telemetry_source_id"],
        "records_with_any_split_key_count": 2,
        "split_key_presence_counts": {"telemetry_source_id": 2},
        "distinct_split_group_counts": {"telemetry_source_id": 2},
    }
    assert extraction["sample_record_shape_evidence"] == {
        "sample_record_limit": 3,
        "sample_record_count": 2,
        "sample_records": extraction["extracted_records"],
        "raw_fields_carried": False,
    }
    assert "selected" not in extraction
    assert "pass" not in extraction


def test_explicit_calibration_extraction_reports_missing_mapped_raw_fields(tmp_path):
    path = tmp_path / "records.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"t": 1.0, "step_id": 1, "source_id": "episode_a"}),
                json.dumps({"t": 2.0, "label": "dig"}),
            ]
        ),
        encoding="utf-8",
    )

    extraction = build_explicit_calibration_record_extraction(
        [path],
        field_mapping=FIELD_MAPPING,
        required_output_fields=REQUIRED_OUTPUT_FIELDS,
        episode_split_key_candidates=SPLIT_KEYS,
    )

    assert extraction["status"] == "present"
    assert extraction["extracted_record_count"] == 2
    assert extraction["usable_extracted_record_count"] == 0
    assert extraction["extracted_records"] == [
        {
            "telemetry_source_id": "episode_a",
            "telemetry_step_id": 1,
            "telemetry_time_s": 1.0,
        },
        {
            "telemetry_label": "dig",
            "telemetry_time_s": 2.0,
        },
    ]
    assert extraction["missing_output_field_summary"][
        "missing_required_output_field_counts"
    ] == {
        "telemetry_time_s": 0,
        "telemetry_step_id": 1,
        "telemetry_label": 1,
    }
    assert (
        extraction["missing_output_field_summary"][
            "records_missing_any_required_output_field_count"
        ]
        == 2
    )
    assert extraction["split_summary"]["records_with_any_split_key_count"] == 1


def test_explicit_calibration_extraction_reports_invalid_inputs(tmp_path):
    path = tmp_path / "records.jsonl"
    path.write_text(json.dumps({"t": 1.0}), encoding="utf-8")

    assert (
        build_explicit_calibration_record_extraction(
            [path],
            field_mapping={},
            required_output_fields=REQUIRED_OUTPUT_FIELDS,
            episode_split_key_candidates=SPLIT_KEYS,
        )["status"]
        == "invalid_field_mapping"
    )
    assert (
        build_explicit_calibration_record_extraction(
            [path],
            field_mapping={"telemetry_time_s": 1},
            required_output_fields=REQUIRED_OUTPUT_FIELDS,
            episode_split_key_candidates=SPLIT_KEYS,
        )["status"]
        == "invalid_field_mapping"
    )
    assert (
        build_explicit_calibration_record_extraction(
            [path],
            field_mapping=FIELD_MAPPING,
            required_output_fields=[],
            episode_split_key_candidates=SPLIT_KEYS,
        )["status"]
        == "invalid_required_output_fields"
    )
    assert (
        build_explicit_calibration_record_extraction(
            [path],
            field_mapping=FIELD_MAPPING,
            required_output_fields=REQUIRED_OUTPUT_FIELDS,
            episode_split_key_candidates=[],
        )["status"]
        == "invalid_split_keys"
    )
    assert (
        build_explicit_calibration_record_extraction(
            [tmp_path / "missing.jsonl"],
            field_mapping=FIELD_MAPPING,
            required_output_fields=REQUIRED_OUTPUT_FIELDS,
            episode_split_key_candidates=SPLIT_KEYS,
        )["status"]
        == "invalid_source_paths"
    )


def test_explicit_calibration_extraction_reports_no_supported_sources_or_records(
    tmp_path,
):
    (tmp_path / "notes.txt").write_text("unsupported", encoding="utf-8")
    empty_jsonl = tmp_path / "empty.jsonl"
    empty_jsonl.write_text("", encoding="utf-8")

    no_supported = build_explicit_calibration_record_extraction(
        [tmp_path / "notes.txt"],
        field_mapping=FIELD_MAPPING,
        required_output_fields=REQUIRED_OUTPUT_FIELDS,
        episode_split_key_candidates=SPLIT_KEYS,
    )
    no_records = build_explicit_calibration_record_extraction(
        [empty_jsonl],
        field_mapping=FIELD_MAPPING,
        required_output_fields=REQUIRED_OUTPUT_FIELDS,
        episode_split_key_candidates=SPLIT_KEYS,
    )

    assert no_supported["status"] == "no_supported_sources"
    assert no_supported["unsupported_source_count"] == 1
    assert no_records["status"] == "no_records"
    assert no_records["supported_source_count"] == 1
    assert no_records["extracted_record_count"] == 0


def test_explicit_calibration_extraction_does_not_infer_unmapped_raw_fields(
    tmp_path,
):
    path = tmp_path / "records.jsonl"
    path.write_text(
        json.dumps(
            {
                "t": 1.0,
                "label": "success_like_value",
                "source_id": "episode_like_value",
                "mass_in_bucket_kg": 3.0,
            }
        ),
        encoding="utf-8",
    )

    extraction = build_explicit_calibration_record_extraction(
        [path],
        field_mapping={"telemetry_time_s": "t"},
        required_output_fields=["telemetry_time_s"],
        episode_split_key_candidates=["telemetry_source_id"],
    )

    assert extraction["status"] == "present"
    assert extraction["extracted_records"] == [{"telemetry_time_s": 1.0}]
    assert extraction["usable_extracted_record_count"] == 0
    assert extraction["split_summary"]["records_with_any_split_key_count"] == 0
    assert extraction["mapping_summary"]["mapped_raw_fields"] == ["t"]
    assert "label" not in extraction["extracted_records"][0]
    assert "source_id" not in extraction["extracted_records"][0]
    assert "mass_in_bucket_kg" not in extraction["extracted_records"][0]
