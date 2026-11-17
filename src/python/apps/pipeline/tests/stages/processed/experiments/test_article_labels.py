"""Verify source conservation and safe reuse of the compact CPU selection."""

import hashlib
import json
from pathlib import Path

import duckdb
import pytest
from pipeline.stages.processed.experiments.article_labels import (
    adopt_company_candidates,
    prepare_article_labels,
)


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "source"
    relative = "2020-01/eng_Latn/part-000000.parquet"
    article = source / relative
    article.parent.mkdir(parents=True)
    legacy = tmp_path / "legacy"
    tags = legacy / "shards/00000/part-00000.parquet"
    tags.parent.mkdir(parents=True)
    domains = tmp_path / "domains.csv"
    domains.write_text("domain\nexample.com\n", encoding="utf-8")
    with duckdb.connect() as con:
        con.execute(
            """COPY (SELECT 'duplicate' AS id,
                CASE WHEN n = 3 THEN ' ' ELSE 'Alpha reports profits. ' END AS text,
                {'title': 'Company report',
                 'publish_date': CASE WHEN n = 1 THEN 'unknown' ELSE '2020-01-02' END,
                 'url': 'https://example.com/story',
                 'url_hostname': CASE WHEN n = 4 THEN 'example.com.evil.test'
                                     ELSE 'news.example.com' END} AS metadata
                FROM range(5) x(n)) TO $target (FORMAT PARQUET)""",
            {"target": str(article)},
        )
        con.execute(
            """COPY (SELECT 'row-' || n AS row_key, $relative AS source_path,
                n AS source_row, CASE WHEN n = 1 THEN NULL ELSE 2020 END AS year,
                CASE WHEN n = 1 THEN 'unsupported_year' ELSE 'complete' END
                    AS top1000_coverage,
                CASE WHEN n IN (1, 2) THEN [] ELSE
                    [{'issuer_id': 'top1000:1', 'name': 'Alpha',
                      'cased_name_match_count': 1,
                      'uncertainty_flags': ['provisional']}]
                    END AS top1000_candidates,
                CASE WHEN n = 1 THEN
                    [{'issuer_id': 'gh:0000000001', 'name': 'Alpha',
                      'cased_name_match_count': 1,
                      'uncertainty_flags': ['provisional']}]
                    ELSE [] END AS gh_candidates
                FROM range(5) x(n)) TO $target (FORMAT PARQUET)""",
            {"relative": relative, "target": str(tags)},
        )
    references = {}
    for name in ("membership", "registry", "gh"):
        path = tmp_path / f"{name}.csv"
        path.write_text("key\n1\n", encoding="utf-8")
        references[name] = str(path)
    source_hash = hashlib.sha256(article.read_bytes()).hexdigest()
    (legacy / "manifest.json").write_text(
        json.dumps(
            {
                "config": references,
                "contract_sha256": "legacy-contract",
                "source_population_rows": 5,
                "registry_sha256": {
                    name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                    for name, path in references.items()
                },
                "source_files": [
                    {
                        "index": 0,
                        "relative_path": relative,
                        "sha256": source_hash,
                        "bytes": article.stat().st_size,
                        "rows": 5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (legacy / "summary.json").write_text('{"status": "complete"}', encoding="utf-8")
    (tags.parent / "completed.json").write_text(
        json.dumps(
            {
                "source_index": 0,
                "source_sha256": source_hash,
                "contract_sha256": "legacy-contract",
                "selection": {"first": 0, "last": 5},
                "rows": 5,
                "chunks": [
                    {
                        "file": tags.name,
                        "rows": 5,
                        "sha256": hashlib.sha256(tags.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return source, legacy, domains


@pytest.mark.integration
def test_selection_preserves_uncertain_and_excluded_source_rows(
    corpus: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    # Arrange: adopt a source with duplicate IDs, an uncertain year and no-hit rows.
    source, legacy, domains = corpus
    adopted, output = tmp_path / "adopted", tmp_path / "output"
    adopt_company_candidates(source, legacy, adopted)

    # Act: build compact indices and exact-text duplicate memberships.
    prepare_article_labels(source, adopted, output, domains)

    # Assert: every source row survives in one index; bodies stay in raw storage.
    with duckdb.connect() as con:
        kept = con.execute(
            "SELECT article_id, source_article_id, publish_year, quality_flags, "
            "candidates[1].issuer_id FROM read_parquet(?) ORDER BY source_row",
            [str(output / "shards/00000/retained.parquet")],
        ).fetchall()
        excluded = con.execute(
            "SELECT article_id, exclusion_reason "
            "FROM read_parquet(?) ORDER BY source_row",
            [str(output / "shards/00000/excluded.parquet")],
        ).fetchall()
        membership = con.execute(
            "SELECT count(*), count(DISTINCT article_id), count(DISTINCT document_id) "
            "FROM read_parquet(?)",
            [str(output / "dedup-membership.parquet")],
        ).fetchone()
        columns = con.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)",
            [str(output / "shards/00000/retained.parquet")],
        ).fetchall()
    assert [row[0] for row in kept] == ["row-0", "row-1"]
    assert kept[1][2] is None and "unknown_publication_year" in kept[1][3]
    assert kept[1][4] == "gh:0000000001"
    assert excluded == [
        ("row-2", "no_company_candidate"),
        ("row-3", "empty_text"),
        ("row-4", "publisher_not_allowed"),
    ]
    assert membership == (5, 5, 2)
    assert "text" not in {row[0] for row in columns}
    assert (adopted / "shards/00000/part-00000.parquet").stat().st_ino != (
        legacy / "shards/00000/part-00000.parquet"
    ).stat().st_ino


@pytest.mark.integration
def test_resume_preserves_indices_and_rejects_candidate_corruption(
    corpus: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    # Arrange: freeze a completed compact selection and its candidate snapshot.
    source, legacy, domains = corpus
    adopted, output = tmp_path / "adopted", tmp_path / "output"
    adopt_company_candidates(source, legacy, adopted)
    prepare_article_labels(source, adopted, output, domains)
    retained = output / "shards/00000/retained.parquet"
    before = retained.read_bytes(), retained.stat().st_mtime_ns

    # Act: verify a completed resume, then corrupt its independent adopted input.
    prepare_article_labels(source, adopted, output, domains)
    candidate = adopted / "shards/00000/part-00000.parquet"
    candidate.write_bytes(candidate.read_bytes() + b"corrupt")

    # Assert: resume does not rewrite source indices or accept changed evidence.
    assert (retained.read_bytes(), retained.stat().st_mtime_ns) == before
    with pytest.raises(ValueError, match="checksum differs"):
        prepare_article_labels(source, adopted, output, domains)


@pytest.mark.integration
def test_adoption_rejects_changed_raw_source(
    corpus: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    # Arrange: alter an input after its candidate run was fingerprinted.
    source, legacy, _ = corpus
    article = next(source.glob("**/*.parquet"))
    article.write_bytes(article.read_bytes() + b"changed")
    adopted = tmp_path / "adopted"

    # Act and assert: adoption fails without publishing a partial snapshot.
    with pytest.raises(ValueError, match="Source checksum differs"):
        adopt_company_candidates(source, legacy, adopted)
    assert not adopted.exists()
