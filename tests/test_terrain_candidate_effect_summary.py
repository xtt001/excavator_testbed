from testbed.eval.terrain_candidate_effect_model import (
    build_geometric_swept_footprint_effect,
)
from testbed.eval.terrain_candidate_effect_summary import (
    build_candidate_effect_summary,
)


def _effect_record(
    *,
    candidate_id,
    expected_removed_volume_m3,
    target_removed_volume_m3,
    outside_target_removed_volume_m3,
    overdig_volume_delta_m3,
    footprint_cell_count=2,
    footprint_clipped_by_grid_boundary=False,
):
    return {
        "status": "present",
        "schema": "terrain_candidate_geometric_effect_v1",
        "source": "explicit_geometric_swept_footprint_effect",
        "offline_only": True,
        "candidate_id": candidate_id,
        "footprint": {
            "footprint_cell_count": footprint_cell_count,
            "footprint_clipped_by_grid_boundary": footprint_clipped_by_grid_boundary,
        },
        "summary_metrics": {
            "expected_removed_volume_m3": expected_removed_volume_m3,
            "target_removed_volume_m3": target_removed_volume_m3,
            "outside_target_removed_volume_m3": outside_target_removed_volume_m3,
            "overdig_volume_delta_m3": overdig_volume_delta_m3,
        },
    }


def test_build_candidate_effect_summary_reports_payload_proxy_and_rankings():
    result = build_candidate_effect_summary(
        [
            _effect_record(
                candidate_id="cut_candidate_a",
                expected_removed_volume_m3=0.03,
                target_removed_volume_m3=0.025,
                outside_target_removed_volume_m3=0.005,
                overdig_volume_delta_m3=0.002,
                footprint_cell_count=2,
            ),
            _effect_record(
                candidate_id="cut_candidate_b",
                expected_removed_volume_m3=0.07,
                target_removed_volume_m3=0.05,
                outside_target_removed_volume_m3=0.02,
                overdig_volume_delta_m3=0.015,
                footprint_cell_count=4,
                footprint_clipped_by_grid_boundary=True,
            ),
            _effect_record(
                candidate_id="cut_candidate_c",
                expected_removed_volume_m3=0.0,
                target_removed_volume_m3=0.0,
                outside_target_removed_volume_m3=0.0,
                overdig_volume_delta_m3=0.0,
                footprint_cell_count=0,
            ),
        ],
        payload_capacity_m3=0.04,
    )

    assert result["status"] == "present"
    assert result["schema"] == "terrain_candidate_effect_summary_v1"
    assert result["source"] == "explicit_candidate_effect_summary"
    assert result["offline_only"] is True
    assert result["effect_record_count"] == 3
    assert result["payload_capacity_m3"] == 0.04
    assert [record["candidate_id"] for record in result["summary_records"]] == [
        "cut_candidate_a",
        "cut_candidate_b",
        "cut_candidate_c",
    ]
    assert result["summary_records"][0] == {
        "candidate_id": "cut_candidate_a",
        "input_index": 0,
        "effect_status": "present",
        "offline_only": True,
        "expected_removed_volume_m3": 0.03,
        "target_removed_volume_m3": 0.025,
        "outside_target_removed_volume_m3": 0.005,
        "overdig_volume_delta_m3": 0.002,
        "footprint_cell_count": 2,
        "footprint_clipped_by_grid_boundary": False,
        "payload_proxy_volume_m3": 0.03,
        "payload_proxy_fraction": 0.75,
        "outside_target_volume_fraction": 0.166666666667,
        "overdig_volume_fraction": 0.066666666667,
    }
    assert result["summary_records"][1]["payload_proxy_volume_m3"] == 0.04
    assert result["summary_records"][1]["payload_proxy_fraction"] == 1.0
    assert result["summary_records"][2]["outside_target_volume_fraction"] is None
    assert result["summary_records"][2]["overdig_volume_fraction"] is None
    assert result["aggregate_summary"] == {
        "effect_record_count": 3,
        "payload_proxy_volume_min_m3": 0.0,
        "payload_proxy_volume_max_m3": 0.04,
        "payload_proxy_volume_mean_m3": 0.023333333333,
        "payload_proxy_fraction_min": 0.0,
        "payload_proxy_fraction_max": 1.0,
        "payload_proxy_fraction_mean": 0.583333333333,
        "expected_removed_volume_total_m3": 0.1,
        "target_removed_volume_total_m3": 0.075,
        "outside_target_removed_volume_total_m3": 0.025,
        "overdig_volume_delta_total_m3": 0.017,
        "max_payload_proxy_candidate_id": "cut_candidate_b",
        "max_outside_target_volume_candidate_id": "cut_candidate_b",
        "max_overdig_volume_candidate_id": "cut_candidate_b",
    }
    assert result["diagnostic_rankings"]["semantics"] == (
        "diagnostic_offline_ranking_only"
    )
    assert result["diagnostic_rankings"]["no_production_action"] is True
    assert [
        item["candidate_id"]
        for item in result["diagnostic_rankings"]["payload_proxy_desc"]
    ] == ["cut_candidate_b", "cut_candidate_a", "cut_candidate_c"]
    assert [
        item["candidate_id"]
        for item in result["diagnostic_rankings"]["outside_target_volume_desc"]
    ] == ["cut_candidate_b", "cut_candidate_a", "cut_candidate_c"]
    assert [
        item["candidate_id"]
        for item in result["diagnostic_rankings"]["overdig_volume_desc"]
    ] == ["cut_candidate_b", "cut_candidate_a", "cut_candidate_c"]
    assert "selected" not in result["diagnostic_rankings"]
    assert "top_k" not in result["diagnostic_rankings"]


def test_build_candidate_effect_summary_handles_empty_records_without_defaults():
    result = build_candidate_effect_summary([], payload_capacity_m3=0.04)

    assert result["status"] == "no_effect_records"
    assert result["effect_record_count"] == 0
    assert result["payload_capacity_m3"] == 0.04
    assert result["summary_records"] == []
    assert result["aggregate_summary"]["effect_record_count"] == 0
    assert result["diagnostic_rankings"]["payload_proxy_desc"] == []


def test_build_candidate_effect_summary_rejects_invalid_payload_capacity():
    assert (
        build_candidate_effect_summary([], payload_capacity_m3=0.0)["status"]
        == "invalid_payload_capacity"
    )
    assert (
        build_candidate_effect_summary([], payload_capacity_m3="bad")["status"]
        == "invalid_payload_capacity"
    )


def test_build_candidate_effect_summary_rejects_invalid_effect_records():
    assert (
        build_candidate_effect_summary(
            [{"candidate_id": "missing_effect_fields"}],
            payload_capacity_m3=0.04,
        )["status"]
        == "invalid_effect_records"
    )
    assert (
        build_candidate_effect_summary(
            [
                _effect_record(
                    candidate_id="cut_candidate_bad",
                    expected_removed_volume_m3=-0.1,
                    target_removed_volume_m3=0.0,
                    outside_target_removed_volume_m3=0.0,
                    overdig_volume_delta_m3=0.0,
                )
            ],
            payload_capacity_m3=0.04,
        )["status"]
        == "invalid_effect_records"
    )


def test_build_candidate_effect_summary_accepts_phase4a_effect_records():
    effect = build_geometric_swept_footprint_effect(
        candidate={
            "candidate_id": "cut_candidate_from_effect",
            "anchor_cell_index": 0,
            "anchor_row": 0,
            "anchor_col": 0,
            "direction": "row_forward",
            "candidate_depth_m": 0.2,
            "offline_only": True,
        },
        removed_depth_grid_m=[0.0, 0.0, 0.0, 0.0],
        target_depth_grid_m=[0.25, 0.25, 0.0, 0.0],
        target_region_mask=[True, True, False, False],
        valid_mask=[True, True, True, True],
        grid_shape=[2, 2],
        cell_size_m=0.5,
        bucket_width_m=0.5,
        bucket_length_m=0.5,
    )

    result = build_candidate_effect_summary([effect], payload_capacity_m3=0.2)

    assert result["status"] == "present"
    assert result["effect_record_count"] == 1
    assert result["summary_records"][0]["candidate_id"] == (
        "cut_candidate_from_effect"
    )
    assert result["summary_records"][0]["payload_proxy_volume_m3"] == 0.1
