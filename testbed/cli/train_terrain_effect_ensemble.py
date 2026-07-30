"""Train the offline terrain-effect ensemble from episode-grouped JSONL records."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.terrain_effect_ensemble import (
    DEFAULT_GROUPED_FOLD_COUNT,
    TerrainEffectEnsembleConfig,
    train_terrain_effect_ensemble_from_grouped_fold,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m testbed.cli.train_terrain_effect_ensemble",
        description=(
            "Train a 2x64 terrain-effect ensemble with deterministic "
            "episode-grouped evaluation."
        ),
    )
    parser.add_argument("--records-jsonl", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--input-contract",
        choices=("executed_cut", "planned_cut"),
        required=True,
    )
    parser.add_argument(
        "--fold-count",
        type=int,
        default=DEFAULT_GROUPED_FOLD_COUNT,
    )
    parser.add_argument("--eval-fold", type=int, default=0)
    parser.add_argument(
        "--fold-salt",
        default="terrain_effect_episode_grouped_v1",
    )
    parser.add_argument(
        "--config-json",
        type=Path,
        default=None,
        help="Optional JSON overrides; production defaults use five seeds.",
    )
    parser.add_argument("--summary-json", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        records = _read_jsonl(args.records_jsonl)
        config = _read_config(args.config_json)
        artifact = train_terrain_effect_ensemble_from_grouped_fold(
            records=records,
            output_dir=args.output_dir,
            input_contract=args.input_contract,
            fold_count=args.fold_count,
            eval_fold=args.eval_fold,
            fold_salt=args.fold_salt,
            config=config,
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError, RuntimeError) as exc:
        error = {
            "schema": "terrain_effect_ensemble_cli_result_v1",
            "status": "error",
            "error": str(exc),
        }
        _emit(error, args.summary_json)
        return 2
    _emit(artifact, args.summary_json)
    return 0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            if not isinstance(parsed, Mapping):
                raise ValueError(f"JSONL line {line_number} must contain an object.")
            records.append(dict(parsed))
    if not records:
        raise ValueError("records JSONL contains no records.")
    return records


def _read_config(path: Path | None) -> TerrainEffectEnsembleConfig:
    if path is None:
        return TerrainEffectEnsembleConfig()
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, Mapping):
        raise ValueError("config JSON must contain an object.")
    values = dict(parsed)
    if "hidden_dims" in values:
        values["hidden_dims"] = tuple(values["hidden_dims"])
    if "seeds" in values:
        values["seeds"] = tuple(values["seeds"])
    return TerrainEffectEnsembleConfig(**values)


def _emit(result: Mapping[str, Any], output_path: Path | None) -> None:
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if output_path is None:
        print(payload, end="")
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
