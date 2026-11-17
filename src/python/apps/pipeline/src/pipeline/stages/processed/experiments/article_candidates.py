"""Resolve candidate names through dated issuer links without discarding evidence."""

import csv
import hashlib
import json
import os
import re
import shutil
import time
import unicodedata
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

import duckdb
import typer
from pydantic import BaseModel, Field, TypeAdapter

_SUFFIX = re.compile(
    r"[\s,]+(?:incorporated|inc|corporation|corp|limited|ltd|plc|llc|"
    r"l\.l\.c|(?:&\s+)?(?:co|company))\.?$",
    re.IGNORECASE,
)
_DESCRIPTORS = {
    "company",
    "corporation",
    "group",
    "holding",
    "holdings",
    "incorporated",
    "international",
    "limited",
}


class _Reference(BaseModel):
    path: Path
    sha256: str


class _Source(BaseModel):
    source_root: Path
    company_references: dict[str, _Reference]


class _Completed(BaseModel):
    contract_sha256: str
    input_sha256: str
    output_sha256: str
    counts: dict[str, int] = Field(default_factory=dict)


class _Summary(BaseModel):
    status: Literal["complete"]
    source_rows: int
    retained_rows: int
    excluded_rows: int


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold()


def _forms(name: str, aliases: list[str]) -> list[tuple[str, str, str]]:
    """Record literal registry names and the legacy legal-suffix transform."""
    result: set[tuple[str, str, str]] = set()
    for value, origin in [(name, "legal_name"), *((a, "other_name") for a in aliases)]:
        if value.strip():
            result.add((_normalize(value), origin, value))
        root = value.strip()
        while (shorter := _SUFFIX.sub("", root).rstrip(" ,")) != root:
            root = shorter
        words = re.findall(r"\w+", root)
        if (
            root != value.strip()
            and len("".join(words)) >= 4
            and any(word.casefold() not in _DESCRIPTORS for word in words)
        ):
            result.add((_normalize(root), origin + "_root", value))
    return sorted(result)


def _catalog(
    references: dict[str, _Reference], submissions: Path | None
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    csv.field_size_limit(20_000_000)
    for source in ("registry", "gh"):
        with references[source].path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                name = row.get("company_legal_name", "").strip()
                if not name:
                    continue
                cik = row.get("cik", "").strip()
                if not cik:
                    continue
                cik = str(int(cik)).zfill(10)
                key = row["issuer_key"] if source == "registry" else "gh:" + cik
                aliases = TypeAdapter(list[str]).validate_json(
                    row["other_names"] or "[]"
                )
                sec: dict[str, object] = {}
                if submissions is not None:
                    path = submissions / f"CIK{cik}.json"
                    if path.exists():
                        sec = json.loads(path.read_text(encoding="utf-8"))
                for alias, origin, source_name in _forms(name, aliases):
                    current = _normalize(str(sec.get("name", name)))
                    pattern = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)")
                    former = TypeAdapter(list[dict[str, str]]).validate_python(
                        sec.get("formerNames", [])
                    )
                    periods = [
                        item
                        for item in former
                        if pattern.search(_normalize(item["name"]))
                        and not pattern.search(current)
                    ]
                    records.append(
                        {
                            "issuer_key": key,
                            "cik": cik,
                            "name": name,
                            "alias": alias,
                            "origin": origin,
                            "source_name": source_name,
                            "reference": source,
                            "former_names": json.dumps(periods),
                            "observed_first_year": min(
                                (item["from"][:4] for item in periods), default=""
                            ),
                            "observed_last_year": max(
                                (item["to"][:4] for item in periods), default=""
                            ),
                        }
                    )
    return records


_AUTHORITIES = """
CREATE TEMP TABLE authorities AS
WITH names AS (
    SELECT issuer_key, min(cik) AS cik, min(name) AS name,
        list_distinct(list(alias)) AS aliases,
        list_distinct(list(alias) FILTER(WHERE origin = 'legal_name')) AS legal_names,
        list_distinct(list(alias) FILTER(WHERE origin = 'other_name')) AS other_names,
        list_distinct(list(alias)
            FILTER(WHERE origin = 'legal_name_root')) AS legal_roots,
        list_distinct(list(alias)
            FILTER(WHERE origin = 'other_name_root')) AS other_roots,
        list_distinct(list(struct_pack(alias := alias,
            first_year := try_cast(observed_first_year AS INTEGER),
            last_year := try_cast(observed_last_year AS INTEGER)))
            FILTER(WHERE observed_last_year != '')) AS former_periods
    FROM catalog GROUP BY issuer_key
), membership AS (
    SELECT effective_year::INTEGER AS year,
        'top1000:' || permco AS issuer_id,
        count(DISTINCT cik) FILTER(WHERE link_status = 'verified') AS verified_ciks,
        min(issuer_key) FILTER(WHERE link_status = 'verified') AS issuer_key,
        list_sort(list_distinct(list(upper(trim(ticker))) FILTER(
            WHERE link_status = 'verified' AND coalesce(trim(ticker), '') != ''
        ))) AS verified_tickers
    FROM read_csv($membership, header=true)
    GROUP BY effective_year, permco
)
SELECT m.year, m.issuer_id, m.verified_tickers, n.*,
    CASE WHEN verified_ciks > 1 THEN 'conflicting_verified_links'
         WHEN verified_ciks = 0 THEN 'unverified_article_year_link'
         WHEN n.name IS NULL THEN 'verified_link_missing_registry_name'
         ELSE 'verified_article_year_cik' END AS identity_status
FROM membership m LEFT JOIN names n
    ON m.verified_ciks = 1 AND m.issuer_key = n.issuer_key
UNION ALL BY NAME
SELECT -1 AS year, issuer_key AS issuer_id, *,
    'fixed_gh_cik_undated' AS identity_status
FROM names WHERE starts_with(issuer_key, 'gh:')
"""

_CORRECT = """
CREATE TEMP TABLE corrected AS
WITH pairs AS (
    SELECT article_id, publish_year,
        unnest(list_transform(candidates, (c, i) -> struct_pack(
            ordinal := i, issuer_id := c.issuer_id,
            counted_names := c.name_match_count,
            publisher_tag := list_contains(c.evidence_sources, 'publisher_tag'),
            name_spans := list_concat(
                list_transform(list_filter(c.spans.title,
                    s -> s.source = 'name_alias'),
                    s -> struct_pack(alias := s.alias, field := 'title')),
                list_transform(list_filter(c.spans.body,
                    s -> s.source = 'name_alias'),
                    s -> struct_pack(alias := s.alias, field := 'body'))
            )
        ))) AS c
    FROM input_chunk
), supported AS (
    SELECT article_id, publish_year, c, a.name, a.cik, a.issuer_key,
        a.verified_tickers,
        coalesce(a.identity_status,
            CASE WHEN publish_year IS NULL THEN 'unknown_article_year'
                 ELSE 'unsupported_article_year_or_issuer' END) AS identity_status,
        list_filter(c.name_spans,
            s -> coalesce(list_contains(a.aliases, s.alias), false)) AS supported,
        list_transform(list_distinct(list_transform(c.name_spans, s -> s.alias)),
            alias -> struct_pack(alias := alias,
            former_name_periods := list_filter(a.former_periods, p -> p.alias = alias),
            origins := list_filter([
                CASE WHEN list_contains(a.legal_names, alias) THEN 'legal_name' END,
                CASE WHEN list_contains(a.other_names, alias) THEN 'other_name' END,
                CASE WHEN list_contains(a.legal_roots, alias)
                    THEN 'legal_name_root' END,
                CASE WHEN list_contains(a.other_roots, alias) THEN 'other_name_root' END
            ], origin -> origin IS NOT NULL))) AS alias_provenance
    FROM pairs p LEFT JOIN authorities a
        ON c.issuer_id = a.issuer_id
        AND a.year = CASE WHEN starts_with(c.issuer_id, 'gh:')
                         THEN -1 ELSE publish_year END
), classified AS (
    SELECT *,
        len(list_filter(supported, s -> s.field = 'title')) > 0 AS title_name,
        len(list_filter(supported, s -> s.field = 'body')) > 0 AS body_name,
        c.counted_names > len(c.name_spans) AS censored,
        list_filter([
            CASE WHEN list_any_value(list_transform(alias_provenance,
                a -> CASE WHEN regexp_full_match(a.alias, '[^[:space:]]+')
                    THEN true END)) THEN 'single_token_alias' END,
            CASE WHEN list_any_value(list_transform(alias_provenance,
                a -> CASE WHEN list_contains(a.origins, 'legal_name_root')
                    OR list_contains(a.origins, 'other_name_root') THEN true END))
                THEN 'derived_legal_root' END,
            CASE WHEN list_any_value(list_transform(alias_provenance,
                a -> CASE WHEN list_contains(a.origins, 'other_name')
                    OR list_contains(a.origins, 'other_name_root') THEN true END))
                THEN 'other_name_not_historically_certified' END,
            CASE WHEN list_any_value(list_transform(alias_provenance,
                a -> CASE WHEN len(a.former_name_periods) > 0 THEN true END))
                THEN 'historical_name_context_required' END,
            CASE WHEN list_any_value(list_transform(alias_provenance,
                a -> CASE WHEN len(list_filter(a.former_name_periods,
                    p -> publish_year < p.first_year OR publish_year > p.last_year)) > 0
                    THEN true END)) THEN 'outside_observed_former_name_period' END,
            CASE WHEN c.publisher_tag THEN 'publisher_keyword_unverified' END,
            CASE WHEN c.counted_names > len(c.name_spans)
                THEN 'stored_name_evidence_censored' END,
            CASE WHEN len(supported) < len(c.name_spans)
                THEN 'observed_alias_outside_resolved_registry' END
        ], flag -> flag IS NOT NULL) AS ambiguity_flags
    FROM supported
), annotated AS (
    SELECT *,
        CASE WHEN identity_status = 'verified_article_year_cik'
                  AND title_name AND body_name THEN 'verified_title_and_body'
             WHEN identity_status = 'verified_article_year_cik'
                  AND len(supported) > 0 THEN 'verified_other_name_evidence'
             WHEN identity_status = 'fixed_gh_cik_undated'
                  AND len(supported) > 0 THEN 'fixed_gh_name_evidence'
             WHEN identity_status = 'verified_article_year_cik'
                  THEN 'verified_without_stored_permitted_names'
             ELSE 'unresolved_identity' END AS evidence_tier
    FROM classified
), corrections AS (
    SELECT article_id, list(struct_pack(
        name := name, cik := cik, issuer_key := issuer_key,
        verified_tickers := verified_tickers,
        identity_status := identity_status,
        supported_aliases := list_distinct(list_transform(supported, s -> s.alias)),
        alias_provenance := alias_provenance, ambiguity_flags := ambiguity_flags,
        title_name := title_name, body_name := body_name, censored := censored,
        evidence_tier := evidence_tier
    ) ORDER BY c.ordinal) AS corrections
    FROM annotated GROUP BY article_id
)
SELECT b.* REPLACE(list_transform(b.candidates, (c, i) -> struct_update(c,
    name := r.corrections[i].name,
    original_name := c.name,
    ticker := CASE WHEN r.corrections[i].identity_status = 'verified_article_year_cik'
        THEN r.corrections[i].verified_tickers[1] ELSE c.ticker END,
    tickers := CASE WHEN r.corrections[i].identity_status = 'verified_article_year_cik'
        THEN coalesce(r.corrections[i].verified_tickers, []) ELSE c.tickers END,
    original_ticker := c.ticker, original_tickers := c.tickers,
    original_identity := c.identity,
    identity := CASE WHEN r.corrections[i].identity_status = 'verified_article_year_cik'
        THEN struct_pack(ciks := [r.corrections[i].cik],
            issuer_keys := [r.corrections[i].issuer_key], link_statuses := ['verified'])
        ELSE c.identity END,
    identity_status := r.corrections[i].identity_status,
    authority_cik := r.corrections[i].cik,
    authority_issuer_key := r.corrections[i].issuer_key,
    supported_aliases := r.corrections[i].supported_aliases,
    alias_provenance := r.corrections[i].alias_provenance,
    ambiguity_flags := r.corrections[i].ambiguity_flags,
    permitted_title_name := r.corrections[i].title_name,
    permitted_body_name := r.corrections[i].body_name,
    name_evidence_censored := r.corrections[i].censored,
    evidence_tier := r.corrections[i].evidence_tier
)) AS candidates),
    len(list_filter(r.corrections,
        c -> c.evidence_tier = 'verified_title_and_body')) AS primary_candidate_count,
    CASE WHEN len(list_filter(r.corrections,
        c -> c.evidence_tier = 'verified_title_and_body')) > 0
        THEN 'primary_discovery' ELSE 'deferred' END AS candidate_status
FROM input_chunk b
JOIN corrections r USING(article_id)
"""


def _correct_source(
    con: duckdb.DuckDBPyConnection, path: Path, target: Path
) -> dict[str, int]:
    """Transform every record in bounded execution batches, then stream the parts."""
    original = con.execute(
        "SELECT count(*),coalesce(sum(candidate_count),0) FROM read_parquet(?)",
        [str(path)],
    ).fetchone()
    if original is None:
        raise ValueError(f"Broad candidate source is missing: {path}")
    parts = target.parent / "parts"
    parts.mkdir()
    totals: dict[str, int] = {}
    for first in range(0, max(int(original[0]), 1), 16384):
        con.execute(
            "CREATE TEMP TABLE input_chunk AS SELECT * EXCLUDE(file_row_number) "
            "FROM read_parquet($input,file_row_number=true,hive_partitioning=false) "
            "WHERE file_row_number >= $first AND file_row_number < $last",
            {"input": str(path), "first": first, "last": first + 16384},
        )
        con.execute(_CORRECT)
        row = con.execute(
            "SELECT count(*),sum(candidate_count),"
            "count(*) FILTER(WHERE primary_candidate_count>0),"
            "sum(primary_candidate_count),"
            "sum(len(list_filter(candidates,"
            "c -> c.identity_status='verified_article_year_cik'))),"
            "sum(len(list_filter(candidates,"
            "c -> c.name IS NOT NULL AND c.name IS DISTINCT FROM c.original_name))) "
            "FROM corrected"
        ).fetchone()
        if row is None:
            raise ValueError(f"Corrected source counts are missing: {path}")
        for key, count in zip(
            (
                "articles",
                "candidate_pairs",
                "primary_discovery_articles",
                "primary_discovery_pairs",
                "verified_identity_pairs",
                "name_corrections",
            ),
            row,
            strict=True,
        ):
            totals[key] = totals.get(key, 0) + int(count or 0)
        con.execute(
            "COPY (SELECT * FROM corrected ORDER BY source_row) TO $target "
            "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 16384)",
            {"target": str(parts / f"part-{first:09d}.parquet")},
        )
        con.execute("DROP TABLE corrected")
        con.execute("DROP TABLE input_chunk")
    if (totals["articles"], totals["candidate_pairs"]) != original:
        raise ValueError(f"Corrected source counts differ: {path}")
    con.execute("SET threads=1")
    con.execute(
        "COPY (SELECT * FROM read_parquet($parts)) TO $target "
        "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 16384)",
        {
            "parts": [str(part) for part in sorted(parts.glob("*.parquet"))],
            "target": str(target),
        },
    )
    con.execute("SET threads=4")
    shutil.rmtree(parts)
    return totals


def correct_article_candidates(
    source: Annotated[
        Path, typer.Option("--input", help="Completed broad CPU candidate index.")
    ],
    output: Annotated[Path, typer.Option(help="Corrected names and evidence tiers.")],
    submissions: Annotated[
        Path | None,
        typer.Option("--sec-submissions", help="Frozen SEC submissions snapshot."),
    ] = None,
    references: Annotated[
        Path | None,
        typer.Option(
            "--references", help="Explicit relocated company-reference directory."
        ),
    ] = None,
    resume: Annotated[
        bool, typer.Option(help="Verify completed source checkpoints.")
    ] = True,
) -> None:
    """Resolve registry identities and preserve every broad candidate for review.

    The title-and-body tier is a retrieval diagnostic, not a relevance label.
    Registry names and aliases are not certified historical company names.
    Unsupported links and censored legacy evidence remain explicit.
    """
    source, output = source.resolve(), output.resolve()
    started = time.monotonic()
    parent = _Source.model_validate_json((source / "manifest.json").read_bytes())
    if references is not None:
        parent.company_references = {
            key: _Reference(
                path=references.resolve() / f"{key}.csv", sha256=value.sha256
            )
            for key, value in parent.company_references.items()
        }
    baseline_summary = _Summary.model_validate_json(
        (source / "summary.json").read_bytes()
    )
    if baseline_summary.source_rows != (
        baseline_summary.retained_rows + baseline_summary.excluded_rows
    ):
        raise ValueError("Baseline source counts do not reconcile")
    for reference in parent.company_references.values():
        if _sha256(reference.path) != reference.sha256:
            raise ValueError(f"Company reference checksum differs: {reference.path}")
    contract_data = {
        "version": "article-candidate-correction-1",
        "source_root": str(parent.source_root),
        "baseline_root": str(source),
        "baseline_manifest_sha256": _sha256(source / "manifest.json"),
        "baseline_summary_sha256": _sha256(source / "summary.json"),
        "company_references": {
            key: value.model_dump(mode="json")
            for key, value in parent.company_references.items()
        },
        "implementation_sha256": _sha256(Path(__file__)),
        "sec_submissions": None
        if submissions is None
        else {
            "path": str(submissions.resolve()),
            "manifest_sha256": _sha256(submissions / "manifest.json"),
        },
        "excluded_index": str(source / "shards/*/excluded.parquet"),
        "dedup_membership": str(source / "dedup-membership.parquet"),
        "semantics": (
            "All broad candidates preserved; tiers do not establish relevance."
        ),
    }
    contract = hashlib.sha256(
        json.dumps(contract_data, sort_keys=True).encode()
    ).hexdigest()
    manifest = {**contract_data, "contract_sha256": contract}
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        if not resume or json.loads(manifest_path.read_text()) != manifest:
            raise ValueError("Correction contract changed; use a fresh output")
    else:
        if output.exists() and any(output.iterdir()):
            raise ValueError("Correction output has no manifest")
        output.mkdir(parents=True, exist_ok=True)
        _write_json(manifest_path, manifest)
    shards = output / "shards"
    shards.mkdir(exist_ok=True)
    totals: dict[str, int] = {}
    with duckdb.connect(
        config={
            "threads": 4,
            "memory_limit": "2GB",
            "max_temp_directory_size": "4GB",
            "temp_directory": str(output / ".spill"),
        }
    ) as con:
        con.execute("SET enable_progress_bar=false")
        if submissions is not None:
            sec_manifest = TypeAdapter(dict[str, object]).validate_json(
                (submissions / "manifest.json").read_bytes()
            )
            records = TypeAdapter(list[dict[str, object]]).validate_python(
                sec_manifest["records"]
            )
            for record in records:
                path = submissions / str(record["path"])
                if _sha256(path) != record["sha256"]:
                    raise ValueError(f"SEC submission checksum differs: {path}")
        catalog = _catalog(parent.company_references, submissions)
        with TemporaryDirectory(dir=output) as temporary:
            path = Path(temporary) / "catalog.json"
            _write_json(path, catalog)
            con.execute(
                "CREATE TEMP TABLE catalog AS SELECT * FROM read_json(?)", [str(path)]
            )
        con.execute(
            _AUTHORITIES,
            {"membership": str(parent.company_references["membership"].path)},
        )
        catalog_path = output / "catalog.parquet"
        catalog_temporary = output / "catalog.parquet.tmp"
        con.execute(
            "COPY catalog TO $path (FORMAT PARQUET, COMPRESSION ZSTD)",
            {"path": str(catalog_temporary)},
        )
        if catalog_path.exists():
            if _sha256(catalog_path) != _sha256(catalog_temporary):
                raise ValueError("Catalog output differs from the verified references")
            catalog_temporary.unlink()
        else:
            os.replace(catalog_temporary, catalog_path)
        inputs = sorted(source.glob("shards/*/retained.parquet"))
        if not inputs:
            raise ValueError("Broad CPU index has no retained source shards")
        for index, path in enumerate(inputs):
            destination = shards / path.parent.name
            input_hash = _sha256(path)
            baseline_outputs = TypeAdapter(dict[str, str]).validate_python(
                json.loads((path.parent / "completed.json").read_text())["outputs"]
            )
            if input_hash != baseline_outputs["retained.parquet"]:
                raise ValueError(f"Broad candidate checksum differs: {path}")
            if destination.exists():
                completed = _Completed.model_validate_json(
                    (destination / "completed.json").read_bytes()
                )
                if (
                    completed.contract_sha256 != contract
                    or completed.input_sha256 != input_hash
                    or completed.output_sha256
                    != _sha256(destination / "retained.parquet")
                ):
                    raise ValueError(f"Correction checkpoint differs: {destination}")
            else:
                with TemporaryDirectory(dir=shards) as temporary:
                    staging = Path(temporary) / "result"
                    staging.mkdir()
                    counts = _correct_source(con, path, staging / "retained.parquet")
                    completed = _Completed(
                        contract_sha256=contract,
                        input_sha256=input_hash,
                        output_sha256=_sha256(staging / "retained.parquet"),
                        counts=counts,
                    )
                    _write_json(staging / "completed.json", completed.model_dump())
                    os.replace(staging, destination)
            for key, count in completed.counts.items():
                totals[key] = totals.get(key, 0) + count
            typer.echo(
                f"Corrected {index + 1}/{len(inputs)}: "
                f"{totals['primary_discovery_articles']:,} "
                "title/body discovery articles"
            )
    if totals["articles"] != baseline_summary.retained_rows:
        raise ValueError("Corrected article counts differ from the completed baseline")
    _write_json(
        output / "summary.json",
        {
            "status": "complete",
            **totals,
            "source_files": len(inputs),
            "source_rows": baseline_summary.source_rows,
            "retained_rows": totals["articles"],
            "excluded_rows": baseline_summary.excluded_rows,
            "deferred_articles": totals["articles"]
            - totals["primary_discovery_articles"],
            "elapsed_seconds": time.monotonic() - started,
            "contract_sha256": contract,
            "semantics": (
                "Discovery tiers preserve all broad candidates and deferred records."
            ),
        },
    )
