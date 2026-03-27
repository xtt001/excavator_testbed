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
  5. on task success / Q-key / max_steps reached → EpisodeRecorder.save()

Stop session:   Ctrl+C  (saves the current partial episode first).
Discard episode: press D key before saving (episode not counted).
Joystick reset: configured reset button discards the current partial episode
                and starts a fresh Unity reset on the next episode attempt.
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

from testbed.data.schema import (
    ATTR_ACTION_ORDER,
    ATTR_ACTION_SEMANTICS,
    ATTR_AXIS_MAP,
    ATTR_CAMERA_FPS,
    ATTR_CAMERA_HEIGHT,
    ATTR_CAMERA_NAMES,
    ATTR_CAMERA_ROW_ORDER,
    ATTR_CAMERA_WIDTH,
    ATTR_DEADZONE,
    ATTR_DT,
    ATTR_EPISODE_ID,
    ATTR_ENV_STATE_ORDER,
    ATTR_IMAGE_FORMAT,
    ATTR_INVERT,
    ATTR_JOYSTICK_IDS,
    ATTR_KEY_SPEED,
    ATTR_LIMIT,
    ATTR_NOTES,
    ATTR_PARAM_VERSION,
    ATTR_PROTOCOL_VERSION,
    ATTR_QPOS_ORDER,
    ATTR_QVEL_ORDER,
    ATTR_RECORD_CONFIG_PATH,
    ATTR_RECORD_CONFIG_YAML,
    ATTR_RESPONSE_PROFILE_ATTACK_RATE,
    ATTR_RESPONSE_PROFILE_ENABLED,
    ATTR_RESPONSE_PROFILE_EXPONENT,
    ATTR_RESPONSE_PROFILE_RECENTER_RATE,
    ATTR_RESPONSE_PROFILE_RELEASE_RATE,
    ATTR_SCALE,
    ATTR_SEED,
    ATTR_SESSION_ID,
    ATTR_SIM_BACKEND,
    ATTR_TASK_NAME,
    ATTR_TELEOP_INPUT,
    ATTR_CONTROL_HZ,
    ATTR_OPERATOR_ID,
)

log = logging.getLogger(__name__)


def _action_control_flags(ainfo) -> tuple[bool, bool, bool]:
    extras = getattr(ainfo, "extras", {}) or {}
    return (
        bool(extras.get("reset_requested", False)),
        bool(extras.get("discard_requested", False)),
        bool(extras.get("quit_requested", False)),
    )


def _should_stop_on_success(*, episode_success: bool, stop_on_success: bool) -> bool:
    return bool(stop_on_success and episode_success)


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
    parser.add_argument("--operator-id", type=str, default=None,
                        help="Optional operator ID saved into episode metadata.")
    parser.add_argument("--session-id", type=str, default=None,
                        help="Optional session ID saved into episode metadata.")
    parser.add_argument("--notes", type=str, default=None,
                        help="Optional notes saved into episode metadata.")
    args = parser.parse_args()

    # ── Load config ───────────────────────────────────────────────────────────
    with open(args.config) as f:
        cfg: dict = yaml.safe_load(f) or {}

    teleop_cfg = cfg.setdefault("teleop", {})
    task_cfg = cfg.setdefault("task", {})
    teleop_meta_cfg = teleop_cfg.setdefault("metadata", {})
    if args.num_episodes is not None:
        teleop_cfg["num_episodes"] = int(args.num_episodes)
    if args.output_dir is not None:
        task_cfg["dataset_dir"] = str(args.output_dir)
    if args.seed is not None:
        task_cfg["seed"] = int(args.seed)
    if args.input is not None:
        teleop_cfg["input"] = args.input
    if args.operator_id is not None:
        teleop_meta_cfg["operator_id"] = args.operator_id
    if args.session_id is not None:
        teleop_meta_cfg["session_id"] = args.session_id
    if args.notes is not None:
        teleop_meta_cfg["notes"] = args.notes

    agx_cfg    = cfg.get("agx", {})
    success_cfg = cfg.get("success", {})
    reward_cfg = cfg.get("reward", {})

    num_episodes = int(teleop_cfg.get("num_episodes", 10))
    dataset_dir  = Path(task_cfg.get("dataset_dir", "data/agx_teleop"))
    seed         = int(task_cfg.get("seed", -1))
    max_steps    = task_cfg.get("max_steps", 500)
    input_device = str(teleop_cfg.get("input", "joystick"))
    stop_on_success = bool(teleop_cfg.get("stop_on_success", True))
    camera_names: list[str] = task_cfg.get("camera_names", ["fpv"])
    record_config_yaml = yaml.safe_dump(cfg, sort_keys=False)

    log.info(
        "Config: %d episodes → %s  max_steps=%d  input=%s  stop_on_success=%s",
        num_episodes,
        dataset_dir,
        max_steps,
        input_device,
        stop_on_success,
    )

    # ── Build backend ─────────────────────────────────────────────────────────
    from testbed.backends.agx.backend import AGXSimBackend
    from testbed.tasks.logic.excavator_reward import (
        build_agx_excavation_mission_overrides,
    )

    reward_overrides = build_agx_excavation_mission_overrides(
        success_cfg=success_cfg,
        reward_cfg=reward_cfg,
    )
    backend = AGXSimBackend(
        host=agx_cfg.get("host", "127.0.0.1"),
        port=agx_cfg.get("port", 5057),
        timeout=agx_cfg.get("timeout", 10.0),
        reset_terrain=agx_cfg.get("reset_terrain", True),
        reset_pose=agx_cfg.get("reset_pose", True),
        task_name=task_cfg.get("task_name", "agx_excavation_teleop"),
        reward_overrides=reward_overrides,
    )
    info = backend.get_info()
    _validate_requested_cameras(info.camera_names, camera_names)

    # ── Build action source ───────────────────────────────────────────────────
    if input_device == "joystick":
        from testbed.actions.gamepad import JoystickActionSource
        action_source = JoystickActionSource.from_config(
            teleop_cfg.get("joystick", {}),
            default_dt=float(task_cfg.get("dt", info.dt)),
        )
    else:
        from testbed.actions.keyboard import KeyboardActionSource
        action_source = KeyboardActionSource.from_config(teleop_cfg.get("keyboard", {}))

    # ── Build metadata template ───────────────────────────────────────────────
    base_meta = _build_episode_metadata(
        info=info,
        task_cfg=task_cfg,
        teleop_cfg=teleop_cfg,
        input_device=input_device,
        camera_names=camera_names,
        config_path=args.config.resolve(),
        record_config_yaml=record_config_yaml,
    )

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
            meta[ATTR_SEED] = ep_seed
            meta[ATTR_EPISODE_ID] = f"episode_{episode_idx}"

            recorder = EpisodeRecorder(
                output_dir=dataset_dir,
                episode_idx=episode_idx,
                metadata=meta,
                camera_names=camera_names,
            )

            ts = backend.reset(seed=ep_seed)
            action_source.reset()

            discard = False
            reset_requested = False
            episode_success = bool(ts.info.get("task_success", False))

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
                reset_now, discard_now, quit_now = _action_control_flags(ainfo)
                if quit_now:
                    _abort = True
                    break
                if reset_now:
                    reset_requested = True
                    discard = True
                    log.info("Episode reset requested by joystick.")
                    break
                if discard_now:
                    discard = True
                    log.info("Episode discarded by joystick.")
                    break

                ts_next = backend.step(action)
                step_id = int(obs.get("step_id", local_step))

                recorder.record(
                    obs=obs,
                    action=action,
                    reward=ts_next.reward,
                    step_id=step_id,
                    step_ns=time.time_ns(),
                    action_src_type=ainfo.source_type,
                    action_src_id=ainfo.source_id,
                )
                episode_success = episode_success or bool(ts_next.info.get("task_success", False))
                ts = ts_next

                if _should_stop_on_success(
                    episode_success=episode_success,
                    stop_on_success=stop_on_success,
                ):
                    log.info(
                        "Episode reached task success at step %d and will end early.",
                        local_step + 1,
                    )
                    break

                # Enforce control rate
                _sleep_to_rate(task_cfg.get("control_hz", 50))

            if not discard and len(recorder) > 0:
                path = recorder.save(success=episode_success)
                log.info("Saved %d steps → %s", len(recorder), path)
                saved += 1
                episode_idx += 1
            elif discard:
                if reset_requested:
                    log.info("Discarded current partial episode and restarting from Unity reset.")
                # don't advance episode_idx

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
    Joystick button-driven controls are handled separately via ActionInfo.extras.
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


def _build_episode_metadata(
    *,
    info,
    task_cfg: dict,
    teleop_cfg: dict,
    input_device: str,
    camera_names: list[str],
    config_path: Path | None = None,
    record_config_yaml: str | None = None,
) -> dict:
    metadata: dict[str, object] = {
        ATTR_TASK_NAME: task_cfg.get("task_name", "agx_excavation_teleop"),
        ATTR_SIM_BACKEND: "agxunity",
        ATTR_CONTROL_HZ: int(round(float(info.control_hz))),
        ATTR_DT: float(info.dt),
        ATTR_ACTION_SEMANTICS: info.action_semantics,
        ATTR_CAMERA_NAMES: ",".join(camera_names),
        ATTR_IMAGE_FORMAT: info.cameras[0].pixel_format if info.cameras else "raw_rgb",
        ATTR_PARAM_VERSION: task_cfg.get("param_version", "v0"),
        ATTR_PROTOCOL_VERSION: info.protocol_version,
        ATTR_ACTION_ORDER: ",".join(info.action_order),
        ATTR_QPOS_ORDER: ",".join(info.qpos_order),
        ATTR_QVEL_ORDER: ",".join(info.qvel_order),
        ATTR_ENV_STATE_ORDER: ",".join(info.env_state_order),
        ATTR_TELEOP_INPUT: input_device,
    }

    metadata_cfg = teleop_cfg.get("metadata", {})
    if metadata_cfg.get("operator_id"):
        metadata[ATTR_OPERATOR_ID] = str(metadata_cfg["operator_id"])
    if metadata_cfg.get("session_id"):
        metadata[ATTR_SESSION_ID] = str(metadata_cfg["session_id"])
    if metadata_cfg.get("notes"):
        metadata[ATTR_NOTES] = str(metadata_cfg["notes"])
    if config_path is not None:
        metadata[ATTR_RECORD_CONFIG_PATH] = str(config_path)
    if record_config_yaml:
        metadata[ATTR_RECORD_CONFIG_YAML] = str(record_config_yaml)

    camera_by_name = {camera.name: camera for camera in info.cameras}
    if len(camera_names) == 1 and camera_names[0] in camera_by_name:
        camera = camera_by_name[camera_names[0]]
        metadata[ATTR_CAMERA_WIDTH] = int(camera.width)
        metadata[ATTR_CAMERA_HEIGHT] = int(camera.height)
        metadata[ATTR_CAMERA_FPS] = float(camera.fps)
        metadata[ATTR_CAMERA_ROW_ORDER] = camera.row_order

    if input_device == "joystick":
        joystick_cfg = teleop_cfg.get("joystick", {})
        metadata[ATTR_DEADZONE] = _broadcast_float_config(
            joystick_cfg.get("deadzone", 0.05)
        )
        metadata[ATTR_SCALE] = _broadcast_float_config(
            joystick_cfg.get("scale", 1.0)
        )
        metadata[ATTR_LIMIT] = np.full(4, float(joystick_cfg.get("clip", 1.0)), dtype=np.float32)
        metadata[ATTR_AXIS_MAP] = np.asarray(
            joystick_cfg.get("axis_map", [0, 1, 3, 4]),
            dtype=np.int32,
        )
        metadata[ATTR_JOYSTICK_IDS] = np.asarray(
            joystick_cfg.get("joystick_ids", [int(joystick_cfg.get("joystick_id", 0))] * 4),
            dtype=np.int32,
        )
        metadata[ATTR_INVERT] = np.asarray(
            joystick_cfg.get("invert", [False, True, False, True]),
            dtype=np.bool_,
        )
        response_profile_cfg = joystick_cfg.get("response_profile", {})
        if bool(response_profile_cfg.get("enabled", False)):
            metadata[ATTR_RESPONSE_PROFILE_ENABLED] = 1
            metadata[ATTR_RESPONSE_PROFILE_ATTACK_RATE] = _broadcast_float_config(
                response_profile_cfg.get("attack_rate", 4.0)
            )
            metadata[ATTR_RESPONSE_PROFILE_RELEASE_RATE] = _broadcast_float_config(
                response_profile_cfg.get("release_rate", 6.0)
            )
            metadata[ATTR_RESPONSE_PROFILE_RECENTER_RATE] = _broadcast_float_config(
                response_profile_cfg.get("recenter_rate", 7.0)
            )
            metadata[ATTR_RESPONSE_PROFILE_EXPONENT] = _broadcast_float_config(
                response_profile_cfg.get("exponent", 1.0)
            )
    else:
        keyboard_cfg = teleop_cfg.get("keyboard", {})
        metadata[ATTR_KEY_SPEED] = float(keyboard_cfg.get("key_speed", 0.5))

    return metadata


def _broadcast_float_config(value: float | list[float]) -> np.ndarray:
    if isinstance(value, (int, float)):
        return np.full(4, float(value), dtype=np.float32)
    return np.asarray(value, dtype=np.float32)


def _validate_requested_cameras(
    available_camera_names: tuple[str, ...],
    requested_camera_names: list[str],
) -> None:
    missing = sorted(set(requested_camera_names) - set(available_camera_names))
    if missing:
        raise KeyError(
            "Requested camera(s) not advertised by Unity GET_INFO: "
            + ", ".join(missing)
        )


if __name__ == "__main__":
    main()
