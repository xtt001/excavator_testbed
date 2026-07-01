"""Offline inventory evidence for terrain calibration sample sources."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any


SCHEMA = "terrain_gold_sample_calibration_inventory_v1"
SOURCE = "explicit_gold_sample_calibration_inventory"
DEFAULT_PROFILE = "explicit_gold_sample_calibration_inventory"
SUPPORTED_SUFFIXES = {".json", ".jsonl"}


def build_gold_sample_calibration_inventory(
    source_paths: Sequence[Any],
    *,
    required_fields: Sequence[Any],
    episode_split_key_candidates: Sequence[Any],
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Inventory explicit candidate gold/calibration sources without fitting models."""

    parsed_required_fields = _parse_field_names(required_fields)
    parsed_split_keys = _parse_field_names(episode_split_key_candidates)
    if parsed_required_fields is None:
        return _inventory_result(
            status="invalid_required_fields",
            profile=profile,
            source_paths=[],
            source_summaries=[],
            required_fields=[],
            split_keys=parsed_split_keys or [],
            validation_errors=[
                "required_fields must be a non-empty sequence of non-empty strings",
            ],
        )
    if parsed_split_keys is None:
        return _inventory_result(
            status="invalid_split_keys",
            profile=profile,
            source_paths=[],
            source_summaries=[],
            required_fields=parsed_required_fields,
            split_keys=[],
            validation_errors=[
                "episode_split_key_candidates must be a non-empty sequence of non-empty strings",
            ],
        )

    parsed_source_paths = _parse_source_paths(source_paths)
    if parsed_source_paths is None:
        return _inventory_result(
            status="invalid_source_paths",
            profile=profile,
            source_paths=[],
            source_summaries=[],
            required_fields=parsed_required_fields,
            split_keys=parsed_split_keys,
            validation_errors=[
                "source_paths must be a sequence of explicit file or directory paths",
            ],
        )
    if not parsed_source_paths:
        return _inventory_result(
            status="no_sources",
            profile=profile,
            source_paths=[],
            source_summaries=[],
            required_fields=parsed_required_fields,
            split_keys=parsed_split_keys,
            validation_errors=[],
        )

    missing_paths = [str(path) for path in parsed_source_paths if not path.exists()]
    if missing_paths:
        return _inventory_result(
            status="invalid_source_paths",
            profile=profile,
            source_paths=[str(path) for path in parsed_source_paths],
            source_summaries=[],
            required_fields=parsed_required_fields,
            split_keys=parsed_split_keys,
            validation_errors=[
                "source_paths do not exist: " + ", ".join(missing_paths)
            ],
        )

    source_files = _discover_source_files(parsed_source_paths)
    source_summaries = [
        _summarize_source_file(
            path,
            required_fields=parsed_required_fields,
            split_keys=parsed_split_keys,
        )
        for path in source_files
    ]
    supported_count = sum(
        1 for summary in source_summaries if summary["status"] != "unsupported_source"
    )
    status = "present" if supported_count > 0 else "no_supported_sources"
    return _inventory_result(
        status=status,
        profile=profile,
        source_paths=[str(path) for path in parsed_source_paths],
        source_summaries=source_summaries,
        required_fields=parsed_required_fields,
        split_keys=parsed_split_keys,
        validation_errors=[],
    )


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
    required_fields: list[str],
    split_keys: list[str],
) -> dict[str, Any]:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return _source_summary(
            path=path,
            status="unsupported_source",
            source_kind="unsupported",
            records=[],
            required_fields=required_fields,
            split_keys=split_keys,
            parser_errors=[],
            unsupported_reason="unsupported_file_suffix",
            metadata_document=False,
        )

    if path.suffix.lower() == ".jsonl":
        records, parser_errors = _read_jsonl_records(path)
        return _source_summary(
            path=path,
            status="parse_error" if parser_errors else "present",
            source_kind="jsonl_records",
            records=records,
            required_fields=required_fields,
            split_keys=split_keys,
            parser_errors=parser_errors,
            unsupported_reason=None,
            metadata_document=False,
        )

    records, parser_errors, metadata_document = _read_json_records(path)
    return _source_summary(
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
        required_fields=required_fields,
        split_keys=split_keys,
        parser_errors=parser_errors,
        unsupported_reason=None,
        metadata_document=metadata_document,
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


def _source_summary(
    *,
    path: Path,
    status: str,
    source_kind: str,
    records: list[dict[str, Any]],
    required_fields: list[str],
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
        "usable_record_count": _usable_record_count(
            records,
            required_fields=required_fields,
            split_keys=split_keys,
        ),
        "field_presence_counts": _field_presence_counts(records, required_fields),
        "missing_required_field_counts": _missing_required_field_counts(
            records,
            required_fields,
        ),
        "records_missing_any_required_field_count": (
            _records_missing_any_required_field_count(records, required_fields)
        ),
        "split_key_presence_counts": _field_presence_counts(records, split_keys),
        "detected_split_keys": _detected_fields(records, split_keys),
        "distinct_split_group_counts": _distinct_group_counts(records, split_keys),
        "records_with_any_split_key_count": _records_with_any_split_key_count(
            records,
            split_keys,
        ),
        "split_group_values": _split_group_values(records, split_keys),
        "parser_errors": parser_errors,
        "unsupported_reason": unsupported_reason,
    }


def _inventory_result(
    *,
    status: str,
    profile: str,
    source_paths: list[str],
    source_summaries: list[dict[str, Any]],
    required_fields: list[str],
    split_keys: list[str],
    validation_errors: list[str],
) -> dict[str, Any]:
    total_record_count = sum(summary["record_count"] for summary in source_summaries)
    usable_record_count = sum(
        summary["usable_record_count"] for summary in source_summaries
    )
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
        "total_record_count": total_record_count,
        "usable_record_count": usable_record_count,
        "source_summaries": source_summaries,
        "field_summary": _field_summary(source_summaries, required_fields),
        "split_summary": _split_summary(source_summaries, split_keys),
        "validation_errors": validation_errors,
        "missing_provenance": _missing_provenance(),
    }


def _field_summary(
    source_summaries: list[dict[str, Any]],
    required_fields: list[str],
) -> dict[str, Any]:
    total_record_count = sum(summary["record_count"] for summary in source_summaries)
    presence_counts = {
        field: sum(
            summary["field_presence_counts"].get(field, 0)
            for summary in source_summaries
        )
        for field in required_fields
    }
    return {
        "required_fields": required_fields,
        "field_presence_counts": presence_counts,
        "missing_required_field_counts": {
            field: total_record_count - count
            for field, count in presence_counts.items()
        },
        "records_missing_any_required_field_count": sum(
            summary.get("records_missing_any_required_field_count", 0)
            for summary in source_summaries
        ),
    }


def _split_summary(
    source_summaries: list[dict[str, Any]],
    split_keys: list[str],
) -> dict[str, Any]:
    presence_counts = {
        key: sum(
            summary["split_key_presence_counts"].get(key, 0)
            for summary in source_summaries
        )
        for key in split_keys
    }
    distinct_groups = {
        key: len(
            set().union(
                *[
                    set(summary.get("split_group_values", {}).get(key, []))
                    for summary in source_summaries
                ]
            )
        )
        for key in split_keys
    }
    return {
        "episode_split_key_candidates": split_keys,
        "detected_split_keys": [key for key in split_keys if presence_counts[key] > 0],
        "records_with_any_split_key_count": sum(
            summary.get("records_with_any_split_key_count", 0)
            for summary in source_summaries
        ),
        "split_key_presence_counts": presence_counts,
        "distinct_split_group_counts": distinct_groups,
    }


def _field_presence_counts(
    records: list[dict[str, Any]],
    fields: list[str],
) -> dict[str, int]:
    return {
        field: sum(1 for record in records if _field_present(record, field))
        for field in fields
    }


def _missing_required_field_counts(
    records: list[dict[str, Any]],
    required_fields: list[str],
) -> dict[str, int]:
    record_count = len(records)
    return {
        field: record_count
        - sum(1 for record in records if _field_present(record, field))
        for field in required_fields
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
    required_fields: list[str],
    split_keys: list[str],
) -> int:
    return sum(
        1
        for record in records
        if all(_field_present(record, field) for field in required_fields)
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
        "calibrated_effect_model_status": "not_fit",
        "capability_model_status": "not_fit",
        "episode_split_semantics_status": "explicit_candidates_only",
        "label_semantics_status": "explicit_required_fields_only",
        "production_integration_status": "not_integrated",
    }


__all__ = ["build_gold_sample_calibration_inventory"]
