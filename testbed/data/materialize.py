"""Materialize HDF5 VDS wrappers into regular training-friendly HDF5 files."""

from __future__ import annotations

import datetime
import os
import shutil
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.hdf5_io import list_episodes
from testbed.data.vds import STORAGE_MODE_COPY, STORAGE_MODE_VDS


@dataclass(frozen=True)
class MaterializeStats:
    source_path: Path
    output_path: Path
    dataset_count: int
    image_dataset_count: int
    logical_bytes: int


def materialize_episode(
    source_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    image_batch_size: int = 16,
    compress_images: bool = True,
) -> MaterializeStats:
    """Copy one HDF5 episode, resolving virtual datasets into real datasets."""
    source_path = Path(source_path)
    output_path = Path(output_path)
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if output_path.exists() and not overwrite:
        raise FileExistsError(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    stats = _MutableStats()
    try:
        with h5py.File(source_path, "r") as src, h5py.File(tmp_path, "w") as dst:
            _copy_attrs(src.attrs, dst.attrs)
            for name, item in src.items():
                _copy_item(
                    item,
                    dst,
                    name=name,
                    logical_path=name,
                    image_batch_size=max(1, int(image_batch_size)),
                    compress_images=bool(compress_images),
                    stats=stats,
                )
            _mark_materialized(dst, source_path=source_path)
        tmp_path.replace(output_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return MaterializeStats(
        source_path=source_path,
        output_path=output_path,
        dataset_count=stats.dataset_count,
        image_dataset_count=stats.image_dataset_count,
        logical_bytes=stats.logical_bytes,
    )


def materialize_dataset(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
    image_batch_size: int = 16,
    compress_images: bool = True,
    episode_ids: Iterable[int] | None = None,
    recursive: bool = False,
    workers: int = 1,
    copy_json_sidecars: bool = True,
) -> list[MaterializeStats]:
    """Materialize every episode_N.hdf5 file in a dataset directory."""
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    episode_paths = _episode_paths(source_dir, recursive=bool(recursive))
    if episode_ids is not None:
        wanted = {int(value) for value in episode_ids}
        episode_paths = [
            path
            for path in episode_paths
            if int(path.stem.split("_", 1)[1]) in wanted
        ]
    if not episode_paths:
        raise FileNotFoundError(f"No episode_*.hdf5 files found under {source_dir}")

    tasks = [
        (
            source_path,
            output_dir / source_path.relative_to(source_dir),
            bool(overwrite),
            int(image_batch_size),
            bool(compress_images),
        )
        for source_path in episode_paths
    ]
    stats: list[MaterializeStats] = []
    if int(workers) <= 1:
        stats = [_materialize_task(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=int(workers)) as executor:
            futures = [executor.submit(_materialize_task, task) for task in tasks]
            for future in as_completed(futures):
                stats.append(future.result())
        stats.sort(key=lambda item: item.output_path.as_posix())
    if copy_json_sidecars:
        _copy_json_sidecars(source_dir, output_dir)
    return stats


def _materialize_task(
    task: tuple[Path, Path, bool, int, bool],
) -> MaterializeStats:
    source_path, output_path, overwrite, image_batch_size, compress_images = task
    return materialize_episode(
        source_path,
        output_path,
        overwrite=overwrite,
        image_batch_size=image_batch_size,
        compress_images=compress_images,
    )


class _MutableStats:
    def __init__(self) -> None:
        self.dataset_count = 0
        self.image_dataset_count = 0
        self.logical_bytes = 0


def _copy_item(
    item: h5py.Group | h5py.Dataset,
    dst_parent: h5py.Group | h5py.File,
    *,
    name: str,
    logical_path: str,
    image_batch_size: int,
    compress_images: bool,
    stats: _MutableStats,
) -> None:
    if isinstance(item, h5py.Group):
        dst_group = dst_parent.create_group(name)
        _copy_attrs(item.attrs, dst_group.attrs)
        for child_name, child in item.items():
            _copy_item(
                child,
                dst_group,
                name=child_name,
                logical_path=f"{logical_path}/{child_name}",
                image_batch_size=image_batch_size,
                compress_images=compress_images,
                stats=stats,
            )
        return

    _copy_dataset(
        item,
        dst_parent,
        name=name,
        logical_path=logical_path,
        image_batch_size=image_batch_size,
        compress_images=compress_images,
        stats=stats,
    )


def _copy_dataset(
    src_dataset: h5py.Dataset,
    dst_parent: h5py.Group | h5py.File,
    *,
    name: str,
    logical_path: str,
    image_batch_size: int,
    compress_images: bool,
    stats: _MutableStats,
) -> None:
    stats.dataset_count += 1
    stats.logical_bytes += _logical_nbytes(src_dataset)

    if _is_encoded_image_dataset(logical_path, src_dataset):
        stats.image_dataset_count += 1
        dst_dataset = dst_parent.create_dataset(
            name,
            shape=src_dataset.shape,
            dtype=src_dataset.dtype,
        )
        for index in range(int(src_dataset.shape[0])):
            dst_dataset[index] = np.asarray(src_dataset[index], dtype=np.uint8)
    elif _is_image_dataset(logical_path, src_dataset):
        stats.image_dataset_count += 1
        dst_dataset = dst_parent.create_dataset(
            name,
            shape=src_dataset.shape,
            dtype=src_dataset.dtype,
            **_image_dataset_kwargs(src_dataset, compress=compress_images),
        )
        for start in range(0, int(src_dataset.shape[0]), image_batch_size):
            end = min(start + image_batch_size, int(src_dataset.shape[0]))
            dst_dataset[start:end] = src_dataset[start:end]
    elif src_dataset.shape == ():
        dst_dataset = dst_parent.create_dataset(
            name,
            data=src_dataset[()],
            dtype=src_dataset.dtype,
        )
    else:
        dst_dataset = dst_parent.create_dataset(
            name,
            shape=src_dataset.shape,
            dtype=src_dataset.dtype,
        )
        dst_dataset[...] = src_dataset[()]

    _copy_attrs(src_dataset.attrs, dst_dataset.attrs)


def _copy_attrs(src_attrs: h5py.AttributeManager, dst_attrs: h5py.AttributeManager) -> None:
    for key, value in src_attrs.items():
        dst_attrs[key] = value


def _mark_materialized(dst: h5py.File, *, source_path: Path) -> None:
    if "metadata" not in dst:
        return
    meta = dst["metadata"].attrs
    source_storage_mode = str(meta.get("storage_mode", ""))
    source_primitive_mode = str(meta.get("primitive_storage_mode", ""))
    if source_storage_mode == STORAGE_MODE_VDS:
        meta["storage_mode"] = STORAGE_MODE_COPY
    if source_primitive_mode == STORAGE_MODE_VDS:
        meta["primitive_storage_mode"] = STORAGE_MODE_COPY
    meta["materialized_from_path"] = str(source_path.resolve())
    meta["materialized_at"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()
    meta["materialized_source_storage_mode"] = source_storage_mode


def _is_image_dataset(logical_path: str, dataset: h5py.Dataset) -> bool:
    return (
        logical_path.startswith("observations/images/") and dataset.ndim >= 4
    ) or _is_encoded_image_dataset(logical_path, dataset)


def _is_encoded_image_dataset(logical_path: str, dataset: h5py.Dataset) -> bool:
    return logical_path.startswith("observations/encoded_images/") and dataset.ndim == 1


def _image_dataset_kwargs(dataset: h5py.Dataset, *, compress: bool) -> dict[str, Any]:
    if not compress:
        return {}
    return {
        "compression": "lzf",
        "chunks": (1,) + tuple(int(value) for value in dataset.shape[1:]),
    }


def _logical_nbytes(dataset: h5py.Dataset) -> int:
    itemsize = int(dataset.dtype.itemsize)
    if itemsize <= 0:
        return 0
    return int(np.prod(dataset.shape, dtype=np.int64)) * itemsize


def _episode_paths(source_dir: Path, *, recursive: bool) -> list[Path]:
    if not recursive:
        return list_episodes(source_dir)
    paths: list[Path] = []
    for path in source_dir.rglob("episode_*.hdf5"):
        try:
            int(path.stem.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        paths.append(path)
    return sorted(paths, key=lambda path: path.relative_to(source_dir).as_posix())


def _copy_json_sidecars(source_dir: Path, output_dir: Path) -> None:
    for sidecar_path in source_dir.rglob("*.json"):
        rel_path = sidecar_path.relative_to(source_dir)
        target_path = output_dir / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sidecar_path, target_path)
