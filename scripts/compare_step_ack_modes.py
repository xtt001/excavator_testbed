"""
compare_step_ack_modes.py -- Interactive Update vs FixedUpdate comparison.

This script measures AGX step-ack latency in two Unity request-processing modes:

1. Update
2. FixedUpdate

It prompts the operator to flip the Inspector toggle
`m_useFixedUpdateForRequests` on `AgxSimStepAckServer` between the two modes,
then prints and saves a direct comparison.

Usage
-----
    python scripts/compare_step_ack_modes.py
    python scripts/compare_step_ack_modes.py --steps 300 --rounds 2
    python scripts/compare_step_ack_modes.py --out outputs/step_ack_mode_compare
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from testbed.backends.agx.protocol import AgxSimClient


def _delta_ms(t_end_ns: int, t_start_ns: int) -> float:
    if t_end_ns < 0 or t_start_ns < 0:
        return -1.0
    return (t_end_ns - t_start_ns) / 1e6


def _valid(values: np.ndarray) -> np.ndarray:
    return values[values >= 0]


def _stats(values: np.ndarray) -> dict | None:
    values = _valid(values)
    if len(values) == 0:
        return None
    return {
        "mean": float(values.mean()),
        "std": float(values.std()),
        "min": float(values.min()),
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
        "max": float(values.max()),
        "count": int(len(values)),
    }


def _measure_mode(
    client: AgxSimClient,
    *,
    label: str,
    steps: int,
    seed: int,
) -> dict:
    print(f"\n  Measuring [{label}] ({steps} steps)")
    client.reset(seed=seed, reset_terrain=True, reset_pose=True)

    action = np.zeros(4, dtype=np.float32)
    rtt_ms: list[float] = []
    py_to_unity_ms: list[float] = []
    queue_wait_ms: list[float] = []
    physics_ms: list[float] = []
    image_ms: list[float] = []
    serialize_ms: list[float] = []
    unity_to_py_ms: list[float] = []

    for step_id in range(steps):
        t_send = time.time_ns()
        resp = client.step(step_id=step_id, action=action)
        t_recv = time.time_ns()

        rtt_ms.append((t_recv - t_send) / 1e6)
        py_to_unity_ms.append(_delta_ms(resp.t_req_recv_ns, t_send))
        queue_wait_ms.append(_delta_ms(resp.t_queue_exit_ns, resp.t_req_recv_ns))
        physics_ms.append(_delta_ms(resp.t_physics_done_ns, resp.t_queue_exit_ns))
        image_ms.append(_delta_ms(resp.t_image_ready_ns, resp.t_physics_done_ns))
        serialize_ms.append(_delta_ms(resp.t_resp_queued_ns, resp.t_image_ready_ns))
        unity_to_py_ms.append(_delta_ms(t_recv, resp.t_resp_queued_ns))

        if (step_id + 1) % 50 == 0:
            recent = np.asarray(rtt_ms[-50:], dtype=np.float64)
            print(
                f"    step {step_id + 1:4d}/{steps} "
                f"recent_mean={recent.mean():.2f}ms "
                f"recent_p95={np.percentile(recent, 95):.2f}ms"
            )

    result = {
        "label": label,
        "rtt_ms": np.asarray(rtt_ms, dtype=np.float64),
        "py_to_unity_ms": np.asarray(py_to_unity_ms, dtype=np.float64),
        "queue_wait_ms": np.asarray(queue_wait_ms, dtype=np.float64),
        "physics_ms": np.asarray(physics_ms, dtype=np.float64),
        "image_ms": np.asarray(image_ms, dtype=np.float64),
        "serialize_ms": np.asarray(serialize_ms, dtype=np.float64),
        "unity_to_py_ms": np.asarray(unity_to_py_ms, dtype=np.float64),
    }
    result["has_segments"] = any(np.any(arr >= 0) for key, arr in result.items() if key.endswith("_ms") and key != "rtt_ms")
    return result


def _condition_summary(result: dict) -> dict:
    segment_keys = (
        "py_to_unity_ms",
        "queue_wait_ms",
        "physics_ms",
        "image_ms",
        "serialize_ms",
        "unity_to_py_ms",
    )
    return {
        "label": result["label"],
        "has_segments": bool(result["has_segments"]),
        "rtt_ms": _stats(result["rtt_ms"]),
        "segments_ms": {key: _stats(result[key]) for key in segment_keys},
    }


def _format_stats(values: np.ndarray) -> str:
    values = _valid(values)
    if len(values) == 0:
        return "N/A"
    return (
        f"mean={values.mean():6.2f}ms "
        f"std={values.std():5.2f}ms "
        f"p95={np.percentile(values, 95):6.2f}ms"
    )


def _print_summary(update_result: dict, fixed_result: dict) -> None:
    rows = [
        ("Total RTT", "rtt_ms"),
        ("py -> unity", "py_to_unity_ms"),
        ("queue wait", "queue_wait_ms"),
        ("physics", "physics_ms"),
        ("image", "image_ms"),
        ("serialize", "serialize_ms"),
        ("unity -> py", "unity_to_py_ms"),
    ]

    print("\n" + "=" * 78)
    print("  STEP-ACK MODE COMPARISON")
    print("=" * 78)
    for title, key in rows:
        print(
            f"  {title:<14} "
            f"Update: {_format_stats(update_result[key]):<40} "
            f"FixedUpdate: {_format_stats(fixed_result[key])}"
        )

    update_rtt = update_result["rtt_ms"]
    fixed_rtt = fixed_result["rtt_ms"]
    diff_mean = fixed_rtt.mean() - update_rtt.mean()
    diff_p95 = np.percentile(fixed_rtt, 95) - np.percentile(update_rtt, 95)
    print("-" * 78)
    print(
        f"  FixedUpdate - Update RTT: mean={diff_mean:+.2f}ms  "
        f"p95={diff_p95:+.2f}ms"
    )


def _save_json(
    *,
    out_dir: Path,
    host: str,
    port: int,
    steps: int,
    rounds: int,
    update_result: dict,
    fixed_result: dict,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    update_summary = _condition_summary(update_result)
    fixed_summary = _condition_summary(fixed_result)

    update_rtt = update_summary["rtt_ms"]
    fixed_rtt = fixed_summary["rtt_ms"]
    diff = None
    if update_rtt is not None and fixed_rtt is not None:
        diff = {
            "mean_ms": float(fixed_rtt["mean"] - update_rtt["mean"]),
            "p95_ms": float(fixed_rtt["p95"] - update_rtt["p95"]),
            "p99_ms": float(fixed_rtt["p99"] - update_rtt["p99"]),
        }

    payload = {
        "experiment": "step_ack_mode_compare",
        "host": host,
        "port": int(port),
        "steps_per_block": int(steps),
        "rounds": int(rounds),
        "update": update_summary,
        "fixedupdate": fixed_summary,
        "fixedupdate_minus_update_rtt_ms": diff,
    }

    out_path = out_dir / "step_ack_mode_comparison.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return out_path


def _save_plot(*, out_dir: Path, update_result: dict, fixed_result: dict) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    ax = axes[0]
    bins = np.arange(10, 70, 2)
    ax.hist(update_result["rtt_ms"], bins=bins, alpha=0.6, density=True, label="Update")
    ax.hist(fixed_result["rtt_ms"], bins=bins, alpha=0.6, density=True, label="FixedUpdate")
    ax.axvline(20, color="green", linestyle="--", linewidth=1.2, label="target 20ms")
    ax.axvline(40, color="orange", linestyle=":", linewidth=1.0, label="40ms")
    ax.set_title("RTT Distribution")
    ax.set_xlabel("RTT (ms)")
    ax.set_ylabel("Density")
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.plot(update_result["rtt_ms"][:200], linewidth=0.9, label="Update")
    ax.plot(fixed_result["rtt_ms"][:200], linewidth=0.9, label="FixedUpdate")
    ax.axhline(20, color="green", linestyle="--", linewidth=1.0, alpha=0.6)
    ax.set_title("RTT Time Series (first 200 steps)")
    ax.set_xlabel("Step")
    ax.set_ylabel("RTT (ms)")
    ax.legend(fontsize=8)

    ax = axes[2]
    segs = [
        ("py->unity", "py_to_unity_ms"),
        ("queue", "queue_wait_ms"),
        ("physics", "physics_ms"),
        ("image", "image_ms"),
        ("serialize", "serialize_ms"),
        ("unity->py", "unity_to_py_ms"),
    ]
    bottoms = np.zeros(2, dtype=np.float64)
    x = np.array([0.0, 1.0])
    for label, key in segs:
        values = []
        for result in (update_result, fixed_result):
            arr = _valid(result[key])
            values.append(arr.mean() if len(arr) > 0 else 0.0)
        values_arr = np.asarray(values, dtype=np.float64)
        ax.bar(x, values_arr, width=0.5, bottom=bottoms, label=label)
        bottoms += values_arr
    ax.set_xticks(x)
    ax.set_xticklabels(["Update", "FixedUpdate"])
    ax.set_ylabel("Time (ms)")
    ax.set_title("Mean Segment Breakdown")
    ax.legend(fontsize=7)

    plt.tight_layout()
    out_path = out_dir / "step_ack_mode_comparison.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(prog="compare-step-ack-modes")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5057)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--out", default="outputs/step_ack_mode_compare")
    args = parser.parse_args()

    print("\n" + "=" * 62)
    print("  STEP-ACK MODE COMPARE: Update vs FixedUpdate")
    print("=" * 62)
    print("  1. Start with Inspector toggle set to FALSE (Update).")
    print("  2. Script measures Update.")
    print("  3. Script prompts you to flip toggle to TRUE (FixedUpdate).")
    print("  4. Script measures FixedUpdate and writes JSON/PNG results.")
    print()
    input("  Press Enter to start with Update mode... ")

    update_rounds: list[dict] = []
    fixed_rounds: list[dict] = []

    with AgxSimClient(host=args.host, port=args.port, timeout_s=args.timeout) as client:
        info = client.get_info()
        camera_note = ""
        if info.cameras:
            cam = info.cameras[0]
            camera_note = f" image={cam.width}x{cam.height}"
        print(f"\n  Connected to {args.host}:{args.port} protocol={info.protocol_version}{camera_note}")

        for round_idx in range(args.rounds):
            print(f"\n  Round {round_idx + 1}/{args.rounds}")
            update_rounds.append(
                _measure_mode(
                    client,
                    label=f"Update round {round_idx + 1}",
                    steps=args.steps,
                    seed=100 + round_idx,
                )
            )

            print(
                "\n  Flip Inspector toggle now:\n"
                "    AgxSimStepAckServer.m_useFixedUpdateForRequests = TRUE"
            )
            input("  Press Enter when FixedUpdate mode is ready... ")

            client.reset(seed=1000 + round_idx, reset_terrain=True, reset_pose=True)
            warmup = np.zeros(4, dtype=np.float32)
            for warmup_id in range(20):
                client.step(step_id=warmup_id, action=warmup)

            fixed_rounds.append(
                _measure_mode(
                    client,
                    label=f"FixedUpdate round {round_idx + 1}",
                    steps=args.steps,
                    seed=200 + round_idx,
                )
            )

            if round_idx < args.rounds - 1:
                print(
                    "\n  Flip Inspector toggle back:\n"
                    "    AgxSimStepAckServer.m_useFixedUpdateForRequests = FALSE"
                )
                input("  Press Enter when Update mode is ready again... ")

                client.reset(seed=2000 + round_idx, reset_terrain=True, reset_pose=True)
                for warmup_id in range(20):
                    client.step(step_id=warmup_id, action=warmup)

    def _combine(results: list[dict], label: str) -> dict:
        keys = (
            "rtt_ms",
            "py_to_unity_ms",
            "queue_wait_ms",
            "physics_ms",
            "image_ms",
            "serialize_ms",
            "unity_to_py_ms",
        )
        combined = {"label": label}
        for key in keys:
            combined[key] = np.concatenate([result[key] for result in results], axis=0)
        combined["has_segments"] = any(np.any(combined[key] >= 0) for key in keys if key != "rtt_ms")
        return combined

    update_result = _combine(update_rounds, "Update")
    fixed_result = _combine(fixed_rounds, "FixedUpdate")

    _print_summary(update_result, fixed_result)
    out_dir = Path(args.out)
    json_path = _save_json(
        out_dir=out_dir,
        host=args.host,
        port=args.port,
        steps=args.steps,
        rounds=args.rounds,
        update_result=update_result,
        fixed_result=fixed_result,
    )
    plot_path = _save_plot(out_dir=out_dir, update_result=update_result, fixed_result=fixed_result)

    print("\n  Results saved:")
    print(f"    JSON: {json_path}")
    print(f"    PNG:  {plot_path}")


if __name__ == "__main__":
    main()
