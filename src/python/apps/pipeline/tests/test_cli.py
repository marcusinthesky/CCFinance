"""Exercise the installed CLI and reserved stages namespace."""

import subprocess
import sys

from pipeline.cli import app
from typer.testing import CliRunner


def test_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_stages() -> None:
    result = CliRunner().invoke(app, ["stages", "list"])
    assert result.exit_code == 0
    assert "No data processing stages registered" in result.stdout


def test_unknown_stage_fails() -> None:
    assert CliRunner().invoke(app, ["stages", "missing"]).exit_code != 0


def test_module_entry_point() -> None:
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and arguments
        [sys.executable, "-m", "pipeline", "--help"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "stages" in result.stdout
