"""Verify bounded source projections against native local Parquet layouts."""

from pathlib import Path

import duckdb
import pytest
from pipeline.stages.raw.publishers import extract_group


@pytest.mark.integration
@pytest.mark.parametrize(
    ("dataset", "projection", "english_rows", "expected_rows"),
    [
        (
            "fine_news",
            """text, i::VARCHAR AS id,
                struct_pack(url, url_hostname, title := 'headline') AS metadata,
                ['excluded media'] AS media""",
            4,
            [1, 3, 4],
        ),
        (
            "infini_news",
            """text, url, url_hostname, i::VARCHAR AS warc_record_id,
                'crawl.warc.gz' AS warc_filename, '2020-01-01' AS warc_date,
                '2020-01-01' AS publish_date, 'headline' AS title,
                'reporter' AS author, 'publisher' AS sitename,
                ['finance'] AS categories, ['markets'] AS tags,
                'description' AS description,
                CASE WHEN i = 4 THEN 'fra_Latn' ELSE 'eng_Latn' END AS language,
                0.9 AS language_score""",
            3,
            [1, 3],
        ),
        (
            "refinedweb",
            """text AS content, url, '2020-01-01' AS timestamp,
                'CC-MAIN-2020-05' AS dump, 'segment' AS segment,
                ['excluded image'] AS image_urls""",
            4,
            [1, 3, 4],
        ),
        (
            "fineweb_hq",
            """text, i::VARCHAR AS id, url, '2020-01-01' AS date,
                'CC-MAIN-2020-05' AS dump, 'source.warc.gz' AS file_path,
                CASE WHEN i = 4 THEN 'fr' ELSE 'en' END AS language,
                0.9 AS language_score, 10 AS token_count, 0.8 AS quality_score,
                [[0.5, 0.4]] AS embeddings""",
            3,
            [1, 3],
        ),
    ],
    ids=["fine_news", "infini_news", "refinedweb", "fineweb_hq"],
)
def test_group_preserves_native_metadata_and_source_rows(
    tmp_path: Path,
    dataset: str,
    projection: str,
    english_rows: int,
    expected_rows: list[int],
) -> None:
    # Arrange: each native layout contains excluded rows around the interval.
    source = tmp_path / "source.parquet"
    target = tmp_path / "articles.parquet"
    domains = tmp_path / "domains.csv"
    domains.write_text("domain\nEXAMPLE.COM.\n", encoding="utf-8")
    with duckdb.connect() as con:
        con.execute(
            f"""COPY (
                WITH native AS (
                    SELECT i, 'article-' || i AS text,
                        CASE WHEN i = 2 THEN 'https://notexample.com/a'
                            ELSE 'https://News.Example.COM./a' END AS url,
                        CASE WHEN i = 2 THEN 'notexample.com'
                            WHEN i = 3 THEN ''
                            ELSE 'News.Example.COM.' END AS url_hostname
                    FROM range(6) AS rows(i)
                ) SELECT {projection} FROM native
            ) TO $target (FORMAT PARQUET)""",  # noqa: S608 - fixed test cases.
            {"target": str(source)},
        )

        # Act: materialize and filter exactly rows one through four.
        counts = extract_group(con, dataset, str(source), 1, 5, domains, target)
        result = con.execute(
            "SELECT text, id, metadata.url, source_file, source_row "
            "FROM read_parquet(?) ORDER BY source_row",
            [str(target)],
        ).fetchall()
        columns = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(target)])
        column_names = [row[0] for row in columns.fetchall()]

    # Assert: language filtering, counts, payload and provenance agree.
    assert counts == {
        "input_rows": 4,
        "english_rows": english_rows,
        "matched_rows": len(expected_rows),
    }
    assert result == [
        (
            f"article-{i}",
            None if dataset == "refinedweb" else str(i),
            "https://News.Example.COM./a",
            str(source),
            i,
        )
        for i in expected_rows
    ]
    assert column_names == ["text", "id", "metadata", "source_file", "source_row"]
