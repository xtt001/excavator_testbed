import unittest

from testbed.cli.replay import _resolve_post_tail_steps


class ReplayRefreshConfigTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
