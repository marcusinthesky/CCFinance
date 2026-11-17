"""Compare CPU and CUDA FP32 predictions after the attribute-index patch."""

import json
from functools import partial

import torch
from gliner2 import AutoExtractor
from gliner_attributes import prepare_attributes
from gliner_probabilities import capture_probabilities
from gliner_schema import build_metadata_schema, build_schema, build_transaction_schema


def main() -> None:
    """Run one multi-company example on CPU and GPU with the same weights."""
    # Arrange: request entities, their roles and article type in the same schema.
    torch.set_num_threads(4)
    model = AutoExtractor.from_pretrained("/model", map_location="cpu")
    schema = build_schema(model)
    article = "Apple reported earnings. Microsoft was mentioned."

    # Act: extract the same schema before and after transferring the model.
    cpu = model.extract(article, schema, include_spans=True, include_confidence=True)
    model.to("cuda")
    gpu = model.extract(article, schema, include_spans=True, include_confidence=True)

    # Assert: both devices return the same spans and discrete role labels.
    def labels(result: dict) -> set[tuple]:
        return {
            (
                entity["start"],
                entity["end"],
                entity["text"],
                entity["article_role"]["label"],
            )
            for entity in result["entities"]["company"]
        }

    if not labels(cpu) or labels(cpu) != labels(gpu):
        raise AssertionError("CPU and CUDA company spans or roles differ")
    if cpu["article_type"]["label"] != gpu["article_type"]["label"]:
        raise AssertionError("CPU and CUDA article types differ")
    # Arrange: use different company spans in the same CUDA batch.
    documents = [article, "Microsoft reported higher sales than Apple."]
    expected = model.batch_extract(
        documents, schema, batch_size=2, include_spans=True, include_confidence=True
    )
    model._prepare_batched_attributes = partial(prepare_attributes, model)

    # Act: score the same selected spans with batched role scoring.
    observed = model.batch_extract(
        documents, schema, batch_size=2, include_spans=True, include_confidence=True
    )

    # Assert: batching preserves FP32 spans, role labels and article types.
    maximum = 0.0
    for reference, candidate in zip(expected, observed, strict=True):
        if labels(reference) != labels(candidate):
            raise AssertionError("Batched role scoring changed FP32 spans or roles")
        if reference["article_type"]["label"] != candidate["article_type"]["label"]:
            raise AssertionError("Batched role scoring changed the article type")
        by_span = {
            (entity["start"], entity["end"]): entity
            for entity in reference["entities"]["company"]
        }
        for entity in candidate["entities"]["company"]:
            original = by_span[(entity["start"], entity["end"])]
            maximum = max(
                maximum,
                abs(
                    entity["article_role"]["confidence"]
                    - original["article_role"]["confidence"]
                ),
            )
    if maximum > 0.0001:
        raise AssertionError(f"FP32 role confidence drift exceeds tolerance: {maximum}")
    # Arrange: use two independent company attributes and complete class scores.
    metadata_schema = build_metadata_schema(model)
    plain = model.batch_extract(
        documents,
        metadata_schema,
        batch_size=2,
        include_spans=True,
        include_confidence=True,
    )
    capture_probabilities(model)

    # Act: observe the same forward-pass scores through the diagnostic hooks.
    diagnosed = model.batch_extract(
        documents,
        metadata_schema,
        batch_size=2,
        include_spans=True,
        include_confidence=True,
    )

    # Assert: diagnostics preserve predictions and return consistent distributions.
    for reference, candidate in zip(plain, diagnosed, strict=True):
        classes = candidate.pop("_class_probabilities")
        if set(classes) != {"article_form", "event_family"}:
            raise AssertionError("Missing complete classification probabilities")
        for entity in candidate["entities"]["company"]:
            for name in ("local_relevance", "financial_sentiment"):
                group = entity[name]
                probabilities = group.pop("probabilities")
                if abs(sum(probabilities.values()) - 1) > 0.0001:
                    raise AssertionError("Attribute probabilities do not sum to one")
                if abs(probabilities[group["label"]] - group["confidence"]) > 0.0001:
                    raise AssertionError("Selected attribute probability differs")
        if reference != candidate:
            raise AssertionError("Probability diagnostics changed predictions")
    # Arrange: a record-only control has no configured company attributes.
    transaction_schema = build_transaction_schema(model)

    # Act: extract with the same installed diagnostic hooks.
    transactions = model.batch_extract(documents, transaction_schema, batch_size=2)

    # Assert: optional attribute diagnostics also accept attribute-free schemas.
    if len(transactions) != len(documents):
        raise AssertionError("Attribute-free diagnostics lost documents")
    print(json.dumps({"cpu": cpu, "cuda": gpu, "batched_fp32_maximum_drift": maximum}))


if __name__ == "__main__":
    main()
