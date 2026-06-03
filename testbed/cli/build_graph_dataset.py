"""Attach depth-derived graph observations to existing teleop episodes.

Reads a teleop dataset directory (containing episode_*.hdf5 with no graph
group) plus a YAML "snapshot map" pairing episode index → depth snapshot
sequence. For each episode, builds graph tensors from saved depth frames,
aligns them onto the episode's T teleop timesteps, then writes a new HDF5 copy
to --output-dir with /observations/graph populated.

The original teleop directory is never modified. Old training configs that
do not consume /observations/graph continue to work against either dataset.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.hdf5_io import list_episodes, read_episode, write_episode
from testbed.cli.graph_session_paths import (
    graph_dataset_dir_for_session,
    snapshot_map_for_session,
    teleop_dir_for_session,
)
from testbed.perception.depth_graph import (
    DepthCameraIntrinsics,
    DepthGraphConfig,
    DepthGraphResult,
    depth_frame_to_graph,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-graph-dataset",
        description="Attach depth-derived graph observations to copied teleop HDF5 episodes.",
    )
    parser.add_argument(
        "--graph-session",
        default=None,
        help="Convenience session id. Defaults teleop-dir, snapshot-map, output-dir, and time alignment.",
    )
    parser.add_argument("--teleop-dir", type=Path, default=None)
    parser.add_argument("--snapshot-map", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--max-nodes", type=int, default=256)
    parser.add_argument("--max-edges", type=int, default=1024)
    parser.add_argument("--knn-k", type=int, default=4)
    parser.add_argument("--gradient-node-ratio", type=float, default=0.7)
    parser.add_argument("--roi-u-min", type=float, default=None)
    parser.add_argument("--roi-u-max", type=float, default=None)
    parser.add_argument("--roi-v-min", type=float, default=None)
    parser.add_argument("--roi-v-max", type=float, default=None)
    parser.add_argument("--min-depth", type=float, default=None)
    parser.add_argument("--max-depth", type=float, default=None)
    parser.add_argument(
        "--graph-every-step",
        action="store_true",
        help="Use all provided snapshots as graph keyframes; intended for one depth frame per teleop step.",
    )
    parser.add_argument(
        "--graph-stride",
        type=int,
        default=None,
        help="Use snapshots whose step_id is divisible by this stride, then forward-fill to all T steps.",
    )
    parser.add_argument(
        "--graph-rate-hz",
        type=float,
        default=None,
        help="Convert a target graph rate into a stride using --control-hz or episode metadata.",
    )
    parser.add_argument(
        "--control-hz",
        type=float,
        default=None,
        help="Control frequency used with --graph-rate-hz. Defaults to episode metadata control_hz.",
    )
    parser.add_argument(
        "--align-mode",
        choices=["previous", "nearest"],
        default="previous",
        help="How each teleop timestep selects a graph keyframe.",
    )
    parser.add_argument(
        "--align-domain",
        choices=["auto", "step", "time"],
        default="auto",
        help="Use step_id or timestamp_ns for graph alignment. auto uses time when available.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    graph_session = str(args.graph_session).strip() if args.graph_session else ""
    if graph_session:
        if args.teleop_dir is None:
            args.teleop_dir = teleop_dir_for_session(graph_session)
        if args.snapshot_map is None:
            args.snapshot_map = snapshot_map_for_session(graph_session)
        if args.output_dir is None:
            args.output_dir = graph_dataset_dir_for_session(graph_session)
        if args.align_domain == "auto":
            args.align_domain = "time"
    if args.teleop_dir is None:
        raise SystemExit("--teleop-dir is required unless --graph-session is provided.")
    if args.snapshot_map is None:
        raise SystemExit("--snapshot-map is required unless --graph-session is provided.")
    if args.output_dir is None:
        raise SystemExit("--output-dir is required unless --graph-session is provided.")

    try:
        _run(args)
    except Exception as exc:
        print(f"tb-build-graph-dataset: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _run(args: argparse.Namespace) -> None:
    teleop_dir = args.teleop_dir
    snapshot_map = args.snapshot_map
    output_dir = args.output_dir

    if teleop_dir.resolve() == output_dir.resolve():
        raise ValueError("--output-dir must be different from --teleop-dir.")
    if not teleop_dir.is_dir():
        raise FileNotFoundError(f"teleop directory not found: {teleop_dir}")
    if not snapshot_map.is_file():
        raise FileNotFoundError(f"snapshot map not found: {snapshot_map}")
    if not args.dry_run and any(output_dir.glob("episode_*.hdf5")):
        raise FileExistsError(
            f"--output-dir already contains episode_*.hdf5: {output_dir}"
        )

    entries, snapshot_root = _load_snapshot_map(snapshot_map)
    episode_paths = { _episode_index(path): path for path in list_episodes(teleop_dir) }
    mapped_indices = {entry["episode_index"] for entry in entries}
    skipped_count = 0
    for index in sorted(set(episode_paths) - mapped_indices):
        print(
            f"warning: episode_{index:06d}.hdf5 has no snapshot map entry; skipping",
            file=sys.stderr,
        )
        skipped_count += 1

    processed_count = 0
    for entry in entries:
        episode_index = int(entry["episode_index"])
        src = episode_paths.get(episode_index)
        if src is None or not src.is_file():
            raise FileNotFoundError(
                "snapshot map references missing teleop episode: "
                f"episode_{episode_index:06d}.hdf5 or episode_{episode_index}.hdf5"
            )

        ep = read_episode(src, load_images=True)
        t_steps = int(ep["qpos"].shape[0])
        snapshots = _resolve_episode_snapshots(
            entry,
            snapshot_root=snapshot_root,
            snapshot_map=snapshot_map,
        )
        graph_keyframes = [
            _build_graph_from_snapshot(
                item["path"],
                args,
                step_id=item["step_id"],
                timestamp_ns=item.get("timestamp_ns"),
            )
            for item in snapshots
        ]
        align_domain = _resolve_align_domain(graph_keyframes, ep, str(args.align_domain))
        selected_keyframes = _select_graph_keyframes(graph_keyframes, ep, args, align_domain)
        observation_graph = _align_graphs_to_episode(
            selected_keyframes,
            ep,
            align_mode=str(args.align_mode),
            align_domain=align_domain,
        )
        dst = output_dir / src.name

        summary: dict[str, object] = {
            "episode_index": episode_index,
            "src": str(src),
            "T": t_steps,
            "node_count": int(selected_keyframes[0]["graph"].node_mask.sum()),
            "edge_count": int(selected_keyframes[0]["graph"].edge_mask.sum()),
            "intrinsics_used": all(bool(item["intrinsics_used"]) for item in selected_keyframes),
            "snapshot_count": len(snapshots),
            "graph_keyframe_count": len(selected_keyframes),
            "fresh_count": int(observation_graph["is_fresh"].sum()),
            "align_domain": align_domain,
        }

        if args.dry_run:
            summary["dry_run"] = True
        else:
            _write_with_passthrough(dst, ep, observation_graph)
            summary["dst"] = str(dst)

        print(json.dumps(summary, sort_keys=True))
        processed_count += 1

    print(
        json.dumps(
            {
                "aggregate": True,
                "episodes_processed": processed_count,
                "episodes_skipped": skipped_count,
            },
            sort_keys=True,
        )
    )


def _load_snapshot_map(path: Path) -> tuple[list[dict[str, Any]], Path | None]:
    payload = _load_yaml_subset(path.read_text()) or {}
    if not isinstance(payload, dict):
        raise ValueError("snapshot map must be a YAML mapping.")

    defaults = payload.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise ValueError("snapshot map defaults must be a mapping.")
    snapshot_root_raw = defaults.get("snapshot_root")
    snapshot_root = Path(snapshot_root_raw) if snapshot_root_raw else None

    raw_entries = payload.get("episodes") or []
    if not isinstance(raw_entries, list):
        raise ValueError("snapshot map episodes must be a list.")

    entries: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise ValueError("each snapshot map episode entry must be a mapping.")
        if "episode_index" not in raw_entry:
            raise ValueError("each episode entry must contain episode_index.")
        if "snapshot" not in raw_entry and "snapshots" not in raw_entry:
            raise ValueError("each episode entry must contain snapshot or snapshots.")
        episode_index = int(raw_entry["episode_index"])
        if episode_index in seen:
            raise ValueError(f"duplicate episode_index in snapshot map: {episode_index}")
        seen.add(episode_index)
        entries.append(
            {
                "episode_index": episode_index,
                **({"snapshot": str(raw_entry["snapshot"])} if "snapshot" in raw_entry else {}),
                **({"snapshots": raw_entry["snapshots"]} if "snapshots" in raw_entry else {}),
            }
        )

    return entries, snapshot_root


def _load_yaml_subset(text: str) -> dict[str, Any]:
    try:
        import yaml

        payload = yaml.safe_load(text)
        return payload if payload is not None else {}
    except ModuleNotFoundError:
        return _parse_snapshot_map_subset(text)


def _parse_snapshot_map_subset(text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    defaults: dict[str, str] = {}
    episodes: list[dict[str, Any]] = []
    current_section: str | None = None
    current_episode: dict[str, Any] | None = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped == "defaults:":
            current_section = "defaults"
            continue
        if stripped == "episodes:":
            current_section = "episodes"
            continue
        if current_section == "defaults" and line.startswith("  "):
            key, value = _parse_key_value(stripped)
            defaults[key] = value
            continue
        if current_section == "episodes" and line.startswith("  - "):
            if current_episode is not None:
                episodes.append(current_episode)
            current_episode = {}
            key, value = _parse_key_value(stripped[2:].strip())
            current_episode[key] = int(value) if key == "episode_index" else value
            continue
        if current_section == "episodes" and line.startswith("    "):
            if current_episode is None:
                raise ValueError("snapshot map episode field appears before an episode item.")
            key, value = _parse_key_value(stripped)
            current_episode[key] = int(value) if key == "episode_index" else value
            continue
        raise ValueError(f"unsupported snapshot map YAML line: {raw_line!r}")

    if current_episode is not None:
        episodes.append(current_episode)
    if defaults:
        payload["defaults"] = defaults
    payload["episodes"] = episodes
    return payload


def _parse_key_value(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise ValueError(f"expected key: value YAML line, got: {line!r}")
    key, value = line.split(":", 1)
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    return key.strip(), value


def _resolve_episode_snapshots(
    entry: dict[str, Any],
    *,
    snapshot_root: Path | None,
    snapshot_map: Path,
) -> list[dict[str, Any]]:
    if "snapshots" in entry:
        raw_snapshots = entry["snapshots"]
        if not isinstance(raw_snapshots, list) or not raw_snapshots:
            raise ValueError("episode snapshots must be a non-empty list.")
        snapshots = []
        seen_steps: set[int] = set()
        for raw_item in raw_snapshots:
            if not isinstance(raw_item, dict):
                raise ValueError("each snapshot entry must be a mapping.")
            if "step_id" not in raw_item or "snapshot" not in raw_item:
                raise ValueError("each snapshot entry must contain step_id and snapshot.")
            step_id = int(raw_item["step_id"])
            if step_id in seen_steps:
                raise ValueError(f"duplicate snapshot step_id: {step_id}")
            seen_steps.add(step_id)
            snapshots.append(
                {
                    "step_id": step_id,
                    **(
                        {"timestamp_ns": int(raw_item["timestamp_ns"])}
                        if "timestamp_ns" in raw_item
                        else {}
                    ),
                    "path": _resolve_snapshot_path(
                        str(raw_item["snapshot"]),
                        snapshot_root=snapshot_root,
                        snapshot_map=snapshot_map,
                    ),
                }
            )
        return sorted(snapshots, key=lambda item: int(item["step_id"]))

    return [
        {
            "step_id": 0,
            "path": _resolve_snapshot_path(
                str(entry["snapshot"]),
                snapshot_root=snapshot_root,
                snapshot_map=snapshot_map,
            ),
        }
    ]


def _resolve_snapshot_path(
    snapshot: str,
    *,
    snapshot_root: Path | None,
    snapshot_map: Path,
) -> Path:
    snapshot_path = Path(snapshot)
    if snapshot_path.is_absolute():
        resolved = snapshot_path
    elif snapshot_root is not None:
        root = snapshot_root
        if not root.is_absolute():
            root = snapshot_map.parent / root
        resolved = root / snapshot_path
    else:
        resolved = snapshot_map.parent / snapshot_path
    if not resolved.is_file():
        raise FileNotFoundError(f"snapshot JSON not found: {resolved}")
    return resolved


def _build_graph_from_snapshot(
    snapshot_path: Path,
    args: argparse.Namespace,
    *,
    step_id: int,
    timestamp_ns: int | None,
) -> dict[str, Any]:
    snapshot = json.loads(snapshot_path.read_text())
    meta = snapshot.get("metadata") or {}
    width = int(meta.get("width", 0))
    height = int(meta.get("height", 0))
    depth_values = snapshot.get("depth_m")
    if width <= 0 or height <= 0:
        raise ValueError(f"snapshot metadata must contain positive width/height: {snapshot_path}")
    if not isinstance(depth_values, list) or len(depth_values) != width * height:
        raise ValueError(f"snapshot depth_m length does not match width*height: {snapshot_path}")

    depth = np.asarray(depth_values, dtype=np.float32).reshape(height, width)
    config = DepthGraphConfig(
        max_nodes=int(args.max_nodes),
        knn_k=int(args.knn_k),
        max_edges=int(args.max_edges),
        gradient_node_ratio=float(args.gradient_node_ratio),
        min_depth_m=(
            float(args.min_depth)
            if args.min_depth is not None
            else float(meta.get("near_m", 0.001))
        ),
        max_depth_m=(
            float(args.max_depth)
            if args.max_depth is not None
            else float(meta["far_m"]) if "far_m" in meta else None
        ),
        roi_u_min=args.roi_u_min,
        roi_u_max=args.roi_u_max,
        roi_v_min=args.roi_v_min,
        roi_v_max=args.roi_v_max,
    )
    intrinsics = DepthCameraIntrinsics.from_metadata(meta)
    graph = depth_frame_to_graph(depth, config, intrinsics)
    return {
        "step_id": int(step_id),
        "timestamp_ns": None if timestamp_ns is None else int(timestamp_ns),
        "path": snapshot_path,
        "graph": graph,
        "intrinsics_used": intrinsics is not None,
    }


def _select_graph_keyframes(
    keyframes: list[dict[str, Any]],
    ep: dict[str, Any],
    args: argparse.Namespace,
    align_domain: str,
) -> list[dict[str, Any]]:
    if not keyframes:
        raise ValueError("at least one snapshot is required per mapped episode.")

    if align_domain == "time":
        return _select_time_keyframes(keyframes, ep, args)

    stride = _resolve_graph_stride(ep, args)
    if stride is None:
        return keyframes

    selected = [
        item for item in keyframes
        if int(item["step_id"]) % stride == 0
    ]
    if not selected:
        selected = [keyframes[0]]
    return selected


def _select_time_keyframes(
    keyframes: list[dict[str, Any]],
    ep: dict[str, Any],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    if args.graph_rate_hz is None:
        return keyframes

    graph_rate_hz = float(args.graph_rate_hz)
    if graph_rate_hz <= 0.0:
        raise ValueError("--graph-rate-hz must be positive.")

    interval_ns = int(round(1_000_000_000 / graph_rate_hz))
    selected = []
    last_time_ns: int | None = None
    for item in keyframes:
        timestamp_ns = item.get("timestamp_ns")
        if timestamp_ns is None:
            continue
        timestamp_ns = int(timestamp_ns)
        if last_time_ns is None or timestamp_ns - last_time_ns >= interval_ns:
            selected.append(item)
            last_time_ns = timestamp_ns
    return selected or [keyframes[0]]


def _resolve_graph_stride(
    ep: dict[str, Any],
    args: argparse.Namespace,
) -> int | None:
    if bool(args.graph_every_step):
        return 1
    if args.graph_stride is not None:
        stride = int(args.graph_stride)
        if stride <= 0:
            raise ValueError("--graph-stride must be positive.")
        return stride
    if args.graph_rate_hz is not None:
        graph_rate_hz = float(args.graph_rate_hz)
        if graph_rate_hz <= 0.0:
            raise ValueError("--graph-rate-hz must be positive.")
        control_hz = args.control_hz
        if control_hz is None:
            control_hz = ep.get("metadata", {}).get("control_hz")
        if control_hz is None:
            raise ValueError("--graph-rate-hz requires --control-hz or episode metadata control_hz.")
        stride = int(round(float(control_hz) / graph_rate_hz))
        return max(1, stride)
    return None


def _resolve_align_domain(
    keyframes: list[dict[str, Any]],
    ep: dict[str, Any],
    requested: str,
) -> str:
    if requested == "step":
        return "step"

    has_snapshot_times = all(item.get("timestamp_ns") is not None for item in keyframes)
    step_ns = ep.get("step_ns")
    has_episode_times = step_ns is not None and len(step_ns) > 0
    if requested == "time":
        if not has_snapshot_times:
            raise ValueError("--align-domain time requires timestamp_ns for every snapshot.")
        if not has_episode_times:
            raise ValueError("--align-domain time requires HDF5 timestamps/step_ns.")
        return "time"

    return "time" if has_snapshot_times and has_episode_times else "step"


def _align_graphs_to_episode(
    keyframes: list[dict[str, Any]],
    ep: dict[str, Any],
    *,
    align_mode: str,
    align_domain: str,
) -> dict[str, np.ndarray]:
    first_graph = keyframes[0]["graph"]
    t_steps = int(ep["qpos"].shape[0])
    payload = {
        "node_features": np.zeros((t_steps, *first_graph.node_features.shape), dtype=np.float32),
        "node_mask": np.zeros((t_steps, *first_graph.node_mask.shape), dtype=np.uint8),
        "edge_indices": np.zeros((t_steps, *first_graph.edge_indices.shape), dtype=np.int64),
        "edge_features": np.zeros((t_steps, *first_graph.edge_features.shape), dtype=np.float32),
        "edge_mask": np.zeros((t_steps, *first_graph.edge_mask.shape), dtype=np.uint8),
        "graph_globals": np.zeros((t_steps, *first_graph.graph_globals.shape), dtype=np.float32),
        "source_step_id": np.zeros((t_steps,), dtype=np.int64),
        "source_time_ns": np.full((t_steps,), -1, dtype=np.int64),
        "alignment_delta_ns": np.full((t_steps,), 0, dtype=np.int64),
        "is_fresh": np.zeros((t_steps,), dtype=np.uint8),
    }
    step_ns = ep.get("step_ns")
    previous_keyframe_index = -1

    for step in range(t_steps):
        if align_domain == "time":
            if step_ns is None:
                raise ValueError("time alignment requires HDF5 step_ns.")
            target_time_ns = int(step_ns[step])
            keyframe, keyframe_index = _select_keyframe_for_time(
                keyframes,
                target_time_ns,
                align_mode=align_mode,
            )
        else:
            keyframe, keyframe_index = _select_keyframe_for_step(
                keyframes,
                step,
                align_mode=align_mode,
            )
            target_time_ns = None
        graph = keyframe["graph"]
        payload["node_features"][step] = graph.node_features
        payload["node_mask"][step] = graph.node_mask
        payload["edge_indices"][step] = graph.edge_indices
        payload["edge_features"][step] = graph.edge_features
        payload["edge_mask"][step] = graph.edge_mask
        payload["graph_globals"][step] = graph.graph_globals
        payload["source_step_id"][step] = int(keyframe["step_id"])
        if keyframe.get("timestamp_ns") is not None:
            source_time_ns = int(keyframe["timestamp_ns"])
            payload["source_time_ns"][step] = source_time_ns
            if target_time_ns is not None:
                payload["alignment_delta_ns"][step] = int(target_time_ns - source_time_ns)
        payload["is_fresh"][step] = 1 if keyframe_index != previous_keyframe_index else 0
        previous_keyframe_index = keyframe_index

    return payload


def _select_keyframe_for_step(
    keyframes: list[dict[str, Any]],
    step: int,
    *,
    align_mode: str,
) -> tuple[dict[str, Any], int]:
    if align_mode == "nearest":
        index, item = min(
            enumerate(keyframes),
            key=lambda pair: (abs(int(pair[1]["step_id"]) - step), int(pair[1]["step_id"])),
        )
        return item, index

    previous = [
        (index, item)
        for index, item in enumerate(keyframes)
        if int(item["step_id"]) <= step
    ]
    index, item = previous[-1] if previous else (0, keyframes[0])
    return item, index


def _select_keyframe_for_time(
    keyframes: list[dict[str, Any]],
    target_time_ns: int,
    *,
    align_mode: str,
) -> tuple[dict[str, Any], int]:
    if align_mode == "nearest":
        index, item = min(
            enumerate(keyframes),
            key=lambda pair: (
                abs(int(pair[1]["timestamp_ns"]) - target_time_ns),
                int(pair[1]["timestamp_ns"]),
            ),
        )
        return item, index

    previous = [
        (index, item)
        for index, item in enumerate(keyframes)
        if int(item["timestamp_ns"]) <= target_time_ns
    ]
    index, item = previous[-1] if previous else (0, keyframes[0])
    return item, index


def _write_with_passthrough(
    dst: Path,
    ep: dict[str, Any],
    observation_graph: dict[str, np.ndarray],
) -> None:
    write_episode(
        dst,
        qpos=ep["qpos"],
        qvel=ep["qvel"],
        actions=ep["actions"],
        images=ep["images"],
        rewards=ep["rewards"],
        metadata=ep["metadata"],
        env_state=ep["env_state"],
        step_ids=ep["step_ids"],
        step_ns=ep["step_ns"],
        action_src_types=ep["action_src_types"],
        action_src_ids=ep["action_src_ids"],
        observation_graph=observation_graph,
        v2=ep["v2"],
    )


def _episode_index(path: Path) -> int:
    return int(path.stem.split("_", 1)[1])


if __name__ == "__main__":
    main()
