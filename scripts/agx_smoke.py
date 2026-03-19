"""
Minimal AGX Unity socket smoke test.

Runs:
  GET_INFO -> RESET -> STEP x N

and validates the binary protocol contract documented in the Unity repo.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from testbed.backends.agx.protocol import IMAGE_PIXEL_FORMAT, AgxSimClient


def _assert_finite(name: str, value: np.ndarray) -> None:
    if not np.all(np.isfinite(value)):
        raise RuntimeError(f"{name} contains NaN/Inf: {value}")


def _validate_common_step(
    *,
    resp,
    expected_step_id: int,
    expected_image_shape: tuple[int, int, int] | None,
) -> tuple[int, int, int]:
    image = resp.decode_rgb_image()

    if resp.step_id != expected_step_id:
        raise RuntimeError(
            f"step_id mismatch at step {expected_step_id}: got {resp.step_id}"
        )
    if resp.qpos.shape != (4,):
        raise RuntimeError(
            f"qpos shape mismatch at step {expected_step_id}: {resp.qpos.shape}"
        )
    if resp.qvel.shape != (4,):
        raise RuntimeError(
            f"qvel shape mismatch at step {expected_step_id}: {resp.qvel.shape}"
        )
    if resp.env_state.size < 1:
        raise RuntimeError(
            f"env_state too short at step {expected_step_id}: size={resp.env_state.size}"
        )
    if resp.image_format != IMAGE_PIXEL_FORMAT:
        raise RuntimeError(
            f"image_format mismatch at step {expected_step_id}: {resp.image_format!r}"
        )
    if image is None:
        raise RuntimeError(f"missing fpv image at step {expected_step_id}")
    if image.shape != (resp.image_h, resp.image_w, 3):
        raise RuntimeError(
            f"image shape mismatch at step {expected_step_id}: {image.shape}"
        )

    _assert_finite("qpos", resp.qpos)
    _assert_finite("qvel", resp.qvel)
    _assert_finite("env_state", resp.env_state)

    if np.any(resp.qpos < -1.0e-4) or np.any(resp.qpos > 1.0001):
        raise RuntimeError(
            f"qpos out of normalized range at step {expected_step_id}: {resp.qpos}"
        )

    if expected_image_shape is not None and image.shape != expected_image_shape:
        raise RuntimeError(
            "fpv image shape changed during run: "
            f"expected {expected_image_shape}, got {image.shape}"
        )

    if resp.image_w * resp.image_h * 3 != len(resp.image_payload):
        raise RuntimeError(
            "image payload size mismatch at step "
            f"{expected_step_id}: dims={resp.image_w}x{resp.image_h}, "
            f"bytes={len(resp.image_payload)}"
        )

    return image.shape


def _run_zero_step(client: AgxSimClient, step_id: int) -> tuple[int, object]:
    resp = client.step(step_id=step_id, action=np.zeros(4, dtype=np.float32))
    return step_id + 1, resp


def _capture_reset_baseline(
    client: AgxSimClient,
    *,
    seed: int,
    step_id: int,
    settle_steps: int,
) -> tuple[int, object]:
    reset = client.reset(seed=seed, reset_terrain=True, reset_pose=True)
    if not reset.reset_applied:
        raise RuntimeError("RESET did not apply reset_pose/reset_terrain")

    resp = None
    for _ in range(settle_steps):
        step_id, resp = _run_zero_step(client, step_id)
    assert resp is not None
    return step_id, resp


def _pulse_axis_response(
    client: AgxSimClient,
    *,
    step_id: int,
    axis: int,
    action_value: float,
    response_steps: int,
    expected_image_shape: tuple[int, int, int] | None,
) -> tuple[int, np.ndarray, tuple[int, int, int]]:
    action = np.zeros(4, dtype=np.float32)
    action[axis] = np.float32(action_value)
    axis_values: list[float] = []
    image_shape = expected_image_shape

    for _ in range(response_steps):
        resp = client.step(step_id=step_id, action=action)
        image_shape = _validate_common_step(
            resp=resp,
            expected_step_id=step_id,
            expected_image_shape=image_shape,
        )
        axis_values.append(float(resp.qvel[axis]))
        step_id += 1

    return step_id, np.asarray(axis_values, dtype=np.float32), image_shape


def _run_strict_checks(
    client: AgxSimClient,
    *,
    seed: int,
    start_step_id: int,
    expected_image_shape: tuple[int, int, int] | None,
    reset_qpos_tol: float,
    response_steps: int,
    response_amplitude: float,
    min_response_abs_mean: float,
) -> tuple[int, tuple[int, int, int] | None]:
    print("STRICT starting reset-baseline consistency checks")
    step_id = start_step_id
    step_id, baseline_a = _capture_reset_baseline(
        client,
        seed=seed,
        step_id=step_id,
        settle_steps=2,
    )
    expected_image_shape = _validate_common_step(
        resp=baseline_a,
        expected_step_id=step_id - 1,
        expected_image_shape=expected_image_shape,
    )

    disturbance = np.asarray(
        [response_amplitude, 0.5 * response_amplitude, 0.0, -0.5 * response_amplitude],
        dtype=np.float32,
    )
    for _ in range(max(4, response_steps // 2)):
        resp = client.step(step_id=step_id, action=disturbance)
        expected_image_shape = _validate_common_step(
            resp=resp,
            expected_step_id=step_id,
            expected_image_shape=expected_image_shape,
        )
        step_id += 1

    step_id, baseline_b = _capture_reset_baseline(
        client,
        seed=seed,
        step_id=step_id,
        settle_steps=2,
    )
    expected_image_shape = _validate_common_step(
        resp=baseline_b,
        expected_step_id=step_id - 1,
        expected_image_shape=expected_image_shape,
    )

    qpos_reset_diff = np.abs(baseline_a.qpos - baseline_b.qpos)
    env_reset_diff = np.abs(baseline_a.env_state - baseline_b.env_state)
    if float(np.max(qpos_reset_diff)) > reset_qpos_tol:
        raise RuntimeError(
            "reset baseline qpos drift too large: "
            f"max_diff={float(np.max(qpos_reset_diff)):.6f} "
            f"tol={reset_qpos_tol:.6f}"
        )

    print(
        "STRICT reset baseline ok "
        f"qpos_max_diff={float(np.max(qpos_reset_diff)):.6f} "
        f"env_max_diff={float(np.max(env_reset_diff)):.6f}"
    )

    print("STRICT starting reset-separated action-response sign checks")
    tail_window = max(3, min(6, response_steps // 2))

    step_id, _ = _capture_reset_baseline(
        client,
        seed=seed,
        step_id=step_id,
        settle_steps=2,
    )
    step_id, pos_trace, expected_image_shape = _pulse_axis_response(
        client,
        step_id=step_id,
        axis=0,
        action_value=abs(response_amplitude),
        response_steps=response_steps,
        expected_image_shape=expected_image_shape,
    )
    pos_tail_mean = float(np.mean(pos_trace[-tail_window:]))

    step_id, _ = _capture_reset_baseline(
        client,
        seed=seed,
        step_id=step_id,
        settle_steps=2,
    )
    step_id, neg_trace, expected_image_shape = _pulse_axis_response(
        client,
        step_id=step_id,
        axis=0,
        action_value=-abs(response_amplitude),
        response_steps=response_steps,
        expected_image_shape=expected_image_shape,
    )
    neg_tail_mean = float(np.mean(neg_trace[-tail_window:]))

    if pos_tail_mean < min_response_abs_mean:
        raise RuntimeError(
            "positive swing response too weak: "
            f"tail_mean_qvel={pos_tail_mean:.6f}, min={min_response_abs_mean:.6f}, "
            f"trace={np.round(pos_trace, 6).tolist()}"
        )
    if neg_tail_mean > -min_response_abs_mean:
        raise RuntimeError(
            "negative swing response too weak: "
            f"tail_mean_qvel={neg_tail_mean:.6f}, min={min_response_abs_mean:.6f}, "
            f"trace={np.round(neg_trace, 6).tolist()}"
        )

    print(
        "STRICT swing sign response ok "
        f"tail_window={tail_window} "
        f"pos_tail_mean={pos_tail_mean:.6f} "
        f"neg_tail_mean={neg_tail_mean:.6f}"
    )

    return step_id, expected_image_shape


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5057)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--action",
        type=float,
        nargs=4,
        default=(0.0, 0.0, 0.0, 0.0),
        metavar=("SWING", "BOOM", "STICK", "BUCKET"),
        help="Constant 4D actuator-speed command used for all steps.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Run additional reset-consistency and action-response checks.",
    )
    parser.add_argument(
        "--reset-qpos-tol",
        type=float,
        default=0.02,
        help="Max allowed absolute qpos drift between two reset baselines.",
    )
    parser.add_argument(
        "--response-steps",
        type=int,
        default=12,
        help="Number of steps used per strict action-response pulse.",
    )
    parser.add_argument(
        "--response-amplitude",
        type=float,
        default=0.6,
        help="Absolute action amplitude used for strict swing-response checks.",
    )
    parser.add_argument(
        "--min-response-abs-mean",
        type=float,
        default=0.02,
        help="Minimum absolute mean qvel required in strict response checks.",
    )
    args = parser.parse_args()

    action = np.asarray(args.action, dtype=np.float32)

    with AgxSimClient(host=args.host, port=args.port, timeout_s=args.timeout) as client:
        info = client.get_info()
        print(
            "GET_INFO "
            f"protocol={info.protocol_version} dt={info.dt:.4f}s hz={info.control_hz:.2f} "
            f"action_order={list(info.action_order)} qpos_order={list(info.qpos_order)} "
            f"cameras={list(info.camera_names)} warnings={list(info.warnings)}"
        )

        if info.protocol_version != "agx-sim/v0":
            raise RuntimeError(f"unexpected protocol_version: {info.protocol_version!r}")
        if tuple(info.qpos_order) != (
            "swing_position_norm",
            "boom_position_norm",
            "stick_position_norm",
            "bucket_position_norm",
        ):
            raise RuntimeError(f"unexpected qpos_order: {info.qpos_order}")
        if tuple(info.qvel_order) != (
            "swing_speed",
            "boom_speed",
            "stick_speed",
            "bucket_speed",
        ):
            raise RuntimeError(f"unexpected qvel_order: {info.qvel_order}")
        if tuple(info.action_order) != (
            "swing_speed_cmd",
            "boom_speed_cmd",
            "stick_speed_cmd",
            "bucket_speed_cmd",
        ):
            raise RuntimeError(f"unexpected action_order: {info.action_order}")
        if not info.supports_images:
            raise RuntimeError("Unity GET_INFO reports supports_images = false")
        if "fpv" not in info.camera_names:
            raise RuntimeError(f"fpv camera missing from camera_names: {info.camera_names}")
        if not info.cameras:
            raise RuntimeError("Unity GET_INFO returned no camera descriptors")
        fpv_descriptors = [camera for camera in info.cameras if camera.name == "fpv"]
        if len(fpv_descriptors) != 1:
            raise RuntimeError(f"expected exactly one fpv descriptor, got {len(fpv_descriptors)}")
        fpv = fpv_descriptors[0]
        if fpv.pixel_format != IMAGE_PIXEL_FORMAT:
            raise RuntimeError(
                f"unexpected fpv pixel_format: {fpv.pixel_format!r}"
            )
        if fpv.row_order != "top_to_bottom":
            raise RuntimeError(f"unexpected fpv row_order: {fpv.row_order!r}")
        if fpv.width <= 0 or fpv.height <= 0:
            raise RuntimeError(
                f"invalid fpv dimensions from GET_INFO: {fpv.width}x{fpv.height}"
            )

        reset = client.reset(seed=args.seed, reset_terrain=True, reset_pose=True)
        print(
            "RESET "
            f"applied={reset.reset_applied} dt={reset.dt:.4f}s hz={reset.control_hz:.2f} "
            f"warnings={list(reset.warnings)}"
        )
        if not reset.reset_applied:
            raise RuntimeError("RESET returned reset_applied = false")

        first_shape: tuple[int, int, int] | None = None
        first_warnings: list[str] = []
        start = time.perf_counter()
        step_id = 0

        if args.strict:
            strict_start = time.perf_counter()
            step_id, first_shape = _run_strict_checks(
                client,
                seed=args.seed,
                start_step_id=step_id,
                expected_image_shape=first_shape,
                reset_qpos_tol=args.reset_qpos_tol,
                response_steps=args.response_steps,
                response_amplitude=args.response_amplitude,
                min_response_abs_mean=args.min_response_abs_mean,
            )
            strict_elapsed = time.perf_counter() - strict_start
            print(
                f"STRICT_PASS preflight_elapsed={strict_elapsed:.2f}s "
                f"next_step_id={step_id}"
            )

        sim_time_values: list[int] = []
        for local_index in range(args.steps):
            resp = client.step(step_id=step_id, action=action)
            first_shape = _validate_common_step(
                resp=resp,
                expected_step_id=step_id,
                expected_image_shape=first_shape,
            )
            if resp.warnings and not first_warnings:
                first_warnings = list(resp.warnings)
            sim_time_values.append(int(resp.sim_time_ns))

            if local_index in (0, args.steps - 1):
                print(
                    f"STEP {step_id} "
                    f"qpos={np.round(resp.qpos, 4).tolist()} "
                    f"qvel={np.round(resp.qvel, 4).tolist()} "
                    f"env_state={np.round(resp.env_state, 4).tolist()} "
                    f"image_shape={first_shape} warnings={list(resp.warnings)}"
                )
            step_id += 1

        elapsed = time.perf_counter() - start
        hz = args.steps / elapsed if elapsed > 0 else 0.0
        sim_time_values_np = np.asarray(sim_time_values, dtype=np.int64)
        sim_time_deltas = np.diff(sim_time_values_np)
        monotonic = bool(np.all(sim_time_deltas >= 0))
        if not monotonic:
            raise RuntimeError(
                "sim_time_ns is not monotonic: "
                f"min_delta={int(np.min(sim_time_deltas))}"
            )
        sim_time_delta_ns_median = (
            int(np.median(sim_time_deltas)) if sim_time_deltas.size > 0 else 0
        )
        print(
            f"PASS steps={args.steps} elapsed={elapsed:.2f}s throughput={hz:.2f}Hz "
            f"first_image_shape={first_shape} "
            f"sim_time_delta_ns_median={sim_time_delta_ns_median} "
            f"first_step_warnings={first_warnings}"
        )


if __name__ == "__main__":
    main()
