"""Run the YuLong V2.4 hindsight data chain with tail-friendly logs."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOT_ROOT = Path("/fastdata/pingfan/excavator_testbed_data_hot")
DEFAULT_LABEL_CONFIG = Path("testbed/configs/teleop_yulong_v2_2_pro_full_task.yaml")
DEFAULT_DIG_TRAIN_CONFIG = Path("testbed/configs/act_yulong_v2_4_hindsight_goal_dig_qvel.yaml")
DEFAULT_RETURN_TRAIN_CONFIG = Path(
    "testbed/configs/act_yulong_v2_4_hindsight_goal_return_qvel.yaml"
)
DEFAULT_V2_4_5_DIG_TRAIN_CONFIG = Path(
    "testbed/configs/act_yulong_v2_4_5_spatial_mass_dig_qvel.yaml"
)
DEFAULT_V2_4_5_RETURN_TRAIN_CONFIG = Path(
    "testbed/configs/act_yulong_v2_4_5_spatial_mass_return_envelope_qvel.yaml"
)
DEFAULT_CARRY_TRAIN_CONFIG = Path(
    "testbed/configs/act_yulong_v2_4_5_spatial_mass_carry_qvel.yaml"
)
DEFAULT_DUMP_TRAIN_CONFIG = Path(
    "testbed/configs/act_yulong_v2_4_5_spatial_mass_dump_qvel.yaml"
)
DEFAULT_BOUNDARY_PROFILE = "v2_2_effect_release_fallback"
V2_4_5_BOUNDARY_PROFILE = "v2_4_5_spatial_mass"
DEFAULT_RETURN_MAX_TRANSITION_LEN = 512
DEFAULT_DEPTH_TOKEN_MAX_SATURATION = 0.02
DEFAULT_DEPTH_TOKEN_MIN_P90_P10 = 0.05
DEFAULT_DEPTH_TOKEN_MIN_NONZERO_FRAC = 0.90
DEFAULT_DEPTH_SOURCE_MIN_FRACTION = 0.95
DEFAULT_REQUIRED_DEPTH_SOURCE = "env_state_removed_depth_delta"
DEFAULT_RETURN_MIN_DIG_RATIO = 0.75
DEFAULT_RETURN_MAX_OVERLONG_REJECT_RATIO = 0.10
DEFAULT_DUMP_MAX_LEN = 768
DEFAULT_DUMP_MAX_P95_LEN = 640
DEFAULT_DUMP_MAX_TRANSITION_MODE_FRAC = 0.0
DEFAULT_CARRY_MAX_DEPOSIT_DELTA_KG = 5.0
DEFAULT_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC = 0.10
DEFAULT_DUMP_MAX_PRE_RELEASE_LEAD_STEPS = 120
DEFAULT_RETURN_ENVELOPE_MIN_VALID_FRACTION = 0.95
CURRENT_LINKS = {
    "relabeled": Path("data/yulong_v2_4_removed_depth_relabeled_vds"),
    "operator": Path("data/yulong_v2_4_removed_depth_operator_relabel_vds"),
    "hindsight": Path("data/yulong_v2_4_hindsight_goal_relabel_vds"),
    "primitive_vds": Path("data/yulong_v2_4_hindsight_goal_primitives_vds"),
    "primitive_copy": Path("data/yulong_v2_4_hindsight_goal_primitives_copy"),
}


@dataclass(frozen=True)
class PipelinePaths:
    job_dir: Path
    logs_dir: Path
    relabeled_root: Path | None
    operator_root: Path
    hindsight_root: Path
    primitive_vds_root: Path
    primitive_copy_root: Path


def main() -> None:
    args = _parse_args()
    if args.detach:
        _detach(args)
        return
    _run_pipeline(args)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tb-build-v2_4-hindsight-pipeline",
        description=(
            "Build the V2.4 removed-depth hindsight data chain as VDS first, "
            "then materialize primitive copy in parallel. Every stage writes a "
            "log under --job-dir/logs so progress can be watched with tail -f."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--raw-dir",
        type=Path,
        help="Raw/replayed full-episode root. The pipeline starts with tb-label-v2_1.",
    )
    source.add_argument(
        "--relabeled-dir",
        type=Path,
        help="Existing V2.1/V2.2 relabeled root. The pipeline starts with operator-first.",
    )
    source.add_argument(
        "--operator-dir",
        type=Path,
        help="Existing operator-first root. The pipeline starts with hindsight-goal relabel.",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Output tag. Defaults to YYYYMMDD_HHMMSS.",
    )
    parser.add_argument(
        "--job-dir",
        type=Path,
        default=None,
        help="Job/log directory. Defaults to runs/jobs/yulong_v2_4_removed_depth_<tag>.",
    )
    parser.add_argument(
        "--hot-root",
        type=Path,
        default=DEFAULT_HOT_ROOT,
        help="Root for generated data directories.",
    )
    parser.add_argument("--relabeled-output", type=Path, default=None)
    parser.add_argument("--operator-output", type=Path, default=None)
    parser.add_argument("--hindsight-output", type=Path, default=None)
    parser.add_argument("--primitive-vds-output", type=Path, default=None)
    parser.add_argument("--primitive-copy-output", type=Path, default=None)
    parser.add_argument(
        "--label-config",
        type=Path,
        default=DEFAULT_LABEL_CONFIG,
        help="Config passed to tb-label-v2_1 when --raw-dir is used.",
    )
    parser.add_argument(
        "--v2-label-source-dir",
        type=Path,
        default=None,
        help=(
            "When --raw-dir is a replay refresh, transfer /v2 labels from this "
            "already-QC'd relabeled root instead of recomputing cycle boundaries."
        ),
    )
    parser.add_argument("--scenario-id", type=str, default=None)
    parser.add_argument(
        "--qualified-dig-start-mode",
        choices=("progress", "contact_depth"),
        default="progress",
    )
    parser.add_argument(
        "--boundary-profile",
        type=str,
        default=DEFAULT_BOUNDARY_PROFILE,
        help="Forwarded to tb-build-primitives-v2_2.",
    )
    parser.add_argument(
        "--return-max-transition-len",
        type=int,
        default=DEFAULT_RETURN_MAX_TRANSITION_LEN,
        help=(
            "Forwarded to tb-build-primitives-v2_2. The default matches the "
            "V2.4 return ACT episode_len so very long dump->next-dig gaps do "
            "not enter return training."
        ),
    )
    parser.add_argument(
        "--return-clean-profile",
        type=str,
        default=None,
        help="Optional transition clean profile forwarded to tb-build-primitives-v2_2.",
    )
    parser.add_argument(
        "--materialize-workers",
        type=int,
        default=16,
        help="Worker processes for tb-materialize-vds --recursive.",
    )
    parser.add_argument("--image-batch-size", type=int, default=16)
    parser.add_argument(
        "--skip-pre-materialize-qc",
        action="store_true",
        help=(
            "Skip primitive-VDS token/return QC before image materialization. "
            "The default is to fail before materialize/train when token or "
            "transition checks do not pass."
        ),
    )
    parser.add_argument(
        "--depth-token-max-saturation",
        type=float,
        default=DEFAULT_DEPTH_TOKEN_MAX_SATURATION,
        help="Maximum allowed fraction of gold dig depth tokens with dim7 >= 0.999.",
    )
    parser.add_argument(
        "--depth-token-min-p90-p10",
        type=float,
        default=DEFAULT_DEPTH_TOKEN_MIN_P90_P10,
        help="Minimum required gold dig depth-token p90-p10 separation.",
    )
    parser.add_argument(
        "--depth-token-min-nonzero-frac",
        type=float,
        default=DEFAULT_DEPTH_TOKEN_MIN_NONZERO_FRAC,
        help="Minimum allowed fraction of nonzero gold dig depth tokens.",
    )
    parser.add_argument(
        "--depth-source-min-fraction",
        type=float,
        default=DEFAULT_DEPTH_SOURCE_MIN_FRACTION,
        help=(
            "Minimum fraction of gold dig episodes whose depth_outcome_source "
            "matches --required-depth-outcome-source."
        ),
    )
    parser.add_argument(
        "--required-depth-outcome-source",
        type=str,
        default=DEFAULT_REQUIRED_DEPTH_SOURCE,
        help="Required reliable depth source for gold dig token/outcome QC.",
    )
    parser.add_argument(
        "--return-min-dig-ratio",
        type=float,
        default=DEFAULT_RETURN_MIN_DIG_RATIO,
        help=(
            "Minimum return primitive count divided by dig primitive count. "
            "Catches collapsed cycle boundaries before materialization."
        ),
    )
    parser.add_argument(
        "--return-max-overlong-reject-ratio",
        type=float,
        default=DEFAULT_RETURN_MAX_OVERLONG_REJECT_RATIO,
        help=(
            "Maximum allowed overlong-return rejects divided by all return "
            "candidates. Large values usually mean next qualified-dig-start "
            "boundaries were missed."
        ),
    )
    parser.add_argument(
        "--dump-max-len",
        type=int,
        default=DEFAULT_DUMP_MAX_LEN,
        help=(
            "Maximum allowed dump primitive length during pre-materialize QC. "
            "Catches dump windows that swallowed return/next-cycle data."
        ),
    )
    parser.add_argument(
        "--dump-max-p95-len",
        type=int,
        default=DEFAULT_DUMP_MAX_P95_LEN,
        help=(
            "Maximum allowed p95 dump primitive length during pre-materialize QC."
        ),
    )
    parser.add_argument(
        "--dump-max-transition-mode-frac",
        type=float,
        default=DEFAULT_DUMP_MAX_TRANSITION_MODE_FRAC,
        help=(
            "Maximum allowed fraction of dump primitive steps labelled as "
            "transition mode or transition phase."
        ),
    )
    parser.add_argument(
        "--carry-max-deposit-delta-kg",
        type=float,
        default=DEFAULT_CARRY_MAX_DEPOSIT_DELTA_KG,
        help="Maximum accepted deposit delta inside carry windows.",
    )
    parser.add_argument(
        "--carry-max-deposit-to-payload-loss-frac",
        type=float,
        default=DEFAULT_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC,
        help="Maximum carry deposit contamination ratio.",
    )
    parser.add_argument(
        "--dump-max-pre-release-lead-steps",
        type=int,
        default=DEFAULT_DUMP_MAX_PRE_RELEASE_LEAD_STEPS,
        help="Maximum allowed dump_start lead before release_onset.",
    )
    parser.add_argument(
        "--return-envelope-min-valid-fraction",
        type=float,
        default=DEFAULT_RETURN_ENVELOPE_MIN_VALID_FRACTION,
        help="Minimum fraction of return episodes with a valid V2.4.5 envelope.",
    )
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Skip a stage when its expected output already contains episode files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Forward --overwrite to build/materialize stages.",
    )
    parser.add_argument(
        "--update-current-symlinks",
        action="store_true",
        help=(
            "Update data/yulong_v2_4_* current symlinks after successful stages. "
            "Existing real directories are never replaced."
        ),
    )
    parser.add_argument(
        "--train",
        action="store_true",
        help=(
            "After data QC, train dig/return. With --boundary-profile "
            "v2_4_5_spatial_mass this trains dig->return->carry->dump."
        ),
    )
    parser.add_argument("--dig-train-config", type=Path, default=DEFAULT_DIG_TRAIN_CONFIG)
    parser.add_argument(
        "--return-train-config",
        type=Path,
        default=DEFAULT_RETURN_TRAIN_CONFIG,
    )
    parser.add_argument("--carry-train-config", type=Path, default=DEFAULT_CARRY_TRAIN_CONFIG)
    parser.add_argument("--dump-train-config", type=Path, default=DEFAULT_DUMP_TRAIN_CONFIG)
    parser.add_argument(
        "--skip-boundary-audit",
        action="store_true",
        help="Skip Gate 2 boundary audit artifact export after primitive numeric QC.",
    )
    parser.add_argument(
        "--boundary-audit-max-videos",
        type=int,
        default=24,
        help="Maximum boundary videos to export for Gate 2 visual review.",
    )
    parser.add_argument(
        "--stop-after-gate",
        choices=(
            "none",
            "primitive_qc",
            "boundary_audit",
            "materialize_qc",
            "train_dig",
            "train_return",
            "train_carry",
            "train_dump",
        ),
        default="none",
        help=(
            "Stop after a feedback gate summary is written. This supports "
            "closed-loop review instead of one-shot execution."
        ),
    )
    parser.add_argument(
        "--ack-feedback-gates",
        action="store_true",
        help=(
            "Acknowledge that previous gate summaries were reviewed. For "
            "v2_4_5_spatial_mass this is required to continue past Gate 2 "
            "without an explicit --stop-after-gate value."
        ),
    )
    parser.add_argument(
        "--no-cleanup-after-train",
        action="store_true",
        help=(
            "Do not remove the materialized primitive copy and non-best "
            "checkpoints after --train completes successfully."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the stage commands and write manifest, but do not execute them.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only write stage logs; do not tee subprocess output to stdout.",
    )
    parser.add_argument(
        "--detach",
        action="store_true",
        help="Start the same pipeline in the background and print tail commands.",
    )
    return parser.parse_args()


def _effective_stop_after_gate(args: argparse.Namespace) -> str:
    explicit = str(args.stop_after_gate)
    if explicit != "none":
        return explicit
    if (
        str(args.boundary_profile) == V2_4_5_BOUNDARY_PROFILE
        and not bool(args.ack_feedback_gates)
        and not bool(args.skip_boundary_audit)
    ):
        return "boundary_audit"
    return "none"


def _run_pipeline(args: argparse.Namespace) -> None:
    tag = _tag(args.tag)
    paths = _paths(args, tag)
    stop_after_gate = _effective_stop_after_gate(args)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = paths.job_dir / "manifest.json"
    stages = _stage_commands(args, paths)
    _write_manifest(
        manifest_path,
        args=args,
        tag=tag,
        paths=paths,
        stages=stages,
    )
    _log_user(paths, f"job_dir={paths.job_dir}")
    _log_user(paths, f"tail: tail -f {paths.logs_dir}/*.log")

    for stage_name, command, output_path, link_name in stages:
        if output_path is not None and args.reuse_existing and _has_episode_files(output_path):
            _log_user(paths, f"skip {stage_name}: reusing existing {output_path}")
        else:
            _run_stage(
                stage_name,
                command,
                paths=paths,
                dry_run=bool(args.dry_run),
                quiet=bool(args.quiet),
            )
        if stage_name == "04_primitive_vds" and not bool(args.dry_run):
            pre_qc_payload = _run_pre_materialize_qc(
                paths.primitive_vds_root,
                args=args,
            )
            _write_stage_json(paths.logs_dir / "04_pre_materialize_qc.json", pre_qc_payload)
            _log_user(paths, "pre-materialize QC " + json.dumps(pre_qc_payload, sort_keys=True))
            if not bool(pre_qc_payload.get("passed", False)):
                raise SystemExit(
                    "pre-materialize QC failed; see "
                    f"{paths.logs_dir / '04_pre_materialize_qc.json'}"
                )
            if stop_after_gate == "primitive_qc":
                _log_user(paths, "stop-after-gate primitive_qc")
                return
        if stage_name == "04b_boundary_audit" and not bool(args.dry_run):
            audit_gate_payload = _run_boundary_audit_gate_summary(paths)
            _write_stage_json(
                paths.logs_dir / "04b_boundary_audit_gate_summary.json",
                audit_gate_payload,
            )
            _log_user(
                paths,
                "boundary audit gate "
                + json.dumps(audit_gate_payload, sort_keys=True),
            )
            if stop_after_gate == "boundary_audit":
                _log_user(paths, "stop-after-gate boundary_audit")
                return
        if (
            output_path is not None
            and link_name is not None
            and bool(args.update_current_symlinks)
            and not bool(args.dry_run)
        ):
            _update_current_link(CURRENT_LINKS[link_name], output_path)

    if not bool(args.dry_run):
        qc_payload = _run_qc(paths.primitive_copy_root)
        _write_stage_json(paths.logs_dir / "06_qc.json", qc_payload)
        _log_user(paths, "QC " + json.dumps(qc_payload, sort_keys=True))
        materialize_gate_payload = _feedback_gate_payload(
            gate="gate1b_materialized_copy_qc",
            passed=True,
            failed_checks=[],
            current_result=qc_payload,
            next_step="train_or_manual_review",
        )
        _write_stage_json(
            paths.logs_dir / "06_materialize_qc_gate_summary.json",
            materialize_gate_payload,
        )
        if stop_after_gate == "materialize_qc":
            _log_user(paths, "stop-after-gate materialize_qc")
            return

    if args.train:
        if not args.update_current_symlinks:
            raise SystemExit("--train requires --update-current-symlinks so configs see the new copy root.")
        dig_train_config = args.dig_train_config
        return_train_config = args.return_train_config
        if str(args.boundary_profile) == V2_4_5_BOUNDARY_PROFILE:
            if dig_train_config == DEFAULT_DIG_TRAIN_CONFIG:
                dig_train_config = DEFAULT_V2_4_5_DIG_TRAIN_CONFIG
            if return_train_config == DEFAULT_RETURN_TRAIN_CONFIG:
                return_train_config = DEFAULT_V2_4_5_RETURN_TRAIN_CONFIG
        train_stages = [
            (
                "07_train_dig",
                [sys.executable, "-m", "testbed.cli.train", "--config", str(dig_train_config)],
            ),
            (
                "08_train_return",
                [
                    sys.executable,
                    "-m",
                    "testbed.cli.train",
                    "--config",
                    str(return_train_config),
                ],
            ),
        ]
        if str(args.boundary_profile) == V2_4_5_BOUNDARY_PROFILE:
            train_stages.extend(
                [
                    (
                        "09_train_carry",
                        [
                            sys.executable,
                            "-m",
                            "testbed.cli.train",
                            "--config",
                            str(args.carry_train_config),
                        ],
                    ),
                    (
                        "10_train_dump",
                        [
                            sys.executable,
                            "-m",
                            "testbed.cli.train",
                            "--config",
                            str(args.dump_train_config),
                        ],
                    ),
                ]
            )
        for stage_name, command in train_stages:
            _run_stage(
                stage_name,
                command,
                paths=paths,
                dry_run=bool(args.dry_run),
                quiet=bool(args.quiet),
            )
            if not bool(args.dry_run):
                gate_payload = _feedback_gate_payload(
                    gate=f"gate3_{stage_name}",
                    passed=True,
                    failed_checks=[],
                    current_result={
                        "stage": stage_name,
                        "config": command[-1],
                        "status": "completed",
                    },
                    next_step=_next_training_gate(stage_name, train_stages),
                )
                _write_stage_json(
                    paths.logs_dir / f"{stage_name}_gate_summary.json",
                    gate_payload,
                )
            stop_name = {
                "07_train_dig": "train_dig",
                "08_train_return": "train_return",
                "09_train_carry": "train_carry",
                "10_train_dump": "train_dump",
            }.get(stage_name)
            if stop_name is not None and stop_after_gate == stop_name:
                _log_user(paths, f"stop-after-gate {stop_name}")
                return
        if not bool(args.no_cleanup_after_train):
            cleanup_command = _cleanup_command(args, paths)
            _run_stage(
                "11_cleanup_training_artifacts",
                cleanup_command,
                paths=paths,
                dry_run=bool(args.dry_run),
                quiet=bool(args.quiet),
            )

    _log_user(paths, "pipeline complete")


def _paths(args: argparse.Namespace, tag: str) -> PipelinePaths:
    job_dir = (
        args.job_dir
        if args.job_dir is not None
        else Path("runs/jobs") / f"yulong_v2_4_removed_depth_{tag}"
    )
    hot_root = args.hot_root
    relabeled_root = args.relabeled_output
    if args.raw_dir is not None and relabeled_root is None:
        relabeled_root = hot_root / f"yulong_v2_4_removed_depth_relabeled_vds_{tag}"
    operator_root = (
        args.operator_dir
        if args.operator_dir is not None
        else (
            args.operator_output
            if args.operator_output is not None
            else hot_root / f"yulong_v2_4_removed_depth_operator_relabel_vds_{tag}"
        )
    )
    hindsight_root = (
        args.hindsight_output
        if args.hindsight_output is not None
        else hot_root / f"yulong_v2_4_removed_depth_hindsight_goal_relabel_vds_{tag}"
    )
    primitive_vds_root = (
        args.primitive_vds_output
        if args.primitive_vds_output is not None
        else hot_root / f"yulong_v2_4_removed_depth_hindsight_goal_primitives_vds_{tag}"
    )
    primitive_copy_root = (
        args.primitive_copy_output
        if args.primitive_copy_output is not None
        else hot_root / f"yulong_v2_4_removed_depth_hindsight_goal_primitives_copy_{tag}"
    )
    return PipelinePaths(
        job_dir=job_dir,
        logs_dir=job_dir / "logs",
        relabeled_root=relabeled_root,
        operator_root=operator_root,
        hindsight_root=hindsight_root,
        primitive_vds_root=primitive_vds_root,
        primitive_copy_root=primitive_copy_root,
    )


def _stage_commands(
    args: argparse.Namespace,
    paths: PipelinePaths,
) -> list[tuple[str, list[str], Path | None, str | None]]:
    stages: list[tuple[str, list[str], Path | None, str | None]] = []
    source_for_operator = args.relabeled_dir
    if args.raw_dir is not None:
        if paths.relabeled_root is None:
            raise AssertionError("relabeled_root should be set when --raw-dir is used")
        command = [
            sys.executable,
            "-m",
            "testbed.cli.label_v2_1",
            "--dataset-dir",
            str(args.raw_dir),
            "--output-dir",
            str(paths.relabeled_root),
            "--storage-mode",
            "vds",
            "--qualified-dig-start-mode",
            str(args.qualified_dig_start_mode),
        ]
        if args.label_config is not None:
            command.extend(["--config", str(args.label_config)])
        if args.scenario_id:
            command.extend(["--scenario-id", str(args.scenario_id)])
        if args.v2_label_source_dir is not None:
            command.extend(["--v2-label-source-dir", str(args.v2_label_source_dir)])
        stages.append(("01_label_v2_1_vds", command, paths.relabeled_root, "relabeled"))
        source_for_operator = paths.relabeled_root

    if args.operator_dir is None:
        if source_for_operator is None:
            raise SystemExit("Either --operator-dir, --relabeled-dir, or --raw-dir is required.")
        command = [
            sys.executable,
            "-m",
            "testbed.cli.build_operator_first_v2_2",
            "--dataset-dir",
            str(source_for_operator),
            "--output-dir",
            str(paths.operator_root),
            "--storage-mode",
            "vds",
        ]
        if args.overwrite:
            command.append("--overwrite")
        stages.append(("02_operator_first_vds", command, paths.operator_root, "operator"))

    command = [
        sys.executable,
        "-m",
        "testbed.cli.build_hindsight_goal_v2_4",
        "--dataset-dir",
        str(paths.operator_root),
        "--output-dir",
        str(paths.hindsight_root),
        "--storage-mode",
        "vds",
    ]
    if args.overwrite:
        command.append("--overwrite")
    stages.append(("03_hindsight_goal_vds", command, paths.hindsight_root, "hindsight"))

    command = [
        sys.executable,
        "-m",
        "testbed.cli.build_primitives_v2_2",
        "--raw-dir",
        str(paths.hindsight_root),
        "--output-root",
        str(paths.primitive_vds_root),
        "--storage-mode",
        "vds",
        "--boundary-profile",
        str(args.boundary_profile),
    ]
    if args.return_max_transition_len is not None:
        command.extend(
            ["--return-max-transition-len", str(int(args.return_max_transition_len))]
        )
    if args.return_clean_profile:
        command.extend(["--return-clean-profile", str(args.return_clean_profile)])
    if args.overwrite:
        command.append("--overwrite")
    stages.append(("04_primitive_vds", command, paths.primitive_vds_root, "primitive_vds"))

    if not bool(args.skip_boundary_audit):
        command = [
            sys.executable,
            "-m",
            "testbed.cli.audit_primitive_boundaries",
            "--primitive-root",
            str(paths.primitive_vds_root),
            "--boundary",
            "both",
            "--sample",
            "balanced",
            "--max-videos",
            str(max(0, int(args.boundary_audit_max_videos))),
        ]
        stages.append(("04b_boundary_audit", command, None, None))

    command = [
        sys.executable,
        "-m",
        "testbed.cli.materialize_vds",
        "--input",
        str(paths.primitive_vds_root),
        "--output",
        str(paths.primitive_copy_root),
        "--recursive",
        "--workers",
        str(max(1, int(args.materialize_workers))),
        "--image-batch-size",
        str(max(1, int(args.image_batch_size))),
    ]
    if args.overwrite:
        command.append("--overwrite")
    stages.append(("05_materialize_primitive_copy", command, paths.primitive_copy_root, "primitive_copy"))
    return stages


def _run_pre_materialize_qc(
    primitive_vds_root: Path,
    *,
    args: argparse.Namespace,
) -> dict[str, Any]:
    if bool(args.skip_pre_materialize_qc):
        return {
            "root": str(primitive_vds_root),
            "passed": True,
            "skipped": True,
            "reason": "--skip-pre-materialize-qc",
        }

    import h5py
    import numpy as np

    payload: dict[str, Any] = {
        "root": str(primitive_vds_root),
        "passed": True,
        "failed_checks": [],
        "thresholds": {
            "depth_token_max_saturation": float(args.depth_token_max_saturation),
            "depth_token_min_p90_p10": float(args.depth_token_min_p90_p10),
            "depth_token_min_nonzero_frac": float(args.depth_token_min_nonzero_frac),
            "depth_source_min_fraction": float(args.depth_source_min_fraction),
            "required_depth_outcome_source": str(args.required_depth_outcome_source),
            "return_max_transition_len": (
                None
                if args.return_max_transition_len is None
                else int(args.return_max_transition_len)
            ),
            "return_min_dig_ratio": float(args.return_min_dig_ratio),
            "return_max_overlong_reject_ratio": float(
                args.return_max_overlong_reject_ratio
            ),
            "dump_max_len": int(args.dump_max_len),
            "dump_max_p95_len": int(args.dump_max_p95_len),
            "dump_max_transition_mode_frac": float(
                args.dump_max_transition_mode_frac
            ),
            "carry_max_deposit_delta_kg": float(args.carry_max_deposit_delta_kg),
            "carry_max_deposit_to_payload_loss_frac": float(
                args.carry_max_deposit_to_payload_loss_frac
            ),
            "dump_max_pre_release_lead_steps": int(
                args.dump_max_pre_release_lead_steps
            ),
            "return_envelope_min_valid_fraction": float(
                args.return_envelope_min_valid_fraction
            ),
        },
        "primitives": {},
    }

    def fail(message: str) -> None:
        payload["passed"] = False
        payload["failed_checks"].append(message)

    for primitive in ("dig", "carry", "dump", "return"):
        episodes = _episode_files(primitive_vds_root / primitive)
        payload["primitives"][primitive] = {"episode_count": len(episodes)}
    if payload["primitives"]["dig"]["episode_count"] <= 0:
        fail("no dig primitive episodes")
    if payload["primitives"]["dump"]["episode_count"] <= 0:
        fail("no dump primitive episodes")
    if payload["primitives"]["return"]["episode_count"] <= 0:
        fail("no return primitive episodes")

    dig_depth_tokens: list[float] = []
    dig_depth_outcomes: list[float] = []
    dig_raw_depth_m: list[float] = []
    gold_depth_tokens: list[float] = []
    gold_depth_outcomes: list[float] = []
    gold_raw_depth_m: list[float] = []
    source_counts: dict[str, int] = {}
    gold_source_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    contract_versions: dict[str, int] = {}
    depth_scales: dict[str, int] = {}

    for path in _episode_files(primitive_vds_root / "dig"):
        with h5py.File(path, "r") as handle:
            tier = _h5_training_tier(handle)
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            source = _h5_depth_source(handle)
            source_counts[source] = source_counts.get(source, 0) + 1
            if tier == "gold":
                gold_source_counts[source] = gold_source_counts.get(source, 0) + 1

            metadata = handle["metadata"].attrs if "metadata" in handle else handle.attrs
            contract = _h5_text(metadata.get("dig_cut_token_contract_version", ""))
            if contract:
                contract_versions[contract] = contract_versions.get(contract, 0) + 1
            if "dig_cut_depth_scale_m" in metadata:
                scale = f"{float(metadata['dig_cut_depth_scale_m']):.6g}"
                depth_scales[scale] = depth_scales.get(scale, 0) + 1

            token_depth = _h5_step_value(handle, "v2/step/dig_cut_tokens", col=7)
            if token_depth is not None:
                dig_depth_tokens.append(token_depth)
                if tier == "gold":
                    gold_depth_tokens.append(token_depth)
            outcome_depth = _h5_step_value(handle, "v2/step/dig_outcome_targets", col=7)
            if outcome_depth is not None:
                dig_depth_outcomes.append(outcome_depth)
                if tier == "gold":
                    gold_depth_outcomes.append(outcome_depth)
            raw_depth = _h5_cycle_depth_m(handle)
            if raw_depth is not None:
                dig_raw_depth_m.append(raw_depth)
                if tier == "gold":
                    gold_raw_depth_m.append(raw_depth)

    dig_payload = payload["primitives"]["dig"]
    dig_payload["training_tier_counts"] = tier_counts
    dig_payload["depth_outcome_source_counts"] = source_counts
    dig_payload["gold_depth_outcome_source_counts"] = gold_source_counts
    dig_payload["dig_cut_token_contract_versions"] = contract_versions
    dig_payload["dig_cut_depth_scales_m"] = depth_scales
    dig_payload["token_depth_dim7_stats"] = _numeric_stats(dig_depth_tokens)
    dig_payload["gold_token_depth_dim7_stats"] = _numeric_stats(gold_depth_tokens)
    dig_payload["outcome_depth_dim7_stats"] = _numeric_stats(dig_depth_outcomes)
    dig_payload["gold_outcome_depth_dim7_stats"] = _numeric_stats(gold_depth_outcomes)
    dig_payload["raw_removed_depth_max_delta_m_stats"] = _numeric_stats(dig_raw_depth_m)
    dig_payload["gold_raw_removed_depth_max_delta_m_stats"] = _numeric_stats(
        gold_raw_depth_m
    )

    gold_count = int(sum(gold_source_counts.values()))
    reliable_gold = int(gold_source_counts.get(str(args.required_depth_outcome_source), 0))
    source_fraction = float(reliable_gold / gold_count) if gold_count > 0 else 0.0
    dig_payload["gold_required_depth_source_fraction"] = source_fraction
    if gold_count <= 0:
        fail("no gold dig episodes for token/depth QC")
    elif source_fraction < float(args.depth_source_min_fraction):
        fail(
            "gold reliable depth source fraction "
            f"{source_fraction:.4f} < {float(args.depth_source_min_fraction):.4f}"
        )

    gold_stats = dig_payload["gold_token_depth_dim7_stats"]
    if gold_stats is None:
        fail("missing gold dig depth tokens")
    else:
        saturation = float(gold_stats["saturation_ge_0_999"])
        spread = float(gold_stats["p90"] - gold_stats["p10"])
        nonzero = float(gold_stats["nonzero_gt_1e_6"])
        if saturation > float(args.depth_token_max_saturation):
            fail(
                "gold depth token saturation "
                f"{saturation:.4f} > {float(args.depth_token_max_saturation):.4f}"
            )
        if spread < float(args.depth_token_min_p90_p10):
            fail(
                "gold depth token p90-p10 spread "
                f"{spread:.4f} < {float(args.depth_token_min_p90_p10):.4f}"
            )
        if nonzero < float(args.depth_token_min_nonzero_frac):
            fail(
                "gold depth token nonzero fraction "
                f"{nonzero:.4f} < {float(args.depth_token_min_nonzero_frac):.4f}"
            )

    from testbed.data.v2_1 import PHASE_NAME_TO_ID
    from testbed.planner.boundary_detector import MODE_TRANSITION

    transition_phase_ids = {
        int(PHASE_NAME_TO_ID["transition_corridor"]),
        int(PHASE_NAME_TO_ID["transition_wait_next_dig"]),
    }
    dump_lengths: list[int] = []
    dump_transition_fracs: list[float] = []
    for path in _episode_files(primitive_vds_root / "dump"):
        with h5py.File(path, "r") as handle:
            length = _h5_action_len(handle)
            dump_lengths.append(length)
            transition_mask = np.zeros(length, dtype=bool)
            mode_id = _h5_1d_array(handle, "v2/step/mode_id")
            if mode_id is not None and mode_id.size == length:
                transition_mask |= mode_id.astype(np.int64) == int(MODE_TRANSITION)
            phase_id = _h5_1d_array(handle, "v2/step/phase_id")
            if phase_id is not None and phase_id.size == length:
                transition_mask |= np.isin(
                    phase_id.astype(np.int64),
                    np.asarray(sorted(transition_phase_ids), dtype=np.int64),
                )
            dump_transition_fracs.append(
                float(np.mean(transition_mask)) if length > 0 else 0.0
            )
    dump_payload = payload["primitives"]["dump"]
    dump_payload["length_stats"] = _numeric_stats(dump_lengths)
    dump_payload["transition_mode_or_phase_frac_stats"] = _numeric_stats(
        dump_transition_fracs
    )
    dump_payload["transition_contaminated_episode_count"] = int(
        sum(value > 0.0 for value in dump_transition_fracs)
    )
    dump_stats = dump_payload["length_stats"]
    if dump_stats is not None:
        dump_max = int(dump_stats["max"])
        dump_p95 = float(dump_stats["p95"])
        if dump_max > int(args.dump_max_len):
            fail(f"dump max length {dump_max} > {int(args.dump_max_len)}")
        if dump_p95 > float(args.dump_max_p95_len):
            fail(
                "dump p95 length "
                f"{dump_p95:.1f} > {float(args.dump_max_p95_len):.1f}"
            )
    dump_transition_stats = dump_payload["transition_mode_or_phase_frac_stats"]
    if dump_transition_stats is not None:
        dump_transition_max = float(dump_transition_stats["max"])
        if dump_transition_max > float(args.dump_max_transition_mode_frac):
            fail(
                "dump transition-mode/phase fraction "
                f"{dump_transition_max:.4f} > "
                f"{float(args.dump_max_transition_mode_frac):.4f}"
            )

    carry_deposit_delta: list[float] = []
    carry_deposit_ratio: list[float] = []
    for path in _episode_files(primitive_vds_root / "carry"):
        with h5py.File(path, "r") as handle:
            metadata = handle["metadata"].attrs if "metadata" in handle else handle.attrs
            if "carry_deposit_delta_kg" in metadata:
                carry_deposit_delta.append(float(metadata["carry_deposit_delta_kg"]))
            if "carry_deposit_to_payload_loss_frac" in metadata:
                carry_deposit_ratio.append(
                    float(metadata["carry_deposit_to_payload_loss_frac"])
                )
    carry_payload = payload["primitives"]["carry"]
    carry_payload["deposit_delta_kg_stats"] = _numeric_stats(carry_deposit_delta)
    carry_payload["deposit_to_payload_loss_frac_stats"] = _numeric_stats(
        carry_deposit_ratio
    )
    carry_bad_count = 0
    for delta, ratio in zip(carry_deposit_delta, carry_deposit_ratio):
        if (
            float(delta) > float(args.carry_max_deposit_delta_kg)
            and float(ratio) > float(args.carry_max_deposit_to_payload_loss_frac)
        ):
            carry_bad_count += 1
    carry_payload["deposit_contaminated_episode_count"] = int(carry_bad_count)
    if carry_bad_count > 0:
        fail(f"carry deposit contamination count {carry_bad_count} > 0")

    dump_leads: list[float] = []
    for path in _episode_files(primitive_vds_root / "dump"):
        with h5py.File(path, "r") as handle:
            metadata = handle["metadata"].attrs if "metadata" in handle else handle.attrs
            if "dump_pre_release_lead_steps" in metadata:
                dump_leads.append(float(metadata["dump_pre_release_lead_steps"]))
    dump_payload["pre_release_lead_steps_stats"] = _numeric_stats(dump_leads)
    if dump_leads and max(dump_leads) > int(args.dump_max_pre_release_lead_steps):
        fail(
            "dump pre-release lead max "
            f"{max(dump_leads):.0f} > {int(args.dump_max_pre_release_lead_steps)}"
        )

    return_lengths: list[int] = []
    return_tiers: dict[str, int] = {}
    return_envelope_valid: list[float] = []
    return_envelope_full_mask_valid: list[float] = []
    for path in _episode_files(primitive_vds_root / "return"):
        with h5py.File(path, "r") as handle:
            return_lengths.append(_h5_action_len(handle))
            tier = _h5_training_tier(handle)
            return_tiers[tier] = return_tiers.get(tier, 0) + 1
            token = _h5_1d_or_2d_array(
                handle,
                "v2/step/return_start_envelope_tokens_v1",
            )
            mask = _h5_1d_or_2d_array(
                handle,
                "v2/step/return_start_envelope_valid_mask",
            )
            if token is not None and token.size > 0:
                token_arr = np.asarray(token, dtype=np.float32)
                if token_arr.ndim == 2 and token_arr.shape[1] > 16:
                    return_envelope_valid.append(float(np.mean(token_arr[:, 16] > 0.5)))
                elif token_arr.ndim == 1 and token_arr.shape[0] > 16:
                    return_envelope_valid.append(float(token_arr[16] > 0.5))
            if mask is not None and mask.size > 0:
                mask_arr = np.asarray(mask)
                return_envelope_full_mask_valid.append(float(np.mean(mask_arr > 0.5)))
                if token is None:
                    if mask_arr.ndim == 2 and mask_arr.shape[1] > 16:
                        return_envelope_valid.append(
                            float(np.mean(mask_arr[:, 16] > 0.5))
                        )
                    elif mask_arr.ndim == 1 and mask_arr.shape[0] > 16:
                        return_envelope_valid.append(float(mask_arr[16] > 0.5))
    return_payload = payload["primitives"]["return"]
    return_payload["length_stats"] = _numeric_stats(return_lengths)
    return_payload["training_tier_counts"] = return_tiers
    return_payload["return_start_envelope_valid_fraction_stats"] = _numeric_stats(
        return_envelope_valid
    )
    return_payload["return_start_envelope_full_mask_fraction_stats"] = _numeric_stats(
        return_envelope_full_mask_valid
    )
    if return_envelope_valid:
        valid_fraction = float(np.mean(np.asarray(return_envelope_valid) >= 1.0))
        return_payload["return_start_envelope_episode_valid_fraction"] = valid_fraction
        if valid_fraction < float(args.return_envelope_min_valid_fraction):
            fail(
                "return envelope valid episode fraction "
                f"{valid_fraction:.4f} < {float(args.return_envelope_min_valid_fraction):.4f}"
            )
    elif str(args.boundary_profile) == V2_4_5_BOUNDARY_PROFILE:
        fail("missing return_start_envelope_valid_mask in return episodes")
    dig_count = int(payload["primitives"]["dig"]["episode_count"])
    return_count = int(return_payload["episode_count"])
    return_ratio = float(return_count / dig_count) if dig_count > 0 else 0.0
    return_payload["return_to_dig_episode_ratio"] = return_ratio
    if dig_count > 0 and return_ratio < float(args.return_min_dig_ratio):
        fail(
            "return/dig episode ratio "
            f"{return_ratio:.4f} < {float(args.return_min_dig_ratio):.4f}"
        )
    if return_lengths and args.return_max_transition_len is not None:
        max_len = int(max(return_lengths))
        limit = int(args.return_max_transition_len)
        return_payload["max_len"] = max_len
        if max_len > limit:
            fail(f"return max length {max_len} > {limit}")

    summary_path = primitive_vds_root / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        reject_counts = dict(summary.get("reject_counts", {}) or {})
        return_payload["reject_counts"] = {
            key: int(value)
            for key, value in reject_counts.items()
            if str(key).startswith("return:")
        }
        overlong = int(reject_counts.get("return:overlong_transition_len", 0))
        pose_realign = int(reject_counts.get("return:return_window_contains_pose_realign", 0))
        candidate_count = int(return_count + overlong + pose_realign)
        overlong_ratio = (
            float(overlong / candidate_count) if candidate_count > 0 else 0.0
        )
        return_payload["return_candidate_count"] = candidate_count
        return_payload["overlong_reject_ratio"] = overlong_ratio
        if overlong_ratio > float(args.return_max_overlong_reject_ratio):
            fail(
                "return overlong reject ratio "
                f"{overlong_ratio:.4f} > "
                f"{float(args.return_max_overlong_reject_ratio):.4f}"
            )
    else:
        return_payload["summary_json"] = "missing"

    payload["feedback_gate"] = _feedback_gate_payload(
        gate="gate1_primitive_vds_numeric_qc",
        passed=bool(payload.get("passed", False)),
        failed_checks=list(payload.get("failed_checks", []) or []),
        current_result={
            "root": str(primitive_vds_root),
            "primitives": payload.get("primitives", {}),
            "thresholds": payload.get("thresholds", {}),
        },
        next_step=(
            "continue_to_gate2_boundary_visual_review"
            if bool(payload.get("passed", False))
            else "pause_before_materialize_and_fix_builder_or_thresholds"
        ),
    )
    return payload


def _run_boundary_audit_gate_summary(paths: PipelinePaths) -> dict[str, Any]:
    audit_summary_path = paths.primitive_vds_root / "boundary_audit" / "summary.json"
    audit_payload: dict[str, Any] = {}
    if audit_summary_path.exists():
        audit_payload = json.loads(audit_summary_path.read_text(encoding="utf-8"))
    return _feedback_gate_payload(
        gate="gate2_boundary_visual_review",
        passed=False,
        failed_checks=["manual_visual_review_required"],
        current_result={
            "audit_summary_path": str(audit_summary_path),
            "audit": audit_payload,
        },
        next_step="human_review_boundary_videos_then_rerun_with_--ack-feedback-gates",
    )


def _feedback_gate_payload(
    *,
    gate: str,
    passed: bool,
    failed_checks: list[Any],
    current_result: dict[str, Any],
    next_step: str,
) -> dict[str, Any]:
    failed = [str(item) for item in failed_checks]
    return {
        "gate": str(gate),
        "status": "pass" if bool(passed) else "pause",
        "passed": bool(passed),
        "current_result": current_result,
        "deviation_from_expected": failed,
        "decision": "continue" if bool(passed) else "pause",
        "next_step": str(next_step),
        "review_required": not bool(passed),
        "written_at": _now(),
    }


def _next_training_gate(
    stage_name: str,
    train_stages: list[tuple[str, list[str]]],
) -> str:
    stage_names = [name for name, _ in train_stages]
    try:
        index = stage_names.index(stage_name)
    except ValueError:
        return "manual_review"
    if index + 1 < len(stage_names):
        return stage_names[index + 1]
    return "gate4_offline_combo_diagnostics"


def _run_stage(
    stage_name: str,
    command: list[str],
    *,
    paths: PipelinePaths,
    dry_run: bool,
    quiet: bool,
) -> None:
    log_path = paths.logs_dir / f"{stage_name}.log"
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    header = f"[{_now()}] RUN {' '.join(command)}\n"
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(header)
        log.flush()
        if not quiet:
            print(header, end="", flush=True)
        if dry_run:
            log.write(f"[{_now()}] DRY RUN\n")
            return
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            log.flush()
            if not quiet:
                print(line, end="", flush=True)
        rc = process.wait()
        log.write(f"[{_now()}] EXIT rc={rc}\n")
        log.flush()
        if rc != 0:
            raise SystemExit(f"{stage_name} failed with rc={rc}; see {log_path}")


def _cleanup_command(args: argparse.Namespace, paths: PipelinePaths) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "testbed.cli.cleanup_training_artifacts",
        "--delete",
        "--no-default-scan-roots",
        "--no-manifest-scan",
        "--no-default-ckpt-roots",
        "--primitive-copy-root",
        str(paths.primitive_copy_root),
        "--primitive-vds-root",
        str(paths.primitive_vds_root),
    ]
    dig_train_config = args.dig_train_config
    return_train_config = args.return_train_config
    if str(args.boundary_profile) == V2_4_5_BOUNDARY_PROFILE:
        if dig_train_config == DEFAULT_DIG_TRAIN_CONFIG:
            dig_train_config = DEFAULT_V2_4_5_DIG_TRAIN_CONFIG
        if return_train_config == DEFAULT_RETURN_TRAIN_CONFIG:
            return_train_config = DEFAULT_V2_4_5_RETURN_TRAIN_CONFIG
    config_paths = [dig_train_config, return_train_config]
    if str(args.boundary_profile) == V2_4_5_BOUNDARY_PROFILE:
        config_paths.extend([args.carry_train_config, args.dump_train_config])
    for config_path in config_paths:
        ckpt_dir = _train_config_ckpt_dir(config_path)
        if ckpt_dir is not None:
            command.extend(["--ckpt-dir", str(ckpt_dir)])
    return command


def _train_config_ckpt_dir(config_path: Path) -> Path | None:
    import yaml

    path = config_path if config_path.is_absolute() else ROOT / config_path
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return None
    train = dict(payload.get("train", {}) or {})
    ckpt_dir = train.get("ckpt_dir")
    if not ckpt_dir:
        return None
    return Path(str(ckpt_dir))


def _run_qc(primitive_copy_root: Path) -> dict[str, Any]:
    import h5py

    payload: dict[str, Any] = {"root": str(primitive_copy_root), "primitives": {}}
    for primitive in ("dig", "carry", "dump", "return"):
        root = primitive_copy_root / primitive
        episodes = sorted(root.glob("episode_*.hdf5"))
        item: dict[str, Any] = {"episode_count": len(episodes)}
        if episodes:
            with h5py.File(episodes[0], "r") as handle:
                image = handle["observations/images/fpv"]
                item["first_episode"] = str(episodes[0])
                item["image_virtual"] = bool(image.is_virtual)
                item["image_shape"] = list(image.shape)
                item["has_dig_outcome_targets"] = "v2/step/dig_outcome_targets" in handle
                item["has_return_outcome_targets"] = (
                    "v2/step/return_outcome_targets" in handle
                )
                item["storage_mode"] = str(handle["metadata"].attrs.get("storage_mode", ""))
                item["primitive_storage_mode"] = str(
                    handle["metadata"].attrs.get("primitive_storage_mode", "")
                )
        payload["primitives"][primitive] = item
    if payload["primitives"]["dig"]["episode_count"] <= 0:
        raise RuntimeError("QC failed: no dig primitive episodes")
    if payload["primitives"]["return"]["episode_count"] <= 0:
        raise RuntimeError("QC failed: no return primitive episodes")
    for primitive in ("dig", "return"):
        item = payload["primitives"][primitive]
        if item.get("image_virtual"):
            raise RuntimeError(f"QC failed: {primitive} first image dataset is still virtual")
    return payload


def _episode_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(
        path.glob("episode_*.hdf5"),
        key=lambda item: int(item.stem.split("_")[-1]),
    )


def _h5_training_tier(handle: Any) -> str:
    metadata = handle["metadata"].attrs if "metadata" in handle else handle.attrs
    tier = _h5_text(metadata.get("training_tier", ""))
    if tier:
        return tier
    if "v2/cycle/training_tier" in handle:
        data = handle["v2/cycle/training_tier"]
        if data.shape[0] > 0:
            return _h5_text(data[0])
    return ""


def _h5_depth_source(handle: Any) -> str:
    metadata = handle["metadata"].attrs if "metadata" in handle else handle.attrs
    source = _h5_text(metadata.get("depth_outcome_source", ""))
    if source:
        return source
    if "v2/cycle/depth_outcome_source" in handle:
        data = handle["v2/cycle/depth_outcome_source"]
        if data.shape[0] > 0:
            return _h5_text(data[0])
    return ""


def _h5_step_value(handle: Any, dataset_path: str, *, col: int) -> float | None:
    if dataset_path not in handle:
        return None
    data = handle[dataset_path]
    if data.ndim != 2 or data.shape[0] <= 0 or data.shape[1] <= col:
        return None
    value = float(data[0, col])
    return value if _finite(value) else None


def _h5_cycle_depth_m(handle: Any) -> float | None:
    if "v2/cycle/actual_removed_depth_delta_grid" not in handle:
        return None
    data = handle["v2/cycle/actual_removed_depth_delta_grid"]
    if data.shape[0] <= 0:
        return None
    import numpy as np

    value = float(np.max(np.asarray(data[0], dtype=np.float32)))
    return value if _finite(value) else None


def _h5_action_len(handle: Any) -> int:
    if "actions" in handle:
        return int(handle["actions"].shape[0])
    if "action" in handle:
        return int(handle["action"].shape[0])
    if "observations/qpos" in handle:
        return int(handle["observations/qpos"].shape[0])
    raise KeyError("episode is missing actions/action/observations/qpos")


def _h5_1d_array(handle: Any, dataset_path: str) -> Any | None:
    if dataset_path not in handle:
        return None
    import numpy as np

    data = np.asarray(handle[dataset_path])
    if data.ndim <= 0:
        return None
    return data.reshape(-1)


def _h5_1d_or_2d_array(handle: Any, dataset_path: str) -> Any | None:
    if dataset_path not in handle:
        return None
    import numpy as np

    data = np.asarray(handle[dataset_path])
    if data.ndim <= 0:
        return None
    return data


def _h5_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "item"):
        try:
            return _h5_text(value.item())
        except ValueError:
            pass
    return str(value)


def _numeric_stats(values: Iterable[float | int]) -> dict[str, Any] | None:
    import numpy as np

    arr = np.asarray(list(values), dtype=np.float32).reshape(-1)
    if arr.size <= 0:
        return None
    finite = arr[np.isfinite(arr)]
    if finite.size <= 0:
        return None
    return {
        "count": int(finite.size),
        "min": float(np.min(finite)),
        "p10": float(np.percentile(finite, 10)),
        "p50": float(np.percentile(finite, 50)),
        "p90": float(np.percentile(finite, 90)),
        "p95": float(np.percentile(finite, 95)),
        "p98": float(np.percentile(finite, 98)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "saturation_ge_0_999": float(np.mean(finite >= 0.999)),
        "nonzero_gt_1e_6": float(np.mean(np.abs(finite) > 1.0e-6)),
    }


def _finite(value: float) -> bool:
    import math

    return math.isfinite(float(value))


def _detach(args: argparse.Namespace) -> None:
    tag = _tag(args.tag)
    paths = _paths(args, tag)
    paths.job_dir.mkdir(parents=True, exist_ok=True)
    log_path = paths.job_dir / "pipeline.log"
    child_args = _argv_without_detach()
    if args.tag is None and "--tag" not in child_args:
        child_args.extend(["--tag", tag])
    command = [
        sys.executable,
        "-m",
        "testbed.cli.build_v2_4_hindsight_pipeline",
        *child_args,
    ]
    with open(log_path, "a", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    (paths.job_dir / "pipeline.pid").write_text(f"{process.pid}\n", encoding="utf-8")
    print(f"Started pipeline pid={process.pid}")
    print(f"Main log: {log_path}")
    print(f"Tail main log: tail -f {log_path}")
    print(f"Tail stage logs: tail -f {paths.logs_dir}/*.log")


def _argv_without_detach() -> list[str]:
    out: list[str] = []
    skip_next = False
    for item in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if item == "--detach":
            continue
        out.append(item)
    return out


def _write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    tag: str,
    paths: PipelinePaths,
    stages: Iterable[tuple[str, list[str], Path | None, str | None]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "tag": tag,
        "paths": {
            "job_dir": str(paths.job_dir),
            "logs_dir": str(paths.logs_dir),
            "relabeled_root": None if paths.relabeled_root is None else str(paths.relabeled_root),
            "operator_root": str(paths.operator_root),
            "hindsight_root": str(paths.hindsight_root),
            "primitive_vds_root": str(paths.primitive_vds_root),
            "primitive_copy_root": str(paths.primitive_copy_root),
        },
        "args": {
            key: _json_value(value)
            for key, value in sorted(vars(args).items())
            if key != "detach"
        },
        "stages": [
            {
                "name": name,
                "command": command,
                "output_path": None if output is None else str(output),
                "current_link": None if link is None else str(CURRENT_LINKS[link]),
            }
            for name, command, output, link in stages
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_stage_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _update_current_link(link_path: Path, target_path: Path) -> None:
    link_path = link_path
    if link_path.exists() or link_path.is_symlink():
        if not link_path.is_symlink():
            raise RuntimeError(f"Refusing to replace real directory/file current link: {link_path}")
        link_path.unlink()
    link_path.parent.mkdir(parents=True, exist_ok=True)
    relative = os.path.relpath(target_path.resolve(), start=link_path.parent.resolve())
    link_path.symlink_to(relative)


def _has_episode_files(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_file():
        return path.name.startswith("episode_") and path.suffix == ".hdf5"
    return any(path.rglob("episode_*.hdf5"))


def _log_user(paths: PipelinePaths, message: str) -> None:
    line = f"[{_now()}] {message}"
    print(line, flush=True)
    paths.job_dir.mkdir(parents=True, exist_ok=True)
    with open(paths.job_dir / "pipeline.log", "a", encoding="utf-8") as log:
        log.write(line + "\n")


def _tag(value: str | None) -> str:
    if value:
        return str(value)
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


if __name__ == "__main__":
    main()
