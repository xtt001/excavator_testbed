"""CLI for the bounded Strict-18 Return-only closed-loop probe."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.return_closed_loop_runtime import (
    DEFAULT_UNITY_REPO,
    build_current_return_closed_loop_runtime_lock,
    run_return_closed_loop_probe_from_files,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-return-closed-loop-probe",
        description=(
            "Run the frozen Return-only preflight. Motion remains disabled "
            "unless --execute is explicitly supplied."
        ),
    )
    parser.add_argument("--stage-a-v3-root", type=Path, required=True)
    parser.add_argument("--return-training-config", type=Path, required=True)
    parser.add_argument("--runtime-lock", type=Path, required=True)
    parser.add_argument("--return-validation", type=Path)
    parser.add_argument("--unity-repo", type=Path, default=DEFAULT_UNITY_REPO)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5057)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Opt in to non-zero Return actions after the complete preflight.",
    )
    parser.add_argument(
        "--prepare-runtime-lock-only",
        action="store_true",
        help=(
            "Write a no-overwrite lock describing current capabilities and "
            "exit without connecting to Unity."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.prepare_runtime_lock_only:
        if args.return_validation is None:
            raise SystemExit(
                "--prepare-runtime-lock-only requires --return-validation"
            )
        lock = build_current_return_closed_loop_runtime_lock(
            stage_a_v3_root=args.stage_a_v3_root,
            return_validation_path=args.return_validation,
            unity_repo=args.unity_repo,
        )
        args.runtime_lock.parent.mkdir(parents=True, exist_ok=True)
        with args.runtime_lock.open("x", encoding="utf-8") as handle:
            json.dump(lock, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        print(
            json.dumps(
                {
                    "status": "runtime_lock_prepared",
                    "runtime_lock": str(args.runtime_lock.resolve()),
                    "execution_requested": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    result = run_return_closed_loop_probe_from_files(
        stage_a_v3_root=args.stage_a_v3_root,
        return_training_config_path=args.return_training_config,
        runtime_lock_path=args.runtime_lock,
        output_root=args.output_root,
        execute=bool(args.execute),
        device=str(args.device),
        host=str(args.host),
        port=int(args.port),
        timeout_s=float(args.timeout),
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "output_root": result["output_root"],
                "arm_count": result["arm_count"],
                "nonzero_action_count": result["nonzero_action_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] in {"preflight_passed", "completed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
