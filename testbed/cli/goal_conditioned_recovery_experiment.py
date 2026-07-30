"""Prepare and collect the offline goal-conditioned recovery experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.goal_conditioned_recovery_experiment import (
    CONDITION_IDS,
    build_goal_conditioned_functional_config,
    build_goal_conditioned_recovery_preflight,
    collect_goal_conditioned_recovery_evidence,
    validate_goal_conditioned_functional_record,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tb-goal-conditioned-recovery-experiment",
        description=(
            "Build no-overwrite offline artifacts for the E0/G1/W1 "
            "goal-conditioned recovery experiment. This CLI never runs live."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser(
        "build-preflight",
        help="Build three request-local configs and offline preflight evidence.",
    )
    preflight.add_argument("--base-config", type=Path, required=True)
    preflight.add_argument("--condition-set", type=Path, required=True)
    preflight.add_argument("--output-root", type=Path, required=True)
    preflight.add_argument("--predictor-manifest", type=Path)
    preflight.add_argument("--exact-diagnostic-artifact", type=Path)
    preflight.add_argument("--exact-diagnostic-artifact-sha256")

    collect = subparsers.add_parser(
        "collect-evidence",
        help="Collect existing offline or completed three-way evidence.",
    )
    collect.add_argument("--experiment-manifest", type=Path, required=True)
    collect.add_argument("--output-dir", type=Path, required=True)
    collect.add_argument(
        "--live-record",
        action="append",
        default=[],
        metavar="CONDITION=PATH",
        help=(
            "Completed record; provide exactly E0_expert_goal, "
            "G1_planner_continuous_goal and W1_internal_wall_safe_goal, "
            "or omit all for an offline-only decision."
        ),
    )

    functional = subparsers.add_parser(
        "build-functional-config",
        help="Build the one-shot G1 A0 1x10 config after a passing decision.",
    )
    functional.add_argument("--causal-decision", type=Path, required=True)
    functional.add_argument("--output-dir", type=Path, required=True)

    validate = subparsers.add_parser(
        "validate-functional",
        help="Validate one completed goal-conditioned 1x10 record.",
    )
    validate.add_argument("--record", type=Path, required=True)
    validate.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "build-preflight":
        result = build_goal_conditioned_recovery_preflight(
            base_config_path=args.base_config,
            condition_set_path=args.condition_set,
            output_root=args.output_root,
            predictor_manifest_path=args.predictor_manifest,
            exact_diagnostic_artifact_path=(
                args.exact_diagnostic_artifact
            ),
            exact_diagnostic_artifact_sha256=(
                args.exact_diagnostic_artifact_sha256
            ),
        )
    elif args.command == "collect-evidence":
        result = collect_goal_conditioned_recovery_evidence(
            experiment_manifest_path=args.experiment_manifest,
            live_record_paths=_live_record_paths(
                args.live_record,
                parser=parser,
            ),
            output_dir=args.output_dir,
        )
    elif args.command == "build-functional-config":
        result = build_goal_conditioned_functional_config(
            causal_decision_path=args.causal_decision,
            output_dir=args.output_dir,
        )
    else:
        result = validate_goal_conditioned_functional_record(
            record_path=args.record,
            output_dir=args.output_dir,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


def _live_record_paths(
    values: list[str],
    *,
    parser: argparse.ArgumentParser,
) -> dict[str, Path] | None:
    if not values:
        return None
    parsed: dict[str, Path] = {}
    for value in values:
        condition_id, separator, raw_path = value.partition("=")
        if (
            not separator
            or condition_id not in CONDITION_IDS
            or not raw_path
            or condition_id in parsed
        ):
            parser.error(
                "--live-record must be a unique CONDITION=PATH for "
                f"{', '.join(CONDITION_IDS)}"
            )
        parsed[condition_id] = Path(raw_path)
    if set(parsed) != set(CONDITION_IDS):
        parser.error(
            "--live-record must provide all three conditions or none"
        )
    return parsed


if __name__ == "__main__":
    main()
