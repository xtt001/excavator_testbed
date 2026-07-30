"""CLI for the Strict-18 wall-contact diagnostic evidence lifecycle."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from typing import Any

from testbed.eval.wall_contact_ab_lineage import build_ab_lineage
from testbed.eval.wall_contact_semantics_experiment import (
    build_wall_contact_source_spec,
    collect_expert_geometry_evidence,
    collect_expert_replay_evidence,
    collect_paired_ab_evidence,
    finalize_wall_contact_semantics_experiment,
    initialize_wall_contact_semantics_experiment,
    prepare_wall_contact_semantics_experiment,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare and collect diagnostic-only Strict-18 wall-contact "
            "evidence; this command never runs live evaluation."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    initialize = commands.add_parser(
        "initialize",
        help="create the complete no-overwrite evidence root from sources",
    )
    initialize.add_argument("--rollout-jsonl", required=True)
    initialize.add_argument("--planner-trace", required=True)
    initialize.add_argument("--target-episode-id", default="episode_168")
    initialize.add_argument("--target-raw-fields-sha256", required=True)
    initialize.add_argument("--target-cycle-index", type=int, required=True)
    initialize.add_argument("--full-source-dir", required=True)
    initialize.add_argument("--split", required=True)
    initialize.add_argument("--dig-primitives-dir", required=True)
    initialize.add_argument("--execution-library", required=True)
    initialize.add_argument("--pose-library", required=True)
    initialize.add_argument("--legacy-sweep", required=True)
    initialize.add_argument("--unity-repo-root", required=True)
    initialize.add_argument(
        "--contact-monitor-code",
        action="append",
        required=True,
    )
    initialize.add_argument("--base-config", required=True)
    initialize.add_argument("--output-root", required=True)
    initialize.set_defaults(handler=_initialize)

    source = commands.add_parser(
        "build-source-spec",
        help="hash the 18 expert and Unity lineage inputs",
    )
    source.add_argument("--full-source-dir", required=True)
    source.add_argument("--split", required=True)
    source.add_argument("--dig-primitives-dir", required=True)
    source.add_argument("--execution-library", required=True)
    source.add_argument("--pose-library", required=True)
    source.add_argument("--legacy-sweep", required=True)
    source.add_argument("--unity-repo-root", required=True)
    source.add_argument(
        "--contact-monitor-code",
        action="append",
        required=True,
        help="repeat for every sidecar/adapter C# source in lineage order",
    )
    source.add_argument("--frozen-target-handoff", required=True)
    source.add_argument("--expected-reset-state", required=True)
    source.add_argument("--output", required=True)
    source.set_defaults(handler=_build_source_spec)

    lineage = commands.add_parser(
        "build-ab-lineage",
        help="derive target handoff and reset baseline from a frozen rollout",
    )
    lineage.add_argument("--rollout-jsonl", required=True)
    lineage.add_argument("--planner-trace", required=True)
    lineage.add_argument("--target-episode-id", default="episode_168")
    lineage.add_argument("--target-raw-fields-sha256", required=True)
    lineage.add_argument("--target-cycle-index", type=int, required=True)
    lineage.add_argument("--output-dir", required=True)
    lineage.set_defaults(handler=_build_ab_lineage)

    prepare = commands.add_parser(
        "prepare",
        help="write the no-overwrite request root and explicit blockers",
    )
    prepare.add_argument("--source-spec", required=True)
    prepare.add_argument("--base-config", required=True)
    prepare.add_argument("--output-root", required=True)
    prepare.set_defaults(handler=_prepare)

    _add_collect_command(
        commands,
        name="collect-geometry",
        measurement_help="Unity geometry measurement",
        handler=_collect_geometry,
    )
    _add_collect_command(
        commands,
        name="collect-replay",
        measurement_help="18-source recorded-action replay measurement",
        handler=_collect_replay,
    )
    _add_collect_command(
        commands,
        name="collect-ab",
        measurement_help="six-attempt paired A/B set",
        handler=_collect_ab,
        needs_expert_replay=True,
    )

    finalize = commands.add_parser(
        "finalize",
        help="join the three evidence collections into a causal report",
    )
    finalize.add_argument("--manifest", required=True)
    finalize.add_argument("--geometry-collection", required=True)
    finalize.add_argument("--replay-collection", required=True)
    finalize.add_argument("--ab-collection", required=True)
    finalize.add_argument("--output-dir", required=True)
    finalize.set_defaults(handler=_finalize)
    return parser


def _add_collect_command(
    commands: Any,
    *,
    name: str,
    measurement_help: str,
    handler: Callable[[argparse.Namespace], dict[str, Any]],
    needs_expert_replay: bool = False,
) -> None:
    command = commands.add_parser(name)
    command.add_argument("--manifest", required=True)
    command.add_argument(
        "--measurement",
        required=True,
        help=measurement_help,
    )
    command.add_argument("--output", required=True)
    if needs_expert_replay:
        command.add_argument("--expert-replay-collection", required=True)
    command.set_defaults(handler=handler)


def _build_source_spec(args: argparse.Namespace) -> dict[str, Any]:
    return build_wall_contact_source_spec(
        full_source_dir=args.full_source_dir,
        split_path=args.split,
        dig_primitives_dir=args.dig_primitives_dir,
        execution_library_path=args.execution_library,
        pose_library_path=args.pose_library,
        legacy_sweep_path=args.legacy_sweep,
        unity_repo_root=args.unity_repo_root,
        contact_monitor_code_paths=args.contact_monitor_code,
        frozen_target_handoff_path=args.frozen_target_handoff,
        expected_reset_state_path=args.expected_reset_state,
        output_path=args.output,
    )


def _initialize(args: argparse.Namespace) -> dict[str, Any]:
    return initialize_wall_contact_semantics_experiment(
        rollout_jsonl_path=args.rollout_jsonl,
        planner_trace_path=args.planner_trace,
        target_episode_id=args.target_episode_id,
        target_raw_fields_sha256=args.target_raw_fields_sha256,
        target_cycle_index=args.target_cycle_index,
        full_source_dir=args.full_source_dir,
        split_path=args.split,
        dig_primitives_dir=args.dig_primitives_dir,
        execution_library_path=args.execution_library,
        pose_library_path=args.pose_library,
        legacy_sweep_path=args.legacy_sweep,
        unity_repo_root=args.unity_repo_root,
        contact_monitor_code_paths=args.contact_monitor_code,
        base_config_path=args.base_config,
        output_root=args.output_root,
    )


def _prepare(args: argparse.Namespace) -> dict[str, Any]:
    return prepare_wall_contact_semantics_experiment(
        source_spec_path=args.source_spec,
        base_config_path=args.base_config,
        output_root=args.output_root,
    )


def _build_ab_lineage(args: argparse.Namespace) -> dict[str, Any]:
    return build_ab_lineage(
        rollout_jsonl_path=args.rollout_jsonl,
        planner_trace_path=args.planner_trace,
        target_episode_id=args.target_episode_id,
        target_raw_fields_sha256=args.target_raw_fields_sha256,
        target_cycle_index=args.target_cycle_index,
        output_dir=args.output_dir,
    )


def _collect_geometry(args: argparse.Namespace) -> dict[str, Any]:
    return collect_expert_geometry_evidence(
        experiment_manifest_path=args.manifest,
        measurement_path=args.measurement,
        output_path=args.output,
    )


def _collect_replay(args: argparse.Namespace) -> dict[str, Any]:
    return collect_expert_replay_evidence(
        experiment_manifest_path=args.manifest,
        measurement_path=args.measurement,
        output_path=args.output,
    )


def _collect_ab(args: argparse.Namespace) -> dict[str, Any]:
    return collect_paired_ab_evidence(
        experiment_manifest_path=args.manifest,
        attempt_set_path=args.measurement,
        output_path=args.output,
        expert_replay_collection_path=args.expert_replay_collection,
    )


def _finalize(args: argparse.Namespace) -> dict[str, Any]:
    return finalize_wall_contact_semantics_experiment(
        experiment_manifest_path=args.manifest,
        geometry_collection_path=args.geometry_collection,
        expert_replay_collection_path=args.replay_collection,
        paired_ab_collection_path=args.ab_collection,
        output_dir=args.output_dir,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = args.handler(args)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
