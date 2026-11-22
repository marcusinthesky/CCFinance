"""Test story pairing across encoders."""

import duckdb
import pytest
from pipeline.stages.research.experiments.lopez_lira_tang.title_comparison import (
    _compare_title_predictions,
    _paired_drift_interval,
)


@pytest.mark.component
@pytest.mark.parametrize("title_id", ["common", "different"])
def test_encoder_pairing_requires_identical_story_keys(title_id: str) -> None:
    """Reject mismatched story keys and measure MiniLM minus Gemma in return units."""
    # Arrange
    with duckdb.connect() as con:
        con.execute(
            """
            CREATE TABLE daily AS
            SELECT sample, 'drift' AS target, DATE '2024-05-01' AS month,
                   DATE '2024-05-06' AS session, true AS evaluated, 2 AS positions,
                   'fit' AS disposition, 1 AS long_exposure, 0 AS short_exposure,
                   ret AS long_return, 0.0 AS short_security_return,
                   ret AS portfolio_return
            FROM (VALUES ('body',0.0),('gemma_title',0.01),('minilm_title',-0.02))
                AS fit(sample,ret)
            """
        )
        con.execute(
            """
            CREATE TABLE positions AS
            SELECT sample,target,month,session,1 AS cik,'X' AS ticker,
                   CASE WHEN sample='minilm_title' THEN ? ELSE 'common' END AS id,
                   1 AS source_rank, 100 AS training_rows, 0.01 AS realized_return,
                   1 AS realized_sign, sign(portfolio_return) AS predicted_sign,
                   0.5 AS positive_probability
            FROM daily
            """,
            [title_id],
        )

        # Act and assert
        if title_id == "different":
            with pytest.raises(ValueError, match="fixed body prediction support"):
                _compare_title_predictions(con)
        else:
            _compare_title_predictions(con)
            assert _paired_drift_interval(con, "minilm_title", "gemma_title", 21) == (
                pytest.approx(-0.03),
                pytest.approx(-0.03),
            )
