"""
export_summary.py — Export a human-readable summary JSON from a trace.

Usage (CLI)
-----------
    python -m testbed.latency_module.analysis.export_summary \
        --trace outputs/run_xxx/trace.jsonl \
        --out   outputs/run_xxx/summary.json

Usage (programmatic)
--------------------
    from testbed.latency_module.analysis.export_summary import export_run_summary
    export_run_summary("outputs/run_xxx")
"""

from __future__ import annotations

import json
from pathlib import Path


def export_run_summary(run_dir: str | Path, *, overwrite: bool = True) -> dict:
    """
    Compute metrics and plots for one run directory, write summary.json.

    Expected run_dir layout:
        run_dir/
          trace.jsonl
          summary.json   ← written by this function
          plots/         ← written by plot_latency.plot_all()

    Returns the summary dict.
    """
    from testbed.latency_module.analysis.parse_trace import (
        load_trace,
        pivot_step_latency,
    )
    from testbed.latency_module.analysis.compute_metrics import (
        compute_chain_metrics,
        compute_step_metrics,
    )
    from testbed.latency_module.analysis.plot_latency import plot_all

    run_dir = Path(run_dir)
    trace_path = run_dir / "trace.jsonl"

    if not trace_path.exists():
        print(f"  [export_summary] trace not found: {trace_path}")
        return {}

    print(f"  [export_summary] loading {trace_path}")
    df = load_trace(trace_path)
    if df.empty:
        print("  [export_summary] trace is empty — nothing to export")
        return {}

    steps = pivot_step_latency(df)
    chain_metrics = compute_chain_metrics(df)
    step_metrics  = compute_step_metrics(steps) if not steps.empty else {}

    # Determine group_col for comparison plot
    group_col = "delay_inject_ms"
    if not steps.empty and group_col in steps.columns and steps[group_col].nunique() <= 1:
        group_col = "run_id"

    # Generate plots
    plot_all(steps if not steps.empty else df, run_dir, group_col=group_col)

    summary = {
        "run_dir":      str(run_dir),
        "trace_path":   str(trace_path),
        "event_count":  int(len(df)),
        "step_count":   int(len(steps)) if not steps.empty else 0,
        **chain_metrics,
        **step_metrics,
    }

    out_path = run_dir / "summary.json"
    if not out_path.exists() or overwrite:
        out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"  [export_summary] wrote → {out_path}")

    return summary


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="tb-latency-summary",
        description="Export latency summary JSON and plots from a trace.jsonl.",
    )
    parser.add_argument(
        "--trace", "-t", type=Path,
        help="Path to trace.jsonl file (default: <run_dir>/trace.jsonl).",
    )
    parser.add_argument(
        "--run-dir", "-r", type=Path, default=None,
        help="Run directory containing trace.jsonl.  Inferred from --trace if omitted.",
    )
    parser.add_argument(
        "--out", "-o", type=Path, default=None,
        help="Override output path for summary.json.",
    )
    args = parser.parse_args()

    if args.trace and args.run_dir is None:
        args.run_dir = Path(args.trace).parent
    if args.run_dir is None:
        parser.error("Provide --trace or --run-dir.")

    summary = export_run_summary(args.run_dir)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"  [export_summary] also wrote → {args.out}")


if __name__ == "__main__":
    main()
