"""Build the frozen cycle-six hard-bottom execution diagnosis."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from testbed.eval.hard_bottom_execution_diagnostic import (
    DEFAULT_HARD_BOTTOM_MARGIN_M,
    DEFAULT_WORKTOOL_WIDTH_M,
    DIAGNOSIS_FILENAME,
    SOURCE_MANIFEST_FILENAME,
    SOURCE_MANIFEST_SCHEMA,
    HardBottomExecutionDiagnosticError,
    analyze_hard_bottom_execution,
)

_SKILLS = ("dig", "carry", "dump", "return")


def build_hard_bottom_execution_diagnostic(
    *,
    results_dir: str | Path,
    video_path: str | Path,
    prior_path: str | Path,
    unity_scene_path: str | Path,
    output_dir: str | Path,
    cycle_index: int = 5,
    hard_bottom_margin_m: float = DEFAULT_HARD_BOTTOM_MARGIN_M,
    worktool_width_m: float = DEFAULT_WORKTOOL_WIDTH_M,
) -> dict[str, Any]:
    """Freeze one failed run by SHA and write two no-overwrite files."""

    destination = Path(output_dir).expanduser()
    manifest_path = destination / SOURCE_MANIFEST_FILENAME
    diagnosis_path = destination / DIAGNOSIS_FILENAME
    existing = [path for path in (manifest_path, diagnosis_path) if path.exists()]
    if existing:
        raise FileExistsError(
            f"hard-bottom diagnostic no-overwrite file exists: {existing[0]}"
        )
    results = _require_directory(results_dir, "results_dir")
    video = _require_file(video_path, "video")
    prior = _require_file(prior_path, "prior")
    scene = _require_file(unity_scene_path, "unity_scene")
    required = {
        "config": results / "eval_resolved_config.yaml",
        "metadata": results / "eval_run_metadata.json",
        "hdf5": results / "hdf5_rollouts/episode_0.hdf5",
        "jsonl": results / "rollouts/rollout_000.jsonl",
        "planner_trace": results / "rollouts/rollout_000_planner_trace.json",
        "summary": results / "rollouts/rollout_000_summary.json",
        "rollout_manifest": results / "rollout_manifest.json",
        "metrics": results / "metrics.json",
        "results_csv": results / "results.csv",
    }
    for label, path in required.items():
        _require_file(path, label)
    config = _load_mapping(required["config"], kind="yaml")
    policy = _mapping(config.get("policy"), "policy")
    _validate_prior_lineage(
        planner=policy.get("dig_cut_planner"),
        prior=prior,
        metadata_path=required["metadata"],
    )
    _validate_scene_sha(config=config, scene=scene)
    external: list[tuple[str, Path]] = [
        ("video/rollout_000.mp4", video),
        ("prior", prior),
        ("unity_scene", scene),
    ]
    for skill in _SKILLS:
        checkpoint = _require_file(
            policy.get(f"{skill}_ckpt_path", ""), f"{skill}_checkpoint"
        )
        checkpoint_dir = Path(
            str(policy.get(f"{skill}_ckpt_dir", checkpoint.parent))
        ).expanduser()
        stats = _require_file(
            checkpoint_dir / "dataset_stats.pkl", f"{skill}_stats"
        )
        external.extend(
            [(f"checkpoint/{skill}", checkpoint), (f"stats/{skill}", stats)]
        )
    analysis = analyze_hard_bottom_execution(
        rollout_hdf5_path=required["hdf5"],
        rollout_jsonl_path=required["jsonl"],
        cycle_index=cycle_index,
        hard_bottom_margin_m=hard_bottom_margin_m,
        worktool_width_m=worktool_width_m,
    )
    result_sources = [
        (f"results/{path.relative_to(results).as_posix()}", path)
        for path in sorted(
            (item for item in results.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(results).as_posix(),
        )
    ]
    manifest = _source_manifest(
        entries=[*result_sources, *external], results_dir=results
    )
    manifest_bytes = _json_bytes(manifest)
    artifact = {
        **analysis,
        "source_manifest": {
            "schema": SOURCE_MANIFEST_SCHEMA,
            "filename": SOURCE_MANIFEST_FILENAME,
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "entry_count": len(manifest["entries"]),
            "freeze_mode": manifest["freeze_mode"],
        },
        "input_paths": {
            "results_dir": str(results.resolve()),
            "rollout_hdf5": str(required["hdf5"].resolve()),
            "rollout_jsonl": str(required["jsonl"].resolve()),
            "video": str(video.resolve()),
            "prior": str(prior.resolve()),
            "unity_scene": str(scene.resolve()),
        },
    }
    artifact_bytes = _json_bytes(artifact)
    destination.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("xb") as handle:
        handle.write(manifest_bytes)
    with diagnosis_path.open("xb") as handle:
        handle.write(artifact_bytes)
    return artifact


def _source_manifest(
    *, entries: Sequence[tuple[str, Path]], results_dir: Path
) -> dict[str, Any]:
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for label, raw_path in entries:
        label = str(label).strip()
        if not label or label in seen:
            raise HardBottomExecutionDiagnosticError(
                f"source_manifest_label_invalid_or_duplicate:{label}"
            )
        seen.add(label)
        path = _require_file(raw_path, f"source:{label}")
        records.append(
            {
                "label": label,
                "path": str(path.resolve()),
                "size_bytes": int(path.stat().st_size),
                "sha256": _sha256(path),
            }
        )
    records.sort(key=lambda item: str(item["label"]))
    composite = hashlib.sha256(
        "\n".join(
            f"{item['label']}:{item['size_bytes']}:{item['sha256']}"
            for item in records
        ).encode()
    ).hexdigest()
    return {
        "schema": SOURCE_MANIFEST_SCHEMA,
        "status": "frozen",
        "freeze_mode": "reference_only_sha256_no_copy",
        "source_results_dir": str(results_dir.resolve()),
        "entry_count": len(records),
        "entries": records,
        "composite_sha256": composite,
    }


def _validate_prior_lineage(
    *, planner: Any, prior: Path, metadata_path: Path
) -> None:
    configured = Path(
        str(_mapping(planner, "dig_cut_planner").get("prior_path", ""))
    ).expanduser()
    if not configured.is_absolute():
        cwd = str(_load_mapping(metadata_path, kind="json").get("cwd", "")).strip()
        if not cwd:
            raise HardBottomExecutionDiagnosticError(
                "relative_prior_path_requires_metadata_cwd"
            )
        configured = Path(cwd) / configured
    if configured.resolve() != prior.resolve():
        raise HardBottomExecutionDiagnosticError(
            "explicit_prior_does_not_match_resolved_config"
        )


def _validate_scene_sha(*, config: Mapping[str, Any], scene: Path) -> None:
    evaluation = _mapping(config.get("eval"), "eval")
    metadata = _mapping(
        evaluation.get("record_hdf5_metadata"), "record_hdf5_metadata"
    )
    scene_id = str(metadata.get("unity_scene_id", ""))
    if "@sha256:" not in scene_id:
        raise HardBottomExecutionDiagnosticError("unity_scene_id_sha256_missing")
    expected = scene_id.rsplit("@sha256:", 1)[1].strip()
    actual = _sha256(scene)
    if expected != actual:
        raise HardBottomExecutionDiagnosticError(
            f"unity_scene_sha256_mismatch:expected={expected}:actual={actual}"
        )


def _load_mapping(path: Path, *, kind: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        value = yaml.safe_load(text) if kind == "yaml" else json.loads(text)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise HardBottomExecutionDiagnosticError(
            f"{kind}_mapping_invalid:{path}"
        ) from exc
    return _mapping(value, kind)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise HardBottomExecutionDiagnosticError(f"{label}_must_be_mapping")
    return dict(value)


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
        ).encode()
    except (TypeError, ValueError) as exc:
        raise HardBottomExecutionDiagnosticError(
            "diagnostic_payload_not_strict_json"
        ) from exc


def _require_file(path: str | Path, label: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        raise HardBottomExecutionDiagnosticError(f"{label}_missing:{candidate}")
    return candidate


def _require_directory(path: str | Path, label: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_dir():
        raise HardBottomExecutionDiagnosticError(f"{label}_missing:{candidate}")
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-hard-bottom-execution-diagnostic",
        description=(
            "Freeze a failed rollout by SHA256 and reconstruct one dig from "
            "its first pre-action observation to the first typed hard-bottom "
            "contact edge."
        ),
    )
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--unity-scene", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cycle-index", type=int, default=5)
    parser.add_argument(
        "--hard-bottom-margin-m",
        type=float,
        default=DEFAULT_HARD_BOTTOM_MARGIN_M,
    )
    parser.add_argument(
        "--worktool-width-m",
        type=float,
        default=DEFAULT_WORKTOOL_WIDTH_M,
    )
    args = parser.parse_args()

    artifact = build_hard_bottom_execution_diagnostic(
        results_dir=args.results_dir,
        video_path=args.video,
        prior_path=args.prior,
        unity_scene_path=args.unity_scene,
        output_dir=args.output_dir,
        cycle_index=args.cycle_index,
        hard_bottom_margin_m=args.hard_bottom_margin_m,
        worktool_width_m=args.worktool_width_m,
    )
    print(
        json.dumps(
            {
                "schema": artifact["schema"],
                "status": artifact["status"],
                "primary_cause": artifact["classification"]["primary_cause"],
                "output": str(
                    (args.output_dir / DIAGNOSIS_FILENAME).resolve()
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
