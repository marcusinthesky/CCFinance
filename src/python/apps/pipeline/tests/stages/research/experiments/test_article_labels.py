"""Check coverage denominators, provisional cohort counts and processing ETA."""

import csv
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pipeline.stages.research.experiments.article_labels import (
    REPORT_FILES,
    report_article_labels,
    throughput_estimates,
)


@pytest.mark.unit
@given(
    remaining=st.integers(min_value=1, max_value=1_000_000),
    completed=st.integers(min_value=1, max_value=1000),
    elapsed=st.integers(min_value=1, max_value=3600),
    available=st.integers(min_value=1, max_value=86400),
)
def test_eta_uses_completed_documents_and_reserves_deadline_time(
    remaining: int, completed: int, elapsed: int, available: int
) -> None:
    # Arrange: the elapsed wall time includes both completions and failed attempts.
    now = datetime(2026, 11, 16, 18, tzinfo=UTC)
    deadline = now + timedelta(seconds=available + 1800)

    # Act: project from the completed-document throughput without removing failures.
    result = throughput_estimates(
        remaining + completed,
        {"completed": completed, "failed": 7, "elapsed_seconds": elapsed},
        now=now,
        deadline=deadline,
        reserve_seconds=1800,
    )

    # Assert: required capacity and ETA use the same outstanding document workload.
    assert result["remaining_inference_units"] == remaining
    assert result["available_gpu_seconds"] == available
    assert result["required_inference_units_per_second"] == pytest.approx(
        remaining / available
    )
    assert result["conditional_remaining_seconds"] == pytest.approx(
        remaining * elapsed / completed
    )


@pytest.mark.unit
def test_missing_benchmark_cannot_claim_completion_before_an_expired_deadline() -> None:
    # Arrange: the time budget has expired and no inference has completed.
    now = datetime(2026, 11, 17, 8, tzinfo=UTC)

    # Act: retain the workload without inventing a measured processing rate.
    result = throughput_estimates(
        12,
        {},
        now=now,
        deadline=now - timedelta(hours=1),
        reserve_seconds=1800,
    )

    # Assert: no available time, measured rate or conditional ETA is fabricated.
    assert result["remaining_inference_units"] == 12
    assert result["available_gpu_seconds"] == 0
    assert result["required_inference_units_per_second"] is None
    assert result["conditional_remaining_seconds"] is None
    assert result["conditional_deadline_feasible"] is None


def _cpu_fixture(root: Path) -> tuple[Path, Path]:
    cpu = root / "cpu"
    shard = cpu / "shards" / "00000"
    shard.mkdir(parents=True)
    with duckdb.connect() as connection:
        connection.sql(
            "SELECT 'a-' || y || '-' || n AS article_id, "
            "'d-' || y || '-' || least(n, 41) AS document_id, "
            "(2018 + y)::INTEGER AS publish_year, 'news.example' AS hostname, "
            "1 AS candidate_count, 200 + least(n, 41) AS text_chars, "
            "[]::VARCHAR[] AS quality_flags, "
            "[{'issuer_id': 'top1000:1', "
            "'cased_name_match_count': (n % 2 = 0)::INTEGER, "
            "'tag_match_count': (n = 0)::INTEGER, "
            "'spans': {'title': CASE WHEN n < 2 "
            "THEN [{'source': 'name_alias'}] ELSE [] END, "
            "'body': CASE WHEN n = 1 THEN "
            "[{'source': 'name_alias'}, {'source': 'name_alias'}] ELSE [] END}, "
            "'uncertainty_flags': CASE WHEN n >= 40 THEN [] "
            "ELSE ['shared_alias'] END}] AS candidates "
            "FROM range(5) years(y), range(43) documents(n)"
        ).write_parquet(str(shard / "retained.parquet"))
        connection.sql(
            "SELECT 'excluded' AS article_id, 'x' AS document_id, "
            "NULL::INTEGER AS publish_year, 'news.example' AS hostname, "
            "0 AS candidate_count, 800 AS text_chars, "
            "['unknown_year'] AS quality_flags, "
            "'no_company_candidate' AS exclusion_reason"
        ).write_parquet(str(shard / "excluded.parquet"))
    membership = cpu / "membership.csv"
    membership.write_text(
        "permco,effective_year,link_status\n"
        + "".join(
            f"{issuer},{year},candidate_only\n"
            for issuer in (1, 2)
            for year in range(2018, 2024)
        ),
        encoding="utf-8",
    )
    (cpu / "manifest.json").write_text(
        json.dumps(
            {
                "company_references": {"membership": {"path": str(membership)}},
                "source_files": [{"rows": 216}],
            }
        ),
        encoding="utf-8",
    )
    params = root / "params.yaml"
    params.write_text(
        json.dumps(
            {
                "experiments": {
                    "article_labels": {
                        "deadline_utc": "2026-11-17T05:00:00Z",
                        "model_revision": "1" * 40,
                        "base_revision": "2" * 40,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return cpu, params


@pytest.mark.integration
def test_report_preserves_exclusions_zeros_and_candidate_only_cohorts(
    tmp_path: Path,
) -> None:
    # Arrange: one issuer has 42 texts plus a duplicate per year; another has none.
    cpu, params = _cpu_fixture(tmp_path)
    output = tmp_path / "report"

    # Act: publish a CPU-only report without implying completed inference.
    report_article_labels(cpu, output, params=params)

    # Assert: counts reconcile, eligible zero cells survive and no precision is claimed.
    assert {path.name for path in output.iterdir()} == set(REPORT_FILES)
    metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["population"]["source_records"] == 216
    assert metrics["population"]["retained_records"] == 215
    assert metrics["population"]["excluded_records"] == 1
    assert metrics["population"]["candidate_documents"] == 210
    assert metrics["population"]["undated_records"] == 1
    assert metrics["validation_status"] == "pending_human"
    assert metrics["precision_target_validated"] is False
    assert metrics["capacity"]["observed_inference_units_per_second"] is None
    assert {
        row["evidence_tier"]: row["article_records"]
        for row in metrics["evidence_tiers"]
    } == {
        "any_cased_name": 110,
        "any_publisher_annotation": 5,
        "any_title_name": 10,
        "title_and_cased_name": 5,
        "repeated_body_name": 5,
        "issuer_without_shared_alias_or_ticker": 15,
    }
    with (output / "company_year.csv").open(encoding="utf-8") as handle:
        annual = list(csv.DictReader(handle))
    assert len(annual) == 12
    assert all(
        row["candidate_article_records"] == "43" and row["candidate_documents"] == "42"
        for row in annual
        if row["issuer_id"] == "top1000:1" and row["publish_year"] != "2023"
    )
    assert all(
        row["candidate_documents"] == "0"
        for row in annual
        if row["issuer_id"] == "top1000:2"
    )
    with (output / "cohorts.csv").open(encoding="utf-8") as handle:
        cohorts = list(csv.DictReader(handle))
    assert [row["candidate_companies"] for row in cohorts] == ["1", "0", "0", "0"]
    assert "unvalidated" in (output / "summary.tex").read_text(encoding="utf-8")
    assert r"\begin{tabular}" in (output / "coverage.tex").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        report_article_labels(cpu, output, params=params)


@pytest.mark.integration
def test_benchmark_uses_inference_frame_and_does_not_scale_observed_judgments(
    tmp_path: Path,
) -> None:
    # Arrange: two scored inputs use the measured frame, with two issuers on one input.
    cpu, params = _cpu_fixture(tmp_path)
    census = tmp_path / "census"
    report_article_labels(cpu, census, params=params)
    (cpu / "shards").rename(tmp_path / "saved-shards")
    scores = tmp_path / "scores"
    scores.mkdir()
    (scores / "benchmark.json").write_text(
        json.dumps(
            {
                "frame_documents": 215,
                "frame_unit": "retained_source_records",
                "completed": 2,
                "failed": 1,
                "elapsed_seconds": 400,
                "frame_preparation_seconds": 396,
                "throughput_elapsed_seconds": 4,
                "throughput_completed": 2,
            }
        ),
        encoding="utf-8",
    )
    with duckdb.connect() as connection:
        connection.sql(
            "SELECT * FROM (VALUES ('accepted', 'i-1'), ('accepted', 'i-1'), "
            "('review', 'i-2')) AS rows(status, inference_id)"
        ).write_parquet(str(scores / "predictions.parquet"))
    output = tmp_path / "report"

    # Act: reuse the completed census without reading source indices again.
    report_article_labels(cpu, output, scores=scores, params=params, census=census)

    # Assert: candidate-pair counts stay distinct from inference units and population.
    metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["capacity"]["inference_units"] == 215
    assert metrics["capacity"]["remaining_inference_units"] == 213
    assert metrics["capacity_workload_unit"] == "retained_source_records"
    assert metrics["capacity"]["observed_inference_units_per_second"] == 0.5
    assert metrics["capacity"]["conditional_remaining_seconds"] == 426
    assert metrics["capacity"]["measured_frame_preparation_seconds"] == 396
    assert metrics["observed_judgments"] == [
        {"status": "accepted", "candidate_pairs": 2, "inference_units": 1},
        {"status": "review", "candidate_pairs": 1, "inference_units": 1},
    ]
    assert "Observed scored subset only" in metrics["judgment_counts_scope"]


@pytest.mark.integration
@pytest.mark.parametrize("progress_mtime_ns", [1_000_000_000, 0])
def test_resumed_progress_replaces_stale_summary_until_deadline_finalization(
    tmp_path: Path,
    progress_mtime_ns: int,
) -> None:
    # Arrange: a resumed batch advances the clock and counters after an earlier stop.
    cpu, params = _cpu_fixture(tmp_path)
    census = tmp_path / "census"
    report_article_labels(cpu, census, params=params)
    scores = tmp_path / "scores"
    scores.mkdir()
    summary_path = scores / "summary.json"
    progress_path = scores / "progress.json"
    stale_summary = {
        "requested": 215,
        "frame_documents": 215,
        "frame_unit": "retained_source_records",
        "attempted": 2,
        "completed": 2,
        "context_deferred": 0,
        "unattempted": 213,
        "status": "storage_limited",
        "elapsed_seconds": 104,
        "frame_preparation_seconds": 100,
        "throughput_completed": 2,
        "throughput_elapsed_seconds": 4,
    }
    progress = {
        "requested": 215,
        "attempted": 5,
        "completed": 4,
        "context_deferred": 1,
        "unattempted": 210,
        "elapsed_seconds": 6,
    }
    summary_path.write_text(json.dumps(stale_summary))
    progress_path.write_text(json.dumps(progress))
    os.utime(summary_path, ns=(1_000_000_000, 1_000_000_000))
    os.utime(progress_path, ns=(progress_mtime_ns, progress_mtime_ns))
    active = tmp_path / "active"

    # Act: report the resumed run while its terminal summary still describes a stop.
    report_article_labels(cpu, active, scores=scores, params=params, census=census)

    # Assert: fresh counters and the active clock replace stale status and throughput.
    metrics = json.loads((active / "metrics.json").read_text())
    assert metrics["benchmark_source"] == "progress.json"
    assert metrics["benchmark"] == progress
    assert metrics["capacity"]["completed_inference_units"] == 4
    assert metrics["capacity"]["remaining_inference_units"] == 211
    assert metrics["capacity"]["observed_inference_units_per_second"] == pytest.approx(
        4 / 6
    )
    assert metrics["capacity"]["measured_frame_preparation_seconds"] is None
    assert "active scoring-loop" in metrics["capacity"]["basis"]

    # Arrange: the writer finalizes both files with identical rich deadline metadata.
    final_summary = (
        stale_summary
        | progress
        | {
            "status": "deadline_reached",
            "elapsed_seconds": 106,
            "throughput_completed": 4,
            "throughput_elapsed_seconds": 6,
        }
    )
    summary_path.write_text(json.dumps(final_summary))
    progress_path.write_text(json.dumps(final_summary))
    os.utime(summary_path, ns=(3_000_000_000, 3_000_000_000))
    os.utime(progress_path, ns=(4_000_000_000, 4_000_000_000))
    finalized = tmp_path / "finalized"

    # Act: report the terminal checkpoint after its two atomic metadata writes.
    report_article_labels(cpu, finalized, scores=scores, params=params, census=census)

    # Assert: final status, frame preparation and summary provenance are preserved.
    final_metrics = json.loads((finalized / "metrics.json").read_text())
    assert final_metrics["benchmark_source"] == "summary.json"
    assert final_metrics["benchmark"] == final_summary
    assert final_metrics["capacity"]["measured_frame_preparation_seconds"] == 100
    assert final_metrics["capacity"][
        "observed_inference_units_per_second"
    ] == pytest.approx(4 / 6)
    assert "active scoring-loop" not in final_metrics["capacity"]["basis"]

    # Arrange: only the complete terminal progress snapshot remains available.
    summary_path.unlink()
    progress_only = tmp_path / "progress-only"

    # Act: report terminal progress without inventing a live scoring invocation.
    report_article_labels(
        cpu, progress_only, scores=scores, params=params, census=census
    )

    # Assert: progress-only fallback preserves terminal metadata and throughput basis.
    progress_metrics = json.loads((progress_only / "metrics.json").read_text())
    assert progress_metrics["benchmark_source"] == "progress.json"
    assert progress_metrics["benchmark"] == final_summary
    assert progress_metrics["capacity"]["basis"] == final_metrics["capacity"]["basis"]


@pytest.mark.integration
@pytest.mark.parametrize("threshold", [0.0, 0.9])
def test_production_chunks_keep_source_and_pair_denominators_and_unknowns(
    tmp_path: Path,
    threshold: float,
) -> None:
    # Arrange: committed chunks mix scored, unresolved, long and failed source rows.
    cpu, params = _cpu_fixture(tmp_path)
    census = tmp_path / "census"
    report_article_labels(cpu, census, params=params)
    (cpu / "shards").rename(tmp_path / "saved-shards")
    scores = tmp_path / "production"
    (scores / "chunks").mkdir(parents=True)
    (scores / "progress.json").write_text(
        json.dumps(
            {
                "requested": 215,
                "frame_documents": 215,
                "frame_unit": "retained_source_records",
                "attempted": 5,
                "completed": 3,
                "context_deferred": 1,
                "server_failed": 1,
                "unattempted": 210,
                "elapsed_seconds": 2,
            }
        )
    )
    (scores / "manifest.json").write_text(
        json.dumps(
            {
                "scorer_sha256": "a" * 64,
                "contract_sha256": "b" * 64,
                "rubric": "frozen-test-rubric",
                "config": {"min_probability": threshold, "model": "test-model"},
                "runtime": {"model_revision": "c" * 40},
            }
        )
    )
    records = [
        {
            "article_id": str(index),
            "inference_id": "request-" + str(index),
            "status": status,
            "article_json": json.dumps(
                {
                    "document_id": f"document-{index}",
                    "publish_year": None if index == 0 else 2018,
                }
            ),
            "decision_json": json.dumps(
                {"model_name": "test-model", "companies": companies}
            ),
        }
        for index, (status, companies) in enumerate(
            [
                (
                    "complete",
                    [
                        {
                            "status": "accepted",
                            "issuer_id": "top1000:1",
                            "identity_score": 0.99,
                            "substantive_score": 0.8,
                            "raw_primary_score": 0.95,
                            "primary_score": 0.95,
                            "coverage_score": 0.95,
                        },
                        {
                            "issuer_id": "gh:other",
                            "status": "review",
                            "identity_score": 0.4,
                        },
                    ],
                ),
                (
                    "complete",
                    [{"issuer_id": "top1000:1", "status": "deferred_identity"}],
                ),
                ("too_long", [{"issuer_id": "top1000:1", "status": "too_long"}]),
                (
                    "server_failed",
                    [{"issuer_id": "top1000:1", "status": "server_failed"}],
                ),
            ]
        )
    ]
    fixture = tmp_path / "decisions.json"
    fixture.write_text(json.dumps(records))
    with duckdb.connect() as connection:
        connection.execute(
            "COPY (SELECT * FROM read_json($input)) TO $output (FORMAT PARQUET)",
            {"input": str(fixture), "output": str(scores / "chunks/00000000.parquet")},
        )
    output = tmp_path / "report"

    # Act: summarize committed production decisions while reusing the CPU census.
    report_article_labels(cpu, output, scores=scores, params=params, census=census)

    # Assert: source successes do not masquerade as scored companies or human accuracy.
    metrics = json.loads((output / "metrics.json").read_text())
    production = metrics["production_scoring"]
    assert production["source_records_in_chunks"] == 4
    assert production["source_records_with_scored_companies"] == 1
    assert production["source_records_with_only_deferred_identity"] == 1
    assert production["candidate_pairs_in_chunks"] == 5
    assert production["reported_attempted_source_records"] == 5
    assert production["unattempted_source_records"] == 210
    assert production["source_records_without_committed_decisions"] == 211
    assert metrics["benchmark_source"] == "progress.json"
    assert metrics["benchmark"]["completed"] == 3
    assert "active scoring-loop" in metrics["capacity"]["basis"]
    assert {
        row["status"]: row["candidate_pairs"] for row in metrics["observed_judgments"]
    } == {
        "accepted": 1,
        "review": 1,
        "deferred_identity": 1,
        "too_long": 1,
        "server_failed": 1,
    }
    metadata = metrics["scoring_metadata"]
    assert metadata["model_selection_threshold"] == threshold
    assert metadata["rubric"] == "frozen-test-rubric"
    assert metadata["scorer_sha256"] == "a" * 64
    assert metadata["validation_status"] == "pending_human"
    assert metrics["precision_target_validated"] is False
    distributions = {row["score"]: row for row in metrics["score_distributions"]}
    assert distributions["identity_score"]["observed_candidate_pairs"] == 2
    assert distributions["identity_score"]["at_least_threshold"] == (
        2 if threshold == 0 else 1
    )
    assert distributions["raw_primary_score"]["at_least_threshold"] == 1
    assert (output / "source_statuses.csv").is_file()
    assert (output / "judgments.csv").is_file()
    assert (output / "score_distributions.csv").is_file()
    assert "provisional" in (output / "scoring.tex").read_text()
    with (output / "observed_company_year.csv").open() as stream:
        annual = list(csv.DictReader(stream))
    observed = next(
        row
        for row in annual
        if row["issuer_id"] == "top1000:1" and row["publish_year"] == "2018"
    )
    assert observed["attempted_article_records"] == "3"
    assert observed["pending_article_records"] == "40"
    assert observed["unscorable_article_records"] == "3"
    assert observed["accepted_documents"] == observed["primary_documents"] == "0"
    assert observed["substantive_documents"] == "0"
    unknown_year = next(
        row
        for row in annual
        if row["issuer_id"] == "top1000:1" and row["publish_year"] == ""
    )
    assert (
        unknown_year["accepted_documents"] == unknown_year["primary_documents"] == "1"
    )
    assert unknown_year["pending_article_records"] == ""
    assert unknown_year["substantive_documents"] == ("1" if threshold == 0 else "0")
    gh = next(row for row in annual if row["issuer_id"] == "gh:other")
    assert gh["review_article_records"] == "1"
    assert gh["candidate_article_records"] == gh["pending_article_records"] == ""

    # Arrange: a new production attempt stops before committing any source records.
    (scores / "chunks").rename(tmp_path / "saved-chunks")
    manifest = json.loads((scores / "manifest.json").read_text())
    manifest["storage"] = "compressed-source-record-chunks"
    (scores / "manifest.json").write_text(json.dumps(manifest))
    summary = json.loads((scores / "progress.json").read_text())
    summary.update(attempted=0, completed=0, unattempted=215)
    (scores / "summary.json").write_text(json.dumps(summary))
    (scores / "progress.json").write_text(json.dumps(summary))
    empty = tmp_path / "empty"

    # Act: reuse the same census and summarize the explicitly empty committed scope.
    report_article_labels(cpu, empty, scores=scores, params=params, census=output)

    # Assert: no stale scores survive and every source row remains unattempted.
    empty_metrics = json.loads((empty / "metrics.json").read_text())
    assert empty_metrics["production_scoring"]["source_records_in_chunks"] == 0
    assert empty_metrics["production_scoring"]["unattempted_source_records"] == 215
    assert empty_metrics["observed_judgments"] == []
    assert empty_metrics["benchmark_source"] == "summary.json"

    # Arrange: remove every metadata snapshot while preserving the census.
    (scores / "summary.json").unlink()
    (scores / "progress.json").unlink()

    # Act and Assert: missing progress fails explicitly rather than inventing zeros.
    with pytest.raises(
        FileNotFoundError, match=r"benchmark\.json.*summary\.json.*progress\.json"
    ):
        report_article_labels(
            cpu, tmp_path / "missing", scores=scores, params=params, census=output
        )


@pytest.mark.integration
def test_observed_company_years_deduplicate_text_and_preserve_pending_cohorts(
    tmp_path: Path,
) -> None:
    # Arrange: 42 selected texts per year have duplicate, deferred and pending copies.
    cpu, params = _cpu_fixture(tmp_path)
    census = tmp_path / "census"
    report_article_labels(cpu, census, params=params)
    (cpu / "shards").rename(tmp_path / "saved-shards")
    scores = tmp_path / "production"
    (scores / "chunks").mkdir(parents=True)
    records = []
    for year in range(5):
        for number in range(43):
            if year == 4 and number == 42:
                continue
            deferred = year == 0 and number == 42
            company = {
                "issuer_id": "top1000:1",
                "status": "deferred_identity" if deferred else "accepted",
                "identity_score": None if deferred else 0.99,
                "substantive_score": None if deferred else 0.95,
                "raw_primary_score": None if deferred else 0.8,
            }
            companies = [company]
            if year == number == 0:
                companies.append(company | {"issuer_id": "gh:same-company"})
            records.append(
                {
                    "article_id": f"a-{year}-{number}",
                    "inference_id": f"request-{year}-{number}",
                    "status": "complete",
                    "article_json": json.dumps(
                        {
                            "document_id": f"d-{year}-{min(number, 41)}",
                            "publish_year": 2018 + year,
                        }
                    ),
                    "decision_json": json.dumps({"companies": companies}),
                }
            )
    (scores / "summary.json").write_text(
        json.dumps(
            {
                "requested": 215,
                "frame_documents": 215,
                "completed": 214,
                "attempted": 214,
                "unattempted": 1,
                "elapsed_seconds": 100,
            }
        )
    )
    (scores / "manifest.json").write_text(
        json.dumps(
            {
                "config": {"min_probability": 0.9},
                "storage": "compressed-source-record-chunks",
            }
        )
    )
    fixture = tmp_path / "decisions.json"
    fixture.write_text(json.dumps(records))
    with duckdb.connect() as connection:
        connection.execute(
            "COPY (SELECT * FROM read_json($input)) TO $output (FORMAT PARQUET)",
            {"input": str(fixture), "output": str(scores / "chunks/00000000.parquet")},
        )
    output = tmp_path / "report"

    # Act: build the observed panels using the saved census and committed decisions.
    report_article_labels(cpu, output, scores=scores, params=params, census=census)

    # Assert: exact-text cohorts never count copies, unknowns, or unrostered GH rows.
    with (output / "observed_company_year.csv").open() as stream:
        annual = list(csv.DictReader(stream))
    first = next(
        row
        for row in annual
        if row["issuer_id"] == "top1000:1" and row["publish_year"] == "2018"
    )
    assert first["attempted_article_records"] == "43"
    assert first["accepted_article_records"] == "42"
    assert first["accepted_documents"] == first["substantive_documents"] == "42"
    assert first["primary_documents"] == "0"
    assert first["unscorable_article_records"] == "1"
    last = next(
        row
        for row in annual
        if row["issuer_id"] == "top1000:1" and row["publish_year"] == "2022"
    )
    assert last["pending_article_records"] == "1"
    assert last["documents_without_attempted_copy"] == "0"
    assert all(
        row["accepted_documents"] == "0"
        for row in annual
        if row["issuer_id"] == "top1000:2"
    )
    gh = next(row for row in annual if row["issuer_id"] == "gh:same-company")
    assert gh["eligible_membership"] == "false"
    assert gh["candidate_documents"] == gh["pending_article_records"] == ""
    assert gh["accepted_documents"] == "1"
    with (output / "observed_cohorts.csv").open() as stream:
        cohorts = list(csv.DictReader(stream))
    assert [row["observed_accepted_companies"] for row in cohorts] == [
        "1",
        "0",
        "0",
        "0",
    ]
    assert [row["observed_substantive_companies"] for row in cohorts] == [
        "1",
        "0",
        "0",
        "0",
    ]
    assert all(row["observed_primary_companies"] == "0" for row in cohorts)
    assert all(
        row["cells_with_pending_candidates"]
        == row["cells_with_unscorable_candidates"]
        == "1"
        for row in cohorts
    )
    assert all(row["validation_status"] == "pending_human" for row in cohorts)

    # Arrange: add a committed association to a roster cell with no candidate records.
    invalid = records[0] | {
        "article_id": "invalid",
        "decision_json": json.dumps(
            {
                "companies": [company | {"issuer_id": "top1000:2"}],
            }
        ),
    }
    fixture.write_text(json.dumps([invalid]))
    with duckdb.connect() as connection:
        connection.execute(
            "COPY (SELECT * FROM read_json($input)) TO $output (FORMAT PARQUET)",
            {"input": str(fixture), "output": str(scores / "chunks/00000001.parquet")},
        )

    # Act and Assert: census reconciliation fails instead of reporting negative pending.
    with pytest.raises(ValueError, match="exceed the candidate census"):
        report_article_labels(
            cpu, tmp_path / "invalid", scores=scores, params=params, census=census
        )
