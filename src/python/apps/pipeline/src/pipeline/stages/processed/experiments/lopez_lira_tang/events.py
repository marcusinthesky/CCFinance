"""Build the event eligibility and public-price panel for the body-vector study."""

import csv
from bisect import bisect_left
from collections import defaultdict
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Annotated

import duckdb
import typer
from duckdb import DuckDBPyConnection

from pipeline.stages.processed.publication_times import (
    INDIA,
    NEW_YORK,
    PARSER_VERSION,
    cutoff_time,
    first_publication,
    overnight_status,
)


def copy_parquet(con: DuckDBPyConnection, query: str, path: Path) -> None:
    """Write a query result as a Zstandard-compressed Parquet file."""
    con.sql(query).write_parquet(str(path), compression="zstd")


def article_files(directory: Path, start: str, end: str, pattern: str) -> list[str]:
    """Find article partitions in the inclusive study month range."""
    return [
        str(p / pattern)
        for p in sorted(directory.iterdir())
        if start <= p.name <= end and p.is_dir()
    ]


def _calendar(con: DuckDBPyConnection, path: Path) -> None:
    con.execute(
        "CREATE TABLE sessions (session DATE, previous_session DATE, "
        "cutoff_at TIMESTAMP, close_at TIMESTAMP)"
    )
    previous = None
    with path.open() as schedule:
        for row in csv.DictReader(schedule):
            session = date.fromisoformat(row["session"])
            close = datetime.combine(
                session, time.fromisoformat(row["close_time"]), NEW_YORK
            )
            cutoff = datetime.combine(session, cutoff_time(), NEW_YORK)
            con.execute(
                "INSERT INTO sessions VALUES (?,?,?,?)",
                [session, previous, _utc_clock(cutoff), _utc_clock(close)],
            )
            previous = session


def _utc_clock(timestamp: datetime) -> datetime:
    return timestamp.astimezone(UTC).replace(tzinfo=None)


def _timing(
    con: DuckDBPyConnection, raw: list[str], articles: Path, links: Path
) -> None:
    con.execute(
        """
        CREATE TABLE article_pool AS
        SELECT id, host, published AS indexed_date, captured, article_form,
            extraction_status, text_length, usable
        FROM read_parquet(?)
        WHERE host IN ('business-standard.com','lifestyle.livemint.com')
          AND captured BETWEEN '2020-12-31' AND '2024-05-31 13:00:00'
        """,
        [str(articles / "articles.parquet")],
    )
    con.execute(
        """
        CREATE TABLE links AS
        SELECT l.* FROM read_parquet(?) AS l SEMI JOIN article_pool USING (id)
        """,
        [str(links / "articles/*.parquet")],
    )
    con.execute(
        """
        CREATE TABLE timestamps (
            id VARCHAR, title VARCHAR, body_sha256 VARCHAR, publication_evidence
                VARCHAR,
            publication_timezone VARCHAR, parser_version VARCHAR, published_at
                TIMESTAMP,
            captured_at TIMESTAMP, publication_date_ny DATE, session DATE, timing_status
                VARCHAR
        )
        """
    )
    sessions = con.sql(
        """SELECT s.session, s.cutoff_at, p.close_at FROM sessions s
           JOIN sessions p ON p.session=s.previous_session ORDER BY s.cutoff_at"""
    ).fetchall()
    cutoffs = [row[1] for row in sessions]
    # Fetch the captured body unchanged for each linked, usable article.
    candidates = con.execute(
        """
        SELECT a.id, a.host, a.captured, n.metadata.title,
            n.metadata.source_text_sha256, n.text
        FROM read_parquet(?) n JOIN article_pool a USING (id) SEMI JOIN links USING (id)
        WHERE a.usable
        """,
        [raw],
    ).fetchall()
    timestamp_rows = []
    for article_id, host, captured, title, body_hash, body in candidates:
        evidence, published = first_publication(host, body or "")
        captured_at = captured.replace(tzinfo=UTC)
        session = None
        status = "no_first_publication"
        if published is not None:
            index = bisect_left(cutoffs, _utc_clock(published))
            if index == len(sessions):
                status = "outside_calendar"
            else:
                day, cutoff, previous_close = sessions[index]
                status = overnight_status(
                    _utc_clock(published), captured, previous_close, cutoff
                )
                if status == "eligible":
                    session = day
        timestamp_rows.append(
            (
                article_id,
                title,
                body_hash,
                evidence,
                INDIA.key,
                PARSER_VERSION,
                _utc_clock(published) if published else None,
                _utc_clock(captured_at),
                published.astimezone(NEW_YORK).date() if published else None,
                session,
                status,
            )
        )
    if timestamp_rows:
        con.executemany(
            "INSERT INTO timestamps VALUES (?,?,?,?,?,?,?,?,?,?,?)", timestamp_rows
        )


def apply_event_rules(
    con: DuckDBPyConnection, raw: list[str], articles: Path, links: Path, issuers: Path
) -> None:
    """Build the overnight event screen and ticker history."""
    con.execute(
        """
        CREATE MACRO norm(s) AS trim(regexp_replace(lower(coalesce(s, '')),
            '[^a-z0-9]+', ' ', 'g'));
        CREATE MACRO title_key(s) AS regexp_replace(norm(s),
            ' (business standard|mint)$', '');
        CREATE MACRO venue(s) AS CASE WHEN s='New York Stock Exchange' THEN 'NYSE' ELSE
            s END;
        """
    )
    con.execute(
        """
        CREATE TABLE ticker_history AS SELECT DISTINCT cik, ticker, venue(exchange) AS
            exchange,
            valid_from, valid_to, source
        FROM read_parquet(?)
        """,
        [str(issuers / "tickers.parquet")],
    )
    con.execute(
        """
        CREATE TABLE preperiod AS
        SELECT l.cik, count(DISTINCT a.id) AS preperiod_usable
        FROM read_parquet(?) a JOIN read_parquet(?) l USING (id)
        WHERE a.usable AND a.captured < TIMESTAMP '2021-01-01'
          AND a.published BETWEEN DATE '2017-01-01' AND DATE '2020-12-31'
          AND l.link_score >= 0.5
        GROUP BY l.cik
        """,
        [str(articles / "articles.parquet"), str(links / "articles/*.parquet")],
    )
    con.execute(
        """
        CREATE TABLE event_links AS
        SELECT a.*, t.* EXCLUDE(id), l.cik, l.ticker, i.name, i.entity_type,
               l.link_score, l.n_mentions, l.first_offset_share,
                   l.relevance_substantive,
               l.self_publisher, coalesce(p.preperiod_usable,0) AS preperiod_usable,
               count(*) OVER (PARTITION BY a.id) AS linked_issuers,
               l.n_mentions >= 3 AND l.first_offset_share <= 1 AND
                   l.relevance_substantive >= 0
                 AND l.link_score >= 0.5 AS focused,
               regexp_matches(norm(t.title),
                   '\\b(stocks?|shares?) (gains?|rises?|falls?|drops?|surges?|'
                       || 'slides?|slumps?)\\b')
                 AND NOT regexp_matches(norm(t.title),
                     '\\b(after|as|on|amid|following|ahead|because)\\b') AS
                     movement_only_proxy,
               title_key(t.title) AS headline_key
        FROM article_pool a JOIN timestamps t USING (id) JOIN links l USING (id)
        LEFT JOIN read_parquet(?) i USING (cik)
        LEFT JOIN preperiod p ON l.cik=p.cik
        WHERE t.timing_status = 'eligible'
        """,
        [str(issuers / "issuers.parquet")],
    )
    con.execute(
        """
        CREATE TABLE matches AS
        SELECT e.id, e.cik,
               count(DISTINCT (t.cik,t.ticker)) FILTER (WHERE t.cik IS NOT NULL) AS
                   security_classes,
               count(*) FILTER (WHERE t.ticker=e.ticker AND t.valid_from IS NOT NULL) AS
                   dated_match,
               count(*) FILTER (WHERE t.ticker=e.ticker AND t.valid_from IS NULL) AS
                   unknown_start_match,
               min(t.exchange) FILTER (WHERE t.ticker=e.ticker) AS exchange
        FROM event_links e LEFT JOIN ticker_history t ON t.cik=e.cik
          AND t.exchange IN ('NYSE','NYSE American','Nasdaq')
          AND (t.valid_from IS NULL OR e.session >= t.valid_from)
          AND (t.valid_to IS NULL OR e.session <= t.valid_to)
        GROUP BY e.id,e.cik
        """
    )
    con.execute(
        """
        CREATE TABLE matches_asof AS
        SELECT o.id, l.cik, a.published, a.captured, title_key(o.metadata.title) AS
            headline_key
        FROM read_parquet(?) o
        SEMI JOIN (SELECT DISTINCT headline_key FROM event_links WHERE headline_key <>
            '') k
            ON k.headline_key=title_key(o.metadata.title)
        JOIN read_parquet(?) a USING (id)
        JOIN read_parquet(?) l USING (id)
        WHERE a.usable AND a.published IS NOT NULL
        """,
        [raw, str(articles / "articles.parquet"), str(links / "articles/*.parquet")],
    )
    con.execute(
        """
        CREATE TABLE event_screen AS
        WITH flags AS (
            SELECT e.*, m.* EXCLUDE (id,cik),
                   EXISTS (
                       SELECT 1 FROM matches_asof v
                       WHERE v.cik=e.cik AND v.headline_key=e.headline_key
                         AND v.captured <= e.captured
                         AND v.published BETWEEN e.publication_date_ny-90
                           AND e.publication_date_ny-1 AND v.id<>e.id
                   ) AS prior_exact_title,
                   EXISTS (
                       SELECT 1 FROM read_parquet(?) a
                       WHERE a.cik=e.cik AND length(norm(a.key))>=3
                         AND a.source IN
                             ('sec_name','former_name','wikidata_label',
                              'wikidata_alias')
                         AND contains(' ' || norm(e.title) || ' ', ' ' || norm(a.key) ||
                             ' ')
                         AND (a.valid_from IS NULL OR e.session>=a.valid_from)
                         AND (a.valid_to IS NULL OR e.session<=a.valid_to)
                   ) AS title_named
            FROM event_links e JOIN matches m USING (id,cik)
        )
        SELECT *, CASE
          WHEN NOT coalesce(focused,false) THEN 'focus_proxy'
          WHEN extraction_status IS DISTINCT FROM 'ok' OR coalesce(text_length,0)<=0
              THEN 'incomplete_body_proxy'
          WHEN entity_type IS DISTINCT FROM 'operating' THEN 'issuer_type'
          WHEN security_classes>1 THEN 'ambiguous_classes'
          WHEN dated_match=0 AND unknown_start_match=0 THEN 'no_active_listing'
          WHEN dated_match=0 AND preperiod_usable=0 THEN 'unknown_listing_start'
          WHEN movement_only_proxy THEN 'price_movement_proxy'
          WHEN headline_key='' THEN 'missing_title'
          WHEN prior_exact_title THEN 'prior_exact_title'
          ELSE 'eligible'
        END AS event_status
        FROM flags
        """,
        [str(issuers / "aliases.parquet")],
    )


def headline_similarity(first: str, second: str) -> float:
    """Return one minus normalized Optimal String Alignment distance."""
    if not first or not second:
        return 0.0
    previous = list(range(len(second) + 1))
    two_back = previous
    for i, char in enumerate(first, 1):
        current = [i]
        for j, other in enumerate(second, 1):
            distance = min(
                previous[j] + 1, current[-1] + 1, previous[j - 1] + (char != other)
            )
            if i > 1 and j > 1 and char == second[j - 2] and other == first[i - 2]:
                distance = min(distance, two_back[j - 2] + 1)
            current.append(distance)
        two_back, previous = previous, current
    return 1 - previous[-1] / max(len(first), len(second))


def remove_same_session_repeats(con: DuckDBPyConnection) -> None:
    """Flag later same-session stories with matching headlines."""
    prior: dict[tuple[int, date], list[str]] = defaultdict(list)
    repeats = []
    for article, cik, session, key in con.sql(
        """SELECT id,cik,session,headline_key
           FROM event_screen WHERE event_status='eligible'
           ORDER BY session, cik, published_at, captured_at, id"""
    ).fetchall():
        titles = prior[cik, session]
        if any(headline_similarity(key, title) > 0.6 for title in titles):
            repeats.append((article, cik))
        else:
            titles.append(key)
    if repeats:
        con.executemany(
            "UPDATE event_screen SET event_status='similar_same_session' "
            "WHERE id=? AND cik=?",
            repeats,
        )


def prepare_lopez_events(
    raw: Annotated[Path, typer.Option()],
    articles: Annotated[Path, typer.Option()],
    links: Annotated[Path, typer.Option()],
    issuers: Annotated[Path, typer.Option()],
    calendar: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Write exchange sessions, timing evidence, listings and screened events."""
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={"threads": "2", "memory_limit": "2GB"}) as con:
        _calendar(con, calendar)
        raw_files = article_files(raw, "2020-12", "2024-06", "**/*.parquet")
        _timing(con, raw_files, articles, links)
        apply_event_rules(
            con,
            article_files(raw, "2020-09", "2024-06", "**/*.parquet"),
            articles,
            links,
            issuers,
        )
        remove_same_session_repeats(con)
        copy_parquet(con, "FROM sessions ORDER BY session", output / "sessions.parquet")
        copy_parquet(
            con,
            "FROM event_screen ORDER BY session,cik,published_at,captured_at,id",
            output / "events.parquet",
        )
        copy_parquet(
            con, "FROM ticker_history ORDER BY ALL", output / "ticker_history.parquet"
        )
        copy_parquet(
            con,
            """SELECT p.*, t.* EXCLUDE(id)
               FROM article_pool p LEFT JOIN timestamps t USING(id)
                     ORDER BY p.id""",
            output / "timestamps.parquet",
        )
        con.sql(
            """SELECT DISTINCT replace(ticker,'.','-') AS symbol, session,
                    previous_session, cik, exchange
               FROM event_screen JOIN sessions USING(session)
               WHERE event_status='eligible' ORDER BY ALL"""
        ).write_csv(str(output / "price_requests.csv"), header=True)
