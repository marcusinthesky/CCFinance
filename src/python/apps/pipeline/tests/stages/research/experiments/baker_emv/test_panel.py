from datetime import date
from math import sqrt
from pathlib import Path

import duckdb
import pytest
from pipeline.stages.research.experiments.baker_emv.panel import build_baker_emv_panel


@pytest.mark.integration
def test_panel_calibration_and_lags_preserve_missing_calendar_month(
    tmp_path: Path,
) -> None:
    # Arrange
    window = tmp_path / "window.json"
    window.write_text(
        '{"start":"2023-01-01","end":"2023-04-01","calibration_end":"2023-02-01",'
        '"min_publication_days":15}'
    )
    news, market, output = (
        tmp_path / "news.parquet",
        tmp_path / "market.parquet",
        tmp_path / "panel",
    )
    with duckdb.connect() as con:
        con.execute(
            """
            COPY (SELECT host, month::DATE AS month, hit_share, publication_days
            FROM (VALUES
                ('a', '2023-01-01', 0., 20), ('a', '2023-02-01', 0.1, 20),
                ('a', '2023-04-01', 0.2, 20),
                ('b', '2023-01-01', 0.2, 20), ('b', '2023-02-01', 0.6, 20),
                ('b', '2023-04-01', 0.2, 5),
                ('constant', '2023-01-01', 0.5, 20), ('constant', '2023-02-01', 0.5, 20)
            ) AS t(host, month, hit_share, publication_days)) TO ?
            """,
            [str(news)],
        )
        con.execute(
            """
            COPY (SELECT month::DATE AS month, vix, 20 AS vix_days, 20 AS return_days,
                         vix AS realized_volatility FROM (VALUES
                ('2023-01-01', 15.), ('2023-02-01', 25.),
                ('2023-03-01', 20.), ('2023-04-01', 20.)
            ) AS t(month, vix)) TO ?
            """,
            [str(market)],
        )

    # Act
    build_baker_emv_panel(news, market, window, output)
    with duckdb.connect() as con:
        months = con.execute(
            """
            SELECT variant, month, contributing_publishers, emv, emv_lag1, emv_lag2
            FROM read_parquet(?) ORDER BY variant, month
            """,
            [str(output / "monthly_panel.parquet")],
        ).fetchall()
        scales = con.execute(
            """
            SELECT host, publisher_sd FROM read_parquet(?)
            WHERE variant = 'baseline' AND month = '2023-01-01'
            ORDER BY host
            """,
            [str(output / "coverage.parquet")],
        ).fetchall()

    # Assert
    assert [row[0] for row in scales] == ["a", "b", "constant"]
    assert [row[1] for row in scales] == pytest.approx(
        [0.1 / sqrt(2), 0.4 / sqrt(2), 0]
    )
    assert months[0][2:4] == pytest.approx((2, 20 / 3))
    assert months[1][2:4] == pytest.approx((2, 100 / 3))
    assert months[2][1:4] == (date(2023, 3, 1), 0, None)
    assert months[3][2:4] == pytest.approx((2, 100 / 3))
    assert months[3][4] is None
    assert months[3][5] == pytest.approx(100 / 3)
    assert months[7][2:4] == pytest.approx((1, 160 / 3))
