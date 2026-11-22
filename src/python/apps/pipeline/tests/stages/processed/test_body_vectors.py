"""Check article and vector identity at the Parquet boundary."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.stages.processed.body_vectors import verify_body_vectors


@pytest.mark.integration
@pytest.mark.parametrize("fault", ["none", "missing", "duplicate", "order", "blank"])
def test_vector_alignment(tmp_path: Path, fault: str) -> None:
    # Arrange a two-row source and a vector group with a controlled discrepancy.
    source = tmp_path / "source"
    source.mkdir()
    group = tmp_path / "vectors" / "part.parquet"
    group.mkdir(parents=True)
    (source / "provenance.json").write_text(
        json.dumps(
            {
                "records": 2,
                "revision": "fixture",
                "shards": [{"path": "part.parquet", "records": 2}],
            }
        )
    )
    with duckdb.connect() as con:
        con.execute("CREATE TABLE docs (id VARCHAR, text VARCHAR)")
        con.executemany(
            "INSERT INTO docs VALUES (?, ?)",
            [("a", "hello"), ("a" if fault == "duplicate" else "b", " \t")],
        )
        con.table("docs").write_parquet(str(source / "part.parquet"))
        con.execute("CREATE TABLE vec (id VARCHAR, embedding FLOAT[], has_text BOOL)")
        con.execute(
            "INSERT INTO vec VALUES (?, list_concat([1.0], repeat([0.0], 767)), true)",
            ["b" if fault == "order" else "a"],
        )
        if fault != "missing":
            con.execute(
                "INSERT INTO vec VALUES (?, repeat([0.0], 768), ?)",
                ["a" if fault == "order" else "b", fault == "blank"],
            )
        con.execute(
            """COPY vec TO $path (FORMAT PARQUET, KV_METADATA {
              model:'google/embeddinggemma-300m',
              revision:'57c266a740f537b4dc058e1b0cda161fd15afa75',
              prefix:'title: none | text: ', max_tokens:'2048'})""",
            {"path": str(group / "group-0000.parquet")},
        )

    # Act and assert that only a fully aligned corpus produces a report.
    report = tmp_path / "report.json"
    if fault == "none":
        verify_body_vectors(source, group.parent, report)
        assert json.loads(report.read_text())["nonblank"] == 1
    else:
        with pytest.raises(ValueError, match=r"source IDs|Vector alignment"):
            verify_body_vectors(source, group.parent, report)
        assert not report.exists()
