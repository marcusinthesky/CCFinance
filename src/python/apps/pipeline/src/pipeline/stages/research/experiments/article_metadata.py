"""Summarize metadata extraction on a sample: throughput, coverage and score spread."""

import json
from pathlib import Path
from typing import Annotated

import duckdb
import typer
from statsmodels.stats.proportion import proportion_confint

ATTRIBUTES = ("local_relevance", "financial_sentiment")
DIAGNOSTIC = "id LIKE 'diagnostic:%'"


def _attribute(
    con: duckdb.DuckDBPyConnection, name: str, labels: list[str]
) -> dict[str, object]:
    """Report winning-label shares and how far each winner leads the runner-up."""
    winners, top, margin = con.execute(
        f"""SELECT histogram(list_position({name}, list_max({name}))),
            median(list_max({name})),
            median(list_max({name}) - list_sort({name}, 'DESC')[2])
        FROM mentions WHERE {name} IS NOT NULL AND NOT {DIAGNOSTIC}"""  # noqa: S608
    ).fetchone()
    count = sum(winners.values()) if winners else 0
    return {
        "mentions": count,
        "winner_shares": {
            labels[index - 1]: value / count for index, value in (winners or {}).items()
        },
        "median_winning_score": top,
        "median_margin": margin,
    }


def report_article_metadata(
    benchmark: Annotated[
        Path, typer.Option(help="Extraction output for the sampled articles.")
    ],
    diagnostics: Annotated[
        Path, typer.Option(help="Authored diagnostic articles and expectations.")
    ],
    output: Annotated[Path, typer.Option(help="Directory for the report files.")],
) -> None:
    """Estimate sample statistics, excluding authored diagnostics from them."""
    labels = json.loads((benchmark / "schema.json").read_text())["labels"]
    progress = json.loads((benchmark / "progress.json").read_text())
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        for table in ("articles", "mentions"):
            con.read_parquet(str(benchmark / table / "*.parquet")).create_view(table)
        articles, invalid, windows, companies, below = con.execute(
            f"""SELECT count(*), count(*) FILTER (status <> 'ok'), sum(n_windows),
                count(*) FILTER (id IN (
                    SELECT id FROM mentions WHERE entity_type = 'company')),
                (SELECT avg((list_max(w.event_family) < 0.5)::INTEGER)
                 FROM (SELECT unnest(windows) AS w FROM articles
                       WHERE NOT {DIAGNOSTIC}))
            FROM articles WHERE NOT {DIAGNOSTIC}"""  # noqa: S608
        ).fetchone()
        low, high = proportion_confint(companies, articles, method="wilson")
        mentions = dict(
            con.execute(
                f"""SELECT entity_type, count(*) / {articles} FROM mentions
                WHERE NOT {DIAGNOSTIC} GROUP BY ALL ORDER BY ALL"""  # noqa: S608
            ).fetchall()
        )
        forms = dict(
            con.execute(
                f"""SELECT article_form, count(*) / {articles} FROM articles
                WHERE NOT {DIAGNOSTIC} GROUP BY ALL ORDER BY ALL"""  # noqa: S608
            ).fetchall()
        )
        metrics = {
            "articles": articles,
            "invalid_articles": invalid,
            "windows_per_article": windows / articles,
            "articles_per_second": progress["articles_per_second"],
            "hours_per_million_articles": 1e6 / progress["articles_per_second"] / 3600,
            "peak_cuda_reserved_gib": progress["peak_cuda_reserved_bytes"] / 2**30,
            # Hash-priority selection is a simple random sample of articles.
            "company_article_share": {
                "estimate": companies / articles,
                "wilson95_low": low,
                "wilson95_high": high,
            },
            "mentions_per_article": mentions,
            "article_form_shares": forms,
            "event_family_windows_below_threshold": below,
        } | {name: _attribute(con, name, labels[name]) for name in ATTRIBUTES}
        found = con.execute(
            f"""SELECT id, entity_type, text, financial_sentiment FROM mentions
            WHERE {DIAGNOSTIC} ORDER BY id, start"""  # noqa: S608
        ).fetchall()
    cases = {}
    for line in diagnostics.read_text().splitlines():
        case = json.loads(line)
        cases[case["id"]] = {"expectation": case["expectation"], "mentions": {}}
    # Show each company's winning sentiment beside its mention for review.
    sentiments = labels["financial_sentiment"]
    for identifier, entity_type, text, scores in found:
        label = f" ({sentiments[scores.index(max(scores))]})" if scores else ""
        cases[identifier]["mentions"].setdefault(entity_type, []).append(text + label)
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (output / "diagnostics.json").write_text(json.dumps(cases, indent=2) + "\n")
    typer.echo(f"Wrote: {benchmark} -> {output}")
