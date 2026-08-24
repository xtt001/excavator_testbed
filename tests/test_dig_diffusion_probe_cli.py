from __future__ import annotations

from pathlib import Path

import pytest

from testbed.cli import dig_minimal_diffusion_probe as cli


def test_minimal_dp_probe_is_default_off() -> None:
    args = cli.parse_args([])

    assert args.execute_probe is False
    assert args.dry_run is False


def test_full_probe_requires_explicit_opt_in(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--output-dir", str(tmp_path / "must_not_exist")])
