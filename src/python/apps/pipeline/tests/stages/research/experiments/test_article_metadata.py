"""Exercise benchmark statistics against a tiny extraction output."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.cli import app
from typer.testing import CliRunner

WINDOW = "{'start': 0, 'stop': 9, 'article_form': [0.8, 0.2], 'event_family': [%s]}"


@pytest.mark.integration
def test_report_excludes_diagnostics_from_sample_statistics(tmp_path: Path) -> None:
    # Arrange: four sampled articles, two with companies, and one diagnostic.
    benchmark = tmp_path / "benchmark"
    (benchmark / "articles").mkdir(parents=True)
    (benchmark / "mentions").mkdir()
    labels = {"financial_sentiment": ["positive", "negative"]}
    labels |= {"local_relevance": ["substantive", "incidental"]}
    (benchmark / "schema.json").write_text(json.dumps({"labels": labels}))
    progress = {"articles_per_second": 100.0, "peak_cuda_reserved_bytes": 2**30}
    (benchmark / "progress.json").write_text(json.dumps(progress))
    diagnostics = tmp_path / "diagnostics.jsonl"
    case = {"id": "diagnostic:case", "text": "Apple", "expectation": "Apple"}
    diagnostics.write_text(json.dumps(case) + "\n")
    articles = [("a", 0.9), ("b", 0.1), ("c", 0.2), ("d", 0.3)]
    articles.append(("diagnostic:case", 0.9))
    mentions = [
        ("a", "company", "Acme", [0.7, 0.3]),
        ("a", "person", "Ann", None),
        ("b", "company", "Beta", [0.2, 0.8]),
        ("diagnostic:case", "company", "Apple", [0.6, 0.4]),
    ]
    with duckdb.connect() as con:
        values = ", ".join(
            f"('{name}', 'ok', 1, 'reporting', [{WINDOW % score}])"
            for name, score in articles
        )
        con.execute(
            f"""COPY (SELECT * FROM (VALUES {values})
            AS t(id, status, n_windows, article_form, windows))
            TO ? (FORMAT parquet)""",  # noqa: S608 - authored test values.
            [str(benchmark / "articles/part.parquet")],
        )
        con.execute(
            """CREATE TABLE mentions (id VARCHAR, entity_type VARCHAR, text VARCHAR,
            start INTEGER, financial_sentiment FLOAT[], local_relevance FLOAT[])"""
        )
        con.executemany(
            "INSERT INTO mentions VALUES (?, ?, ?, 0, ?, ?)",
            [(*row, row[3]) for row in mentions],
        )
        con.execute("COPY mentions TO ?", [str(benchmark / "mentions/part.parquet")])
    output = tmp_path / "report"

    # Act: report the benchmark.
    result = CliRunner().invoke(
        app,
        [
            *("stages", "research", "report-article-metadata"),
            *("--benchmark", str(benchmark), "--diagnostics", str(diagnostics)),
            *("--output", str(output)),
        ],
    )

    # Assert: statistics use only the four sampled articles.
    assert result.exit_code == 0, result.output
    metrics = json.loads((output / "metrics.json").read_text())
    share = metrics["company_article_share"]
    assert share["estimate"] == 0.5
    assert share["wilson95_low"] < 0.5 < share["wilson95_high"]
    assert metrics["mentions_per_article"] == {"company": 0.5, "person": 0.25}
    assert metrics["event_family_windows_below_threshold"] == 0.75
    sentiment = metrics["financial_sentiment"]
    assert sentiment["winner_shares"] == {"positive": 0.5, "negative": 0.5}
    assert sentiment["median_margin"] == pytest.approx(0.5)
    cases = json.loads((output / "diagnostics.json").read_text())
    assert cases["diagnostic:case"]["mentions"] == {"company": ["Apple (positive)"]}
