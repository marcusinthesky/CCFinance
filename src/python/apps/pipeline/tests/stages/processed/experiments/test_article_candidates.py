"""Protect dated identity resolution and conservation of uncertain evidence."""

import csv
import hashlib
import json
import shutil
from pathlib import Path

import duckdb
import pytest
from pipeline.stages.processed.experiments.article_candidates import (
    correct_article_candidates,
)


@pytest.fixture
def candidates(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    shard = source / "shards/00000"
    shard.mkdir(parents=True)
    references = {}
    tables = {
        "registry": [
            {
                "issuer_key": "PERMCO:1|CIK:0000000001",
                "cik": "0000000001",
                "company_legal_name": "Alpha Mining Inc.",
                "other_names": '["Alpha"]',
            },
            {
                "issuer_key": "PERMCO:1|CIK:0000000002",
                "cik": "0000000002",
                "company_legal_name": "American Airlines Inc.",
                "other_names": '["American Airlines"]',
            },
            {
                "issuer_key": "PERMCO:2|CIK:0000000003",
                "cik": "0000000003",
                "company_legal_name": "Apple Inc.",
                "other_names": '["Apple"]',
            },
            {
                "issuer_key": "PERMCO:3|CIK:0000000004",
                "cik": "0000000004",
                "company_legal_name": "Phillips Edison & Company, Inc.",
                "other_names": "[]",
            },
        ],
        "membership": [
            {
                "effective_year": 2002,
                "permco": 1,
                "cik": "0000000001",
                "issuer_key": "PERMCO:1|CIK:0000000001",
                "link_status": "candidate_only",
                "ticker": "AMR",
            },
            {
                "effective_year": 2021,
                "permco": 1,
                "cik": "0000000002",
                "issuer_key": "PERMCO:1|CIK:0000000002",
                "link_status": "verified",
                "ticker": "AAL",
            },
            {
                "effective_year": 2021,
                "permco": 1,
                "cik": "0000000001",
                "issuer_key": "PERMCO:1|CIK:0000000001",
                "link_status": "candidate_only",
                "ticker": "AMR",
            },
            {
                "effective_year": 2021,
                "permco": 2,
                "cik": "0000000003",
                "issuer_key": "PERMCO:2|CIK:0000000003",
                "link_status": "verified",
                "ticker": "AAPL",
            },
            {
                "effective_year": 2021,
                "permco": 3,
                "cik": "0000000004",
                "issuer_key": "PERMCO:3|CIK:0000000004",
                "link_status": "verified",
                "ticker": "PECO",
            },
        ],
        "gh": [
            {
                "company_legal_name": "Costco Wholesale Corp.",
                "cik": "0000909832",
                "other_names": '["Costco", "PRICE"]',
            }
        ],
    }
    for name, rows in tables.items():
        path = tmp_path / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        references[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    (source / "manifest.json").write_text(
        json.dumps(
            {
                "source_root": str(tmp_path / "raw"),
                "company_references": references,
            }
        ),
        encoding="utf-8",
    )
    (source / "summary.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "source_rows": 6,
                "retained_rows": 6,
                "excluded_rows": 0,
            }
        ),
        encoding="utf-8",
    )
    records = []
    for index, year, issuer, alias, name, count in (
        (0, 2021, "top1000:1", "american airlines", "Alpha Mining Inc.", 2),
        (1, 2002, "top1000:1", "alpha", "Alpha Mining Inc.", 2),
        (2, 2021, "top1000:2", "apple", "Apple Inc.", 2),
        (3, 2021, "top1000:1", "alpha", "Alpha Mining Inc.", 3),
        (4, 2026, "gh:0000909832", "price", "Costco Wholesale Corp.", 2),
        (
            5,
            2021,
            "top1000:3",
            "phillips edison",
            "Phillips Edison & Company, Inc.",
            2,
        ),
    ):
        span = {"alias": alias, "source": "name_alias"}
        tag_spans: list[dict[str, str]] = []
        records.append(
            {
                "article_id": f"article-{index}",
                "source_path": "part.parquet",
                "source_row": index,
                "publish_year": year,
                "candidate_count": 1,
                "candidates": [
                    {
                        "issuer_id": issuer,
                        "name": name,
                        "ticker": "AMR",
                        "tickers": ["AAL", "AMR"],
                        "identity": {
                            "ciks": ["0000000001", "0000000002"],
                            "issuer_keys": [
                                "PERMCO:1|CIK:0000000001",
                                "PERMCO:1|CIK:0000000002",
                            ],
                            "link_statuses": ["candidate_only", "verified"],
                        },
                        "name_match_count": count,
                        "evidence_sources": ["name_alias"],
                        "spans": {"title": [span], "body": [span], "tag": tag_spans},
                    }
                ],
            }
        )
    path = tmp_path / "records.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    with duckdb.connect() as con:
        con.execute(
            "COPY (SELECT * FROM read_json($input)) TO $target (FORMAT PARQUET)",
            {"input": str(path), "target": str(shard / "retained.parquet")},
        )
    (shard / "completed.json").write_text(
        json.dumps(
            {
                "outputs": {
                    "retained.parquet": hashlib.sha256(
                        (shard / "retained.parquet").read_bytes()
                    ).hexdigest()
                }
            }
        ),
        encoding="utf-8",
    )
    submissions = tmp_path / "submissions"
    submissions.mkdir()
    sec = submissions / "CIK0000909832.json"
    sec.write_text(
        json.dumps(
            {
                "name": "COSTCO WHOLESALE CORP /NEW",
                "formerNames": [
                    {
                        "name": "PRICE/COSTCO INC",
                        "from": "1994-01-05",
                        "to": "1997-01-06",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (submissions / "manifest.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "path": sec.name,
                        "sha256": hashlib.sha256(sec.read_bytes()).hexdigest(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return source, submissions


@pytest.mark.integration
def test_correction_resolves_year_identity_and_preserves_deferred_candidates(
    candidates: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    # Arrange: include a ticker-reuse error, an unverified year and a real brand.
    source, submissions = candidates
    output = tmp_path / "corrected"

    # Act: resolve only verified dated links and retain historical context flags.
    correct_article_candidates(source, output, submissions=submissions)

    # Assert: names follow dated CIKs while all rows and original evidence survive.
    with duckdb.connect() as con:
        rows = con.execute(
            "SELECT article_id,candidates[1],candidate_status "
            "FROM read_parquet(?) ORDER BY source_row",
            [str(output / "shards/00000/retained.parquet")],
        ).fetchall()
    assert len(rows) == 6
    assert rows[0][1]["name"] == "American Airlines Inc."
    assert rows[0][1]["original_name"] == "Alpha Mining Inc."
    assert rows[0][1]["authority_cik"] == "0000000002"
    assert rows[0][1]["ticker"] == "AAL"
    assert rows[0][1]["tickers"] == ["AAL"]
    assert rows[0][1]["identity"] == {
        "ciks": ["0000000002"],
        "issuer_keys": ["PERMCO:1|CIK:0000000002"],
        "link_statuses": ["verified"],
    }
    assert rows[0][1]["original_ticker"] == "AMR"
    assert rows[0][1]["original_tickers"] == ["AAL", "AMR"]
    assert rows[0][1]["original_identity"]["ciks"] == [
        "0000000001",
        "0000000002",
    ]
    assert rows[0][2] == rows[2][2] == "primary_discovery"
    assert rows[1][1]["name"] is None
    assert rows[1][2] == "deferred"
    assert rows[3][1]["name_evidence_censored"]
    assert not rows[3][1]["supported_aliases"]
    assert "single_token_alias" in rows[2][1]["ambiguity_flags"]
    assert "outside_observed_former_name_period" in rows[4][1]["ambiguity_flags"]
    assert rows[4][1]["supported_aliases"] == ["price"]
    assert rows[4][1]["spans"]["body"][0]["alias"] == "price"
    assert rows[5][2] == "primary_discovery"
    assert rows[5][1]["supported_aliases"] == ["phillips edison"]
    assert rows[5][1]["alias_provenance"][0]["origins"] == ["legal_name_root"]


@pytest.mark.integration
@pytest.mark.parametrize(
    "artifact", ["catalog.parquet", "shards/00000/retained.parquet"]
)
def test_resume_verifies_corrected_outputs_without_rewriting_shards(
    candidates: tuple[Path, Path],
    tmp_path: Path,
    artifact: str,
) -> None:
    # Arrange: freeze corrected output and its modification time.
    source, submissions = candidates
    output = tmp_path / "corrected"
    relocated = tmp_path / "relocated"
    relocated.mkdir()
    for reference in json.loads((source / "manifest.json").read_text())[
        "company_references"
    ].values():
        shutil.move(reference["path"], relocated)
    correct_article_candidates(
        source, output, submissions=submissions, references=relocated
    )
    path = output / artifact
    path.chmod(0o444)
    before = path.stat().st_mtime_ns

    # Act: verify a completed resume and then alter the output bytes.
    correct_article_candidates(
        source, output, submissions=submissions, references=relocated
    )
    after_resume = path.stat().st_mtime_ns
    path.chmod(0o644)
    path.write_bytes(path.read_bytes() + b"corrupt")

    # Assert: unchanged shards were reused and corruption is rejected.
    assert after_resume == before
    with pytest.raises(ValueError, match="differs"):
        correct_article_candidates(
            source, output, submissions=submissions, references=relocated
        )
