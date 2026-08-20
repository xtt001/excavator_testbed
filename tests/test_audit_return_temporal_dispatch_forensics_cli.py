from __future__ import annotations

from pathlib import Path

from testbed.cli import audit_return_temporal_dispatch_forensics as cli


def test_defaults_point_to_frozen_return_stability_artifact() -> None:
    args = cli.build_parser().parse_args([])

    assert args.return_stability_output_root == cli.DEFAULT_RETURN_STABILITY_OUTPUT_ROOT
    assert args.output_root == cli.DEFAULT_OUTPUT_ROOT
    assert args.device == "cuda"


def test_cli_accepts_explicit_paths_and_device() -> None:
    args = cli.build_parser().parse_args(
        [
            "--return-stability-output-root",
            "/tmp/stability",
            "--output-root",
            "/tmp/out",
            "--device",
            "cpu",
        ]
    )

    assert args.return_stability_output_root == Path("/tmp/stability")
    assert args.output_root == Path("/tmp/out")
    assert args.device == "cpu"
