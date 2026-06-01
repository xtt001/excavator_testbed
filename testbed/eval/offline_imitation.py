"""Offline imitation evaluation for recorded demonstration streams."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.hdf5_io import list_episodes
from testbed.data.real_one_dig import EXCAVATOR_JOINT_ORDER
from testbed.data.schema import ATTR_CONTROL_HZ, DS_ACTION, DS_QPOS, DS_QVEL


@dataclass(frozen=True)
class OfflineImitationEpisodeResult:
    """Summary for one offline imitation episode."""

    episode_id: int
    episode_path: str
    steps: int
    control_hz: float
    overall_mae: float
    overall_rmse: float
    active_mae: float | None
    idle_false_motion_rate: float | None
    sign_accuracy: float | None
    overlay_video_path: str
    action_plot_path: str
    metrics_path: str
    actions_csv_path: str
    missing_diagnostics: list[str]


def load_act_policy_from_config(
    config: dict[str, Any],
    *,
    ckpt_path: str | Path | None = None,
    device: str | None = None,
    temporal_agg: bool | None = None,
):
    """Load an ACT policy using the same checkpoint convention as live eval."""

    task_cfg = config.get("task", {})
    policy_cfg = config.get("policy", {})
    train_cfg = config.get("train", {})
    eval_cfg = config.get("eval", {})
    policy_class = str(policy_cfg.get("class", policy_cfg.get("name", "ACT"))).upper()
    if policy_class != "ACT":
        raise NotImplementedError("Offline real one-dig eval currently supports ACT only.")

    explicit_ckpt = ckpt_path or eval_cfg.get("ckpt_path") or policy_cfg.get("ckpt_path")
    explicit_ckpt_dir = eval_cfg.get("ckpt_dir", train_cfg.get("ckpt_dir"))
    if explicit_ckpt:
        resolved_ckpt_path = Path(explicit_ckpt)
        ckpt_dir = Path(explicit_ckpt_dir) if explicit_ckpt_dir else resolved_ckpt_path.parent
    else:
        ckpt_dir = Path(explicit_ckpt_dir) if explicit_ckpt_dir else Path("ckpts")
        resolved_ckpt_path = ckpt_dir / "policy_best.ckpt"

    act_params = policy_cfg.get("act_params", {})
    camera_names = list(task_cfg.get("camera_names", ["fpv"]))
    low_dim_keys = list(policy_cfg.get("low_dim_keys", ["qpos", "qvel"]))
    state_dim = 4 * len(low_dim_keys)
    policy_config = {
        "lr": float(train_cfg.get("lr", 1e-5)),
        "num_queries": int(act_params.get("chunk_size", 100)),
        "kl_weight": float(act_params.get("kl_weight", 10)),
        "hidden_dim": int(act_params.get("hidden_dim", 512)),
        "dim_feedforward": int(act_params.get("dim_feedforward", 3200)),
        "lr_backbone": 1e-5,
        "backbone": "resnet18",
        "enc_layers": 4,
        "dec_layers": 7,
        "nheads": 8,
        "camera_names": camera_names,
        "equipment_model": task_cfg.get("equipment_model", "agxunity"),
        "max_episode_len": int(task_cfg.get("episode_len", 400)),
        "low_dim_keys": low_dim_keys,
        "state_dim": state_dim,
        "train_with_zero_latent": bool(act_params.get("train_with_zero_latent", False)),
    }

    from testbed.policies.act.adapter import ACTAdapter

    return ACTAdapter.from_checkpoint(
        ckpt_path=resolved_ckpt_path,
        policy_config=policy_config,
        norm_stats_path=ckpt_dir / "dataset_stats.pkl",
        temporal_agg=bool(
            policy_cfg.get("temporal_agg", False) if temporal_agg is None else temporal_agg
        ),
        device=str(policy_cfg.get("device", "cuda") if device is None else device),
    )


def run_offline_imitation_eval(
    *,
    dataset_dir: str | Path,
    output_dir: str | Path,
    policy: Any,
    episode_ids: list[int] | None = None,
    max_steps: int | None = None,
    camera_name: str = "fpv",
    action_threshold: float = 0.05,
) -> list[OfflineImitationEpisodeResult]:
    """Run a policy over recorded episodes and compare against expert actions."""

    dataset_dir = Path(dataset_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    episode_paths = _resolve_episode_paths(dataset_dir, episode_ids)
    if not episode_paths:
        raise FileNotFoundError(f"No episode_*.hdf5 files found under {dataset_dir}")

    results = [
        _evaluate_episode(
            episode_path=path,
            output_dir=output_dir,
            policy=policy,
            max_steps=max_steps,
            camera_name=camera_name,
            action_threshold=float(action_threshold),
        )
        for path in episode_paths
    ]
    _write_summary(output_dir, results)
    return results


def write_resolved_offline_eval_config(config: dict[str, Any], output_dir: str | Path) -> Path:
    """Write the resolved config used by the offline eval CLI."""

    import yaml

    path = Path(output_dir) / "offline_eval_resolved_config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _evaluate_episode(
    *,
    episode_path: Path,
    output_dir: Path,
    policy: Any,
    max_steps: int | None,
    camera_name: str,
    action_threshold: float,
) -> OfflineImitationEpisodeResult:
    episode_id = _episode_id(episode_path)
    episode = _read_episode(episode_path, camera_name=camera_name, max_steps=max_steps)
    if hasattr(policy, "reset"):
        policy.reset()

    policy_action = _predict_episode_actions(policy, episode, camera_name=camera_name)
    metrics = compute_action_metrics(
        expert_action=episode["action"],
        policy_action=policy_action,
        threshold=action_threshold,
    )
    missing_diagnostics = list(episode["missing_diagnostics"])

    actions_csv_path = output_dir / f"episode_{episode_id}_actions.csv"
    metrics_path = output_dir / f"episode_{episode_id}_metrics.json"
    action_plot_path = output_dir / f"episode_{episode_id}_actions.png"
    overlay_video_path = output_dir / f"episode_{episode_id}_overlay.mp4"

    _write_actions_csv(
        actions_csv_path,
        time_s=episode["time_s"],
        expert_action=episode["action"],
        policy_action=policy_action,
        raw_action=episode["raw_action"],
        commanded_action=episode["commanded_action"],
    )
    _write_metrics_json(
        metrics_path,
        metrics=metrics,
        episode_id=episode_id,
        episode_path=episode_path,
        missing_diagnostics=missing_diagnostics,
    )
    _write_action_plot(
        action_plot_path,
        time_s=episode["time_s"],
        expert_action=episode["action"],
        policy_action=policy_action,
        raw_action=episode["raw_action"],
        commanded_action=episode["commanded_action"],
    )
    _write_overlay_video(
        overlay_video_path,
        frames=episode["images"],
        time_s=episode["time_s"],
        expert_action=episode["action"],
        policy_action=policy_action,
        control_hz=float(episode["control_hz"]),
    )

    return OfflineImitationEpisodeResult(
        episode_id=episode_id,
        episode_path=str(episode_path),
        steps=int(episode["action"].shape[0]),
        control_hz=float(episode["control_hz"]),
        overall_mae=float(metrics["overall"]["mae"]),
        overall_rmse=float(metrics["overall"]["rmse"]),
        active_mae=metrics["overall"]["active_mae"],
        idle_false_motion_rate=metrics["overall"]["idle_false_motion_rate"],
        sign_accuracy=metrics["overall"]["sign_accuracy"],
        overlay_video_path=str(overlay_video_path),
        action_plot_path=str(action_plot_path),
        metrics_path=str(metrics_path),
        actions_csv_path=str(actions_csv_path),
        missing_diagnostics=missing_diagnostics,
    )


def compute_action_metrics(
    *,
    expert_action: np.ndarray,
    policy_action: np.ndarray,
    threshold: float = 0.05,
) -> dict[str, Any]:
    """Compute deadband-aware action imitation metrics."""

    expert = np.asarray(expert_action, dtype=np.float32)
    policy = np.asarray(policy_action, dtype=np.float32)
    if expert.shape != policy.shape:
        raise ValueError(f"expert/policy action shape mismatch: {expert.shape} != {policy.shape}")

    diff = policy - expert
    abs_diff = np.abs(diff)
    per_axis: dict[str, Any] = {}
    axis_sign_values: list[float] = []
    axis_active_mae_values: list[float] = []
    axis_idle_false_values: list[float] = []
    for axis, name in enumerate(EXCAVATOR_JOINT_ORDER[: expert.shape[1]]):
        axis_expert = expert[:, axis]
        axis_policy = policy[:, axis]
        axis_abs = abs_diff[:, axis]
        active = np.abs(axis_expert) > threshold
        idle = ~active
        active_mae = _optional_mean(axis_abs[active])
        sign_accuracy = _optional_mean(
            (np.sign(axis_policy[active]) == np.sign(axis_expert[active])).astype(np.float32)
        )
        idle_false_motion_rate = _optional_mean(
            (np.abs(axis_policy[idle]) > threshold).astype(np.float32)
        )
        if active_mae is not None:
            axis_active_mae_values.append(active_mae)
        if sign_accuracy is not None:
            axis_sign_values.append(sign_accuracy)
        if idle_false_motion_rate is not None:
            axis_idle_false_values.append(idle_false_motion_rate)
        per_axis[name] = {
            "mae": float(np.mean(axis_abs)),
            "rmse": float(np.sqrt(np.mean(np.square(diff[:, axis])))),
            "active_mae": active_mae,
            "sign_accuracy": sign_accuracy,
            "idle_false_motion_rate": idle_false_motion_rate,
            "active_steps": int(np.sum(active)),
            "idle_steps": int(np.sum(idle)),
        }

    any_active = np.any(np.abs(expert) > threshold, axis=1)
    any_idle = ~any_active
    return {
        "threshold": float(threshold),
        "overall": {
            "mae": float(np.mean(abs_diff)),
            "rmse": float(np.sqrt(np.mean(np.square(diff)))),
            "active_mae": _optional_mean(abs_diff[any_active]),
            "sign_accuracy": _optional_mean(np.asarray(axis_sign_values, dtype=np.float32)),
            "idle_false_motion_rate": _optional_mean(
                (np.any(np.abs(policy[any_idle]) > threshold, axis=1)).astype(np.float32)
            ),
            "active_axis_mae_mean": _optional_mean(np.asarray(axis_active_mae_values, dtype=np.float32)),
            "idle_axis_false_motion_rate_mean": _optional_mean(
                np.asarray(axis_idle_false_values, dtype=np.float32)
            ),
            "steps": int(expert.shape[0]),
        },
        "per_axis": per_axis,
    }


def _read_episode(
    episode_path: Path,
    *,
    camera_name: str,
    max_steps: int | None,
) -> dict[str, Any]:
    with h5py.File(episode_path, "r") as f:
        images_path = f"observations/images/{camera_name}"
        if images_path not in f:
            raise KeyError(f"Episode {episode_path} does not contain {images_path}")
        action = f[DS_ACTION][()].astype(np.float32)
        qpos = f[DS_QPOS][()].astype(np.float32)
        qvel = f[DS_QVEL][()].astype(np.float32)
        images = f[images_path][()].astype(np.uint8)
        control_hz = _read_control_hz(f)
        step_ns = f["timestamps/step_ns"][()] if "timestamps/step_ns" in f else None
        raw_action, raw_missing = _read_optional_action(f, "diagnostics/raw_action", action.shape)
        commanded_action, commanded_missing = _read_optional_action(
            f,
            "diagnostics/commanded_action",
            action.shape,
        )

    n_steps = int(action.shape[0])
    if max_steps is not None:
        n_steps = min(n_steps, int(max_steps))
    action = action[:n_steps]
    qpos = qpos[:n_steps]
    qvel = qvel[:n_steps]
    images = images[:n_steps]
    raw_action = None if raw_action is None else raw_action[:n_steps]
    commanded_action = None if commanded_action is None else commanded_action[:n_steps]
    time_s = _time_s(step_ns, n_steps=n_steps, control_hz=control_hz)
    missing_diagnostics = []
    if raw_missing:
        missing_diagnostics.append("diagnostics/raw_action")
    if commanded_missing:
        missing_diagnostics.append("diagnostics/commanded_action")
    return {
        "action": action,
        "qpos": qpos,
        "qvel": qvel,
        "images": images,
        "raw_action": raw_action,
        "commanded_action": commanded_action,
        "time_s": time_s,
        "control_hz": control_hz,
        "missing_diagnostics": missing_diagnostics,
    }


def _predict_episode_actions(
    policy: Any,
    episode: dict[str, Any],
    *,
    camera_name: str,
) -> np.ndarray:
    expert = episode["action"]
    predictions = np.zeros_like(expert, dtype=np.float32)
    for step in range(int(expert.shape[0])):
        obs = {
            "qpos": episode["qpos"][step],
            "qvel": episode["qvel"][step],
            f"image_{camera_name}": episode["images"][step],
        }
        pred = np.asarray(policy.predict(obs), dtype=np.float32).reshape(-1)
        if pred.shape[0] != expert.shape[1]:
            raise ValueError(
                f"Policy action dim {pred.shape[0]} does not match expert dim {expert.shape[1]}"
            )
        predictions[step] = pred
    return predictions


def _write_actions_csv(
    path: Path,
    *,
    time_s: np.ndarray,
    expert_action: np.ndarray,
    policy_action: np.ndarray,
    raw_action: np.ndarray | None,
    commanded_action: np.ndarray | None,
) -> None:
    axes = EXCAVATOR_JOINT_ORDER[: expert_action.shape[1]]
    fieldnames = ["step", "time_s"]
    for prefix in ("expert", "policy", "raw", "commanded"):
        fieldnames.extend(f"{prefix}_{axis}" for axis in axes)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for step in range(int(expert_action.shape[0])):
            row: dict[str, Any] = {"step": step, "time_s": f"{float(time_s[step]):.6f}"}
            for axis_idx, axis in enumerate(axes):
                row[f"expert_{axis}"] = f"{float(expert_action[step, axis_idx]):.8g}"
                row[f"policy_{axis}"] = f"{float(policy_action[step, axis_idx]):.8g}"
                row[f"raw_{axis}"] = (
                    "" if raw_action is None else f"{float(raw_action[step, axis_idx]):.8g}"
                )
                row[f"commanded_{axis}"] = (
                    ""
                    if commanded_action is None
                    else f"{float(commanded_action[step, axis_idx]):.8g}"
                )
            writer.writerow(row)


def _write_metrics_json(
    path: Path,
    *,
    metrics: dict[str, Any],
    episode_id: int,
    episode_path: Path,
    missing_diagnostics: list[str],
) -> None:
    payload = {
        "episode_id": int(episode_id),
        "episode_path": str(episode_path),
        "missing_diagnostics": list(missing_diagnostics),
        "metrics": metrics,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_action_plot(
    path: Path,
    *,
    time_s: np.ndarray,
    expert_action: np.ndarray,
    policy_action: np.ndarray,
    raw_action: np.ndarray | None,
    commanded_action: np.ndarray | None,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    axes_names = EXCAVATOR_JOINT_ORDER[: expert_action.shape[1]]
    fig, axs = plt.subplots(len(axes_names), 1, figsize=(12, 8), sharex=True)
    axs = np.atleast_1d(axs)
    for axis_idx, axis_name in enumerate(axes_names):
        ax = axs[axis_idx]
        ax.plot(time_s, expert_action[:, axis_idx], label="expert", linewidth=1.5)
        ax.plot(time_s, policy_action[:, axis_idx], label="policy", linewidth=1.2)
        if raw_action is not None:
            ax.plot(time_s, raw_action[:, axis_idx], label="raw", alpha=0.35, linewidth=0.9)
        if commanded_action is not None:
            ax.plot(
                time_s,
                commanded_action[:, axis_idx],
                label="commanded",
                alpha=0.35,
                linewidth=0.9,
            )
        ax.set_ylabel(axis_name)
        ax.grid(True, alpha=0.25)
        ax.set_ylim(-1.1, 1.1)
    axs[-1].set_xlabel("time (s)")
    axs[0].legend(loc="upper right", ncol=4)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _write_overlay_video(
    path: Path,
    *,
    frames: np.ndarray,
    time_s: np.ndarray,
    expert_action: np.ndarray,
    policy_action: np.ndarray,
    control_hz: float,
) -> None:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = frames.shape[1:3]
    panel_h = 170
    fps = max(1, int(round(control_hz)))
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (w, h + panel_h),
    )
    for step, frame in enumerate(frames):
        writer.write(
            _render_overlay_frame(
                frame,
                time_s=float(time_s[step]),
                step=step,
                expert=expert_action[step],
                policy=policy_action[step],
                panel_h=panel_h,
            )
        )
    writer.release()


def _render_overlay_frame(
    frame_rgb: np.ndarray,
    *,
    time_s: float,
    step: int,
    expert: np.ndarray,
    policy: np.ndarray,
    panel_h: int,
) -> np.ndarray:
    import cv2

    frame_bgr = cv2.cvtColor(np.asarray(frame_rgb, dtype=np.uint8), cv2.COLOR_RGB2BGR)
    h, w = frame_bgr.shape[:2]
    panel = np.full((panel_h, w, 3), 245, dtype=np.uint8)
    cv2.putText(
        panel,
        f"step={step}  t={time_s:.2f}s",
        (12, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (30, 30, 30),
        1,
        cv2.LINE_AA,
    )
    center_x = int(w * 0.55)
    max_bar = max(50, int(w * 0.32))
    for axis_idx, axis_name in enumerate(EXCAVATOR_JOINT_ORDER[: expert.shape[0]]):
        y = 50 + axis_idx * 28
        cv2.putText(
            panel,
            axis_name,
            (12, y + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (40, 40, 40),
            1,
            cv2.LINE_AA,
        )
        cv2.line(panel, (center_x - max_bar, y), (center_x + max_bar, y), (190, 190, 190), 1)
        cv2.line(panel, (center_x, y - 8), (center_x, y + 8), (120, 120, 120), 1)
        _draw_action_bar(panel, center_x, y - 6, max_bar, float(expert[axis_idx]), (230, 120, 20))
        _draw_action_bar(panel, center_x, y + 6, max_bar, float(policy[axis_idx]), (40, 150, 60))
        cv2.putText(
            panel,
            f"E {float(expert[axis_idx]):+.2f}  P {float(policy[axis_idx]):+.2f}",
            (max(12, w - 170), y + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (35, 35, 35),
            1,
            cv2.LINE_AA,
        )
    return np.concatenate([frame_bgr, panel], axis=0)


def _draw_action_bar(
    image: np.ndarray,
    center_x: int,
    y: int,
    max_bar: int,
    value: float,
    color: tuple[int, int, int],
) -> None:
    import cv2

    length = int(np.clip(value, -1.0, 1.0) * max_bar)
    if length >= 0:
        cv2.rectangle(image, (center_x, y - 4), (center_x + length, y + 4), color, -1)
    else:
        cv2.rectangle(image, (center_x + length, y - 4), (center_x, y + 4), color, -1)


def _write_summary(output_dir: Path, results: list[OfflineImitationEpisodeResult]) -> None:
    summary_json = output_dir / "summary.json"
    summary_csv = output_dir / "summary.csv"
    payload = {
        "n_episodes": len(results),
        "results": [asdict(result) for result in results],
    }
    summary_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if not results:
        return
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        fieldnames = list(asdict(results[0]).keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = asdict(result)
            row["missing_diagnostics"] = ",".join(result.missing_diagnostics)
            writer.writerow(row)


def _resolve_episode_paths(dataset_dir: Path, episode_ids: list[int] | None) -> list[Path]:
    if episode_ids is None:
        return list_episodes(dataset_dir)
    paths = []
    for episode_id in episode_ids:
        path = dataset_dir / f"episode_{int(episode_id)}.hdf5"
        if not path.exists():
            raise FileNotFoundError(f"Missing episode: {path}")
        paths.append(path)
    return paths


def _read_optional_action(
    f: h5py.File,
    path: str,
    expected_shape: tuple[int, int],
) -> tuple[np.ndarray | None, bool]:
    if path not in f:
        return None, True
    data = f[path][()].astype(np.float32)
    if data.shape[:2] != expected_shape[:2]:
        return None, True
    return data, False


def _read_control_hz(f: h5py.File) -> float:
    if "metadata" in f and ATTR_CONTROL_HZ in f["metadata"].attrs:
        return float(f["metadata"].attrs[ATTR_CONTROL_HZ])
    if ATTR_CONTROL_HZ in f.attrs:
        return float(f.attrs[ATTR_CONTROL_HZ])
    return 50.0


def _time_s(step_ns: np.ndarray | None, *, n_steps: int, control_hz: float) -> np.ndarray:
    if step_ns is not None and len(step_ns) >= n_steps:
        selected = np.asarray(step_ns[:n_steps], dtype=np.float64)
        return ((selected - selected[0]) / 1_000_000_000.0).astype(np.float32)
    hz = float(control_hz)
    if hz <= 0.0:
        hz = 50.0
    return (np.arange(n_steps, dtype=np.float32) / hz).astype(np.float32)


def _optional_mean(values: np.ndarray) -> float | None:
    if values.size == 0:
        return None
    return float(np.mean(values))


def _episode_id(path: Path) -> int:
    return int(path.stem.split("_", 1)[1])
