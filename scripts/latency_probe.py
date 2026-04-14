"""
latency_probe.py — Measure live step-ack RTT and per-segment breakdown.

Connects to Unity, runs N steps, and prints:
  - Overall RTT distribution (mean / std / p50 / p95 / p99)
  - Per-segment breakdown (if Unity has the new timestamp fields)
  - ASCII histogram of step intervals
  - Session drift (early vs late episodes)

Usage
-----
    python scripts/latency_probe.py                        # 200 steps, default settings
    python scripts/latency_probe.py --steps 500            # more samples
    python scripts/latency_probe.py --steps 200 --resets 3 # 3 episodes of 200 steps each
    python scripts/latency_probe.py --save                  # also write trace.jsonl

This script works WITHOUT the latency module (standalone), and also
optionally logs to the latency module when --save is used.
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


# ── Stats helper ──────────────────────────────────────────────────────────────

def _stats(arr: np.ndarray, label: str) -> None:
    if len(arr) == 0 or np.all(arr < 0):
        print(f"  {label}: N/A (no data)")
        return
    a = arr[arr >= 0]
    if len(a) == 0:
        print(f"  {label}: N/A (all -1, Unity build too old)")
        return
    print(
        f"  {label}: "
        f"n={len(a):5d}  "
        f"mean={a.mean():6.2f}ms  "
        f"std={a.std():5.2f}ms  "
        f"p50={np.percentile(a,50):6.2f}ms  "
        f"p95={np.percentile(a,95):6.2f}ms  "
        f"p99={np.percentile(a,99):6.2f}ms  "
        f"min={a.min():5.2f}ms  max={a.max():5.2f}ms"
    )


def _ascii_hist(arr: np.ndarray, label: str, bins_ms: tuple = (10, 70, 5)) -> None:
    lo, hi, step = bins_ms
    bins = np.arange(lo, hi + step, step)
    hist, _ = np.histogram(arr, bins=bins)
    total = hist.sum()
    print(f"\n  {label} (n={total}):")
    for i, count in enumerate(hist):
        lo_b, hi_b = bins[i], bins[i + 1]
        bar = "█" * (count * 40 // max(hist.max(), 1))
        pct = count / total * 100 if total > 0 else 0
        marker = " ← target" if lo_b <= 20 < hi_b else ""
        print(f"    [{lo_b:3.0f}-{hi_b:3.0f}ms] {bar:<40s} {count:4d} ({pct:4.1f}%){marker}")


# ── Main ──────────────────────────────────────────────────────────────────────

def run_probe(
    host: str = "127.0.0.1",
    port: int = 5057,
    steps_per_episode: int = 200,
    num_episodes: int = 1,
    timeout: float = 10.0,
    save: bool = False,
    out_dir: str = "outputs/latency_probe",
) -> None:
    print(f"\n{'='*60}")
    print(f"  Latency Probe  →  {host}:{port}")
    print(f"  {num_episodes} episode(s) × {steps_per_episode} steps")
    print(f"{'='*60}\n")

    # ── Optional latency module logging ──────────────────────────────────────
    session = None
    if save:
        from testbed.latency_module import LatencySession
        cfg = {
            "latency": {
                "enabled": True,
                "output_dir": out_dir,
                "run_id": f"probe_{time.strftime('%Y%m%d_%H%M%S')}",
                "analysis": {"auto_export_on_close": True},
            }
        }
        session = LatencySession.from_config(cfg)
        session.open()
        session.start_run()

    with AgxSimClient(host=host, port=port, timeout_s=timeout) as client:
        info = client.get_info()
        print(f"Connected: {info.protocol_version}  "
              f"dt={info.dt:.4f}s  hz={info.control_hz:.1f}  "
              f"image={info.cameras[0].width}x{info.cameras[0].height if info.cameras else '?'}")

        if session:
            session.attach_probe(client)

        all_rtt:         list[float] = []
        all_py_to_unity: list[float] = []
        all_queue_wait:  list[float] = []
        all_physics:     list[float] = []
        all_image:       list[float] = []
        all_serialize:   list[float] = []
        all_unity_to_py: list[float] = []

        episode_means: list[float] = []

        action = np.zeros(4, dtype=np.float32)

        for ep_idx in range(num_episodes):
            if session:
                session.start_episode(ep_idx)

            reset = client.reset(seed=ep_idx, reset_terrain=True, reset_pose=True)
            print(f"\n  Episode {ep_idx}: reset_applied={reset.reset_applied}  "
                  f"warnings={list(reset.warnings)}")

            ep_rtts: list[float] = []
            step_id = 0

            for step in range(steps_per_episode):
                t_send = time.time_ns()

                if session:
                    # probe instruments this step automatically
                    resp = client.step(step_id=step_id, action=action)
                else:
                    resp = client.step(step_id=step_id, action=action)

                t_recv = time.time_ns()
                rtt_ms = (t_recv - t_send) / 1e6
                ep_rtts.append(rtt_ms)
                all_rtt.append(rtt_ms)

                # Breakdown (if Unity supports it)
                def _ms(t_unity: int, t_ref: int) -> float:
                    return (t_unity - t_ref) / 1e6 if t_unity > 0 and t_ref > 0 else -1.0

                all_py_to_unity.append(_ms(resp.t_req_recv_ns,     t_send))
                all_queue_wait.append( _ms(resp.t_queue_exit_ns,   resp.t_req_recv_ns))
                all_physics.append(    _ms(resp.t_physics_done_ns, resp.t_queue_exit_ns))
                all_image.append(      _ms(resp.t_image_ready_ns,  resp.t_physics_done_ns))
                all_serialize.append(  _ms(resp.t_resp_queued_ns,  resp.t_image_ready_ns))
                all_unity_to_py.append(_ms(t_recv,                 resp.t_resp_queued_ns))

                step_id += 1

            ep_mean = float(np.mean(ep_rtts))
            episode_means.append(ep_mean)
            print(f"    → mean={ep_mean:.1f}ms  p95={np.percentile(ep_rtts,95):.1f}ms  "
                  f"p99={np.percentile(ep_rtts,99):.1f}ms")

            if session:
                session.end_episode()

    if session:
        session.close()

    # ── Print results ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RESULTS  (target: {1000/info.control_hz:.0f}ms per step @ {info.control_hz:.0f}Hz)")
    print(f"{'='*60}")

    arr = np.array(all_rtt)
    _stats(arr, "Total RTT      ")

    # Breakdown
    has_breakdown = np.array(all_py_to_unity)
    if np.any(has_breakdown >= 0):
        print()
        print("  Per-segment breakdown (Unity timestamps available):")
        print("  " + "-" * 56)
        _stats(np.array(all_py_to_unity),  "py→unity (STEP_REQ net)")
        _stats(np.array(all_queue_wait),   "queue wait (Update tick)")
        _stats(np.array(all_physics),      "AGX DoStep() (physics) ")
        _stats(np.array(all_image),        "Image Collect()        ")
        _stats(np.array(all_serialize),    "Serialize              ")
        _stats(np.array(all_unity_to_py),  "unity→py (STEP_RESP net)")
    else:
        print()
        print("  Per-segment breakdown: NOT AVAILABLE")
        print("  → Unity build does not include latency timestamps yet.")
        print("  → Apply the C# changes to AgxSimProtocol.cs and AgxSimStepAckServer.cs")
        print("  → then rebuild and run again.")

    # Distribution
    _ascii_hist(arr, "RTT distribution")

    # Session drift
    if len(episode_means) > 1:
        print(f"\n  Session drift across {len(episode_means)} episodes:")
        for i, m in enumerate(episode_means):
            bar = "█" * int(m / 2)
            drift = f"  (+{m - episode_means[0]:.1f}ms)" if i > 0 else "  (baseline)"
            print(f"    ep{i:02d}: {m:5.1f}ms  {bar}{drift}")
        total_drift = episode_means[-1] - episode_means[0]
        print(f"  Total drift: {total_drift:+.1f}ms over {len(episode_means)} episodes")

    if save:
        print(f"\n  Trace saved → {out_dir}/")

    print(f"\n{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="latency_probe",
        description="Measure live AGX step-ack RTT and per-segment breakdown.",
    )
    parser.add_argument("--host",    default="127.0.0.1")
    parser.add_argument("--port",    type=int, default=5057)
    parser.add_argument("--steps",   type=int, default=200,
                        help="Steps per episode (default: 200)")
    parser.add_argument("--resets",  type=int, default=1,
                        help="Number of episodes/resets (default: 1)")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--save",    action="store_true",
                        help="Also write trace.jsonl via latency module")
    parser.add_argument("--out",     default="outputs/latency_probe",
                        help="Output dir when --save is set")
    args = parser.parse_args()

    run_probe(
        host=args.host,
        port=args.port,
        steps_per_episode=args.steps,
        num_episodes=args.resets,
        timeout=args.timeout,
        save=args.save,
        out_dir=args.out,
    )


if __name__ == "__main__":
    main()
