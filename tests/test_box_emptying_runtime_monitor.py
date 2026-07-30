from __future__ import annotations

import numpy as np
import pytest

from testbed.data.schema import ENV_STATE_V2_4_DIM
from testbed.planner.box_emptying.runtime_monitor import (
    BoxEmptyingRuntimeContractError,
    BoxEmptyingRuntimeMonitor,
    RuntimeMonitorConfig,
)
from testbed.planner.box_emptying.safety_interlock import (
    BoxEmptyingSafetyInterlock,
)


def _obs(
    step: int,
    *,
    volumes: tuple[float, ...],
    fraction: float,
    payload: float = 0.0,
) -> dict[str, object]:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[0] = payload
    env[75] = 1.25
    env[89] = 0.60
    env[90] = 1600.0
    env[91:97] = volumes
    env[97] = sum(volumes) * 1600.0
    env[98] = max(env[97], 1.0) / max(fraction, 1.0e-6)
    env[99] = fraction
    env[100] = 1.0
    return {"step_id": step, "env_state": env}


def test_monitor_records_stable_cycle_with_and_semantics_for_ineffective() -> None:
    monitor = BoxEmptyingRuntimeMonitor(
        RuntimeMonitorConfig(stable_window_steps=3)
    )
    start = (0.20,) * 6
    end = (0.1995,) * 6  # 0.003 m3 total progress, below 0.005.
    for step in range(3):
        assert not monitor.observe(
            _obs(step, volumes=start, fraction=1.0, payload=14.0),
            cycle_index=0,
        ).stop
    for step in range(3, 6):
        monitor.observe(
            _obs(step, volumes=end, fraction=0.99, payload=14.0),
            cycle_index=0,
        )
    completed = monitor.observe(
        _obs(6, volumes=end, fraction=0.99, payload=0.0),
        cycle_index=1,
    )
    assert completed.completed_cycle_outcome is not None
    assert completed.completed_cycle_outcome.payload_kg == pytest.approx(14.0)
    assert completed.completed_cycle_outcome.stable_net_removed_volume_m3 == pytest.approx(
        0.003,
        abs=1.0e-6,
    )

    # High payload alone makes a cycle effective; low-progress is an AND gate.
    for cycle in (1, 2, 3):
        base = 10 + cycle * 10
        for offset in range(3):
            monitor.observe(
                _obs(base + offset, volumes=end, fraction=0.99, payload=15.0),
                cycle_index=cycle,
            )
        decision = monitor.observe(
            _obs(base + 3, volumes=end, fraction=0.99),
            cycle_index=cycle + 1,
        )
        assert decision.reason != "three_consecutive_ineffective"


def test_monitor_stops_after_three_ineffective_cycles_and_at_empty_hold() -> None:
    monitor = BoxEmptyingRuntimeMonitor(
        RuntimeMonitorConfig(stable_window_steps=2)
    )
    volumes = (0.20,) * 6
    step = 0
    for cycle in range(3):
        for _ in range(2):
            monitor.observe(
                _obs(step, volumes=volumes, fraction=0.8, payload=10.0),
                cycle_index=cycle,
            )
            step += 1
        decision = monitor.observe(
            _obs(step, volumes=volumes, fraction=0.8),
            cycle_index=cycle + 1,
        )
        step += 1
    assert decision.stop is True
    assert decision.reason == "three_consecutive_ineffective"

    monitor.reset()
    low = (0.005,) * 6
    assert not monitor.observe(
        _obs(100, volumes=low, fraction=0.05), cycle_index=0
    ).stop
    assert not monitor.observe(
        _obs(101, volumes=low, fraction=0.05), cycle_index=0
    ).stop
    empty = monitor.observe(
        _obs(102, volumes=low, fraction=0.05), cycle_index=0
    )
    assert empty.stop is True
    assert empty.reason == "empty_box_5pct_three_observations"


def test_monitor_requires_a_stable_window_before_cycle_completion() -> None:
    monitor = BoxEmptyingRuntimeMonitor(
        RuntimeMonitorConfig(stable_window_steps=3)
    )
    monitor.observe(
        _obs(0, volumes=(0.2,) * 6, fraction=1.0),
        cycle_index=0,
    )
    with pytest.raises(BoxEmptyingRuntimeContractError, match="stable"):
        monitor.observe(
            _obs(1, volumes=(0.2,) * 6, fraction=1.0),
            cycle_index=1,
        )


def test_external_stop_is_neutral_until_ack_before_terminal_exit() -> None:
    interlock = BoxEmptyingSafetyInterlock()
    interlock.request_neutral_event(
        step_id=20,
        reason="maximum_120_cycles",
        terminal=True,
    )
    proposed = np.ones(4, dtype=np.float32)
    first = interlock.filter_action(
        _obs(20, volumes=(0.2,) * 6, fraction=1.0),
        proposed,
        active_cell_id=0,
        active_corridor_id=0,
    )
    assert first.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert first.awaiting_neutral_ack is True
    acknowledged = interlock.filter_action(
        _obs(21, volumes=(0.2,) * 6, fraction=1.0),
        proposed,
        active_cell_id=0,
        active_corridor_id=0,
    )
    assert acknowledged.action.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert acknowledged.neutral_acknowledged is True
    assert acknowledged.terminal is True
