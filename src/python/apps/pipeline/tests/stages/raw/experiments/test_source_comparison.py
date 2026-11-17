"""Exercise metadata preparation and duplicate-safe acquisition locally."""

import json
from pathlib import Path

import duckdb
import pytest
import yaml
from pipeline.cli import app
from pipeline.experiments.source_comparison import FileRecord
from pipeline.stages.raw.experiments import source_comparison
from typer.testing import CliRunner


@pytest.mark.integration
def test_prepared_groups_drive_acquisition_without_duplicate_payloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: two groups force repeated draws; mock only the remote inventory.
    source = tmp_path / "source.parquet"
    with duckdb.connect() as con:
        con.execute(
            """COPY (SELECT i::VARCHAR AS id, 'article-' || i AS text,
                struct_pack(url_hostname := 'example.com',
                    url := 'https://example.com/' || i) AS metadata,
                repeat('excluded media', 100) AS media
                FROM range(4096) AS rows(i)) TO $target
                (FORMAT PARQUET, ROW_GROUP_SIZE 2048)""",
            {"target": str(source)},
        )
    domains = tmp_path / "domains.csv"
    domains.write_text("domain\nexample.com\n", encoding="utf-8")
    params = tmp_path / "params.yaml"
    revision = "0" * 40
    dataset = {"source": f"hf://datasets/example/source@{revision}/data/*.parquet"}
    config: dict[str, object] = {"seed": 42, "draws": 4, "domains": str(domains)}
    config["datasets"] = {"fine_news": dataset}
    params.write_text(yaml.safe_dump({"experiments": {"source_comparison": config}}))
    monkeypatch.setattr(
        source_comparison,
        "source_files",
        lambda _: [
            FileRecord(file=str(source), size=source.stat().st_size, identity="x")
        ],
    )
    monkeypatch.setattr(source_comparison, "check_range", lambda _: 8)
    manifests = tmp_path / "manifest"
    samples = tmp_path / "sample"
    runner = CliRunner()

    # Act: prepare through the public CLI, then acquire only its planned intervals.
    common = ("--dataset", "fine_news", "--params", str(params))
    prepared = runner.invoke(
        app,
        ["stages", "raw", "prepare-comparison", *common, "--output", str(manifests)],
    )
    assert prepared.exit_code == 0, prepared.output
    acquired = runner.invoke(
        app,
        [
            *("stages", "raw", "sample-comparison", *common),
            *("--manifest", str(manifests / "manifest.json")),
            *("--output", str(samples)),
        ],
    )

    # Assert: probabilities and physical payloads preserve the replacement design.
    assert acquired.exit_code == 0, acquired.output
    selection = json.loads((manifests / "manifest.json").read_text())
    counts = json.loads((samples / "counts.json").read_text())
    assert len(selection["draws"]) == len(counts["draws"]) == 4
    assert all(draw["probability"] == 0.5 for draw in selection["draws"])
    unique = {draw["row_group"] for draw in selection["draws"]}
    assert len(list(samples.glob("*.parquet"))) == len(unique)
    assert all(
        draw["input_rows"] == draw["matched_rows"] == 2048 for draw in counts["draws"]
    )
    assert counts["network_bytes"] is None
    with duckdb.connect() as con:
        result = con.execute(
            "SELECT count(*), count(DISTINCT source_row) FROM read_parquet(?)",
            [str(samples / "*.parquet")],
        ).fetchone()
    assert result is not None
    rows, distinct_rows = result
    assert rows == distinct_rows == 2048 * len(unique)
