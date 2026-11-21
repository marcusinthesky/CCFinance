"""Test the replication's fitting and portfolio-day rules."""

import csv
from datetime import date
from pathlib import Path

import duckdb
import pytest
from pipeline.stages.research.experiments.lopez_lira_tang import (
    _portfolio_days,
    _portfolio_metrics,
    fit_disposition,
    fit_lopez_probes,
    training_start,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("train", "test", "labels", "expected"),
    [
        (99, 5, {-1, 1}, "insufficient_training"),
        (100, 5, {-1, 1}, "fit"),
        (100, 0, {-1, 1}, "empty_test_month"),
        (100, 5, {1}, "single_class"),
        (100, 5, {-1, 0}, "no_positive_class"),
    ],
)
def test_fit_boundaries(train: int, test: int, labels: set[int], expected: str) -> None:
    """Use the observed sign classes and the minimum-100 rule."""
    # Arrange
    month = date(2021, 10, 1)

    # Act
    decision = fit_disposition(train, test, labels)

    # Assert
    assert decision == expected
    assert training_start(month) == date(2021, 3, 31)


@pytest.mark.integration
def test_monthly_prediction_uses_only_observable_training_labels(
    tmp_path: Path,
) -> None:
    """Change a future return and preserve October's signs and fitted probabilities."""
    # Arrange
    with duckdb.connect() as db:
        db.execute(
            """
            CREATE TABLE sample AS
            SELECT i::VARCHAR id, i+100 AS cik, concat('T',i) ticker,
                   CASE WHEN i<101 THEN DATE '2021-09-30' WHEN i=101 THEN DATE
                       '2021-10-04'
                        ELSE DATE '2021-12-01' END AS session,
                   TIMESTAMP '2021-09-30 12:00' AS published_at,
                   TIMESTAMP '2021-09-30 12:01' AS captured_at,
                   CASE WHEN i<100 THEN TIMESTAMP '2021-09-30 20:00'
                        ELSE TIMESTAMP '2021-12-01 20:00' END AS label_observed_at,
                   true AS title_named, CASE WHEN i%2=0 THEN 0.01 ELSE -0.01 END AS
                       reaction,
                   CASE WHEN i%2=0 THEN 0.01 ELSE -0.01 END AS drift,
                   [CASE WHEN i%2=0 THEN 1.0 ELSE -1.0 END] ||
                       list_resize([]::DOUBLE[],767,0.0) AS embedding
            FROM range(103) t(i)
            """
        )
        initial = tmp_path / "before"
        revised = tmp_path / "after"
        initial.mkdir()
        revised.mkdir()
        db.table("sample").write_parquet(str(initial / "sample.parquet"))
        db.execute(
            "UPDATE sample SET reaction=0.5, drift=-0.5 WHERE id IN ('100','102')"
        )
        db.table("sample").write_parquet(str(revised / "sample.parquet"))

    # Act
    for path in (initial, revised):
        fit_lopez_probes(path, path, prediction_end="2021-12-31")

    # Assert
    october_runs: list[list[dict[str, str]]] = []
    for path in (initial, revised):
        with (path / "predictions.csv").open() as predictions:
            october_runs.append(
                [
                    row
                    for row in csv.DictReader(predictions)
                    if row["month"] == "2021-10-01"
                ]
            )
        with (path / "windows.csv").open() as windows:
            audit = list(csv.DictReader(windows))
        assert [
            row["disposition"]
            for row in audit
            if row["target"] == "reaction" and row["sample"] == "body"
        ] == ["fit", "empty_test_month", "fit"]
        assert audit[0]["last_label_observed_at"] == "2021-09-30 20:00:00"
    assert len(october_runs[0]) == 4
    assert october_runs[0] == october_runs[1]
    assert all(row["training_rows"] == "100" for row in october_runs[0])


@pytest.mark.component
def test_daily_returns_use_only_first_story_and_minimum_two_per_leg() -> None:
    """Include zero-leg evaluated days in the metric denominator."""
    # Arrange
    with duckdb.connect() as db:
        db.execute(
            """
            CREATE TABLE sessions AS SELECT * FROM (VALUES
               (DATE '2022-01-03'),(DATE '2022-01-04'),(DATE '2022-01-05'),(DATE
                   '2022-01-06')
            ) t(session);
            CREATE TABLE windows AS SELECT 'body' AS sample, 'drift' AS target, DATE
                '2022-01-01' AS month,
                 DATE '2022-01-31' test_end, 'fit' disposition;
            CREATE TABLE predictions AS
            SELECT 'body' AS sample, 'drift' AS target, session, cik, cik::VARCHAR
                ticker,
                TIMESTAMP '2022-01-01' + id * INTERVAL '1 hour' AS published_at,
                TIMESTAMP '2022-01-01' AS captured_at, id, predicted_sign,
                    realized_return
            FROM (VALUES
              (DATE '2022-01-03',1,1,1,0.5),
              (DATE '2022-01-04',1,2,1,0.01),(DATE '2022-01-04',2,3,1,0.03),
              (DATE '2022-01-04',1,4,-1,0.5),
              (DATE '2022-01-05',1,5,1,0.01),(DATE '2022-01-05',2,6,1,0.03),
              (DATE '2022-01-05',3,7,-1,-0.01),(DATE '2022-01-05',4,8,-1,-0.03)
            ) t(session,cik,id,predicted_sign,realized_return)
            """
        )

        # Act
        _portfolio_days(db)
        daily = db.sql(
            "SELECT gross_exposure,portfolio_return FROM daily ORDER BY session"
        ).fetchall()
        metrics = _portfolio_metrics(db)
        summary = dict(zip(metrics.columns, metrics.fetchall()[0], strict=True))

    # Assert
    assert daily == [(0, 0), (1, 0.02), (2, 0.04), (0, None)]
    assert summary["evaluated_days"] == 3
    assert summary["hit_rate"] == pytest.approx(2 / 3)
    assert summary["mean_return"] == pytest.approx(0.02)
    assert summary["annualized_sharpe"] == pytest.approx(252**0.5)
