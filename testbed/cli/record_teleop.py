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
Discard episode: press Backspace before saving (episode not counted).
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
    ATTR_DIG_AREA_PRESET_ID,
    ATTR_DUMP_AREA_PRESET_ID,
    ATTR_DT,
    ATTR_EPISODE_ID,
    ATTR_ENV_STATE_CONTRACT_VERSION,
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
    ATTR_STOP_REASON,
    ATTR_TASK_NAME,
    ATTR_TELEOP_INPUT,
    ATTR_CONTROL_HZ,
    ATTR_TARGET_DUMP_COUNT,
    ATTR_OPERATOR_ID,
    ATTR_OPERATOR_NOTES,
    ATTR_OBSERVER_NOTES,
    ATTR_RECORDING_MODE,
    ATTR_RECORDING_PROTOCOL_VERSION,
    ATTR_SCENARIO_ID,
    ATTR_SCENE_VERSION,
    ATTR_SOIL_PRESET_ID,
    ATTR_TARGET_DEPTH_M,
    ATTR_TASK_GOAL_DESCRIPTION,
    ATTR_WARMUP_OR_TRAIN,
)
from testbed.data.v2_1 import (
    GOAL_TOKEN_VERSION,
    PHASE_VERSION,
    build_v2_1_metadata_attrs,
)
from testbed.planner.boundary_detector import build_boundary_detector_from_config
from testbed.cli.graph_session_paths import (
    default_depth_snapshot_root_base,
    depth_snapshot_dir_for_session,
    teleop_dir_for_session,
)

log = logging.getLogger(__name__)

STOP_MODE_TASK_SUCCESS_TAIL = "task_success_tail"
STOP_MODE_TARGET_DUMP_COUNT = "target_dump_count"


def _action_control_flags(ainfo) -> tuple[bool, bool, bool, bool]:
    extras = getattr(ainfo, "extras", {}) or {}
    return (
        bool(extras.get("reset_requested", False)),
        bool(extras.get("discard_requested", False)),
        bool(extras.get("save_episode_requested", False)),
        bool(extras.get("quit_requested", False)),
    )


def _advance_success_stop_state(
    *,
    episode_success: bool,
    stop_on_success: bool,
    just_reached_success: bool,
    post_success_tail_steps: int,
    post_success_tail_remaining: int | None,
) -> tuple[bool, int | None]:
    if not stop_on_success:
        return False, None

    if just_reached_success:
        post_success_tail_remaining = max(0, int(post_success_tail_steps))
        if post_success_tail_remaining == 0:
            return True, 0
        return False, post_success_tail_remaining

    if not episode_success:
        return False, post_success_tail_remaining

    if post_success_tail_remaining is None:
        return True, None

    if post_success_tail_remaining <= 0:
        return True, 0

    post_success_tail_remaining -= 1
    if post_success_tail_remaining <= 0:
        return True, 0
    return False, post_success_tail_remaining


def _resolve_stop_mode(teleop_cfg: dict) -> str:
    stop_mode = str(teleop_cfg.get("stop_mode", "")).strip()
    if stop_mode:
        return stop_mode
    if bool(teleop_cfg.get("stop_on_success", True)):
        return STOP_MODE_TASK_SUCCESS_TAIL
    return "none"


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
    parser.add_argument("--graph-session", type=str, default=None,
                        help="Convenience session id for graph smoke collection. Derives teleop/depth output paths and enables depth capture.")
    parser.add_argument("--depth-capture", action="store_true",
                        help="Ask Unity to start/stop depth sequence capture around each episode.")
    parser.add_argument("--depth-capture-hz", type=float, default=1.0,
                        help="Unity depth sequence capture frequency in Hz.")
    parser.add_argument("--depth-capture-root", type=Path, default=None,
                        help="Base Unity depth JSON root. With --graph-session, output dir becomes <root>/<session>.")
    parser.add_argument("--depth-capture-output-dir", type=str, default=None,
                        help="Unity-side depth JSON output directory. Omit to derive from --graph-session or keep Unity Inspector setting.")
    parser.add_argument("--depth-capture-session-id", type=str, default=None,
                        help="Optional Unity depth capture session id. Defaults to --session-id or metadata session_id.")
    args = parser.parse_args()

    # ── Load config ───────────────────────────────────────────────────────────
    with open(args.config) as f:
        cfg: dict = yaml.safe_load(f) or {}

    teleop_cfg = cfg.setdefault("teleop", {})
    task_cfg = cfg.setdefault("task", {})
    teleop_meta_cfg = teleop_cfg.setdefault("metadata", {})
    depth_capture_cfg = cfg.setdefault("depth_capture", {})
    graph_session = str(args.graph_session).strip() if args.graph_session else ""
    if graph_session:
        args.depth_capture = True
        if args.session_id is None:
            args.session_id = graph_session
        if args.output_dir is None:
            args.output_dir = teleop_dir_for_session(graph_session)
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
    stop_mode = _resolve_stop_mode(teleop_cfg)
    stop_on_success = bool(teleop_cfg.get("stop_on_success", True))
    post_success_tail_steps = int(teleop_cfg.get("post_success_tail_steps", 0))
    scenario_id = task_cfg.get("scenario_id")
    camera_names: list[str] = task_cfg.get("camera_names", ["fpv"])
    record_config_yaml = yaml.safe_dump(cfg, sort_keys=False)

    recording_mode = str(task_cfg.get("recording_mode", "")).strip()
    target_dump_count = int(teleop_cfg.get("target_dump_count", 3))
    manual_save_key = str(teleop_cfg.get("manual_save_key", "s")).strip()
    depth_capture_enabled = bool(args.depth_capture or depth_capture_cfg.get("enabled", False))
    depth_capture_hz = float(args.depth_capture_hz)
    configured_depth_root = (
        args.depth_capture_root
        if args.depth_capture_root is not None
        else depth_capture_cfg.get("snapshot_root")
    )
    depth_capture_output_dir = str(args.depth_capture_output_dir or "")
    depth_capture_session_id = (
        args.depth_capture_session_id
        if args.depth_capture_session_id is not None
        else str(teleop_meta_cfg.get("session_id", ""))
    )
    if depth_capture_enabled and not depth_capture_session_id:
        depth_capture_session_id = f"teleop_{int(time.time())}"
    if depth_capture_enabled and not depth_capture_output_dir and graph_session:
        depth_capture_output_dir = str(
            depth_snapshot_dir_for_session(
                graph_session,
                root=default_depth_snapshot_root_base(
                    configured_root=configured_depth_root
                ),
            )
        )

    if stop_mode not in (
        STOP_MODE_TASK_SUCCESS_TAIL,
        STOP_MODE_TARGET_DUMP_COUNT,
        "none",
    ):
        raise ValueError(
            f"Unsupported teleop.stop_mode {stop_mode!r}. Expected one of: "
            f"{STOP_MODE_TASK_SUCCESS_TAIL}, {STOP_MODE_TARGET_DUMP_COUNT}, none."
        )

    dump_boundary_detector = None
    if stop_mode == STOP_MODE_TARGET_DUMP_COUNT:
        dump_boundary_detector = build_boundary_detector_from_config(
            reward_cfg=reward_cfg,
            success_cfg=success_cfg,
        )

    log.info(
        (
            "Config: %d episodes → %s  max_steps=%d  input=%s  "
            "stop_mode=%s  stop_on_success=%s  post_success_tail_steps=%d  "
            "scenario_id=%s  recording_mode=%s  target_dump_count=%d"
        ),
        num_episodes,
        dataset_dir,
        max_steps,
        input_device,
        stop_mode,
        stop_on_success,
        post_success_tail_steps,
        "" if scenario_id is None else scenario_id,
        recording_mode,
        target_dump_count,
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
        scenario_id=None if scenario_id is None else str(scenario_id),
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
    depth_capture_active = False
    depth_capture_episode_idx = -1

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
            if depth_capture_enabled:
                backend.start_depth_capture(
                    session_id=depth_capture_session_id,
                    episode_index=episode_idx,
                    first_step_id=0,
                    capture_hz=depth_capture_hz,
                    control_hz=float(task_cfg.get("control_hz", info.control_hz)),
                    output_dir=depth_capture_output_dir,
                )
                depth_capture_active = True
                depth_capture_episode_idx = episode_idx
                log.info(
                    (
                        "Unity depth capture started: session_id=%s "
                        "episode_index=%d capture_hz=%.3f output_dir=%s"
                    ),
                    depth_capture_session_id,
                    episode_idx,
                    depth_capture_hz,
                    depth_capture_output_dir or "<unity-default>",
                )

            discard = False
            reset_requested = False
            episode_success = bool(ts.info.get("task_success", False))
            post_success_tail_remaining: int | None = None
            completed_dump_count = 0
            target_dump_count_reached = False
            stop_reason = ""
            if dump_boundary_detector is not None:
                dump_boundary_detector.reset()

            for local_step in range(max_steps):
                if _abort:
                    break

                # Check for quit / discard from keyboard
                discard, manual_save_now, quit_now = _check_pygame_events(
                    action_source,
                    manual_save_key=manual_save_key,
                )
                if quit_now:
                    _abort = True
                    break
                if manual_save_now:
                    stop_reason = "manual_episode_end"
                    log.info("Episode manual save requested by keyboard.")
                    break
                if discard:
                    log.info("Episode discarded by user.")
                    break

                obs    = ts.observation
                action, ainfo = action_source.next_action(obs)
                reset_now, discard_now, save_now, quit_now = _action_control_flags(ainfo)
                if quit_now:
                    _abort = True
                    break
                if save_now:
                    stop_reason = "manual_episode_end"
                    log.info("Episode manual save requested by joystick.")
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
                current_task_success = bool(ts_next.info.get("task_success", False))
                just_reached_success = (not episode_success) and current_task_success
                episode_success = episode_success or current_task_success
                ts = ts_next

                should_stop = False
                if stop_mode == STOP_MODE_TASK_SUCCESS_TAIL:
                    should_stop, post_success_tail_remaining = _advance_success_stop_state(
                        episode_success=episode_success,
                        stop_on_success=stop_on_success,
                        just_reached_success=just_reached_success,
                        post_success_tail_steps=post_success_tail_steps,
                        post_success_tail_remaining=post_success_tail_remaining,
                    )
                    if just_reached_success and stop_on_success and post_success_tail_steps > 0:
                        log.info(
                            (
                                "Episode reached task success at step %d; "
                                "recording %d additional tail steps before stopping."
                            ),
                            local_step + 1,
                            post_success_tail_steps,
                        )
                    elif just_reached_success and stop_on_success:
                        log.info(
                            "Episode reached task success at step %d and will end immediately.",
                            local_step + 1,
                        )
                    if should_stop and stop_on_success and post_success_tail_steps > 0:
                        stop_reason = STOP_MODE_TASK_SUCCESS_TAIL
                        log.info(
                            "Episode completed post-success tail and will stop at step %d.",
                            local_step + 1,
                        )
                    elif should_stop and stop_on_success:
                        stop_reason = STOP_MODE_TASK_SUCCESS_TAIL
                elif stop_mode == STOP_MODE_TARGET_DUMP_COUNT and dump_boundary_detector is not None:
                    dump_event = dump_boundary_detector.update(
                        env_state=ts.observation.get("env_state", np.zeros(9, dtype=np.float32)),
                        action=action,
                        qpos=ts.observation.get("qpos", np.zeros(4, dtype=np.float32)),
                        reward_phase=str(
                            ts.info.get("reward_phase", ts.observation.get("reward_phase", ""))
                        ),
                        task_step_successes=list(
                            ts.info.get(
                                "task_step_successes",
                                ts.observation.get("task_step_successes", []),
                            )
                        ),
                        task_metrics=dict(
                            ts.info.get("task_metrics", ts.observation.get("task_metrics", {}))
                        ),
                    )
                    completed_dump_count = dump_boundary_detector.completed_dump_count
                    if dump_event.dump_end:
                        log.info(
                            "Episode reached dump_end #%d at step %d.",
                            completed_dump_count,
                            local_step + 1,
                        )
                    target_reached_now = completed_dump_count >= target_dump_count
                    just_reached_target = bool(target_reached_now and not target_dump_count_reached)
                    target_dump_count_reached = target_dump_count_reached or target_reached_now
                    should_stop, post_success_tail_remaining = _advance_success_stop_state(
                        episode_success=target_dump_count_reached,
                        stop_on_success=True,
                        just_reached_success=just_reached_target,
                        post_success_tail_steps=post_success_tail_steps,
                        post_success_tail_remaining=post_success_tail_remaining,
                    )
                    if just_reached_target:
                        stop_reason = "target_dump_count_reached"
                        if post_success_tail_steps > 0:
                            log.info(
                                (
                                    "Episode reached target_dump_count=%d at step %d; "
                                    "recording %d additional tail steps before stopping."
                                ),
                                target_dump_count,
                                local_step + 1,
                                post_success_tail_steps,
                            )
                        else:
                            log.info(
                                "Episode reached target_dump_count=%d at step %d and will stop.",
                                target_dump_count,
                                local_step + 1,
                            )
                    if should_stop and target_dump_count_reached and post_success_tail_steps > 0:
                        log.info(
                            "Episode completed target_dump_count tail and will stop at step %d.",
                            local_step + 1,
                        )

                if should_stop:
                    break

                # Enforce control rate
                _sleep_to_rate(task_cfg.get("control_hz", 50))

            recorder.metadata["stop_mode"] = stop_mode
            if scenario_id is not None:
                recorder.metadata["scenario_id"] = str(scenario_id)
            if recording_mode:
                recorder.metadata[ATTR_RECORDING_MODE] = str(recording_mode)
            if stop_mode == STOP_MODE_TARGET_DUMP_COUNT:
                recorder.metadata[ATTR_TARGET_DUMP_COUNT] = int(target_dump_count)
                recorder.metadata["goal_token_version"] = GOAL_TOKEN_VERSION
                recorder.metadata["phase_version"] = PHASE_VERSION
                recorder.metadata["completed_dump_count"] = int(completed_dump_count)

            if not stop_reason and not discard and not _abort:
                stop_reason = "max_steps_reached"
                if stop_mode == STOP_MODE_TARGET_DUMP_COUNT:
                    log.warning(
                        (
                            "Episode reached max_steps=%d before target_dump_count=%d; "
                            "completed_dump_count=%d."
                        ),
                        max_steps,
                        target_dump_count,
                        completed_dump_count,
                    )
            if stop_reason:
                recorder.metadata[ATTR_STOP_REASON] = str(stop_reason)
            if depth_capture_enabled:
                recorder.metadata["depth_capture_enabled"] = True
                recorder.metadata["depth_capture_session_id"] = str(depth_capture_session_id)
                recorder.metadata["depth_capture_hz"] = float(depth_capture_hz)
                recorder.metadata["depth_capture_output_dir"] = str(depth_capture_output_dir)

            if depth_capture_active:
                try:
                    backend.stop_depth_capture()
                    log.info("Unity depth capture stopped for episode_%06d.", episode_idx)
                finally:
                    depth_capture_active = False

            if not discard and len(recorder) > 0:
                save_success = (
                    bool(stop_reason == "target_dump_count_reached")
                    if stop_mode == STOP_MODE_TARGET_DUMP_COUNT
                    else episode_success
                )
                path = recorder.save(success=save_success)
                log.info("Saved %d steps → %s", len(recorder), path)
                saved += 1
                episode_idx += 1
            elif discard:
                if reset_requested:
                    log.info("Discarded current partial episode and restarting from Unity reset.")
                # don't advance episode_idx

    finally:
        if depth_capture_active:
            try:
                backend.stop_depth_capture()
                log.info(
                    "Unity depth capture stopped during shutdown for episode_%06d.",
                    depth_capture_episode_idx,
                )
            except Exception as exc:
                log.warning("Failed to stop Unity depth capture during shutdown: %s", exc)
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


def _check_pygame_events(action_source, *, manual_save_key: str = "s") -> tuple[bool, bool, bool]:
    """
    Poll pygame events for session-level controls.

    Returns (discard_episode, manual_save_episode, quit_session).
    Works whether action_source is joystick or keyboard.
    Joystick button-driven controls are handled separately via ActionInfo.extras.
    """
    try:
        import pygame
        for event in pygame.event.get(pygame.QUIT):
            return False, True
        keys = pygame.key.get_pressed()
        if keys[pygame.K_q]:          # Q = end session
            return False, False, True
        if keys[pygame.K_d]:          # D = discard this episode
            return True, False, False
        save_key = _pygame_key_code(pygame, manual_save_key)
        if save_key is not None and keys[save_key]:
            return False, True, False
    except Exception:
        pass
    return False, False, False


def _pygame_key_code(pygame, key_name: str | None) -> int | None:
    if not key_name:
        return None
    key_name = str(key_name).strip().lower()
    if not key_name:
        return None
    if len(key_name) == 1:
        return getattr(pygame, f"K_{key_name}", None)
    return getattr(pygame, f"K_{key_name}", None)


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
    scenario_id = task_cfg.get("scenario_id")
    recording_mode = str(task_cfg.get("recording_mode", "")).strip()
    if scenario_id and recording_mode == "teleop_multi_raw":
        metadata.update(build_v2_1_metadata_attrs(scenario_id=str(scenario_id)))
        metadata[ATTR_RECORDING_MODE] = str(recording_mode)
        metadata[ATTR_TARGET_DUMP_COUNT] = int(teleop_cfg.get("target_dump_count", 3))
    elif scenario_id:
        metadata[ATTR_SCENARIO_ID] = str(scenario_id)

    metadata_cfg = teleop_cfg.get("metadata", {})
    if metadata_cfg.get("operator_id"):
        metadata[ATTR_OPERATOR_ID] = str(metadata_cfg["operator_id"])
    if metadata_cfg.get("session_id"):
        metadata[ATTR_SESSION_ID] = str(metadata_cfg["session_id"])
    if metadata_cfg.get("notes"):
        metadata[ATTR_NOTES] = str(metadata_cfg["notes"])
    for attr_name in (
        ATTR_SCENE_VERSION,
        ATTR_SOIL_PRESET_ID,
        ATTR_DIG_AREA_PRESET_ID,
        ATTR_DUMP_AREA_PRESET_ID,
        ATTR_TASK_GOAL_DESCRIPTION,
        ATTR_TARGET_DEPTH_M,
        ATTR_RECORDING_PROTOCOL_VERSION,
        ATTR_WARMUP_OR_TRAIN,
        ATTR_OPERATOR_NOTES,
        ATTR_OBSERVER_NOTES,
        ATTR_ENV_STATE_CONTRACT_VERSION,
        "offtarget_deposited_mass_source",
    ):
        if attr_name in metadata_cfg:
            metadata[attr_name] = metadata_cfg[attr_name]
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
