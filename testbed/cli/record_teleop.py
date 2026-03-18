"""
tb-record-teleop — Record expert teleop demos from AGXUnity to HDF5.

Usage
-----
    tb-record-teleop --config testbed/configs/teleop_v0.yaml
    tb-record-teleop --config testbed/configs/teleop_v0.yaml --num-episodes 20
    python -m testbed.cli.record_teleop --config testbed/configs/teleop_v0.yaml

Loop (per episode)
──────────────────
  1. AGXSimBackend.reset()           → first obs
  2. JoystickActionSource.next_action(obs) → action
  3. AGXSimBackend.step(action)      → next obs, reward
  4. EpisodeRecorder.record(obs, action, ...)
  5. on Q-key / max_steps reached → EpisodeRecorder.save()

Stop session:   Ctrl+C  (saves the current partial episode first).
Discard episode: press D key before saving (episode not counted).
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

import numpy as np
import yaml

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="tb-record-teleop",
        description="Record expert joystick demos from AGX → HDF5 (schema v1.1).",
    )
    parser.add_argument("--config", "-c", type=Path, required=True,
                        help="Path to teleop YAML config.")
    parser.add_argument("--num-episodes", "-n", type=int, default=None,
                        help="Override teleop.num_episodes from config.")
    parser.add_argument("--output-dir", "-o", type=Path, default=None,
                        help="Override teleop.dataset_dir from config.")
    parser.add_argument("--seed", type=int, default=None,
                        help="Override seed for all resets.")
    parser.add_argument("--input", choices=["joystick", "keyboard"], default=None,
                        help="Override teleop.input from config.")
    args = parser.parse_args()

    # ── Load config ───────────────────────────────────────────────────────────
    with open(args.config) as f:
        cfg: dict = yaml.safe_load(f) or {}

    agx_cfg    = cfg.get("agx", {})
    teleop_cfg = cfg.get("teleop", {})
    task_cfg   = cfg.get("task", {})

    num_episodes = args.num_episodes or teleop_cfg.get("num_episodes", 10)
    dataset_dir  = Path(args.output_dir or task_cfg.get("dataset_dir", "data/agx_teleop"))
    seed         = args.seed if args.seed is not None else task_cfg.get("seed", -1)
    max_steps    = task_cfg.get("max_steps", 500)
    input_device = args.input or teleop_cfg.get("input", "joystick")
    camera_names: list[str] = task_cfg.get("camera_names", ["fpv"])

    log.info("Config: %d episodes → %s  max_steps=%d  input=%s",
             num_episodes, dataset_dir, max_steps, input_device)

    # ── Build backend ─────────────────────────────────────────────────────────
    from testbed.backends.agx.backend import AGXSimBackend
    backend = AGXSimBackend(
        host=agx_cfg.get("host", "127.0.0.1"),
        port=agx_cfg.get("port", 9000),
        timeout=agx_cfg.get("timeout", 10.0),
    )

    # ── Build action source ───────────────────────────────────────────────────
    if input_device == "joystick":
        from testbed.actions.gamepad import JoystickActionSource
        action_source = JoystickActionSource.from_config(teleop_cfg.get("joystick", {}))
    else:
        from testbed.actions.keyboard import KeyboardActionSource
        action_source = KeyboardActionSource.from_config(teleop_cfg.get("keyboard", {}))

    # ── Build metadata template ───────────────────────────────────────────────
    base_meta = {
        "task_name":        task_cfg.get("task_name", "agx_excavation_teleop"),
        "sim_backend":      "agxunity",
        "control_hz":       task_cfg.get("control_hz", 50),
        "dt":               task_cfg.get("dt", 0.02),
        "action_semantics": "actuator_speed_cmd",
        "camera_names":     ",".join(camera_names),
        "image_format":     "raw_rgb",
        "param_version":    task_cfg.get("param_version", "v0"),
    }

    # ── Graceful shutdown on Ctrl+C ───────────────────────────────────────────
    _abort = False
    def _sigint(_s, _f):
        nonlocal _abort
        _abort = True
        log.warning("Ctrl+C received — will finish current episode then exit.")
    signal.signal(signal.SIGINT, _sigint)

    # ── Episode loop ──────────────────────────────────────────────────────────
    from testbed.data.recorder import EpisodeRecorder

    dataset_dir.mkdir(parents=True, exist_ok=True)
    episode_idx = _next_episode_idx(dataset_dir)
    saved = 0

    try:
        while saved < num_episodes and not _abort:
            log.info("─── Episode %d / %d ───", saved + 1, num_episodes)

            ep_seed = seed if seed >= 0 else int(time.time()) % (2**31)
            meta = dict(base_meta)
            meta["seed"] = ep_seed

            recorder = EpisodeRecorder(
                output_dir=dataset_dir,
                episode_idx=episode_idx,
                metadata=meta,
                camera_names=camera_names,
            )

            ts = backend.reset(seed=ep_seed)
            action_source.reset()

            discard = False

            for local_step in range(max_steps):
                if _abort:
                    break

                # Check for quit / discard from keyboard
                discard, quit_now = _check_pygame_events(action_source)
                if quit_now:
                    _abort = True
                    break
                if discard:
                    log.info("Episode discarded by user.")
                    break

                obs    = ts.observation
                action, ainfo = action_source.next_action(obs)

                ts = backend.step(action)
                step_id = ts.info.get("step_id", local_step)

                recorder.record(
                    obs=ts.observation,
                    action=action,
                    reward=ts.reward,
                    step_id=step_id,
                    step_ns=time.time_ns(),
                    action_src_type=ainfo.source_type,
                    action_src_id=ainfo.source_id,
                )

                # Enforce control rate
                _sleep_to_rate(task_cfg.get("control_hz", 50))

            if not discard and len(recorder) > 0:
                path = recorder.save(success=False)   # success determined by evaluator
                log.info("Saved %d steps → %s", len(recorder), path)
                saved += 1
                episode_idx += 1
            elif discard:
                pass  # don't advance episode_idx

    finally:
        backend.close()
        action_source.close()

    log.info("Session complete: %d / %d episodes saved to %s", saved, num_episodes, dataset_dir)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _next_episode_idx(dataset_dir: Path) -> int:
    """Find the next free episode index in dataset_dir."""
    existing = sorted(
        dataset_dir.glob("episode_*.hdf5"),
        key=lambda p: int(p.stem.split("_", 1)[1]),
    )
    if not existing:
        return 0
    return int(existing[-1].stem.split("_", 1)[1]) + 1


_last_step_time: float = 0.0

def _sleep_to_rate(control_hz: float) -> None:
    """Busy-spin / sleep to maintain the target control rate."""
    global _last_step_time
    target_dt = 1.0 / control_hz
    now = time.perf_counter()
    elapsed = now - _last_step_time
    if elapsed < target_dt:
        time.sleep(target_dt - elapsed)
    _last_step_time = time.perf_counter()


def _check_pygame_events(action_source) -> tuple[bool, bool]:
    """
    Poll pygame events for session-level controls.

    Returns (discard_episode, quit_session).
    Works whether action_source is joystick or keyboard.
    """
    try:
        import pygame
        for event in pygame.event.get(pygame.QUIT):
            return False, True
        keys = pygame.key.get_pressed()
        if keys[pygame.K_q]:          # Q = end session
            return False, True
        if keys[pygame.K_d]:          # D = discard this episode
            return True, False
    except Exception:
        pass
    return False, False


if __name__ == "__main__":
    main()
