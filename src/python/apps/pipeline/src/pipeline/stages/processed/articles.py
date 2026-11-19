"""Date-check and deduplicate articles, keeping every source record.

Fine News already keeps one representative per MinHash cluster, recording the
cluster size as ``sampling_weight``; it is kept as ``copies``, the article's
syndication reach. Exact text repeats and normalized-URL repeats remain across
monthly captures. The earliest capture in each group is canonical, and the
others name it in ``duplicate_of``.

A publication date dates the text only if the text was captured soon after it.
Captures more than ``max_lag_days`` after the publication date are "archival":
the date may be true, but the text was not observably published then. A date
more than one day after capture is "future"; one day is allowed for publisher
time zones, because publication dates are local and capture times are UTC.
Usable articles are canonical and consistently dated.
"""

import json
import os
from pathlib import Path
from typing import Annotated

import duckdb
import typer

# Publication dates are local; captures are UTC, so allow one day of skew.
FUTURE_TOLERANCE_DAYS = 1
DATE_STATUSES = ("consistent", "archival", "future", "missing")


def prepare_articles(
    source: Annotated[Path, typer.Option(help="Raw Fine News shards.")] = Path(
        "data/raw/fine-news"
    ),
    extraction: Annotated[
        Path, typer.Option(help="GLiNER output with articles/.")
    ] = Path("data/processed/article-metadata"),
    max_lag_days: Annotated[
        int, typer.Option(help="Days a capture may follow its publication date.")
    ] = 7,
    output: Annotated[Path, typer.Option(help="Output directory.")] = Path(
        "data/processed/articles"
    ),
) -> None:
    """Write one row per article with date status, duplicates, form and copies."""
    output.mkdir(parents=True, exist_ok=True)
    target = output / "articles.parquet"
    temporary = target.with_suffix(".tmp")
    with duckdb.connect() as con:
        con.execute("SET TimeZone = 'UTC'")
        con.execute(
            """CREATE TABLE raw AS
            SELECT id,
                   regexp_replace(lower(metadata.url_hostname), '^www[.]', '') AS host,
                   try_cast(left(metadata.publish_date, 10) AS DATE) AS published,
                   (metadata.warc_date AT TIME ZONE 'UTC') AS captured,
                   metadata.text_length AS text_length,
                   coalesce(metadata.sampling_weight, 1) AS copies,
                   metadata.text_xxhash64 AS text_hash,
                   metadata.normalized_url AS url
            FROM read_parquet($pattern)""",
            {"pattern": str(source / "**" / "*.parquet")},
        )
        con.execute(
            f"""CREATE TABLE articles AS
            WITH dated AS (
                SELECT *, date_diff('day', published, captured::DATE) AS lag_days
                FROM raw
            ), grouped AS (
                SELECT *,
                    CASE WHEN text_hash IS NULL THEN id ELSE first_value(id) OVER (
                        PARTITION BY text_hash ORDER BY captured, id) END AS text_first,
                    CASE WHEN url IS NULL THEN id ELSE first_value(id) OVER (
                        PARTITION BY url ORDER BY captured, id) END AS url_first
                FROM dated
            ), checked AS (
                SELECT g.id, g.host, g.published, g.captured, g.lag_days,
                    CASE WHEN g.published IS NULL THEN 'missing'
                         WHEN g.lag_days < -{FUTURE_TOLERANCE_DAYS} THEN 'future'
                         WHEN g.lag_days > $max_lag THEN 'archival'
                         ELSE 'consistent' END AS date_status,
                    g.text_length, g.copies,
                    CASE WHEN g.text_first <> g.id THEN g.text_first
                         WHEN g.url_first <> g.id THEN g.url_first END AS duplicate_of,
                    CASE WHEN g.text_first <> g.id THEN 'text'
                         WHEN g.url_first <> g.id THEN 'url' END AS duplicate_kind,
                    m.article_form, m.status AS extraction_status
                FROM grouped AS g
                LEFT JOIN read_parquet($metadata) AS m USING (id)
            )
            SELECT *, duplicate_of IS NULL AS canonical,
                   duplicate_of IS NULL AND date_status = 'consistent' AS usable
            FROM checked ORDER BY id""",  # noqa: S608 - authored constants.
            {
                "max_lag": max_lag_days,
                "metadata": str(extraction / "articles" / "*.parquet"),
            },
        )
        con.execute(
            f"COPY articles TO '{temporary}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        os.replace(temporary, target)
        counts = con.execute(
            "SELECT count(*), count(*) FILTER (WHERE canonical), "
            "count(*) FILTER (WHERE duplicate_kind = 'text'), "
            "count(*) FILTER (WHERE duplicate_kind = 'url'), "
            "count(*) FILTER (WHERE usable), "
            "count(*) FILTER (WHERE article_form IS NULL) FROM articles"
        ).fetchall()[0]
        statuses = dict(
            con.execute(
                "SELECT date_status, count(*) FROM articles GROUP BY 1"
            ).fetchall()
        )
    summary = {
        "max_lag_days": max_lag_days,
        "future_tolerance_days": FUTURE_TOLERANCE_DAYS,
        "articles": counts[0],
        "canonical": counts[1],
        "text_duplicates": counts[2],
        "url_duplicates": counts[3],
        "usable": counts[4],
        "without_extraction": counts[5],
        "date_status": {status: statuses.get(status, 0) for status in DATE_STATUSES},
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    typer.echo(f"Wrote: {output}")
