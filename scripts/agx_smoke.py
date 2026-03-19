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

        if tuple(info.qpos_order) != (
            "swing_position_norm",
            "boom_position_norm",
            "stick_position_norm",
            "bucket_position_norm",
        ):
            raise RuntimeError(f"unexpected qpos_order: {info.qpos_order}")

        reset = client.reset(seed=args.seed, reset_terrain=True, reset_pose=True)
        print(
            "RESET "
            f"applied={reset.reset_applied} dt={reset.dt:.4f}s hz={reset.control_hz:.2f} "
            f"warnings={list(reset.warnings)}"
        )

        first_shape: tuple[int, int, int] | None = None
        first_warnings: list[str] = []
        start = time.perf_counter()

        for step_id in range(args.steps):
            resp = client.step(step_id=step_id, action=action)
            image = resp.decode_rgb_image()

            if resp.step_id != step_id:
                raise RuntimeError(
                    f"step_id mismatch at step {step_id}: got {resp.step_id}"
                )
            if resp.qpos.shape != (4,):
                raise RuntimeError(
                    f"qpos shape mismatch at step {step_id}: {resp.qpos.shape}"
                )
            if resp.qvel.shape != (4,):
                raise RuntimeError(
                    f"qvel shape mismatch at step {step_id}: {resp.qvel.shape}"
                )
            if resp.env_state.size < 1:
                raise RuntimeError(
                    f"env_state too short at step {step_id}: size={resp.env_state.size}"
                )
            if resp.image_format != IMAGE_PIXEL_FORMAT:
                raise RuntimeError(
                    f"image_format mismatch at step {step_id}: {resp.image_format!r}"
                )
            if image is None:
                raise RuntimeError(f"missing fpv image at step {step_id}")
            if image.shape != (resp.image_h, resp.image_w, 3):
                raise RuntimeError(
                    f"image shape mismatch at step {step_id}: {image.shape}"
                )

            if first_shape is None:
                first_shape = image.shape
            if resp.warnings and not first_warnings:
                first_warnings = list(resp.warnings)

            if step_id in (0, args.steps - 1):
                print(
                    f"STEP {step_id} "
                    f"qpos={np.round(resp.qpos, 4).tolist()} "
                    f"qvel={np.round(resp.qvel, 4).tolist()} "
                    f"env_state={np.round(resp.env_state, 4).tolist()} "
                    f"image_shape={image.shape} warnings={list(resp.warnings)}"
                )

        elapsed = time.perf_counter() - start
        hz = args.steps / elapsed if elapsed > 0 else 0.0
        print(
            f"PASS steps={args.steps} elapsed={elapsed:.2f}s throughput={hz:.2f}Hz "
            f"first_image_shape={first_shape} first_step_warnings={first_warnings}"
        )


if __name__ == "__main__":
    main()
