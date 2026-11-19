"""Build the firm-year coverage panel over a declared universe of listed issuers.

Counts follow the article funnel for each issuer and year:

- ``raw``: articles linked at the operating score, by their linker date.
- ``dated``: of those, articles whose capture confirms the publication date.
- ``usable``: dated and canonical (not a repeat of an earlier capture).
- ``focused``: usable and meeting the company-focus rule.

Press releases, self-published articles, distinct publishers and syndication
copies are counted among usable articles.

Issuer listings rarely carry start dates, so an issuer-year joins the universe
on one of two kinds of evidence: a dated listing covering the year, or a
current listing of unknown start together with a public float measured in the
year or the year before. Zero counts are kept for universe members. Linked
issuer-years outside the universe (mostly foreign private issuers, which report
no public float) stay in the panel, flagged, so totals still reconcile.

Size bands are public-float quantiles within each year, among universe members
with a float measured in that year or the year before. Pricing Perspective
roster tickers map to issuers listed during 2018-2022; a roster CIK overrides
the match.
"""

import json
from pathlib import Path
from typing import Annotated

import duckdb
import typer

# SIC divisions by two-digit major group.
DIVISIONS = (
    (1, 9, "Agriculture"),
    (10, 14, "Mining"),
    (15, 17, "Construction"),
    (20, 39, "Manufacturing"),
    (40, 49, "Transport and utilities"),
    (50, 51, "Wholesale"),
    (52, 59, "Retail"),
    (60, 67, "Finance"),
    (70, 89, "Services"),
    (91, 99, "Public administration"),
)
ROSTER_YEARS = (2018, 2022)


def _division_sql(column: str) -> str:
    cases = " ".join(
        f"WHEN try_cast(left({column}, 2) AS INTEGER) BETWEEN {low} AND {high} "
        f"THEN '{name}'"
        for low, high, name in DIVISIONS
    )
    return f"CASE {cases} ELSE 'Unknown' END"


def build_coverage_panel(
    articles: Annotated[Path, typer.Option(help="Prepared article table.")] = Path(
        "data/processed/articles"
    ),
    links: Annotated[Path, typer.Option(help="Linker output.")] = Path(
        "data/processed/company-links"
    ),
    issuers: Annotated[Path, typer.Option(help="Prepared issuer tables.")] = Path(
        "data/processed/issuers"
    ),
    public_float: Annotated[Path, typer.Option(help="Public-float table.")] = Path(
        "data/processed/public-float"
    ),
    roster: Annotated[Path, typer.Option(help="Pricing Perspective roster.")] = Path(
        "data/inputs/coverage/pricing-perspective.csv"
    ),
    threshold: Annotated[float, typer.Option(help="Operating link score.")] = 0.5,
    min_relevance: Annotated[float, typer.Option(help="Focus rule.")] = 0.0,
    max_offset: Annotated[float, typer.Option(help="Focus rule.")] = 1.0,
    min_mentions: Annotated[int, typer.Option(help="Focus rule.")] = 3,
    first_year: Annotated[int, typer.Option(help="First panel year.")] = 2016,
    last_year: Annotated[int, typer.Option(help="Last panel year.")] = 2026,
    complete_from: Annotated[int, typer.Option(help="First full year.")] = 2017,
    complete_through: Annotated[int, typer.Option(help="Last full year.")] = 2025,
    size_bands: Annotated[int, typer.Option(help="Public-float quantiles.")] = 5,
    output: Annotated[Path, typer.Option(help="Output directory.")] = Path(
        "data/research/coverage"
    ),
) -> None:
    """Write the firm-year panel, the mapped roster and a summary."""
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.read_parquet(str(issuers / "issuers.parquet")).create("issuers")
        con.read_parquet(str(issuers / "tickers.parquet")).create("tickers")
        con.read_parquet(str(public_float / "public_float.parquet")).create("float")
        con.execute(
            "CREATE TABLE years AS SELECT range::INTEGER AS year FROM range(?, ?)",
            [first_year, last_year + 1],
        )
        con.execute(
            """CREATE TABLE counts AS
            SELECT l.cik, year(l.day)::INTEGER AS year,
                count(*) AS raw,
                count(*) FILTER (WHERE a.date_status = 'consistent') AS dated,
                count(*) FILTER (WHERE a.usable) AS usable,
                count(*) FILTER (WHERE a.usable
                    AND l.relevance_substantive >= $relevance
                    AND l.first_offset_share <= $offset
                    AND l.n_mentions >= $mentions) AS focused,
                count(*) FILTER (WHERE a.usable
                    AND a.article_form = 'press release') AS press_releases,
                count(*) FILTER (WHERE a.usable AND l.self_publisher)
                    AS self_published,
                count(DISTINCT a.host) FILTER (WHERE a.usable) AS publishers,
                coalesce(sum(a.copies) FILTER (WHERE a.usable), 0) AS copies
            FROM read_parquet($links) AS l
            JOIN read_parquet($articles) AS a USING (id)
            WHERE l.link_score >= $threshold
            GROUP BY ALL""",
            {
                "links": str(links / "articles" / "*.parquet"),
                "articles": str(articles / "articles.parquet"),
                "threshold": threshold,
                "relevance": min_relevance,
                "offset": max_offset,
                "mentions": min_mentions,
            },
        )
        con.execute(
            """CREATE TABLE sizes AS
            WITH yearly AS (
                SELECT cik, year(measured)::INTEGER AS year,
                       arg_max(value_usd, measured) AS value_usd,
                       max(measured) AS measured
                FROM float GROUP BY ALL
            )
            SELECT y.year, f.cik,
                   arg_max(f.value_usd, f.measured) AS float_usd,
                   max(f.measured) AS float_measured
            FROM years AS y JOIN yearly AS f ON f.year BETWEEN y.year - 1 AND y.year
            GROUP BY ALL"""
        )
        con.execute(
            """CREATE TABLE universe AS
            SELECT t.cik, y.year,
                   CASE WHEN bool_or(year(t.valid_from) <= y.year) THEN 'dated'
                        ELSE 'float' END AS basis
            FROM tickers AS t CROSS JOIN years AS y
            LEFT JOIN sizes AS s ON s.cik = t.cik AND s.year = y.year
            WHERE (t.valid_to IS NULL OR year(t.valid_to) >= y.year)
              AND (year(t.valid_from) <= y.year
                   OR (t.valid_from IS NULL AND s.cik IS NOT NULL))
            GROUP BY ALL"""
        )
        division = _division_sql("i.sic")
        con.execute(
            f"""CREATE TABLE panel AS
            WITH members AS (
                SELECT cik, year FROM universe
                UNION
                SELECT cik, year FROM counts
                WHERE year BETWEEN $first AND $last
            ), banded AS (
                SELECT s.year, s.cik, s.float_usd, s.float_measured,
                       ntile($bands) OVER (PARTITION BY s.year
                                           ORDER BY s.float_usd) AS size_band
                FROM sizes AS s JOIN universe AS u USING (cik, year)
            )
            SELECT m.cik, m.year, i.name, i.sic, {division} AS division,
                   u.cik IS NOT NULL AS in_universe, u.basis,
                   b.float_usd, b.float_measured, b.size_band,
                   m.year NOT BETWEEN $complete_from AND $complete_through
                       AS partial_year,
                   coalesce(c.raw, 0) AS raw, coalesce(c.dated, 0) AS dated,
                   coalesce(c.usable, 0) AS usable,
                   coalesce(c.focused, 0) AS focused,
                   coalesce(c.press_releases, 0) AS press_releases,
                   coalesce(c.self_published, 0) AS self_published,
                   coalesce(c.publishers, 0) AS publishers,
                   coalesce(c.copies, 0) AS copies
            FROM members AS m
            LEFT JOIN universe AS u USING (cik, year)
            LEFT JOIN counts AS c USING (cik, year)
            LEFT JOIN banded AS b USING (cik, year)
            LEFT JOIN issuers AS i USING (cik)
            ORDER BY m.cik, m.year""",  # noqa: S608 - authored constants.
            {
                "first": first_year,
                "last": last_year,
                "bands": size_bands,
                "complete_from": complete_from,
                "complete_through": complete_through,
            },
        )
        con.execute(
            """CREATE TABLE roster AS
            WITH authored AS (
                SELECT row_number() OVER () AS position, upper(trim(ticker)) AS ticker,
                       name, try_cast(cik AS BIGINT) AS cik
                FROM read_csv($roster, all_varchar = true)
            ), candidates AS (
                SELECT a.position, t.cik, t.exchange, t.source
                FROM authored AS a JOIN tickers AS t
                  ON replace(t.ticker, '.', '-') = replace(a.ticker, '.', '-')
                 AND (t.valid_from IS NULL OR t.valid_from <= make_date($last, 12, 31))
                 AND (t.valid_to IS NULL OR t.valid_to >= make_date($first, 1, 1))
            ), chosen AS (
                SELECT position, count(DISTINCT cik) AS options,
                       first(cik ORDER BY exchange = 'Nasdaq' DESC, source = 'sec' DESC,
                             cik) AS cik
                FROM candidates GROUP BY position
            )
            SELECT a.ticker, a.name, coalesce(a.cik, c.cik) AS cik,
                   CASE WHEN a.cik IS NOT NULL THEN 'override'
                        WHEN c.cik IS NULL THEN 'unmatched'
                        WHEN c.options > 1 THEN 'ambiguous'
                        ELSE 'matched' END AS status
            FROM authored AS a LEFT JOIN chosen AS c USING (position)
            ORDER BY a.position""",
            {
                "roster": str(roster),
                "first": ROSTER_YEARS[0],
                "last": ROSTER_YEARS[1],
            },
        )
        con.table("panel").write_parquet(
            str(output / "panel.parquet"), compression="zstd"
        )
        con.table("roster").write_parquet(
            str(output / "pp_roster.parquet"), compression="zstd"
        )
        totals = con.sql(
            "SELECT count(*), count(*) FILTER (WHERE in_universe), "
            "count(*) FILTER (WHERE basis = 'dated'), "
            "count(*) FILTER (WHERE basis = 'float'), "
            "sum(raw), sum(usable), sum(focused) FROM panel"
        ).fetchall()[0]
        statuses = dict(
            con.sql("SELECT status, count(*) FROM roster GROUP BY 1").fetchall()
        )
    summary = {
        "issuer_years": totals[0],
        "universe_issuer_years": totals[1],
        "universe_basis": {"dated": totals[2], "float": totals[3]},
        "raw": totals[4],
        "usable": totals[5],
        "focused": totals[6],
        "roster": statuses,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    typer.echo(f"Wrote: {output}")
