from __future__ import annotations

from pathlib import Path

from testbed.cli import audit_return_temporal_dispatch_validation as cli


def test_defaults_use_frozen_checkpoint_lineage_and_new_root() -> None:
    args = cli.build_parser().parse_args([])

    assert args.return_training_config == cli.DEFAULT_RETURN_TRAINING_CONFIG
    assert args.checkpoint_lineage_manifest == cli.DEFAULT_CHECKPOINT_LINEAGE_MANIFEST
    assert args.output_root == cli.DEFAULT_OUTPUT_ROOT
    assert args.device == "cuda"


def test_cli_accepts_explicit_paths() -> None:
    args = cli.build_parser().parse_args(
        [
            "--return-training-config",
            "testbed/configs/return.yaml",
            "--checkpoint-lineage-manifest",
            "/tmp/lineage.json",
            "--output-root",
            "/tmp/out",
            "--device",
            "cpu",
        ]
    )

    assert args.return_training_config == Path("testbed/configs/return.yaml")
    assert args.checkpoint_lineage_manifest == Path("/tmp/lineage.json")
    assert args.output_root == Path("/tmp/out")
    assert args.device == "cpu"
