"""Check the coverage report's screen, near-duplicate audit and outputs."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.cli import app
from typer.testing import CliRunner

STORY = " ".join(f"acme{index}" for index in range(80))
# id, cik, mentions, text; every article is usable and captured in May 2019.
ARTICLES = [
    ("a1", 1, 4, STORY),
    ("a2", 1, 1, STORY + " reporting by a wire desk"),
    ("a3", 1, 3, "Acme opened a new plant in Ohio, adding two hundred jobs. " * 4),
    ("a4", 2, 5, "Beta named a new chief executive on Monday morning. " * 4),
]
LINK_ESTIMATE = {"estimate": 0.9, "ci95_low": 0.8, "ci95_high": 1.0, "n": 10}


def _estimates() -> dict[str, object]:
    names = ("link_precision", "recall", "article_recall")
    return {"estimates": dict.fromkeys(names, LINK_ESTIMATE)}


def _fixture(root: Path) -> list[str]:
    """Write articles, raw text, links, a panel, roster and quality inputs."""
    for folder in ("articles", "raw/2019-05/eng_Latn", "links/articles", "panel"):
        (root / folder).mkdir(parents=True)
    (root / "focus").mkdir()
    focus = {"test": {"precision": LINK_ESTIMATE, "recall": LINK_ESTIMATE}}
    (root / "focus/metrics.json").write_text(json.dumps(focus))
    (root / "focus/curve.csv").write_text(
        "rule,value,split,precision,recall,f1\n"
        "min_mentions,1,dev,0.3,0.9,0.45\nmin_mentions,1,test,0.3,0.9,0.45\n"
    )
    (root / "links.json").write_text(
        json.dumps({"pooled": _estimates(), "test": _estimates()})
    )
    with duckdb.connect() as con:
        con.execute("CREATE TABLE raw (id VARCHAR, text VARCHAR)")
        con.executemany(
            "INSERT INTO raw VALUES (?, ?)", [(a, text) for a, _, _, text in ARTICLES]
        )
        con.table("raw").write_parquet(str(root / "raw/2019-05/eng_Latn/p.parquet"))
        con.execute(
            "CREATE TABLE articles AS SELECT id, 'example.com' AS host, "
            "DATE '2019-05-01' AS published, TIMESTAMP '2019-05-01 09:00' AS captured, "
            "0 AS lag_days, 'consistent' AS date_status, 1 AS copies, "
            "'reporting' AS article_form, true AS canonical, true AS usable FROM raw"
        )
        con.table("articles").write_parquet(str(root / "articles/articles.parquet"))
        con.execute(
            "CREATE TABLE links (id VARCHAR, cik BIGINT, link_score DOUBLE, "
            "relevance_substantive FLOAT, first_offset_share DOUBLE, "
            "n_mentions BIGINT, self_publisher BOOLEAN)"
        )
        con.executemany(
            "INSERT INTO links VALUES (?, ?, 0.9, 0.5, 0.0, ?, false)",
            [(a, cik, mentions) for a, cik, mentions, _ in ARTICLES],
        )
        con.table("links").write_parquet(str(root / "links/articles/u.parquet"))
        con.execute(
            """CREATE TABLE panel AS
            SELECT cik, year::INTEGER AS year, 'Firm' AS name, '3571' AS sic,
                   'Manufacturing' AS division, true AS in_universe, 'float' AS basis,
                   1e9 * cik AS float_usd, DATE '2019-03-01' AS float_measured,
                   cik::BIGINT AS size_band, false AS partial_year,
                   60 * (2 - cik) AS raw, 60 * (2 - cik) AS dated,
                   50 * (2 - cik) AS usable, 10 * (2 - cik) AS focused,
                   0 AS press_releases, 0 AS self_published,
                   3 AS publishers, 50 AS copies
            FROM (VALUES (1), (2)) AS c(cik), range(2017, 2026) AS y(year)"""
        )
        con.table("panel").write_parquet(str(root / "panel/panel.parquet"))
        con.execute(
            "CREATE TABLE roster AS SELECT 'ACME' AS ticker, 'Acme' AS name, "
            "1::BIGINT AS cik, 'matched' AS status"
        )
        con.table("roster").write_parquet(str(root / "panel/pp_roster.parquet"))
    return [
        "stages", "research", "report-coverage",
        "--panel", str(root / "panel"), "--articles", str(root / "articles"),
        "--links", str(root / "links"), "--source", str(root / "raw"),
        "--link-metrics", str(root / "links.json"), "--focus", str(root / "focus"),
        "--months", "1", "--sample-size", "10", "--output", str(root / "out"),
    ]  # fmt: skip


@pytest.mark.integration
def test_report_screens_issuers_and_finds_same_issuer_near_duplicates(
    tmp_path: Path,
) -> None:
    # Arrange: one roster issuer above the raw screen, one wire repeat.
    arguments = _fixture(tmp_path)

    # Act: write the report.
    result = CliRunner().invoke(app, arguments)

    # Assert: screen counts, the near-duplicate pair and every output.
    assert result.exit_code == 0, result.output
    metrics = json.loads((tmp_path / "out/metrics.json").read_text())
    screen = metrics["pp_screen"]
    assert (screen["roster_raw"]["passing"], screen["roster_focused"]["passing"]) == (
        1, 0,
    )  # fmt: skip
    assert screen["all_usable"] == {
        "firms": 2, "passing": 1, "median_weakest_year": 50, "passing_in_roster": 1,
    }  # fmt: skip
    near = metrics["near_duplicates"]
    assert (near["sampled"], near["with_near_duplicate"]) == (4, 2)
    assert metrics["funnel"]["focused"] == 3
    report = (tmp_path / "out/report.tex").read_text()
    for name in ("funnel", "screen", "survival", "consecutive", "quality"):
        assert rf"\input{{tables/{name}.tex}}" in report
        assert (tmp_path / f"out/tables/{name}.tex").exists()
    for name in ("volume", "lag", "ccdf", "survival", "size", "lorenz", "focus"):
        assert rf"\input{{figures/{name}.tex}}" in report
    assert (
        (tmp_path / "out/figures/survival.csv")
        .read_text()
        .startswith("threshold,all_raw,all_usable,all_focused,roster_raw")
    )
