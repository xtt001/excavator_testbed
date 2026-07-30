from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from testbed.cli.build_surface_depth_planner_prior import (
    load_split_episode_ids,
    write_surface_depth_planner_prior_outputs,
)


def test_load_split_episode_ids_selects_requested_partition(tmp_path: Path) -> None:
    split_path = tmp_path / "dig_source_split.yaml"
    split_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "split_policy": "source_identity_exact_allowlist_v1",
                "train_ids": [0, 2, 4],
                "val_ids": [5, 7],
            }
        ),
        encoding="utf-8",
    )

    ids, provenance = load_split_episode_ids(split_path, partition="train")

    assert ids == (0, 2, 4)
    assert provenance == {
        "split_path": str(split_path.resolve()),
        "partition": "train",
        "primitive_episode_count": 3,
        "split_policy": "source_identity_exact_allowlist_v1",
    }


def test_load_split_episode_ids_rejects_overlap(tmp_path: Path) -> None:
    split_path = tmp_path / "return_source_split.yaml"
    split_path.write_text(
        yaml.safe_dump({"train_ids": [0, 1], "val_ids": [1, 2]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="split_partition_overlap"):
        load_split_episode_ids(split_path, partition="train")


def test_prior_output_writer_is_no_overwrite(tmp_path: Path) -> None:
    prior_path = tmp_path / "prior.json"
    state_path = tmp_path / "state.json"
    write_surface_depth_planner_prior_outputs(
        prior={"prior_id": "test"},
        state_payload={"exemplar_count": 0},
        prior_path=prior_path,
        state_exemplar_path=state_path,
    )

    assert json.loads(prior_path.read_text(encoding="utf-8"))["prior_id"] == "test"
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_surface_depth_planner_prior_outputs(
            prior={"prior_id": "replacement"},
            state_payload={"exemplar_count": 1},
            prior_path=prior_path,
            state_exemplar_path=state_path,
        )
