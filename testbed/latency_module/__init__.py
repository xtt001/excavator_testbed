"""
Latency Instrumentation & Analysis Module
==========================================

A non-invasive, pluggable observability layer for the AGXUnity excavator
teleoperation testbed.

Quick start
-----------
    from testbed.latency_module import LatencySession

    with LatencySession.from_config(cfg) as session:
        session.start_episode(episode_idx=0)
        probe = session.probe           # ControlProbe wrapping AgxSimClient
        probe.step(step_id, action)     # automatically timed
        session.end_episode()

    # Offline: analyse outputs/<run_id>/trace.jsonl
    from testbed.latency_module import export_run_summary
    export_run_summary("outputs/run_xxx")
"""

from testbed.latency_module.session import LatencySession


def export_run_summary(*args, **kwargs):
    """
    Lazily import the pandas-backed offline exporter.

    This keeps live recording usable in environments that do not have the
    analysis stack installed yet.
    """
    from testbed.latency_module.analysis.export_summary import (
        export_run_summary as _export_run_summary,
    )

    return _export_run_summary(*args, **kwargs)

__all__ = ["LatencySession", "export_run_summary"]
