from __future__ import annotations

import numpy as np
import pytest

from testbed.planner.primitive.token.tokens import ReturnRelocateTokenPlanner


def test_return_relocate_token_planner_copies_and_clears_target_fields() -> None:
    return_target_tokens = np.arange(10, dtype=np.float32)

    token = ReturnRelocateTokenPlanner().plan(return_target_tokens)

    return_target_tokens[0] = 99.0
    np.testing.assert_allclose(token[:7], np.arange(7, dtype=np.float32))
    assert float(token[7]) == 0.0
    assert float(token[8]) == 0.0
    assert float(token[9]) == 9.0
    with pytest.raises(ValueError):
        token[0] = 7.0
