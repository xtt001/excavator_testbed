"""Collect the completed bounded ACT regression causal matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testbed.eval.act_regression_live_matrix import (
    collect_act_regression_live_evidence,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-collect-act-regression-live-evidence",
        description=(
            "Validate and collect the completed 3x4 bounded live matrix, "
            "then write the no-overwrite evidence matrix and root-cause report."
        ),
    )
    parser.add_argument("--live-manifest", type=Path, required=True)
    parser.add_argument("--offline-a0", type=Path, required=True)
    parser.add_argument("--offline-a1", type=Path, required=True)
    parser.add_argument("--evidence-matrix", type=Path, required=True)
    parser.add_argument("--diagnosis", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    result = collect_act_regression_live_evidence(
        live_manifest_path=args.live_manifest,
        offline_a0_path=args.offline_a0,
        offline_a1_path=args.offline_a1,
        evidence_matrix_output_path=args.evidence_matrix,
        diagnosis_output_path=args.diagnosis,
        report_output_path=args.report,
    )
    print(
        json.dumps(
            {
                "schema": result["evidence_matrix"]["schema"],
                "status": result["evidence_matrix"]["status"],
                "root_cause_classification": result["diagnosis"][
                    "root_cause_classification"
                ],
                "evidence_matrix": str(args.evidence_matrix.resolve()),
                "diagnosis": str(args.diagnosis.resolve()),
                "report": str(args.report.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
