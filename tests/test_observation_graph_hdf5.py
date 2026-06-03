from pathlib import Path

import numpy as np

from testbed.data.hdf5_io import read_episode, write_episode


def _base_episode(length: int = 3) -> dict:
    return {
        "qpos": np.zeros((length, 4), dtype=np.float32),
        "qvel": np.zeros((length, 4), dtype=np.float32),
        "actions": np.zeros((length, 4), dtype=np.float32),
        "images": {"fpv": np.zeros((length, 4, 4, 3), dtype=np.uint8)},
    }


def test_read_episode_returns_none_when_observation_graph_is_absent(tmp_path: Path) -> None:
    path = tmp_path / "episode_0.hdf5"

    write_episode(path, **_base_episode())

    episode = read_episode(path, load_images=False)

    assert episode["observation_graph"] is None


def test_write_episode_round_trips_sensor_derived_observation_graph(
    tmp_path: Path,
) -> None:
    path = tmp_path / "episode_0.hdf5"
    graph = {
        "node_features": np.arange(3 * 4 * 5, dtype=np.float64).reshape(3, 4, 5),
        "node_mask": np.array(
            [
                [1, 1, 0, 0],
                [1, 1, 1, 0],
                [1, 0, 0, 0],
            ],
            dtype=bool,
        ),
        "edge_indices": np.array(
            [
                [[0, 1], [1, 0]],
                [[0, 1], [1, 2]],
                [[0, 0], [0, 0]],
            ],
            dtype=np.int32,
        ),
        "edge_features": np.ones((3, 2, 3), dtype=np.float64),
        "edge_mask": np.array([[1, 1], [1, 0], [0, 0]], dtype=bool),
        "graph_globals": np.ones((3, 2), dtype=np.float64),
    }

    write_episode(path, **_base_episode(), observation_graph=graph)

    episode = read_episode(path, load_images=False)
    loaded = episode["observation_graph"]

    assert loaded is not None
    assert loaded["node_features"].dtype == np.float32
    assert loaded["node_features"].shape == (3, 4, 5)
    np.testing.assert_array_equal(loaded["node_mask"], graph["node_mask"].astype(np.uint8))
    assert loaded["edge_indices"].dtype == np.int64
    np.testing.assert_array_equal(loaded["edge_indices"], graph["edge_indices"])
    assert loaded["edge_features"].dtype == np.float32
    np.testing.assert_array_equal(loaded["edge_mask"], graph["edge_mask"].astype(np.uint8))
    assert loaded["graph_globals"].shape == (3, 2)
