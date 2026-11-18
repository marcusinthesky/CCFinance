"""Check issuer keys, dated tickers and dated aliases from a small snapshot."""

import json
from datetime import date
from pathlib import Path

import duckdb
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pipeline.cli import app
from pipeline.stages.processed.issuers import normalize
from typer.testing import CliRunner


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Apple Inc.", "apple"),
        ("AMAZON COM INC", "amazon com"),
        ("The Coca-Cola Company", "coca cola"),
        ("META PLATFORMS, INC. /DE/", "meta platforms"),
        ("Johnson & Johnson", "johnson and johnson"),
        ("Apple\u2019s", "apple"),
        ("Goldman Sachs Group Inc", "goldman sachs group"),
        ("Inc.", "inc"),
    ],
)
def test_normalize_ignores_case_punctuation_and_legal_forms(
    name: str, key: str
) -> None:
    # Arrange: an issuer or mention name with its expected key.
    expected = key

    # Act: normalize the name.
    actual = normalize(name)

    # Assert: the key ignores presentation but keeps distinguishing words.
    assert actual == expected


@pytest.mark.unit
@given(st.text())
def test_normalize_is_idempotent(name: str) -> None:
    # Arrange: any text, including punctuation and non-Latin scripts.
    key = normalize(name)

    # Act: normalize the key again.
    again = normalize(key)

    # Assert: keys are fixed points, so aliases and mentions compare stably.
    assert again == key


def _csv(path: Path, header: str, *rows: str) -> None:
    path.write_text("\n".join((header, *rows)) + "\n", encoding="utf-8")


@pytest.mark.component
def test_prepare_issuers_dates_tickers_and_aliases(tmp_path: Path) -> None:
    # Arrange: renames, delistings, shareholders, owned brands, a subsidiary ticker.
    source = tmp_path / "raw"
    (source / "sec").mkdir(parents=True)
    (source / "wikidata").mkdir()
    listing = [
        [1326801, "Meta Platforms, Inc.", "META", "Nasdaq"],
        [6201, "American Airlines Group Inc.", "AAL", "Nasdaq"],
        [9, "Pink Co", "PNK", "OTC"],
    ]
    (source / "sec/company_tickers_exchange.json").write_text(
        json.dumps({"fields": ["cik", "name", "ticker", "exchange"], "data": listing})
    )
    facebook = {
        "name": "FACEBOOK INC",
        "from": "2004-07-30T00:00:00.000Z",
        "to": "2021-10-28T00:00:00.000Z",
    }
    submissions: list[dict[str, object]] = [
        {
            "cik": "0001326801",
            "name": "Meta Platforms, Inc.",
            "formerNames": [facebook],
        },
        {"cik": "0001418091", "name": "Twitter, Inc.", "formerNames": []},
        {"cik": "0001364742", "name": "BlackRock, Inc.", "sic": "6282"},
    ]
    (source / "sec/submissions.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in submissions)
    )
    wikidata = source / "wikidata"
    _csv(
        wikidata / "tickers.csv",
        "item,cik,exchange,exchangeLabel,ticker,start,end",
        "Q380,0001326801,Q82059,Nasdaq,FB,2012-05-18T00:00:00Z,2022-06-08",
        "Q2,0001418091,Q13677,New York Stock Exchange,TWTR,2013-11-07,2022-10-27",
        "Q3,0001652044,Q82059,Nasdaq,GOOGL,2016-01-01T00:00:00Z,",
        "Q7,0001364742,Q13677,New York Stock Exchange,BLK,1999-10-01,",
        "Q8,0000004515,Q82059,Nasdaq,AAL,,",
        "Q312,0000320193,Q217475,Tokyo Stock Exchange,6689,1990-09-01,2004-12-25",
    )
    _csv(
        wikidata / "names.csv",
        "item,cik,name,kind",
        "Q380,0001326801,Facebook,alias",
        "Q2,0001418091,Twitter,alias",
        "Q3,0001652044,Alphabet Inc.,label",
        "Q7,0001364742,BlackRock,label",
        "Q95,0001288776,Google,label",
    )
    header = "item,parent,name,start,end,sitelinks"
    _csv(
        wikidata / "parents.csv",
        header,
        "Q95,Q3,Google,2015-01-01T00:00:00Z,,212",
    )
    _csv(
        wikidata / "owners.csv",
        header,
        "Q866,Q95,YouTube,2006-11-01T00:00:00Z,,245",
        "Q9,Q95,Obscure,,,3",
        "Q2,Q7,Twitter,,,90",
        "Q20,Q7,SoftBank Group,,,90",
    )
    exchanges = tmp_path / "exchanges.csv"
    _csv(exchanges, "exchange", "Nasdaq", "New York Stock Exchange")
    output = tmp_path / "issuers"

    # Act: prepare the linking tables through the public CLI.
    result = CliRunner().invoke(
        app,
        [
            "stages",
            "processed",
            "prepare-issuers",
            "--source",
            str(source),
            "--exchanges",
            str(exchanges),
            "--output",
            str(output),
        ],
    )

    # Assert: listed issuers carry dated tickers, names and subsidiary aliases.
    assert result.exit_code == 0, result.output
    keys = [
        "facebook",
        "meta platforms",
        "youtube",
        "twtr",
        "twitter",
        "softbank group",
    ]
    with duckdb.connect() as con:
        issuers = con.execute(
            "SELECT cik FROM read_parquet(?) ORDER BY 1",
            [str(output / "issuers.parquet")],
        ).fetchall()
        meta = con.execute(
            "SELECT ticker, valid_from, valid_to FROM read_parquet(?) "
            "WHERE cik = 1326801 ORDER BY ALL",
            [str(output / "tickers.parquet")],
        ).fetchall()
        aliases = con.execute(
            "SELECT key, cik, source, valid_from, valid_to FROM read_parquet(?) "
            "WHERE list_contains(?, key) ORDER BY ALL",
            [str(output / "aliases.parquet"), keys],
        ).fetchall()
    assert issuers == [(6201,), (1326801,), (1364742,), (1418091,), (1652044,)]
    assert meta == [
        ("FB", date(2012, 5, 18), date(2022, 6, 8)),
        ("META", date(2012, 5, 18), None),
    ]
    assert aliases == [
        ("facebook", 1326801, "former_name", date(2004, 7, 30), date(2021, 10, 28)),
        ("facebook", 1326801, "wikidata_alias", None, None),
        ("meta platforms", 1326801, "sec_name", date(2021, 10, 28), None),
        ("twitter", 1418091, "sec_name", None, None),
        ("twitter", 1418091, "wikidata_alias", None, None),
        ("twtr", 1418091, "ticker", date(2013, 11, 7), date(2022, 10, 27)),
        ("youtube", 1652044, "wikidata_subsidiary", date(2015, 1, 1), None),
    ]
