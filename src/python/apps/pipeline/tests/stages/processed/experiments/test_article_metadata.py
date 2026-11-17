"""Exercise the reproducible benchmark sample against local Parquet files."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.cli import app
from typer.testing import CliRunner


@pytest.mark.integration
def test_sample_ignores_file_layout_and_appends_diagnostics(tmp_path: Path) -> None:
    # Arrange: store the same articles as one file and as two files.
    rows = [(f"id-{index}", f"text {index}") for index in range(20)]
    diagnostics = tmp_path / "diagnostics.jsonl"
    case = {"id": "diagnostic:case", "text": "Apple", "expectation": "One company"}
    diagnostics.write_text(json.dumps(case) + "\n", encoding="utf-8")
    layouts = {"one": [rows], "two": [rows[:7], rows[7:]]}
    with duckdb.connect() as con:
        for layout, parts in layouts.items():
            for index, part in enumerate(parts):
                path = tmp_path / layout / "2020-01" / f"part-{index}.parquet"
                path.parent.mkdir(parents=True, exist_ok=True)
                con.execute("CREATE OR REPLACE TABLE part (id VARCHAR, text VARCHAR)")
                con.executemany("INSERT INTO part VALUES (?, ?)", part)
                con.execute("COPY part TO ? (FORMAT parquet)", [str(path)])

    # Act: sample five raw articles from each layout.
    samples: dict[str, list[tuple[object, ...]]] = {}
    for layout in layouts:
        output = tmp_path / f"sample-{layout}"
        result = CliRunner().invoke(
            app,
            [
                *("stages", "processed", "sample-articles"),
                *("--source", str(tmp_path / layout)),
                *("--diagnostics", str(diagnostics), "--size", "5"),
                *("--output", str(output)),
            ],
        )
        assert result.exit_code == 0, result.output
        with duckdb.connect() as con:
            samples[layout] = con.execute(
                "SELECT id, text FROM read_parquet(?) ORDER BY id",
                [str(output / "articles.parquet")],
            ).fetchall()

    # Assert: both layouts select the same five articles plus the diagnostic.
    assert samples["one"] == samples["two"]
    assert len(samples["one"]) == 6
    assert ("diagnostic:case", "Apple") in samples["one"]
