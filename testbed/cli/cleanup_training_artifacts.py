"""Clean regenerated training artifacts after successful ACT training."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOT_ROOT = Path("/fastdata/pingfan/excavator_testbed_data_hot")
KEEP_CKPT_NAME = "policy_best.ckpt"


@dataclass(frozen=True)
class PrimitiveCopyCandidate:
    copy_root: Path
    vds_root: Path | None
    source: str


def main() -> None:
    args = _parse_args()
    copy_scan_roots = (
        list(args.copy_scan_root)
        if args.copy_scan_root is not None
        else ([] if args.no_default_scan_roots else _default_copy_scan_roots())
    )
    summary = cleanup_training_artifacts(
        delete=bool(args.delete),
        primitive_copy_roots=args.primitive_copy_root,
        primitive_vds_roots=args.primitive_vds_root,
        copy_scan_roots=copy_scan_roots,
        manifest_roots=[] if args.no_manifest_scan else args.manifest_root,
        ckpt_dirs=args.ckpt_dir,
        ckpt_roots=[] if args.no_default_ckpt_roots else args.ckpt_root,
        symlink_roots=[] if args.no_symlink_cleanup else args.symlink_root,
        keep_ckpt_name=str(args.keep_ckpt_name),
        clean_copies=not bool(args.skip_primitive_copies),
        clean_ckpts=not bool(args.skip_ckpts),
    )
    _print_summary(summary, as_json=bool(args.json))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tb-cleanup-training-artifacts",
        description=(
            "Remove VDS-materialized primitive training copies and non-best "
            "checkpoints after policy_best.ckpt has been written."
        ),
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually remove files. Without this flag the command only reports candidates.",
    )
    parser.add_argument(
        "--primitive-copy-root",
        action="append",
        type=Path,
        default=[],
        help="Explicit materialized primitive copy root to remove.",
    )
    parser.add_argument(
        "--primitive-vds-root",
        action="append",
        type=Path,
        default=[],
        help=(
            "VDS root paired with --primitive-copy-root. When several are "
            "given, they are paired by order."
        ),
    )
    parser.add_argument(
        "--manifest-root",
        action="append",
        type=Path,
        default=[Path("runs/jobs")],
        help="Root to scan for V2.4 pipeline manifest.json files.",
    )
    parser.add_argument(
        "--no-manifest-scan",
        action="store_true",
        help="Do not discover primitive copy roots from runs/jobs manifests.",
    )
    parser.add_argument(
        "--copy-scan-root",
        action="append",
        type=Path,
        default=None,
        help=(
            "Root whose direct children are scanned for *primitives_copy* "
            "directories with matching *primitives_vds* siblings."
        ),
    )
    parser.add_argument(
        "--no-default-scan-roots",
        action="store_true",
        help="Do not scan the default data/runs/data/fastdata roots for copy directories.",
    )
    parser.add_argument(
        "--ckpt-dir",
        action="append",
        type=Path,
        default=[],
        help="Checkpoint directory to clean recursively.",
    )
    parser.add_argument(
        "--ckpt-root",
        action="append",
        type=Path,
        default=[Path("runs/ckpts")],
        help="Checkpoint root to scan recursively for non-best .ckpt files.",
    )
    parser.add_argument(
        "--no-default-ckpt-roots",
        action="store_true",
        help="Do not scan default checkpoint roots.",
    )
    parser.add_argument(
        "--keep-ckpt-name",
        type=str,
        default=KEEP_CKPT_NAME,
        help="Checkpoint filename to preserve. Defaults to policy_best.ckpt.",
    )
    parser.add_argument(
        "--symlink-root",
        action="append",
        type=Path,
        default=[Path("data")],
        help="Root whose direct symlink children are removed if they point to deleted copies.",
    )
    parser.add_argument(
        "--no-symlink-cleanup",
        action="store_true",
        help="Do not remove current symlinks that point at deleted primitive copies.",
    )
    parser.add_argument(
        "--skip-primitive-copies",
        action="store_true",
        help="Only clean checkpoints.",
    )
    parser.add_argument(
        "--skip-ckpts",
        action="store_true",
        help="Only clean primitive copy roots.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON summary.")
    return parser.parse_args()


def cleanup_training_artifacts(
    *,
    delete: bool,
    primitive_copy_roots: Iterable[Path] = (),
    primitive_vds_roots: Iterable[Path] = (),
    copy_scan_roots: Iterable[Path] = (),
    manifest_roots: Iterable[Path] = (),
    ckpt_dirs: Iterable[Path] = (),
    ckpt_roots: Iterable[Path] = (),
    symlink_roots: Iterable[Path] = (),
    keep_ckpt_name: str = KEEP_CKPT_NAME,
    clean_copies: bool = True,
    clean_ckpts: bool = True,
) -> dict[str, Any]:
    """Clean artifacts and return a machine-readable summary."""
    summary: dict[str, Any] = {
        "mode": "delete" if delete else "dry-run",
        "primitive_copies": {"candidates": [], "removed": [], "skipped": []},
        "checkpoints": {"candidates": [], "removed": []},
        "symlinks": {"removed": []},
    }

    removed_copy_roots: list[Path] = []
    if clean_copies:
        candidates = _discover_copy_candidates(
            primitive_copy_roots=primitive_copy_roots,
            primitive_vds_roots=primitive_vds_roots,
            copy_scan_roots=copy_scan_roots,
            manifest_roots=manifest_roots,
        )
        for candidate in candidates:
            item = _candidate_payload(candidate)
            reason = _copy_skip_reason(candidate)
            if reason:
                item["reason"] = reason
                summary["primitive_copies"]["skipped"].append(item)
                continue
            summary["primitive_copies"]["candidates"].append(item)
            if delete:
                shutil.rmtree(candidate.copy_root)
                removed_copy_roots.append(candidate.copy_root)
                summary["primitive_copies"]["removed"].append(item)

        if delete and removed_copy_roots:
            for link in _symlinks_pointing_to(removed_copy_roots, symlink_roots):
                summary["symlinks"]["removed"].append(str(_display_path(link)))
                link.unlink()

    if clean_ckpts:
        for path in _discover_nonbest_checkpoints(
            ckpt_dirs=ckpt_dirs,
            ckpt_roots=ckpt_roots,
            keep_ckpt_name=keep_ckpt_name,
        ):
            payload = {"path": str(_display_path(path)), "bytes": int(path.stat().st_size)}
            summary["checkpoints"]["candidates"].append(payload)
            if delete:
                path.unlink()
                summary["checkpoints"]["removed"].append(payload)

    return summary


def _discover_copy_candidates(
    *,
    primitive_copy_roots: Iterable[Path],
    primitive_vds_roots: Iterable[Path],
    copy_scan_roots: Iterable[Path],
    manifest_roots: Iterable[Path],
) -> list[PrimitiveCopyCandidate]:
    candidates: dict[Path, PrimitiveCopyCandidate] = {}

    explicit_copy_roots = list(primitive_copy_roots)
    explicit_vds_roots = list(primitive_vds_roots)
    for index, copy_root in enumerate(explicit_copy_roots):
        vds_root = explicit_vds_roots[index] if index < len(explicit_vds_roots) else None
        _add_candidate(
            candidates,
            PrimitiveCopyCandidate(
                copy_root=_repo_path(copy_root),
                vds_root=None if vds_root is None else _repo_path(vds_root),
                source="explicit",
            ),
        )

    for manifest_root in manifest_roots:
        for candidate in _manifest_candidates(_repo_path(manifest_root)):
            _add_candidate(candidates, candidate)

    for scan_root in copy_scan_roots:
        for candidate in _name_heuristic_candidates(_repo_path(scan_root)):
            _add_candidate(candidates, candidate)

    return sorted(candidates.values(), key=lambda item: str(item.copy_root))


def _add_candidate(
    candidates: dict[Path, PrimitiveCopyCandidate],
    candidate: PrimitiveCopyCandidate,
) -> None:
    key = candidate.copy_root
    existing = candidates.get(key)
    if existing is None or existing.vds_root is None:
        candidates[key] = candidate


def _manifest_candidates(manifest_root: Path) -> list[PrimitiveCopyCandidate]:
    if not manifest_root.exists():
        return []
    manifests = (
        [manifest_root]
        if manifest_root.is_file()
        else sorted(manifest_root.rglob("manifest.json"))
    )
    candidates: list[PrimitiveCopyCandidate] = []
    for manifest_path in manifests:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        paths = dict(payload.get("paths", {}) or {})
        copy_root = paths.get("primitive_copy_root")
        vds_root = paths.get("primitive_vds_root")
        if copy_root:
            candidates.append(
                PrimitiveCopyCandidate(
                    copy_root=_repo_path(Path(str(copy_root))),
                    vds_root=None if not vds_root else _repo_path(Path(str(vds_root))),
                    source=str(_display_path(manifest_path)),
                )
            )
    return candidates


def _name_heuristic_candidates(scan_root: Path) -> list[PrimitiveCopyCandidate]:
    if not scan_root.exists() or not scan_root.is_dir():
        return []
    candidates: list[PrimitiveCopyCandidate] = []
    for child in sorted(scan_root.iterdir()):
        if not child.is_dir() or child.is_symlink():
            continue
        if "primitives_copy" not in child.name:
            continue
        vds_root = _infer_vds_root(child)
        if vds_root is None:
            continue
        candidates.append(
            PrimitiveCopyCandidate(
                copy_root=child,
                vds_root=vds_root,
                source=f"name-heuristic:{_display_path(scan_root)}",
            )
        )
    return candidates


def _infer_vds_root(copy_root: Path) -> Path | None:
    text = str(copy_root)
    for old, new in (
        ("primitives_copy", "primitives_vds"),
        ("primitive_copy", "primitive_vds"),
    ):
        if old not in text:
            continue
        candidate = Path(text.replace(old, new, 1))
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _copy_skip_reason(candidate: PrimitiveCopyCandidate) -> str | None:
    copy_root = candidate.copy_root
    vds_root = candidate.vds_root or _infer_vds_root(copy_root)
    if not copy_root.exists():
        return "copy root does not exist"
    if not copy_root.is_dir() or copy_root.is_symlink():
        return "copy root is not a real directory"
    if "primitives_copy" not in copy_root.name:
        return "copy root name does not contain primitives_copy"
    if vds_root is None or not vds_root.exists() or not vds_root.is_dir():
        return "matching primitive VDS root is missing"
    if _safe_resolve(copy_root) == _safe_resolve(vds_root):
        return "copy root resolves to the same path as VDS root"
    if not _has_episode_files(copy_root):
        return "copy root has no episode_*.hdf5 files"
    return None


def _discover_nonbest_checkpoints(
    *,
    ckpt_dirs: Iterable[Path],
    ckpt_roots: Iterable[Path],
    keep_ckpt_name: str,
) -> list[Path]:
    roots = [_repo_path(path) for path in [*ckpt_dirs, *ckpt_roots]]
    paths: dict[Path, None] = {}
    for root in roots:
        if root.is_file() and root.suffix == ".ckpt":
            if root.name != keep_ckpt_name:
                paths[root] = None
            continue
        if not root.exists() or not root.is_dir():
            continue
        for path in root.rglob("*.ckpt"):
            if path.is_file() and path.name != keep_ckpt_name:
                paths[path] = None
    return sorted(paths)


def _symlinks_pointing_to(
    removed_roots: Iterable[Path],
    symlink_roots: Iterable[Path],
) -> list[Path]:
    resolved_roots = [_safe_resolve(path) for path in removed_roots]
    links: list[Path] = []
    for root in symlink_roots:
        root = _repo_path(root)
        if not root.exists() or not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_symlink():
                continue
            target = _safe_resolve(child)
            if any(_is_relative_to(target, removed) for removed in resolved_roots):
                links.append(child)
    return links


def _has_episode_files(root: Path) -> bool:
    try:
        next(root.rglob("episode_*.hdf5"))
    except StopIteration:
        return False
    return True


def _candidate_payload(candidate: PrimitiveCopyCandidate) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "copy_root": str(_display_path(candidate.copy_root)),
        "source": candidate.source,
    }
    if candidate.vds_root is not None:
        payload["vds_root"] = str(_display_path(candidate.vds_root))
    return payload


def _print_summary(summary: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    mode = summary["mode"]
    copy_candidates = summary["primitive_copies"]["candidates"]
    copy_removed = summary["primitive_copies"]["removed"]
    copy_skipped = summary["primitive_copies"]["skipped"]
    ckpt_candidates = summary["checkpoints"]["candidates"]
    ckpt_removed = summary["checkpoints"]["removed"]
    symlink_removed = summary["symlinks"]["removed"]
    print(
        f"cleanup mode={mode} "
        f"copy_candidates={len(copy_candidates)} copy_removed={len(copy_removed)} "
        f"copy_skipped={len(copy_skipped)} "
        f"ckpt_candidates={len(ckpt_candidates)} ckpt_removed={len(ckpt_removed)} "
        f"symlink_removed={len(symlink_removed)}"
    )
    for item in copy_removed if mode == "delete" else copy_candidates:
        print(f"copy: {item['copy_root']}")
    for item in ckpt_removed if mode == "delete" else ckpt_candidates:
        print(f"ckpt: {item['path']}")
    for link in symlink_removed:
        print(f"symlink: {link}")
    for item in copy_skipped:
        print(f"skip: {item['copy_root']} ({item['reason']})")


def _default_copy_scan_roots() -> list[Path]:
    roots = [Path("data"), Path("runs/data")]
    if DEFAULT_HOT_ROOT.exists():
        roots.append(DEFAULT_HOT_ROOT)
    return roots


def _repo_path(path: Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return ROOT / path


def _display_path(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def _safe_resolve(path: Path) -> Path:
    return path.resolve(strict=False)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    main()
