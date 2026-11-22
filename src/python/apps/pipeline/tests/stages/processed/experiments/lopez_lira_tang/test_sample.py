"""Exercise return construction and missing identity or price evidence."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.stages.processed.experiments.lopez_lira_tang.sample import (
    prepare_lopez_sample,
)


@pytest.mark.integration
def test_sample_handles_adjustment_boundaries_and_missing_prices(
    tmp_path: Path,
) -> None:
    """Keep comparable bars and distinguish missing price and identity evidence."""
    # Arrange
    events = tmp_path / "events"
    prices = tmp_path / "price_snapshot"
    vectors = tmp_path / "vectors"
    output = tmp_path / "sample"
    events.mkdir()
    prices.mkdir()
    (prices / "prices").mkdir()
    (vectors / "2021-07").mkdir(parents=True)
    symbols = ("DIV", "SPLIT", "RISE", "FALL", "MISSING", "CHANGED", "DELISTED")
    fixtures = {
        "DIV": (100, 99, 99),
        "SPLIT": (40, 40, 40),
        "RISE": (100, 105, 102),
        "FALL": (100, 95, 99),
        "MISSING": (100, None, None),
        "CHANGED": (100, 100, 101),
    }
    previous_open, current_open = 1626701400, 1626787800
    (prices / "requests.csv").write_text(
        "symbol,status\n" + "".join(f"{symbol},recorded\n" for symbol in symbols)
    )
    for symbol, (previous, opening, closing) in fixtures.items():
        events_today = (
            {"dividends": {"ex": {"date": current_open, "amount": 1}}}
            if symbol == "DIV"
            else {"splits": {"effective": {"date": current_open, "splitRatio": "4:1"}}}
            if symbol == "SPLIT"
            else {}
        )
        result = {
            "meta": {"instrumentType": "EQUITY", "symbol": symbol, "currency": "USD"},
            "timestamp": [previous_open, current_open],
            "indicators": {
                "quote": [{"open": [previous, opening], "close": [previous, closing]}]
            },
            "events": events_today,
        }
        (prices / "prices" / f"{symbol}.json").write_text(
            json.dumps({"chart": {"result": [result]}})
        )
    (prices / "prices" / "DELISTED.json").write_text(
        '{"chart":{"result":null,'
        '"error":{"description":"No data found, symbol may be delisted"}}}'
    )
    with duckdb.connect() as db:
        db.execute(
            """
            CREATE TABLE events AS
            SELECT ticker AS id,ticker,cik,DATE '2021-07-20' AS session,'Nasdaq' AS
                exchange,
                   TIMESTAMP '2021-07-20 09:00' AS published_at,
                   TIMESTAMP '2021-07-20 09:01' AS captured_at,'eligible' AS
                       event_status,
                   1 AS linked_issuers,'test.host' AS host
            FROM (VALUES
                ('DIV',1),('SPLIT',2),('RISE',3),('MISSING',4),('CHANGED',5),('DELISTED',6),
                ('FALL',7),('NULLVEC',8),('NULLCOORD',9))
                t(ticker,cik);
            CREATE TABLE sessions AS SELECT DATE '2021-07-20' AS session,DATE
                '2021-07-19' AS previous_session,
                TIMESTAMP '2021-07-20 13:00' AS cutoff_at,TIMESTAMP '2021-07-20 20:00'
                    AS close_at;
            CREATE TABLE ticker_history AS
              SELECT cik,ticker,exchange,
                  CASE WHEN ticker='CHANGED' THEN session ELSE DATE '2000-01-01' END AS
                      valid_from,
                  NULL::DATE AS valid_to FROM events
              UNION ALL SELECT 5,'OLD','Nasdaq', DATE '2000-01-01', DATE '2021-07-19';
            CREATE TABLE timestamps AS SELECT id,host,'eligible' AS timing_status,true
                AS usable FROM events;
            CREATE TABLE vectors AS SELECT id,true AS has_text,
                 CASE WHEN id='NULLVEC' THEN NULL
                      WHEN id='NULLCOORD' THEN [NULL::FLOAT]
                         || list_resize([]::FLOAT[],767,0.0)
                      ELSE [1.0] || list_resize([]::FLOAT[],767,0.0) END AS embedding
                 FROM events;
            """
        )
        for table in ("events", "sessions", "ticker_history", "timestamps"):
            db.table(table).write_parquet(str(events / f"{table}.parquet"))
        db.table("vectors").write_parquet(
            str(vectors / "2021-07" / "group-0001.parquet")
        )

    # Act
    prepare_lopez_sample(events, prices, vectors, output)

    # Assert
    with duckdb.connect() as db:
        eligible = db.read_parquet(str(output / "eligibility.parquet"))
        observations = {
            ticker: (status, reaction, drift, split)
            for ticker, status, reaction, drift, split in eligible.select(
                "ticker,sample_status,reaction,drift,split_ratio"
            ).fetchall()
        }
    assert observations["DIV"] == ("included", 0, 0, None)
    assert observations["SPLIT"] == ("included", 0, 0, "4:1")
    assert observations["RISE"] == ("included", 0.05, pytest.approx(-3 / 105), None)
    assert observations["FALL"] == ("included", -0.05, pytest.approx(4 / 95), None)
    assert observations["MISSING"][:3] == ("missing_session_bar", None, None)
    assert observations["CHANGED"][:3] == ("listing_boundary", None, None)
    assert observations["DELISTED"][:3] == ("unavailable_price_history", None, None)
    assert observations["NULLVEC"][:3] == ("invalid_vector", None, None)
    assert observations["NULLCOORD"][:3] == ("invalid_vector", None, None)
