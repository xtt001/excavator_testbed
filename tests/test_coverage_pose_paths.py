from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from testbed.data.coverage_pose_paths import (
    COVERAGE_POSE_PATH_LIBRARY_SCHEMA,
    QPOS_ORDER,
    build_coverage_pose_path_library,
)

DATA_ROOT = Path(
    "/data/pingfan/excavator_testbed_data/"
    "yulong_strict18_terrain_residual_v0"
)
DIG_PRIMITIVES = DATA_ROOT / "primitives_copy/dig"
SPLIT = DATA_ROOT / "splits/dig_source_split.yaml"
EXECUTION_LIBRARY = (
    DATA_ROOT / "qc/strict_train_coverage_execution_library_v1_1.json"
)
NORMALIZATION = Path(
    "/home/pingfan/AGXUnityE85ExcavatorSim/Assets/"
    "AGXUnity_Excavator/AGXUnity_Excavator_Assets/"
    "Calibration/YuLong_norm.json"
)
HAS_STRICT_INPUTS = all(
    path.is_file() if path.suffix else path.is_dir()
    for path in (
        DIG_PRIMITIVES,
        SPLIT,
        EXECUTION_LIBRARY,
        NORMALIZATION,
    )
)


@pytest.mark.skipif(
    not HAS_STRICT_INPUTS,
    reason="strict-18 materialized dig inputs are unavailable",
)
def test_pose_path_library_is_train_only_and_covers_execution_tail(
    tmp_path: Path,
) -> None:
    output = tmp_path / "strict_train_coverage_pose_paths_v1.json"

    returned = build_coverage_pose_path_library(
        dig_primitives_dir=DIG_PRIMITIVES,
        split_path=SPLIT,
        execution_library_path=EXECUTION_LIBRARY,
        normalization_path=NORMALIZATION,
        output_path=output,
    )

    assert returned == output.resolve()
    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert artifact["schema"] == COVERAGE_POSE_PATH_LIBRARY_SCHEMA
    assert artifact["status"] == "completed"
    assert artifact["sample_count"] == 374
    assert artifact["qpos_contract"]["order"] == list(QPOS_ORDER)
    assert artifact["qpos_contract"]["dim"] == 4
    assert artifact["source_lineage"]["train_source_episode_ids"] == [
        3,
        6,
        7,
        8,
        9,
        13,
        16,
        19,
        23,
        24,
        25,
        27,
        28,
        29,
        30,
        32,
    ]
    assert artifact["source_lineage"]["validation_source_episode_ids"] == [
        33,
        34,
    ]
    assert artifact["source_lineage"]["validation_rows_read"] == 0
    assert not {
        record["source_episode_id"] for record in artifact["records"]
    }.intersection({33, 34})

    episode_168 = next(
        record
        for record in artifact["records"]
        if record["exemplar_id"] == "episode_168"
    )
    assert episode_168["source_episode_id"] == 24
    assert episode_168["raw_fields_sha256"] == (
        "c167e087f3d41f6db8fe0ad260d5f72c3440b6fab9115fdf55959feacc50991c"
    )
    assert episode_168["first_valid_local_index"] == 0
    assert episode_168["last_valid_local_index"] == 150
    assert episode_168["token_peak_path_index"] == 33
    assert len(episode_168["qpos_path"]) == 151
    assert episode_168["qpos_path"][0] == episode_168["exemplar_start_qpos"]
    assert episode_168["path_includes_extraction_tail"] is True
    assert artifact["source_lock"]["normalization"]["sha256"] == (
        hashlib.sha256(NORMALIZATION.read_bytes()).hexdigest()
    )


@pytest.mark.skipif(
    not HAS_STRICT_INPUTS,
    reason="strict-18 materialized dig inputs are unavailable",
)
def test_pose_path_library_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "pose_paths.json"
    output.write_text("occupied", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build_coverage_pose_path_library(
            dig_primitives_dir=DIG_PRIMITIVES,
            split_path=SPLIT,
            execution_library_path=EXECUTION_LIBRARY,
            normalization_path=NORMALIZATION,
            output_path=output,
        )
