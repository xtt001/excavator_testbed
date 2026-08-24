from __future__ import annotations

from pathlib import Path

import pytest

from testbed.cli import dig_goal_action_identifiability_precheck as cli


def test_identifiability_precheck_is_default_off() -> None:
    args = cli.parse_args([])

    assert args.execute_precheck is False
    assert args.dry_run is False


def test_dry_run_never_calls_full_runtime_or_training(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = {"dry": 0, "full": 0}

    def dry(**_: object) -> dict:
        calls["dry"] += 1
        return {
            "status": "dry_run",
            "act_dp_training_started": False,
            "unity_started": False,
        }

    def forbidden(**_: object) -> dict:
        calls["full"] += 1
        raise AssertionError("full precheck/training must not run during dry-run")

    monkeypatch.setattr(cli, "run_identifiability_dry_run", dry)
    monkeypatch.setattr(cli, "run_goal_action_identifiability_precheck", forbidden)

    result = cli.main(["--dry-run", "--output-dir", str(tmp_path / "unused")])

    assert result == 0
    assert calls == {"dry": 1, "full": 0}


def test_full_precheck_requires_explicit_opt_in(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--output-dir", str(tmp_path / "must_not_exist")])
