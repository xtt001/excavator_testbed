from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from testbed.data.primitive_source_split import write_primitive_source_splits

PRIMITIVES = ("dig", "carry", "dump", "return")


def _write_primitive_fixture(
    root: Path,
    *,
    source_episode_ids: tuple[int, ...],
    training_tiers: tuple[str, ...] | None = None,
) -> None:
    tiers = training_tiers or tuple("gold" for _ in source_episode_ids)
    assert len(tiers) == len(source_episode_ids)
    rows = []
    for primitive_name in PRIMITIVES:
        primitive_dir = root / primitive_name
        primitive_dir.mkdir(parents=True, exist_ok=True)
        for primitive_episode_id, (source_episode_id, training_tier) in enumerate(
            zip(source_episode_ids, tiers, strict=True)
        ):
            (primitive_dir / f"episode_{primitive_episode_id}.hdf5").touch()
            rows.append(
                {
                    "primitive_name": primitive_name,
                    "primitive_episode_id": primitive_episode_id,
                    "source_episode_id": f"episode_{source_episode_id}",
                    "training_tier": training_tier,
                }
            )
    (root / "window_manifest.json").write_text(
        json.dumps(rows, indent=2) + "\n",
        encoding="utf-8",
    )


def test_primitive_split_uses_source_identity_without_leakage(tmp_path: Path) -> None:
    primitive_root = tmp_path / "primitives"
    _write_primitive_fixture(
        primitive_root,
        source_episode_ids=(3, 3, 7, 33, 34),
        training_tiers=("gold", "silver", "gold", "gold", "gold"),
    )

    output_dir = tmp_path / "splits"
    paths = write_primitive_source_splits(
        primitive_root=primitive_root,
        output_dir=output_dir,
        train_source_episode_ids=(3, 7),
        val_source_episode_ids=(33, 34),
    )

    assert set(paths) == set(PRIMITIVES)
    for primitive_name in PRIMITIVES:
        split = yaml.safe_load(paths[primitive_name].read_text(encoding="utf-8"))
        assert split["available_episode_ids"] == [0, 2, 3, 4]
        assert split["train_ids"] == [0, 2]
        assert split["val_ids"] == [3, 4]
        assert split["required_training_tier"] == "gold"
        assert split["train_source_episode_ids"] == [3, 7]
        assert split["val_source_episode_ids"] == [33, 34]
        assert not set(split["train_ids"]) & set(split["val_ids"])
        source_by_episode = {
            int(key): value
            for key, value in split[
                "source_episode_id_by_primitive_episode_id"
            ].items()
        }
        assert {source_by_episode[index] for index in split["train_ids"]} == {3, 7}
        assert {source_by_episode[index] for index in split["val_ids"]} == {33, 34}


def test_primitive_split_rejects_sources_outside_exact_allowlist(
    tmp_path: Path,
) -> None:
    primitive_root = tmp_path / "primitives"
    _write_primitive_fixture(
        primitive_root,
        source_episode_ids=(3, 7, 33, 34, 99),
    )

    output_dir = tmp_path / "splits"
    with pytest.raises(ValueError, match="exactly match the split allowlist"):
        write_primitive_source_splits(
            primitive_root=primitive_root,
            output_dir=output_dir,
            train_source_episode_ids=(3, 7),
            val_source_episode_ids=(33, 34),
        )
    assert not output_dir.exists()
