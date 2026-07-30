"""Virtualize large HDF5 image datasets for compact archival copies.

This module is the archival counterpart to :mod:`testbed.data.materialize`.
It keeps low-dimensional arrays local in the output HDF5 file, but replaces
``/observations/images/*`` and ``/observations/encoded_images/*`` datasets with
VDS links back to the canonical source
episode.  The result is much smaller than a materialized copy while preserving
lossless reads when the source HDF5 files remain available.
"""

from __future__ import annotations

import datetime
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import h5py
import numpy as np

from testbed.data.hdf5_io import list_episodes
from testbed.data.vds import STORAGE_MODE_COPY, STORAGE_MODE_VDS


@dataclass(frozen=True)
class SourcePrefixRewrite:
    old: Path
    new: Path


@dataclass(frozen=True)
class ImageReference:
    source_path: Path
    source_dataset_path: str
    start: int
    end: int


@dataclass(frozen=True)
class VirtualizeImagesStats:
    source_path: Path
    output_path: Path
    dataset_count: int
    image_dataset_count: int
    virtualized_image_bytes: int
    copied_logical_bytes: int


def virtualize_episode_images(
    source_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    source_prefix_rewrites: Iterable[SourcePrefixRewrite] | None = None,
    fallback_source_dir: str | Path | None = None,
    relative_paths: bool = True,
) -> VirtualizeImagesStats:
    """Write one compact HDF5 copy with image datasets backed by VDS.

    The input episode must carry provenance metadata such as
    ``vds_source_*`` or ``source_episode_path/source_start_step`` so the image
    frame range can be traced back to a canonical source HDF5 episode.
    """
    source_path = Path(source_path)
    output_path = Path(output_path)
    fallback_source_dir = None if fallback_source_dir is None else Path(fallback_source_dir)
    rewrites = tuple(source_prefix_rewrites or ())
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if output_path.exists() and not overwrite:
        raise FileExistsError(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    stats = _MutableStats()
    image_refs: list[ImageReference] = []
    try:
        with h5py.File(source_path, "r") as src, h5py.File(tmp_path, "w") as dst:
            _copy_attrs(src.attrs, dst.attrs)
            for name, item in src.items():
                _copy_or_virtualize_item(
                    item,
                    dst,
                    name=name,
                    logical_path=name,
                    source_file_path=source_path,
                    output_path=tmp_path,
                    rewrites=rewrites,
                    fallback_source_dir=fallback_source_dir,
                    relative_paths=relative_paths,
                    stats=stats,
                    image_refs=image_refs,
                )
            _mark_image_virtualized(
                dst,
                source_path=source_path,
                image_refs=image_refs,
                relative_paths=relative_paths,
            )
        tmp_path.replace(output_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return VirtualizeImagesStats(
        source_path=source_path,
        output_path=output_path,
        dataset_count=stats.dataset_count,
        image_dataset_count=stats.image_dataset_count,
        virtualized_image_bytes=stats.virtualized_image_bytes,
        copied_logical_bytes=stats.copied_logical_bytes,
    )


def virtualize_dataset_images(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
    source_prefix_rewrites: Iterable[SourcePrefixRewrite] | None = None,
    fallback_source_dir: str | Path | None = None,
    relative_paths: bool = True,
    episode_ids: Iterable[int] | None = None,
    recursive: bool = False,
    copy_json_sidecars: bool = True,
) -> list[VirtualizeImagesStats]:
    """Virtualize episode files in a dataset directory.

    When ``recursive`` is true, primitive subdirectories such as
    ``dig/episode_0.hdf5`` are preserved under the output directory.
    """
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    fallback_source_dir = None if fallback_source_dir is None else Path(fallback_source_dir)
    episode_paths = _episode_paths(source_dir, recursive=recursive)
    if episode_ids is not None:
        wanted = {int(value) for value in episode_ids}
        episode_paths = [
            path
            for path in episode_paths
            if int(path.stem.split("_", 1)[1]) in wanted
        ]
    if not episode_paths:
        raise FileNotFoundError(f"No episode_*.hdf5 files found under {source_dir}")

    stats: list[VirtualizeImagesStats] = []
    for episode_path in episode_paths:
        rel_path = episode_path.relative_to(source_dir)
        stats.append(
            virtualize_episode_images(
                episode_path,
                output_dir / rel_path,
                overwrite=overwrite,
                source_prefix_rewrites=source_prefix_rewrites,
                fallback_source_dir=(
                    None
                    if fallback_source_dir is None
                    else fallback_source_dir / episode_path.relative_to(source_dir).parent
                ),
                relative_paths=relative_paths,
            )
        )
    if copy_json_sidecars:
        _copy_json_sidecars(source_dir, output_dir)
    return stats


class _MutableStats:
    def __init__(self) -> None:
        self.dataset_count = 0
        self.image_dataset_count = 0
        self.virtualized_image_bytes = 0
        self.copied_logical_bytes = 0


def _copy_or_virtualize_item(
    item: h5py.Group | h5py.Dataset,
    dst_parent: h5py.Group | h5py.File,
    *,
    name: str,
    logical_path: str,
    source_file_path: Path,
    output_path: Path,
    rewrites: tuple[SourcePrefixRewrite, ...],
    fallback_source_dir: Path | None,
    relative_paths: bool,
    stats: _MutableStats,
    image_refs: list[ImageReference],
) -> None:
    if isinstance(item, h5py.Group):
        dst_group = dst_parent.create_group(name)
        _copy_attrs(item.attrs, dst_group.attrs)
        for child_name, child in item.items():
            _copy_or_virtualize_item(
                child,
                dst_group,
                name=child_name,
                logical_path=f"{logical_path}/{child_name}",
                    source_file_path=source_file_path,
                    output_path=output_path,
                    rewrites=rewrites,
                    fallback_source_dir=fallback_source_dir,
                    relative_paths=relative_paths,
                stats=stats,
                image_refs=image_refs,
            )
        return

    stats.dataset_count += 1
    logical_bytes = _logical_nbytes(item)
    if _is_image_dataset(logical_path, item):
        stats.image_dataset_count += 1
        stats.virtualized_image_bytes += logical_bytes
        image_ref = _resolve_image_reference(
            source_file_path=source_file_path,
            source_file=item.file,
            dataset_path=logical_path,
            dataset=item,
            rewrites=rewrites,
            fallback_source_dir=fallback_source_dir,
        )
        _create_image_vds(
            dst_parent,
            name=name,
            logical_path=logical_path,
            source_dataset=item,
            image_ref=image_ref,
            output_path=output_path,
            relative_paths=relative_paths,
        )
        dst_dataset = dst_parent[name]
        _copy_attrs(item.attrs, dst_dataset.attrs)
        _write_image_ref_attrs(dst_dataset.attrs, image_ref=image_ref, output_path=output_path)
        image_refs.append(image_ref)
        return

    stats.copied_logical_bytes += logical_bytes
    _copy_dataset(item, dst_parent, name=name)


def _copy_dataset(
    src_dataset: h5py.Dataset,
    dst_parent: h5py.Group | h5py.File,
    *,
    name: str,
) -> None:
    if src_dataset.shape == ():
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


def _resolve_image_reference(
    *,
    source_file_path: Path,
    source_file: h5py.File,
    dataset_path: str,
    dataset: h5py.Dataset,
    rewrites: tuple[SourcePrefixRewrite, ...],
    fallback_source_dir: Path | None,
) -> ImageReference:
    meta = _metadata_attrs(source_file)
    length = int(dataset.shape[0])
    ref_path, ref_start, ref_end = _source_window_from_metadata(
        owner_path=source_file_path,
        meta=meta,
        length=length,
        rewrites=rewrites,
        fallback_source_dir=fallback_source_dir,
    )
    return _resolve_backing_image_reference(
        source_path=ref_path,
        dataset_path=dataset_path,
        start=ref_start,
        end=ref_end,
        rewrites=rewrites,
        depth=0,
    )


def _resolve_backing_image_reference(
    *,
    source_path: Path,
    dataset_path: str,
    start: int,
    end: int,
    rewrites: tuple[SourcePrefixRewrite, ...],
    depth: int,
) -> ImageReference:
    if depth > 16:
        raise RecursionError(f"VDS source chain is too deep for {source_path}")
    source_path = _apply_rewrites(source_path, rewrites)
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    with h5py.File(source_path, "r") as f:
        if dataset_path not in f:
            raise KeyError(f"{source_path} is missing {dataset_path}")
        source_dataset = f[dataset_path]
        if not source_dataset.is_virtual:
            if end > int(source_dataset.shape[0]):
                raise ValueError(
                    f"Frame range {start}:{end} exceeds {source_path}:{dataset_path} "
                    f"length {source_dataset.shape[0]}"
                )
            return ImageReference(
                source_path=source_path,
                source_dataset_path=dataset_path,
                start=int(start),
                end=int(end),
            )

        image_attrs = dict(source_dataset.attrs)
        if "image_vds_source_abs_path" in image_attrs:
            next_path = _apply_rewrites(
                Path(str(image_attrs["image_vds_source_abs_path"])),
                rewrites,
            )
            next_start_base = int(image_attrs["image_vds_source_start_step"])
            next_end_base = int(image_attrs["image_vds_source_end_step_exclusive"])
            next_start, next_end = _project_virtual_range(
                start=start,
                end=end,
                target_len=int(source_dataset.shape[0]),
                source_start=next_start_base,
                source_end=next_end_base,
                source_path=source_path,
                dataset_path=dataset_path,
            )
            return _resolve_backing_image_reference(
                source_path=next_path,
                dataset_path=str(image_attrs.get("image_vds_source_dataset", dataset_path)),
                start=next_start,
                end=next_end,
                rewrites=rewrites,
                depth=depth + 1,
            )

        meta = _metadata_attrs(f)
        next_path, next_start_base, _next_end_base = _source_window_from_metadata(
            owner_path=source_path,
            meta=meta,
            length=int(source_dataset.shape[0]),
            rewrites=rewrites,
            require_vds_keys=True,
        )
        next_start, next_end = _project_virtual_range(
            start=start,
            end=end,
            target_len=int(source_dataset.shape[0]),
            source_start=next_start_base,
            source_end=_next_end_base,
            source_path=source_path,
            dataset_path=dataset_path,
        )
        return _resolve_backing_image_reference(
            source_path=next_path,
            dataset_path=dataset_path,
            start=next_start,
            end=next_end,
            rewrites=rewrites,
            depth=depth + 1,
        )


def _project_virtual_range(
    *,
    start: int,
    end: int,
    target_len: int,
    source_start: int,
    source_end: int,
    source_path: Path,
    dataset_path: str,
) -> tuple[int, int]:
    """Project either target-relative or backing-source absolute frame ranges."""
    start = int(start)
    end = int(end)
    target_len = int(target_len)
    source_start = int(source_start)
    source_end = int(source_end)
    if 0 <= start <= end <= target_len:
        return int(source_start + start), int(source_start + end)
    if source_start <= start <= end <= source_end:
        return start, end
    raise ValueError(
        f"Frame range {start}:{end} is neither target-relative length {target_len} "
        f"nor source-absolute range {source_start}:{source_end} for "
        f"{source_path}:{dataset_path}"
    )


def _source_window_from_metadata(
    *,
    owner_path: Path,
    meta: dict[str, Any],
    length: int,
    rewrites: tuple[SourcePrefixRewrite, ...],
    fallback_source_dir: Path | None = None,
    require_vds_keys: bool = False,
) -> tuple[Path, int, int]:
    if (
        not require_vds_keys
        and _is_primitive_copy_metadata(meta)
        and "replay_source_episode" in meta
        and "source_start_step" in meta
    ):
        source_path = _metadata_path(
            owner_path=owner_path,
            meta=meta,
            rel_key=None,
            abs_key="replay_source_episode",
            rewrites=rewrites,
        )
        start = int(meta.get("source_start_step", 0))
        end = int(meta.get("source_end_step_exclusive", start + length))
        return source_path, start, end

    if (
        not require_vds_keys
        and _is_primitive_copy_metadata(meta)
        and "source_dataset_dir" in meta
        and "source_episode_id" in meta
    ):
        source_dir = _apply_rewrites(Path(str(meta["source_dataset_dir"])), rewrites)
        episode_name = _episode_name_from_metadata(meta["source_episode_id"])
        source_path = source_dir / episode_name
        start = int(meta.get("source_start_step", 0))
        end = int(meta.get("source_end_step_exclusive", start + length))
        return source_path, start, end

    if (
        not require_vds_keys
        and _is_primitive_copy_metadata(meta)
        and "source_episode_path" in meta
    ):
        source_path = _metadata_path(
            owner_path=owner_path,
            meta=meta,
            rel_key=None,
            abs_key="source_episode_path",
            rewrites=rewrites,
        )
        start = int(meta.get("source_start_step", 0))
        end = int(meta.get("source_end_step_exclusive", start + length))
        return source_path, start, end

    if "vds_source_start_step" in meta and (
        "vds_source_abs_path" in meta or "vds_source_path" in meta
    ):
        source_path = _metadata_path(
            owner_path=owner_path,
            meta=meta,
            rel_key="vds_source_path",
            abs_key="vds_source_abs_path",
            rewrites=rewrites,
        )
        start = int(meta.get("vds_source_start_step", 0))
        end = int(meta.get("vds_source_end_step_exclusive", start + length))
        return source_path, start, end

    if not require_vds_keys and "source_dataset_dir" in meta and "source_episode_id" in meta:
        source_dir = _apply_rewrites(Path(str(meta["source_dataset_dir"])), rewrites)
        episode_name = _episode_name_from_metadata(meta["source_episode_id"])
        source_path = source_dir / episode_name
        start = int(meta.get("source_start_step", 0))
        end = int(meta.get("source_end_step_exclusive", start + length))
        return source_path, start, end

    if not require_vds_keys and "source_episode_path" in meta:
        source_path = _metadata_path(
            owner_path=owner_path,
            meta=meta,
            rel_key=None,
            abs_key="source_episode_path",
            rewrites=rewrites,
        )
        start = int(meta.get("source_start_step", 0))
        end = int(meta.get("source_end_step_exclusive", start + length))
        return source_path, start, end

    if not require_vds_keys and fallback_source_dir is not None:
        episode_name = _episode_name_from_metadata(
            meta.get("episode_id", owner_path.stem)
        )
        source_path = _apply_rewrites(fallback_source_dir / episode_name, rewrites)
        return source_path, 0, int(length)

    raise ValueError(
        f"{owner_path} does not carry source-frame metadata needed to virtualize images"
    )


def _is_primitive_copy_metadata(meta: dict[str, Any]) -> bool:
    return bool(
        meta.get("primitive_name")
        or meta.get("primitive_window")
        or meta.get("primitive_storage_mode")
    )


def _episode_name_from_metadata(value: Any) -> str:
    text = value.decode() if isinstance(value, bytes) else str(value)
    if text.endswith(".hdf5"):
        return Path(text).name
    if text.startswith("episode_"):
        return f"{text}.hdf5"
    return f"episode_{int(text)}.hdf5"


def _metadata_path(
    *,
    owner_path: Path,
    meta: dict[str, Any],
    rel_key: str | None,
    abs_key: str,
    rewrites: tuple[SourcePrefixRewrite, ...],
) -> Path:
    candidates: list[Path] = []
    if rel_key and meta.get(rel_key):
        candidates.append(owner_path.parent / str(meta[rel_key]))
    if meta.get(abs_key):
        abs_candidate = Path(str(meta[abs_key]))
        rewritten = _apply_rewrites(abs_candidate, rewrites)
        if rewritten != abs_candidate:
            candidates.append(rewritten)
        candidates.append(abs_candidate)
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate.exists():
            return candidate.resolve()
    if candidates:
        return _apply_rewrites(candidates[0], rewrites)
    raise KeyError(abs_key)


def _create_image_vds(
    dst_parent: h5py.Group | h5py.File,
    *,
    name: str,
    logical_path: str,
    source_dataset: h5py.Dataset,
    image_ref: ImageReference,
    output_path: Path,
    relative_paths: bool,
) -> None:
    target_shape = (int(image_ref.end - image_ref.start),) + tuple(
        int(value) for value in source_dataset.shape[1:]
    )
    layout = h5py.VirtualLayout(shape=target_shape, dtype=source_dataset.dtype)
    source_ref = _source_ref_for_output(
        source_path=image_ref.source_path,
        output_path=output_path,
        relative_paths=relative_paths,
    )
    vsource = h5py.VirtualSource(
        source_ref,
        image_ref.source_dataset_path,
        shape=(int(image_ref.end),) + target_shape[1:],
    )
    layout[...] = vsource[int(image_ref.start) : int(image_ref.end)]
    dst_parent.create_virtual_dataset(name, layout)


def _source_ref_for_output(
    *,
    source_path: Path,
    output_path: Path,
    relative_paths: bool,
) -> str:
    if not relative_paths:
        return str(source_path.resolve())
    return os.path.relpath(source_path.resolve(), start=output_path.parent.resolve())


def _write_image_ref_attrs(
    attrs: h5py.AttributeManager,
    *,
    image_ref: ImageReference,
    output_path: Path,
) -> None:
    attrs["image_storage_mode"] = STORAGE_MODE_VDS
    attrs["image_vds_source_path"] = _source_ref_for_output(
        source_path=image_ref.source_path,
        output_path=output_path,
        relative_paths=True,
    )
    attrs["image_vds_source_abs_path"] = str(image_ref.source_path.resolve())
    attrs["image_vds_source_dataset"] = str(image_ref.source_dataset_path)
    attrs["image_vds_source_start_step"] = int(image_ref.start)
    attrs["image_vds_source_end_step_exclusive"] = int(image_ref.end)


def _mark_image_virtualized(
    dst: h5py.File,
    *,
    source_path: Path,
    image_refs: list[ImageReference],
    relative_paths: bool,
) -> None:
    if "metadata" not in dst:
        return
    meta = dst["metadata"].attrs
    source_storage_mode = str(meta.get("storage_mode", ""))
    source_primitive_mode = str(meta.get("primitive_storage_mode", ""))
    if source_storage_mode == STORAGE_MODE_COPY:
        meta["storage_mode"] = STORAGE_MODE_VDS
    if source_primitive_mode == STORAGE_MODE_COPY:
        meta["primitive_storage_mode"] = STORAGE_MODE_VDS
    meta["image_storage_mode"] = STORAGE_MODE_VDS
    meta["image_virtualized_from_path"] = str(source_path.resolve())
    meta["image_virtualized_at"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()
    meta["image_virtualized_source_storage_mode"] = source_storage_mode
    meta["image_virtualized_lowdim_storage_mode"] = STORAGE_MODE_COPY
    meta["image_vds_path_mode"] = "relative" if relative_paths else "absolute"
    if len(image_refs) == 1:
        image_ref = image_refs[0]
        meta["image_vds_source_abs_path"] = str(image_ref.source_path.resolve())
        meta["image_vds_source_dataset"] = str(image_ref.source_dataset_path)
        meta["image_vds_source_start_step"] = int(image_ref.start)
        meta["image_vds_source_end_step_exclusive"] = int(image_ref.end)


def _copy_attrs(src_attrs: h5py.AttributeManager, dst_attrs: h5py.AttributeManager) -> None:
    for key, value in src_attrs.items():
        dst_attrs[key] = value


def _metadata_attrs(h5_file: h5py.File) -> dict[str, Any]:
    if "metadata" not in h5_file:
        return {}
    return dict(h5_file["metadata"].attrs)


def _is_image_dataset(logical_path: str, dataset: h5py.Dataset) -> bool:
    return (
        logical_path.startswith("observations/images/") and dataset.ndim >= 4
    ) or (
        logical_path.startswith("observations/encoded_images/") and dataset.ndim == 1
    )


def _logical_nbytes(dataset: h5py.Dataset) -> int:
    itemsize = int(dataset.dtype.itemsize)
    if itemsize <= 0:
        return 0
    return int(np.prod(dataset.shape, dtype=np.int64)) * itemsize


def _apply_rewrites(path: Path, rewrites: tuple[SourcePrefixRewrite, ...]) -> Path:
    path_str = str(path.expanduser())
    for rewrite in rewrites:
        old = str(rewrite.old.expanduser())
        if path_str == old or path_str.startswith(old.rstrip("/") + "/"):
            suffix = path_str[len(old) :].lstrip("/")
            return (rewrite.new.expanduser() / suffix).resolve()
    return path.expanduser()


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
