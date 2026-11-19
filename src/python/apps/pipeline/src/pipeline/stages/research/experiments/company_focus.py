"""Choose and evaluate the rule that marks company-focused article links.

A linked issuer is focused when the article is substantially about it. The
company-links judges labelled each issuer in the uniform article sample as the
subject, mentioned, or a source or venue; that role is the reference, so no new
labels are needed. Candidate rules threshold three linker article scores: the
strongest substantive relevance among the issuer's mentions, the position of
its first mention, and its mention count.

The candidate with the highest F1 on development articles is reported, and the
configured rule is evaluated on test articles, which played no part in choosing
it. A predicted focus is correct only if the link is also correct, so precision
is end to end. Recall is over subjects the judge found in the issuer reference.
Articles are the sampling units, so intervals treat issuers within an article
as clustered.
"""

import csv
import itertools
import json
from pathlib import Path
from typing import Annotated, Any

import duckdb
import typer

from pipeline.stages.research.experiments.company_links import SECURITY, ratio

type Row = dict[str, Any]
RELEVANCE = tuple(round(0.05 * step, 2) for step in range(19))
OFFSETS = (1.0, 0.5, 0.25, 0.1)
MENTIONS = (1, 2, 3, 4, 5, 6)


def _focused(link: Row, rule: Row) -> bool:
    return (
        link["relevance"] >= rule["min_relevance"]
        and link["offset"] <= rule["max_offset"]
        and link["mentions"] >= rule["min_mentions"]
    )


def evaluate(articles: list[Row], rule: Row, population: int) -> Row:
    """Precision, recall and F1 of a rule over sampled articles."""
    rows = []
    for article in articles:
        predicted = [link for link in article["links"] if _focused(link, rule)]
        rows.append(
            {
                "stratum": "all",
                "population": population,
                "predicted": len(predicted),
                "hits": sum(link["subject"] for link in predicted),
                "linked": sum(link["correct"] for link in predicted),
                "subjects": article["subjects"],
            }
        )
    precision = ratio(rows, lambda r: r["hits"], lambda r: r["predicted"])
    recall = ratio(rows, lambda r: r["hits"], lambda r: r["subjects"])
    focus = ratio(rows, lambda r: r["hits"], lambda r: r["linked"])
    p, r = precision["estimate"], recall["estimate"]
    f1 = 2 * p * r / (p + r) if p and r else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "focus_precision": focus,
        "f1": f1,
    }


def _articles(con: duckdb.DuckDBPyConnection) -> list[Row]:
    """Sampled articles with their linked issuers and judged subjects."""
    links = con.sql(
        """WITH pairs AS (
               SELECT d.id, d.day, l.cik, l.relevance_substantive AS relevance,
                      l.first_offset_share AS offset, l.n_mentions AS mentions
               FROM drawn AS d JOIN links AS l USING (id)
           ), matches AS (
               SELECT p.id, p.cik, bool_or(g.role = 'subject') AS subject
               FROM pairs AS p JOIN gold AS g ON g.id = p.id AND (g.cik = p.cik
                   OR security(g.cik, p.day) = security(p.cik, p.day))
               GROUP BY ALL
           )
           SELECT p.id, p.cik, p.relevance, p.offset, p.mentions,
                  m.id IS NOT NULL AS correct, coalesce(m.subject, false) AS subject
           FROM pairs AS p LEFT JOIN matches AS m USING (id, cik)"""
    ).fetchall()
    subjects = dict(
        con.sql(
            "SELECT id, count(*) FROM gold WHERE role = 'subject' GROUP BY id"
        ).fetchall()
    )
    by_id: dict[str, list[Row]] = {}
    for article, _, relevance, offset, mentions, correct, subject in links:
        by_id.setdefault(article, []).append(
            {"relevance": relevance, "offset": offset, "mentions": mentions}
            | {"correct": correct, "subject": subject and correct}
        )
    return [
        {
            "split": split,
            "links": by_id.get(article, []),
            "subjects": subjects.get(article, 0),
        }
        for article, split in con.sql("SELECT id, split FROM drawn").fetchall()
    ]


def report_company_focus(
    sample: Annotated[Path, typer.Option(help="Sample directory.")] = Path(
        "data/processed/experiments/company-links/sample"
    ),
    labels: Annotated[Path, typer.Option(help="Labels directory.")] = Path(
        "data/processed/experiments/company-links/labels"
    ),
    links: Annotated[Path, typer.Option(help="Linker output.")] = Path(
        "data/processed/company-links"
    ),
    issuers: Annotated[Path, typer.Option(help="Prepared issuer tables.")] = Path(
        "data/processed/issuers"
    ),
    threshold: Annotated[float, typer.Option(help="Operating link score.")] = 0.5,
    min_relevance: Annotated[
        float, typer.Option(help="Configured minimum substantive relevance.")
    ] = 0.0,
    max_offset: Annotated[
        float, typer.Option(help="Configured maximum first-mention position.")
    ] = 1.0,
    min_mentions: Annotated[
        int, typer.Option(help="Configured minimum mentions of the issuer.")
    ] = 1,
    output: Annotated[Path, typer.Option(help="Report directory.")] = Path(
        "data/research/experiments/company-focus"
    ),
) -> None:
    """Write the development grid, the chosen rule and test estimates."""
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.read_parquet(str(sample / "articles.parquet")).create_view("drawn")
        con.read_parquet(str(issuers / "tickers.parquet")).create_view("tickers")
        con.execute(SECURITY)
        con.execute(
            """CREATE TABLE gold AS
            SELECT * FROM (
                SELECT a.id, unnest(a.issuers, recursive := true)
                FROM read_json($labels) AS a WHERE a.judge = 'primary'
            ) WHERE cik IS NOT NULL AND role <> 'source_or_venue'""",
            {"labels": str(labels / "articles.jsonl")},
        )
        con.execute(
            """CREATE TABLE links AS
            SELECT id, cik, link_score, relevance_substantive, first_offset_share,
                   n_mentions
            FROM read_parquet($links)
            WHERE link_score >= $threshold""",
            {"links": str(links / "articles" / "*.parquet"), "threshold": threshold},
        )
        population = con.sql("SELECT count(DISTINCT id) FROM links").fetchall()[0][0]
        articles = _articles(con)
    splits = {
        name: [a for a in articles if a["split"] == name] for name in ("dev", "test")
    }
    grid = []
    for relevance, offset, mentions in itertools.product(RELEVANCE, OFFSETS, MENTIONS):
        rule = {"min_relevance": relevance, "max_offset": offset}
        rule["min_mentions"] = mentions
        grid.append(rule | {"dev_f1": evaluate(splits["dev"], rule, population)["f1"]})
    best = max(
        grid,
        key=lambda r: (
            r["dev_f1"],
            -r["min_mentions"],
            r["max_offset"],
            -r["min_relevance"],
        ),
    )
    configured = {"min_relevance": min_relevance, "max_offset": max_offset}
    configured["min_mentions"] = min_mentions
    every_link = {"min_relevance": 0.0, "max_offset": 1.0, "min_mentions": 1}
    metrics = {
        "threshold": threshold,
        "articles": {name: len(rows) for name, rows in splits.items()},
        "configured": configured,
        "dev_best": best,
        "configured_is_dev_best": all(best[k] == v for k, v in configured.items()),
        "dev": evaluate(splits["dev"], configured, population),
        "test": evaluate(splits["test"], configured, population),
        "test_every_link": evaluate(splits["test"], every_link, population),
    }
    curves = [("min_relevance", value) for value in RELEVANCE]
    curves += [("min_mentions", value) for value in MENTIONS]
    with (output / "curve.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rule", "value", "split", "precision", "recall", "f1"])
        for key, value in curves:
            for name, rows in splits.items():
                result = evaluate(rows, every_link | {key: value}, population)
                precision = result["precision"]["estimate"]
                recall = result["recall"]["estimate"]
                writer.writerow([key, value, name, precision, recall, result["f1"]])
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    typer.echo(f"Wrote: {output}")
