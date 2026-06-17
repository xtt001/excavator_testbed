"""Evaluate PrimitivePlannerACTPolicy through the shadow action-tree runner.

This entry point is experimental and shadow-only. It intentionally reuses the
normal eval CLI arguments and patches PrimitivePlannerACTPolicy.predict only for
the lifetime of this process.
"""

from __future__ import annotations

from testbed.planner.primitive_action_tree import patch_primitive_action_tree_predict


def main() -> None:
    with patch_primitive_action_tree_predict():
        from testbed.cli import eval as eval_cli

        eval_cli.main()


if __name__ == "__main__":
    main()
