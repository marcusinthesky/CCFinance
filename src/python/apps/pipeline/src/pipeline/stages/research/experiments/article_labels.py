"""Report observed article-label coverage and conditional processing capacity."""

import csv
import json
import math
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

import duckdb
import typer
from pydantic import JsonValue, TypeAdapter
from statsmodels.iolib.summary import Summary
from statsmodels.iolib.table import SimpleTable

from pipeline.experiments.article_labels import ArticleLabelsConfig, load_config

REPORT_FILES = (
    "metrics.json",
    "methods.json",
    "year_publisher.csv",
    "distributions.csv",
    "evidence_tiers.csv",
    "company_year.csv",
    "cohorts.csv",
    "summary.tex",
    "coverage.tex",
    "throughput.tex",
)
EVIDENCE_DEFINITIONS: dict[str, JsonValue] = {
    "any_cased_name": (
        "Legacy cased-name counter > 0; absence of the lowercase_single_token flag "
        "does not ensure capitalization of multiword aliases"
    ),
    "any_publisher_annotation": (
        "At least one candidate has a publisher metadata tag match"
    ),
    "any_title_name": "At least one stored title span is a name alias",
    "title_and_cased_name": (
        "The same candidate has a stored title name span and a positive legacy "
        "cased-name counter anywhere in the article"
    ),
    "repeated_body_name": (
        "At least two stored body spans for the same candidate are name aliases; "
        "legacy example spans are capped at four per field"
    ),
    "issuer_without_shared_alias_or_ticker": (
        "At least one candidate lacks shared_alias and shared_ticker flags; "
        "other uncertainty flags may remain"
    ),
}


def _read_json(path: Path) -> dict[str, JsonValue]:
    return TypeAdapter(dict[str, JsonValue]).validate_json(
        path.read_text(encoding="utf-8")
    )


def _number(values: dict[str, JsonValue], key: str) -> float | None:
    value = values.get(key)
    return (
        float(value)
        if isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        else None
    )


def throughput_estimates(
    population: int,
    benchmark: dict[str, JsonValue],
    *,
    now: datetime,
    deadline: datetime,
    reserve_seconds: int,
) -> dict[str, JsonValue]:
    """Estimate remaining capacity from completed inference inputs and wall time.

    A benchmark rate is conditional on its selected documents and operating
    conditions. Failed inputs remain outstanding, rather than disappearing
    from the denominator. No benchmark means no measured rate or completion ETA.
    """
    if population < 0 or reserve_seconds < 0:
        raise ValueError("Population and reserved seconds must be nonnegative")
    if now.tzinfo is None or deadline.tzinfo is None:
        raise ValueError("Capacity timestamps must include a timezone")
    completed = _number(benchmark, "completed") or 0.0
    measured_completed = _number(benchmark, "throughput_completed")
    if measured_completed is None:
        measured_completed = completed
    elapsed = _number(benchmark, "throughput_elapsed_seconds")
    if elapsed is None:
        elapsed = _number(benchmark, "elapsed_seconds")
    if completed < 0 or completed > population:
        raise ValueError("Completed inputs exceed the inference population")
    if not 0 <= measured_completed <= completed:
        raise ValueError("Throughput completions must be a subset of completed inputs")
    available = max(0.0, (deadline - now).total_seconds() - reserve_seconds)
    remaining = population - int(completed)
    rate = (
        measured_completed / elapsed
        if measured_completed > 0 and elapsed and elapsed > 0
        else None
    )
    eta = remaining / rate if rate is not None else (0.0 if remaining == 0 else None)
    return {
        "as_of_utc": now.astimezone(UTC).isoformat(),
        "deadline_utc": deadline.astimezone(UTC).isoformat(),
        "reserve_seconds": reserve_seconds,
        "available_gpu_seconds": available,
        "inference_units": population,
        "completed_inference_units": int(completed),
        "remaining_inference_units": remaining,
        "required_inference_units_per_second": remaining / available
        if available
        else (0.0 if remaining == 0 else None),
        "observed_inference_units_per_second": rate,
        "measured_frame_preparation_seconds": _number(
            benchmark, "frame_preparation_seconds"
        ),
        "conditional_remaining_seconds": eta,
        "conditional_completion_utc": (now + timedelta(seconds=eta)).isoformat()
        if eta is not None
        else None,
        "conditional_deadline_feasible": eta <= available if eta is not None else None,
        "basis": (
            "Observed scoring-loop completion rate including body I/O; conditional "
            "extrapolation excludes a repeated frame-preparation pass"
            if "throughput_elapsed_seconds" in benchmark
            else "Observed end-to-end completion rate; conditional extrapolation"
        ),
    }


def _query_rows(
    connection: duckdb.DuckDBPyConnection,
    query: str,
    parameters: dict[str, int | float | str] | None = None,
) -> list[dict[str, JsonValue]]:
    result = connection.execute(query, parameters)
    names = [column[0] for column in result.description or []]
    return [dict(zip(names, row, strict=True)) for row in result.fetchall()]


def _write_csv(path: Path, rows: list[dict[str, JsonValue]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def _reference_path(
    manifest: dict[str, JsonValue], name: str, cpu: Path
) -> Path | None:
    references = manifest.get("company_references")
    if not isinstance(references, dict):
        return None
    reference = references.get(name)
    value = reference.get("path") if isinstance(reference, dict) else reference
    if not isinstance(value, str):
        return None
    path = Path(value)
    return path if path.is_absolute() or path.exists() else cpu / path


def _company_tables(
    connection: duckdb.DuckDBPyConnection, manifest: dict[str, JsonValue], cpu: Path
) -> bool:
    membership = _reference_path(manifest, "membership", cpu)
    if membership is None:
        connection.execute(
            "CREATE TABLE company_year (issuer_id VARCHAR, publish_year INTEGER, "
            "eligible_membership BOOLEAN, candidate_article_records BIGINT, "
            "candidate_documents BIGINT)"
        )
        return False
    connection.read_csv(str(membership), all_varchar=True).create_view("membership")
    connection.execute(
        "CREATE TABLE company_year AS WITH roster AS ("
        "SELECT 'top1000:' || permco AS issuer_id, "
        "try_cast(effective_year AS INTEGER) AS publish_year, "
        "string_agg(DISTINCT coalesce(link_status, 'unknown'), ';') "
        "AS identity_link_statuses FROM membership "
        "WHERE permco IS NOT NULL AND try_cast(effective_year AS INTEGER) IS NOT NULL"
        " GROUP BY permco, effective_year"
        "), projected AS (SELECT document_id, publish_year, "
        "unnest(list_distinct(list_transform(candidates, c -> c.issuer_id))) "
        "AS issuer_id FROM retained), documents AS ("
        "SELECT issuer_id, publish_year, document_id, count(*) AS article_records "
        "FROM projected JOIN roster USING (issuer_id, publish_year) "
        "GROUP BY issuer_id, publish_year, document_id), observed AS ("
        "SELECT issuer_id, publish_year, sum(article_records) "
        "AS candidate_article_records, count(*) AS candidate_documents "
        "FROM documents GROUP BY issuer_id, publish_year) "
        "SELECT roster.*, true AS eligible_membership, "
        "coalesce(observed.candidate_article_records, 0) AS candidate_article_records, "
        "coalesce(observed.candidate_documents, 0) AS candidate_documents "
        "FROM roster LEFT JOIN observed USING (issuer_id, publish_year)"
    )
    return True


def _evidence_tiers(
    connection: duckdb.DuckDBPyConnection,
) -> list[dict[str, JsonValue]]:
    """Count existing evidence predicates without altering retained eligibility.

    Legacy spans contain at most four examples per field. Presence and the
    two-body-span predicate describe those stored examples, not full match counts.
    The legacy cased-name counter tests absence of a lowercase-single-token flag;
    it does not require capitalization of every multiword alias.
    Identity ambiguity here means shared aliases or tickers; other historical
    certification and signal uncertainty flags remain in the separate report.
    """
    return _query_rows(
        connection,
        """
        WITH evidence AS (
            SELECT document_id,
                list_bool_or(list_transform(candidates,
                    c -> c.cased_name_match_count > 0)) AS any_cased_name,
                list_bool_or(list_transform(candidates,
                    c -> c.tag_match_count > 0)) AS any_publisher_annotation,
                list_bool_or(list_transform(candidates,
                    c -> len(list_filter(c.spans.title,
                        s -> s.source = 'name_alias')) > 0)) AS any_title_name,
                list_bool_or(list_transform(candidates,
                    c -> len(list_filter(c.spans.title,
                        s -> s.source = 'name_alias')) > 0
                    AND c.cased_name_match_count > 0)) AS title_and_cased_name,
                list_bool_or(list_transform(candidates,
                    c -> len(list_filter(c.spans.body,
                        s -> s.source = 'name_alias')) >= 2)) AS repeated_body_name,
                list_bool_or(list_transform(candidates,
                    c -> NOT list_contains(c.uncertainty_flags, 'shared_alias')
                    AND NOT list_contains(c.uncertainty_flags, 'shared_ticker')))
                    AS issuer_without_shared_alias_or_ticker
            FROM retained
        ), documents AS (
            SELECT document_id, bool_or(COLUMNS(* EXCLUDE(document_id)))
            FROM evidence GROUP BY document_id
        ), units AS (
            SELECT *, 'record' AS unit FROM evidence
            UNION ALL SELECT *, 'document' AS unit FROM documents
        ), unpivoted AS (
            UNPIVOT units ON COLUMNS(* EXCLUDE(document_id, unit))
            INTO NAME evidence_tier VALUE matches
        ), tiers(evidence_tier) AS (VALUES
            ('any_cased_name'), ('any_publisher_annotation'), ('any_title_name'),
            ('title_and_cased_name'), ('repeated_body_name'),
            ('issuer_without_shared_alias_or_ticker')
        )
        SELECT evidence_tier,
            count(*) FILTER (WHERE matches AND unit = 'record') AS article_records,
            count(*) FILTER (WHERE matches AND unit = 'document')
                AS exact_text_documents,
            'Existing candidate evidence; unvalidated primary-topic proxy' AS basis
        FROM tiers LEFT JOIN unpivoted USING (evidence_tier)
        GROUP BY evidence_tier ORDER BY evidence_tier
        """,
    )


def _cohorts(
    connection: duckdb.DuckDBPyConnection, membership_available: bool
) -> list[dict[str, JsonValue]]:
    rows: list[dict[str, JsonValue]] = []
    for threshold in (42, 47):
        for years in (5, 10):
            result = _query_rows(
                connection,
                "WITH eligible AS (SELECT issuer_id, publish_year, "
                "publish_year - row_number() OVER "
                "(PARTITION BY issuer_id ORDER BY publish_year) AS run "
                "FROM company_year WHERE candidate_documents >= $threshold), "
                "runs AS (SELECT issuer_id, count(*) AS consecutive_years "
                "FROM eligible GROUP BY issuer_id, run) "
                "SELECT count(DISTINCT issuer_id) AS companies FROM runs "
                "WHERE consecutive_years >= $years",
                {"threshold": threshold, "years": years},
            )[0]
            rows.append(
                {
                    "annual_documents": threshold,
                    "consecutive_years": years,
                    "candidate_companies": result["companies"]
                    if membership_available
                    else None,
                    "basis": "Exact-text candidate documents; unvalidated associations",
                }
            )
    return rows


def _latex(metrics: dict[str, JsonValue]) -> dict[str, str]:
    summary = Summary()
    population = metrics["population"]
    capacity = metrics["capacity"]
    if not isinstance(population, dict) or not isinstance(capacity, dict):
        raise ValueError("Coverage and capacity summaries must be mappings")
    tables = [
        (
            "coverage",
            "Observed CPU article records",
            population,
            (
                "source_records",
                "retained_records",
                "excluded_records",
                "candidate_documents",
            ),
        ),
        (
            "throughput",
            "Conditional processing capacity",
            capacity,
            (
                "remaining_inference_units",
                "available_gpu_seconds",
                "required_inference_units_per_second",
                "observed_inference_units_per_second",
                "conditional_remaining_seconds",
            ),
        ),
    ]
    production = metrics.get("production_scoring")
    if isinstance(production, dict):
        tables.append(
            (
                "scoring",
                "Observed provisional production decisions",
                production,
                (
                    "source_records_in_chunks",
                    "source_records_with_scored_companies",
                    "source_records_with_only_deferred_identity",
                    "candidate_pairs_in_chunks",
                    "unattempted_source_records",
                ),
            )
        )
    for _, title, values, fields in tables:
        summary.tables.append(
            SimpleTable(
                [
                    [f"{value:,.3f}" if isinstance(value, float) else str(value)]
                    if (value := values.get(field)) is not None
                    else ["--"]
                    for field in fields
                ],
                headers=["Value"],
                stubs=[field.replace("_", " ") for field in fields],
                title=title,
            )
        )
    summary.add_extra_txt(
        [
            "Candidate counts are not validated company associations.",
            "Exact-text groups do not establish distinct syndicated stories.",
            "Processing projections are conditional on the measured workload.",
            "Human validation is pending; the precision target is unvalidated.",
        ]
    )
    return {"summary.tex": summary.as_latex()} | {
        f"{name}.tex": table.as_latex_tabular(center=False)
        for (name, *_), table in zip(tables, summary.tables, strict=True)
    }


def _production_metrics(
    connection: duckdb.DuckDBPyConnection,
    scores: Path,
    benchmark: dict[str, JsonValue],
    config: ArticleLabelsConfig,
) -> dict[str, JsonValue]:
    """Extract scalars in DuckDB without materializing rich records in Python."""
    files = sorted(scores.glob("chunks/*.parquet"))
    if files:
        connection.from_parquet([str(path) for path in files]).create_view(
            "score_chunks"
        )
        connection.execute(
            "CREATE VIEW scored_records AS SELECT article_id,inference_id,status,"
            "json_extract_string(article_json,'$.document_id') AS document_id,"
            "try_cast(json_extract(article_json,'$.publish_year') AS INTEGER) "
            "AS publish_year,"
            "json_extract(decision_json,'$.companies[*]') AS companies,"
            "json_extract_string(decision_json,'$.model_name') AS model_name "
            "FROM score_chunks"
        )
    else:
        connection.execute(
            "CREATE VIEW scored_records AS SELECT NULL::VARCHAR AS article_id,"
            "NULL::VARCHAR AS inference_id,NULL::VARCHAR AS status,"
            "NULL::VARCHAR AS document_id,NULL::INTEGER AS publish_year,"
            "[]::JSON[] AS companies,NULL::VARCHAR AS model_name WHERE false"
        )
    connection.execute(
        "CREATE VIEW company_scores AS SELECT article_id,inference_id,document_id,"
        "publish_year,"
        "unnest(companies) AS company FROM scored_records"
    )
    judgments = _query_rows(
        connection,
        "SELECT json_extract_string(company,'$.status') AS status,"
        "count(*) AS candidate_pairs FROM company_scores "
        "GROUP BY status ORDER BY status",
    )
    counts = _query_rows(
        connection,
        "SELECT count(*) AS source_records_in_chunks,"
        "count(*) FILTER(WHERE list_bool_or(list_transform(companies,"
        "c -> try_cast(json_extract(c,'$.identity_score') AS DOUBLE) IS NOT NULL))) "
        "AS source_records_with_scored_companies,"
        "count(*) FILTER(WHERE len(companies)>0 AND list_bool_and("
        "list_transform(companies,c -> json_extract_string(c,'$.status')="
        "'deferred_identity'))) AS source_records_with_only_deferred_identity,"
        "coalesce(sum(len(companies)),0) AS candidate_pairs_in_chunks "
        "FROM scored_records",
    )[0]
    counts["source_status_counts"] = _query_rows(
        connection,
        "SELECT status,count(*) AS source_records FROM scored_records "
        "GROUP BY status ORDER BY status",
    )
    counts["reported_attempted_source_records"] = benchmark.get("attempted")
    counts["unattempted_source_records"] = benchmark.get("unattempted")
    requested = _number(benchmark, "requested")
    observed = counts["source_records_in_chunks"]
    counts["source_records_without_committed_decisions"] = (
        max(0, int(requested) - observed)
        if requested is not None and isinstance(observed, int)
        else None
    )
    manifest = (
        _read_json(scores / "manifest.json")
        if (scores / "manifest.json").is_file()
        else {}
    )
    settings = manifest.get("config")
    settings = settings if isinstance(settings, dict) else {}
    threshold = _number(settings, "min_probability")
    if threshold is None:
        threshold = config.min_probability
    distributions = _query_rows(
        connection,
        "WITH values AS (SELECT field,try_cast(json_extract(company,'$.'||field) "
        "AS DOUBLE) AS value FROM company_scores CROSS JOIN "
        "(VALUES('identity_score'),('substantive_score'),('raw_primary_score'),"
        "('primary_score'),('coverage_score')) fields(field)) "
        "SELECT field AS score,count(value) AS observed_candidate_pairs,"
        "min(value) AS minimum,avg(value) AS mean,max(value) AS maximum,"
        "count(*) FILTER(WHERE value >= 0.5) AS at_least_half,"
        "count(*) FILTER(WHERE value >= $threshold) AS at_least_threshold "
        "FROM values GROUP BY field ORDER BY field",
        {"threshold": threshold},
    )
    return {
        "score_source": "committed_production_chunks",
        "observed_judgments": judgments,
        "production_scoring": counts,
        "score_distributions": distributions,
        "scoring_metadata": {
            "scorer_sha256": manifest.get("scorer_sha256"),
            "contract_sha256": manifest.get("contract_sha256"),
            "rubric": manifest.get("rubric"),
            "runtime": manifest.get("runtime"),
            "config": settings,
            "observed_models": _query_rows(
                connection,
                "SELECT model_name,count(*) AS source_records FROM scored_records "
                "GROUP BY model_name ORDER BY model_name",
            ),
            "model_selection_threshold": threshold,
            "validation_status": "pending_human",
            "interpretation": (
                "Scores and selection thresholds are provisional model outputs; "
                "no calibrated probabilities or validated precision are inferred. "
                "The scorer hash identifies the exact rubric when it is not recorded. "
                "Source-record counts and candidate-pair counts "
                "have separate denominators. Attempted and unattempted counters "
                "come from the selected metadata snapshot; committed chunk counts "
                "are independently observed."
            ),
        },
    }


def _score_metrics(
    connection: duckdb.DuckDBPyConnection,
    population: dict[str, JsonValue],
    scores: Path | None,
    config: ArticleLabelsConfig,
) -> dict[str, JsonValue]:
    benchmark: dict[str, JsonValue] = {}
    benchmark_path: Path | None = None
    if scores is not None:
        benchmark_path = next(
            (
                scores / name
                for name in ("benchmark.json", "summary.json", "progress.json")
                if (scores / name).is_file()
            ),
            None,
        )
        if benchmark_path is None:
            raise FileNotFoundError(
                f"Scoring metadata missing in {scores}: expected benchmark.json, "
                "summary.json or progress.json"
            )
        benchmark = _read_json(benchmark_path)
        progress_path = scores / "progress.json"
        if benchmark_path.name == "summary.json" and progress_path.is_file():
            progress = _read_json(progress_path)
            # Live progress replaces the prior stop; finalization writes both alike.
            # Keep each snapshot's status and timing fields together, without merging.
            if progress != benchmark:
                benchmark_path = progress_path
                benchmark = progress
    judgments: list[dict[str, JsonValue]] = []
    if scores is not None and (scores / "predictions.parquet").is_file():
        connection.from_parquet(str(scores / "predictions.parquet")).create_view(
            "predictions"
        )
        judgments = _query_rows(
            connection,
            "SELECT status, count(*) AS candidate_pairs, "
            "count(DISTINCT inference_id) AS inference_units "
            "FROM predictions GROUP BY status ORDER BY status",
        )
    candidate_records = population["retained_records"]
    if not isinstance(candidate_records, int):
        raise ValueError("Candidate record count must be an integer")
    measured_frame = _number(benchmark, "frame_documents")
    if measured_frame is not None and not 0 <= measured_frame <= candidate_records:
        raise ValueError("Inference frame differs from retained article records")
    population_unit = benchmark.get("frame_unit")
    if not isinstance(population_unit, str):
        population_unit = (
            "inference_units"
            if measured_frame is not None
            else "retained_source_records"
        )
    result: dict[str, JsonValue] = {
        "observed_judgments": judgments,
        "judgment_counts_scope": (
            "Observed scored subset only; no population or company-year scaling"
        ),
        "capacity": throughput_estimates(
            int(measured_frame) if measured_frame is not None else candidate_records,
            benchmark,
            now=datetime.now(UTC),
            deadline=config.deadline_utc,
            reserve_seconds=config.reserve_seconds,
        ),
        "capacity_workload_unit": population_unit,
        "capacity_workload_basis": (
            "Retained source records; benchmark samples article rows"
            if population_unit == "retained_source_records"
            else "Inference units: text, title, date, publisher and candidates"
        ),
        "benchmark": benchmark,
        "benchmark_source": benchmark_path.name if benchmark_path is not None else None,
    }
    if (
        benchmark_path is not None
        and benchmark_path.name == "progress.json"
        and "throughput_elapsed_seconds" not in benchmark
    ):
        capacity = result["capacity"]
        if isinstance(capacity, dict):
            capacity["basis"] = (
                "Observed active scoring-loop completion rate including body I/O; "
                "conditional extrapolation excludes initial frame preparation"
            )
    if scores is not None:
        manifest = (
            _read_json(scores / "manifest.json")
            if (scores / "manifest.json").is_file()
            else {}
        )
        if any(scores.glob("chunks/*.parquet")) or manifest.get("storage") == (
            "compressed-source-record-chunks"
        ):
            result.update(_production_metrics(connection, scores, benchmark, config))
    return result


def _write_observed_coverage(
    connection: duckdb.DuckDBPyConnection,
    staging: Path,
    metrics: dict[str, JsonValue],
    methods: dict[str, JsonValue],
) -> None:
    """Keep observed model selections separate from pending candidate records."""
    metadata = metrics.get("scoring_metadata")
    if not isinstance(metadata, dict):
        methods.pop("observed_company_coverage", None)
        return
    threshold = _number(metadata, "model_selection_threshold")
    if threshold is None:
        raise ValueError("Observed selections require the stored scoring cutoff")
    roster = connection.read_csv(str(staging / "company_year.csv"), all_varchar=True)
    if "identity_link_statuses" not in roster.columns:
        roster = roster.project("*,NULL::VARCHAR AS identity_link_statuses")
    roster.create_view("coverage_roster_csv")
    connection.execute(
        "CREATE TEMP TABLE coverage_roster AS SELECT issuer_id,"
        "publish_year::INTEGER AS publish_year,eligible_membership::BOOLEAN "
        "AS eligible_membership,identity_link_statuses,"
        "candidate_article_records::BIGINT AS candidate_article_records,"
        "candidate_documents::BIGINT AS candidate_documents "
        "FROM coverage_roster_csv"
    )
    connection.execute(
        "CREATE TEMP TABLE observed_documents AS WITH pairs AS ("
        "SELECT document_id,publish_year,json_extract_string(company,'$.issuer_id') "
        "AS issuer_id,json_extract_string(company,'$.status') AS status,"
        "try_cast(json_extract(company,'$.identity_score') AS DOUBLE) "
        "AS identity_score,"
        "try_cast(json_extract(company,'$.substantive_score') AS DOUBLE) "
        "AS substantive_score,try_cast(json_extract(company,'$.raw_primary_score') "
        "AS DOUBLE) AS primary_score FROM company_scores) "
        "SELECT issuer_id,publish_year,document_id,"
        "count(*) AS attempted_article_records,"
        "count(*) FILTER(WHERE identity_score IS NOT NULL) AS scored_article_records,"
        "count(*) FILTER(WHERE status IN "
        "('too_long','server_failed','deferred_identity')) "
        "AS unscorable_article_records,count(*) FILTER(WHERE status='review') "
        "AS review_article_records,count(*) FILTER(WHERE status='accepted') "
        "AS accepted_article_records,count(*) FILTER(WHERE status='accepted' "
        "AND substantive_score >= $threshold) AS substantive_article_records,"
        "count(*) FILTER(WHERE status='accepted' AND primary_score >= $threshold) "
        "AS primary_article_records FROM pairs "
        "GROUP BY issuer_id,publish_year,document_id",
        {"threshold": threshold},
    )
    if connection.execute(
        "SELECT count(*) FROM observed_documents "
        "WHERE issuer_id IS NULL OR document_id IS NULL"
    ).fetchone()[0]:
        raise ValueError("Committed company decisions require issuer and document IDs")
    connection.execute(
        "CREATE TEMP TABLE observed_company_year AS WITH observed AS ("
        "SELECT issuer_id,publish_year,sum(attempted_article_records) "
        "AS attempted_article_records,count(*) AS attempted_documents,"
        "sum(scored_article_records) AS scored_article_records,"
        "sum(unscorable_article_records) AS unscorable_article_records,"
        "sum(review_article_records) AS review_article_records,"
        "sum(accepted_article_records) AS accepted_article_records,"
        "count(*) FILTER(WHERE accepted_article_records>0) AS accepted_documents,"
        "sum(substantive_article_records) AS substantive_article_records,"
        "count(*) FILTER(WHERE substantive_article_records>0) AS substantive_documents,"
        "sum(primary_article_records) AS primary_article_records,"
        "count(*) FILTER(WHERE primary_article_records>0) AS primary_documents "
        "FROM observed_documents GROUP BY issuer_id,publish_year) "
        "SELECT coalesce(r.issuer_id,o.issuer_id) AS issuer_id,"
        "coalesce(r.publish_year,o.publish_year) AS publish_year,"
        "coalesce(r.eligible_membership,false) AS eligible_membership,"
        "r.identity_link_statuses,r.candidate_article_records,r.candidate_documents,"
        "coalesce(o.attempted_article_records,0) AS attempted_article_records,"
        "coalesce(o.attempted_documents,0) AS attempted_documents,"
        "coalesce(o.scored_article_records,0) AS scored_article_records,"
        "coalesce(o.unscorable_article_records,0) AS unscorable_article_records,"
        "coalesce(o.review_article_records,0) AS review_article_records,"
        "r.candidate_article_records-coalesce(o.attempted_article_records,0) "
        "AS pending_article_records,"
        "r.candidate_documents-coalesce(o.attempted_documents,0) "
        "AS documents_without_attempted_copy,"
        "coalesce(o.accepted_article_records,0) AS accepted_article_records,"
        "coalesce(o.accepted_documents,0) AS accepted_documents,"
        "coalesce(o.substantive_article_records,0) AS substantive_article_records,"
        "coalesce(o.substantive_documents,0) AS substantive_documents,"
        "coalesce(o.primary_article_records,0) AS primary_article_records,"
        "coalesce(o.primary_documents,0) AS primary_documents,"
        "$threshold AS model_selection_threshold,'pending_human' AS validation_status "
        "FROM coverage_roster r FULL OUTER JOIN observed o "
        "USING(issuer_id,publish_year)",
        {"threshold": threshold},
    )
    if connection.execute(
        "SELECT count(*) FROM observed_company_year WHERE pending_article_records<0 "
        "OR documents_without_attempted_copy<0"
    ).fetchone()[0]:
        raise ValueError("Committed company-year counts exceed the candidate census")
    connection.sql(
        "SELECT * FROM observed_company_year ORDER BY issuer_id,publish_year"
    ).write_csv(str(staging / "observed_company_year.csv"), header=True)
    cohort_rows: list[dict[str, JsonValue]] = []
    with (staging / "cohorts.csv").open(encoding="utf-8") as stream:
        for candidate in csv.DictReader(stream):
            annual = int(candidate["annual_documents"])
            years = int(candidate["consecutive_years"])
            row: dict[str, JsonValue] = {
                "annual_documents": annual,
                "consecutive_years": years,
                "candidate_companies": int(candidate["candidate_companies"])
                if candidate["candidate_companies"]
                else None,
            }
            for label in ("accepted", "substantive", "primary"):
                result = _query_rows(
                    connection,
                    "WITH eligible AS (SELECT issuer_id,publish_year,"
                    "publish_year-row_number() OVER(PARTITION BY issuer_id "
                    "ORDER BY publish_year) AS run FROM observed_company_year "
                    "WHERE eligible_membership AND CASE $label "
                    "WHEN 'accepted' THEN accepted_documents WHEN 'substantive' "
                    "THEN substantive_documents ELSE primary_documents END >= $annual),"
                    "runs AS (SELECT issuer_id,count(*) AS years FROM eligible "
                    "GROUP BY issuer_id,run) "
                    "SELECT count(DISTINCT issuer_id) AS companies "
                    "FROM runs WHERE years >= $years",
                    {"label": label, "annual": annual, "years": years},
                )[0]
                row[f"observed_{label}_companies"] = result["companies"]
            row.update(
                _query_rows(
                    connection,
                    "SELECT count(*) AS eligible_company_year_cells,"
                    "count(*) FILTER(WHERE pending_article_records>0) "
                    "AS cells_with_pending_candidates,count(*) FILTER(WHERE "
                    "unscorable_article_records>0) AS cells_with_unscorable_candidates "
                    "FROM observed_company_year WHERE eligible_membership",
                )[0]
            )
            row.update(
                {
                    "model_selection_threshold": threshold,
                    "validation_status": "pending_human",
                    "basis": (
                        "Observed provisional model selections in committed chunks"
                    ),
                }
            )
            cohort_rows.append(row)
    _write_csv(staging / "observed_cohorts.csv", cohort_rows)
    methods["observed_company_coverage"] = {
        "scope": "Observed provisional model selections; no population extrapolation",
        "accepted": "Stored accepted status; the scorer selection policy is unchanged",
        "substantive_and_primary": (
            "Require accepted status and the respective raw score >= stored cutoff; "
            "independent scores need not yield nested counts"
        ),
        "pending": (
            "Candidate census records minus committed attempts; active unflushed "
            "work remains pending here. Unscorable and review counts remain separate."
        ),
        "documents": (
            "Exact-text document IDs per issuer/year; any selected copy counts once. "
            "Documents without an attempted copy do not measure partially scored "
            "groups "
            "or establish distinct syndicated stories."
        ),
        "eligibility": (
            "Census membership flags are preserved. Unrostered namespaces and unknown "
            "years remain visible with NULL candidate/pending denominators and do not "
            "enter membership cohorts. No source-format exclusions are applied."
        ),
        "validation_status": "pending_human",
    }


def _write_report_files(
    staging: Path, metrics: dict[str, JsonValue], methods: dict[str, JsonValue]
) -> None:
    for name, payload in (("metrics.json", metrics), ("methods.json", methods)):
        (staging / name).write_text(
            json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    for name, content in _latex(metrics).items():
        (staging / name).write_text(content + "\n", encoding="utf-8")
    production = metrics.get("production_scoring")
    if isinstance(production, dict):
        for name, rows in (
            ("source_statuses", production.get("source_status_counts")),
            ("judgments", metrics.get("observed_judgments")),
            ("score_distributions", metrics.get("score_distributions")),
        ):
            if isinstance(rows, list):
                _write_csv(
                    staging / f"{name}.csv",
                    [row for row in rows if isinstance(row, dict)],
                )


def _reuse_census(
    cpu: Path,
    census: Path,
    output: Path,
    scores: Path | None,
    config: ArticleLabelsConfig,
) -> None:
    metrics = _read_json(census / "metrics.json")
    methods = _read_json(census / "methods.json")
    current_summary = (
        _read_json(cpu / "summary.json") if (cpu / "summary.json").exists() else None
    )
    if metrics.get("cpu_processing") != current_summary:
        raise ValueError("The census does not describe the current CPU processing run")
    population = metrics.get("population")
    if not isinstance(population, dict):
        raise ValueError("The census requires a population mapping")
    for key in (
        "score_source",
        "production_scoring",
        "score_distributions",
        "scoring_metadata",
    ):
        metrics.pop(key, None)
    with duckdb.connect() as connection, TemporaryDirectory(dir=output.parent) as temp:
        staging = Path(temp) / "report"
        staging.mkdir()
        for name in REPORT_FILES:
            if name.endswith(".csv"):
                shutil.copyfile(census / name, staging / name)
        metrics.update(_score_metrics(connection, population, scores, config))
        metrics["precision_target"] = config.precision_target
        methods["census_reuse"] = str(census)
        methods["evidence_tiers"] = EVIDENCE_DEFINITIONS
        _write_observed_coverage(connection, staging, metrics, methods)
        _write_report_files(staging, metrics, methods)
        os.rename(staging, output)


def report_article_labels(
    cpu: Annotated[Path, typer.Option(help="Completed CPU index and provenance.")],
    output: Annotated[
        Path, typer.Option(help="New directory for coverage and capacity reports.")
    ],
    scores: Annotated[
        Path | None,
        typer.Option(help="Optional Kev benchmark or active scoring checkpoint."),
    ] = None,
    params: Annotated[Path, typer.Option()] = Path("params.yaml"),
    census: Annotated[
        Path | None,
        typer.Option(
            help="Reuse a completed CPU report without rescanning its indices."
        ),
    ] = None,
) -> None:
    """Summarize observed candidates and a conditional processing deadline."""
    config = load_config(params)
    if output.exists():
        raise FileExistsError(f"Output exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if census is not None:
        _reuse_census(cpu, census, output, scores, config)
        typer.echo(f"Wrote provisional article-label coverage: {output}")
        return
    manifest = _read_json(cpu / "manifest.json")
    retained = sorted(cpu.glob("shards/*/retained.parquet"))
    excluded = sorted(cpu.glob("shards/*/excluded.parquet"))
    if not retained or not excluded:
        raise ValueError("CPU indices require retained and excluded Parquet artifacts")
    with (
        duckdb.connect(config={"memory_limit": "4GB", "threads": 1}) as connection,
        TemporaryDirectory(dir=output.parent) as temporary,
    ):
        staging = Path(temporary) / "report"
        staging.mkdir()
        connection.execute("SET max_temp_directory_size = '8GB'")
        connection.execute("SET preserve_insertion_order = false")
        connection.from_parquet(
            [str(path) for path in retained], union_by_name=True
        ).create_view("retained")
        connection.from_parquet(
            [str(path) for path in excluded], union_by_name=True
        ).create_view("excluded")
        connection.execute(
            "CREATE VIEW articles AS SELECT article_id, document_id, publish_year, "
            "hostname, candidate_count, text_chars, quality_flags, "
            "'retained' AS status "
            "FROM retained UNION ALL SELECT article_id, document_id, publish_year, "
            "hostname, candidate_count, text_chars, quality_flags, exclusion_reason "
            "AS status FROM excluded"
        )
        population = _query_rows(
            connection,
            "SELECT count(*) AS source_records, "
            "count(*) FILTER (WHERE status = 'retained') AS retained_records, "
            "count(*) FILTER (WHERE status != 'retained') AS excluded_records, "
            "count(DISTINCT document_id) FILTER (WHERE status = 'retained') "
            "AS candidate_documents, "
            "coalesce(sum(candidate_count) FILTER (WHERE status = 'retained'), 0) "
            "AS candidate_pairs, "
            "count(*) FILTER (WHERE publish_year IS NULL) AS undated_records "
            "FROM articles",
        )[0]
        source_files = manifest.get("source_files")
        if isinstance(source_files, list):
            expected_rows = sum(
                int(record["rows"])
                for record in source_files
                if isinstance(record, dict) and isinstance(record.get("rows"), int)
            )
            if population["source_records"] != expected_rows:
                raise ValueError("CPU source counts are incomplete or do not reconcile")
        exclusions = _query_rows(
            connection,
            "SELECT status, count(*) AS records FROM articles "
            "GROUP BY status ORDER BY status",
        )
        uncertainties = _query_rows(
            connection,
            "WITH flags AS (SELECT unnest(list_transform(candidates, "
            "c -> c.uncertainty_flags), recursive := true) AS flag FROM retained) "
            "SELECT flag, count(*) AS candidate_pairs FROM flags "
            "GROUP BY flag ORDER BY candidate_pairs DESC, flag",
        )
        population.update(
            _query_rows(
                connection,
                "WITH counts AS (SELECT len(list_filter(candidates, "
                "c -> len(c.uncertainty_flags) > 0)) AS uncertain FROM retained) "
                "SELECT count(*) FILTER (WHERE uncertain > 0) "
                "AS articles_with_uncertain_candidates, coalesce(sum(uncertain), 0) "
                "AS candidate_pairs_with_uncertainty FROM counts",
            )[0]
        )
        quality_flags = _query_rows(
            connection,
            "WITH flags AS (SELECT unnest(quality_flags) AS flag FROM articles) "
            "SELECT flag, count(*) AS article_records FROM flags "
            "GROUP BY flag ORDER BY article_records DESC, flag",
        )
        connection.sql(
            "SELECT publish_year, hostname, status, count(*) AS article_records, "
            "count(DISTINCT document_id) AS exact_text_documents "
            "FROM articles GROUP BY publish_year, hostname, status "
            "ORDER BY publish_year, hostname, status"
        ).write_csv(str(staging / "year_publisher.csv"), header=True)
        distribution = _query_rows(
            connection,
            "SELECT status, count(*) AS records, "
            "quantile_disc(candidate_count, 0.5) AS candidate_count_p50, "
            "quantile_disc(candidate_count, 0.95) AS candidate_count_p95, "
            "max(candidate_count) AS candidate_count_max, "
            "quantile_disc(text_chars, 0.5) AS text_chars_p50, "
            "quantile_disc(text_chars, 0.95) AS text_chars_p95, "
            "max(text_chars) AS text_chars_max FROM articles "
            "GROUP BY status ORDER BY status",
        )
        _write_csv(staging / "distributions.csv", distribution)
        evidence_tiers = _evidence_tiers(connection)
        _write_csv(staging / "evidence_tiers.csv", evidence_tiers)
        for tier in evidence_tiers:
            typer.echo(
                f"{tier['evidence_tier']}: {tier['article_records']} "
                "candidate article records"
            )
        membership_available = _company_tables(connection, manifest, cpu)
        connection.sql(
            "SELECT * FROM company_year ORDER BY issuer_id, publish_year"
        ).write_csv(str(staging / "company_year.csv"), header=True)
        cohorts = _cohorts(connection, membership_available)
        _write_csv(staging / "cohorts.csv", cohorts)
        metrics: dict[str, JsonValue] = {
            "validation_status": "pending_human",
            "reviewer_type": "ai_assisted",
            "precision_target": config.precision_target,
            "precision_target_validated": False,
            "population": population,
            "exclusions": exclusions,
            "input_quality_flags": quality_flags,
            "candidate_uncertainty_flags": uncertainties,
            "evidence_tiers": evidence_tiers,
            "membership_reference_available": membership_available,
            "cpu_processing": _read_json(cpu / "summary.json")
            if (cpu / "summary.json").exists()
            else None,
            **_score_metrics(connection, population, scores, config),
        }
        methods: dict[str, JsonValue] = {
            "frame": "Frozen source article records in completed CPU indices",
            "company_years": "Membership roster with explicit zero candidate counts",
            "cohort_basis": "Top-1000 eligible years and exact-text candidate groups",
            "gh_catalog": (
                "Fixed GH catalog is not historically certified and is excluded "
                "from membership cohorts"
            ),
            "validation": "Exploratory AI-assisted labels; no human accuracy estimate",
            "capacity": (
                "Remaining inference units divided by observed completed-unit "
                "wall-time rate"
            ),
            "evidence_tiers": EVIDENCE_DEFINITIONS,
            "limitations": [
                "Candidate associations are not substantive coverage labels",
                "Exact-text grouping is not story or syndication deduplication",
                "No company-year extrapolation from a small scored sample",
                "Missing years and unresolved identities remain explicit",
                "Evidence tiers overlap and do not establish primary-topic coverage",
            ],
        }
        _write_observed_coverage(connection, staging, metrics, methods)
        _write_report_files(staging, metrics, methods)
        os.rename(staging, output)
    typer.echo(f"Wrote provisional article-label coverage: {output}")
