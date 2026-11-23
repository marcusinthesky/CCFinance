"""Link GLiNER company mentions to US-listed issuers, with evidence and scores.

Each extraction row group is a unit. Staging finds explicit exchange tickers
such as "(NASDAQ: AAPL)", or Reuters codes such as "WMT.N", within or just after
a mention. Across the corpus, these anchors give counts n(key, issuer) and
teach aliases the issuer tables lack. A key anchored at least three times, at
least 90% of the time to one issuer, becomes an alias of that issuer if it
begins one of the issuer's names ("Ford" -> Ford Motor Co) or is anchored in at
least 0.5% of its mentions ("Eli Lilly").

Candidates are the listed securities whose aliases match on the article date;
filers sharing a ticker count once. Each scores weight x share, and a mention
links only if its best candidate holds at least 75% of the evidence. The weight
reflects how specifically the alias names the issuer, raised to a full name's
weight when the same article names or anchors that issuer ("TSLA" beside
"Tesla"). The share is the candidate's smoothed anchor share. Scores aggregate
per article and issuer.
"""

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Annotated

import duckdb
import typer

from pipeline.stages.processed.issuers import normalize

US_EXCHANGES = (
    "NASDAQ|Nasdaq|NasdaqGS|NasdaqGM|NasdaqCM|NYSE American|NYSE MKT|NYSE Arca|"
    "NYSEArca|NYSE|AMEX|Cboe|CBOE|BATS"
)
ANCHOR = re.compile(
    rf"\((?:{US_EXCHANGES})\s*:\s*([A-Z]{{1,5}}(?:[.\-][A-Z])?)\s*[),;]"
)
# Reuters instrument codes such as "WMT.N" or "(AAPL.O)" name US listings too.
RIC = re.compile(r"\b([A-Z]{1,5})\.(?:N|O|OQ|A|K)\b(?!\.)")
# An anchor lies within its mention or closely after it: "Apple Inc. (NASDAQ: AAPL)".
ANCHOR_GAP = 16
# Prior weight of a date-valid alias, by how specifically it names the issuer.
SOURCE_WEIGHTS = {
    "sec_name": 1.0,
    "former_name": 1.0,
    "wikidata_label": 1.0,
    "anchor_alias": 1.0,
    "wikidata_alias": 0.5,
    "wikidata_subsidiary": 0.5,
    "ticker": 0.2,
}
# Prefer dated listings, then plain common-stock symbols over preferred shares,
# notes and other securities filed under the same CIK (JPM over AMJB or JPM-PC).
PRIMARY = (
    "t.valid_from IS NULL, t.valid_from DESC, regexp_matches(t.ticker, '[-.]'), "
    "length(t.ticker), t.ticker"
)
# A mention links only to an unambiguous best candidate, holding at least this
# share of the evidence; otherwise it is "ambiguous" and keeps its candidates.
MIN_SHARE = 0.75
# A trailing ticker in a mention, "Chegg (CHGG)", is not part of the name.
TRAILING_TICKER = r"\s*\([A-Z][A-Z0-9.\-]{0,6}\)\s*$"
# A key becomes an anchor alias of an issuer it is anchored to often and mostly.
LEARNED_ANCHORS = 3
LEARNED_SHARE = 0.9
LEARNED_RATE = 0.005
COVERS = (
    "({table}.valid_from IS NULL OR {table}.valid_from <= {day}) "
    "AND ({table}.valid_to IS NULL OR {day} <= {table}.valid_to)"
)


def find_anchors(text: str) -> list[dict[str, object]]:
    """Return the offset and ticker of each US exchange anchor or Reuters code."""
    matches = [match for pattern in (ANCHOR, RIC) for match in pattern.finditer(text)]
    return [
        {"start": match.start(), "ticker": match.group(1)}
        for match in sorted(matches, key=lambda match: match.start())
    ]


def _write(con: duckdb.DuckDBPyConnection, query: str, target: Path) -> None:
    temporary = target.with_suffix(".tmp")
    con.execute(
        f"COPY ({query}) TO '{temporary}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 12)"
    )
    os.replace(temporary, target)


def row_group(con: duckdb.DuckDBPyConnection, path: Path, group: int) -> list[int]:
    """Return the first and stop row numbers of one Parquet row group."""
    sizes = con.execute(
        "SELECT row_group_id, any_value(row_group_num_rows) FROM parquet_metadata(?) "
        "GROUP BY 1 ORDER BY 1",
        [str(path)],
    ).fetchall()
    first = sum(rows for index, rows in sizes if index < group)
    return [first, first + dict(sizes)[group]]


def stage_unit(
    con: duckdb.DuckDBPyConnection, raw: Path, mentions: Path, target: Path
) -> None:
    """Attach dates, publishers, keys and explicit-ticker anchors to mentions."""
    stem, group = mentions.stem.rsplit("--", 1)
    source = raw / (stem.replace("--", "/") + ".parquet")
    first, stop = row_group(con, source, int(group))
    con.execute(
        """CREATE OR REPLACE TEMP TABLE unit_articles AS
        SELECT id, length(text) AS length, anchors(text) AS anchors,
               coalesce(try_cast(left(metadata.publish_date, 10) AS DATE),
                        metadata.warc_date::DATE) AS day,
               regexp_replace(lower(metadata.url_hostname), '^www[.]', '') AS host
        FROM read_parquet($source, file_row_number = true)
        WHERE file_row_number >= $first AND file_row_number < $stop""",
        {"source": str(source), "first": first, "stop": stop},
    )
    con.execute(
        """CREATE OR REPLACE TEMP TABLE unit_mentions AS
        WITH mentions AS (
            SELECT * FROM read_parquet($mentions) WHERE entity_type = 'company'
            QUALIFY row_number() OVER (PARTITION BY id, start ORDER BY stop DESC) = 1
        ), keys AS (
            SELECT text, normalize_name(regexp_replace(text, $ticker, '')) AS key
            FROM (SELECT DISTINCT text FROM mentions)
        )
        SELECT m.id, m.start, m.stop, m.text, k.key, m.confidence,
               m.local_relevance, m.financial_sentiment, a.day, a.host, a.length
        FROM mentions AS m JOIN keys AS k USING (text)
        JOIN unit_articles AS a USING (id)""",
        {"mentions": str(mentions), "ticker": TRAILING_TICKER},
    )
    covers = COVERS.format(table="t", day="n.day")
    _write(
        con,
        f"""WITH anchors AS (
            SELECT id, day, anchor.start AS at,
                   replace(anchor.ticker, '.', '-') AS ticker
            FROM (SELECT id, day, unnest(anchors) AS anchor FROM unit_articles)
        ), nearest AS (
            SELECT a.id, a.day, a.ticker, max(m.start) AS start
            FROM anchors AS a JOIN unit_mentions AS m
              ON m.id = a.id AND m.start <= a.at AND a.at - m.stop <= {ANCHOR_GAP}
            GROUP BY a.id, a.day, a.ticker, a.at
        ), resolved AS (
            SELECT n.id, n.start, any_value(t.cik) AS anchor_cik
            FROM nearest AS n
            JOIN tickers AS t ON replace(t.ticker, '.', '-') = n.ticker AND {covers}
            GROUP BY n.id, n.start HAVING count(DISTINCT t.cik) = 1
        )
        SELECT m.*, r.anchor_cik
        FROM unit_mentions AS m LEFT JOIN resolved AS r USING (id, start)""",  # noqa: S608 - authored constants.
        target,
    )


def _recover_names(con: duckdb.DuckDBPyConnection) -> None:
    """Resolve one decorated SEC name only when its dated listing corroborates it."""
    alias_date = COVERS.format(table="a", day="u.day")
    listing_date = COVERS.format(table="t", day="u.day")
    con.execute(
        rf"""WITH forms AS (
            SELECT *,
                regexp_extract(text, '\s+([A-Z]{{1,5}}(?:[.-][A-Z])?)$', 1) AS suffix,
                   starts_with(lower(text), 'nasdaq-traded ') AS nasdaq
            FROM unit_links WHERE method = 'unresolved'
        ), names AS (
            SELECT *, normalize_name(CASE
                WHEN nasdaq THEN substr(text, 14)
                WHEN ends_with(lower(text), ' stock') THEN left(text, length(text)-6)
                WHEN suffix <> '' THEN left(text, length(text)-length(suffix))
            END) AS clean
            FROM forms WHERE nasdaq OR ends_with(lower(text), ' stock') OR suffix <> ''
        ), matched AS (
            SELECT u.id, u.start, u.clean, any_value(a.cik) AS cik
            FROM names AS u JOIN aliases AS a ON u.clean = a.key AND {alias_date}
            JOIN tickers AS t ON t.cik = a.cik AND {listing_date}
            WHERE a.source IN ('sec_name', 'former_name') AND u.clean <> ''
            GROUP BY u.id, u.start, u.clean
            HAVING count(DISTINCT a.cik) = 1 AND bool_or(
                (u.suffix = '' OR replace(t.ticker,'.','-') = replace(u.suffix,'.','-'))
                AND (NOT u.nasdaq OR lower(t.exchange) = 'nasdaq'))
        )
        UPDATE unit_links AS l SET cik = m.cik, method = 'normalized_name',
            link_score = 1.0, candidates = [{{'cik': m.cik, 'score': 1.0}}],
            self_publisher = l.self_publisher OR EXISTS (
                SELECT 1 FROM publishers p WHERE p.key = m.clean AND
                (l.host = p.domain OR ends_with(l.host, '.' || p.domain)))
        FROM matched m WHERE l.id = m.id AND l.start = m.start"""  # noqa: S608
    )


def link_unit(
    con: duckdb.DuckDBPyConnection,
    staged: Path,
    smoothing: float,
    labels: dict[str, list[str]],
    targets: dict[str, Path],
    recover_names: bool,
) -> None:
    """Choose one issuer per mention and aggregate links per article."""
    weight = " ".join(f"WHEN '{s}' THEN {w}" for s, w in SOURCE_WEIGHTS.items())
    alias_covers = COVERS.format(table="a", day="s.day")
    listed = COVERS.format(table="t", day="s.day")
    con.execute(
        f"""CREATE OR REPLACE TEMP TABLE unit_links AS
        WITH staged AS (SELECT * FROM read_parquet($staged)),
        candidates AS (
            SELECT s.id, s.start, s.key, a.cik,
                   max(CASE a.source {weight} END) AS weight
            FROM staged AS s JOIN known AS a ON s.key = a.key AND {alias_covers}
            WHERE EXISTS (SELECT 1 FROM tickers AS t WHERE t.cik = a.cik AND {listed})
            GROUP BY ALL
        ), named AS (
            SELECT id, cik FROM candidates WHERE weight >= 1.0
            UNION
            SELECT id, anchor_cik FROM staged WHERE anchor_cik IS NOT NULL
        ), coherent AS (
            SELECT c.id, c.start, c.key, c.cik,
                   CASE WHEN n.cik IS NULL THEN c.weight ELSE 1.0 END AS weight
            FROM candidates AS c LEFT JOIN named AS n USING (id, cik)
        ), scored AS (
            SELECT c.id, c.start, c.cik, c.weight, coalesce(p.n, 0) AS n,
                   first(t.ticker ORDER BY {PRIMARY}) AS security
            FROM coherent AS c
            JOIN staged AS s USING (id, start)
            JOIN tickers AS t ON t.cik = c.cik AND {listed}
            LEFT JOIN priors AS p ON p.key = c.key AND p.cik = c.cik
            GROUP BY c.id, c.start, c.cik, c.weight, p.n
        ), securities AS (
            -- Filers of one listed security (a parent and the subsidiary that
            -- carries its ticker) are one candidate, so their evidence adds up.
            SELECT id, start, first(cik ORDER BY n DESC, weight DESC, cik) AS cik,
                   max(weight) AS weight, sum(n) + $smoothing * max(weight) AS evidence
            FROM scored GROUP BY id, start, security
        ), ranked AS (
            SELECT id, start,
                   list({{'cik': cik, 'score': weight * evidence / total}}
                        ORDER BY weight * evidence / total DESC, cik)[:3]
                       AS candidates,
                   arg_max(evidence / total, weight * evidence / total) AS share
            FROM (SELECT *, sum(evidence) OVER (PARTITION BY id, start) AS total
                  FROM securities)
            GROUP BY id, start
        ), anchored AS (
            SELECT DISTINCT id, key, anchor_cik AS cik
            FROM staged WHERE anchor_cik IS NOT NULL
        ), propagated AS (
            SELECT s.id, s.start, any_value(a.cik) AS cik
            FROM staged AS s JOIN anchored AS a ON s.id = a.id
              AND (s.key = a.key OR starts_with(a.key, s.key || ' '))
            WHERE s.anchor_cik IS NULL
            GROUP BY s.id, s.start HAVING count(DISTINCT a.cik) = 1
        )
        SELECT s.*, r.candidates,
               coalesce(s.anchor_cik, p.cik, CASE WHEN r.share >= {MIN_SHARE}
                                                  THEN r.candidates[1].cik END)
                   AS cik,
               CASE WHEN s.anchor_cik IS NOT NULL OR p.cik IS NOT NULL THEN 1.0
                    ELSE r.candidates[1].score END AS link_score,
               CASE WHEN s.anchor_cik IS NOT NULL THEN 'anchor'
                    WHEN p.cik IS NOT NULL THEN 'propagated'
                    WHEN r.share >= {MIN_SHARE} THEN 'alias'
                    WHEN r.candidates IS NOT NULL THEN 'ambiguous'
                    ELSE 'unresolved' END AS method,
               EXISTS (SELECT 1 FROM publishers AS x WHERE x.key = s.key AND
                       (s.host = x.domain OR ends_with(s.host, '.' || x.domain)))
                   AS self_publisher
        FROM staged AS s
        LEFT JOIN ranked AS r USING (id, start)
        LEFT JOIN propagated AS p USING (id, start)""",  # noqa: S608 - authored constants.
        {"staged": str(staged), "smoothing": smoothing},
    )
    if recover_names:
        _recover_names(con)
    _write(
        con,
        "SELECT id, start, stop, text, key, cik, link_score, method, candidates, "
        "self_publisher FROM unit_links",
        targets["mentions"],
    )
    _write(
        con,
        "SELECT id, key, count(*) AS n FROM unit_links "
        "WHERE method = 'unresolved' GROUP BY ALL",
        targets["unresolved"],
    )
    substantive = labels["local_relevance"].index("substantive") + 1
    sentiment = ", ".join(
        f"sum(link_score * financial_sentiment[{index}]) / sum(link_score)"
        for index in range(1, len(labels["financial_sentiment"]) + 1)
    )
    covers = COVERS.format(table="t", day="l.day")
    _write(
        con,
        f"""WITH articles AS (
            SELECT id, cik, any_value(day) AS day, count(*) AS n_mentions,
                   max(link_score) AS link_score,
                   max(local_relevance[{substantive}]) AS relevance_substantive,
                   [{sentiment}]::FLOAT[] AS sentiment,
                   min(start) / any_value(length) AS first_offset_share,
                   bool_and(self_publisher) AS self_publisher,
                   list({{'start': start, 'stop': stop, 'method': method,
                          'score': link_score}} ORDER BY start) AS evidence
            FROM unit_links WHERE cik IS NOT NULL GROUP BY id, cik
        )
        SELECT l.*,
               first(t.ticker ORDER BY {PRIMARY}) AS ticker,
               first(t.exchange ORDER BY {PRIMARY}) AS exchange
        FROM articles AS l LEFT JOIN tickers AS t ON t.cik = l.cik AND {covers}
        GROUP BY ALL""",  # noqa: S608 - authored constants.
        targets["articles"],
    )


def link_companies(
    extraction: Annotated[
        Path, typer.Option(help="GLiNER output with mentions/ and schema.json.")
    ] = Path("data/processed/article-metadata"),
    source: Annotated[Path, typer.Option(help="Raw Fine News shards.")] = Path(
        "data/raw/fine-news"
    ),
    issuers: Annotated[Path, typer.Option(help="Prepared issuer tables.")] = Path(
        "data/processed/issuers"
    ),
    domains: Annotated[Path, typer.Option(help="Publisher domain list.")] = Path(
        "data/inputs/fine-news/domains.csv"
    ),
    publishers: Annotated[
        Path, typer.Option(help="Publisher names that are not their domain.")
    ] = Path("data/inputs/company-links/publishers.csv"),
    smoothing: Annotated[
        float, typer.Option(help="Pseudo-count given to the alias weight.")
    ] = 1.0,
    recover_names: Annotated[
        bool, typer.Option(help="Recover decorated SEC names.")
    ] = False,
    output: Annotated[Path, typer.Option(help="Output directory.")] = Path(
        "data/processed/company-links"
    ),
) -> None:
    """Link company mentions to dated US-listed issuers, resuming by unit."""
    units = sorted((extraction / "mentions").glob("*.parquet"))
    labels = json.loads((extraction / "schema.json").read_text())["labels"]
    contract = {
        "units": hashlib.sha256("\n".join(u.name for u in units).encode()).hexdigest(),
        "aliases": hashlib.sha256(
            (issuers / "aliases.parquet").read_bytes()
        ).hexdigest(),
        "smoothing": smoothing,
    }
    if recover_names:
        contract["ruleset"] = "normalized-name-v1"
    output.mkdir(parents=True, exist_ok=True)
    recorded = output / "contract.json"
    if recorded.exists() and json.loads(recorded.read_text()) != contract:
        raise SystemExit(f"{recorded} differs; use a new output directory.")
    recorded.write_text(json.dumps(contract, indent=2) + "\n")
    folders = ("staged", "mentions", "unresolved", "articles")
    for folder in folders:
        (output / folder).mkdir(exist_ok=True)
    with duckdb.connect() as con:
        con.execute("SET TimeZone = 'UTC'")
        con.create_function("normalize_name", normalize, ["VARCHAR"], "VARCHAR")
        con.create_function(
            "anchors",
            find_anchors,
            ["VARCHAR"],
            "STRUCT(start INTEGER, ticker VARCHAR)[]",
        )
        for table in ("aliases", "tickers"):
            con.read_parquet(str(issuers / f"{table}.parquet")).create(table)
        con.execute(
            """CREATE TABLE publishers AS
            SELECT domain, normalize_name(name) AS key FROM read_csv($publishers)
            UNION
            SELECT domain, normalize_name(replace(split_part(domain, '.', 1), '-', ' '))
            FROM read_csv($domains)""",
            {"publishers": str(publishers), "domains": str(domains)},
        )
        for unit in units:
            staged = output / "staged" / unit.name
            if not staged.exists() and not (output / "articles" / unit.name).exists():
                stage_unit(con, source, unit, staged)
                typer.echo(f"staged {unit.name}")
        priors = output / "priors.parquet"
        if not priors.exists():
            con.read_parquet(str(output / "staged/*.parquet")).create_view("staged")
            _write(
                con,
                """WITH anchored AS (
                    SELECT key, anchor_cik AS cik, count(*) AS n FROM staged
                    WHERE anchor_cik IS NOT NULL GROUP BY ALL
                ), frequency AS (
                    SELECT key, count(*) AS mentions FROM staged
                    WHERE key IN (SELECT key FROM anchored) GROUP BY key
                )
                SELECT * FROM anchored JOIN frequency USING (key)""",
                priors,
            )
        con.read_parquet(str(priors)).create("priors")
        con.execute(
            """CREATE TABLE known AS
            SELECT key, cik, source, valid_from, valid_to FROM aliases
            UNION ALL
            SELECT key, cik, 'anchor_alias', NULL, NULL FROM (
                SELECT *, sum(n) OVER (PARTITION BY key) AS total FROM priors
            ) AS p
            WHERE n >= $anchors AND n >= $share * total AND (
                n >= $rate * mentions OR EXISTS (
                    SELECT 1 FROM aliases AS a
                    WHERE a.cik = p.cik AND starts_with(a.key, p.key)
                )
            )""",
            {"anchors": LEARNED_ANCHORS, "share": LEARNED_SHARE, "rate": LEARNED_RATE},
        )
        for unit in units:
            targets = {folder: output / folder / unit.name for folder in folders[1:]}
            if not targets["articles"].exists():
                link_unit(
                    con,
                    output / "staged" / unit.name,
                    smoothing,
                    labels,
                    targets,
                    recover_names,
                )
                typer.echo(f"linked {unit.name}")
    shutil.rmtree(output / "staged", ignore_errors=True)
    typer.echo(f"Wrote: {output}")
