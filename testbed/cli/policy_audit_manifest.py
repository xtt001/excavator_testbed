"""CLI for building policy-audit manifests from existing audit JSON files."""

from __future__ import annotations

import argparse
from pathlib import Path

from testbed.eval.policy_audit_manifest import write_policy_audit_manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-policy-audit-manifest",
        description="Summarize existing policy audit JSON artifacts for eval readiness.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output JSON path.")
    parser.add_argument(
        "--dig-ckpt-audit",
        type=Path,
        default=None,
        help="JSON output from tb-audit-dig-ckpt.",
    )
    parser.add_argument(
        "--dig-depth-audit",
        type=Path,
        default=None,
        help="JSON output from tb-audit-dig-depth-semantics.",
    )
    parser.add_argument(
        "--return-ckpt-audit",
        type=Path,
        default=None,
        help="JSON output from tb-audit-return-ckpt.",
    )
    args = parser.parse_args()

    output_path = write_policy_audit_manifest(
        output=args.output,
        dig_ckpt_audit=args.dig_ckpt_audit,
        dig_depth_audit=args.dig_depth_audit,
        return_ckpt_audit=args.return_ckpt_audit,
    )
    print(output_path)


if __name__ == "__main__":
    main()
