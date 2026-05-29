"""tb-lidar-heightmap — convert AGX LiDAR PointCloud2 to local heightmaps."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from testbed.perception.lidar_heightmap import (
    LidarHeightmapConfig,
    points_to_heightmap,
    save_heightmap_npz,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-lidar-heightmap",
        description="Convert /lidar/pointcloud frames into local height/depth grids.",
    )
    parser.add_argument("--topic", default="/lidar/pointcloud")
    parser.add_argument("--input-npy", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("runs/lidar_heightmap"))
    parser.add_argument("--max-frames", type=int, default=1)
    parser.add_argument("--save-every", type=int, default=1)
    parser.add_argument("--resolution-m", type=float, default=0.05)
    parser.add_argument("--x-min-m", type=float, default=-5.0)
    parser.add_argument("--x-max-m", type=float, default=5.0)
    parser.add_argument("--z-min-m", type=float, default=-5.0)
    parser.add_argument("--z-max-m", type=float, default=5.0)
    parser.add_argument("--min-height-m", type=float, default=None)
    parser.add_argument("--max-height-m", type=float, default=None)
    parser.add_argument("--reference-height-m", type=float, default=None)
    parser.add_argument("--png", action="store_true", help="Also write a depth PNG preview.")
    args = parser.parse_args()

    config = LidarHeightmapConfig(
        x_min_m=args.x_min_m,
        x_max_m=args.x_max_m,
        z_min_m=args.z_min_m,
        z_max_m=args.z_max_m,
        resolution_m=args.resolution_m,
        min_height_m=args.min_height_m,
        max_height_m=args.max_height_m,
        reference_height_m=args.reference_height_m,
    )

    if args.input_npy is not None:
        _run_offline(
            input_npy=args.input_npy,
            output_dir=args.output_dir,
            config=config,
            write_png=args.png,
        )
        return

    _run_ros(
        topic=args.topic,
        output_dir=args.output_dir,
        config=config,
        max_frames=args.max_frames,
        save_every=args.save_every,
        write_png=args.png,
    )


def _run_offline(
    *,
    input_npy: Path,
    output_dir: Path,
    config: LidarHeightmapConfig,
    write_png: bool,
) -> None:
    points = np.load(input_npy)
    result = points_to_heightmap(points, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    npz_path = save_heightmap_npz(result, output_dir / "heightmap_000000.npz")
    print(f"Wrote {npz_path}")
    if write_png:
        png_path = _write_depth_png(
            result.depth_m,
            output_dir / "heightmap_000000_depth.png",
        )
        print(f"Wrote {png_path}")


def _run_ros(
    *,
    topic: str,
    output_dir: Path,
    config: LidarHeightmapConfig,
    max_frames: int,
    save_every: int,
    write_png: bool,
) -> None:
    try:
        import rclpy
        from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import PointCloud2
        from sensor_msgs_py import point_cloud2
    except ImportError as exc:
        raise SystemExit(
            "ROS 2 Python packages are required for live mode. "
            "Run: source /opt/ros/jazzy/setup.bash"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    node = rclpy.create_node("lidar_heightmap_exporter")
    qos = QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.BEST_EFFORT,
    )
    frame_counter = {"seen": 0, "saved": 0}
    done = {"value": False}

    def on_cloud(msg: PointCloud2) -> None:
        frame_counter["seen"] += 1
        if frame_counter["seen"] % max(1, save_every) != 0:
            return
        points = _pointcloud2_to_xyz(point_cloud2, msg)
        result = points_to_heightmap(points, config)
        index = frame_counter["saved"]
        npz_path = save_heightmap_npz(
            result,
            output_dir / f"heightmap_{index:06d}.npz",
        )
        print(
            f"Wrote {npz_path} "
            f"points={len(points)} valid_cells={int(result.valid_mask.sum())}"
        )
        if write_png:
            _write_depth_png(
                result.depth_m,
                output_dir / f"heightmap_{index:06d}_depth.png",
            )
        frame_counter["saved"] += 1
        if max_frames > 0 and frame_counter["saved"] >= max_frames:
            done["value"] = True

    node.create_subscription(PointCloud2, topic, on_cloud, qos)
    print(f"Listening on {topic}; output_dir={output_dir}")
    try:
        while rclpy.ok() and not done["value"]:
            rclpy.spin_once(node, timeout_sec=0.5)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def _pointcloud2_to_xyz(point_cloud2_module: object, msg: object) -> np.ndarray:
    points = point_cloud2_module.read_points(
        msg,
        field_names=("x", "y", "z"),
        skip_nans=True,
    )
    if isinstance(points, np.ndarray):
        if points.dtype.fields:
            return np.stack([points["x"], points["y"], points["z"]], axis=1).astype(
                np.float32
            )
        return np.asarray(points, dtype=np.float32).reshape(-1, 3)
    return np.asarray(list(points), dtype=np.float32).reshape(-1, 3)


def _write_depth_png(depth_m: np.ndarray, path: Path) -> Path:
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6), dpi=120)
    image = ax.imshow(depth_m, origin="lower", cmap="viridis")
    fig.colorbar(image, ax=ax, label="depth_m")
    ax.set_title("LiDAR depth grid")
    ax.set_xlabel("grid x")
    ax.set_ylabel("grid z")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


if __name__ == "__main__":
    main()
