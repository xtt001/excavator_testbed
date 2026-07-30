from __future__ import annotations

from pathlib import Path

import cv2
import h5py
import numpy as np
import pytest
import yaml

from testbed.data.hdf5_io import write_episode
from testbed.data.terrain_replay_dataset import REPLAY_CAMERA_NAMES
from testbed.data.vds import _canonical_hdf5_text
from testbed.eval.terrain_replay_salvage_views import (
    build_composite_clean_vds,
    rebuild_strict_composite_clean_vds,
    write_salvage_training_configs,
)


def _jpeg(value: int) -> np.ndarray:
    rgb = np.full((6, 8, 3), value, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return encoded.reshape(-1)


def _write_clean_episode(path: Path, *, value: float) -> None:
    steps = 4
    encoded = {
        camera: [_jpeg(int(value) + step) for step in range(steps)]
        for camera in REPLAY_CAMERA_NAMES
    }
    write_episode(
        path,
        qpos=np.full((steps, 4), value, dtype=np.float32),
        qvel=np.zeros((steps, 4), dtype=np.float32),
        actions=np.full((steps, 4), value / 10.0, dtype=np.float32),
        env_state=np.full((steps, 89), value, dtype=np.float32),
        encoded_images=encoded,
        step_ids=np.arange(steps, dtype=np.int64),
        v2={
            "step": {"action_loss_mask": np.ones(steps, dtype=np.uint8)},
            "cycle": {
                "cycle_id": np.asarray([0], dtype=np.int64),
                "start_step": np.asarray([1], dtype=np.int64),
                "dump_end_step": np.asarray([2], dtype=np.int64),
            },
        },
        metadata={"evidence_kind": "source", "control_hz": 50.0},
    )
    with h5py.File(path, "a") as handle:
        handle["action"].attrs["units"] = "normalized_speed"
        handle["v2/cycle/start_step"].attrs["semantics"] = "qualified_contact"
        string_dtype = h5py.string_dtype(encoding="utf-8")
        handle["v2/cycle"].create_dataset(
            "training_tier",
            data=np.asarray(["gold"], dtype=object),
            dtype=string_dtype,
        )


def test_composite_vds_preserves_nested_v2_89d_jpeg_attrs_and_precedence(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    addition = tmp_path / "addition"
    parent.mkdir()
    addition.mkdir()
    _write_clean_episode(parent / "episode_3.hdf5", value=3.0)
    _write_clean_episode(parent / "episode_4.hdf5", value=40.0)
    _write_clean_episode(addition / "episode_4.hdf5", value=4.0)

    output = tmp_path / "combined"
    report = build_composite_clean_vds(
        output_dir=output,
        source_by_episode={
            3: parent / "episode_3.hdf5",
            4: addition / "episode_4.hdf5",
        },
        evidence_by_episode={3: "strict_parent", 4: "strict_addition"},
        view_kind="combined_strict_clean_vds",
    )

    assert report["episode_ids"] == [3, 4]
    with h5py.File(output / "episode_4.hdf5", "r") as handle:
        assert handle["observations/env_state"].shape == (4, 89)
        assert set(handle["observations/encoded_images"].keys()) == set(
            REPLAY_CAMERA_NAMES
        )
        np.testing.assert_array_equal(handle["v2/cycle/cycle_id"][()], [0])
        assert handle["action"].attrs["units"] == "normalized_speed"
        assert (
            handle["v2/cycle/start_step"].attrs["semantics"]
            == "qualified_contact"
        )
        assert handle["metadata"].attrs["composite_evidence_kind"] == (
            "strict_addition"
        )
        assert handle["observations/qpos"][0, 0] == pytest.approx(4.0)

    with pytest.raises(FileExistsError, match="no-overwrite"):
        build_composite_clean_vds(
            output_dir=output,
            source_by_episode={3: parent / "episode_3.hdf5"},
            evidence_by_episode={3: "strict_parent"},
            view_kind="combined_strict_clean_vds",
        )


def test_composite_vds_canonicalizes_repeated_bytes_literal_wrapping(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_clean_episode(source / "episode_3.hdf5", value=3.0)
    with h5py.File(source / "episode_3.hdf5", "a") as handle:
        del handle["v2/cycle/training_tier"]
        string_dtype = h5py.string_dtype(encoding="utf-8")
        handle["v2/cycle"].create_dataset(
            "training_tier",
            data=np.asarray(["b\"b'gold'\""], dtype=object),
            dtype=string_dtype,
        )

    first = tmp_path / "first"
    build_composite_clean_vds(
        output_dir=first,
        source_by_episode={3: source / "episode_3.hdf5"},
        evidence_by_episode={3: "strict_parent"},
        view_kind="combined_strict_clean_vds",
    )
    second = tmp_path / "second"
    build_composite_clean_vds(
        output_dir=second,
        source_by_episode={3: first / "episode_3.hdf5"},
        evidence_by_episode={3: "strict_parent"},
        view_kind="combined_strict_clean_vds",
    )

    with h5py.File(second / "episode_3.hdf5", "r") as handle:
        assert handle["v2/cycle/training_tier"].asstr()[()].tolist() == ["gold"]


def test_vds_text_codec_rejects_unparseable_or_more_than_four_wrappers() -> None:
    four_wrappers = "gold"
    for _ in range(4):
        four_wrappers = repr(four_wrappers.encode("utf-8"))
    assert _canonical_hdf5_text(four_wrappers) == "gold"

    five_wrappers = repr(four_wrappers.encode("utf-8"))
    with pytest.raises(ValueError, match="more than 4 nested bytes literals"):
        _canonical_hdf5_text(five_wrappers)
    with pytest.raises(ValueError, match="cannot be canonicalized"):
        _canonical_hdf5_text("b'not-closed")


def test_strict_rebuild_requires_exact_source_identity_allowlist(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_clean_episode(source / "episode_3.hdf5", value=3.0)
    _write_clean_episode(source / "episode_4.hdf5", value=4.0)
    source_view = tmp_path / "source_view"
    build_composite_clean_vds(
        output_dir=source_view,
        source_by_episode={
            3: source / "episode_3.hdf5",
            4: source / "episode_4.hdf5",
        },
        evidence_by_episode={3: "strict_parent", 4: "strict_addition"},
        view_kind="combined_strict_clean_vds",
    )

    rejected_output = tmp_path / "rejected"
    with pytest.raises(ValueError, match="exactly match the strict allowlist"):
        rebuild_strict_composite_clean_vds(
            source_view_dir=source_view,
            output_dir=rejected_output,
            strict_episode_ids=(3,),
        )
    assert not rejected_output.exists()

    accepted_output = tmp_path / "accepted"
    report = rebuild_strict_composite_clean_vds(
        source_view_dir=source_view,
        output_dir=accepted_output,
        strict_episode_ids=(3, 4),
    )
    assert report["episode_ids"] == [3, 4]
    assert sorted(path.name for path in accepted_output.glob("episode_*.hdf5")) == [
        "episode_3.hdf5",
        "episode_4.hdf5",
    ]


def test_strict_and_salvage_training_configs_never_silently_enable_partial(
    tmp_path: Path,
) -> None:
    combined = tmp_path / "combined"
    layered = tmp_path / "layered"
    combined.mkdir()
    layered.mkdir()

    paths = write_salvage_training_configs(
        output_root=tmp_path,
        combined_strict_dir=combined,
        layered_salvage_dir=layered,
        strict_episode_ids=(3, 33, 34),
        layered_episode_ids=(1, 3, 33, 34),
    )

    strict = yaml.safe_load(paths["strict"].read_text(encoding="utf-8"))
    salvage = yaml.safe_load(paths["salvage"].read_text(encoding="utf-8"))
    assert strict["default_enabled"] is False
    assert strict["val_ids"] == [33, 34]
    assert salvage["default_enabled"] is False
    assert salvage["usage"] == "partial_replay_salvage_ablation_only"
    assert salvage["gold_status"] == "not_gold"

    resumed_paths = write_salvage_training_configs(
        output_root=tmp_path,
        combined_strict_dir=combined,
        layered_salvage_dir=layered,
        strict_episode_ids=(3, 33, 34),
        layered_episode_ids=(1, 3, 33, 34),
    )
    assert resumed_paths == paths
