"""Check explicit-ticker anchors and dated, scored issuer links."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.cli import app
from pipeline.stages.processed.company_links import find_anchors
from typer.testing import CliRunner


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "anchors"),
    [
        ("Apple Inc. (NASDAQ: AAPL) rose", [(11, "AAPL")]),
        ("Berkshire (NYSE:BRK.B) fell", [(10, "BRK.B")]),
        ("GE (NYSE: GE, TSX: X)", [(3, "GE")]),
        ("Shopify (TSX: SHOP)", []),
        ("Walmart Inc WMT.N fell", [(12, "WMT")]),
        ("Apple (AAPL.O) and A.O. Smith", [(7, "AAPL")]),
        ("in brackets (AAPL)", []),
    ],
)
def test_find_anchors_reads_us_exchange_tickers(
    text: str, anchors: list[tuple[int, str]]
) -> None:
    # Arrange: text that may name a US exchange and ticker in brackets.
    expected = [{"start": start, "ticker": ticker} for start, ticker in anchors]

    # Act: find anchors.
    actual = find_anchors(text)

    # Assert: only US exchange prefixes count.
    assert actual == expected


ARTICLES = [
    ("a1", "2023-03-01", "example.com", "Apple Inc. (NASDAQ: AAPL) rose. Apple grew."),
    ("a2", "2019-05-01", "example.com", "Facebook shares fell; Acme did not."),
    ("a3", "2023-05-01", "example.com", "Facebook shares fell."),
    ("a4", "2023-03-01", "www.reuters.com", "Reuters said Delta cut flights."),
    ("a5", "2023-03-01", "example.com", "Delta (NYSE: DAL) up. " * 3),
    ("a6", "2023-03-01", "example.com", "Ford (NYSE: F) fell. " * 3),
    ("a7", "2023-03-01", "example.com", "Ford cut prices."),
    ("a8", "2023-03-01", "example.com", "Tesla rose; TSLA up."),
    ("a9", "2023-03-01", "example.com", "TSLA fell."),
    ("b1", "2023-03-01", "example.com", "RBC rose."),
    ("b2", "2023-03-01", "example.com", "Walmart Inc WMT.N fell."),
    ("b3", "2023-03-01", "example.com", "Credit Suisse fell."),
    ("b4", "2023-03-01", "example.com", "Chegg (CHGG) rose."),
]
COMPANIES = {"a1": ["Apple Inc.", "Apple"], "a2": ["Facebook", "Acme"]} | {
    "a3": ["Facebook"],
    "a4": ["Reuters", "Delta"],
    "a5": ["Delta"],
    "a6": ["Ford"],
    "a7": ["Ford"],
    "a8": ["Tesla", "TSLA"],
    "a9": ["TSLA"],
    "b1": ["RBC"],
    "b2": ["Walmart Inc WMT.N"],
    "b3": ["Credit Suisse"],
    "b4": ["Chegg (CHGG)"],
}
ISSUERS = {
    "aliases": (
        "cik BIGINT, key VARCHAR, source VARCHAR, valid_from DATE, valid_to DATE",
        [
            (320193, "apple", "sec_name", None, None),
            (1326801, "facebook", "former_name", "2004-07-30", "2021-10-28"),
            (1326801, "facebook", "wikidata_alias", None, None),
            (1075124, "reuters", "wikidata_alias", None, None),
            (27904, "delta", "wikidata_alias", None, None),
            (1101396, "delta", "wikidata_alias", None, None),
            (1318605, "tesla", "sec_name", None, None),
            (1318605, "tsla", "ticker", None, None),
            (1000275, "rbc", "wikidata_alias", None, None),
            (1324948, "rbc", "wikidata_alias", None, None),
            (1053092, "credit suisse", "sec_name", None, None),
            (1159510, "credit suisse", "sec_name", None, None),
            (1364954, "chegg", "sec_name", None, None),
        ],
    ),
    "tickers": (
        "cik BIGINT, ticker VARCHAR, exchange VARCHAR, valid_from DATE, valid_to DATE",
        [
            (320193, "AAPL", "Nasdaq", None, None),
            (1326801, "META", "Nasdaq", None, None),
            (1326801, "FB", "Nasdaq", "2012-05-18", "2022-06-08"),
            (1326801, "META", "Nasdaq", "2022-06-09", None),
            (1075124, "TRI", "NYSE", None, None),
            (27904, "DAL", "NYSE", None, None),
            (27904, "DAL-PA", "NYSE", None, None),
            (27904, "DALX", "NYSE", None, None),
            (1101396, "DLA", "NYSE", None, None),
            (37996, "F", "NYSE", None, None),
            (1318605, "TSLA", "Nasdaq", None, None),
            (1000275, "RY", "NYSE", None, None),
            (1324948, "RY", "NYSE", None, None),
            (104169, "WMT", "Nasdaq", None, None),
            (1053092, "GLDI", "NYSE", None, None),
            (1159510, "CS", "NYSE", None, None),
            (1364954, "CHGG", "NYSE", None, None),
        ],
    ),
}


def _fixture(root: Path) -> list[str]:
    """Write raw articles, GLiNER mentions and issuer tables under root."""
    raw = root / "raw/2020-01/eng_Latn/part-000000.parquet"
    mentions = root / "extraction/mentions/2020-01--eng_Latn--part-000000--000.parquet"
    for folder in (raw.parent, mentions.parent, root / "issuers"):
        folder.mkdir(parents=True)
    labels = {"local_relevance": ["substantive", "incidental", "uncertain"]}
    labels["financial_sentiment"] = ["positive", "negative"]
    (root / "extraction/schema.json").write_text(json.dumps({"labels": labels}))
    (root / "domains.csv").write_text("domain\nreuters.com\nexample.com\n")
    (root / "publishers.csv").write_text("domain,name\nreuters.com,Thomson Reuters\n")
    rows: list[tuple[str, str, str, int, int]] = [("a1", "person", "Tim", 0, 3)]
    for article, _, _, body in ARTICLES:
        for name in COMPANIES[article]:
            start = body.find(name)
            while start >= 0:
                rows.append((article, "company", name, start, start + len(name)))
                start = body.find(name, start + len(name) + 1)
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE raw (id VARCHAR, text VARCHAR, metadata STRUCT("
            "publish_date VARCHAR, warc_date TIMESTAMPTZ, url_hostname VARCHAR))"
        )
        con.executemany(
            "INSERT INTO raw VALUES (?, ?, {'publish_date': ?, 'warc_date': NULL, "
            "'url_hostname': ?})",
            [(i, text, day, host) for i, day, host, text in ARTICLES],
        )
        con.table("raw").write_parquet(str(raw))
        con.execute(
            "CREATE TABLE mentions (id VARCHAR, entity_type VARCHAR, text VARCHAR, "
            "start INTEGER, stop INTEGER, confidence FLOAT, local_relevance FLOAT[], "
            "financial_sentiment FLOAT[])"
        )
        con.executemany(
            "INSERT INTO mentions VALUES "
            "(?, ?, ?, ?, ?, 0.9, [0.7, 0.2, 0.1], [0.6, 0.4])",
            rows,
        )
        con.table("mentions").write_parquet(str(mentions))
        for name, (columns, values) in ISSUERS.items():
            con.execute(f"CREATE TABLE {name} ({columns})")
            insert = f"INSERT INTO {name} VALUES (?, ?, ?, ?, ?)"  # noqa: S608
            con.executemany(insert, values)
            con.table(name).write_parquet(str(root / f"issuers/{name}.parquet"))
    options = {
        "extraction": "extraction",
        "source": "raw",
        "issuers": "issuers",
        "domains": "domains.csv",
        "publishers": "publishers.csv",
        "output": "links",
    }
    arguments = ["stages", "processed", "link-companies"]
    for option, path in options.items():
        arguments += [f"--{option}", str(root / path)]
    return arguments


@pytest.mark.integration
def test_link_companies_scores_dated_candidates(tmp_path: Path) -> None:
    # Arrange: anchors, a rename, ambiguity, learned aliases, coherence, a byline.
    arguments = _fixture(tmp_path)

    # Act: stage, estimate anchor priors and link through the public CLI.
    result = CliRunner().invoke(app, arguments)

    # Assert: each mention has its method, score and self-publisher flag.
    assert result.exit_code == 0, result.output
    links = tmp_path / "links"
    with duckdb.connect() as con:
        mentions = con.execute(
            "SELECT id, text, cik, method, round(link_score, 3), self_publisher "
            "FROM read_parquet(?) ORDER BY id, start",
            [str(links / "mentions/*.parquet")],
        ).fetchall()
        articles = con.execute(
            "SELECT id, cik, ticker, n_mentions FROM read_parquet(?) ORDER BY id, cik",
            [str(links / "articles/*.parquet")],
        ).fetchall()
        unresolved = con.execute(
            "SELECT id, key, n FROM read_parquet(?)",
            [str(links / "unresolved/*.parquet")],
        ).fetchall()
    assert mentions == [
        ("a1", "Apple Inc.", 320193, "anchor", 1.0, False),
        ("a1", "Apple", 320193, "propagated", 1.0, False),
        ("a2", "Facebook", 1326801, "alias", 1.0, False),
        ("a2", "Acme", None, "unresolved", None, False),
        ("a3", "Facebook", 1326801, "alias", 0.5, False),
        ("a4", "Reuters", 1075124, "alias", 0.5, True),
        ("a4", "Delta", 27904, "alias", 0.889, False),
        *[("a5", "Delta", 27904, "anchor", 1.0, False)] * 3,
        *[("a6", "Ford", 37996, "anchor", 1.0, False)] * 3,
        ("a7", "Ford", 37996, "alias", 1.0, False),
        ("a8", "Tesla", 1318605, "alias", 1.0, False),
        ("a8", "TSLA", 1318605, "alias", 1.0, False),
        ("a9", "TSLA", 1318605, "alias", 0.2, False),
        ("b1", "RBC", 1000275, "alias", 0.5, False),
        ("b2", "Walmart Inc WMT.N", 104169, "anchor", 1.0, False),
        ("b3", "Credit Suisse", None, "ambiguous", 0.5, False),
        ("b4", "Chegg (CHGG)", 1364954, "alias", 1.0, False),
    ]
    assert articles == [
        ("a1", 320193, "AAPL", 2),
        ("a2", 1326801, "FB", 1),
        ("a3", 1326801, "META", 1),
        ("a4", 27904, "DAL", 1),
        ("a4", 1075124, "TRI", 1),
        ("a5", 27904, "DAL", 3),
        ("a6", 37996, "F", 3),
        ("a7", 37996, "F", 1),
        ("a8", 1318605, "TSLA", 2),
        ("a9", 1318605, "TSLA", 1),
        ("b1", 1000275, "RY", 1),
        ("b2", 104169, "WMT", 1),
        ("b4", 1364954, "CHGG", 1),
    ]
    assert unresolved == [("a2", "acme", 1)]
    assert not (links / "staged").exists()
