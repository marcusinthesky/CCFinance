"""Qualify historical Business Standard clocks on the frozen issuer roster."""

from pathlib import Path

import duckdb

from .events import (
    apply_event_rules,
    article_files,
    copy_parquet,
    remove_same_session_repeats,
)
from .sample import prepare_lopez_sample

PROCESSED = Path("data/processed")
EXPERIMENTS = PROCESSED / "experiments"
BASE = EXPERIMENTS / "lopez-lira-tang-events"
SAMPLE = EXPERIMENTS / "lopez-lira-tang-sample"
OUTPUT = EXPERIMENTS / "lopez-recovered-events"


def prepare_lopez_recovered() -> None:
    """Rebuild event rules jointly and retain dispositions for every parsed clock."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    raw = Path("data/raw/fine-news")
    links = PROCESSED / "company-links"
    with duckdb.connect(config={"threads": "2", "memory_limit": "2GB"}) as con:
        con.read_parquet(str(BASE / "timestamps.parquet")).create("original")
        con.read_parquet(str(BASE / "sessions.parquet")).create("sessions")
        con.read_parquet(str(SAMPLE / "sample.parquet")).project(
            "cik"
        ).distinct().create("roster")
        con.execute(
            r"""
            CREATE TABLE recovered AS
            WITH markers AS (
                SELECT n.id, regexp_extract(n.text,
                    '(?i)First Published:\s*([a-z]{3},\s+[a-z]+\s+' ||
                    '\d{1,2}\s+20\d{2}\.\s+\d{1,2}:\d{2})\s+IST\b') AS marker
                FROM read_parquet(?) n
                WHERE n.id IN (SELECT id FROM original
                    WHERE host='business-standard.com'
                                AND timing_status='no_first_publication')
            ), clocks AS (
                SELECT *, try_strptime(trim(regexp_replace(
                    regexp_replace(marker, '(?i)^First Published:', ''),
                    '(?i)IST$', '')),
                    '%a, %B %d %Y. %H:%M') AS local_clock FROM markers
            ), parsed AS (
                SELECT *, timezone('UTC', timezone('Asia/Kolkata', local_clock))
                    AS first_utc
                FROM clocks WHERE lower(strftime(local_clock,'%a'))
                    =lower(regexp_extract(marker,'(?i):\s*([a-z]{3}),',1))
            ), calendar AS (
                SELECT s.session, p.close_at, s.cutoff_at FROM sessions s
                JOIN sessions p ON p.session=s.previous_session
            )
            SELECT id,marker,first_utc,c.session,
                CASE WHEN c.session IS NULL THEN 'outside_overnight_interval'
                     WHEN o.captured<first_utc THEN 'capture_before_publication'
                     WHEN o.captured>c.cutoff_at THEN 'capture_after_cutoff'
                     ELSE 'eligible' END AS clock_status
            FROM parsed JOIN original o USING(id) LEFT JOIN calendar c
              ON first_utc>c.close_at AND first_utc<c.cutoff_at
        """,
            [article_files(raw, "2020-12", "2024-06", "**/*.parquet")],
        )
        con.execute("""
            CREATE TABLE article_pool AS SELECT id,host,indexed_date,captured,
                article_form,extraction_status,text_length,usable FROM original;
            CREATE TABLE timestamps AS SELECT o.id,title,body_sha256,
                coalesce(r.marker,o.publication_evidence) AS publication_evidence,
                publication_timezone, CASE WHEN r.id IS NULL THEN parser_version
                    ELSE 'business-standard-historical-v1' END AS parser_version,
                coalesce(r.first_utc,o.published_at) AS published_at, captured_at,
                coalesce(timezone('America/New_York',
                    timezone('UTC', r.first_utc))::DATE,
                    publication_date_ny) AS publication_date_ny,
                coalesce(r.session,o.session) AS session,
                coalesce(r.clock_status,o.timing_status) AS timing_status
            FROM original o LEFT JOIN recovered r USING(id);
        """)
        con.execute(
            """
            CREATE TABLE links AS SELECT l.* FROM read_parquet(?) l
            SEMI JOIN (SELECT id FROM timestamps WHERE timing_status='eligible') t
                USING(id)
        """,
            [str(links / "articles/*.parquet")],
        )
        apply_event_rules(
            con,
            article_files(raw, "2020-09", "2024-06", "**/*.parquet"),
            PROCESSED / "articles",
            links,
            PROCESSED / "issuers",
        )
        con.execute(
            "DELETE FROM event_screen WHERE cik NOT IN (SELECT cik FROM roster)"
        )
        remove_same_session_repeats(con)
        for source, target in (
            ("sessions", "sessions"),
            ("event_screen", "events"),
            ("ticker_history", "ticker_history"),
        ):
            copy_parquet(
                con, f"FROM {source} ORDER BY ALL", OUTPUT / f"{target}.parquet"
            )
        copy_parquet(
            con,
            "FROM article_pool JOIN timestamps USING(id) ORDER BY id",
            OUTPUT / "timestamps.parquet",
        )
        copy_parquet(con, "FROM recovered ORDER BY id", OUTPUT / "recovered.parquet")
    prepare_lopez_sample(
        OUTPUT,
        Path("data/raw/experiments/lopez-lira-tang"),
        PROCESSED / "embeddinggemma-embeddings",
        EXPERIMENTS / "lopez-recovered-sample",
    )
