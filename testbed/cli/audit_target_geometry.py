"""CLI for auditing AGX target-geometry coverage in HDF5 datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.data.target_geometry_audit import audit_target_geometry_dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-audit-target-geometry",
        description=(
            "Check whether a dataset carries the explicit target geometry fields "
            "required for target-safety training."
        ),
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Directory containing episode_*.hdf5 files.",
    )
    parser.add_argument(
        "--min-step-coverage",
        type=float,
        default=0.999,
        help="Minimum valid-step coverage required to mark the dataset usable.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write the audit JSON.",
    )
    args = parser.parse_args()

    payload = audit_target_geometry_dataset(
        args.dataset_dir,
        min_step_coverage=float(args.min_step_coverage),
    )
    text = json.dumps(payload, indent=2, sort_keys=True)
    print(text)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n")


if __name__ == "__main__":
    main()
