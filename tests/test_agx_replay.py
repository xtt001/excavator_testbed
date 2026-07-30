import unittest
from pathlib import Path

import numpy as np

from testbed.cli.replay import (
    _build_arg_parser,
    _env_state_snapshot,
    _resolve_gold_cycle_target_ids,
    _resolve_post_tail_steps,
    _validate_diagnostic_log_args,
    _validate_gold_cycle_sample_args,
    _validate_selection_config_args,
)


class ReplayRefreshConfigTests(unittest.TestCase):
    def test_diagnostic_snapshot_exposes_typed_wall_contact_lineage(self) -> None:
        env_state = np.zeros(107, dtype=np.float32)
        env_state[101:104] = [1.0, 12_345.0, 2.0]

        snapshot = _env_state_snapshot(env_state)

        self.assertEqual(snapshot["excavator_wall_contact_typed_mask"], 1.0)
        self.assertEqual(
            snapshot["excavator_wall_contact_step_max_force_n"],
            12_345.0,
        )
        self.assertEqual(
            snapshot["excavator_wall_contact_session_count"],
            2.0,
        )

    def test_record_refresh_uses_configured_tail_by_default(self) -> None:
        self.assertEqual(
            _resolve_post_tail_steps(
                explicit_value=None,
                teleop_cfg={"post_success_tail_steps": 50},
                record_output_dir="data/out",
            ),
            50,
        )

    def test_explicit_tail_overrides_config(self) -> None:
        self.assertEqual(
            _resolve_post_tail_steps(
                explicit_value=12,
                teleop_cfg={"post_success_tail_steps": 50},
                record_output_dir="data/out",
            ),
            12,
        )

    def test_plain_qa_replay_keeps_zero_tail_by_default(self) -> None:
        self.assertEqual(
            _resolve_post_tail_steps(
                explicit_value=None,
                teleop_cfg={"post_success_tail_steps": 50},
                record_output_dir=None,
            ),
            0,
        )

    def test_replay_parser_accepts_gold_cycle_sample_jsonl_output(self) -> None:
        args = _build_arg_parser().parse_args(
            [
                "--episode",
                "data/source/episode_0.hdf5",
                "--gold-cycle-samples-jsonl",
                "runs/replay/gold_cycle_samples.jsonl",
                "--gold-cycle-samples-target-id",
                "t1_large_shallow_rectangular_pit_default",
                "--gold-cycle-samples-low-payload-kg",
                "30.0",
            ]
        )

        self.assertEqual(args.episode, Path("data/source/episode_0.hdf5"))
        self.assertEqual(
            args.gold_cycle_samples_jsonl,
            Path("runs/replay/gold_cycle_samples.jsonl"),
        )
        self.assertEqual(
            args.gold_cycle_samples_target_id,
            "t1_large_shallow_rectangular_pit_default",
        )
        self.assertEqual(args.gold_cycle_samples_low_payload_kg, 30.0)

    def test_replay_parser_accepts_explicit_terrain_diagnostic_mode(self) -> None:
        args = _build_arg_parser().parse_args(
            [
                "--episode",
                "data/source/episode_0.hdf5",
                "--diagnostic-terrain-mode",
                "no_dynamic_mass",
            ]
        )

        self.assertEqual(args.diagnostic_terrain_mode, "no_dynamic_mass")

    def test_replay_parser_accepts_recording_control_compatibility_profile(self) -> None:
        args = _build_arg_parser().parse_args(
            [
                "--selection-manifest",
                "data/calibrated_replay_selection.jsonl",
                "--selection-profile",
                "calibrated_mixed_current_equivalent",
                "--control-compatibility-profile",
                "recording_pre_fix_v1",
            ]
        )

        self.assertEqual(
            args.control_compatibility_profile, "recording_pre_fix_v1"
        )

    def test_corrected_selection_realign_requires_explicit_evidence_profile(self) -> None:
        parser = _build_arg_parser()
        args = parser.parse_args(
            [
                "--selection-manifest",
                "selection.jsonl",
                "--selection-profile",
                "calibrated_mixed_current_equivalent",
                "--selection-episode-id",
                "episode_14",
                "--config",
                "config.yaml",
                "--record-output-dir",
                "recorded",
                "--diagnostic-log",
                "diagnostics.jsonl",
                "--realign-on-qpos-error",
                "--replay-evidence-profile",
                "replay_corrected_partial_salvage_v1",
            ]
        )

        assert args.replay_evidence_profile == (
            "replay_corrected_partial_salvage_v1"
        )

    def test_replay_parser_accepts_selection_episode_subset(self) -> None:
        args = _build_arg_parser().parse_args(
            [
                "--selection-manifest",
                "data/post_fix_replay_selection.jsonl",
                "--selection-episode-id",
                "episode_23",
                "--selection-episode-id",
                "episode_24",
            ]
        )

        self.assertEqual(args.selection_episode_id, ["episode_23", "episode_24"])

    def test_replay_parser_accepts_calibrated_selection_profile(self) -> None:
        args = _build_arg_parser().parse_args(
            [
                "--selection-manifest",
                "data/calibrated_replay_selection.jsonl",
                "--selection-profile",
                "calibrated_mixed_current_equivalent",
            ]
        )

        self.assertEqual(
            args.selection_profile, "calibrated_mixed_current_equivalent"
        )

    def test_replay_parser_keeps_legacy_post_fix_profile_default(self) -> None:
        args = _build_arg_parser().parse_args(
            ["--selection-manifest", "data/post_fix_replay_selection.jsonl"]
        )

        self.assertEqual(args.selection_profile, "post_fix_raw")

    def test_selection_replay_requires_explicit_recording_config(self) -> None:
        self.assertEqual(
            _validate_selection_config_args(
                selection_manifest=Path("selection.jsonl"),
                config_path=None,
            ),
            ["--selection-manifest requires the explicit recording --config."],
        )
        self.assertEqual(
            _validate_selection_config_args(
                selection_manifest=Path("selection.jsonl"),
                config_path=Path("teleop_yulong.yaml"),
            ),
            [],
        )

    def test_gold_cycle_sample_args_require_target_and_no_overwrite(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "gold_cycle_samples.jsonl"

            self.assertEqual(
                _validate_gold_cycle_sample_args(
                    output_path=output_path,
                    target_id="t1_large_shallow_rectangular_pit_default",
                ),
                [],
            )
            self.assertEqual(
                _validate_gold_cycle_sample_args(
                    output_path=output_path,
                    target_id=None,
                ),
                [
                    "--gold-cycle-samples-target-id is required with "
                    "--gold-cycle-samples-jsonl"
                ],
            )

            output_path.write_text("", encoding="utf-8")

            self.assertEqual(
                _validate_gold_cycle_sample_args(
                    output_path=output_path,
                    target_id="t1_large_shallow_rectangular_pit_default",
                ),
                [f"Gold cycle sample JSONL already exists: {output_path}"],
            )

    def test_selection_replay_emits_diagnostic_t1_and_t2_targets(self) -> None:
        self.assertEqual(
            _resolve_gold_cycle_target_ids(
                target_id=None,
                use_replay_target_set=True,
            ),
            (
                "recording_depth_0p08_full_grid_diagnostic",
                "t1_large_shallow_rectangular_pit_default",
                "t2_long_shallow_trench_default",
            ),
        )

    def test_diagnostic_logs_are_no_overwrite_for_single_and_batch(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episode_0 = root / "episode_0.hdf5"
            episode_1 = root / "episode_1.hdf5"
            single_log = root / "single.jsonl"
            batch_dir = root / "diagnostics"

            self.assertEqual(
                _validate_diagnostic_log_args(single_log, [episode_0]),
                [],
            )
            single_log.write_text("existing\n", encoding="utf-8")
            self.assertEqual(
                _validate_diagnostic_log_args(single_log, [episode_0]),
                [f"Replay diagnostic JSONL already exists: {single_log}"],
            )

            batch_dir.mkdir()
            existing_batch_log = batch_dir / "episode_1_diagnostics.jsonl"
            existing_batch_log.write_text("existing\n", encoding="utf-8")
            self.assertEqual(
                _validate_diagnostic_log_args(
                    batch_dir,
                    [episode_0, episode_1],
                ),
                [f"Replay diagnostic JSONL already exists: {existing_batch_log}"],
            )


if __name__ == "__main__":
    unittest.main()
