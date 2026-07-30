"""Fail-closed output-path guard for no-overwrite evaluation runs."""

from __future__ import annotations

from pathlib import Path


def assert_eval_output_paths_available(
    *,
    enabled: bool,
    results_dir: str | Path,
    video_dir: str | Path,
    rollout_log_dir: str | Path,
    hdf5_dir: str | Path,
    save_video: bool,
    save_rollout_logs: bool,
    record_hdf5: bool,
) -> None:
    """Reject an eval before it can modify any selected material output root."""

    if not enabled:
        return
    candidates: list[tuple[str, Path]] = [
        ("results_dir", Path(results_dir).expanduser()),
    ]
    if save_video:
        candidates.append(("video_dir", Path(video_dir).expanduser()))
    if save_rollout_logs:
        candidates.append(
            ("rollout_log_dir", Path(rollout_log_dir).expanduser())
        )
    if record_hdf5:
        candidates.append(("hdf5_dir", Path(hdf5_dir).expanduser()))

    seen: set[Path] = set()
    for label, candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.exists():
            raise FileExistsError(
                f"eval output already exists ({label}): {candidate}"
            )


__all__ = ["assert_eval_output_paths_available"]
