"""Exercise the installed CLI and data layer command groups."""

import subprocess
import sys

import pytest
from pipeline.cli import app
from typer.testing import CliRunner


def test_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_stages() -> None:
    result = CliRunner().invoke(app, ["stages", "list"])
    assert result.exit_code == 0
    assert "raw: Preserve versioned source snapshots and provenance." in result.stdout
    assert "processed: Build cleaned, deduplicated and enriched" in result.stdout
    assert "research: Curate coverage panels, study cohorts" in result.stdout


@pytest.mark.parametrize("layer", ["raw", "processed", "research"])
def test_layer_help(layer: str) -> None:
    result = CliRunner().invoke(app, ["stages", layer, "--help"])
    assert result.exit_code == 0
    assert layer in result.stdout


@pytest.mark.parametrize("layer", ["raw", "processed", "research"])
def test_unimplemented_layer_command_fails(layer: str) -> None:
    result = CliRunner().invoke(app, ["stages", layer, "build"])
    assert result.exit_code != 0


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
