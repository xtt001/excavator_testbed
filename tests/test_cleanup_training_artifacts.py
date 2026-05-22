from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from testbed.cli.cleanup_training_artifacts import cleanup_training_artifacts


class CleanupTrainingArtifactsTests(unittest.TestCase):
    def test_delete_removes_copy_nonbest_ckpts_and_current_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            copy_root = root / "toy_primitives_copy_tag"
            vds_root = root / "toy_primitives_vds_tag"
            (copy_root / "dig").mkdir(parents=True)
            (vds_root / "dig").mkdir(parents=True)
            (copy_root / "dig" / "episode_0.hdf5").write_text("copy")
            (vds_root / "dig" / "episode_0.hdf5").write_text("vds")

            link_root = root / "data"
            link_root.mkdir()
            (link_root / "toy_primitives_copy").symlink_to(copy_root)

            ckpt_dir = root / "ckpts"
            ckpt_dir.mkdir()
            (ckpt_dir / "policy_best.ckpt").write_text("best")
            (ckpt_dir / "policy_latest.ckpt").write_text("latest")
            (ckpt_dir / "policy_epoch_0_seed_0.ckpt").write_text("epoch")

            summary = cleanup_training_artifacts(
                delete=True,
                primitive_copy_roots=[copy_root],
                primitive_vds_roots=[vds_root],
                copy_scan_roots=[],
                manifest_roots=[],
                ckpt_dirs=[ckpt_dir],
                ckpt_roots=[],
                symlink_roots=[link_root],
            )

            self.assertFalse(copy_root.exists())
            self.assertTrue(vds_root.exists())
            self.assertFalse((link_root / "toy_primitives_copy").exists())
            self.assertTrue((ckpt_dir / "policy_best.ckpt").exists())
            self.assertFalse((ckpt_dir / "policy_latest.ckpt").exists())
            self.assertFalse((ckpt_dir / "policy_epoch_0_seed_0.ckpt").exists())
            self.assertEqual(len(summary["primitive_copies"]["removed"]), 1)
            self.assertEqual(len(summary["checkpoints"]["removed"]), 2)
            self.assertEqual(len(summary["symlinks"]["removed"]), 1)

    def test_dry_run_discovers_by_name_without_removing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            copy_root = root / "toy_primitives_copy_tag"
            vds_root = root / "toy_primitives_vds_tag"
            (copy_root / "return").mkdir(parents=True)
            (vds_root / "return").mkdir(parents=True)
            (copy_root / "return" / "episode_0.hdf5").write_text("copy")
            (vds_root / "return" / "episode_0.hdf5").write_text("vds")

            ckpt_root = root / "runs" / "ckpts" / "run"
            ckpt_root.mkdir(parents=True)
            (ckpt_root / "policy_best.ckpt").write_text("best")
            (ckpt_root / "policy_last.ckpt").write_text("last")

            summary = cleanup_training_artifacts(
                delete=False,
                copy_scan_roots=[root],
                manifest_roots=[],
                ckpt_dirs=[],
                ckpt_roots=[root / "runs" / "ckpts"],
                symlink_roots=[],
            )

            self.assertTrue(copy_root.exists())
            self.assertTrue(vds_root.exists())
            self.assertTrue((ckpt_root / "policy_last.ckpt").exists())
            self.assertEqual(len(summary["primitive_copies"]["candidates"]), 1)
            self.assertEqual(len(summary["checkpoints"]["candidates"]), 1)


if __name__ == "__main__":
    unittest.main()
