"""Join canonical dated articles to the Kazinnik bank-group crosswalk."""

from pathlib import Path
from typing import Annotated

import duckdb
import typer


def prepare_kazinnik_banks(
    articles: Annotated[Path, typer.Option(help="Canonical article catalog.")],
    links: Annotated[Path, typer.Option(help="Article-level company links directory.")],
    source: Annotated[
        Path, typer.Option(help="Raw Fine News shards by capture month.")
    ],
    issuers: Annotated[Path, typer.Option(help="Prepared issuer catalog.")],
    inputs: Annotated[Path, typer.Option(help="Roster, crosswalk and windows.")],
    output: Annotated[Path, typer.Option(help="Output directory.")],
) -> None:
    """Write one row per article and bank, with publication and capture coverage."""
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={"threads": 4}) as con:
        con.execute(
            """CREATE TABLE eligible AS
            SELECT a.*, strftime(captured, '%Y-%m') AS capture_month
            FROM read_parquet($articles) a
            WHERE usable AND EXISTS (
                SELECT 1 FROM read_csv($windows) w
                WHERE a.published BETWEEN w.starts_on AND w.ends_on
            )""",
            {"articles": str(articles), "windows": str(inputs / "windows.csv")},
        )
        con.execute(
            """CREATE TABLE crosswalk AS
            SELECT * FROM read_csv($crosswalk, types={
                'cik': 'BIGINT', 'valid_from': 'DATE', 'valid_through': 'DATE'
            })""",
            {"crosswalk": str(inputs / "crosswalk.csv")},
        )
        invalid = con.execute(
            """SELECT x.bank, x.cik FROM crosswalk x
            ANTI JOIN read_parquet($issuers) i USING (cik)
            UNION ALL
            SELECT x.bank, x.cik FROM crosswalk x
            ANTI JOIN read_csv($roster) r USING (bank)
            UNION ALL
            SELECT x.bank, x.cik FROM crosswalk x
            WHERE x.valid_from > x.valid_through
            UNION ALL
            SELECT x.bank, x.cik FROM crosswalk x JOIN crosswalk y ON (
                x.rowid < y.rowid AND x.cik = y.cik
                AND x.valid_from <= y.valid_through AND y.valid_from <= x.valid_through
            )""",
            {"issuers": str(issuers), "roster": str(inputs / "roster.csv")},
        ).fetchall()
        if invalid:
            message = f"Invalid or conflicting bank mappings: {invalid}"
            raise ValueError(message)
        months = [
            month
            for (month,) in con.execute(
                "SELECT DISTINCT capture_month FROM eligible ORDER BY capture_month"
            ).fetchall()
        ]
        if not months:
            message = "No eligible articles in the study windows"
            raise ValueError(message)

        # Shards are keyed by capture, while eligibility is keyed by publication.
        link_paths = [str(links / f"{month}--*.parquet") for month in months]
        raw_paths = [str(source / month / "*" / "*.parquet") for month in months]
        con.execute(
            """CREATE TABLE linked AS
            SELECT l.id, l.cik, l.ticker, l.link_score, l.n_mentions, l.evidence,
                   a.published
            FROM read_parquet($links) l JOIN eligible a USING (id)""",
            {"links": link_paths},
        )
        con.execute(
            """CREATE TABLE bridge AS
            WITH mapped AS (
                SELECT l.id, x.bank, x.scope, struct_pack(
                    cik := l.cik, ticker := l.ticker, scope := x.scope,
                    mapping_evidence := x.evidence, link_score := l.link_score,
                    n_mentions := l.n_mentions, spans := l.evidence
                ) AS link
                FROM linked l JOIN crosswalk x ON (
                    x.cik = l.cik
                    AND l.published BETWEEN x.valid_from AND x.valid_through
                )
            )
            SELECT id, bank, list(DISTINCT link ORDER BY link) AS bank_links,
                   bool_or(scope <> 'foreign_parent') AS directly_mapped
            FROM mapped GROUP BY id, bank""",
        )
        con.execute(
            """CREATE TABLE headlines AS
            SELECT r.id, r.metadata.title AS headline, r.metadata.url AS url,
                   r.metadata.author AS author,
                   r.metadata.minhash_cluster_id AS minhash_cluster_id,
                   r.metadata.text_xxhash64 AS text_hash
            FROM read_parquet($raw) r
            SEMI JOIN bridge b USING (id)""",
            {"raw": raw_paths},
        )
        problems = con.execute(
            """SELECT b.id
            FROM (SELECT DISTINCT id FROM bridge) b LEFT JOIN headlines h USING (id)
            GROUP BY b.id HAVING count(h.id) <> 1 LIMIT 5""",
        ).fetchall()
        if problems:
            message = f"Missing or ambiguous raw metadata for bank articles: {problems}"
            raise ValueError(message)
        con.execute(
            """COPY (
                SELECT b.*, a.published, a.capture_month, a.host AS publisher,
                       a.article_form, a.copies,
                       h.headline, h.url, h.author, h.minhash_cluster_id, h.text_hash,
                       nullif(trim(regexp_replace(lower(h.headline),
                           '[^\\p{L}\\p{N}]+', ' ', 'g')), '') AS normalized_headline
                FROM bridge b JOIN eligible a USING (id) JOIN headlines h USING (id)
                ORDER BY a.published, b.id, b.bank
            ) TO $path (FORMAT PARQUET)""",
            {"path": str(output / "article_banks.parquet")},
        )
        con.execute(
            """COPY (
                SELECT w.study_window, a.capture_month, a.extraction_status,
                       count(*) AS usable_articles,
                       count(l.id) AS linked_articles, count(b.id) AS bank_articles
                FROM eligible a
                JOIN read_csv($windows) w
                    ON a.published BETWEEN w.starts_on AND w.ends_on
                LEFT JOIN (SELECT DISTINCT id FROM linked) l USING (id)
                LEFT JOIN (SELECT DISTINCT id FROM bridge) b USING (id)
                GROUP BY ALL ORDER BY ALL
            ) TO $path (FORMAT CSV, HEADER TRUE)""",
            {
                "windows": str(inputs / "windows.csv"),
                "path": str(output / "coverage.csv"),
            },
        )
