"""CLI for the two-factor return boom causal diagnostic."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from testbed.eval.return_boom_causal_diagnostic import (
    build_expert_action_support_audit,
    collect_unity_boom_actuator_response,
    write_causal_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a failed return state with strict-18 expert actions, "
            "collect no-ACT Unity boom pulses, and combine the evidence."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    expert = commands.add_parser("expert")
    expert.add_argument("--rollout", type=Path, required=True)
    expert.add_argument("--anchor-step-id", type=int, required=True)
    expert.add_argument("--handoff-audit", type=Path, required=True)
    expert.add_argument("--return-primitives-dir", type=Path, required=True)
    expert.add_argument("--output", type=Path, required=True)
    expert.add_argument("--continuation-steps", type=int, default=10)

    unity = commands.add_parser("unity")
    unity.add_argument("--host", default="127.0.0.1")
    unity.add_argument("--port", type=int, default=5057)
    unity.add_argument(
        "--pose",
        action="append",
        nargs=5,
        metavar=("POSE_ID", "SWING", "BOOM", "STICK", "BUCKET"),
        required=True,
        help=(
            "Repeat for each normalized qpos pose. Unity reaches each pose "
            "through small production-controller actions, without REALIGN."
        ),
    )
    unity.add_argument("--command-amplitude", type=float, default=0.10)
    unity.add_argument("--pulse-steps", type=int, default=20)
    unity.add_argument("--settle-steps", type=int, default=30)
    unity.add_argument("--neutral-steps", type=int, default=30)
    unity.add_argument("--pose-prepare-action-limit", type=float, default=0.20)
    unity.add_argument("--pose-prepare-gain", type=float, default=2.0)
    unity.add_argument("--pose-prepare-max-steps", type=int, default=900)
    unity.add_argument("--pose-prepare-tolerance", type=float, default=0.003)
    unity.add_argument("--timeout", type=float, default=10.0)
    unity.add_argument(
        "--expected-positive-command-qpos-sign",
        type=int,
        choices=(-1, 1),
        default=-1,
    )
    unity.add_argument("--maximum-gain-ratio", type=float, default=2.0)
    unity.add_argument("--output", type=Path, required=True)

    report = commands.add_parser("report")
    report.add_argument("--expert-audit", type=Path, required=True)
    report.add_argument("--actuator-audit", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    return parser


def _poses(values: list[list[str]]) -> list[dict[str, Any]]:
    result = []
    for row in values:
        pose_id, *coordinates = row
        result.append(
            {
                "pose_id": pose_id,
                "qpos": [float(value) for value in coordinates],
            }
        )
    return result


def main() -> None:
    args = _parser().parse_args()
    if args.command == "expert":
        output = build_expert_action_support_audit(
            rollout_path=args.rollout,
            anchor_step_id=args.anchor_step_id,
            handoff_audit_path=args.handoff_audit,
            return_primitives_dir=args.return_primitives_dir,
            output_path=args.output,
            continuation_steps=args.continuation_steps,
        )
    elif args.command == "unity":
        output = collect_unity_boom_actuator_response(
            host=args.host,
            port=args.port,
            poses=_poses(args.pose),
            output_path=args.output,
            command_amplitude=args.command_amplitude,
            pulse_steps=args.pulse_steps,
            settle_steps=args.settle_steps,
            neutral_steps=args.neutral_steps,
            pose_prepare_action_limit=args.pose_prepare_action_limit,
            pose_prepare_gain=args.pose_prepare_gain,
            pose_prepare_max_steps=args.pose_prepare_max_steps,
            pose_prepare_tolerance=args.pose_prepare_tolerance,
            timeout_s=args.timeout,
            expected_positive_command_qpos_sign=(
                args.expected_positive_command_qpos_sign
            ),
            maximum_gain_ratio=args.maximum_gain_ratio,
        )
    else:
        output = write_causal_report(
            expert_audit_path=args.expert_audit,
            actuator_audit_path=args.actuator_audit,
            output_path=args.output,
        )
    print(output)


if __name__ == "__main__":
    main()
