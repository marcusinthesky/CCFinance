"""Entity steering checks independent of external judges or encoder weights."""

from pathlib import Path

import numpy as np
import pytest
from pipeline.experiments.entity_focus import render, visible
from pipeline.stages.processed.experiments.entity_focus import Summary, validate_summary
from pipeline.stages.research.experiments.entity_focus import measure
from pydantic_ai import ModelRetry


@pytest.mark.component
def test_switch_and_mask() -> None:
    """Switch only the focal designation in a shared bid sentence."""
    body = "One bids for Two."
    firms = [
        {
            "name": n,
            "ticker": None,
            "spans": [{"start": body.index(n), "stop": body.index(n) + 3}],
        }
        for n in ("One", "Two")
    ]
    row = {"title": "Bid", "body": body, "firms": firms}
    for firm in firms:
        text, mapping = render(row, firm, "open", "marked", [(0, len(body))])
        assert "<focus>" + firm["name"] + "</focus>" in text
        assert (
            text.split("\n")[-1].replace("<focus>", "").replace("</focus>", "") == body
        )
        assert not visible(13, 16, mapping, 1)
        assert visible(0, len(body), mapping, len(text))
    for arm in ("plain", "header", "sentences"):
        a, _ = render(row, firms[0], "gemma", arm, [(0, len(body))])
        b, _ = render(row, firms[1], "gemma", arm, [(0, len(body))])
        assert (a == b) == (arm == "plain")
    summary = Summary(
        status="supported",
        named="One made an offer.",
        masked="The focal company bid.",
        quote=body,
    )
    assert validate_summary(summary, row) == summary
    for invalid in ({"quote": "invented"}, {"masked": "One made an offer."}):
        with pytest.raises(ModelRetry):
            validate_summary(summary.model_copy(update=invalid), row)
    for status in ("incidental", "wrong_issuer", "insufficient"):
        assert (
            validate_summary(
                Summary(status=status, named=None, masked=None, quote=None), row
            ).status
            == status
        )


@pytest.mark.component
def test_rank_switch() -> None:
    """Two distinct roles must each beat the opposite account."""
    a, b = np.eye(2)
    assert measure([a, b], [a, b], a)["both"] == 1
    assert measure([b, a], [a, b], a)["individual"] == 0
    assert measure([a, a], [a, b], a)["both"] == 0
    assert measure([a, b], [a, a], a)["both"] == 0


@pytest.mark.component
def test_selection_and_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Freeze template winners and recover known accuracy from vector shards."""
    import json

    import duckdb
    import pandas as pd
    from pipeline.experiments.entity_focus import ARMS
    from pipeline.stages.research.experiments import entity_focus as score

    monkeypatch.setattr(score, "ROOT", tmp_path)
    monkeypatch.setattr(score, "REPORT", tmp_path / "report")
    articles = [
        {"id": f"<urn:uuid:{i}>", "yr": 2019, "stratum": "one", "stratum_total": 100}
        for i in range(8)
    ]
    duckdb.from_df(pd.DataFrame(articles)).to_parquet(str(tmp_path / "sample.parquet"))
    for split, group in (("dev", articles[:4]), ("test", articles[4:])):
        labels = []
        for story in group:
            key = story["id"]
            labels.append(
                {
                    "id": key,
                    "luna": {"pair": {"status": "distinct"}},
                    "terra": {"pair": {"status": "distinct"}},
                }
            )
            for model in score.MODELS:
                rows = []
                for side in (0, 1):
                    own = np.eye(2)[side].tolist()
                    for arm in (
                        *ARMS,
                        "luna_masked",
                        "luna_named",
                        "terra_masked",
                        "terra_named",
                    ):
                        good = arm in ("marked", "sentences") or "_" in arm
                        rows.append(
                            {
                                "side": side,
                                "arm": arm,
                                "truncated": False,
                                "vector": own if good else [1.0, 0.0],
                            }
                        )
                folder = tmp_path / f"{split}-{model}"
                folder.mkdir(exist_ok=True)
                duckdb.from_df(pd.DataFrame(rows)).to_parquet(
                    str(folder / (key[10:-1] + ".parquet"))
                )
        (tmp_path / f"{split}-references.json").write_text(json.dumps(labels))
        score.score_entity_focus(split)
    result = json.loads((tmp_path / "report" / "decision.json").read_text())
    assert set(result["selection"].values()) == {"marked"}
    assert all(r["gain"] == 1 for r in result["paired"])
    assert not result["qualifying"]
