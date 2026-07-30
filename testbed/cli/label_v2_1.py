"""Create relabeled sibling datasets with Stage-1 V2.1 `/v2` annotations."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

import yaml

from testbed.data.hdf5_io import list_episodes, read_episode, write_v2_extension
from testbed.data.v2_1 import label_episode_v2_1
from testbed.data.vds import (
    EPISODE_STORAGE_MODES,
    STORAGE_MODE_COPY,
    STORAGE_MODE_VDS,
    write_lineage_json,
    write_vds_episode,
)
from testbed.planner.boundary_detector import (
    QUALIFIED_DIG_START_MODE_PROGRESS,
    QUALIFIED_DIG_START_MODES,
)


def _default_relabeled_name(dataset_name: str) -> str:
    if "v2_1" in dataset_name:
        return f"{dataset_name}_relabeled"
    return f"{dataset_name}_v2_1_relabeled"


def _load_label_config_sections(
    config_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if config_path is None:
        return {}, {}
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}
    if not isinstance(config, dict):
        raise ValueError(f"Label config {config_path} must be a YAML mapping.")
    return dict(config.get("success", {}) or {}), dict(config.get("reward", {}) or {})


_TRANSFER_LABEL_METADATA_KEYS = (
    "scenario_id",
    "goal_token_dim",
    "goal_token_version",
    "phase_version",
    "work_stage_version",
    "scenario_manifest_version",
    "v2_enabled",
    "transition_source",
    "qualified_dig_start_mode",
    "stage_success_version",
    "stage_success_dig_min_payload_gain_kg",
    "stage_success_dig_min_depth_m",
    "stage_success_dump_min_deposit_delta_kg",
    "stage_success_dump_min_deposited_fraction",
    "label_config_path",
)


def _metadata_for_transferred_v2_labels(
    *,
    replay_metadata: dict[str, Any],
    label_metadata: dict[str, Any],
    label_source_path: Path,
) -> dict[str, Any]:
    metadata = dict(replay_metadata)
    for key in _TRANSFER_LABEL_METADATA_KEYS:
        if key in label_metadata:
            metadata[key] = label_metadata[key]
    metadata.update(
        {
            "label_storage_mode": "transfer",
            "v2_label_source_path": str(label_source_path.resolve()),
            "v2_label_source_dataset": str(label_source_path.parent.resolve()),
        }
    )
    return metadata


def _validate_transferred_v2_payload(
    *,
    source_path: Path,
    replay_episode: dict[str, Any],
    label_episode: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    v2_payload = label_episode.get("v2")
    if not v2_payload:
        raise ValueError(
            f"Label-source episode {source_path} is missing /v2; "
            "run tb-label-v2_1 on the source dataset first."
        )
    step_payload = dict(v2_payload.get("step", {}) or {})
    replay_len = int(len(replay_episode["actions"]))
    source_len = int(len(label_episode["actions"]))
    if replay_len != source_len:
        raise ValueError(
            f"Cannot transfer /v2 labels from {source_path.name}: replay length "
            f"{replay_len} != label-source length {source_len}."
        )
    for key, value in step_payload.items():
        if len(value) != replay_len:
            raise ValueError(
                f"Cannot transfer /v2/step/{key} from {source_path.name}: "
                f"length {len(value)} != episode length {replay_len}."
            )
    return {
        "step": step_payload,
        "cycle": dict(v2_payload.get("cycle", {}) or {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-label-v2_1",
        description=(
            "Generate Stage-1 multicycle /v2 labels and write them to a sibling "
            "relabeled dataset directory."
        ),
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Directory containing raw episode_*.hdf5 files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory for relabeled copies. "
            "Default: <dataset-dir>_relabeled sibling directory."
        ),
    )
    parser.add_argument(
        "--scenario-id",
        type=str,
        default=None,
        help="Optional override for metadata.scenario_id.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            "Optional YAML config whose success/reward sections are reused for "
            "offline relabeling. This keeps stage_success thresholds aligned "
            "with the teleop/eval config used to record the episode."
        ),
    )
    parser.add_argument(
        "--pause-eps",
        type=float,
        default=0.05,
        help="Pause threshold for ||action||_1 < eps (default: 0.05).",
    )
    parser.add_argument(
        "--qualified-dig-start-mode",
        type=str,
        choices=sorted(QUALIFIED_DIG_START_MODES),
        default=QUALIFIED_DIG_START_MODE_PROGRESS,
        help=(
            "Boundary detector mode for /v2/step/qualified_dig_start_mask. "
            "Use contact_depth for small buckets where mass progress lags "
            "the physical dig entry."
        ),
    )
    parser.add_argument(
        "--storage-mode",
        type=str,
        choices=EPISODE_STORAGE_MODES,
        default=STORAGE_MODE_COPY,
        help="copy writes relabeled HDF5 copies; vds writes lightweight wrappers.",
    )
    parser.add_argument(
        "--v2-label-source-dir",
        type=Path,
        default=None,
        help=(
            "Optional already-relabeled source root whose /v2 labels are "
            "transferred by episode filename instead of recomputing boundaries. "
            "Use this when a replay only refreshes env_state/images but must "
            "preserve previously QC-accepted cycle boundaries."
        ),
    )
    args = parser.parse_args()
    success_cfg, reward_cfg = _load_label_config_sections(args.config)
    reward_cfg["qualified_dig_start_mode"] = args.qualified_dig_start_mode

    dataset_dir = args.dataset_dir
    output_dir = (
        args.output_dir
        if args.output_dir is not None
        else dataset_dir.parent / _default_relabeled_name(dataset_dir.name)
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    episode_paths = list_episodes(dataset_dir)
    if not episode_paths:
        raise FileNotFoundError(f"No episode_*.hdf5 files found under {dataset_dir}")
    label_source_dir = args.v2_label_source_dir
    label_source_by_name: dict[str, Path] = {}
    if label_source_dir is not None:
        label_source_paths = list_episodes(label_source_dir)
        if not label_source_paths:
            raise FileNotFoundError(
                f"No episode_*.hdf5 files found under label source {label_source_dir}"
            )
        label_source_by_name = {path.name: path for path in label_source_paths}

    labeled = 0
    for source_path in episode_paths:
        episode = read_episode(source_path, load_images=False)
        metadata = dict(episode.get("metadata", {}))
        if label_source_dir is not None:
            try:
                label_source_path = label_source_by_name[source_path.name]
            except KeyError as exc:
                raise FileNotFoundError(
                    f"Label source {label_source_dir} has no episode matching "
                    f"{source_path.name}."
                ) from exc
            label_episode = read_episode(label_source_path, load_images=False)
            v2_payload = _validate_transferred_v2_payload(
                source_path=label_source_path,
                replay_episode=episode,
                label_episode=label_episode,
            )
            metadata_updates = _metadata_for_transferred_v2_labels(
                replay_metadata=metadata,
                label_metadata=dict(label_episode.get("metadata", {})),
                label_source_path=label_source_path,
            )
        else:
            scenario_id = (
                str(args.scenario_id)
                if args.scenario_id
                else str(metadata.get("scenario_id", "")).strip()
            )
            if not scenario_id:
                raise KeyError(
                    f"Episode {source_path.name} is missing metadata.scenario_id; "
                    "pass --scenario-id to label it explicitly."
                )
            env_state = episode.get("env_state")
            if env_state is None:
                raise ValueError(
                    f"Episode {source_path.name} is missing env_state; cannot generate /v2 labels."
                )

            v2_payload, metadata_updates = label_episode_v2_1(
                qpos=episode["qpos"],
                actions=episode["actions"],
                env_state=env_state,
                metadata=metadata,
                scenario_id=scenario_id,
                pause_action_eps=args.pause_eps,
                reward_cfg=reward_cfg,
                success_cfg=success_cfg,
            )
            if args.config is not None:
                metadata_updates["label_config_path"] = str(args.config.resolve())

        target_path = output_dir / source_path.name
        if str(args.storage_mode) == STORAGE_MODE_VDS:
            relabeled_metadata = dict(metadata)
            relabeled_metadata.update(metadata_updates)
            relabeled_metadata.setdefault("label_storage_mode", STORAGE_MODE_VDS)
            write_vds_episode(
                target_path,
                source_path=source_path,
                crop=slice(0, int(len(episode["actions"]))),
                metadata=relabeled_metadata,
                v2_step_overlay=dict(v2_payload.get("step", {}) or {}),
                v2_cycle_payload=dict(v2_payload.get("cycle", {}) or {}),
                action_src_types=episode.get("action_src_types"),
                action_src_ids=episode.get("action_src_ids"),
            )
        else:
            shutil.copy2(source_path, target_path)
            write_v2_extension(
                target_path, v2=v2_payload, metadata_updates=metadata_updates
            )
        labeled += 1

    write_lineage_json(
        output_dir,
        builder="tb-label-v2_1",
        storage_mode=str(args.storage_mode),
        source_roots=[dataset_dir],
        input_dataset_ids=[dataset_dir.name],
        schema_versions={"hdf5": "1.1", "v2_labels": "v2_1"},
        extra={
            "scenario_id": str(args.scenario_id or ""),
            "qualified_dig_start_mode": str(args.qualified_dig_start_mode),
            "config": "" if args.config is None else str(args.config.resolve()),
            "v2_label_source_dir": (
                "" if label_source_dir is None else str(label_source_dir.resolve())
            ),
        },
    )
    print(
        f"Labeled {labeled} episode(s) from {dataset_dir} into sibling dataset {output_dir}"
    )

if __name__ == "__main__":
    main()
