"""Exercise the historical acquisition against local Parquet files."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.cli import app
from typer.testing import CliRunner


@pytest.mark.integration
def test_filter_preserves_english_publisher_rows(tmp_path: Path) -> None:
    # Arrange: create two source shards and a historical-style domain list.
    source = tmp_path / "input/2020-01/eng_Latn/part-000000.parquet"
    source.parent.mkdir(parents=True)
    domains = tmp_path / "domains.csv"
    domains.write_text("domain\nexample.com\n", encoding="utf-8")
    with duckdb.connect() as con:
        con.execute(
            """COPY (SELECT * FROM (VALUES
                ('1', 'one', {'url_hostname': 'EXAMPLE.COM.', 'url': 'https://wrong.test/a'}),
                ('2', 'two', {'url_hostname': 'news.example.com', 'url': 'https://wrong.test/b'}),
                ('3', 'three', {'url_hostname': '', 'url': 'https://example.com/c'}),
                ('4', 'four', {'url_hostname': 'notexample.com', 'url': 'https://example.com/d'})
            ) AS rows(id, text, metadata)) TO ? (FORMAT PARQUET)""",
            [str(source)],
        )
        second = source.parent / "part-000001.parquet"
        con.execute(
            "COPY (SELECT * FROM read_parquet($source) WHERE id = '2') "
            "TO $target (FORMAT PARQUET)",
            {"source": str(source), "target": str(second)},
        )

    output = tmp_path / "output"
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "source": str(source.parent / "*.parquet"),
                "domains": str(domains),
                "output": str(output),
            }
        ),
        encoding="utf-8",
    )

    # Act: filter the source through the public CLI.
    result = CliRunner().invoke(
        app, ["stages", "raw", "filter-fine-news", "--config", str(config)]
    )

    # Assert: only eligible rows and their original fields are preserved.
    assert result.exit_code == 0, result.output
    target = output / "articles.parquet"
    with duckdb.connect() as con:
        result = con.execute(
            "SELECT id, text, metadata.url_hostname, metadata.url "
            "FROM read_parquet(?) ORDER BY id",
            [str(target)],
        ).fetchall()
    assert result == [
        ("1", "one", "EXAMPLE.COM.", "https://wrong.test/a"),
        ("2", "two", "news.example.com", "https://wrong.test/b"),
        ("2", "two", "news.example.com", "https://wrong.test/b"),
        ("3", "three", "", "https://example.com/c"),
    ]
