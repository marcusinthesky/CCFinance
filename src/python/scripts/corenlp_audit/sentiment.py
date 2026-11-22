"""Score paired company and sentence sentiment against blinded mention judgments."""

import csv
import json

import numpy as np
from prepare import META, RESULT, WORK, write_rows

DIRECTION = ("positive", "negative", "neutral")


def main() -> None:
    """Pool weighted confusion counts and cluster paired uncertainty by article."""
    rows = [json.loads(s) for s in (WORK / "units.jsonl").read_text().splitlines()]
    root = dict(
        csv.reader((WORK / "sentiment.tsv").read_text().splitlines(), delimiter="\t")
    )
    terra = {
        r["tag"]: r["label"]
        for r in csv.DictReader((WORK / "terra-sentiment.csv").open())
    }
    if set(root) != {r["tag"] for r in rows} or len(root) != 400 or len(terra) != 40:
        raise ValueError("Incomplete sentiment run")
    mapping = {
        "Positive": "positive",
        "Very positive": "positive",
        "Negative": "negative",
        "Very negative": "negative",
        "Neutral": "neutral",
        "no_containing_sentence": "unscored",
        "over_200_tokens": "unscored",
    }
    archived = {}
    for file in (META / "validation-labels/audit").glob("*.json"):
        record = json.loads(file.read_text())
        if record["frame"] == "mention":
            if record["model"] != "openai-codex:gpt-6.1-terra":
                raise ValueError("Unexpected archived audit judge")
            archived[record["id"], record["start"], record["stop"]] = record["label"][
                "sentiment"
            ]
    for r in rows:
        r["archived_terra"] = archived.get((r["id"], r["start"], r["stop"]))
        r["root"] = root[r["tag"]]
        r["stanford"] = mapping[r["root"]]
        r["terra"] = terra.get(r["tag"])
    write_rows(RESULT / "sentiment-pairs.jsonl", rows)
    gold = np.array([r["ref"] for r in rows])
    pred = {m: np.array([r[m] for r in rows]) for m in ("gliner", "stanford")}
    w = np.array([r["weight"] for r in rows])
    direction = np.isin(gold, DIRECTION)
    ids = np.unique([r["id"] for r in rows], return_inverse=True)[1]
    strata = np.array([r["stratum"] for r in rows])
    rng = np.random.default_rng(46)
    boost = rng.exponential(size=(2000, ids.max() + 1))[:, ids] * w
    for name in np.unique(strata):
        mask = strata == name
        boost[:, mask] *= w[mask].sum() / boost[:, mask].sum(axis=1)[:, None]
    weights = np.vstack([w, boost])
    values = {}
    macro = {}
    reversals = {}
    for model, labels in pred.items():
        metrics = {}
        f1 = []
        for label in DIRECTION:
            positive = direction & (labels == label)
            ref = gold == label
            hits = weights[:, ref & positive].sum(axis=1)
            selected = weights[:, positive].sum(axis=1)
            actual = weights[:, ref].sum(axis=1)
            f1.append(2 * hits / (selected + actual))
            metrics[label] = {
                "precision": float(hits[0] / selected[0]) if selected[0] else None,
                "recall": float(hits[0] / actual[0]),
                "f1": float(f1[-1][0]),
            }
        macro[model] = np.mean(f1, axis=0)
        flip = ((gold == "negative") & (labels == "positive")) | (
            (gold == "positive") & (labels == "negative")
        )
        reversals[model] = weights[:, flip].sum(axis=1) / weights[:, direction].sum(
            axis=1
        )
        values[model] = {
            "classes": metrics,
            "macro_f1": float(macro[model][0]),
            "polarity_reversal": float(reversals[model][0]),
        }
    summary = {
        "n": len(rows),
        "directional": int(direction.sum()),
        "systems": values,
        "root_counts": {
            s: list(root.values()).count(s) for s in sorted(set(root.values()))
        },
        "reference": {
            s: {
                "n": int(sum(gold == s)),
                "weighted_share": w[gold == s].sum() / w.sum(),
            }
            for s in sorted(set(gold))
        },
        "terra": {
            "n": len(terra),
            "agree": sum(r["ref"] == r["terra"] for r in rows if r["terra"]),
        },
    }
    repeat = [r for r in rows if r["terra"]]
    summary["terra"]["invalid"] = sum(r["terra"] == "invalid span" for r in repeat)
    summary["terra"]["reference_counts"] = {
        label: sum(r["terra"] == label for r in repeat)
        for label in sorted(set(terra.values()))
    }
    repeat_direction = [r for r in repeat if r["terra"] in DIRECTION]
    summary["terra"]["directional"] = len(repeat_direction)
    summary["terra"]["directional_hits"] = {
        model: sum(r[model] == r["terra"] for r in repeat_direction)
        for model in ("gliner", "stanford", "ref")
    }
    panel = [r for r in rows if r["archived_terra"] in DIRECTION]
    if len(archived) != 100:
        raise ValueError("Incomplete archived Terra audit")

    def panel_f1(model: str, panel_rows: list[dict], reference: str) -> float:
        f1 = []
        for label in DIRECTION:
            gold_weight = sum(r["weight"] for r in panel_rows if r[reference] == label)
            pred_weight = sum(r["weight"] for r in panel_rows if r[model] == label)
            hits = sum(
                r["weight"] for r in panel_rows if r[reference] == r[model] == label
            )
            f1.append(2 * hits / (gold_weight + pred_weight))
        return float(np.mean(f1))

    summary["archived_terra"] = {
        "n": len(archived),
        "directional": len(panel),
        "macro_f1": {m: panel_f1(m, panel, "archived_terra") for m in pred},
    }
    summary["terra"]["macro_f1"] = {
        m: panel_f1(m, repeat_direction, "terra") for m in pred
    }
    for name, array in (("macro_f1", macro), ("polarity_reversal", reversals)):
        diff = array["gliner"] - array["stanford"]
        summary["delta_" + name] = [
            float(diff[0]),
            *np.quantile(diff[1:], [0.025, 0.975]).tolist(),
        ]
    (RESULT / "sentiment.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
