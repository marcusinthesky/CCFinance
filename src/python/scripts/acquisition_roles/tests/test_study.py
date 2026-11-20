"""Offline acceptance tests for the model-adjudicated retrieval study."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import duckdb
import pandas as pd
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.test import TestModel

from scripts.acquisition_roles import judge, report


def fake_agent(model: str, **options: object) -> Agent:
    """Use fixed structured outputs in the actual Pydantic AI validation loop."""
    return Agent(TestModel(custom_output_args=json.loads(model)), **options)


@pytest.mark.component
def test_judgment_and_resume(tmp_path: Path) -> None:
    """Verify quote grounding, rejection, abstention and cache reuse."""
    job = {
        "id": "x",
        "role": "primary",
        "ciks": [1, 2],
        "rubric": "Classify.",
        "prompt": {"title": "Report", "body": "A bid for B."},
        "model": json.dumps({"direction": "A_buys_B", "quote": "A bid for B."}),
    }
    with patch.object(judge, "Agent", fake_agent):
        record = judge.evaluate(job, tmp_path)
        assert record["start"] == 0 and record["stop"] == len("A bid for B.")
        job["model"] = json.dumps({"direction": "A_buys_B", "quote": "invented"})
        with pytest.raises(UnexpectedModelBehavior):
            judge.evaluate(job, tmp_path)
        job["role"] = "fact"
        job["model"] = json.dumps({"statement": None, "quote": None})
        assert judge.evaluate(job, tmp_path)["statement"] is None
    with patch.object(judge, "Agent", side_effect=AssertionError):
        assert judge.evaluate(job, tmp_path)["statement"] is None


@pytest.mark.component
def test_hand_scored_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify ties, swapped reference order, block inference and the go gate."""
    labels = []
    for i in range(80):
        ciks = [2 * i, 2 * i + 1]
        direction = "A_buys_B" if i < 40 else "other"
        labels.append(
            {"id": str(i), "role": "primary", "direction": direction, "ciks": ciks}
        )
        if i < 20:
            labels.extend(
                [
                    {
                        "id": str(i),
                        "role": "repeat",
                        "direction": "B_buys_A",
                        "ciks": ciks[::-1],
                    },
                    {
                        "id": str(i),
                        "role": "audit",
                        "direction": direction,
                        "ciks": ciks,
                    },
                ]
            )
    (tmp_path / "labels.json").write_text(json.dumps(labels))
    (tmp_path / "facts.json").write_text("[]")
    for model in ("open", "qwen", "gemma"):
        arms = ["query", "mentions", "fact"]
        if model != "qwen":
            arms.extend(
                a + ("-title" if model == "gemma" else "-instruct")
                for a in ("mentions", "fact")
            )
        rows = [
            {
                "id": str(i),
                "cik": 2 * i + j,
                "arm": a,
                "truncated": False,
                "vector": [1.0, 0.0]
                if a.startswith("mentions") or j == 0
                else [0.0, 1.0],
            }
            for i in range(40)
            for j in range(2)
            for a in arms
        ]
        duckdb.from_df(pd.DataFrame(rows)).to_parquet(
            str(tmp_path / (model + ".parquet"))
        )
    monkeypatch.setattr(sys, "argv", ["report", str(tmp_path), str(tmp_path / "out")])
    report.main()
    result = json.loads((tmp_path / "out/decision.json").read_text())
    assert result["decision"] == "go" and result["blocks"] == 20
    assert len(result["conditions"]) == 10
    assert result["differences"]["open/fact vs open/mentions"] == [0.5, 0.5, 0.5]
    assert report.decision(False, 1, 0.5, 0.5, 0.5) == "inconclusive"
    assert report.decision(True, 0.5, 0, 0, 0.09) == "no-go"
