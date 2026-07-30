"""Export short videos and summaries around primitive split boundaries."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_OFFTARGET_DEPOSITED_MASS_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)

DEFAULT_CAMERA = "fpv"
CONTACT_SHEET_OFFSETS = (-80, -40, -10, 0, 10, 40, 80)
CONTACT_SHEET_FRAME_WIDTH = 220
CONTACT_SHEET_METRIC_PRE_STEPS = 120
CONTACT_SHEET_METRIC_POST_STEPS = 120
CONTACT_SHEET_CLEAN_GOLD_MAX_RECORDS = 24
DUMP_START_OUTSIDE_RISK_THRESHOLD_M = 0.30


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-audit-primitive-boundaries",
        description=(
            "Audit primitive split boundaries by exporting short source-video "
            "windows around manifest start/end steps."
        ),
    )
    parser.add_argument(
        "--primitive-root",
        type=Path,
        required=True,
        help="Primitive dataset root containing window_manifest.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Audit output directory. Defaults to <primitive-root>/boundary_audit.",
    )
    parser.add_argument(
        "--camera",
        type=str,
        default=DEFAULT_CAMERA,
        help=f"Camera dataset to export. Default: {DEFAULT_CAMERA}.",
    )
    parser.add_argument(
        "--pre-steps",
        type=int,
        default=100,
        help="Steps before each boundary in exported videos.",
    )
    parser.add_argument(
        "--post-steps",
        type=int,
        default=100,
        help="Steps after each boundary in exported videos.",
    )
    parser.add_argument(
        "--max-videos",
        type=int,
        default=24,
        help="Maximum number of boundary videos to export.",
    )
    parser.add_argument(
        "--boundary",
        choices=("end", "start", "both"),
        default="end",
        help="Which boundary of each primitive window to audit.",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=None,
        help="Video FPS. Defaults to source control_hz or 50.",
    )
    parser.add_argument(
        "--sample",
        choices=("top-risk", "balanced"),
        default="top-risk",
        help="Video sample strategy after scoring all manifest rows.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir or (args.primitive_root / "boundary_audit")
    result = audit_primitive_boundaries(
        primitive_root=args.primitive_root,
        output_dir=output_dir,
        camera=args.camera,
        pre_steps=int(args.pre_steps),
        post_steps=int(args.post_steps),
        max_videos=int(args.max_videos),
        boundary=args.boundary,
        fps=args.fps,
        sample=args.sample,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


def audit_primitive_boundaries(
    *,
    primitive_root: Path,
    output_dir: Path,
    camera: str,
    pre_steps: int,
    post_steps: int,
    max_videos: int,
    boundary: str,
    fps: int | None,
    sample: str,
) -> dict[str, Any]:
    primitive_root = Path(primitive_root)
    output_dir = Path(output_dir)
    manifest_path = primitive_root / "window_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)

    with open(manifest_path) as f:
        manifest = json.load(f)
    if not isinstance(manifest, list):
        raise ValueError(f"{manifest_path} must contain a list of primitive windows.")

    records = _build_audit_records(manifest=manifest, boundary=boundary)
    selected = _select_video_records(records, max_videos=max_videos, sample=sample)

    output_dir.mkdir(parents=True, exist_ok=True)
    videos_dir = output_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    for rank, record in enumerate(selected):
        try:
            video_path = videos_dir / _video_name(rank, record)
            _export_boundary_video(
                record=record,
                output_path=video_path,
                camera=camera,
                pre_steps=pre_steps,
                post_steps=post_steps,
                fps=fps,
            )
            record["video_path"] = str(video_path)
            record["video_export_status"] = "ok"
        except Exception as exc:  # pragma: no cover - best-effort audit artifact.
            record["video_path"] = ""
            record["video_export_status"] = f"failed:{type(exc).__name__}:{exc}"

    selected_contact_sheet = _safe_write_contact_sheet_report(
        records=selected,
        output_dir=output_dir / "contact_sheets",
        camera=camera,
        title="Selected Boundary Keyframes",
        metric_pre_steps=max(int(pre_steps), CONTACT_SHEET_METRIC_PRE_STEPS),
        metric_post_steps=max(int(post_steps), CONTACT_SHEET_METRIC_POST_STEPS),
    )
    clean_contact_sheet = _safe_write_contact_sheet_report(
        records=_select_clean_gold_records(records, max_records=CONTACT_SHEET_CLEAN_GOLD_MAX_RECORDS),
        output_dir=output_dir / "contact_sheets_clean_gold",
        camera=camera,
        title="Clean Gold Boundary Keyframes",
        metric_pre_steps=max(int(pre_steps), CONTACT_SHEET_METRIC_PRE_STEPS),
        metric_post_steps=max(int(post_steps), CONTACT_SHEET_METRIC_POST_STEPS),
    )

    csv_path = output_dir / "boundary_audit.csv"
    _write_csv(csv_path, records)

    selected_json_path = output_dir / "selected_boundary_videos.json"
    with open(selected_json_path, "w") as f:
        json.dump(_jsonable(selected), f, indent=2, sort_keys=True)

    summary = _summary(
        records=records,
        selected=selected,
        primitive_root=primitive_root,
        output_dir=output_dir,
        camera=camera,
        pre_steps=pre_steps,
        post_steps=post_steps,
        boundary=boundary,
        sample=sample,
        selected_contact_sheet=selected_contact_sheet,
        clean_contact_sheet=clean_contact_sheet,
    )
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(_jsonable(summary), f, indent=2, sort_keys=True)
    return summary


def _build_audit_records(*, manifest: list[dict[str, Any]], boundary: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in manifest:
        boundary_names = ["end"] if boundary == "end" else ["start"] if boundary == "start" else ["start", "end"]
        for boundary_name in boundary_names:
            records.append(_audit_record(entry, boundary_name=boundary_name))
    records.sort(key=lambda item: (-float(item["risk_score"]), str(item["primitive_name"]), int(item["primitive_episode_id"])))
    return records


def _audit_record(entry: dict[str, Any], *, boundary_name: str) -> dict[str, Any]:
    primitive = str(entry.get("primitive_name", "unknown"))
    start = _as_int(entry.get("source_start_step"), 0)
    end = _as_int(entry.get("source_end_step_exclusive"), start)
    boundary_step = start if boundary_name == "start" else end
    risk_flags, risk_score = _risk(entry=entry, primitive=primitive, boundary_name=boundary_name)
    return {
        "primitive_name": primitive,
        "primitive_episode_id": _as_int(entry.get("primitive_episode_id"), -1),
        "primitive_window": str(entry.get("primitive_window", "")),
        "boundary": boundary_name,
        "boundary_step": int(boundary_step),
        "source_episode_path": str(entry.get("source_episode_path", "")),
        "source_episode_id": str(entry.get("source_episode_id", "")),
        "source_cycle_id": _as_int(entry.get("source_cycle_id"), -1),
        "source_start_step": int(start),
        "source_end_step_exclusive": int(end),
        "source_window_len": _as_int(entry.get("source_window_len"), max(0, end - start)),
        "training_tier": str(entry.get("training_tier", "")),
        "risk_score": float(risk_score),
        "risk_flags": "|".join(risk_flags) if risk_flags else "none",
        "operator_cut_payload_gain_kg": _as_float(entry.get("operator_cut_payload_gain_kg")),
        "cycle_effective_deposit_delta_kg": _as_float(entry.get("cycle_effective_deposit_delta_kg")),
        "return_entry_delta_norm_m": _as_float(entry.get("return_entry_delta_norm_m")),
        "carry_bucket_mass_loss_kg": _as_float(
            dict(entry.get("carry_qc") or {}).get("carry_bucket_mass_loss_kg")
        ),
        "carry_dump_boundary_source": str(
            dict(entry.get("carry_qc") or {}).get("carry_dump_ownership_boundary_source", "")
        ),
        "dump_start_source": str(
            dict(entry.get("dump_qc") or {}).get("dump_start_source", "")
        ),
        "dump_pre_release_lead_steps": _as_float(
            dict(entry.get("dump_qc") or {}).get("dump_pre_release_lead_steps")
        ),
        "dump_start_relative_x_m": _as_float(
            dict(entry.get("dump_qc") or {}).get("dump_start_dump_area_relative_x_m")
        ),
        "dump_start_relative_z_m": _as_float(
            dict(entry.get("dump_qc") or {}).get("dump_start_dump_area_relative_z_m")
        ),
        "dump_start_height_above_rim_m": _as_float(
            dict(entry.get("dump_qc") or {}).get("dump_start_height_above_rim_m")
        ),
        "dump_start_over_target_footprint": _as_float(
            dict(entry.get("dump_qc") or {}).get("dump_start_over_target_footprint")
        ),
        "dump_start_clearance_ok": _as_float(
            dict(entry.get("dump_qc") or {}).get("dump_start_clearance_ok")
        ),
        "dump_acceptance_mode": str(
            dict(entry.get("dump_qc") or {}).get("dump_acceptance_mode", "")
        ),
        "output_episode_path": str(entry.get("output_episode_path", "")),
    }


def _risk(*, entry: dict[str, Any], primitive: str, boundary_name: str) -> tuple[list[str], float]:
    flags: list[str] = []
    score = 0.0

    if str(entry.get("training_tier", "gold")) != "gold":
        flags.append("non_gold")
        score += 2.0

    window_len = _as_float(entry.get("source_window_len"))
    if math.isfinite(window_len) and window_len < 40:
        flags.append("short_window")
        score += 1.0

    payload = _as_float(entry.get("operator_cut_payload_gain_kg"))
    deposit = _as_float(entry.get("cycle_effective_deposit_delta_kg"))
    return_delta = _as_float(entry.get("return_entry_delta_norm_m"))

    if primitive == "dig" and math.isfinite(payload) and payload < 15.0:
        flags.append("low_dig_payload")
        score += 3.0
    if primitive == "dump" and math.isfinite(deposit) and deposit < 15.0:
        flags.append("low_effective_deposit")
        score += 3.0
    if primitive == "return" and math.isfinite(return_delta) and return_delta > 0.20:
        flags.append("return_target_gap")
        score += 3.0

    carry_qc = dict(entry.get("carry_qc") or {})
    carry_loss = _as_float(carry_qc.get("carry_bucket_mass_loss_kg"))
    if primitive == "carry" and math.isfinite(carry_loss) and carry_loss > 5.0:
        flags.append("carry_mass_loss")
        score += 3.0
    release_steps = _as_float(carry_qc.get("carry_steps_before_release"))
    if primitive == "carry" and math.isfinite(release_steps) and release_steps <= 2.0:
        flags.append("carry_dump_transition_tight")
        score += 1.0
    official_gap = _as_float(carry_qc.get("carry_dump_approach_steps_before_intent"))
    if primitive == "carry" and math.isfinite(official_gap) and official_gap > 120.0:
        flags.append("early_dump_ownership_vs_official")
        score += 1.0

    dump_qc = dict(entry.get("dump_qc") or {})
    outside = _as_float(
        dump_qc.get(
            "start_dump_area_footprint_outside_distance_m",
            dump_qc.get("dump_start_dump_area_footprint_outside_distance_m"),
        )
    )
    if (
        primitive == "dump"
        and math.isfinite(outside)
        and outside > DUMP_START_OUTSIDE_RISK_THRESHOLD_M
    ):
        flags.append("dump_start_outside_footprint")
        score += 1.5

    if boundary_name == "start":
        score *= 0.85
    return flags, score


def _select_video_records(records: list[dict[str, Any]], *, max_videos: int, sample: str) -> list[dict[str, Any]]:
    if max_videos <= 0:
        return []
    if sample == "top-risk":
        return [dict(record) for record in records[:max_videos]]

    by_primitive: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_primitive[str(record["primitive_name"])].append(record)
    selected: list[dict[str, Any]] = []
    primitive_names = sorted(by_primitive)
    while len(selected) < max_videos and primitive_names:
        progressed = False
        for primitive in primitive_names:
            bucket = by_primitive[primitive]
            if bucket:
                selected.append(dict(bucket.pop(0)))
                progressed = True
                if len(selected) >= max_videos:
                    break
        if not progressed:
            break
    return selected


def _export_boundary_video(
    *,
    record: dict[str, Any],
    output_path: Path,
    camera: str,
    pre_steps: int,
    post_steps: int,
    fps: int | None,
) -> None:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("opencv-python is required to export audit videos") from exc

    source_path = Path(str(record["source_episode_path"]))
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    image_path = f"observations/images/{camera}"
    with h5py.File(source_path, "r") as f:
        if image_path not in f:
            raise KeyError(f"{image_path} not found in {source_path}")
        ds = f[image_path]
        total = int(ds.shape[0])
        boundary_step = int(np.clip(int(record["boundary_step"]), 0, max(0, total - 1)))
        start = max(0, boundary_step - int(pre_steps))
        end = min(total, boundary_step + int(post_steps))
        frames = np.asarray(ds[start:end], dtype=np.uint8)
        meta = dict(f["metadata"].attrs) if "metadata" in f else {}
    if frames.size == 0:
        raise ValueError("empty frame window")

    source_fps = _safe_int(meta.get("control_hz"), 50)
    video_fps = int(fps or source_fps or 50)
    h, w = frames[0].shape[:2]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        video_fps,
        (w, h),
    )
    boundary_local = boundary_step - start
    for i, frame in enumerate(frames):
        img = frame[:, :, ::-1].copy()
        if i == boundary_local:
            cv2.line(img, (0, 0), (w - 1, h - 1), (0, 220, 255), 2)
            cv2.line(img, (w - 1, 0), (0, h - 1), (0, 220, 255), 2)
        _draw_overlay(img, record=record, source_step=start + i, boundary_step=boundary_step)
        writer.write(img)
    writer.release()


def _safe_write_contact_sheet_report(
    *,
    records: list[dict[str, Any]],
    output_dir: Path,
    camera: str,
    title: str,
    metric_pre_steps: int,
    metric_post_steps: int,
) -> dict[str, Any]:
    try:
        return _write_contact_sheet_report(
            records=records,
            output_dir=output_dir,
            camera=camera,
            title=title,
            metric_pre_steps=metric_pre_steps,
            metric_post_steps=metric_post_steps,
        )
    except Exception as exc:  # pragma: no cover - best-effort audit artifact.
        return {
            "status": f"failed:{type(exc).__name__}:{exc}",
            "record_count": int(len(records)),
            "sheet_count": 0,
            "failed_count": int(len(records)),
            "index_path": str(output_dir / "index.html"),
            "selected_records_path": str(output_dir / "records.json"),
        }


def _write_contact_sheet_report(
    *,
    records: list[dict[str, Any]],
    output_dir: Path,
    camera: str,
    title: str,
    metric_pre_steps: int,
    metric_post_steps: int,
) -> dict[str, Any]:
    from PIL import Image  # noqa: F401 - imported here to fail softly via wrapper.

    output_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir = output_dir / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)

    report_records: list[dict[str, Any]] = []
    failed_count = 0
    for rank, record in enumerate(records):
        report_record = dict(record)
        sheet_path = sheets_dir / _sheet_name(rank, record)
        try:
            _render_contact_sheet(
                record=record,
                output_path=sheet_path,
                camera=camera,
                metric_pre_steps=metric_pre_steps,
                metric_post_steps=metric_post_steps,
            )
            report_record["contact_sheet_path"] = str(sheet_path)
            report_record["contact_sheet_status"] = "ok"
            record["contact_sheet_path"] = str(sheet_path)
            record["contact_sheet_status"] = "ok"
        except Exception as exc:  # pragma: no cover - best-effort audit artifact.
            failed_count += 1
            report_record["contact_sheet_path"] = ""
            report_record["contact_sheet_status"] = f"failed:{type(exc).__name__}:{exc}"
            record["contact_sheet_path"] = ""
            record["contact_sheet_status"] = report_record["contact_sheet_status"]
        report_records.append(report_record)

    records_path = output_dir / "records.json"
    with open(records_path, "w") as f:
        json.dump(_jsonable(report_records), f, indent=2, sort_keys=True)

    index_path = output_dir / "index.html"
    _write_contact_sheet_index(
        path=index_path,
        title=title,
        records=report_records,
        output_dir=output_dir,
        camera=camera,
        metric_pre_steps=metric_pre_steps,
        metric_post_steps=metric_post_steps,
    )
    return {
        "status": "ok",
        "record_count": int(len(report_records)),
        "sheet_count": int(len(report_records) - failed_count),
        "failed_count": int(failed_count),
        "index_path": str(index_path),
        "selected_records_path": str(records_path),
    }


def _render_contact_sheet(
    *,
    record: dict[str, Any],
    output_path: Path,
    camera: str,
    metric_pre_steps: int,
    metric_post_steps: int,
) -> None:
    from PIL import Image, ImageDraw

    source_path = Path(str(record["source_episode_path"]))
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    image_path = f"observations/images/{camera}"
    env_path = "observations/env_state"
    with h5py.File(source_path, "r") as f:
        if image_path not in f:
            raise KeyError(f"{image_path} not found in {source_path}")
        if env_path not in f:
            raise KeyError(f"{env_path} not found in {source_path}")

        image_ds = f[image_path]
        env_ds = f[env_path]
        total = min(int(image_ds.shape[0]), int(env_ds.shape[0]))
        if total <= 0:
            raise ValueError("empty source episode")

        boundary_step = int(np.clip(int(record["boundary_step"]), 0, total - 1))
        frame_steps = [
            int(np.clip(boundary_step + int(offset), 0, total - 1))
            for offset in CONTACT_SHEET_OFFSETS
        ]
        frames = [np.asarray(image_ds[step], dtype=np.uint8) for step in frame_steps]

        win_start = max(0, boundary_step - int(metric_pre_steps))
        win_end = min(total, boundary_step + int(metric_post_steps) + 1)
        env_window = np.asarray(env_ds[win_start:win_end], dtype=np.float32)

    metrics = _extract_boundary_metrics(env_window)
    boundary_index = int(boundary_step - win_start)
    frame_images = [
        _make_frame_tile(
            frame=frame,
            width=CONTACT_SHEET_FRAME_WIDTH,
            offset=int(offset),
            source_step=int(step),
            is_boundary=offset == 0,
        )
        for frame, offset, step in zip(frames, CONTACT_SHEET_OFFSETS, frame_steps)
    ]

    margin = 18
    gap = 8
    title_h = 112
    frame_h = max(img.height for img in frame_images)
    plot_h = 136
    plot_gap = 12
    width = max(
        1180,
        margin * 2 + sum(img.width for img in frame_images) + gap * (len(frame_images) - 1),
    )
    height = title_h + frame_h + 22 + plot_h * 3 + plot_gap * 2 + margin
    canvas = Image.new("RGB", (width, height), (246, 247, 249))
    draw = ImageDraw.Draw(canvas)

    _draw_sheet_header(
        draw=draw,
        record=record,
        metrics=metrics,
        boundary_index=boundary_index,
        x=margin,
        y=14,
        width=width - 2 * margin,
    )

    x = margin
    frame_y = title_h
    for img in frame_images:
        canvas.paste(img, (x, frame_y))
        x += img.width + gap

    plot_y = frame_y + frame_h + 18
    steps = np.arange(win_start, win_end, dtype=np.int32)
    _draw_metric_panel(
        draw=draw,
        rect=(margin, plot_y, width - margin, plot_y + plot_h),
        title="mass / deposit",
        steps=steps,
        boundary_step=boundary_step,
        series=[
            ("bucket_mass_kg", metrics["bucket_mass_kg"], (31, 119, 180)),
            ("deposit_gain_kg", metrics["deposit_gain_kg"], (44, 160, 44)),
        ],
    )
    plot_y += plot_h + plot_gap
    _draw_metric_panel(
        draw=draw,
        rect=(margin, plot_y, width - margin, plot_y + plot_h),
        title="dump-area geometry",
        steps=steps,
        boundary_step=boundary_step,
        series=[
            ("relative_x_m", metrics["relative_x_m"], (214, 39, 40)),
            ("relative_z_m", metrics["relative_z_m"], (148, 103, 189)),
            ("outside_m", metrics["outside_m"], (255, 127, 14)),
            ("height_above_rim_m", metrics["height_above_rim_m"], (23, 190, 207)),
        ],
    )
    plot_y += plot_h + plot_gap
    _draw_metric_panel(
        draw=draw,
        rect=(margin, plot_y, width - margin, plot_y + plot_h),
        title="target masks",
        steps=steps,
        boundary_step=boundary_step,
        series=[
            ("over_target_footprint", metrics["over_target_footprint"], (44, 160, 44)),
            ("clearance_ok", metrics["clearance_ok"], (31, 119, 180)),
            ("target_hdist_m", metrics["target_hdist_m"], (127, 127, 127)),
        ],
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, quality=92)


def _extract_boundary_metrics(env_window: np.ndarray) -> dict[str, np.ndarray]:
    n = int(env_window.shape[0]) if env_window.ndim == 2 else 0

    def col(idx: int) -> np.ndarray:
        if n <= 0 or env_window.ndim != 2 or env_window.shape[1] <= idx:
            return np.full((n,), np.nan, dtype=np.float32)
        values = np.asarray(env_window[:, idx], dtype=np.float32)
        values[~np.isfinite(values)] = np.nan
        return values

    deposit_parts = [
        np.maximum(col(ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX), 0.0),
        np.maximum(col(ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX), 0.0),
        np.maximum(col(ENV_STATE_OFFTARGET_DEPOSITED_MASS_IDX), 0.0),
    ]
    if deposit_parts:
        deposit = np.nanmax(np.stack(deposit_parts, axis=0), axis=0)
        finite_deposit = deposit[np.isfinite(deposit)]
        if len(finite_deposit):
            deposit = deposit - float(finite_deposit[0])
    else:
        deposit = np.full((n,), np.nan, dtype=np.float32)

    return {
        "bucket_mass_kg": col(ENV_STATE_MASS_IN_BUCKET_IDX),
        "deposit_gain_kg": deposit.astype(np.float32, copy=False),
        "relative_x_m": col(ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX),
        "relative_z_m": col(ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX),
        "outside_m": col(ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX),
        "over_target_footprint": col(ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX),
        "clearance_ok": col(ENV_STATE_DUMP_CLEARANCE_OK_IDX),
        "height_above_rim_m": col(ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX),
        "target_hdist_m": col(ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX),
    }


def _make_frame_tile(
    *,
    frame: np.ndarray,
    width: int,
    offset: int,
    source_step: int,
    is_boundary: bool,
) -> Any:
    from PIL import Image, ImageDraw

    img = Image.fromarray(_as_rgb_uint8(frame))
    scale = float(width) / max(1, img.width)
    height = max(1, int(round(img.height * scale)))
    img = img.resize((int(width), height), Image.Resampling.BILINEAR)
    tile = Image.new("RGB", (int(width), height + 34), (28, 31, 36))
    tile.paste(img, (0, 34))
    draw = ImageDraw.Draw(tile)
    label = f"offset {offset:+d}  step {source_step}"
    draw.rectangle((0, 0, width, 34), fill=(28, 31, 36))
    draw.text((7, 10), label, fill=(255, 255, 255))
    if is_boundary:
        draw.rectangle((1, 35, width - 2, height + 32), outline=(255, 205, 0), width=4)
        draw.line((0, 34, width - 1, height + 33), fill=(255, 205, 0), width=2)
        draw.line((width - 1, 34, 0, height + 33), fill=(255, 205, 0), width=2)
    return tile


def _as_rgb_uint8(frame: np.ndarray) -> np.ndarray:
    arr = np.asarray(frame)
    if arr.ndim == 2:
        arr = np.repeat(arr[:, :, None], 3, axis=2)
    if arr.ndim == 3 and arr.shape[2] > 3:
        arr = arr[:, :, :3]
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return arr


def _draw_sheet_header(
    *,
    draw: Any,
    record: dict[str, Any],
    metrics: dict[str, np.ndarray],
    boundary_index: int,
    x: int,
    y: int,
    width: int,
) -> None:
    draw.rectangle((x, y, x + width, y + 92), fill=(255, 255, 255), outline=(222, 226, 230))
    primitive = str(record["primitive_name"])
    boundary = str(record["boundary"])
    offset_note = "end offset 0 is source_end_step_exclusive / first post-primitive frame"
    if boundary == "start":
        offset_note = "start offset 0 is source_start_step / first primitive frame"
    title = (
        f"{primitive} {boundary} boundary | p{int(record['primitive_episode_id'])} "
        f"{record['source_episode_id']} c{int(record['source_cycle_id'])} "
        f"step={int(record['boundary_step'])} risk={float(record['risk_score']):.1f}"
    )
    draw.text((x + 12, y + 10), title[:190], fill=(20, 23, 28))
    draw.text((x + 12, y + 29), f"flags={record['risk_flags']} | tier={record['training_tier']}", fill=(67, 76, 88))
    draw.text((x + 12, y + 48), offset_note, fill=(67, 76, 88))
    draw.text((x + 12, y + 67), _boundary_metric_summary(metrics, boundary_index), fill=(20, 23, 28))


def _boundary_metric_summary(metrics: dict[str, np.ndarray], boundary_index: int) -> str:
    b = int(np.clip(boundary_index, 0, max(0, len(metrics["bucket_mass_kg"]) - 1)))
    p80 = int(np.clip(b + 80, 0, max(0, len(metrics["bucket_mass_kg"]) - 1)))
    m0 = _series_value(metrics["bucket_mass_kg"], b)
    m80 = _series_value(metrics["bucket_mass_kg"], p80)
    d0 = _series_value(metrics["deposit_gain_kg"], b)
    d80 = _series_value(metrics["deposit_gain_kg"], p80)
    out0 = _series_value(metrics["outside_m"], b)
    out80 = _series_value(metrics["outside_m"], p80)
    return (
        f"@0 rel_x={_fmt(_series_value(metrics['relative_x_m'], b))}m "
        f"rel_z={_fmt(_series_value(metrics['relative_z_m'], b))}m "
        f"outside={_fmt(out0)}m over={_fmt(_series_value(metrics['over_target_footprint'], b))} "
        f"clear={_fmt(_series_value(metrics['clearance_ok'], b))} "
        f"rim_h={_fmt(_series_value(metrics['height_above_rim_m'], b))}m | "
        f"+80 mass_drop={_fmt(m0 - m80)}kg deposit_gain={_fmt(d80 - d0)}kg "
        f"outside_delta={_fmt(out80 - out0)}m"
    )


def _draw_metric_panel(
    *,
    draw: Any,
    rect: tuple[int, int, int, int],
    title: str,
    steps: np.ndarray,
    boundary_step: int,
    series: list[tuple[str, np.ndarray, tuple[int, int, int]]],
) -> None:
    x0, y0, x1, y1 = rect
    draw.rectangle(rect, fill=(255, 255, 255), outline=(222, 226, 230))
    draw.text((x0 + 8, y0 + 8), title, fill=(20, 23, 28))
    plot_left = x0 + 52
    plot_top = y0 + 28
    plot_right = x1 - 14
    plot_bottom = y1 - 22
    draw.rectangle((plot_left, plot_top, plot_right, plot_bottom), outline=(230, 233, 237))

    valid_values = []
    for _, values, _ in series:
        arr = np.asarray(values, dtype=np.float32)
        valid_values.extend(arr[np.isfinite(arr)].tolist())
    if valid_values:
        vmin = float(np.min(valid_values))
        vmax = float(np.max(valid_values))
    else:
        vmin = 0.0
        vmax = 1.0
    if not math.isfinite(vmin) or not math.isfinite(vmax) or abs(vmax - vmin) < 1e-6:
        pad = 0.5 if abs(vmax) < 1.0 else abs(vmax) * 0.05
        vmin -= pad
        vmax += pad
    else:
        pad = (vmax - vmin) * 0.08
        vmin -= pad
        vmax += pad

    draw.text((x0 + 8, plot_top), _fmt(vmax), fill=(97, 106, 118))
    draw.text((x0 + 8, plot_bottom - 10), _fmt(vmin), fill=(97, 106, 118))
    if len(steps) > 1:
        bx = _plot_x(boundary_step, int(steps[0]), int(steps[-1]), plot_left, plot_right)
        draw.line((bx, plot_top, bx, plot_bottom), fill=(255, 205, 0), width=3)
        for offset in CONTACT_SHEET_OFFSETS:
            step = int(np.clip(boundary_step + offset, int(steps[0]), int(steps[-1])))
            kx = _plot_x(step, int(steps[0]), int(steps[-1]), plot_left, plot_right)
            draw.line((kx, plot_bottom - 4, kx, plot_bottom), fill=(150, 155, 162), width=1)

    legend_x = x0 + 150
    for label, values, color in series:
        draw.line((legend_x, y0 + 15, legend_x + 18, y0 + 15), fill=color, width=3)
        draw.text((legend_x + 23, y0 + 9), label, fill=(55, 63, 74))
        legend_x += 170
        _draw_series(
            draw=draw,
            values=values,
            steps=steps,
            rect=(plot_left, plot_top, plot_right, plot_bottom),
            vmin=vmin,
            vmax=vmax,
            color=color,
        )


def _draw_series(
    *,
    draw: Any,
    values: np.ndarray,
    steps: np.ndarray,
    rect: tuple[int, int, int, int],
    vmin: float,
    vmax: float,
    color: tuple[int, int, int],
) -> None:
    if len(steps) <= 1:
        return
    plot_left, plot_top, plot_right, plot_bottom = rect
    points: list[tuple[int, int]] = []
    for step, value in zip(steps, values):
        value_f = float(value)
        if not math.isfinite(value_f):
            if len(points) > 1:
                draw.line(points, fill=color, width=2)
            points = []
            continue
        x = _plot_x(int(step), int(steps[0]), int(steps[-1]), plot_left, plot_right)
        y = int(round(plot_bottom - (value_f - vmin) / max(1e-9, vmax - vmin) * (plot_bottom - plot_top)))
        y = int(np.clip(y, plot_top, plot_bottom))
        points.append((x, y))
    if len(points) > 1:
        draw.line(points, fill=color, width=2)


def _plot_x(step: int, start: int, end: int, left: int, right: int) -> int:
    if end <= start:
        return int(left)
    alpha = (int(step) - int(start)) / float(end - start)
    return int(round(left + np.clip(alpha, 0.0, 1.0) * (right - left)))


def _series_value(values: np.ndarray, index: int) -> float:
    if len(values) == 0:
        return float("nan")
    idx = int(np.clip(index, 0, len(values) - 1))
    return float(values[idx])


def _write_contact_sheet_index(
    *,
    path: Path,
    title: str,
    records: list[dict[str, Any]],
    output_dir: Path,
    camera: str,
    metric_pre_steps: int,
    metric_post_steps: int,
) -> None:
    cards: list[str] = []
    for record in records:
        sheet_path = str(record.get("contact_sheet_path", ""))
        status = str(record.get("contact_sheet_status", ""))
        rel = ""
        if sheet_path:
            try:
                rel = Path(sheet_path).relative_to(output_dir).as_posix()
            except ValueError:
                rel = sheet_path
        heading = (
            f"{record['primitive_name']} {record['boundary']} | "
            f"p{int(record['primitive_episode_id'])} {record['source_episode_id']} "
            f"c{int(record['source_cycle_id'])} risk={float(record['risk_score']):.1f}"
        )
        image_html = f'<a href="{escape(rel)}"><img src="{escape(rel)}" alt="{escape(heading)}"></a>' if rel else ""
        cards.append(
            "\n".join(
                [
                    "<section class=\"card\">",
                    f"<h2>{escape(heading)}</h2>",
                    f"<p><code>{escape(status)}</code> flags={escape(str(record['risk_flags']))} "
                    f"tier={escape(str(record['training_tier']))}</p>",
                    image_html,
                    "</section>",
                ]
            )
        )

    body = "\n".join(cards) if cards else "<p>No records selected for this report.</p>"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ margin: 24px; font-family: system-ui, sans-serif; background: #f6f7f9; color: #15171a; }}
    header {{ max-width: 1160px; margin-bottom: 20px; }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    p {{ line-height: 1.45; }}
    .card {{ background: #fff; border: 1px solid #dde2e7; border-radius: 8px; padding: 14px; margin: 0 0 18px; }}
    .card h2 {{ margin: 0 0 6px; font-size: 17px; }}
    .card img {{ max-width: 100%; height: auto; border: 1px solid #d3d8de; }}
    code {{ background: #eef1f4; padding: 2px 5px; border-radius: 4px; }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <p>Camera <code>{escape(camera)}</code>; metric window is -{int(metric_pre_steps)} to +{int(metric_post_steps)} steps. Offset 0 is the audited boundary frame: for end boundaries it is <code>source_end_step_exclusive</code>, the first post-primitive frame.</p>
    <p>Carry/dump review should combine signed dump-area <code>relative_x/z</code> corridor, <code>bucket_over_target_footprint_mask</code>, <code>dump_clearance_ok_mask</code>, height above rim, mass drop, deposit gain, and the video/keyframe intuition. The unsigned outside-distance curve is only a proximity signal.</p>
  </header>
  {body}
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def _select_clean_gold_records(records: list[dict[str, Any]], *, max_records: int) -> list[dict[str, Any]]:
    if max_records <= 0:
        return []
    clean = [
        record
        for record in records
        if str(record.get("training_tier")) == "gold" and str(record.get("risk_flags")) == "none"
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in clean:
        grouped[(str(record["primitive_name"]), str(record["boundary"]))].append(record)

    selected: list[dict[str, Any]] = []
    priority = [
        ("carry", "end"),
        ("dump", "start"),
        ("dump", "end"),
        ("carry", "start"),
        ("dig", "end"),
        ("return", "end"),
        ("dig", "start"),
        ("return", "start"),
    ]
    per_group = max(1, int(math.ceil(max_records / max(1, len(priority)))))
    for key in priority:
        for record in grouped.get(key, [])[:per_group]:
            selected.append(dict(record))
            if len(selected) >= max_records:
                return selected
    for record in clean:
        if len(selected) >= max_records:
            break
        if not any(
            int(record["primitive_episode_id"]) == int(existing["primitive_episode_id"])
            and str(record["boundary"]) == str(existing["boundary"])
            for existing in selected
        ):
            selected.append(dict(record))
    return selected


def _sheet_name(rank: int, record: dict[str, Any]) -> str:
    primitive = str(record["primitive_name"])
    ep = str(record["source_episode_id"]).replace("/", "_")
    cycle = int(record["source_cycle_id"])
    pid = int(record["primitive_episode_id"])
    boundary = str(record["boundary"])
    score = float(record["risk_score"])
    return f"{rank:03d}_{primitive}_p{pid:04d}_{ep}_c{cycle:03d}_{boundary}_risk{score:.1f}.jpg"


def _draw_overlay(img: np.ndarray, *, record: dict[str, Any], source_step: int, boundary_step: int) -> None:
    import cv2

    h, w = img.shape[:2]
    lines = [
        f"{record['primitive_name']} {record['boundary']} boundary  risk={record['risk_score']:.1f}",
        f"{record['source_episode_id']} cycle={record['source_cycle_id']} step={source_step} boundary={boundary_step}",
        f"flags={record['risk_flags']}",
        (
            f"payload={_fmt(record.get('operator_cut_payload_gain_kg'))}kg "
            f"deposit={_fmt(record.get('cycle_effective_deposit_delta_kg'))}kg "
            f"return_gap={_fmt(record.get('return_entry_delta_norm_m'))}m"
        ),
    ]
    x = 8
    y = 22
    line_h = 19
    box_h = line_h * len(lines) + 10
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (w, box_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, img, 0.45, 0, dst=img)
    for line in lines:
        cv2.putText(
            img,
            line[:130],
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        y += line_h
    cv2.putText(
        img,
        "BOUNDARY" if source_step == boundary_step else "",
        (max(8, w - 140), max(box_h + 26, h - 18)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (0, 220, 255),
        2,
        cv2.LINE_AA,
    )


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        path.write_text("")
        return
    fieldnames = list(records[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def _summary(
    *,
    records: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    primitive_root: Path,
    output_dir: Path,
    camera: str,
    pre_steps: int,
    post_steps: int,
    boundary: str,
    sample: str,
    selected_contact_sheet: dict[str, Any],
    clean_contact_sheet: dict[str, Any],
) -> dict[str, Any]:
    primitive_counts = Counter(str(record["primitive_name"]) for record in records)
    flag_counts: Counter[str] = Counter()
    for record in records:
        for flag in str(record["risk_flags"]).split("|"):
            if flag and flag != "none":
                flag_counts[flag] += 1
    risk_scores = np.asarray([float(record["risk_score"]) for record in records], dtype=np.float32)
    return {
        "primitive_root": str(primitive_root),
        "output_dir": str(output_dir),
        "camera": camera,
        "pre_steps": int(pre_steps),
        "post_steps": int(post_steps),
        "boundary": boundary,
        "sample": sample,
        "record_count": int(len(records)),
        "video_count": int(len(selected)),
        "primitive_counts": dict(sorted(primitive_counts.items())),
        "risk_flag_counts": dict(sorted(flag_counts.items())),
        "risk_score": {
            "min": float(np.min(risk_scores)) if len(risk_scores) else 0.0,
            "median": float(np.median(risk_scores)) if len(risk_scores) else 0.0,
            "p90": float(np.percentile(risk_scores, 90)) if len(risk_scores) else 0.0,
            "max": float(np.max(risk_scores)) if len(risk_scores) else 0.0,
        },
        "top_records": records[:20],
        "selected_videos": selected,
        "summary_path": str(output_dir / "summary.json"),
        "csv_path": str(output_dir / "boundary_audit.csv"),
        "selected_videos_path": str(output_dir / "selected_boundary_videos.json"),
        "videos_dir": str(output_dir / "videos"),
        "selected_contact_sheet": selected_contact_sheet,
        "clean_gold_contact_sheet": clean_contact_sheet,
    }


def _video_name(rank: int, record: dict[str, Any]) -> str:
    primitive = str(record["primitive_name"])
    ep = str(record["source_episode_id"]).replace("/", "_")
    cycle = int(record["source_cycle_id"])
    pid = int(record["primitive_episode_id"])
    boundary = str(record["boundary"])
    score = float(record["risk_score"])
    return f"{rank:03d}_{primitive}_p{pid:04d}_{ep}_c{cycle:03d}_{boundary}_risk{score:.1f}.mp4"


def _as_float(value: Any, default: float = float("nan")) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int) -> int:
    try:
        if isinstance(value, bytes):
            value = value.decode()
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _fmt(value: Any) -> str:
    number = _as_float(value)
    if not math.isfinite(number):
        return "nan"
    return f"{number:.2f}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


if __name__ == "__main__":
    main()
