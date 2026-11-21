"""Measure captured news and daily market closes for monthly EMV tracking."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import typer

INPUTS = Path("data/inputs/baker-emv")
ROOT = Path("data/processed/experiments/baker-emv")


def measure_baker_emv(
    source: Path = Path("data/raw/fine-news"),
    articles: Path = Path("data/processed/articles/articles.parquet"),
    hosts: Path = INPUTS / "hosts.csv",
    dictionary: Path = INPUTS / "dictionary.json",
    window: Path = INPUTS / "window.json",
    output: Path = ROOT / "news",
) -> None:
    """Write one hit row per eligible article and the complete publisher ledger."""
    terms = json.loads(dictionary.read_text())
    bounds = json.loads(window.read_text())
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as work, duckdb.connect() as con:
        con.execute("SET threads = 4")
        con.execute("SET memory_limit = '4GB'")
        con.execute("SET temp_directory = ?", [str(Path(work) / "spill")])
        con.execute(
            "CREATE TEMP TABLE publishers AS SELECT * FROM read_csv(?, header = true)",
            [str(hosts)],
        )
        con.execute(
            """
            CREATE TEMP TABLE eligible AS
            SELECT a.id, a.host, p.publisher, a.published,
                   a.captured::DATE AS capture_day,
                   date_trunc('month', a.published)::DATE AS month
            FROM read_parquet(?) AS a JOIN publishers AS p USING (host)
            WHERE a.usable AND a.published >= ?::DATE
              AND a.published < ?::DATE + INTERVAL 1 MONTH
            """,
            [str(articles), bounds["start"], bounds["end"]],
        )
        con.execute(
            """
            CREATE TEMP TABLE article_hits AS
            WITH text_fields AS (
                SELECT a.*, lower(coalesce(r.metadata.title, '')) AS title,
                       lower(coalesce(r.text, '')) AS body
                FROM read_parquet($raw) AS r JOIN eligible AS a USING (id)
            ), matches AS (
                SELECT * EXCLUDE (title, body),
                       regexp_matches(title, $economy) OR regexp_matches(body, $economy)
                           AS economy_hit,
                       regexp_matches(title, $equity) OR regexp_matches(body, $equity)
                           AS equity_hit,
                       regexp_matches(title, $volatility)
                           OR regexp_matches(body, $volatility) AS volatility_hit
                FROM text_fields
            )
            SELECT *, economy_hit AND equity_hit AND volatility_hit AS emv_hit
            FROM matches ORDER BY id
            """,
            {"raw": str(source / "**" / "*.parquet"), **terms},
        )
        [(eligible, unique_eligible)] = con.execute(
            "SELECT count(*), count(DISTINCT id) FROM eligible"
        ).fetchall()
        [(matched, unique_matched)] = con.execute(
            "SELECT count(*), count(DISTINCT id) FROM article_hits"
        ).fetchall()
        if (
            eligible != unique_eligible
            or eligible != matched
            or matched != unique_matched
        ):
            raise ValueError(
                "Eligible prepared articles must match unique raw article IDs"
            )
        con.execute(
            """
            CREATE TEMP TABLE publisher_month AS
            WITH months AS (
                SELECT month::DATE AS month
                FROM generate_series(?::DATE, ?::DATE, INTERVAL 1 MONTH) AS t(month)
            ), counts AS (
                SELECT host, month, count(*) AS eligible_articles,
                       count(DISTINCT published) AS publication_days,
                       count(*) FILTER (WHERE emv_hit) AS emv_hits
                FROM article_hits GROUP BY host, month
            )
            SELECT p.host, p.publisher, m.month,
                   coalesce(c.eligible_articles, 0) AS eligible_articles,
                   coalesce(c.publication_days, 0) AS publication_days,
                   coalesce(c.emv_hits, 0) AS emv_hits,
                   c.emv_hits / c.eligible_articles AS hit_share
            FROM publishers p CROSS JOIN months m LEFT JOIN counts c USING (host, month)
            ORDER BY month, host
            """,
            [bounds["start"], bounds["end"]],
        )
        con.execute(
            "COPY article_hits TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(Path(work) / "article_hits.parquet")],
        )
        con.execute(
            "COPY publisher_month TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(Path(work) / "publisher_month.parquet")],
        )
        for filename in ("article_hits.parquet", "publisher_month.parquet"):
            os.replace(Path(work) / filename, output / filename)
    typer.echo(f"Wrote: {output}")


def prepare_baker_emv_market(
    source: Path = Path("data/raw/experiments/baker-emv/market.csv"),
    window: Path = INPUTS / "window.json",
    output: Path = ROOT / "market",
) -> None:
    """Write daily closes and annualized monthly realized volatility."""
    bounds = json.loads(window.read_text())
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as work, duckdb.connect() as con:
        con.execute(
            """
            CREATE TEMP TABLE closes AS
            SELECT observation_date::DATE AS day,
                   nullif(nullif(VIXCLS, ''), '.')::DOUBLE AS vix_close,
                   nullif(nullif(SP500, ''), '.')::DOUBLE AS sp500_close
            FROM read_csv(?, all_varchar = true, header = true)
            WHERE observation_date::DATE < ?::DATE + INTERVAL 1 MONTH
            """,
            [str(source), bounds["end"]],
        )
        [(invalid, days, unique_days, prior)] = con.execute(
            """
            SELECT count(*) FILTER (
                       WHERE day IS NULL OR vix_close <= 0 OR sp500_close <= 0
                          OR NOT isfinite(vix_close) OR NOT isfinite(sp500_close)
                   ), count(*), count(DISTINCT day),
                   max(day) FILTER (WHERE day < ?::DATE AND sp500_close IS NOT NULL)
            FROM closes
            """,
            [bounds["start"]],
        ).fetchall()
        if invalid or days != unique_days or prior is None:
            raise ValueError(
                "Market data needs unique dates, positive closes, and a prior close"
            )
        con.execute(
            """
            CREATE TEMP TABLE daily_market AS
            WITH returns AS (
                SELECT day,
                       ln(sp500_close / lag(sp500_close) OVER (ORDER BY day))
                           AS log_return
                FROM closes WHERE sp500_close IS NOT NULL AND day >= ?
            )
            SELECT *, day >= ?::DATE AS study_day
            FROM closes LEFT JOIN returns USING (day)
            WHERE day >= ? AND (vix_close IS NOT NULL OR sp500_close IS NOT NULL)
            ORDER BY day
            """,
            [prior, bounds["start"], prior],
        )
        con.execute(
            """
            CREATE TEMP TABLE monthly_market AS
            SELECT date_trunc('month', day)::DATE AS month,
                   count(vix_close) FILTER (WHERE sp500_close IS NOT NULL) AS vix_days,
                   count(vix_close) FILTER (WHERE sp500_close IS NULL) AS vix_only_days,
                   count(log_return) AS return_days,
                   avg(vix_close) FILTER (WHERE sp500_close IS NOT NULL) AS vix,
                   100 * sqrt(252 * avg(log_return ^ 2)) AS realized_volatility
            FROM daily_market
            WHERE study_day
            GROUP BY month ORDER BY month
            """
        )
        con.execute(
            "COPY daily_market TO ? (FORMAT PARQUET)",
            [str(Path(work) / "daily_market.parquet")],
        )
        con.execute(
            "COPY monthly_market TO ? (FORMAT PARQUET)",
            [str(Path(work) / "monthly_market.parquet")],
        )
        for filename in ("daily_market.parquet", "monthly_market.parquet"):
            os.replace(Path(work) / filename, output / filename)
    typer.echo(f"Wrote: {output}")
