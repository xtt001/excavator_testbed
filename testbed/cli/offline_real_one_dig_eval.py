"""tb-offline-real-one-dig-eval - compare real one-dig expert and policy actions."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="tb-offline-real-one-dig-eval",
        description=(
            "Run a trained policy over recorded real one-dig episodes without "
            "sending commands to Unity or the real machine."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("testbed/configs/act_real_one_dig_v1_smoke.yaml"),
        help="Training/eval config used to locate dataset and checkpoint.",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Override task.dataset_dir from the config.",
    )
    parser.add_argument(
        "--ckpt-path",
        type=Path,
        default=None,
        help="Override eval.ckpt_path from the config.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/eval/real_one_dig_v1_offline"),
        help="Directory for overlay videos, action plots, metrics, and summary files.",
    )
    parser.add_argument(
        "--episode-ids",
        type=int,
        nargs="+",
        default=None,
        help="Evaluate only selected converted episode ids, e.g. 0 1 8.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Evaluate only the first N steps of each selected episode.",
    )
    parser.add_argument(
        "--camera",
        default="fpv",
        help="Camera name under observations/images. Default: fpv.",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Override policy device, e.g. cpu or cuda.",
    )
    parser.add_argument(
        "--temporal-agg",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override ACT temporal aggregation for offline prediction.",
    )
    parser.add_argument(
        "--action-threshold",
        type=float,
        default=0.05,
        help="Deadband threshold for active/idle metrics. Default: 0.05.",
    )
    args = parser.parse_args()

    config = _load_config(args.config)
    if args.dataset_dir is not None:
        config.setdefault("task", {})["dataset_dir"] = str(args.dataset_dir)
    if args.ckpt_path is not None:
        config.setdefault("eval", {})["ckpt_path"] = str(args.ckpt_path)
    if args.device is not None:
        config.setdefault("policy", {})["device"] = str(args.device)
    if args.temporal_agg is not None:
        config.setdefault("policy", {})["temporal_agg"] = bool(args.temporal_agg)
    config["offline_eval"] = {
        "dataset_dir": str(
            config.get("task", {}).get("dataset_dir", "data/real_one_dig_v1_windows")
        ),
        "ckpt_path": (
            str(args.ckpt_path)
            if args.ckpt_path is not None
            else config.get("eval", {}).get("ckpt_path")
        ),
        "output_dir": str(args.output_dir),
        "episode_ids": args.episode_ids,
        "max_steps": args.max_steps,
        "camera": args.camera,
        "device": args.device,
        "temporal_agg": args.temporal_agg,
        "action_threshold": float(args.action_threshold),
    }

    from testbed.eval.offline_imitation import (
        load_act_policy_from_config,
        run_offline_imitation_eval,
        write_resolved_offline_eval_config,
    )

    dataset_dir = Path(
        config.get("task", {}).get("dataset_dir", "data/real_one_dig_v1_windows")
    )
    policy = load_act_policy_from_config(
        config,
        ckpt_path=args.ckpt_path,
        device=args.device,
        temporal_agg=args.temporal_agg,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_resolved_offline_eval_config(config, args.output_dir)
    results = run_offline_imitation_eval(
        dataset_dir=dataset_dir,
        output_dir=args.output_dir,
        policy=policy,
        episode_ids=args.episode_ids,
        max_steps=args.max_steps,
        camera_name=args.camera,
        action_threshold=args.action_threshold,
    )

    log.info("Evaluated %d real one-dig episode(s).", len(results))
    for result in results:
        log.info(
            "episode_%d: T=%d mae=%.4f active_mae=%s sign_acc=%s",
            result.episode_id,
            result.steps,
            result.overall_mae,
            "n/a" if result.active_mae is None else f"{result.active_mae:.4f}",
            "n/a" if result.sign_accuracy is None else f"{result.sign_accuracy:.3f}",
        )
    log.info("Offline eval outputs written to %s", args.output_dir)


def _load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


if __name__ == "__main__":
    main()
