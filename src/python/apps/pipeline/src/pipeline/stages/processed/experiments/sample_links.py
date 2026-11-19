"""Draw the independent company-link evaluation samples."""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

import duckdb
import typer

from pipeline.stages.processed.company_links import row_group
from pipeline.stages.processed.issuers import normalize

SPLIT = "CASE WHEN sha256($seed || ':split:' || id) < '8' THEN 'dev' ELSE 'test' END"
STRATA = """
CASE coalesce(matches, 0) WHEN 0 THEN 'none' WHEN 1 THEN 'one' ELSE 'several' END
|| ':' || CASE WHEN frequency >= 1000 THEN 'head'
               WHEN frequency >= 10 THEN 'torso' ELSE 'tail' END
"""


def _context(con: duckdb.DuckDBPyConnection, source: Path, table: str) -> None:
    """Attach title, date, publisher and text from each sampled row group."""
    con.execute(
        "CREATE TABLE texts (id VARCHAR, title VARCHAR, day DATE, host VARCHAR, "
        "text VARCHAR)"
    )
    units = con.sql(f"SELECT DISTINCT unit FROM {table}").fetchall()  # noqa: S608
    for (unit,) in units:
        stem, group = Path(unit).stem.rsplit("--", 1)
        raw = source / (stem.replace("--", "/") + ".parquet")
        first, stop = row_group(con, raw, int(group))
        con.execute(
            f"""INSERT INTO texts
            SELECT id, metadata.title,
                   coalesce(try_cast(left(metadata.publish_date, 10) AS DATE),
                            metadata.warc_date::DATE),
                   metadata.url_hostname, text
            FROM read_parquet($raw, file_row_number = true)
            WHERE file_row_number >= $first AND file_row_number < $stop
              AND id IN (SELECT id FROM {table} WHERE unit = $unit)""",  # noqa: S608
            {"raw": str(raw), "first": first, "stop": stop, "unit": unit},
        )


def sample_links(
    extraction: Annotated[
        Path, typer.Option(help="GLiNER output with mentions/.")
    ] = Path("data/processed/article-metadata"),
    issuers: Annotated[Path, typer.Option(help="Prepared issuer tables.")] = Path(
        "data/processed/issuers"
    ),
    source: Annotated[Path, typer.Option(help="Raw Fine News shards.")] = Path(
        "data/raw/fine-news"
    ),
    per_stratum: Annotated[int, typer.Option(help="Mentions per stratum.")] = 100,
    articles: Annotated[int, typer.Option(help="Articles for recall.")] = 300,
    window: Annotated[int, typer.Option(help="Context characters per side.")] = 750,
    seed: Annotated[int, typer.Option(help="Sampling seed.")] = 42,
    output: Annotated[Path, typer.Option(help="New sample directory.")] = Path(
        "data/processed/experiments/company-links/sample"
    ),
) -> None:
    """Draw stratified company mentions and uniform articles with context."""
    output.mkdir(parents=True, exist_ok=False)
    with TemporaryDirectory(dir=output.parent) as spill, duckdb.connect() as con:
        con.execute("SET TimeZone = 'UTC'")
        # Bounded memory over ~100M mentions: top-k aggregates, spilling if needed.
        con.execute("SET memory_limit = '4GB'")
        con.execute("SET temp_directory = ?", [spill])
        con.create_function("normalize_name", normalize, ["VARCHAR"], "VARCHAR")
        con.read_parquet(str(extraction / "mentions/*.parquet"), filename=True).filter(
            "entity_type = 'company'"
        ).create_view("mentions")
        con.read_parquet(str(issuers / "aliases.parquet")).create_view("aliases")
        con.execute(
            """CREATE TABLE keys AS
            SELECT text, normalize_name(text) AS key
            FROM (SELECT DISTINCT text FROM mentions)"""
        )
        con.execute(
            f"""CREATE TABLE drawn_mentions AS
            WITH keyed AS (
                SELECT m.id, m.start, k.key
                FROM mentions AS m JOIN keys AS k USING (text)
            ), frequencies AS (
                SELECT key, count(*) AS frequency FROM keyed GROUP BY key
            ), matches AS (
                SELECT key, count(DISTINCT cik) AS matches FROM aliases GROUP BY key
            ), strata AS (
                SELECT id, start, key, {STRATA} AS stratum,
                       sha256($seed || ':' || id || ':' || start) AS priority
                FROM keyed JOIN frequencies USING (key) LEFT JOIN matches USING (key)
            ), drawn AS (
                SELECT stratum, count(*) AS population,
                       min_by({{'id': id, 'start': start, 'key': key}}, priority,
                              $per_stratum) AS rows
                FROM strata GROUP BY stratum
            )
            SELECT stratum, population, unnest(rows, recursive := true) FROM drawn""",  # noqa: S608 - authored strata expression.
            {"seed": str(seed), "per_stratum": per_stratum},
        )
        con.execute(
            f"""CREATE TABLE sampled AS
            SELECT *, {SPLIT} AS split FROM (
                SELECT d.id, d.start, max(m.stop) AS stop,
                       arg_max(m.text, m.stop) AS text, d.key, d.stratum,
                       d.population,
                       any_value(regexp_extract(m.filename, '[^/]+$')) AS unit
                FROM mentions AS m JOIN drawn_mentions AS d USING (id, start)
                GROUP BY d.id, d.start, d.key, d.stratum, d.population
            )""",  # noqa: S608
            {"seed": str(seed)},
        )
        con.execute(
            f"""CREATE TABLE drawn AS
            WITH ids AS (
                SELECT id, any_value(regexp_extract(filename, '[^/]+$')) AS unit
                FROM mentions GROUP BY id
            ), drawn AS (
                SELECT min_by({{'id': id, 'unit': unit}}, sha256($seed || ':' || id),
                              $articles) AS rows
                FROM ids
            )
            SELECT *, {SPLIT} AS split
            FROM (SELECT unnest(rows, recursive := true) FROM drawn)""",  # noqa: S608
            {"seed": str(seed), "articles": articles},
        )
        _context(con, source, "sampled")
        con.execute(
            """COPY (
                SELECT s.* EXCLUDE (unit), count(*) OVER (PARTITION BY stratum)
                       AS sampled, t.title, t.day, t.host,
                       substr(t.text, greatest(1, s.start + 1 - $window),
                              s.start - greatest(0, s.start - $window))
                       || '⟦' || substr(t.text, s.start + 1, s.stop - s.start)
                       || '⟧' || substr(t.text, s.stop + 1, $window) AS excerpt
                FROM sampled AS s JOIN texts AS t USING (id)
            ) TO $target (FORMAT PARQUET)""",
            {"window": window, "target": str(output / "mentions.parquet")},
        )
        con.execute("DROP TABLE texts")
        _context(con, source, "drawn")
        con.execute(
            """COPY (
                SELECT t.id, drawn.split, t.title, t.day, t.host,
                       left(t.text, 12000) AS text,
                       length(t.text) > 12000 AS truncated
                FROM texts AS t JOIN drawn USING (id)
            ) TO $target (FORMAT PARQUET)""",
            {"target": str(output / "articles.parquet")},
        )
    typer.echo(f"Wrote: {output}")
