"""
demo_sim.py — Run a trained ACT policy in the MuJoCo sim and save a video.

Usage (run from repo root with aloha env active):
    python scripts/demo_sim.py
    python scripts/demo_sim.py --ckpt runs/ckpts/transfer_cube_act_v0/policy_latest.ckpt
    python scripts/demo_sim.py --rollouts 5 --out runs/demo/

What this does:
  1. Loads the trained checkpoint (best or latest)
  2. Runs N rollouts of sim_transfer_cube_scripted (vx300s bimanual)
     using the EE-space MuJoCo backend — same env used for data collection
  3. Saves each rollout as an MP4 video with reward overlay
  4. Prints per-rollout success and a final success rate

NOTE: This is 100% scripted-data trained, sim-only.
      No excavator, no teleop. Swap task/ckpt when ready.
"""

from __future__ import annotations

import argparse
import os
import pickle
import sys
from pathlib import Path

import numpy as np

# ── ensure repo root is on path ───────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CKPT_DIR     = ROOT / "runs/ckpts/transfer_cube_act_v0"
DEFAULT_CKPT = CKPT_DIR / "policy_best.ckpt"
FALLBACK_CKPT= CKPT_DIR / "policy_latest.ckpt"
STATS_PATH   = CKPT_DIR / "dataset_stats.pkl"
OUT_DIR      = ROOT / "runs/demo/transfer_cube_act_v0"

TASK_NAME       = "sim_transfer_cube_scripted"
EQUIPMENT_MODEL = "vx300s_bimanual"
EPISODE_LEN     = 400
CAMERA_NAMES    = ["top"]
ENV_MAX_REWARD  = 4.0

POLICY_CONFIG = {
    "lr":              1e-5,
    "num_queries":     100,   # chunk_size
    "kl_weight":       10.0,
    "hidden_dim":      512,
    "dim_feedforward": 3200,
    "lr_backbone":     1e-5,
    "backbone":        "resnet18",
    "enc_layers":      4,
    "dec_layers":      7,
    "nheads":          8,
    "camera_names":    CAMERA_NAMES,
    "equipment_model": EQUIPMENT_MODEL,
}


def make_env():
    from testbed.backends.mujoco.backend import MuJoCoSimBackend
    return MuJoCoSimBackend(task_name=TASK_NAME, equipment_model=EQUIPMENT_MODEL)


def load_policy(ckpt_path: Path):
    from testbed.policies.act.adapter import ACTAdapter
    print(f"Loading checkpoint: {ckpt_path}")
    return ACTAdapter.from_checkpoint(
        ckpt_path=ckpt_path,
        policy_config=POLICY_CONFIG,
        norm_stats_path=STATS_PATH,
        temporal_agg=True,
    )


def run_rollout(env, policy, seed: int) -> tuple[list[float], list[np.ndarray]]:
    """Run one episode. Returns (rewards, frames)."""
    from testbed.backends.mujoco.tasks.sampling import sample_box_pose

    np.random.seed(seed)
    object_pose = sample_box_pose()
    env.set_initial_object_pose(object_pose)
    ts = env.reset()
    policy.reset()

    rewards: list[float]      = []
    frames:  list[np.ndarray] = []

    for _ in range(EPISODE_LEN):
        obs = ts.observation
        policy_input = dict(obs)

        # build image_<cam> keys expected by ACTAdapter
        for cam in CAMERA_NAMES:
            if "images" in obs and cam in obs["images"]:
                from einops import rearrange
                img = rearrange(
                    np.array(obs["images"][cam], dtype=np.float32) / 255.0,
                    "h w c -> c h w",
                )
                policy_input[f"image_{cam}"] = img

        action = policy.predict(policy_input)
        ts = env.step(action)

        rewards.append(float(ts.reward) if ts.reward is not None else 0.0)
        if "images" in ts.observation and CAMERA_NAMES[0] in ts.observation["images"]:
            frames.append(ts.observation["images"][CAMERA_NAMES[0]].copy())

    return rewards, frames


def save_video(frames: list[np.ndarray], path: Path, rewards: list[float], success: bool) -> None:
    from testbed.eval.video import save_eval_video
    from testbed.backends.mujoco.tasks.constants import DT
    path.parent.mkdir(parents=True, exist_ok=True)
    save_eval_video(
        frames=frames,
        dt=DT,
        video_path=path,
        reward_curve=rewards,
        phase_labels=None,
        success=success,
    )
    print(f"  Video: {path}")


def main():
    parser = argparse.ArgumentParser(description="Run trained ACT policy demo in sim.")
    parser.add_argument("--ckpt",     type=Path, default=None,  help="Checkpoint path (default: policy_best.ckpt, fallback: policy_latest.ckpt)")
    parser.add_argument("--rollouts", type=int,  default=10,    help="Number of rollouts (default: 10)")
    parser.add_argument("--out",      type=Path, default=OUT_DIR, help="Output directory for videos")
    parser.add_argument("--seed",     type=int,  default=1000,  help="Base random seed (default: 1000, FIXED for eval)")
    args = parser.parse_args()

    # resolve checkpoint
    ckpt_path = args.ckpt
    if ckpt_path is None:
        ckpt_path = DEFAULT_CKPT if DEFAULT_CKPT.exists() else FALLBACK_CKPT
    if not ckpt_path.exists():
        print(f"ERROR: checkpoint not found: {ckpt_path}")
        print("Is training still running? Check: grep 'Epoch' runs/train_log.txt | tail -3")
        sys.exit(1)

    if not STATS_PATH.exists():
        print(f"ERROR: dataset_stats.pkl not found at {STATS_PATH}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Task:    {TASK_NAME}")
    print(f"  Model:   {EQUIPMENT_MODEL}")
    print(f"  Ckpt:    {ckpt_path.name}")
    print(f"  Rollouts:{args.rollouts}")
    print(f"  Seed:    {args.seed} (fixed — do not change for fair eval)")
    print(f"  Output:  {args.out}")
    print(f"{'='*60}\n")

    env    = make_env()
    policy = load_policy(ckpt_path)

    successes   = 0
    max_rewards = []

    for i in range(args.rollouts):
        rewards, frames = run_rollout(env, policy, seed=args.seed + i)
        max_r   = max(rewards) if rewards else 0.0
        success = max_r >= ENV_MAX_REWARD
        if success:
            successes += 1
        max_rewards.append(max_r)

        status = "✓ SUCCESS" if success else f"✗ failed  (max_reward={max_r:.1f})"
        print(f"  Rollout {i:2d}  {status}")

        video_path = Path(args.out) / f"rollout_{i:03d}.mp4"
        if frames:
            save_video(frames, video_path, rewards, success)

    print(f"\n{'='*60}")
    print(f"  Success rate:  {successes}/{args.rollouts} = {100*successes/args.rollouts:.1f}%")
    print(f"  Avg max reward:{np.mean(max_rewards):.2f} / {ENV_MAX_REWARD:.1f}")
    print(f"  Videos saved to: {args.out}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
