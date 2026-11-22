from datetime import date
from pathlib import Path

import duckdb
import pytest
from pipeline.stages.processed.experiments.baker_emv.news import measure_baker_emv

DICTIONARY = (
    Path(__file__).resolve().parents[9] / "data/inputs/baker-emv/dictionary.json"
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
