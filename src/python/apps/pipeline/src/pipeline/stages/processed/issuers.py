"""Build dated issuer, ticker and alias tables for company linking."""

import json
import re
import unicodedata
from pathlib import Path
from typing import Annotated

import duckdb
import typer

LEGAL_FORMS = frozenset(
    {
        *("inc", "incorporated", "corp", "corporation", "co", "company"),
        *("ltd", "limited", "plc", "llc", "lp", "llp"),
        *("sa", "ag", "nv", "se", "spa", "bv", "gmbh"),
    }
)
STATE_SUFFIX = re.compile(r"\s*/[a-z]{2,4}/?\s*$")
POSSESSIVE = re.compile(r"['\u2019]s\b")
NON_WORD = re.compile(r"[\W_]+")


def normalize(name: str) -> str:
    """Return the comparison key shared by issuer aliases and mentions.

    Case, punctuation, possessives, a leading "the", SEC state suffixes such
    as "/DE/" and trailing legal forms are ignored. Words such as "Group" or
    "Holdings" are kept because they distinguish issuers.
    """
    text = unicodedata.normalize("NFKC", name).casefold()
    text = unicodedata.normalize("NFKC", text)
    text = POSSESSIVE.sub("", STATE_SUFFIX.sub("", text)).replace("&", " and ")
    tokens = NON_WORD.sub(" ", text).split()
    while len(tokens) > 1 and tokens[0] == "the":
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in LEGAL_FORMS:
        tokens.pop()
    return " ".join(tokens)


# Dates arrive as ISO timestamps; Wikidata "unknown value" IRIs read as unknown.
TABLES = """
CREATE MACRO day(value) AS try_cast(left(value, 10) AS DATE);

CREATE TABLE exchanges AS SELECT exchange FROM read_csv(getvariable('exchanges'));

CREATE TABLE wikidata_listing AS
SELECT cik::BIGINT AS cik, ticker, exchangeLabel AS exchange,
       day(start) AS valid_from, day("end") AS valid_to
FROM read_csv(getvariable('wikidata') || '/tickers.csv', all_varchar = true)
WHERE regexp_full_match(cik, '[0-9]+');

-- SEC listings are current and undated: an issuer is taken as listed from its
-- earliest dated US listing in Wikidata (Alphabet from 2016), otherwise always.
-- Wikidata also gives a parent's open listing to operating subsidiaries (AAL on
-- American Airlines, Inc.); the ticker's current SEC registrant takes it.
CREATE TABLE listing AS
WITH earliest AS (
    SELECT cik, min(valid_from) AS valid_from FROM wikidata_listing
    WHERE exchange IN (SELECT exchange FROM exchanges) GROUP BY cik
)
SELECT l.cik, l.ticker, l.exchange, e.valid_from, NULL::DATE AS valid_to,
       'sec' AS source
FROM sec_listing AS l LEFT JOIN earliest AS e USING (cik)
UNION ALL
SELECT *, 'wikidata' FROM wikidata_listing AS w
WHERE NOT (w.valid_to IS NULL AND EXISTS (
    SELECT 1 FROM sec_listing AS l WHERE l.ticker = w.ticker AND l.cik <> w.cik
));

CREATE TABLE tickers AS
SELECT * FROM listing
WHERE exchange IN (SELECT exchange FROM exchanges)
  AND (valid_to IS NULL OR valid_to >= getvariable('since')::DATE);

-- SEC submissions store the CIK as zero-padded text.
CREATE TABLE submissions AS
SELECT * REPLACE (cik::BIGINT AS cik) FROM read_json(
    getvariable('submissions'), format = 'newline_delimited', columns = {
        cik: 'VARCHAR', name: 'VARCHAR', entityType: 'VARCHAR', sic: 'VARCHAR',
        sicDescription: 'VARCHAR',
        formerNames: 'STRUCT("name" VARCHAR, "from" VARCHAR, "to" VARCHAR)[]'
    }
)
WHERE cik::BIGINT IN (SELECT cik FROM tickers);

CREATE TABLE names AS
SELECT item, cik::BIGINT AS cik, name, kind
FROM read_csv(getvariable('wikidata') || '/names.csv', all_varchar = true)
WHERE regexp_full_match(cik, '[0-9]+');

CREATE TABLE issuers AS
SELECT cik, coalesce(s.name, any_value(l.name)) AS name,
       any_value(s.entityType) AS entity_type, any_value(s.sic) AS sic,
       any_value(s.sicDescription) AS industry, min(n.item) AS wikidata
FROM (SELECT DISTINCT cik FROM tickers) AS u
LEFT JOIN submissions AS s USING (cik)
LEFT JOIN sec_listing AS l USING (cik)
LEFT JOIN names AS n USING (cik)
GROUP BY cik, s.name;

-- "Owned by" also records shareholdings (Twitter -> BlackRock), so it is kept
-- only for items that are not issuers themselves (YouTube -> Google), and not
-- when the owner is a bank, broker, asset manager or fund (SIC 6000-6299,
-- 6722, 6726, 6799), whose holdings are investments (SoftBank -> JPMorgan).
CREATE TABLE investors AS
SELECT DISTINCT n.item FROM names AS n JOIN issuers AS i USING (cik)
WHERE try_cast(i.sic AS INTEGER) BETWEEN 6000 AND 6299
   OR i.sic IN ('6722', '6726', '6799');

CREATE TABLE edges AS
SELECT item, parent, name, day(start) AS valid_from, day("end") AS valid_to
FROM read_csv(
    [getvariable('wikidata') || '/parents.csv',
     getvariable('wikidata') || '/owners.csv'],
    all_varchar = true, filename = true
)
WHERE sitelinks::INTEGER >= getvariable('min_sitelinks')
  AND NOT (ends_with(filename, 'owners.csv') AND (
      item IN (SELECT item FROM names) OR parent IN (SELECT item FROM investors)
  ));

-- A subsidiary resolves to its parent's issuer, or through one intermediate
-- parent (YouTube -> Google -> Alphabet); validity is the overlap of edges.
CREATE TABLE subsidiaries AS
WITH walks AS (
    SELECT name, parent AS target, valid_from, valid_to FROM edges
    UNION ALL
    SELECT child.name, parent.parent,
           greatest(child.valid_from, parent.valid_from),
           least(child.valid_to, parent.valid_to)
    FROM edges AS child JOIN edges AS parent ON child.parent = parent.item
)
SELECT DISTINCT names.cik, walks.name, walks.valid_from, walks.valid_to
FROM walks JOIN (SELECT DISTINCT item, cik FROM names) AS names
    ON walks.target = names.item
WHERE names.cik IN (SELECT cik FROM issuers)
  AND NOT coalesce(walks.valid_from > walks.valid_to, false);

CREATE TABLE aliases AS
WITH candidates AS (
    SELECT cik, name AS alias, 'sec_name' AS source,
           day(list_max([former."to" FOR former IN formerNames])) AS valid_from,
           NULL::DATE AS valid_to
    FROM submissions
    UNION ALL
    SELECT cik, former.name, 'former_name', day(former."from"), day(former."to")
    FROM (SELECT cik, unnest(formerNames) AS former FROM submissions)
    UNION ALL
    SELECT cik, name, 'sec_name', NULL, NULL
    FROM sec_listing
    WHERE cik IN (SELECT cik FROM issuers)
      AND cik NOT IN (SELECT cik FROM submissions)
    UNION ALL
    SELECT cik, name, 'wikidata_' || kind, NULL, NULL
    FROM names WHERE cik IN (SELECT cik FROM issuers)
    UNION ALL
    SELECT cik, name, 'wikidata_subsidiary', valid_from, valid_to FROM subsidiaries
    UNION ALL
    SELECT cik, ticker, 'ticker', valid_from, valid_to FROM tickers
)
SELECT DISTINCT cik, alias, normalize_name(alias) AS key, source, valid_from, valid_to
FROM candidates
WHERE length(normalize_name(alias)) >= 2;
"""


def prepare_issuers(
    source: Annotated[Path, typer.Option(help="Issuer snapshot.")] = Path(
        "data/raw/issuers"
    ),
    exchanges: Annotated[
        Path, typer.Option(help="CSV of exchange names that count as US-listed.")
    ] = Path("data/inputs/issuers/exchanges.csv"),
    since: Annotated[str, typer.Option(help="Earliest listing date kept.")] = (
        "2016-01-01"
    ),
    min_sitelinks: Annotated[
        int, typer.Option(help="Wikipedia editions a subsidiary needs.")
    ] = 10,
    output: Annotated[Path, typer.Option(help="New output directory.")] = Path(
        "data/processed/issuers"
    ),
) -> None:
    """Resolve listed CIKs, dated tickers and dated aliases for linking."""
    output.mkdir(parents=True, exist_ok=False)
    listing = json.loads((source / "sec/company_tickers_exchange.json").read_text())
    with duckdb.connect() as con:
        con.create_function("normalize_name", normalize, ["VARCHAR"], "VARCHAR")
        con.execute(
            "CREATE TABLE sec_listing (cik BIGINT, name VARCHAR, ticker VARCHAR, "
            "exchange VARCHAR)"
        )
        fields = listing["fields"]
        for values in listing["data"]:
            row = dict(zip(fields, values, strict=True))
            con.execute(
                "INSERT INTO sec_listing VALUES (?, ?, ?, ?)",
                [row["cik"], row["name"], row["ticker"], row["exchange"]],
            )
        variables = {
            "wikidata": str(source / "wikidata"),
            "submissions": str(source / "sec/submissions.jsonl"),
            "exchanges": str(exchanges),
            "since": since,
            "min_sitelinks": min_sitelinks,
        }
        for name, value in variables.items():
            con.execute(f"SET VARIABLE {name} = ?", [value])
        con.execute(TABLES)
        for table in ("issuers", "tickers", "aliases"):
            con.table(table).order("ALL").write_parquet(
                str(output / f"{table}.parquet"), compression="zstd"
            )
        summary = {
            "issuers": con.sql("SELECT count(*) FROM issuers").fetchall()[0][0],
            "aliases_by_source": dict(
                con.sql("SELECT source, count(*) FROM aliases GROUP BY ALL").fetchall()
            ),
            "excluded_exchanges": dict(
                con.sql(
                    "SELECT exchange, count(DISTINCT cik) FROM listing "
                    "WHERE exchange NOT IN (SELECT DISTINCT exchange FROM tickers) "
                    "GROUP BY ALL ORDER BY 2 DESC LIMIT 20"
                ).fetchall()
            ),
        }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    typer.echo(f"Wrote: {output}")
