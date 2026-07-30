from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest
import yaml

from testbed.data.handoff_envelope import (
    CARRY_START_ENVELOPE_FEATURE_ORDER,
    STRICT18_CARRY_TRAIN_SAMPLE_COUNT,
    build_carry_start_envelope,
)

STRICT18_TRAIN_SOURCES = (3, 6, 7, 8, 9, 13, 16, 19, 23, 24, 25, 27, 28, 29, 30, 32)


def _write_carry_episode(
    path: Path,
    *,
    episode_id: int,
    source_id: int,
    evidence_kind: str = "strict_parent_selected_replay",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    first = np.arange(13, dtype=np.float32) / 100.0 + float(episode_id)
    with h5py.File(path, "w") as handle:
        observations = handle.create_group("observations")
        observations.create_dataset(
            "qpos",
            data=np.stack((first[0:4], np.full(4, 9999.0, dtype=np.float32))),
        )
        observations.create_dataset(
            "qvel",
            data=np.stack((first[4:8], np.full(4, 9999.0, dtype=np.float32))),
        )
        env_first = np.zeros(89, dtype=np.float32)
        env_first[28:31] = first[8:11]
        env_first[8] = first[11]
        env_first[31] = first[12]
        observations.create_dataset(
            "env_state",
            data=np.stack((env_first, np.full(89, 9999.0, dtype=np.float32))),
        )
        metadata = handle.create_group("metadata")
        metadata.attrs["primitive_name"] = "carry"
        metadata.attrs["training_tier"] = "gold"
        metadata.attrs["storage_mode"] = "copy"
        metadata.attrs["source_episode_id"] = f"episode_{source_id}"
        metadata.attrs["composite_evidence_kind"] = evidence_kind
        metadata.attrs["composite_view_kind"] = "combined_strict_clean_vds"


def _write_strict18_fixture(tmp_path: Path) -> tuple[Path, Path]:
    dataset_dir = tmp_path / "primitives_copy" / "carry"
    train_ids = list(range(STRICT18_CARRY_TRAIN_SAMPLE_COUNT))
    val_ids = [STRICT18_CARRY_TRAIN_SAMPLE_COUNT, STRICT18_CARRY_TRAIN_SAMPLE_COUNT + 1]
    source_by_id = {
        episode_id: STRICT18_TRAIN_SOURCES[
            episode_id % len(STRICT18_TRAIN_SOURCES)
        ]
        for episode_id in train_ids
    }
    source_by_id.update({val_ids[0]: 33, val_ids[1]: 34})
    for episode_id in train_ids:
        _write_carry_episode(
            dataset_dir / f"episode_{episode_id}.hdf5",
            episode_id=episode_id,
            source_id=source_by_id[episode_id],
            evidence_kind=(
                "strict_salvage_addition"
                if episode_id == 94
                else "strict_parent_selected_replay"
            ),
        )

    split_path = tmp_path / "splits" / "carry_source_split.yaml"
    split_path.parent.mkdir(parents=True)
    split_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "split_policy": "source_identity_exact_allowlist_v1",
                "dataset_dir": str(dataset_dir),
                "available_episode_ids": train_ids + val_ids,
                "train_ids": train_ids,
                "val_ids": val_ids,
                "train_source_episode_ids": list(STRICT18_TRAIN_SOURCES),
                "val_source_episode_ids": [33, 34],
                "allowed_source_episode_ids": [
                    *STRICT18_TRAIN_SOURCES,
                    33,
                    34,
                ],
                "required_training_tier": "gold",
                "source_episode_id_by_primitive_episode_id": source_by_id,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return split_path, dataset_dir


def test_builder_uses_only_strict18_train_carry_first_frames(
    tmp_path: Path,
) -> None:
    split_path, dataset_dir = _write_strict18_fixture(tmp_path)
    output_path = tmp_path / "artifacts" / "carry_start_envelope_v1.json"

    written = build_carry_start_envelope(
        split_path=split_path,
        output_path=output_path,
    )

    assert written == output_path.resolve()
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["schema"] == "carry_start_envelope_v1"
    assert artifact["feature_order"] == list(CARRY_START_ENVELOPE_FEATURE_ORDER)
    assert artifact["sample_count"] == STRICT18_CARRY_TRAIN_SAMPLE_COUNT
    assert set(artifact["percentiles"]) == {"p01", "p50", "p99"}
    assert all(len(values) == 13 for values in artifact["percentiles"].values())
    assert artifact["percentiles"]["p01"][0] == pytest.approx(3.73)
    assert artifact["percentiles"]["p50"][0] == pytest.approx(186.5)
    assert artifact["percentiles"]["p99"][0] == pytest.approx(369.27)
    assert artifact["percentiles"]["p50"][12] == pytest.approx(186.62)
    assert max(artifact["percentiles"]["p99"]) < 1000.0

    lineage = artifact["source_lineage"]
    assert lineage["partition"] == "train"
    assert lineage["dataset_dir"] == str(dataset_dir.resolve())
    assert lineage["train_primitive_episode_ids"] == list(
        range(STRICT18_CARRY_TRAIN_SAMPLE_COUNT)
    )
    assert lineage["train_source_episode_ids"] == list(STRICT18_TRAIN_SOURCES)
    assert lineage["validation_source_episode_ids"] == [33, 34]
    assert len(lineage["source_episode_id_by_primitive_episode_id"]) == 374
    assert lineage["strict_evidence_kind_counts"] == {
        "strict_parent_selected_replay": 373,
        "strict_salvage_addition": 1,
    }
    assert len(artifact["split_sha256"]) == 64
    assert len(artifact["input_sha256"]) == 64


def test_builder_rejects_validation_source_in_train_partition(
    tmp_path: Path,
) -> None:
    split_path, _ = _write_strict18_fixture(tmp_path)
    split = yaml.safe_load(split_path.read_text(encoding="utf-8"))
    split["source_episode_id_by_primitive_episode_id"][0] = 33
    split_path.write_text(yaml.safe_dump(split, sort_keys=False), encoding="utf-8")
    output_path = tmp_path / "carry_start_envelope_v1.json"

    with pytest.raises(ValueError, match="validation source"):
        build_carry_start_envelope(
            split_path=split_path,
            output_path=output_path,
        )

    assert not output_path.exists()


def test_builder_rejects_partial_or_layered_salvage_dataset_path(
    tmp_path: Path,
) -> None:
    split_path, dataset_dir = _write_strict18_fixture(tmp_path)
    unsafe_dir = tmp_path / "partial_salvage" / "primitives_copy" / "carry"
    unsafe_dir.parent.mkdir(parents=True)
    dataset_dir.rename(unsafe_dir)
    split = yaml.safe_load(split_path.read_text(encoding="utf-8"))
    split["dataset_dir"] = str(unsafe_dir)
    split_path.write_text(yaml.safe_dump(split, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="partial/layered salvage"):
        build_carry_start_envelope(
            split_path=split_path,
            output_path=tmp_path / "carry_start_envelope_v1.json",
        )


def test_builder_is_strictly_no_overwrite(tmp_path: Path) -> None:
    split_path, _ = _write_strict18_fixture(tmp_path)
    output_path = tmp_path / "carry_start_envelope_v1.json"
    output_path.write_text('{"owner":"existing"}\n', encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build_carry_start_envelope(
            split_path=split_path,
            output_path=output_path,
        )

    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "owner": "existing"
    }
