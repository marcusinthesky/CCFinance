"""Check the company-focus rule choice and its end-to-end estimates."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.cli import app
from typer.testing import CliRunner

# id, split, judged issuers as (cik, role).
ARTICLES = [
    ("d1", "dev", [(1, "subject")]),
    ("d2", "dev", [(2, "mentioned")]),
    ("t1", "test", [(1, "subject")]),
    ("t2", "test", [(4, "subject")]),
]
# id, linked cik, relevance, first-mention position, mentions.
LINKS = [
    ("d1", 1, 0.4, 0.0, 3),
    ("d2", 2, 0.6, 0.0, 2),
    ("t1", 1, 0.5, 0.0, 4),
    ("t2", 3, 0.5, 0.0, 5),
]


def _fixture(root: Path) -> list[str]:
    """Write a sample, judged roles, linked issuers and tickers under root."""
    for folder in ("sample", "labels", "links/articles", "issuers"):
        (root / folder).mkdir(parents=True)
    with (root / "labels/articles.jsonl").open("w") as handle:
        for article, _, issuers in ARTICLES:
            judged = [{"name": "x", "cik": c, "role": r} for c, r in issuers]
            record = {"id": article, "judge": "primary", "issuers": judged}
            handle.write(json.dumps(record) + "\n")
    with duckdb.connect() as con:
        con.execute("CREATE TABLE drawn (id VARCHAR, split VARCHAR, day DATE)")
        con.executemany(
            "INSERT INTO drawn VALUES (?, ?, DATE '2020-01-01')",
            [(article, split) for article, split, _ in ARTICLES],
        )
        con.table("drawn").write_parquet(str(root / "sample/articles.parquet"))
        con.execute(
            "CREATE TABLE links (id VARCHAR, cik BIGINT, link_score DOUBLE, "
            "relevance_substantive FLOAT, first_offset_share DOUBLE, n_mentions BIGINT)"
        )
        con.executemany("INSERT INTO links VALUES (?, ?, 0.9, ?, ?, ?)", LINKS)
        con.table("links").write_parquet(str(root / "links/articles/u.parquet"))
        con.execute(
            "CREATE TABLE tickers (cik BIGINT, ticker VARCHAR, valid_from DATE, "
            "valid_to DATE)"
        )
        con.executemany(
            "INSERT INTO tickers VALUES (?, ?, NULL, NULL)",
            [(1, "A"), (2, "B"), (3, "C"), (4, "D")],
        )
        con.table("tickers").write_parquet(str(root / "issuers/tickers.parquet"))
    return [
        "stages", "research", "report-company-focus",
        "--sample", str(root / "sample"), "--labels", str(root / "labels"),
        "--links", str(root / "links"), "--issuers", str(root / "issuers"),
        "--min-mentions", "3", "--output", str(root / "out"),
    ]  # fmt: skip


@pytest.mark.integration
def test_focus_rule_is_chosen_on_dev_and_scored_end_to_end_on_test(
    tmp_path: Path,
) -> None:
    # Arrange: only the mention count separates subjects from mentions in dev.
    arguments = _fixture(tmp_path)

    # Act: report the focus rule.
    result = CliRunner().invoke(app, arguments)

    # Assert: dev picks three mentions; test counts the wrong link as an error.
    assert result.exit_code == 0, result.output
    metrics = json.loads((tmp_path / "out/metrics.json").read_text())
    best = metrics["dev_best"]
    assert (best["min_mentions"], best["min_relevance"], best["max_offset"]) == (
        3, 0.0, 1.0,
    )  # fmt: skip
    assert metrics["configured_is_dev_best"]
    test = metrics["test"]
    assert test["precision"]["estimate"] == pytest.approx(0.5)
    assert test["recall"]["estimate"] == pytest.approx(0.5)
    assert test["focus_precision"]["estimate"] == 1.0
    assert metrics["dev"]["f1"] == 1.0
    curve = (tmp_path / "out/curve.csv").read_text().splitlines()
    assert curve[0] == "rule,value,split,precision,recall,f1"
    assert "min_mentions,3,dev,1.0,1.0,1.0" in curve
