"""Restart Unity Play Mode, run AGX smoke, and optionally replay depth QC."""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UNITY_PROJECT = Path("/home/pingfan/AGXUnityE85ExcavatorSim")
DEFAULT_STATUS_RELATIVE = Path("Temp/CodexPlayModeBootstrap/status.json")
DEFAULT_REQUEST_RELATIVE = Path("Temp/CodexPlayModeBootstrap.request")
UNITY_EXECUTE_METHOD = (
    "AGXUnity_Excavator.Scripts.Editor.CodexPlayModeBootstrap.RunFromCommandLine"
)
REMOVED_DEPTH_SLICE = slice(39, 45)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-unity-restart-smoke",
        description=(
            "Restart Unity Play Mode through Editor automation, run strict "
            "step-ack smoke, and optionally replay a few episodes with "
            "removed-depth QC."
        ),
    )
    parser.add_argument(
        "--unity-project",
        type=Path,
        default=DEFAULT_UNITY_PROJECT,
        help="Unity project directory.",
    )
    parser.add_argument(
        "--unity-editor",
        type=Path,
        default=None,
        help="Unity editor executable. Defaults to UNITY_EDITOR or common Unity paths.",
    )
    parser.add_argument(
        "--trigger",
        choices=("auto", "request-file", "execute-method"),
        default="auto",
        help=(
            "How to trigger Unity automation. request-file is for an already "
            "open Editor; execute-method launches Unity and leaves Play Mode running."
        ),
    )
    parser.add_argument(
        "--status-path",
        type=Path,
        default=None,
        help="Status JSON path written by Unity automation.",
    )
    parser.add_argument("--timeout-sec", type=float, default=300.0)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5057)
    parser.add_argument("--smoke-steps", type=int, default=500)
    parser.add_argument("--smoke-timeout", type=float, default=5.0)
    parser.add_argument("--no-strict", action="store_true")
    parser.add_argument(
        "--replay-episode",
        type=Path,
        action="append",
        default=[],
        help="Episode file or directory to replay after smoke. May be repeated.",
    )
    parser.add_argument(
        "--max-replay-episodes",
        type=int,
        default=2,
        help="Max episode files selected across replay inputs.",
    )
    parser.add_argument(
        "--replay-config",
        type=Path,
        default=None,
        help="Teleop config passed to tb-replay.",
    )
    parser.add_argument(
        "--record-output-dir",
        type=Path,
        default=None,
        help="Output directory for refreshed HDF5 episodes.",
    )
    parser.add_argument(
        "--post-tail-steps",
        type=int,
        default=None,
        help="Optional tb-replay --post-tail-steps override.",
    )
    parser.add_argument(
        "--replay-diagnostic-dir",
        type=Path,
        default=None,
        help="Optional directory for per-episode tb-replay JSONL diagnostics.",
    )
    parser.add_argument(
        "--replay-diagnostic-every",
        type=int,
        default=1,
        help="Forwarded to tb-replay --diagnostic-every when diagnostics are enabled.",
    )
    parser.add_argument(
        "--replay-diagnostic-error-threshold",
        type=float,
        default=0.02,
        help="Forwarded to tb-replay --diagnostic-error-threshold.",
    )
    parser.add_argument(
        "--replay-diagnostic-jump-threshold",
        type=float,
        default=0.05,
        help="Forwarded to tb-replay --diagnostic-jump-threshold.",
    )
    parser.add_argument(
        "--replay-realign-on-qpos-error",
        action="store_true",
        help="Forward tb-replay --realign-on-qpos-error.",
    )
    parser.add_argument(
        "--replay-realign-error-threshold",
        type=float,
        default=0.04,
        help="Forwarded to tb-replay --realign-error-threshold.",
    )
    parser.add_argument(
        "--replay-realign-axis",
        choices=("swing", "all"),
        default="all",
        help="Forwarded to tb-replay --realign-axis.",
    )
    parser.add_argument(
        "--replay-realign-hold-steps",
        type=int,
        default=3,
        help="Forwarded to tb-replay --realign-hold-steps.",
    )
    parser.add_argument(
        "--replay-realign-min-steps-between",
        type=int,
        default=200,
        help="Forwarded to tb-replay --realign-min-steps-between.",
    )
    parser.add_argument(
        "--replay-realign-burn-in-steps",
        type=int,
        default=15,
        help="Forwarded to tb-replay --realign-burn-in-steps.",
    )
    parser.add_argument(
        "--replay-realign-max-count",
        type=int,
        default=20,
        help="Forwarded to tb-replay --realign-max-count.",
    )
    parser.add_argument(
        "--check-removed-depth",
        action="store_true",
        help="Fail unless refreshed HDF5 env_state[:,39:45] changes.",
    )
    parser.add_argument("--depth-min-delta", type=float, default=1.0e-4)
    args = parser.parse_args()

    unity_project = args.unity_project.expanduser().resolve()
    status_path = _resolve_status_path(unity_project, args.status_path)
    before_recorded = _snapshot_recorded_outputs(args.record_output_dir)

    _run_unity_bootstrap(
        unity_project=unity_project,
        unity_editor=args.unity_editor,
        trigger=args.trigger,
        status_path=status_path,
        timeout_sec=args.timeout_sec,
    )
    _run_agx_smoke(
        host=args.host,
        port=args.port,
        steps=args.smoke_steps,
        timeout=args.smoke_timeout,
        strict=not args.no_strict,
    )

    replay_inputs = [path.expanduser().resolve() for path in args.replay_episode]
    if replay_inputs:
        if args.record_output_dir is None:
            raise SystemExit("--record-output-dir is required when --replay-episode is set")
        _run_replays(
            replay_inputs=replay_inputs,
            max_episodes=args.max_replay_episodes,
            replay_config=args.replay_config,
            record_output_dir=args.record_output_dir,
            post_tail_steps=args.post_tail_steps,
            replay_diagnostic_dir=args.replay_diagnostic_dir,
            replay_diagnostic_every=args.replay_diagnostic_every,
            replay_diagnostic_error_threshold=args.replay_diagnostic_error_threshold,
            replay_diagnostic_jump_threshold=args.replay_diagnostic_jump_threshold,
            replay_realign_on_qpos_error=args.replay_realign_on_qpos_error,
            replay_realign_error_threshold=args.replay_realign_error_threshold,
            replay_realign_axis=args.replay_realign_axis,
            replay_realign_hold_steps=args.replay_realign_hold_steps,
            replay_realign_min_steps_between=args.replay_realign_min_steps_between,
            replay_realign_burn_in_steps=args.replay_realign_burn_in_steps,
            replay_realign_max_count=args.replay_realign_max_count,
        )

    if args.check_removed_depth:
        if args.record_output_dir is None:
            raise SystemExit(
                "--record-output-dir is required when --check-removed-depth is set"
            )
        recorded = _new_recorded_outputs(args.record_output_dir, before_recorded)
        if not recorded:
            recorded = _resolve_episode_files(args.record_output_dir, args.max_replay_episodes)
        _check_removed_depth(
            recorded,
            min_delta=args.depth_min_delta,
        )

    print("PASS Unity automation, strict smoke, and requested replay/depth gates passed.")


def _run_unity_bootstrap(
    *,
    unity_project: Path,
    unity_editor: Path | None,
    trigger: str,
    status_path: Path,
    timeout_sec: float,
) -> None:
    if not unity_project.exists():
        raise SystemExit(f"Unity project not found: {unity_project}")

    if status_path.exists():
        status_path.unlink()

    selected_trigger = trigger
    if selected_trigger == "auto":
        selected_trigger = (
            "request-file" if _unity_editor_is_open(unity_project) else "execute-method"
        )

    process: subprocess.Popen[str] | None = None
    if selected_trigger == "request-file":
        _write_request_file(
            unity_project=unity_project,
            status_path=status_path,
            timeout_sec=timeout_sec,
        )
        print(f"Unity automation requested through {DEFAULT_REQUEST_RELATIVE}")
    else:
        editor = _resolve_unity_editor(unity_editor)
        log_path = unity_project / "Temp/CodexPlayModeBootstrap/unity_restart.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(editor),
            "-projectPath",
            str(unity_project),
            "-executeMethod",
            UNITY_EXECUTE_METHOD,
            "-codexStatusPath",
            str(status_path),
            "-codexTimeoutSec",
            f"{timeout_sec:.1f}",
            "-logFile",
            str(log_path),
        ]
        print(f"Launching Unity automation: {' '.join(command)}")
        process = subprocess.Popen(
            command,
            cwd=unity_project,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            text=True,
        )

    status = _wait_for_unity_status(
        status_path=status_path,
        timeout_sec=timeout_sec,
        process=process,
    )
    print(
        "Unity automation PASS "
        f"phase={status.get('phase', '')} "
        f"elapsed={float(status.get('elapsed_sec', 0.0)):.1f}s "
        f"message={status.get('message', '')}"
    )


def _write_request_file(
    *,
    unity_project: Path,
    status_path: Path,
    timeout_sec: float,
) -> None:
    request_path = unity_project / DEFAULT_REQUEST_RELATIVE
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request = {
        "status_path": str(status_path),
        "timeout_sec": float(timeout_sec),
    }
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")


def _wait_for_unity_status(
    *,
    status_path: Path,
    timeout_sec: float,
    process: subprocess.Popen[str] | None,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last_status: dict[str, Any] | None = None
    last_printed_phase = ""

    while time.monotonic() < deadline:
        status = _read_json_if_ready(status_path)
        if status is not None:
            last_status = status
            phase = str(status.get("phase", ""))
            if phase != last_printed_phase:
                print(
                    "Unity automation "
                    f"phase={phase} message={status.get('message', '')}"
                )
                last_printed_phase = phase

            if bool(status.get("complete", False)):
                if bool(status.get("success", False)):
                    return status
                raise SystemExit(
                    "Unity automation failed: "
                    f"phase={phase} message={status.get('message', '')}"
                )

        if process is not None and process.poll() is not None:
            raise SystemExit(
                "Unity automation process exited before success. "
                f"returncode={process.returncode}"
            )

        time.sleep(0.5)

    raise SystemExit(
        "Unity automation timed out waiting for status completion. "
        f"last_status={last_status}"
    )


def _run_agx_smoke(
    *,
    host: str,
    port: int,
    steps: int,
    timeout: float,
    strict: bool,
) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts/agx_smoke.py"),
        "--host",
        host,
        "--port",
        str(port),
        "--steps",
        str(steps),
        "--timeout",
        str(timeout),
    ]
    if strict:
        command.append("--strict")
    _run_checked(command, cwd=ROOT, label="agx_smoke")


def _run_replays(
    *,
    replay_inputs: list[Path],
    max_episodes: int,
    replay_config: Path | None,
    record_output_dir: Path,
    post_tail_steps: int | None,
    replay_diagnostic_dir: Path | None,
    replay_diagnostic_every: int,
    replay_diagnostic_error_threshold: float,
    replay_diagnostic_jump_threshold: float,
    replay_realign_on_qpos_error: bool,
    replay_realign_error_threshold: float,
    replay_realign_axis: str,
    replay_realign_hold_steps: int,
    replay_realign_min_steps_between: int,
    replay_realign_burn_in_steps: int,
    replay_realign_max_count: int,
) -> None:
    episodes: list[Path] = []
    for replay_input in replay_inputs:
        episodes.extend(_resolve_episode_files(replay_input, max_episodes))
        if len(episodes) >= max_episodes:
            break
    episodes = episodes[: max(0, max_episodes)]
    if not episodes:
        raise SystemExit(f"No replay episodes found in: {replay_inputs}")

    if replay_diagnostic_dir is not None:
        replay_diagnostic_dir.mkdir(parents=True, exist_ok=True)

    for episode in episodes:
        command = [
            sys.executable,
            "-m",
            "testbed.cli.replay",
            "--episode",
            str(episode),
            "--record-output-dir",
            str(record_output_dir),
        ]
        if replay_config is not None:
            command.extend(["--config", str(replay_config)])
        if post_tail_steps is not None:
            command.extend(["--post-tail-steps", str(post_tail_steps)])
        if replay_realign_on_qpos_error:
            command.extend(
                [
                    "--realign-on-qpos-error",
                    "--realign-error-threshold",
                    str(float(replay_realign_error_threshold)),
                    "--realign-axis",
                    str(replay_realign_axis),
                    "--realign-hold-steps",
                    str(max(1, int(replay_realign_hold_steps))),
                    "--realign-min-steps-between",
                    str(max(0, int(replay_realign_min_steps_between))),
                    "--realign-burn-in-steps",
                    str(max(0, int(replay_realign_burn_in_steps))),
                    "--realign-max-count",
                    str(max(0, int(replay_realign_max_count))),
                ]
            )
        if replay_diagnostic_dir is not None:
            diagnostic_path = replay_diagnostic_dir / f"{episode.stem}_diagnostics.jsonl"
            command.extend(
                [
                    "--diagnostic-log",
                    str(diagnostic_path),
                    "--diagnostic-every",
                    str(max(0, int(replay_diagnostic_every))),
                    "--diagnostic-error-threshold",
                    str(float(replay_diagnostic_error_threshold)),
                    "--diagnostic-jump-threshold",
                    str(float(replay_diagnostic_jump_threshold)),
                ]
            )
        _run_checked(command, cwd=ROOT, label=f"tb-replay:{episode.name}")


def _check_removed_depth(episodes: list[Path], *, min_delta: float) -> None:
    if not episodes:
        raise SystemExit("No refreshed episodes available for removed-depth QC")

    from testbed.data.hdf5_io import read_episode

    summaries: list[str] = []
    passed = False
    for episode in episodes:
        data = read_episode(episode, load_images=False)
        env_state = data.get("env_state")
        if env_state is None:
            summaries.append(f"{episode.name}: missing env_state")
            continue

        arr = np.asarray(env_state, dtype=np.float32)
        if arr.ndim != 2 or arr.shape[1] < REMOVED_DEPTH_SLICE.stop:
            summaries.append(f"{episode.name}: env_state shape={arr.shape}")
            continue

        depth = arr[:, REMOVED_DEPTH_SLICE]
        if not np.all(np.isfinite(depth)):
            summaries.append(f"{episode.name}: removed-depth contains NaN/Inf")
            continue

        peak_abs = float(np.max(np.abs(depth))) if depth.size else 0.0
        peak_delta = float(np.max(np.ptp(depth, axis=0))) if depth.size else 0.0
        summaries.append(
            f"{episode.name}: peak_abs={peak_abs:.6f} peak_delta={peak_delta:.6f}"
        )
        passed = passed or peak_delta >= min_delta

    print("Removed-depth QC:")
    for summary in summaries:
        print(f"  {summary}")

    if not passed:
        raise SystemExit(
            "removed-depth QC failed: env_state[:,39:45] did not change by "
            f">= {min_delta:g}"
        )


def _run_checked(command: list[str], *, cwd: Path, label: str) -> None:
    print(f"Running {label}: {' '.join(command)}")
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"{label} failed with return code {completed.returncode}")


def _resolve_status_path(unity_project: Path, status_path: Path | None) -> Path:
    if status_path is None:
        return (unity_project / DEFAULT_STATUS_RELATIVE).resolve()
    status_path = status_path.expanduser()
    return status_path.resolve() if status_path.is_absolute() else (ROOT / status_path).resolve()


def _unity_editor_is_open(unity_project: Path) -> bool:
    return (unity_project / "Temp/UnityLockfile").exists()


def _resolve_unity_editor(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    env_path = os.environ.get("UNITY_EDITOR")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    for executable in ("unity-editor", "Unity"):
        found = shutil.which(executable)
        if found:
            candidates.append(Path(found))
    for pattern in (
        "~/Unity/Hub/Editor/*/Editor/Unity",
        "/home/pingfan/Unity/Hub/Editor/*/Editor/Unity",
        "/opt/Unity/Hub/Editor/*/Editor/Unity",
        "/opt/unity/Editor/Unity",
        "/opt/Unity/Editor/Unity",
    ):
        candidates.extend(Path(path) for path in sorted(glob.glob(os.path.expanduser(pattern))))

    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate.resolve()

    raise SystemExit(
        "Unity editor executable not found. Pass --unity-editor or set UNITY_EDITOR."
    )


def _snapshot_recorded_outputs(record_output_dir: Path | None) -> set[Path]:
    if record_output_dir is None or not record_output_dir.exists():
        return set()
    return {path.resolve() for path in record_output_dir.glob("*.hdf5")}


def _new_recorded_outputs(record_output_dir: Path, before: set[Path]) -> list[Path]:
    if not record_output_dir.exists():
        return []
    after = {path.resolve() for path in record_output_dir.glob("*.hdf5")}
    return sorted(after - before, key=_episode_sort_key)


def _resolve_episode_files(path: Path, limit: int) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        episodes = sorted(path.glob("episode_*.hdf5"), key=_episode_sort_key)
        if not episodes:
            episodes = sorted(path.glob("*.hdf5"), key=_episode_sort_key)
        return episodes[: max(0, limit)]
    return []


def _episode_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"episode_(\d+)", path.stem)
    return (int(match.group(1)), path.stem) if match else (999999, path.stem)


def _read_json_if_ready(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


if __name__ == "__main__":
    main()
