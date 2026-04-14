from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "load_trace": (
        "testbed.latency_module.analysis.parse_trace",
        "load_trace",
    ),
    "filter_events": (
        "testbed.latency_module.analysis.parse_trace",
        "filter_events",
    ),
    "pivot_step_latency": (
        "testbed.latency_module.analysis.parse_trace",
        "pivot_step_latency",
    ),
    "load_all_runs": (
        "testbed.latency_module.analysis.parse_trace",
        "load_all_runs",
    ),
    "latency_stats": (
        "testbed.latency_module.analysis.compute_metrics",
        "latency_stats",
    ),
    "compute_step_metrics": (
        "testbed.latency_module.analysis.compute_metrics",
        "compute_step_metrics",
    ),
    "compute_chain_metrics": (
        "testbed.latency_module.analysis.compute_metrics",
        "compute_chain_metrics",
    ),
    "metrics_from_trace": (
        "testbed.latency_module.analysis.compute_metrics",
        "metrics_from_trace",
    ),
    "plot_all": (
        "testbed.latency_module.analysis.plot_latency",
        "plot_all",
    ),
    "export_run_summary": (
        "testbed.latency_module.analysis.export_summary",
        "export_run_summary",
    ),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        )
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_EXPORTS.keys()))

__all__ = [
    "load_trace",
    "filter_events",
    "pivot_step_latency",
    "load_all_runs",
    "latency_stats",
    "compute_step_metrics",
    "compute_chain_metrics",
    "metrics_from_trace",
    "plot_all",
    "export_run_summary",
]
