"""Join overnight events to public prices and fixed body vectors."""

import csv
import json
import tempfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import duckdb
import typer
from duckdb import DuckDBPyConnection

from pipeline.stages.processed.publication_times import NEW_YORK

from .events import article_files, copy_parquet


def _market_day(timestamp: int) -> date:
    return datetime.fromtimestamp(timestamp, NEW_YORK).date()


def _quotes(con: DuckDBPyConnection, prices: Path) -> None:
    con.execute(
        """CREATE TABLE quotes (
            symbol VARCHAR, day DATE, open_price DOUBLE, close_price DOUBLE,
            cash_dividend DOUBLE, split_ratio VARCHAR, provider_exchange VARCHAR,
            PRIMARY KEY (symbol, day)
        );
        CREATE TABLE price_responses(
            symbol VARCHAR PRIMARY KEY, response_status VARCHAR, first_trade DATE
        );
        """
    )
    bars = []
    statuses = []
    with (prices / "requests.csv").open() as ledger:
        for item in csv.DictReader(ledger):
            symbol = item["symbol"]
            path = prices / "prices" / f"{symbol}.json"
            try:
                chart = json.loads(path.read_bytes())["chart"] if path.exists() else {}
            except (ValueError, KeyError, TypeError):
                chart = {}
            results = chart.get("result") or []
            if not results:
                error = chart.get("error") or {}
                statuses.append(
                    (symbol, error.get("description") or item["status"], None)
                )
                continue
            result = results[0]
            meta = result["meta"]
            first_trade = (
                _market_day(meta["firstTradeDate"])
                if meta.get("firstTradeDate")
                else None
            )
            if (
                meta.get("instrumentType") != "EQUITY"
                or meta.get("currency") != "USD"
                or symbol.upper() != meta.get("symbol", "").upper()
            ):
                statuses.append((symbol, "provider_identity_or_type", first_trade))
                continue
            quote = (result.get("indicators", {}).get("quote") or [{}])[0]
            if (
                not result.get("timestamp")
                or "open" not in quote
                or "close" not in quote
            ):
                statuses.append((symbol, "provider_no_bars", first_trade))
                continue
            statuses.append((symbol, "available", first_trade))
            events = result.get("events", {})
            dividends: dict[date, float] = defaultdict(float)
            for event in events.get("dividends", {}).values():
                dividends[_market_day(event["date"])] += event["amount"]
            splits = {
                _market_day(event["date"]): event["splitRatio"]
                for event in events.get("splits", {}).values()
            }
            for timestamp, opening, closing in zip(
                result.get("timestamp", []), quote["open"], quote["close"], strict=True
            ):
                day = _market_day(timestamp)
                bars.append(
                    (
                        symbol,
                        day,
                        opening,
                        closing,
                        dividends[day],
                        splits.get(day),
                        meta.get("fullExchangeName"),
                    )
                )
    # Avoid row-wise INSERT round trips for chart history.
    _insert_rows(con, "quotes", bars)
    _insert_rows(con, "price_responses", statuses)


def _insert_rows(
    con: DuckDBPyConnection,
    table: str,
    rows: list[
        tuple[str, date, float | None, float | None, float, str | None, str | None]
    ]
    | list[tuple[str, str, date | None]],
) -> None:
    if not rows:
        return
    with tempfile.NamedTemporaryFile(mode="w", newline="", suffix=".csv") as fp:
        csv.writer(fp).writerows(rows)
        fp.flush()
        con.execute(f"COPY {table} FROM ? (FORMAT CSV, HEADER false)", [fp.name])


def _attach_vectors(con: DuckDBPyConnection, vectors: Path) -> None:
    con.execute(
        "CREATE TABLE body_vectors(id VARCHAR, has_text BOOLEAN, embedding FLOAT[])"
    )
    # Stream one partition at a time so the corpus-sized vector scan stays bounded.
    for pattern in article_files(vectors, "2020-12", "2024-06", "**/group-*.parquet"):
        con.execute(
            """INSERT INTO body_vectors
               SELECT v.id,v.has_text,v.embedding FROM read_parquet(?) v
               SEMI JOIN (SELECT id FROM events WHERE event_status='eligible') e
               USING (id)""",
            [pattern],
        )
    if con.sql(
        "SELECT id FROM body_vectors GROUP BY id HAVING count(*)>1 LIMIT 1"
    ).fetchone():
        msg = "Duplicate body embedding article IDs in the eligible sample"
        raise ValueError(msg)


def _price_panel(con: DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE MACRO reaction_return(pc,o,c,d) AS
            CASE WHEN d=0 THEN (o-pc)/pc ELSE (o*(c+d)-pc*c)/(pc*c) END;
        CREATE MACRO drift_return(o,c) AS (c-o)/o;
        CREATE TABLE joined AS
        WITH ready AS (
            SELECT e.*, s.previous_session, s.cutoff_at, s.close_at AS
                label_observed_at,
                   replace(e.ticker,'.','-') AS symbol, p.close_price AS previous_close,
                   q.open_price, q.close_price, q.cash_dividend, q.split_ratio,
                       q.provider_exchange,
                   r.response_status, r.first_trade,
                   v.embedding,
                   CASE
                     WHEN e.event_status<>'eligible' THEN e.event_status
                     WHEN v.id IS NULL THEN 'missing_vector'
                     WHEN v.has_text IS DISTINCT FROM true OR
                         array_length(v.embedding) IS DISTINCT FROM 768 OR
                         list_count(v.embedding) IS DISTINCT FROM 768
                       THEN 'invalid_vector'
                     WHEN list_sum(list_transform(v.embedding, x -> x * x))
                          NOT BETWEEN 0.98 AND 1.02
                       THEN 'invalid_vector'
                     WHEN r.response_status IS NULL THEN 'missing_price_request'
                     WHEN r.response_status<>'available' THEN
                         'unavailable_price_history'
                     WHEN r.first_trade>e.session THEN 'before_provider_first_trade'
                     WHEN NOT EXISTS (
                         SELECT 1 FROM ticker_history t WHERE t.cik=e.cik AND
                             t.ticker=e.ticker
                         AND t.exchange=e.exchange AND (t.valid_from IS NULL OR
                             t.valid_from<=s.previous_session)
                         AND (t.valid_to IS NULL OR t.valid_to>=e.session)
                       ) THEN 'listing_boundary'
                     WHEN coalesce(p.close_price,0)<=0 OR NOT isfinite(p.close_price)
                       THEN 'missing_previous_close'
                     WHEN coalesce(q.open_price,0)<=0 OR coalesce(q.close_price,0)<=0
                         OR NOT isfinite(q.open_price) OR NOT isfinite(q.close_price)
                         OR NOT isfinite(q.cash_dividend) THEN 'missing_session_bar'
                     ELSE 'included'
                   END AS sample_status
            FROM events e JOIN sessions s USING(session)
            LEFT JOIN quotes q ON q.symbol=replace(e.ticker,'.','-') AND q.day=e.session
            LEFT JOIN quotes p ON p.symbol=replace(e.ticker,'.','-') AND
                p.day=s.previous_session
            LEFT JOIN price_responses r ON r.symbol=replace(e.ticker,'.','-')
            LEFT JOIN body_vectors v USING(id)
        )
        SELECT *, CASE WHEN sample_status='included' THEN
            reaction_return(previous_close,open_price,close_price,cash_dividend) END AS
                reaction,
            CASE WHEN sample_status='included' THEN drift_return(open_price,close_price)
                END AS drift
        FROM ready
        """
    )


def prepare_lopez_sample(
    events: Annotated[Path, typer.Option()],
    prices: Annotated[Path, typer.Option()],
    vectors: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Join fixed vectors and public bars, retaining attrition and session support."""
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={"threads": "2", "memory_limit": "1GB"}) as con:
        for table in ("events", "sessions", "ticker_history", "timestamps"):
            con.read_parquet(str(events / f"{table}.parquet")).create(table)
        _quotes(con, prices)
        _attach_vectors(con, vectors)
        _price_panel(con)
        copy_parquet(
            con,
            """SELECT * EXCLUDE(embedding) FROM joined
               ORDER BY session,cik,published_at,captured_at,id""",
            output / "eligibility.parquet",
        )
        copy_parquet(
            con,
            """SELECT * FROM joined WHERE sample_status='included'
                   ORDER BY session,cik,published_at,captured_at,id""",
            output / "sample.parquet",
        )
        copy_parquet(
            con, "SELECT * FROM sessions ORDER BY session", output / "sessions.parquet"
        )
        con.sql(
            """SELECT s.session, count(j.id) AS article_security_rows,
                   count(DISTINCT j.id) AS articles,
                   count(DISTINCT j.cik) AS firms, count(DISTINCT (j.cik,j.ticker))
                       FILTER (WHERE j.id IS NOT NULL) AS securities,
                   count(DISTINCT j.id) FILTER (WHERE j.linked_issuers>1) AS
                       multi_issuer_articles
               FROM sessions s LEFT JOIN joined j ON j.session=s.session AND
                   j.sample_status='included'
               GROUP BY s.session ORDER BY s.session"""
        ).write_csv(str(output / "daily_support.csv"), header=True)
        con.sql(
            """SELECT 'timing' AS phase, host,
                   coalesce(timing_status,
                       case when usable then 'no_issuer_link_or_payload'
                         else 'unusable_article' end) AS disposition, count(*) AS rows,
                             count(DISTINCT id) AS articles
               FROM timestamps GROUP BY ALL
               UNION ALL
               SELECT 'sample', host, sample_status, count(*), count(DISTINCT id) FROM
                   joined GROUP BY ALL
               ORDER BY ALL"""
        ).write_csv(str(output / "attrition.csv"), header=True)
        con.sql(
            """SELECT j.symbol,j.cik,j.exchange,j.session,j.previous_session,
                    j.sample_status,j.response_status,j.first_trade,j.provider_exchange,
                    j.cash_dividend,j.split_ratio
               FROM joined j WHERE event_status='eligible' GROUP BY ALL ORDER BY ALL"""
        ).write_csv(str(output / "price_ledger.csv"), header=True)
