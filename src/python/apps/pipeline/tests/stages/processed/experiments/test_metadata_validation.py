"""Check pilot exclusion, sample weights and paired audit membership."""

from pathlib import Path

import duckdb
import pytest
from pipeline.stages.processed.experiments.metadata_validation import (
    sample_metadata_confirmation,
)


@pytest.mark.integration
def test_confirmation_excludes_pilot_and_keeps_negative_windows(tmp_path: Path) -> None:
    # Arrange a frame with one pilot and equal numbers of positive and empty windows.
    for name in ("articles", "mentions"):
        (tmp_path / name).mkdir()
    with duckdb.connect() as con:
        con.sql("SELECT range AS id, true AS usable FROM range(17)").write_parquet(
            str(tmp_path / "quality.parquet")
        )
        con.sql("SELECT 0 AS id").write_parquet(str(tmp_path / "pilot.parquet"))
        con.sql("""SELECT range AS id, 'reporting' AS article_form,
                [{'start':0,'stop':12,'event_family':[range%2]}] AS windows
                FROM range(17)""").write_parquet(str(tmp_path / "articles/u.parquet"))
        con.sql("""SELECT range AS id, 0 AS start, 4 AS stop, 'company' AS entity_type,
                [1.0,0.0] AS financial_sentiment FROM range(17)""").write_parquet(
            str(tmp_path / "mentions/u.parquet")
        )

    # Act on the production sampling command.
    path = tmp_path / "confirmation.parquet"
    sample_metadata_confirmation(
        tmp_path / "quality.parquet", tmp_path, tmp_path / "pilot.parquet", path, size=8
    )

    # Assert inclusion weights reconstruct frame totals and both audits share a draw.
    with duckdb.connect() as con:
        con.read_parquet(str(path)).create_view("sample")
        assert con.sql("SELECT count(*) FROM sample WHERE id='0'").fetchone() == (0,)
        assert con.sql("""SELECT DISTINCT count(*),sum(audit::INT),sum(population/draws)
                       FROM sample GROUP BY frame""").fetchall() == [(8, 2, 16.0)]
        assert con.sql("""SELECT count(*) FROM sample WHERE frame='window'
                       AND stratum='empty'""").fetchone() == (4,)
