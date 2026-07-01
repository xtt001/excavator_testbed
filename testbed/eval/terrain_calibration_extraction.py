"""Explicit offline mapping evidence for terrain calibration records."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "terrain_explicit_calibration_record_extraction_v1"
SOURCE = "explicit_calibration_record_extraction"
DEFAULT_PROFILE = "explicit_calibration_record_extraction"
SUPPORTED_SUFFIXES = {".json", ".jsonl"}
SAMPLE_RECORD_LIMIT = 3


def build_explicit_calibration_record_extraction(
    source_paths: Sequence[Any],
    *,
    field_mapping: Mapping[Any, Any],
    required_output_fields: Sequence[Any],
    episode_split_key_candidates: Sequence[Any],
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Extract provisional calibration records only through explicit field mapping."""

    parsed_mapping = _parse_field_mapping(field_mapping)
    parsed_required_fields = _parse_field_names(required_output_fields)
    parsed_split_keys = _parse_field_names(episode_split_key_candidates)
    if parsed_mapping is None:
        return _extraction_result(
            status="invalid_field_mapping",
            profile=profile,
            source_paths=[],
            source_summaries=[],
            field_mapping={},
            required_output_fields=parsed_required_fields or [],
            split_keys=parsed_split_keys or [],
            extracted_records=[],
            validation_errors=[
                "field_mapping must be a non-empty mapping of output fields to raw fields",
            ],
        )
    if parsed_required_fields is None:
        return _extraction_result(
            status="invalid_required_output_fields",
            profile=profile,
            source_paths=[],
            source_summaries=[],
            field_mapping=parsed_mapping,
            required_output_fields=[],
            split_keys=parsed_split_keys or [],
            extracted_records=[],
            validation_errors=[
                "required_output_fields must be a non-empty sequence of non-empty strings",
            ],
        )
    if parsed_split_keys is None:
        return _extraction_result(
            status="invalid_split_keys",
            profile=profile,
            source_paths=[],
            source_summaries=[],
            field_mapping=parsed_mapping,
            required_output_fields=parsed_required_fields,
            split_keys=[],
            extracted_records=[],
            validation_errors=[
                "episode_split_key_candidates must be a non-empty sequence of non-empty strings",
            ],
        )

    parsed_source_paths = _parse_source_paths(source_paths)
    if parsed_source_paths is None:
        return _extraction_result(
            status="invalid_source_paths",
            profile=profile,
            source_paths=[],
            source_summaries=[],
            field_mapping=parsed_mapping,
            required_output_fields=parsed_required_fields,
            split_keys=parsed_split_keys,
            extracted_records=[],
            validation_errors=[
                "source_paths must be a sequence of explicit file or directory paths",
            ],
        )
    if not parsed_source_paths:
        return _extraction_result(
            status="no_sources",
            profile=profile,
            source_paths=[],
            source_summaries=[],
            field_mapping=parsed_mapping,
            required_output_fields=parsed_required_fields,
            split_keys=parsed_split_keys,
            extracted_records=[],
            validation_errors=[],
        )

    missing_paths = [str(path) for path in parsed_source_paths if not path.exists()]
    if missing_paths:
        return _extraction_result(
            status="invalid_source_paths",
            profile=profile,
            source_paths=[str(path) for path in parsed_source_paths],
            source_summaries=[],
            field_mapping=parsed_mapping,
            required_output_fields=parsed_required_fields,
            split_keys=parsed_split_keys,
            extracted_records=[],
            validation_errors=[
                "source_paths do not exist: " + ", ".join(missing_paths)
            ],
        )

    source_files = _discover_source_files(parsed_source_paths)
    source_summaries: list[dict[str, Any]] = []
    extracted_records: list[dict[str, Any]] = []
    for path in source_files:
        source_summary, source_extracted_records = _summarize_source_file(
            path,
            field_mapping=parsed_mapping,
            required_output_fields=parsed_required_fields,
            split_keys=parsed_split_keys,
        )
        source_summaries.append(source_summary)
        extracted_records.extend(source_extracted_records)

    supported_count = sum(
        1 for summary in source_summaries if summary["status"] != "unsupported_source"
    )
    total_source_record_count = sum(
        summary["record_count"] for summary in source_summaries
    )
    if supported_count == 0:
        status = "no_supported_sources"
    elif total_source_record_count == 0:
        status = "no_records"
    else:
        status = "present"
    return _extraction_result(
        status=status,
        profile=profile,
        source_paths=[str(path) for path in parsed_source_paths],
        source_summaries=source_summaries,
        field_mapping=parsed_mapping,
        required_output_fields=parsed_required_fields,
        split_keys=parsed_split_keys,
        extracted_records=extracted_records,
        validation_errors=[],
    )


def _parse_field_mapping(field_mapping: Mapping[Any, Any]) -> dict[str, str] | None:
    if not isinstance(field_mapping, Mapping) or not field_mapping:
        return None
    parsed_mapping: dict[str, str] = {}
    for output_field, raw_field in field_mapping.items():
        if not isinstance(output_field, str) or not output_field:
            return None
        if not isinstance(raw_field, str) or not raw_field:
            return None
        parsed_mapping[output_field] = raw_field
    return parsed_mapping


def _parse_field_names(values: Sequence[Any]) -> list[str] | None:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        return None
    parsed_values: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            return None
        if value not in parsed_values:
            parsed_values.append(value)
    return parsed_values or None


def _parse_source_paths(source_paths: Sequence[Any]) -> list[Path] | None:
    if isinstance(source_paths, (str, bytes)) or not isinstance(source_paths, Sequence):
        return None
    parsed_paths: list[Path] = []
    for source_path in source_paths:
        try:
            parsed_paths.append(Path(source_path))
        except TypeError:
            return None
    return parsed_paths


def _discover_source_files(source_paths: list[Path]) -> list[Path]:
    source_files: list[Path] = []
    for source_path in source_paths:
        if source_path.is_file():
            source_files.append(source_path)
            continue
        source_files.extend(path for path in source_path.rglob("*") if path.is_file())
    return sorted(source_files, key=lambda path: str(path))


def _summarize_source_file(
    path: Path,
    *,
    field_mapping: dict[str, str],
    required_output_fields: list[str],
    split_keys: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return (
            _source_summary(
                path=path,
                status="unsupported_source",
                source_kind="unsupported",
                records=[],
                extracted_records=[],
                required_output_fields=required_output_fields,
                split_keys=split_keys,
                parser_errors=[],
                unsupported_reason="unsupported_file_suffix",
                metadata_document=False,
            ),
            [],
        )

    if path.suffix.lower() == ".jsonl":
        records, parser_errors = _read_jsonl_records(path)
        extracted_records = [
            _extract_record(record, field_mapping) for record in records
        ]
        return (
            _source_summary(
                path=path,
                status="parse_error" if parser_errors else "present",
                source_kind="jsonl_records",
                records=records,
                extracted_records=extracted_records,
                required_output_fields=required_output_fields,
                split_keys=split_keys,
                parser_errors=parser_errors,
                unsupported_reason=None,
                metadata_document=False,
            ),
            extracted_records,
        )

    records, parser_errors, metadata_document = _read_json_records(path)
    extracted_records = [_extract_record(record, field_mapping) for record in records]
    return (
        _source_summary(
            path=path,
            status=(
                "parse_error"
                if parser_errors
                else "metadata_document"
                if metadata_document
                else "present"
            ),
            source_kind="json_metadata_document" if metadata_document else "json_record_list",
            records=records,
            extracted_records=extracted_records,
            required_output_fields=required_output_fields,
            split_keys=split_keys,
            parser_errors=parser_errors,
            unsupported_reason=None,
            metadata_document=metadata_document,
        ),
        extracted_records,
    )


def _read_jsonl_records(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    parser_errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return records, [f"failed to read source: {exc}"]

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            parser_errors.append(f"line {line_number}: {exc.msg}")
            continue
        if not isinstance(parsed, dict):
            parser_errors.append(f"line {line_number}: JSONL record must be an object")
            continue
        records.append(parsed)
    return records, parser_errors


def _read_json_records(path: Path) -> tuple[list[dict[str, Any]], list[str], bool]:
    records: list[dict[str, Any]] = []
    parser_errors: list[str] = []
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return records, [f"failed to read source: {exc}"], False
    except json.JSONDecodeError as exc:
        return records, [exc.msg], False

    if isinstance(parsed, list):
        for index, item in enumerate(parsed):
            if isinstance(item, dict):
                records.append(item)
            else:
                parser_errors.append(f"item {index}: JSON record must be an object")
        return records, parser_errors, False
    if isinstance(parsed, dict):
        return records, parser_errors, True
    return records, ["JSON source must be a list of objects or metadata object"], False


def _extract_record(
    record: dict[str, Any],
    field_mapping: dict[str, str],
) -> dict[str, Any]:
    extracted_record: dict[str, Any] = {}
    for output_field in sorted(field_mapping):
        raw_field = field_mapping[output_field]
        if _field_present(record, raw_field):
            extracted_record[output_field] = record[raw_field]
    return extracted_record


def _source_summary(
    *,
    path: Path,
    status: str,
    source_kind: str,
    records: list[dict[str, Any]],
    extracted_records: list[dict[str, Any]],
    required_output_fields: list[str],
    split_keys: list[str],
    parser_errors: list[str],
    unsupported_reason: str | None,
    metadata_document: bool,
) -> dict[str, Any]:
    return {
        "path": str(path),
        "status": status,
        "source_kind": source_kind,
        "metadata_document": metadata_document,
        "record_count": len(records),
        "extracted_record_count": len(extracted_records),
        "usable_extracted_record_count": _usable_record_count(
            extracted_records,
            required_output_fields=required_output_fields,
            split_keys=split_keys,
        ),
        "output_field_presence_counts": _field_presence_counts(
            extracted_records,
            required_output_fields,
        ),
        "missing_required_output_field_counts": _missing_field_counts(
            extracted_records,
            required_output_fields,
        ),
        "records_missing_any_required_output_field_count": (
            _records_missing_any_required_field_count(
                extracted_records,
                required_output_fields,
            )
        ),
        "split_key_presence_counts": _field_presence_counts(
            extracted_records,
            split_keys,
        ),
        "detected_split_keys": _detected_fields(extracted_records, split_keys),
        "distinct_split_group_counts": _distinct_group_counts(
            extracted_records,
            split_keys,
        ),
        "records_with_any_split_key_count": _records_with_any_split_key_count(
            extracted_records,
            split_keys,
        ),
        "split_group_values": _split_group_values(extracted_records, split_keys),
        "parser_errors": parser_errors,
        "unsupported_reason": unsupported_reason,
    }


def _extraction_result(
    *,
    status: str,
    profile: str,
    source_paths: list[str],
    source_summaries: list[dict[str, Any]],
    field_mapping: dict[str, str],
    required_output_fields: list[str],
    split_keys: list[str],
    extracted_records: list[dict[str, Any]],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "input_source_paths": source_paths,
        "source_count": len(source_summaries),
        "supported_source_count": sum(
            1
            for summary in source_summaries
            if summary["status"] != "unsupported_source"
        ),
        "unsupported_source_count": sum(
            1
            for summary in source_summaries
            if summary["status"] == "unsupported_source"
        ),
        "total_source_record_count": sum(
            summary["record_count"] for summary in source_summaries
        ),
        "extracted_record_count": len(extracted_records),
        "usable_extracted_record_count": _usable_record_count(
            extracted_records,
            required_output_fields=required_output_fields,
            split_keys=split_keys,
        ),
        "mapping_summary": _mapping_summary(field_mapping),
        "extracted_records": extracted_records,
        "source_summaries": source_summaries,
        "missing_output_field_summary": _missing_output_field_summary(
            extracted_records,
            required_output_fields,
        ),
        "split_summary": _split_summary(extracted_records, split_keys),
        "sample_record_shape_evidence": _sample_record_shape_evidence(
            extracted_records,
        ),
        "validation_errors": validation_errors,
        "missing_provenance": _missing_provenance(),
    }


def _mapping_summary(field_mapping: dict[str, str]) -> dict[str, Any]:
    sorted_output_fields = sorted(field_mapping)
    sorted_raw_fields = sorted(set(field_mapping.values()))
    return {
        "mapping_kind": "caller_provided_explicit_raw_field_mapping",
        "no_inference": True,
        "output_to_raw_field_mapping": [
            {"output_field": output_field, "raw_field": field_mapping[output_field]}
            for output_field in sorted_output_fields
        ],
        "mapped_output_fields": sorted_output_fields,
        "mapped_raw_fields": sorted_raw_fields,
    }


def _missing_output_field_summary(
    extracted_records: list[dict[str, Any]],
    required_output_fields: list[str],
) -> dict[str, Any]:
    presence_counts = _field_presence_counts(extracted_records, required_output_fields)
    record_count = len(extracted_records)
    return {
        "required_output_fields": required_output_fields,
        "output_field_presence_counts": presence_counts,
        "missing_required_output_field_counts": {
            field: record_count - count for field, count in presence_counts.items()
        },
        "records_missing_any_required_output_field_count": (
            _records_missing_any_required_field_count(
                extracted_records,
                required_output_fields,
            )
        ),
    }


def _split_summary(
    extracted_records: list[dict[str, Any]],
    split_keys: list[str],
) -> dict[str, Any]:
    presence_counts = _field_presence_counts(extracted_records, split_keys)
    return {
        "episode_split_key_candidates": split_keys,
        "detected_split_keys": [key for key in split_keys if presence_counts[key] > 0],
        "records_with_any_split_key_count": _records_with_any_split_key_count(
            extracted_records,
            split_keys,
        ),
        "split_key_presence_counts": presence_counts,
        "distinct_split_group_counts": _distinct_group_counts(
            extracted_records,
            split_keys,
        ),
    }


def _sample_record_shape_evidence(
    extracted_records: list[dict[str, Any]],
) -> dict[str, Any]:
    sample_records = extracted_records[:SAMPLE_RECORD_LIMIT]
    return {
        "sample_record_limit": SAMPLE_RECORD_LIMIT,
        "sample_record_count": len(sample_records),
        "sample_records": sample_records,
        "raw_fields_carried": False,
    }


def _field_presence_counts(
    records: list[dict[str, Any]],
    fields: list[str],
) -> dict[str, int]:
    return {
        field: sum(1 for record in records if _field_present(record, field))
        for field in fields
    }


def _missing_field_counts(
    records: list[dict[str, Any]],
    fields: list[str],
) -> dict[str, int]:
    record_count = len(records)
    return {
        field: record_count - sum(1 for record in records if _field_present(record, field))
        for field in fields
    }


def _detected_fields(records: list[dict[str, Any]], fields: list[str]) -> list[str]:
    return [
        field
        for field in fields
        if any(_field_present(record, field) for record in records)
    ]


def _distinct_group_counts(
    records: list[dict[str, Any]],
    split_keys: list[str],
) -> dict[str, int]:
    return {
        key: len(
            {
                str(record[key])
                for record in records
                if _field_present(record, key)
            }
        )
        for key in split_keys
    }


def _split_group_values(
    records: list[dict[str, Any]],
    split_keys: list[str],
) -> dict[str, list[str]]:
    return {
        key: sorted(
            {
                str(record[key])
                for record in records
                if _field_present(record, key)
            }
        )
        for key in split_keys
    }


def _usable_record_count(
    records: list[dict[str, Any]],
    *,
    required_output_fields: list[str],
    split_keys: list[str],
) -> int:
    return sum(
        1
        for record in records
        if all(_field_present(record, field) for field in required_output_fields)
        and any(_field_present(record, key) for key in split_keys)
    )


def _records_missing_any_required_field_count(
    records: list[dict[str, Any]],
    required_fields: list[str],
) -> int:
    return sum(
        1
        for record in records
        if not all(_field_present(record, field) for field in required_fields)
    )


def _records_with_any_split_key_count(
    records: list[dict[str, Any]],
    split_keys: list[str],
) -> int:
    return sum(
        1
        for record in records
        if any(_field_present(record, key) for key in split_keys)
    )


def _field_present(record: dict[str, Any], field: str) -> bool:
    return field in record and record[field] is not None


def _missing_provenance() -> dict[str, str]:
    return {
        "official_sample_schema_status": "not_defined",
        "field_mapping_status": "caller_provided_explicit_only",
        "automatic_alias_inference_status": "not_performed",
        "calibrated_effect_model_status": "not_fit",
        "capability_model_status": "not_fit",
        "episode_split_semantics_status": "explicit_candidates_only",
        "label_semantics_status": "explicit_mapping_only",
        "production_integration_status": "not_integrated",
    }


__all__ = ["build_explicit_calibration_record_extraction"]
