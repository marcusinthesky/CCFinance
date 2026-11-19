"""Check stratified link samples and cached, validated adjudication."""

from pathlib import Path

import duckdb
import pytest
from pipeline.cli import app
from typer.testing import CliRunner

UNIT = "2020-01--eng_Latn--part-000000--000.parquet"


def _write(con: duckdb.DuckDBPyConnection, query: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con.sql(query).write_parquet(str(path))


@pytest.mark.integration
def test_sample_links_draws_strata_with_marked_context(tmp_path: Path) -> None:
    # Arrange: three mentions of an issuer alias, one unknown firm and one person.
    with duckdb.connect() as con:
        _write(
            con,
            "SELECT 'a' || i AS id, 'Pre Apple post ' || i AS text, "
            "{'title': 'T', 'publish_date': '2020-01-02', "
            "'warc_date': NULL::TIMESTAMPTZ, 'url_hostname': 'x.com'} AS metadata "
            "FROM range(4) AS r(i)",
            tmp_path / "raw/2020-01/eng_Latn/part-000000.parquet",
        )
        _write(
            con,
            "SELECT 'a' || i AS id, 'company' AS entity_type, 4 AS start, 9 AS stop, "
            "CASE WHEN i < 3 THEN 'Apple' ELSE 'Acme' END AS text "
            "FROM range(4) AS r(i) UNION ALL "
            "SELECT 'a0', 'person', 0, 3, 'Pre'",
            tmp_path / f"extraction/mentions/{UNIT}",
        )
        _write(
            con,
            "SELECT 1 AS cik, 'Apple' AS alias, 'apple' AS key",
            tmp_path / "issuers/aliases.parquet",
        )
    arguments = ["stages", "processed", "sample-links", "--per-stratum", "2"]
    for option in ("extraction", "issuers"):
        arguments += [f"--{option}", str(tmp_path / option)]
    arguments += ["--source", str(tmp_path / "raw")]
    arguments += ["--output", str(tmp_path / "sample")]

    # Act: draw the sample through the public CLI.
    result = CliRunner().invoke(app, arguments)

    # Assert: each stratum keeps its population, size and marked excerpt.
    assert result.exit_code == 0, result.output
    with duckdb.connect() as con:
        rows = con.execute(
            "SELECT stratum, population, sampled, count(*), "
            "bool_and(regexp_full_match(excerpt, 'Pre ⟦Apple⟧ post [0-3]')) "
            "FROM read_parquet(?) GROUP BY ALL ORDER BY ALL",
            [str(tmp_path / "sample/mentions.parquet")],
        ).fetchall()
        articles = con.execute(
            "SELECT count(*) FROM read_parquet(?)",
            [str(tmp_path / "sample/articles.parquet")],
        ).fetchone()
    assert rows == [("none:tail", 1, 1, 1, True), ("one:tail", 3, 2, 2, True)]
    assert articles == (4,)
