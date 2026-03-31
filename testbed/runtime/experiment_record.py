"""Helpers for writing experiment-level records and comparison registries."""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path
from typing import Any

import yaml


def build_experiment_record(
    *,
    train_ckpt_dir: Path,
    eval_results_dir: Path,
    dataset_dir: Path | None = None,
    experiment_name: str = "",
    notes: str = "",
) -> dict[str, Any]:
    train_run_metadata = _read_json_if_exists(train_ckpt_dir / "run_metadata.json")
    train_resolved_config = _read_yaml_if_exists(train_ckpt_dir / "resolved_config.yaml")
    eval_run_metadata = _read_json_if_exists(eval_results_dir / "eval_run_metadata.json")
    eval_resolved_config = _read_yaml_if_exists(eval_results_dir / "eval_resolved_config.yaml")
    eval_metrics = _read_json_if_exists(eval_results_dir / "metrics.json")
    rollout_manifest = _read_json_if_exists(eval_results_dir / "rollout_manifest.json")

    resolved_dataset_dir = _resolve_dataset_dir(
        explicit_dataset_dir=dataset_dir,
        train_run_metadata=train_run_metadata,
        train_resolved_config=train_resolved_config,
    )
    qc_summary = _read_json_if_exists(resolved_dataset_dir / "qc" / "summary.json") if resolved_dataset_dir else {}
    qc_episodes_csv = resolved_dataset_dir / "qc" / "episodes.csv" if resolved_dataset_dir else None

    failure_means = _mean_failure_counts(rollout_manifest)
    success_rates = dict(rollout_manifest.get("success_rates_by_mode", {}))
    success_counts = dict(rollout_manifest.get("success_counts_by_mode", {}))
    metrics_extra = dict(eval_metrics.get("extra", {}))

    generated_at = datetime.datetime.utcnow().isoformat()
    record_name = experiment_name or _default_experiment_name(
        train_ckpt_dir=train_ckpt_dir,
        eval_results_dir=eval_results_dir,
        generated_at=generated_at,
    )

    return {
        "record_type": "experiment_record",
        "generated_at": generated_at,
        "experiment_name": record_name,
        "notes": notes,
        "dataset": {
            "dataset_dir": "" if resolved_dataset_dir is None else str(resolved_dataset_dir.resolve()),
            "qc_summary_path": _existing_path_str(
                None if resolved_dataset_dir is None else resolved_dataset_dir / "qc" / "summary.json"
            ),
            "qc_episodes_csv_path": _existing_path_str(qc_episodes_csv),
            "n_episodes": qc_summary.get("n_episodes"),
            "success_rate": qc_summary.get("success_rate"),
            "episode_length_mean": _nested_get(qc_summary, "episode_length", "mean", default=[None])[0],
            "episode_length_std": _nested_get(qc_summary, "episode_length", "std", default=[None])[0],
        },
        "train": {
            "ckpt_dir": str(train_ckpt_dir.resolve()),
            "run_metadata_path": _existing_path_str(train_ckpt_dir / "run_metadata.json"),
            "resolved_config_path": _existing_path_str(train_ckpt_dir / "resolved_config.yaml"),
            "best_epoch": _nested_get(train_run_metadata, "training_result", "best_epoch"),
            "best_val_loss": _nested_get(train_run_metadata, "training_result", "best_val_loss"),
            "command": train_run_metadata.get("command", ""),
            "split_train_ids": _nested_get(train_run_metadata, "split", "train_ids", default=[]),
            "split_val_ids": _nested_get(train_run_metadata, "split", "val_ids", default=[]),
        },
        "eval": {
            "results_dir": str(eval_results_dir.resolve()),
            "run_metadata_path": _existing_path_str(eval_results_dir / "eval_run_metadata.json"),
            "resolved_config_path": _existing_path_str(eval_results_dir / "eval_resolved_config.yaml"),
            "metrics_path": _existing_path_str(eval_results_dir / "metrics.json"),
            "results_csv_path": _existing_path_str(eval_results_dir / "results.csv"),
            "rollout_manifest_path": _existing_path_str(eval_results_dir / "rollout_manifest.json"),
            "ckpt_path": eval_metrics.get("ckpt_path", ""),
            "n_rollouts": eval_metrics.get("n_rollouts"),
            "avg_return": eval_metrics.get("avg_return"),
            "avg_episode_len": eval_metrics.get("avg_episode_len"),
            "success_mode": metrics_extra.get("success_mode", ""),
            "primary_success_rate": eval_metrics.get("success_rate"),
            "primary_success_count": eval_metrics.get("n_success"),
            "legacy_success_rate": success_rates.get("legacy_success"),
            "legacy_success_count": success_counts.get("legacy_success"),
            "final_hold_success_rate": success_rates.get("final_hold_success"),
            "final_hold_success_count": success_counts.get("final_hold_success"),
            "strict_final_hold_success_rate": success_rates.get("strict_final_hold_success"),
            "strict_final_hold_success_count": success_counts.get("strict_final_hold_success"),
            "dump_complete_final_hold_success_rate": success_rates.get("dump_complete_final_hold_success"),
            "dump_complete_final_hold_success_count": success_counts.get("dump_complete_final_hold_success"),
            "strict_dump_complete_success_rate": success_rates.get("strict_dump_complete_success"),
            "strict_dump_complete_success_count": success_counts.get("strict_dump_complete_success"),
            "avg_final_success_signal": metrics_extra.get("avg_final_success_signal"),
            "avg_max_success_signal": metrics_extra.get("avg_max_success_signal"),
            "avg_final_bucket_mass": metrics_extra.get("avg_final_bucket_mass"),
            "avg_ending_success_consecutive_steps": metrics_extra.get("avg_ending_success_consecutive_steps"),
            "avg_ending_dump_complete_consecutive_steps": metrics_extra.get(
                "avg_ending_dump_complete_consecutive_steps"
            ),
            "mean_failure_counts": failure_means,
        },
        "artifacts": {
            "train_ckpt_dir": str(train_ckpt_dir.resolve()),
            "eval_results_dir": str(eval_results_dir.resolve()),
            "rollout_videos_dir": str((eval_results_dir.parent / "videos").resolve()),
        },
        "raw": {
            "train_run_metadata": train_run_metadata,
            "train_resolved_config": train_resolved_config,
            "eval_run_metadata": eval_run_metadata,
            "eval_resolved_config": eval_resolved_config,
            "eval_metrics": eval_metrics,
            "rollout_manifest": rollout_manifest,
            "dataset_qc_summary": qc_summary,
        },
    }


def write_experiment_record(
    *,
    record: dict[str, Any],
    output_root: Path,
) -> tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    record_dir = output_root / _slugify(record["experiment_name"])
    record_dir.mkdir(parents=True, exist_ok=True)

    json_path = record_dir / "experiment_record.json"
    md_path = record_dir / "experiment_record.md"

    with open(json_path, "w") as f:
        json.dump(record, f, indent=2, sort_keys=False)

    md_path.write_text(render_experiment_record_markdown(record))
    return json_path, md_path


def append_experiment_registry(record: dict[str, Any], registry_csv_path: Path) -> Path:
    registry_csv_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "generated_at": record.get("generated_at", ""),
        "experiment_name": record.get("experiment_name", ""),
        "dataset_dir": _nested_get(record, "dataset", "dataset_dir", default=""),
        "dataset_n_episodes": _nested_get(record, "dataset", "n_episodes", default=""),
        "dataset_success_rate": _nested_get(record, "dataset", "success_rate", default=""),
        "train_ckpt_dir": _nested_get(record, "train", "ckpt_dir", default=""),
        "train_best_epoch": _nested_get(record, "train", "best_epoch", default=""),
        "train_best_val_loss": _nested_get(record, "train", "best_val_loss", default=""),
        "eval_results_dir": _nested_get(record, "eval", "results_dir", default=""),
        "success_mode": _nested_get(record, "eval", "success_mode", default=""),
        "primary_success_rate": _nested_get(record, "eval", "primary_success_rate", default=""),
        "legacy_success_rate": _nested_get(record, "eval", "legacy_success_rate", default=""),
        "final_hold_success_rate": _nested_get(record, "eval", "final_hold_success_rate", default=""),
        "strict_final_hold_success_rate": _nested_get(record, "eval", "strict_final_hold_success_rate", default=""),
        "dump_complete_final_hold_success_rate": _nested_get(record, "eval", "dump_complete_final_hold_success_rate", default=""),
        "strict_dump_complete_success_rate": _nested_get(record, "eval", "strict_dump_complete_success_rate", default=""),
        "avg_return": _nested_get(record, "eval", "avg_return", default=""),
        "avg_episode_len": _nested_get(record, "eval", "avg_episode_len", default=""),
        "avg_final_success_signal": _nested_get(record, "eval", "avg_final_success_signal", default=""),
        "avg_max_success_signal": _nested_get(record, "eval", "avg_max_success_signal", default=""),
        "avg_final_bucket_mass": _nested_get(record, "eval", "avg_final_bucket_mass", default=""),
        "mean_spill_before_target": _nested_get(record, "eval", "mean_failure_counts", "spill_before_target", default=0.0),
        "mean_hard_target_collision": _nested_get(record, "eval", "mean_failure_counts", "hard_target_collision", default=0.0),
        "mean_unsafe_target_distance": _nested_get(record, "eval", "mean_failure_counts", "unsafe_target_distance", default=0.0),
        "notes": record.get("notes", ""),
    }

    write_header = not registry_csv_path.exists()
    with open(registry_csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return registry_csv_path


def render_experiment_record_markdown(record: dict[str, Any]) -> str:
    dataset = record.get("dataset", {})
    train = record.get("train", {})
    eval_record = record.get("eval", {})
    failure_means = dict(eval_record.get("mean_failure_counts", {}))

    lines = [
        f"# Experiment Record - {record.get('experiment_name', '')}",
        "",
        f"- Generated at: `{record.get('generated_at', '')}`",
        f"- Notes: {record.get('notes', '') or '(none)'}",
        "",
        "## Dataset",
        "",
        f"- Dataset dir: `{dataset.get('dataset_dir', '')}`",
        f"- QC summary: `{dataset.get('qc_summary_path', '')}`",
        f"- Episodes: `{dataset.get('n_episodes', '')}`",
        f"- Demo success rate: `{dataset.get('success_rate', '')}`",
        f"- Episode length mean/std: `{dataset.get('episode_length_mean', '')}` / `{dataset.get('episode_length_std', '')}`",
        "",
        "## Train",
        "",
        f"- Checkpoint dir: `{train.get('ckpt_dir', '')}`",
        f"- Best epoch: `{train.get('best_epoch', '')}`",
        f"- Best val loss: `{train.get('best_val_loss', '')}`",
        f"- Run metadata: `{train.get('run_metadata_path', '')}`",
        f"- Resolved config: `{train.get('resolved_config_path', '')}`",
        f"- Command: `{train.get('command', '')}`",
        "",
        "## Eval",
        "",
        f"- Results dir: `{eval_record.get('results_dir', '')}`",
        f"- Success mode: `{eval_record.get('success_mode', '')}`",
        f"- Primary success rate: `{eval_record.get('primary_success_rate', '')}`",
        f"- Legacy success rate: `{eval_record.get('legacy_success_rate', '')}`",
        f"- Final-hold success rate: `{eval_record.get('final_hold_success_rate', '')}`",
        f"- Strict-final-hold success rate: `{eval_record.get('strict_final_hold_success_rate', '')}`",
        f"- Dump-complete-final-hold success rate: `{eval_record.get('dump_complete_final_hold_success_rate', '')}`",
        f"- Strict-dump-complete success rate: `{eval_record.get('strict_dump_complete_success_rate', '')}`",
        f"- Avg return: `{eval_record.get('avg_return', '')}`",
        f"- Avg episode len: `{eval_record.get('avg_episode_len', '')}`",
        f"- Avg final success signal: `{eval_record.get('avg_final_success_signal', '')}`",
        f"- Avg max success signal: `{eval_record.get('avg_max_success_signal', '')}`",
        f"- Avg final bucket mass: `{eval_record.get('avg_final_bucket_mass', '')}`",
        "",
        "## Mean Failure Counts",
        "",
    ]

    if failure_means:
        for name in sorted(failure_means):
            lines.append(f"- `{name}`: `{failure_means[name]}`")
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Eval metrics: `{eval_record.get('metrics_path', '')}`",
            f"- Eval results.csv: `{eval_record.get('results_csv_path', '')}`",
            f"- Rollout manifest: `{eval_record.get('rollout_manifest_path', '')}`",
            f"- Eval run metadata: `{eval_record.get('run_metadata_path', '')}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _resolve_dataset_dir(
    *,
    explicit_dataset_dir: Path | None,
    train_run_metadata: dict[str, Any],
    train_resolved_config: dict[str, Any],
) -> Path | None:
    if explicit_dataset_dir is not None:
        return explicit_dataset_dir
    train_meta_dataset = _nested_get(train_run_metadata, "paths", "dataset_dir")
    if train_meta_dataset:
        return Path(train_meta_dataset)
    train_cfg_dataset = _nested_get(train_resolved_config, "task", "dataset_dir")
    if train_cfg_dataset:
        return Path(train_cfg_dataset)
    return None


def _mean_failure_counts(rollout_manifest: dict[str, Any]) -> dict[str, float]:
    rollouts = list(rollout_manifest.get("rollouts", []))
    if not rollouts:
        return {}
    totals: dict[str, float] = {}
    for rollout in rollouts:
        for name, count in dict(rollout.get("failure_counts", {})).items():
            totals[str(name)] = totals.get(str(name), 0.0) + float(count)
    return {
        name: totals[name] / len(rollouts)
        for name in sorted(totals)
    }


def _default_experiment_name(
    *,
    train_ckpt_dir: Path,
    eval_results_dir: Path,
    generated_at: str,
) -> str:
    stamp = generated_at.replace(":", "").replace("-", "")
    return f"{stamp}_{train_ckpt_dir.name}_{eval_results_dir.parent.name}"


def _slugify(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in text.strip())
    return cleaned or "experiment_record"


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _read_yaml_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _nested_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _existing_path_str(path: Path | None) -> str:
    if path is None:
        return ""
    return str(path.resolve()) if path.exists() else ""
