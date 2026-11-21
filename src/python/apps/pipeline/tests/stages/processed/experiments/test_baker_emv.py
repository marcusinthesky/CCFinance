from datetime import date
from math import log, sqrt
from pathlib import Path

import duckdb
import pytest
from pipeline.stages.processed.experiments.baker_emv import (
    measure_baker_emv,
    prepare_baker_emv_market,
)

DICTIONARY = (
    Path(__file__).resolve().parents[8] / "data/inputs/baker-emv/dictionary.json"
)


@pytest.mark.integration
def test_news_hits_use_publication_month_and_whole_terms(tmp_path: Path) -> None:
    # Arrange
    raw = tmp_path / "raw"
    raw.mkdir()
    articles = tmp_path / "articles.parquet"
    hosts = tmp_path / "hosts.csv"
    hosts.write_text("host,publisher\nexample.com,Example\n")
    window = tmp_path / "window.json"
    window.write_text('{"start":"2023-09-01","end":"2023-11-01"}')
    output = tmp_path / "news"
    with duckdb.connect() as con:
        con.execute(
            """
            COPY (
                SELECT id, {'title': title} AS metadata, body AS text
                FROM (VALUES
                    ('repeat', 'Economic news',
                        'EQUITIES are risky. Equities are risky.'),
                    ('possessive', NULL, 'Financial risk for Standard & Poor\u2019s.'),
                    ('split', 'The economy and the stock', 'market and volatility.'),
                    ('substring', NULL, 'Economic instability in stocks is riskier.'),
                    ('october', NULL, 'Financial uncertainty.'),
                    ('duplicate', NULL, 'Economy, volatility and stock market.')
                ) AS t(id, title, body)
            ) TO ?
            """,
            [str(raw / "raw.parquet")],
        )
        con.execute(
            """
            COPY (
                SELECT id, 'example.com' AS host, published::DATE AS published,
                       '2023-10-01'::TIMESTAMP AS captured, id <> 'duplicate' AS usable
                FROM (VALUES ('repeat', '2023-09-30'), ('possessive', '2023-09-28'),
                    ('split', '2023-09-30'), ('substring', '2023-09-30'),
                    ('october', '2023-10-01'), ('duplicate', '2023-09-30')
                ) AS t(id, published)
            ) TO ?
            """,
            [str(articles)],
        )

    # Act
    measure_baker_emv(raw, articles, hosts, DICTIONARY, window, output)
    with duckdb.connect() as con:
        hits = con.execute(
            "SELECT id, emv_hit FROM read_parquet(?) ORDER BY id",
            [str(output / "article_hits.parquet")],
        ).fetchall()
        ledger = con.execute(
            """
            SELECT month, eligible_articles, publication_days, emv_hits, hit_share
            FROM read_parquet(?) ORDER BY month
            """,
            [str(output / "publisher_month.parquet")],
        ).fetchall()

    # Assert
    assert hits == [
        ("october", False),
        ("possessive", True),
        ("repeat", True),
        ("split", False),
        ("substring", False),
    ]
    assert ledger == [
        (date(2023, 9, 1), 4, 2, 2, 0.5),
        (date(2023, 10, 1), 1, 1, 0, 0.0),
        (date(2023, 11, 1), 0, 0, 0, None),
    ]


@pytest.mark.integration
def test_market_uses_preceding_close_and_trading_day_rms(tmp_path: Path) -> None:
    # Arrange
    source = tmp_path / "market.csv"
    source.write_text(
        "observation_date,VIXCLS,SP500\n"
        "2020-01-30,44,100\n"
        "2020-01-31,55,200\n"
        "2020-02-03,10,220\n"
        "2020-02-04,.,\n"
        "2020-02-05,20,242\n"
        "2020-02-17,99,\n"
        "2020-03-02,30,121\n"
    )
    window = tmp_path / "window.json"
    window.write_text('{"start":"2020-02-01","end":"2020-03-01"}')
    output = tmp_path / "market"

    # Act
    prepare_baker_emv_market(source, window, output)
    with duckdb.connect() as con:
        daily = con.execute(
            "SELECT day, study_day FROM read_parquet(?) ORDER BY day",
            [str(output / "daily_market.parquet")],
        ).fetchall()
        market = con.execute(
            """
            SELECT vix_days, return_days, vix, realized_volatility
            FROM read_parquet(?) ORDER BY month
            """,
            [str(output / "monthly_market.parquet")],
        ).fetchall()

    # Assert
    assert daily == [
        (date(2020, 1, 31), False),
        (date(2020, 2, 3), True),
        (date(2020, 2, 5), True),
        (date(2020, 2, 17), True),
        (date(2020, 3, 2), True),
    ]
    assert market[0] == pytest.approx((2, 2, 15, 100 * sqrt(252) * log(1.1)))
    assert market[1] == pytest.approx((1, 1, 30, 100 * sqrt(252) * log(2)))
