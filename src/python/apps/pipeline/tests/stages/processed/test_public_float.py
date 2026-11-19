"""Check public-float tabulation by filer and measurement date."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.cli import app
from typer.testing import CliRunner


@pytest.mark.integration
def test_prepare_public_float_keeps_one_row_per_filer_and_date(
    tmp_path: Path,
) -> None:
    # Arrange: two frames, one filer reported twice for the same date.
    frames = tmp_path / "raw/frames"
    frames.mkdir(parents=True)
    apple = {"cik": 320193, "end": "2019-03-29", "val": 8.7e11, "accn": "a1"}
    restated = apple | {"val": 8.8e11, "accn": "a2"}
    ford = {"cik": 37996, "end": "2019-06-28", "val": 3.9e10, "accn": "f1"}
    (frames / "CY2019Q1I.json").write_text(json.dumps({"data": [apple, restated]}))
    (frames / "CY2019Q2I.json").write_text(json.dumps({"data": [ford]}))
    arguments = ["stages", "processed", "prepare-public-float"]
    arguments += ["--source", str(tmp_path / "raw"), "--output", str(tmp_path / "out")]

    # Act: tabulate the frames.
    result = CliRunner().invoke(app, arguments)

    # Assert: the latest accession wins and each frame is recorded.
    assert result.exit_code == 0, result.output
    with duckdb.connect() as con:
        rows = con.execute(
            "SELECT cik, measured::VARCHAR, value_usd, frame FROM read_parquet(?)",
            [str(tmp_path / "out/public_float.parquet")],
        ).fetchall()
    assert rows == [
        (37996, "2019-06-28", 3.9e10, "CY2019Q2I"),
        (320193, "2019-03-29", 8.8e11, "CY2019Q1I"),
    ]
