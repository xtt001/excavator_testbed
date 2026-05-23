"""Attach V2.4.5 dig depth-profile tokens to dig primitive episodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np

from testbed.cli.audit_dig_depth_semantics import (
    DEFAULT_QC6_DIG_DATASET,
    _parse_metadata_filter_args,
    _select_episode_paths,
    compute_episode_metrics,
    summarize_metrics,
)
from testbed.data.dig_depth_profile_v2_4 import (
    DIG_DEPTH_PROFILE_CONTRACT_VERSION,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_ORDER,
    build_dig_depth_profile_token_from_metrics,
)
from testbed.data.schema import DS_ENV_STATE, DS_V2_STEP_DIG_DEPTH_PROFILE_TOKENS_V1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-dig-depth-profile-tokens-v1",
        description=(
            "Build /v2/step/dig_depth_profile_tokens_v1 for dig primitive episodes "
            "from qc6 depth-semantics metrics."
        ),
    )
    parser.add_argument(
        "--dataset-dir",
        default=DEFAULT_QC6_DIG_DATASET,
        help="Dig primitive dataset root. Defaults to the qc6 materialized dig copy.",
    )
    parser.add_argument(
        "--training-tier",
        default="gold",
        help="Metadata training_tier to select; use 'all' to disable this filter.",
    )
    parser.add_argument(
        "--surface-source",
        choices=("current_cell", "dominant_cell"),
        default="current_cell",
        help="Surface source forwarded to the depth-semantics audit.",
    )
    parser.add_argument(
        "--max-episodes",
        type=int,
        default=0,
        help="Maximum filtered episodes to update; <=0 means all matching episodes.",
    )
    parser.add_argument(
        "--metadata-filter",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Additional metadata filter. Repeats are allowed.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing dig_depth_profile_tokens_v1 dataset.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute metrics and summary without writing HDF5 files.",
    )
    parser.add_argument("--summary-output", default=None, help="Optional JSON summary path.")
    args = parser.parse_args()

    metadata_filters = _parse_metadata_filter_args(args.metadata_filter)
    if str(args.training_tier).lower() != "all":
        metadata_filters["training_tier"] = str(args.training_tier)
    dataset_dir = Path(args.dataset_dir)
    episode_paths = _select_episode_paths(
        dataset_dir=dataset_dir,
        metadata_filters=metadata_filters,
        max_episodes=int(args.max_episodes),
    )
    if not episode_paths:
        raise FileNotFoundError(
            f"No matching dig episodes found under {dataset_dir} with filters "
            f"{metadata_filters}."
        )

    records: list[dict[str, object]] = []
    token_preview: list[dict[str, object]] = []
    for index, episode_path in enumerate(episode_paths):
        print(f"[{index + 1}/{len(episode_paths)}] {episode_path.name}", flush=True)
        metrics = compute_episode_metrics(
            episode_path,
            surface_source=str(args.surface_source),
        )
        token = build_dig_depth_profile_token_from_metrics(metrics)
        records.append(metrics)
        if len(token_preview) < 8:
            token_preview.append(
                {
                    "episode_id": metrics["episode_id"],
                    "dominant_cell_id": metrics["dominant_removed_depth_cell_id"],
                    "token": token.astype(float).tolist(),
                }
            )
        if not bool(args.dry_run):
            _write_episode_token(episode_path, token=token, force=bool(args.force))

    summary = {
        "schema_version": "dig_depth_profile_token_build_v1",
        "dataset_dir": str(dataset_dir),
        "metadata_filters": metadata_filters,
        "surface_source": str(args.surface_source),
        "dry_run": bool(args.dry_run),
        "updated_count": 0 if bool(args.dry_run) else len(records),
        "record_count": len(records),
        "token_dim": int(DIG_DEPTH_PROFILE_TOKEN_DIM),
        "token_contract_version": DIG_DEPTH_PROFILE_CONTRACT_VERSION,
        "token_order": list(DIG_DEPTH_PROFILE_TOKEN_ORDER),
        "token_preview": token_preview,
        "depth_semantics_summary": summarize_metrics(records),
    }
    if args.summary_output:
        output_path = Path(args.summary_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary["depth_semantics_summary"]["headline"], indent=2, sort_keys=True))
    if args.summary_output:
        print(args.summary_output)


def _write_episode_token(
    episode_path: Path,
    *,
    token: np.ndarray,
    force: bool,
) -> None:
    with h5py.File(episode_path, "a") as handle:
        if DS_ENV_STATE not in handle:
            raise KeyError(f"{episode_path} is missing {DS_ENV_STATE}.")
        n_steps = int(handle[DS_ENV_STATE].shape[0])
        if DS_V2_STEP_DIG_DEPTH_PROFILE_TOKENS_V1 in handle:
            if not force:
                raise FileExistsError(
                    f"{episode_path} already has {DS_V2_STEP_DIG_DEPTH_PROFILE_TOKENS_V1}; "
                    "rerun with --force to overwrite."
                )
            del handle[DS_V2_STEP_DIG_DEPTH_PROFILE_TOKENS_V1]
        group = handle.require_group("v2/step")
        repeated = np.repeat(token.reshape(1, -1), n_steps, axis=0).astype(np.float32)
        group.create_dataset("dig_depth_profile_tokens_v1", data=repeated)
        meta = handle.require_group("metadata")
        meta.attrs["dig_depth_profile_token_dim"] = int(DIG_DEPTH_PROFILE_TOKEN_DIM)
        meta.attrs["dig_depth_profile_token_contract_version"] = (
            DIG_DEPTH_PROFILE_CONTRACT_VERSION
        )
        meta.attrs["dig_depth_profile_token_order"] = ",".join(
            DIG_DEPTH_PROFILE_TOKEN_ORDER
        )


if __name__ == "__main__":
    main()
