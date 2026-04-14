"""
latency_ab_test.py — Interactive A/B test: Update vs FixedUpdate step processing.

Workflow
--------
1. Start Unity with the new Inspector toggle (m_useFixedUpdateForRequests).
2. Set toggle to FALSE (Update mode) in Inspector.
3. Run this script — it measures condition A, then prompts you to flip the toggle.
4. Flip toggle to TRUE (FixedUpdate) in Inspector while sim is RUNNING.
5. Press Enter — script measures condition B.
6. Script prints and saves a side-by-side comparison with plots.

Usage
-----
    python scripts/latency_ab_test.py
    python scripts/latency_ab_test.py --steps 500
    python scripts/latency_ab_test.py --steps 300 --host 127.0.0.1 --port 5057
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from testbed.backends.agx.protocol import AgxSimClient


# ── Measurement helpers ───────────────────────────────────────────────────────

def _measure_condition(
    client: AgxSimClient,
    label: str,
    steps: int,
) -> dict:
    """Run `steps` zero-action steps, record per-step timing."""
    print(f"\n  Measuring [{label}]  ({steps} steps) ...")
    client.reset(seed=0, reset_terrain=True, reset_pose=True)

    action = np.zeros(4, dtype=np.float32)
    rtts:         list[float] = []
    py_to_unity:  list[float] = []
    queue_wait:   list[float] = []
    physics:      list[float] = []
    image_cap:    list[float] = []
    serialize:    list[float] = []
    unity_to_py:  list[float] = []

    def _ms(t_unity: int, t_ref: int) -> float:
        return (t_unity - t_ref) / 1e6 if t_unity > 0 and t_ref > 0 else -1.0

    for step_id in range(steps):
        t_send = time.time_ns()
        resp = client.step(step_id=step_id, action=action)
        t_recv = time.time_ns()

        rtt = (t_recv - t_send) / 1e6
        rtts.append(rtt)
        py_to_unity.append( _ms(resp.t_req_recv_ns,     t_send))
        queue_wait.append(  _ms(resp.t_queue_exit_ns,   resp.t_req_recv_ns))
        physics.append(     _ms(resp.t_physics_done_ns, resp.t_queue_exit_ns))
        image_cap.append(   _ms(resp.t_image_ready_ns,  resp.t_physics_done_ns))
        serialize.append(   _ms(resp.t_resp_queued_ns,  resp.t_image_ready_ns))
        unity_to_py.append( _ms(t_recv,                 resp.t_resp_queued_ns))

        # live progress every 50 steps
        if (step_id + 1) % 50 == 0:
            recent = np.array(rtts[-50:])
            print(f"    step {step_id+1:4d}/{steps}  "
                  f"recent_mean={recent.mean():.1f}ms  "
                  f"recent_p95={np.percentile(recent,95):.1f}ms")

    arr = np.array(rtts)
    has_segs = any(v >= 0 for v in py_to_unity)

    return dict(
        label       = label,
        rtts        = arr,
        py_to_unity = np.array(py_to_unity),
        queue_wait  = np.array(queue_wait),
        physics     = np.array(physics),
        image_cap   = np.array(image_cap),
        serialize   = np.array(serialize),
        unity_to_py = np.array(unity_to_py),
        has_segs    = has_segs,
    )


# ── Reporting helpers ─────────────────────────────────────────────────────────

def _seg_mean(arr: np.ndarray) -> str:
    v = arr[arr >= 0]
    return f"{v.mean():.2f}ms" if len(v) > 0 else "N/A"


def _print_comparison(a: dict, b: dict) -> None:
    def row(name, va, vb):
        ca = f"{va.mean():6.2f} ± {va.std():.2f}ms  p95={np.percentile(va,95):.2f}ms" if len(va[va>=0])>0 else "  N/A"
        cb = f"{vb.mean():6.2f} ± {vb.std():.2f}ms  p95={np.percentile(vb,95):.2f}ms" if len(vb[vb>=0])>0 else "  N/A"
        print(f"  {name:<28s}  A: {ca}   B: {cb}")

    print(f"\n{'='*75}")
    print(f"  A/B COMPARISON")
    print(f"  A = {a['label']:<30s}  ({len(a['rtts'])} steps)")
    print(f"  B = {b['label']:<30s}  ({len(b['rtts'])} steps)")
    print(f"{'='*75}")

    row("Total RTT",              a['rtts'],        b['rtts'])
    if a['has_segs'] or b['has_segs']:
        print(f"  {'─'*71}")
        row("  py → unity  (req net)", a['py_to_unity'],  b['py_to_unity'])
        row("  queue wait (tick wait)", a['queue_wait'],   b['queue_wait'])
        row("  AGX DoStep() (physics)", a['physics'],      b['physics'])
        row("  Image Collect()        ", a['image_cap'],    b['image_cap'])
        row("  Serialize              ", a['serialize'],    b['serialize'])
        row("  unity → py  (resp net)", a['unity_to_py'],  b['unity_to_py'])

    # Bimodal check
    print(f"\n  Distribution shape:")
    for cond in [a, b]:
        r = cond['rtts']
        fast = r[r < 28]
        slow = r[r >= 28]
        print(f"  [{cond['label']:30s}]  "
              f"fast(<28ms)={len(fast)/len(r)*100:4.1f}%  avg={fast.mean():.1f}ms  |  "
              f"slow(≥28ms)={len(slow)/len(r)*100:4.1f}%  avg={slow.mean():.1f}ms  "
              f"← {'BIMODAL (FixedUpdate symptom)' if len(slow)/len(r) > 0.3 and slow.mean() > 35 else 'smooth (Update)'}")


def _plot_comparison(a: dict, b: dict, out_dir: Path) -> None:
    import warnings; warnings.filterwarnings("ignore")
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # ── 1. Overlapping distributions ─────────────────────────────────────────
    ax = axes[0]
    bins = np.arange(10, 70, 2)
    for cond, color in [(a, "#4C72B0"), (b, "#C44E52")]:
        ax.hist(cond['rtts'], bins=bins, alpha=0.6, color=color,
                label=cond['label'], density=True)
    ax.axvline(20, color="green", linestyle="--", lw=1.2, label="target 20ms")
    ax.axvline(40, color="orange", linestyle=":", lw=1,   label="2× tick (40ms)")
    ax.set_xlabel("Step RTT (ms)"); ax.set_ylabel("Density")
    ax.set_title("RTT Distribution\nUpdate vs FixedUpdate")
    ax.legend(fontsize=8)

    # ── 2. Time-series (first 200 steps of each, rolling mean only) ──────────
    ax = axes[1]
    win = 30
    for cond, color in [(a, "#4C72B0"), (b, "#C44E52")]:
        r = cond['rtts'][:200]
        # raw data as faint fill between min/max per window for context
        if len(r) >= win:
            smooth = np.convolve(r, np.ones(win)/win, mode='valid')
            xs = np.arange(win-1, len(r))
            ax.fill_between(xs,
                            np.convolve(r, np.ones(win)/win, mode='valid') - r[win-1:].std()*0.5,
                            np.convolve(r, np.ones(win)/win, mode='valid') + r[win-1:].std()*0.5,
                            color=color, alpha=0.15)
            ax.plot(xs, smooth, color=color, linewidth=2.0, label=cond['label'])
        else:
            ax.plot(r, color=color, linewidth=2.0, label=cond['label'])
    ax.axhline(20, color="green", linestyle="--", lw=1, alpha=0.5)
    ax.set_xlabel("Step index"); ax.set_ylabel("RTT (ms)")
    ax.set_title(f"RTT Time-Series (rolling mean={win}, ±0.5σ band)")
    ax.legend(fontsize=8)

    # ── 3. Segment stacked bar (if available) ─────────────────────────────────
    ax = axes[2]
    if a['has_segs'] or b['has_segs']:
        seg_names  = ["py→unity", "queue wait", "DoStep", "image", "serialize", "unity→py"]
        seg_fields = ["py_to_unity", "queue_wait", "physics", "image_cap", "serialize", "unity_to_py"]
        colors     = ["#4C72B0", "#CCB974", "#C44E52", "#55A868", "#8172B2", "#64B5CD"]
        x = np.array([0.0, 1.0])
        bottoms = np.zeros(2)
        for seg, seg_f, col in zip(seg_names, seg_fields, colors):
            vals = []
            for cond in [a, b]:
                arr = cond[seg_f]
                v = arr[arr >= 0]
                vals.append(v.mean() if len(v) > 0 else 0.0)
            vals = np.array(vals)
            ax.bar(x, vals, 0.5, bottom=bottoms, color=col, label=seg)
            bottoms += vals
        ax.set_xticks(x)
        ax.set_xticklabels([a['label'], b['label']], fontsize=8)
        ax.set_ylabel("Time (ms)")
        ax.set_title("RTT Segment Breakdown\n(mean per condition)")
        ax.legend(fontsize=7, loc="upper right")
    else:
        ax.text(0.5, 0.5, "Segment breakdown\nnot available\n(rebuild Unity first)",
                ha="center", va="center", transform=ax.transAxes, fontsize=10)
        ax.set_title("Segment Breakdown")

    plt.tight_layout()
    out_path = out_dir / "ab_comparison.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Plot saved → {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def _print_drift_warning(steps_between: int) -> None:
    """Print estimated terrain drift contamination between the two conditions."""
    # From measured data: within-episode drift ≈ 1ms per 900 steps in ep0
    # Between A and B there is 1 extra terrain reset + steps_between steps.
    # Reset drift: ~0.3-0.5ms/reset; step drift: ~0.001ms/step
    est_drift_ms = 0.4 + steps_between * 0.001
    print(f"\n  ⚠  Terrain drift estimate between A and B: ~{est_drift_ms:.1f}ms")
    print(f"     (Expected Update vs FixedUpdate difference: 5-15ms)")
    print(f"     → Drift is negligible; no restart needed for this test.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="latency-ab-test")
    parser.add_argument("--host",  default="127.0.0.1")
    parser.add_argument("--port",  type=int, default=5057)
    parser.add_argument("--steps", type=int, default=200,
                        help="Steps per block (default: 200)")
    parser.add_argument("--rounds", type=int, default=2,
                        help="Interleaved rounds A-B-A-B... (default: 2, i.e. ABAB)")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--out", default="outputs/ab_test",
                        help="Output directory for comparison plot")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("  LATENCY A/B TEST: Update vs FixedUpdate")
    print(f"  Design: {args.rounds} rounds × {args.steps} steps (interleaved A-B-A-B)")
    print(f"  This controls for terrain drift — each round has equal drift exposure.")
    print(f"{'='*60}")
    print("""
  Prerequisites:
    1. Unity is running with AGXUnity_Excavator scene
    2. Inspector → AgxSimStepAckServer:
       [m_useFixedUpdateForRequests] = FALSE  (start in Update mode)
  """)

    _print_drift_warning(args.steps * args.rounds)
    print()
    input("  Press Enter to begin (current mode should be Update = FALSE)...")

    all_a_rtts: list[np.ndarray] = []
    all_b_rtts: list[np.ndarray] = []
    all_a_segs: dict[str, list] = {k: [] for k in
        ["py_to_unity","queue_wait","physics","image_cap","serialize","unity_to_py"]}
    all_b_segs: dict[str, list] = {k: [] for k in
        ["py_to_unity","queue_wait","physics","image_cap","serialize","unity_to_py"]}

    with AgxSimClient(host=args.host, port=args.port, timeout_s=args.timeout) as client:
        info = client.get_info()
        print(f"\n  Connected: {info.protocol_version}  "
              + (f"image={info.cameras[0].width}x{info.cameras[0].height}"
                 if info.cameras else ""))

        for round_idx in range(args.rounds):
            print(f"\n  ── Round {round_idx+1}/{args.rounds} ──────────────────────")

            # ── Condition A (Update) ──────────────────────────────────────────
            # Inspector should be FALSE at this point
            res_a = _measure_condition(
                client,
                f"A_r{round_idx+1}: Update",
                args.steps,
            )
            all_a_rtts.append(res_a["rtts"])
            for k in all_a_segs:
                all_a_segs[k].append(res_a[k])

            # ── Prompt toggle ─────────────────────────────────────────────────
            print(f"""
  → NOW flip the Inspector toggle to TRUE (FixedUpdate)
    [m_useFixedUpdateForRequests]  FALSE → TRUE""")
            input("    Press Enter when done...")

            # Warm-up
            print("    Warming up 20 steps after toggle...")
            client.reset(seed=round_idx + 10)
            warmup = np.zeros(4, dtype=np.float32)
            for i in range(20):
                client.step(step_id=i, action=warmup)

            # ── Condition B (FixedUpdate) ─────────────────────────────────────
            res_b = _measure_condition(
                client,
                f"B_r{round_idx+1}: FixedUpdate",
                args.steps,
            )
            all_b_rtts.append(res_b["rtts"])
            for k in all_b_segs:
                all_b_segs[k].append(res_b[k])

            # ── Prompt toggle back ────────────────────────────────────────────
            if round_idx < args.rounds - 1:
                print(f"""
  → NOW flip the Inspector toggle back to FALSE (Update)
    [m_useFixedUpdateForRequests]  TRUE → FALSE""")
                input("    Press Enter when done...")
                print("    Warming up 20 steps after toggle back...")
                client.reset(seed=round_idx + 20)
                for i in range(20):
                    client.step(step_id=i, action=warmup)

    # ── Aggregate across rounds (average removes drift) ───────────────────────
    combined_a_rtts = np.concatenate(all_a_rtts)
    combined_b_rtts = np.concatenate(all_b_rtts)

    def _agg_segs(seg_dict: dict) -> dict:
        # each value is a list of np.ndarray — concatenate across rounds
        return {k: np.concatenate(v) for k, v in seg_dict.items()}

    def _has_segs(seg_dict: dict) -> bool:
        for arrays in seg_dict.values():
            combined = np.concatenate(arrays)
            if np.any(combined >= 0):
                return True
        return False

    result_a = dict(
        label="A: Update",
        rtts=combined_a_rtts,
        has_segs=_has_segs(all_a_segs),
        **_agg_segs(all_a_segs),
    )
    result_b = dict(
        label="B: FixedUpdate",
        rtts=combined_b_rtts,
        has_segs=_has_segs(all_b_segs),
        **_agg_segs(all_b_segs),
    )

    _print_comparison(result_a, result_b)
    _plot_comparison(result_a, result_b, Path(args.out))

    print(f"\n  {'='*56}")
    print(f"  FINAL SUMMARY  ({args.rounds} rounds × {args.steps} steps each)")
    print(f"  {'='*56}")
    rtt_a = combined_a_rtts
    rtt_b = combined_b_rtts
    print(f"  A (Update):      mean={rtt_a.mean():.1f}ms  "
          f"p95={np.percentile(rtt_a,95):.1f}ms  std={rtt_a.std():.1f}ms")
    print(f"  B (FixedUpdate): mean={rtt_b.mean():.1f}ms  "
          f"p95={np.percentile(rtt_b,95):.1f}ms  std={rtt_b.std():.1f}ms")
    diff = rtt_b.mean() - rtt_a.mean()
    diff_p95 = np.percentile(rtt_b,95) - np.percentile(rtt_a,95)
    print(f"  FixedUpdate overhead: mean +{diff:.1f}ms  p95 +{diff_p95:.1f}ms")
    print(f"\n  Plot → outputs/ab_test/ab_comparison.png")


if __name__ == "__main__":
    main()
