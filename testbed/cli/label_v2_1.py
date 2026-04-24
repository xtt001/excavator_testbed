"""Create relabeled sibling datasets with Stage-1 V2.1 `/v2` annotations."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from testbed.data.hdf5_io import list_episodes, read_episode, write_v2_extension
from testbed.data.v2_1 import label_episode_v2_1


def _default_relabeled_name(dataset_name: str) -> str:
    if "v2_1" in dataset_name:
        return f"{dataset_name}_relabeled"
    return f"{dataset_name}_v2_1_relabeled"


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
        "--pause-eps",
        type=float,
        default=0.05,
        help="Pause threshold for ||action||_1 < eps (default: 0.05).",
    )
    args = parser.parse_args()

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

    labeled = 0
    for source_path in episode_paths:
        episode = read_episode(source_path)
        metadata = dict(episode.get("metadata", {}))
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
        )

        target_path = output_dir / source_path.name
        shutil.copy2(source_path, target_path)
        write_v2_extension(target_path, v2=v2_payload, metadata_updates=metadata_updates)
        labeled += 1

    print(
        f"Labeled {labeled} episode(s) from {dataset_dir} into sibling dataset {output_dir}"
    )

if __name__ == "__main__":
    main()
