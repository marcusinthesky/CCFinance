"""Check the firm-year coverage panel, its universe and the roster mapping."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.cli import app
from typer.testing import CliRunner

ISSUERS = [(1, "Apple", "3571"), (2, "Bank", "6022"), (3, "New", "7372")]
ISSUERS += [(9, "ASML", "3674")]
# cik, ticker, exchange, source, listed from, listed to.
TICKERS = [
    (1, "AAPL", "Nasdaq", "sec", None, None),
    (2, "BNK", "New York Stock Exchange", "wikidata", "2015-01-01", "2019-06-30"),
    (3, "NEW", "Nasdaq", "sec", None, None),
    (9, "ASML", "Nasdaq", "sec", None, None),
]
FLOATS = [(1, "2019-03-29", 8e11), (1, "2020-03-27", 1e12)]
# id, cik, day, link score, mentions; article status, canonical, form.
LINKS = [
    ("x1", 1, "2019-05-01", 0.9, 3, "consistent", True, "reporting"),
    ("x2", 1, "2019-05-02", 0.9, 1, "consistent", True, "press release"),
    ("x3", 1, "2019-06-01", 0.9, 4, "archival", True, "reporting"),
    ("x4", 1, "2019-06-02", 0.3, 3, "consistent", True, "reporting"),
    ("x5", 9, "2020-01-10", 0.9, 5, "consistent", True, "reporting"),
    ("x6", 1, "2019-07-01", 0.9, 3, "consistent", False, "reporting"),
]
ROSTER = "ticker,name,cik\naapl,Apple,\nASML,ASML,\nZZZZ,Unknown,\nBNK,Bank,2\n"


def _fixture(root: Path) -> list[str]:
    """Write articles, links, issuers, public float and a roster under root."""
    for folder in ("articles", "links/articles", "issuers", "float"):
        (root / folder).mkdir(parents=True)
    (root / "roster.csv").write_text(ROSTER)
    with duckdb.connect() as con:
        con.execute("CREATE TABLE issuers (cik BIGINT, name VARCHAR, sic VARCHAR)")
        con.executemany("INSERT INTO issuers VALUES (?, ?, ?)", ISSUERS)
        con.table("issuers").write_parquet(str(root / "issuers/issuers.parquet"))
        con.execute(
            "CREATE TABLE tickers (cik BIGINT, ticker VARCHAR, exchange VARCHAR, "
            "source VARCHAR, valid_from DATE, valid_to DATE)"
        )
        con.executemany("INSERT INTO tickers VALUES (?, ?, ?, ?, ?, ?)", TICKERS)
        con.table("tickers").write_parquet(str(root / "issuers/tickers.parquet"))
        con.execute("CREATE TABLE f (cik BIGINT, measured DATE, value_usd DOUBLE)")
        con.executemany("INSERT INTO f VALUES (?, ?, ?)", FLOATS)
        con.table("f").write_parquet(str(root / "float/public_float.parquet"))
        con.execute(
            "CREATE TABLE links (id VARCHAR, cik BIGINT, day DATE, link_score DOUBLE, "
            "relevance_substantive FLOAT, first_offset_share DOUBLE, "
            "n_mentions BIGINT, self_publisher BOOLEAN)"
        )
        con.executemany(
            "INSERT INTO links VALUES (?, ?, ?, ?, 0.5, 0.0, ?, false)",
            [row[:5] for row in LINKS],
        )
        con.table("links").write_parquet(str(root / "links/articles/u.parquet"))
        con.execute(
            "CREATE TABLE articles (id VARCHAR, date_status VARCHAR, "
            "canonical BOOLEAN, usable BOOLEAN, host VARCHAR, "
            "article_form VARCHAR, copies BIGINT)"
        )
        con.executemany(
            "INSERT INTO articles VALUES (?, ?, ?, ? AND ? = 'consistent', "
            "'example.com', ?, 2)",
            [(r[0], r[5], r[6], r[6], r[5], r[7]) for r in LINKS],
        )
        con.table("articles").write_parquet(str(root / "articles/articles.parquet"))
    return [
        "stages", "research", "build-coverage-panel",
        "--articles", str(root / "articles"), "--links", str(root / "links"),
        "--issuers", str(root / "issuers"), "--public-float", str(root / "float"),
        "--roster", str(root / "roster.csv"), "--min-mentions", "3",
        "--first-year", "2018", "--last-year", "2021",
        "--complete-from", "2019", "--complete-through", "2020",
        "--output", str(root / "out"),
    ]  # fmt: skip


@pytest.mark.integration
def test_panel_counts_the_funnel_over_an_evidenced_universe(tmp_path: Path) -> None:
    # Arrange: dated and float-evidenced listings, and links through the funnel.
    arguments = _fixture(tmp_path)

    # Act: build the panel.
    result = CliRunner().invoke(app, arguments)

    # Assert: universe membership, zero rows, funnel counts and roster matches.
    assert result.exit_code == 0, result.output
    with duckdb.connect() as con:
        panel = {
            (row[0], row[1]): row[2:]
            for row in con.execute(
                "SELECT cik, year, in_universe, basis, partial_year, raw, dated, "
                "usable, focused, press_releases, copies, size_band, division "
                "FROM read_parquet(?)",
                [str(tmp_path / "out/panel.parquet")],
            ).fetchall()
        }
        roster = con.execute(
            "SELECT ticker, cik, status FROM read_parquet(?)",
            [str(tmp_path / "out/pp_roster.parquet")],
        ).fetchall()
    assert sorted(panel) == [
        (1, 2019), (1, 2020), (1, 2021), (2, 2018), (2, 2019), (9, 2020),
    ]  # fmt: skip
    assert panel[1, 2019] == (
        True, "float", False, 4, 3, 2, 1, 1, 4, 1, "Manufacturing",
    )  # fmt: skip
    assert panel[1, 2021][:8] == (True, "float", True, 0, 0, 0, 0, 0)
    assert panel[2, 2018][:3] == (True, "dated", True)
    assert panel[2, 2019][-1] == "Finance"
    assert panel[9, 2020][:2] == (False, None)
    assert panel[9, 2020][3:7] == (1, 1, 1, 1)
    assert roster == [
        ("AAPL", 1, "matched"),
        ("ASML", 9, "matched"),
        ("ZZZZ", None, "unmatched"),
        ("BNK", 2, "override"),
    ]
    summary = json.loads((tmp_path / "out/summary.json").read_text())
    assert summary["universe_basis"] == {"dated": 2, "float": 3}
    assert (summary["raw"], summary["usable"], summary["focused"]) == (5, 3, 2)
