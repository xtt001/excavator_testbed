"""Deterministic artifact rendering for the Strict-18 support-contract audit.

The support-contract evaluator decides whether a candidate is admissible.  This
module only writes its immutable evidence: JSON, a concise Markdown report, and
per-Return SVG traces.  Keeping the renderer separate keeps the evaluator below
the large-file boundary and makes output formatting independently testable.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


def write_return_support_plots(
    destination: Path,
    plot_specs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Write one exclusive eight-panel qpos/qvel SVG per Return segment."""

    plots_dir = destination / "plots"
    if plot_specs:
        plots_dir.mkdir(exist_ok=False)
    records: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for spec in plot_specs:
        stem = _safe_segment_filename(str(spec["segment_id"]))
        filename = f"return_{stem}.svg"
        if filename in used_names:
            raise ValueError(f"duplicate sanitized Return plot filename {filename!r}")
        used_names.add(filename)
        path = plots_dir / filename
        write_text_exclusive(path, _return_segment_svg(spec))
        records.append(
            {
                "segment_id": str(spec["segment_id"]),
                "path": str(path.relative_to(destination)),
                "sha256": sha256_file(path),
            }
        )
    return records


def render_support_contract_report(
    *,
    status: str,
    selections: Mapping[str, Mapping[str, Any]],
    target_diagnosis: Mapping[str, Any],
    plot_records: Sequence[Mapping[str, Any]],
) -> str:
    """Render the human-readable summary without changing audit semantics."""

    lines = [
        "# Strict-18 支持范围合同离线审计",
        "",
        f"状态：`{status}`。本审计只使用 strict-train 拟合候选规则，并用保留验证来源选择规则。",
        "目标 rollout 不参与阈值、协方差、候选选择或负对照构造。结果不能证明 Unity、真实机械或闭环挖掘效果。",
        "",
        "| Primitive | Selected rule | Selection status | Validation normal coverage | Synthetic obvious-OOD rejection |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for primitive in ("dig", "return"):
        selection = selections[primitive]
        selected_id = selection["selected_candidate_id"]
        selected_record = next(
            (
                record
                for record in selection["candidate_records"]
                if record["candidate_id"] == selected_id
            ),
            None,
        )
        coverage = (
            "—"
            if selected_record is None
            else f"{selected_record['validation_normal_coverage']:.3f}"
        )
        rejection = (
            "—"
            if selected_record is None
            else f"{selected_record['synthetic_obvious_ood_rejection']:.3f}"
        )
        lines.append(
            f"| {primitive} | {selected_id or 'none'} | "
            f"{selection['selection_status']} | {coverage} | {rejection} |"
        )
    lines.extend(("", "## Recorded Stage-A diagnosis", ""))
    for primitive in ("dig", "return"):
        aggregate = target_diagnosis["primitives"][primitive]["aggregate"]
        lines.append(
            f"- {primitive.capitalize()}："
            f"{target_diagnosis['primitives'][primitive]['segment_count']} 段；"
            f"v1 越界段 {aggregate['v1_out_of_support_segment_count']}；"
            f"选中规则支持段 {aggregate['selected_supported_segment_count']}；"
            f"选中规则仍越界段 {aggregate['selected_out_of_support_segment_count']}。"
        )
    lines.extend(
        (
            "",
            "qpos/qvel/token 归因仅说明哪一类数字字段越过 v1 轴向范围；"
            "它不能单独证明时间对齐或字段语义错误。",
        )
    )
    if plot_records:
        lines.extend(("", "## Return qpos/qvel traces", ""))
        for plot in plot_records:
            lines.append(f"- `{plot['segment_id']}`：[SVG]({plot['path']})")
    lines.append("")
    return "\n".join(lines)


def write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    """Write canonical JSON once; no artifact file may be overwritten."""

    with path.open("x", encoding="utf-8") as handle:
        json.dump(_json_ready(dict(payload)), handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def write_text_exclusive(path: Path, text: str) -> None:
    """Write text once; an existing file is a no-overwrite contract failure."""

    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def sha256_file(path: Path) -> str:
    """Return the stable content SHA recorded alongside a generated SVG."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _return_segment_svg(spec: Mapping[str, Any]) -> str:
    feature = _finite_matrix(spec["feature"], label="Return SVG feature")
    feature_order = tuple(str(value) for value in spec["feature_order"])
    lower = _finite_vector(spec["lower"], label="Return SVG lower")
    upper = _finite_vector(spec["upper"], label="Return SVG upper")
    if feature.shape[1] != len(feature_order) or lower.shape != upper.shape:
        raise ValueError("Return SVG feature/bounds shape mismatch")
    required = tuple(
        [f"qpos[{index}]" for index in range(4)]
        + [f"qvel[{index}]" for index in range(4)]
    )
    if tuple(feature_order[:8]) != required:
        raise ValueError(
            "Return SVG requires qpos[0..3], qvel[0..3] as the first eight features"
        )
    width, height = 1200, 820
    panel_width, panel_height = 555, 160
    left, top = 48, 104
    panels: list[str] = []
    for index in range(8):
        row, column = divmod(index, 2)
        x = left + column * 590
        y = top + row * 170
        panels.append(
            _svg_panel(
                x=x,
                y=y,
                width=panel_width,
                height=panel_height,
                label=feature_order[index],
                values=feature[:, index],
                p01=float(lower[index]),
                p99=float(upper[index]),
            )
        )
    title = html.escape(str(spec["segment_id"]))
    selected = html.escape(str(spec["selected_candidate_id"] or "not selected"))
    selected_status = html.escape(str(spec["selected_status"]))
    fraction = float(spec["v1_in_support_fraction"])
    return "\n".join(
        (
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="white"/>',
            '<style>text{font-family:monospace;fill:#17212b}.axis{stroke:#52616b;stroke-width:1}.band{fill:#d7ebff}.trace{fill:none;stroke:#c2352b;stroke-width:2}.bound{stroke:#2b6cb0;stroke-width:1;stroke-dasharray:4 3}.small{font-size:12px}.title{font-size:16px;font-weight:bold}</style>',
            f'<text x="48" y="30" class="title">Return numeric support trace: {title}</text>',
            '<text x="48" y="54" class="small">Blue band: strict-train v1 p01--p99. Red trace: recorded pre-action qpos/qvel.</text>',
            f'<text x="48" y="76" class="small">v1 frame support: {fraction:.3f}; selected rule: {selected}; selected status: {selected_status}</text>',
            *panels,
            '</svg>',
            '',
        )
    )


def _svg_panel(
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    label: str,
    values: np.ndarray,
    p01: float,
    p99: float,
) -> str:
    values = _finite_vector(values, label=f"SVG values {label}")
    if p01 > p99:
        raise ValueError(f"SVG p01 exceeds p99 for {label}")
    lo = min(float(np.min(values)), p01)
    hi = max(float(np.max(values)), p99)
    span = hi - lo
    pad = max(span * 0.08, 1.0e-6)
    lo -= pad
    hi += pad
    plot_x = x + 54
    plot_y = y + 24
    plot_width = width - 68
    plot_height = height - 48

    def value_y(value: float) -> float:
        return plot_y + (hi - value) * plot_height / (hi - lo)

    def sample_x(index: int) -> float:
        if len(values) == 1:
            return plot_x + plot_width / 2.0
        return plot_x + index * plot_width / float(len(values) - 1)

    band_top = value_y(p99)
    band_bottom = value_y(p01)
    points = " ".join(
        f"{sample_x(index):.2f},{value_y(float(value)):.2f}"
        for index, value in enumerate(values)
    )
    escaped = html.escape(label)
    return "\n".join(
        (
            f'<g id="{html.escape(_safe_segment_filename(label))}">',
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="#fafafa" stroke="#c7d0d9"/>',
            f'<text x="{x + 8}" y="{y + 16}" class="small">{escaped}</text>',
            f'<rect class="band" x="{plot_x:.2f}" y="{band_top:.2f}" width="{plot_width:.2f}" height="{band_bottom - band_top:.2f}"/>',
            f'<line class="axis" x1="{plot_x:.2f}" y1="{plot_y + plot_height:.2f}" x2="{plot_x + plot_width:.2f}" y2="{plot_y + plot_height:.2f}"/>',
            f'<line class="axis" x1="{plot_x:.2f}" y1="{plot_y:.2f}" x2="{plot_x:.2f}" y2="{plot_y + plot_height:.2f}"/>',
            f'<line class="bound" x1="{plot_x:.2f}" y1="{band_top:.2f}" x2="{plot_x + plot_width:.2f}" y2="{band_top:.2f}"/>',
            f'<line class="bound" x1="{plot_x:.2f}" y1="{band_bottom:.2f}" x2="{plot_x + plot_width:.2f}" y2="{band_bottom:.2f}"/>',
            f'<polyline class="trace" points="{points}"/>',
            f'<text x="{x + 4}" y="{plot_y + 10:.2f}" class="small">{hi:.4g}</text>',
            f'<text x="{x + 4}" y="{plot_y + plot_height:.2f}" class="small">{lo:.4g}</text>',
            f'<text x="{x + width - 132}" y="{y + 16}" class="small">p01={p01:.4g} p99={p99:.4g}</text>',
            '</g>',
        )
    )


def _safe_segment_filename(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    if not clean:
        raise ValueError("segment id cannot be converted to a safe filename")
    return clean


def _finite_matrix(value: Any, *, label: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError(f"{label} must be a non-empty rank-2 matrix")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{label} contains non-finite values")
    return matrix


def _finite_vector(value: Any, *, label: str) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float64).reshape(-1)
    if vector.size == 0 or not np.isfinite(vector).all():
        raise ValueError(f"{label} must be a non-empty finite vector")
    return vector


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return _json_ready(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("artifact JSON cannot contain non-finite floats")
    return value


__all__ = [
    "render_support_contract_report",
    "sha256_file",
    "write_json_exclusive",
    "write_return_support_plots",
    "write_text_exclusive",
]
