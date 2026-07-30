"""
watch_sim.py — Live MuJoCo viewer of the trained ACT policy.

Opens a real-time interactive MuJoCo window showing the robot
executing the learned policy.  You can rotate/zoom/pan with mouse.

Usage (run from repo root, aloha env active):
    python scripts/watch_sim.py               # runs 3 rollouts
    python scripts/watch_sim.py --rollouts 5
    python scripts/watch_sim.py --seed 1002   # try a different cube position
    python scripts/watch_sim.py --no-policy   # just show env, no policy
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CKPT_DIR     = ROOT / "runs/ckpts/transfer_cube_act_v0"
DEFAULT_CKPT = CKPT_DIR / "policy_best.ckpt"
STATS_PATH   = CKPT_DIR / "dataset_stats.pkl"

TASK_NAME       = "sim_transfer_cube_scripted"
EQUIPMENT_MODEL = "vx300s_bimanual"
EPISODE_LEN     = 400
CAMERA_NAMES    = ["top"]
ENV_MAX_REWARD  = 4.0
DT              = 0.02          # 50 Hz — sleep between steps for real-time feel

POLICY_CONFIG = {
    "lr":              1e-5,
    "num_queries":     100,
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


# ─────────────────────────────────────────────────────────────────────────────

def load_policy(ckpt_path: Path):
    from testbed.policies.act.adapter import ACTAdapter
    print(f"Loading checkpoint: {ckpt_path.name}")
    return ACTAdapter.from_checkpoint(
        ckpt_path=ckpt_path,
        policy_config=POLICY_CONFIG,
        norm_stats_path=STATS_PATH,
        temporal_agg=True,
    )


def watch_rollout(env, policy, seed: int, viewer, realtime: bool) -> float:
    """Run one episode while rendering into `viewer`. Returns max reward."""
    from einops import rearrange

    from testbed.backends.mujoco.tasks.sampling import sample_box_pose

    np.random.seed(seed)
    object_pose = sample_box_pose()
    env.set_initial_object_pose(object_pose)
    ts = env.reset()
    if policy is not None:
        policy.reset()

    max_reward = 0.0
    t0 = time.time()

    for step in range(EPISODE_LEN):
        # ── render ──────────────────────────────────────────────────────────
        viewer.sync()

        # ── policy step ─────────────────────────────────────────────────────
        if policy is not None:
            obs = ts.observation
            policy_input = dict(obs)
            for cam in CAMERA_NAMES:
                if "images" in obs and cam in obs["images"]:
                    img = rearrange(
                        np.array(obs["images"][cam], dtype=np.float32) / 255.0,
                        "h w c -> c h w",
                    )
                    policy_input[f"image_{cam}"] = img
            action = policy.predict(policy_input)
        else:
            # no-policy mode: hold initial qpos
            action = ts.observation["qpos"].copy()

        ts = env.step(action)
        r = float(ts.reward) if ts.reward is not None else 0.0
        max_reward = max(max_reward, r)

        # ── real-time pacing ─────────────────────────────────────────────────
        if realtime:
            elapsed = time.time() - t0
            expected = (step + 1) * DT
            lag = expected - elapsed
            if lag > 0:
                time.sleep(lag)

    return max_reward


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt",      type=Path, default=None)
    parser.add_argument("--rollouts",  type=int,  default=3)
    parser.add_argument("--seed",      type=int,  default=1000)
    parser.add_argument("--no-policy", action="store_true", help="Show env without running the policy")
    parser.add_argument("--fast",      action="store_true", help="Run at max speed (no real-time pacing)")
    args = parser.parse_args()

    # ── checkpoint ──────────────────────────────────────────────────────────
    ckpt_path = args.ckpt or DEFAULT_CKPT
    if not args.no_policy and not ckpt_path.exists():
        print(f"ERROR: checkpoint not found: {ckpt_path}")
        sys.exit(1)

    # ── env + viewer ────────────────────────────────────────────────────────
    import mujoco.viewer as mj_viewer

    from testbed.backends.mujoco.backend import MuJoCoSimBackend

    print(f"Loading environment: {TASK_NAME} / {EQUIPMENT_MODEL}")
    env = MuJoCoSimBackend(task_name=TASK_NAME, equipment_model=EQUIPMENT_MODEL)

    # Prime the env so physics is initialised before we ask for the model
    from testbed.backends.mujoco.tasks.sampling import sample_box_pose
    env.set_initial_object_pose(sample_box_pose())
    env.reset()

    # Grab the underlying mujoco.MjModel and MjData from the dm_control physics
    mj_model = env._env.physics.model.ptr
    mj_data  = env._env.physics.data.ptr

    policy = None if args.no_policy else load_policy(ckpt_path)

    print(f"\n{'='*55}")
    print("  MuJoCo interactive viewer — use mouse to orbit/zoom")
    print(f"  Running {args.rollouts} rollout(s), seed base={args.seed}")
    print(f"  Policy: {'DISABLED' if args.no_policy else ckpt_path.name}")
    print(f"  Speed:  {'max' if args.fast else 'real-time (50 Hz)'}")
    print(f"{'='*55}\n")

    # passive viewer: we drive the physics, viewer just renders
    with mj_viewer.launch_passive(mj_model, mj_data) as viewer:
        viewer.cam.distance = 1.8
        viewer.cam.azimuth  = 90
        viewer.cam.elevation = -20

        successes = 0
        for i in range(args.rollouts):
            print(f"Rollout {i+1}/{args.rollouts}  (seed {args.seed + i}) ...")
            max_r = watch_rollout(
                env, policy, seed=args.seed + i,
                viewer=viewer, realtime=not args.fast,
            )
            success = max_r >= ENV_MAX_REWARD
            if success:
                successes += 1
            status = "✓ SUCCESS" if success else f"✗ failed  (max_reward={max_r:.1f})"
            print(f"  → {status}")

            if i < args.rollouts - 1:
                print("  Resetting in 1 s ...")
                for _ in range(50):          # ~1 s pause between rollouts
                    viewer.sync()
                    time.sleep(0.02)

        print(f"\nDone — {successes}/{args.rollouts} successes")


if __name__ == "__main__":
    main()
