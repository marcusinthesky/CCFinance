"""Check article date status, canonical copies and usability."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.cli import app
from typer.testing import CliRunner

# id, publish date, capture time (UTC), text hash, normalized URL, copies.
RAW = [
    ("a1", "2020-01-10", "2020-01-10 09:00", 1, "u/a1", 3),
    ("a2", "2020-01-10", "2020-01-12 09:00", 1, "u/a2", 1),
    ("a3", "2019-01-01", "2020-01-10 09:00", 3, "u/a3", 1),
    ("a4", "2020-01-11", "2020-01-10 08:00", 4, "u/a4", 1),
    ("a5", "2020-01-12", "2020-01-10 08:00", 5, "u/a5", 1),
    ("a6", "", "2020-01-10 08:00", 6, "u/a6", 1),
    ("a7", "2020-01-03", "2020-01-10 08:00", 7, "u/shared", 1),
    ("a8", "2020-01-03", "2020-01-04 08:00", 8, "u/shared", 1),
    ("a9", "2020-01-02", "2020-01-10 08:00", 9, "u/a9", 1),
]
FORMS = {"a1": "reporting", "a2": "reporting", "a3": "press release"}


def _fixture(root: Path) -> list[str]:
    """Write one raw shard and GLiNER article forms under root."""
    raw = root / "raw/2020-01/eng_Latn/part-000000.parquet"
    forms = root / "extraction/articles/2020-01--eng_Latn--part-000000--000.parquet"
    for folder in (raw.parent, forms.parent):
        folder.mkdir(parents=True)
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE raw (id VARCHAR, text VARCHAR, metadata STRUCT("
            "publish_date VARCHAR, warc_date TIMESTAMPTZ, url_hostname VARCHAR, "
            "text_length INTEGER, sampling_weight BIGINT, text_xxhash64 UBIGINT, "
            "normalized_url VARCHAR))"
        )
        con.executemany(
            "INSERT INTO raw VALUES (?, 'body', {'publish_date': ?, "
            "'warc_date': (?::TIMESTAMP AT TIME ZONE 'UTC'), "
            "'url_hostname': 'www.Example.com', 'text_length': 900, "
            "'sampling_weight': ?, 'text_xxhash64': ?, 'normalized_url': ?})",
            [(i, day, at, copies, text, url) for i, day, at, text, url, copies in RAW],
        )
        con.table("raw").write_parquet(str(raw))
        con.execute(
            "CREATE TABLE forms (id VARCHAR, status VARCHAR, article_form VARCHAR)"
        )
        con.executemany("INSERT INTO forms VALUES (?, 'ok', ?)", list(FORMS.items()))
        con.table("forms").write_parquet(str(forms))
    return [
        "stages", "processed", "prepare-articles",
        "--source", str(root / "raw"), "--extraction", str(root / "extraction"),
        "--max-lag-days", "7", "--output", str(root / "out"),
    ]  # fmt: skip


@pytest.mark.integration
def test_prepare_articles_flags_dates_and_keeps_earliest_copy(tmp_path: Path) -> None:
    # Arrange: dates around each status boundary, and text and URL repeats.
    arguments = _fixture(tmp_path)

    # Act: prepare the article table.
    result = CliRunner().invoke(app, arguments)

    # Assert: statuses, canonical copies and usability follow the rules.
    assert result.exit_code == 0, result.output
    with duckdb.connect() as con:
        rows = {
            row[0]: row[1:]
            for row in con.execute(
                "SELECT id, date_status, lag_days, duplicate_of, duplicate_kind, "
                "canonical, usable, copies, article_form, host FROM read_parquet(?)",
                [str(tmp_path / "out/articles.parquet")],
            ).fetchall()
        }
    assert rows["a1"] == (
        "consistent", 0, None, None, True, True, 3, "reporting", "example.com",
    )  # fmt: skip
    assert rows["a2"][:6] == ("consistent", 2, "a1", "text", False, False)
    assert rows["a3"][:2] == ("archival", 374)
    assert rows["a3"][7] == "press release"
    assert rows["a4"][:2] == ("consistent", -1)
    assert rows["a5"][:2] == ("future", -2)
    assert rows["a6"][:2] == ("missing", None)
    assert rows["a7"][:6] == ("consistent", 7, "a8", "url", False, False)
    assert rows["a8"][4:6] == (True, True)
    assert rows["a9"][:2] == ("archival", 8)
    summary = json.loads((tmp_path / "out/summary.json").read_text())
    assert summary["articles"] == len(RAW)
    assert (summary["text_duplicates"], summary["url_duplicates"]) == (1, 1)
    assert summary["date_status"] == {
        "consistent": 5, "archival": 2, "future": 1, "missing": 1,
    }  # fmt: skip
    assert summary["usable"] == 3
