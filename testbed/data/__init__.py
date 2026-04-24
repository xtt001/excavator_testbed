"""Public `testbed.data` exports with lazy imports.

Avoid importing heavy dataset / labeling modules at package import time so that
submodules like `testbed.data.schema` can be imported without triggering
cross-package circular dependencies.
"""

from __future__ import annotations

from importlib import import_module


__all__ = [
    "write_episode",
    "write_v2_extension",
    "read_episode",
    "list_episodes",
    "EpisodeRecorder",
    "EpisodicDataset",
    "get_norm_stats",
    "load_data",
]


_EXPORT_MAP = {
    "write_episode": ("testbed.data.hdf5_io", "write_episode"),
    "write_v2_extension": ("testbed.data.hdf5_io", "write_v2_extension"),
    "read_episode": ("testbed.data.hdf5_io", "read_episode"),
    "list_episodes": ("testbed.data.hdf5_io", "list_episodes"),
    "EpisodeRecorder": ("testbed.data.recorder", "EpisodeRecorder"),
    "EpisodicDataset": ("testbed.data.dataset", "EpisodicDataset"),
    "get_norm_stats": ("testbed.data.dataset", "get_norm_stats"),
    "load_data": ("testbed.data.dataset", "load_data"),
}


def __getattr__(name: str):
    try:
        module_name, attr_name = _EXPORT_MAP[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
