"""Test construction of daily portfolio returns."""

import duckdb
import pytest
from pipeline.stages.research.experiments.lopez_lira_tang.portfolios import (
    build_portfolio_days,
    portfolio_metrics,
)


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
        build_portfolio_days(db)
        daily = db.sql(
            "SELECT gross_exposure,portfolio_return FROM daily ORDER BY session"
        ).fetchall()
        metrics = portfolio_metrics(db)
        summary = dict(zip(metrics.columns, metrics.fetchall()[0], strict=True))

    # Assert
    assert daily == [(0, 0), (1, 0.02), (2, 0.04), (0, None)]
    assert summary["evaluated_days"] == 3
    assert summary["hit_rate"] == pytest.approx(2 / 3)
    assert summary["mean_return"] == pytest.approx(0.02)
    assert summary["annualized_sharpe"] == pytest.approx(252**0.5)
