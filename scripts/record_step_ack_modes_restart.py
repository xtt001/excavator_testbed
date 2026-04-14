"""
record_step_ack_modes_restart.py -- Restart-based teleop comparison workflow.

This helper runs two separate `tb-record-teleop` sessions:

1. Update mode
2. FixedUpdate mode

Between the two runs, the operator is asked to fully restart Unity/AGX and flip
`AgxSimStepAckServer.m_useFixedUpdateForRequests` in the Inspector.

The script generates two temporary config files from one base teleop config so
that dataset paths, latency run IDs, and metadata stay separated.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def _mode_config(
    base_cfg: dict,
    *,
    mode_name: str,
    run_id: str,
    dataset_dir: str,
    latency_output_dir: str,
    num_episodes: int | None,
    input_device: str | None,
    notes_suffix: str,
    auto_export_on_close: bool,
) -> dict:
    cfg = copy.deepcopy(base_cfg)

    teleop_cfg = cfg.setdefault("teleop", {})
    metadata = teleop_cfg.setdefault("metadata", {})
    task_cfg = cfg.setdefault("task", {})
    latency_cfg = cfg.setdefault("latency", {})

    if num_episodes is not None:
        teleop_cfg["num_episodes"] = int(num_episodes)
    if input_device is not None:
        teleop_cfg["input"] = str(input_device)

    task_cfg["dataset_dir"] = dataset_dir

    session_id = metadata.get("session_id", "")
    if session_id:
        metadata["session_id"] = f"{session_id}_{mode_name}"
    else:
        metadata["session_id"] = run_id

    notes = str(metadata.get("notes", "")).strip()
    metadata["notes"] = (
        f"{notes} | {notes_suffix}".strip(" |") if notes else notes_suffix
    )

    latency_cfg["enabled"] = True
    latency_cfg["output_dir"] = latency_output_dir
    latency_cfg["run_id"] = run_id
    latency_cfg.setdefault("analysis", {})
    latency_cfg["analysis"]["auto_export_on_close"] = bool(auto_export_on_close)

    return cfg


def _run_record(config_path: Path) -> None:
    cmd = ["tb-record-teleop", "--config", str(config_path)]
    print(f"\n  Running: {' '.join(cmd)}\n")
    subprocess.run(cmd, check=True)


def _prompt(message: str) -> None:
    print(message)
    input("  Press Enter when ready... ")


def main() -> None:
    parser = argparse.ArgumentParser(prog="record-step-ack-modes-restart")
    parser.add_argument("--config", "-c", type=Path, required=True)
    parser.add_argument("--num-episodes", "-n", type=int, default=1)
    parser.add_argument("--input", choices=["joystick", "keyboard"], default=None)
    parser.add_argument(
        "--generated-config-dir",
        type=Path,
        default=Path("outputs/step_ack_mode_record/generated_configs"),
    )
    parser.add_argument(
        "--latency-output-dir",
        type=str,
        default="outputs/step_ack_mode_record",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("data/step_ack_mode_record"),
    )
    parser.add_argument("--update-run-id", type=str, default="teleop_update_restart")
    parser.add_argument(
        "--fixed-run-id", type=str, default="teleop_fixedupdate_restart"
    )
    args = parser.parse_args()

    base_cfg = _load_yaml(args.config)
    pandas_available = importlib.util.find_spec("pandas") is not None

    update_dataset_dir = str(args.dataset_root / "update")
    fixed_dataset_dir = str(args.dataset_root / "fixedupdate")

    update_cfg = _mode_config(
        base_cfg,
        mode_name="update",
        run_id=args.update_run_id,
        dataset_dir=update_dataset_dir,
        latency_output_dir=args.latency_output_dir,
        num_episodes=args.num_episodes,
        input_device=args.input,
        notes_suffix="step-ack mode compare: Update, restart-before-run",
        auto_export_on_close=pandas_available,
    )
    fixed_cfg = _mode_config(
        base_cfg,
        mode_name="fixedupdate",
        run_id=args.fixed_run_id,
        dataset_dir=fixed_dataset_dir,
        latency_output_dir=args.latency_output_dir,
        num_episodes=args.num_episodes,
        input_device=args.input,
        notes_suffix="step-ack mode compare: FixedUpdate, restart-before-run",
        auto_export_on_close=pandas_available,
    )

    update_cfg_path = args.generated_config_dir / "update_record.yaml"
    fixed_cfg_path = args.generated_config_dir / "fixedupdate_record.yaml"
    _write_yaml(update_cfg_path, update_cfg)
    _write_yaml(fixed_cfg_path, fixed_cfg)

    print("\n" + "=" * 70)
    print("  RESTART-BASED TELEOP COMPARE: Update vs FixedUpdate")
    print("=" * 70)
    print(f"  Base config: {args.config}")
    print(f"  Update config: {update_cfg_path}")
    print(f"  FixedUpdate config: {fixed_cfg_path}")
    print(f"  Latency outputs: {args.latency_output_dir}")
    print(f"  Dataset root: {args.dataset_root}")
    if not pandas_available:
        print("  pandas not found -> auto-export summary/plots disabled for this run")

    _prompt(
        "\n  STEP 1\n"
        "  Fully start/restart Unity.\n"
        "  In Inspector set:\n"
        "    AgxSimStepAckServer.m_useFixedUpdateForRequests = FALSE\n"
        "  Enter Play mode and make sure the step-ack server is listening."
    )
    _run_record(update_cfg_path)

    _prompt(
        "\n  STEP 2\n"
        "  Fully stop Unity Play mode and restart Unity/AGX.\n"
        "  In Inspector set:\n"
        "    AgxSimStepAckServer.m_useFixedUpdateForRequests = TRUE\n"
        "  Enter Play mode again and make sure the step-ack server is listening."
    )
    _run_record(fixed_cfg_path)

    print("\n  Done. Compare these runs:")
    print(f"    Update trace dir:      {Path(args.latency_output_dir) / args.update_run_id}")
    print(f"    FixedUpdate trace dir: {Path(args.latency_output_dir) / args.fixed_run_id}")
    print(f"    Update dataset dir:      {update_dataset_dir}")
    print(f"    FixedUpdate dataset dir: {fixed_dataset_dir}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"\n  tb-record-teleop failed with exit code {exc.returncode}", file=sys.stderr)
        raise
