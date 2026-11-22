from datetime import date
from math import log, sqrt
from pathlib import Path

import duckdb
import pytest
from pipeline.stages.processed.experiments.baker_emv.market import (
    prepare_baker_emv_market,
)


@pytest.mark.integration
def test_market_uses_preceding_close_and_trading_day_rms(tmp_path: Path) -> None:
    # Arrange
    source = tmp_path / "market.csv"
    source.write_text(
        "observation_date,VIXCLS,SP500\n"
        "2020-01-30,44,100\n"
        "2020-01-31,55,200\n"
        "2020-02-03,10,220\n"
        "2020-02-04,.,\n"
        "2020-02-05,20,242\n"
        "2020-02-17,99,\n"
        "2020-03-02,30,121\n"
    )
    window = tmp_path / "window.json"
    window.write_text('{"start":"2020-02-01","end":"2020-03-01"}')
    output = tmp_path / "market"

    # Act
    prepare_baker_emv_market(source, window, output)
    with duckdb.connect() as con:
        daily = con.execute(
            "SELECT day, study_day FROM read_parquet(?) ORDER BY day",
            [str(output / "daily_market.parquet")],
        ).fetchall()
        market = con.execute(
            """
            SELECT vix_days, return_days, vix, realized_volatility
            FROM read_parquet(?) ORDER BY month
            """,
            [str(output / "monthly_market.parquet")],
        ).fetchall()

    # Assert
    assert daily == [
        (date(2020, 1, 31), False),
        (date(2020, 2, 3), True),
        (date(2020, 2, 5), True),
        (date(2020, 2, 17), True),
        (date(2020, 3, 2), True),
    ]
    assert market[0] == pytest.approx((2, 2, 15, 100 * sqrt(252) * log(1.1)))
    assert market[1] == pytest.approx((1, 1, 30, 100 * sqrt(252) * log(2)))
