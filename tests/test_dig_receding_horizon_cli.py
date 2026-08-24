from __future__ import annotations

from pathlib import Path

import pytest

from testbed.cli import dig_act_receding_horizon_dispatch_diagnostic as cli


def test_dispatch_diagnostic_is_default_off() -> None:
    args = cli.parse_args([])

    assert args.execute_offline_diagnostic is False
    assert args.dry_run is False


def test_dry_run_never_calls_full_runtime_backend_or_unity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = {"dry": 0, "full": 0}

    def dry_run(**_: object) -> dict:
        calls["dry"] += 1
        return {"status": "dry_run", "unity_started": False, "action_sent": False}

    def forbidden_full(**_: object) -> dict:
        calls["full"] += 1
        raise AssertionError("full diagnostic/backend path must not run")

    monkeypatch.setattr(cli, "run_diagnostic_dry_run", dry_run)
    monkeypatch.setattr(cli, "run_offline_dispatch_diagnostic", forbidden_full)

    result = cli.main(["--dry-run", "--output-dir", str(tmp_path / "unused")])

    assert result == 0
    assert calls == {"dry": 1, "full": 0}


def test_full_run_requires_explicit_opt_in(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--output-dir", str(tmp_path / "must-not-exist")])
