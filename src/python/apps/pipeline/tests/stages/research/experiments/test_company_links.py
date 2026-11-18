"""Check weighted link estimates against hand-computed values."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.cli import app
from pipeline.stages.research.experiments.company_links import domain, kappa, ratio
from typer.testing import CliRunner


@pytest.mark.unit
def test_kappa_discounts_chance_agreement() -> None:
    # Arrange: three of four repeated judgements agree.
    pairs = [("a", "a"), ("a", "b"), ("b", "b"), ("b", "b")]

    # Act: compute Cohen's kappa.
    value = kappa(pairs)

    # Assert: observed 0.75 against 0.5 expected by chance.
    assert value == pytest.approx(0.5)


@pytest.mark.unit
def test_ratio_weights_strata_and_domains_keep_full_sample_weights() -> None:
    # Arrange: a small stratum at 50% and a large one at 100%; a cross-cutting group.
    rows = [
        {"stratum": "small", "population": 100, "y": y, "group": g}
        for y, g in ((0.0, "a"), (1.0, "b"))
    ] + [{"stratum": "large", "population": 300, "y": 1.0, "group": "a"}] * 2

    # Act: estimate the population share, and the share within group "a".
    overall = ratio(rows, lambda row: row["y"], lambda _: 1.0)
    within = domain(
        rows, lambda r: float(r["group"] == "a"), lambda r: r["y"], lambda _: 1.0
    )

    # Assert: (100 * 0.5 + 300) / 400, and (50 * 0 + 300) / (50 + 300) for "a".
    assert overall["estimate"] == pytest.approx(0.875)
    assert overall["standard_error"] == pytest.approx(
        (100**2 * (1 - 2 / 100) * 0.5 / 2) ** 0.5 / 400
    )
    assert within["estimate"] == pytest.approx(300 / 350)


SAMPLE = [
    ("m1", "one:head", 100, "apple", 1, "alias", "2019-05-01", "listed", 1),
    ("m2", "one:head", 100, "delta", 2, "alias", "2019-05-01", "listed", 3),
    ("m3", "several:head", 300, "apple", 1, "anchor", "2019-05-01", "listed", 1),
    ("m4", "several:head", 300, "apple", 1, "anchor", "2019-05-01", "listed", 1),
    (
        "m5",
        "none:tail",
        50,
        "acme",
        None,
        "unresolved",
        "2019-05-01",
        "not_listed",
        None,
    ),
    ("m6", "none:tail", 50, "walmart", None, "unresolved", "2021-03-01", "listed", 4),
]
JUDGEMENTS = [
    ("repeat", "m1", "listed", 1),
    ("audit", "m1", "listed", 1),
    ("audit", "m3", "listed", 1),
    ("audit", "m5", "not_company", None),
]


def _fixture(root: Path) -> list[str]:
    for folder in ("sample", "labels", "links/mentions", "links/articles", "issuers"):
        (root / folder).mkdir(parents=True)
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE sample (id VARCHAR, start INTEGER, stratum VARCHAR, "
            "population INTEGER, key VARCHAR, cik BIGINT, method VARCHAR, "
            "day DATE, link_score DOUBLE, split VARCHAR DEFAULT 'test')"
        )
        con.executemany(
            "INSERT INTO sample VALUES (?, 0, ?, ?, ?, ?, ?, ?, "
            "CASE WHEN ? = 'alias' THEN 0.9 WHEN ? = 'anchor' THEN 1.0 END, ?)",
            [
                (prefix + i, s, n, k, c, m, d, m, m, split)
                for prefix, split in (("", "test"), ("dev-", "dev"))
                for i, s, n, k, c, m, d, *_ in SAMPLE
            ],
        )
        con.table("sample").write_parquet(str(root / "sample/mentions.parquet"))
        con.table("sample").write_parquet(str(root / "links/mentions/u.parquet"))
        con.sql(
            "SELECT unnest(['a1', 'a2']) AS id, 'test' AS split, "
            "DATE '2019-05-01' AS day"
        ).write_parquet(str(root / "sample/articles.parquet"))
        con.sql(
            "SELECT id, cik, 0.9 AS link_score "
            "FROM (VALUES ('a1', 1), ('a2', 1), ('a2', 2)) AS t(id, cik)"
        ).write_parquet(str(root / "links/articles/u.parquet"))
        con.sql("SELECT 1 AS cik, 'Apple Inc.' AS name").write_parquet(
            str(root / "issuers/issuers.parquet")
        )
        con.sql(
            "SELECT *, NULL::DATE AS valid_from, NULL::DATE AS valid_to "
            "FROM (VALUES (1, 'AAPL'), (2, 'DAL'), (3, 'DLA')) AS t(cik, ticker)"
        ).write_parquet(str(root / "issuers/tickers.parquet"))
    labels = [
        {"id": prefix + i, "start": 0, "judge": "primary", "decision": d, "cik": c}
        | {"role": "subject", "rationale": "r"}
        for prefix in ("", "dev-")
        for i, *_, d, c in SAMPLE
    ] + [
        {"id": i, "start": 0, "judge": j, "decision": d, "cik": c}
        for j, i, d, c in JUDGEMENTS
    ]
    (root / "labels/mentions.jsonl").write_text(
        "".join(json.dumps(label) + "\n" for label in labels)
    )
    gold = [
        {"id": "a1", "judge": "primary", "issuers": [{"cik": 1, "role": "subject"}]},
        {
            "id": "a2",
            "judge": "primary",
            "issuers": [
                {"cik": 2, "role": "subject"},
                {"cik": 9, "role": "source_or_venue"},
            ],
        },
    ]
    (root / "labels/articles.jsonl").write_text(
        "".join(json.dumps(label) + "\n" for label in gold)
    )
    arguments = ["stages", "research", "report-company-links"]
    for option in ("sample", "labels", "links", "issuers"):
        arguments += [f"--{option}", str(root / option)]
    return arguments


@pytest.mark.integration
def test_report_estimates_precision_recall_and_judge_reliability(
    tmp_path: Path,
) -> None:
    # Arrange: six labelled mentions in three strata per split, judges, articles.
    arguments = _fixture(tmp_path)
    strict = [*arguments, "--threshold", "0.95", "--output", str(tmp_path / "strict")]

    # Act: report at the default threshold and at a stricter one.
    result = CliRunner().invoke(app, [*arguments, "--output", str(tmp_path / "out")])
    stricter = CliRunner().invoke(app, strict)

    # Assert: weighted estimates, domains, kappas and gates match hand values.
    assert result.exit_code == 0, result.output
    assert stricter.exit_code == 0, stricter.output
    metrics = json.loads((tmp_path / "out/metrics.json").read_text())
    estimates = metrics["test"]["estimates"]
    assert (
        metrics["dev"]["estimates"]["link_precision"] == (estimates["link_precision"])
    )
    pooled = metrics["pooled"]["estimates"]["link_precision"]
    assert pooled["estimate"] == pytest.approx(estimates["link_precision"]["estimate"])
    assert pooled["n"] == 2 * estimates["link_precision"]["n"]
    assert estimates["link_precision"]["estimate"] == pytest.approx(350 / 400)
    assert estimates["recall"]["estimate"] == pytest.approx(350 / 425)
    assert estimates["nil_precision"]["estimate"] == pytest.approx(0.5)
    assert estimates["ambiguous_precision"]["estimate"] == 1.0
    assert estimates["article_precision"]["estimate"] == pytest.approx(2 / 3)
    assert estimates["article_recall"]["estimate"] == 1.0
    assert estimates["article_recall_mentioned"]["estimate"] == 1.0
    assert metrics["test"]["by_method"]["alias"]["estimate"] == pytest.approx(0.5)
    assert metrics["test"]["by_year"]["2021"]["recall"]["estimate"] == 0.0
    judge = metrics["adjudicator"]
    assert (judge["anchor_agreement"], judge["repeat_kappa"]) == (1.0, 1.0)
    assert judge["anchors"] == 4
    assert judge["anchor_ci95_low"] == pytest.approx(0.025**0.25)
    assert judge["anchor_ci95_high"] == 1.0
    assert judge["audit_kappa"] == 1.0
    assert judge["audit_kappa_full_decision"] == pytest.approx(0.4)
    assert [gate["passed"] for gate in metrics["gates"].values()] == [
        False, True, True, True, True,
    ]  # fmt: skip
    strict_metrics = json.loads((tmp_path / "strict/metrics.json").read_text())
    strict_estimates = strict_metrics["test"]["estimates"]
    assert strict_estimates["link_precision"]["estimate"] == 1.0
    assert strict_estimates["recall"]["estimate"] == pytest.approx(300 / 425)
    errors = (tmp_path / "out/errors.csv").read_text().splitlines()
    assert errors[1].startswith("false_negative,walmart,25.0,1")
    assert errors[2].startswith("false_positive,delta,50.0,1")
    summary = (tmp_path / "out/summary.tex").read_text()
    assert "Mention precision & 0.875" in summary
    assert r"\multicolumn{2}{c}{Pooled}" in summary
    assert "Judge agreement with explicit tickers & 1.000 [0.398, 1.000] & 4" in summary
