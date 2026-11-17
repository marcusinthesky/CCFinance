"""Expose diagnostic distributions from the pinned GLiNER 2.1.0 decoder.

These instance-local hooks reuse computed scores and do not run another encoder
pass. They require the existing batched-attribute hook. Returned scores retain
their upstream softmax or sigmoid meaning; they are not calibrated accuracy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch

if TYPE_CHECKING:
    from gliner2.models.boundary.engine import BoundaryExtractor


def capture_probabilities(model: BoundaryExtractor) -> None:
    """Attach full window classifications and retained-span attribute scores."""
    classify = model._decode_classification_probabilities
    attribute = model._attach_entity_attributes

    def classification(
        results: dict, name: str, configuration: dict, probabilities: torch.Tensor
    ) -> None:
        classify(results, name, configuration, probabilities)
        results.setdefault("_class_probabilities", {})[name] = {
            "activation": "sigmoid" if configuration.get("multi_label") else "softmax",
            "threshold": configuration.get("cls_threshold", 0.5),
            "values": dict(
                zip(
                    configuration["labels"],
                    probabilities.detach().float().cpu().tolist(),
                    strict=True,
                )
            ),
        }

    def attributes(
        sample: int,
        core: dict,
        specs: list[dict],
        metadata: dict,
        decoded: dict,
        coordinates: dict,
    ) -> None:
        attribute(sample, core, specs, metadata, decoded, coordinates)
        if (
            "_pending_attribute_inputs" in core
            or not decoded
            or not metadata.get("entity_attribute_groups")
        ):
            return
        cached = core.get("_batched_attribute_logits", {}).get(sample)
        if cached is None:
            if any(decoded.values()):
                raise ValueError("Probability diagnostics require batched attributes")
            return
        rows = {label: index for index, label in enumerate(cached["labels"])}
        for entity_type, items in decoded.items():
            for item in items:
                column = cached["pairs"][coordinates[id(item)]]
                for name, group in metadata["entity_attribute_groups"].items():
                    if group.applies_to and entity_type not in group.applies_to:
                        continue
                    logits = cached["logits"][[rows[x] for x in group.labels], column]
                    probabilities = (
                        torch.sigmoid(logits)
                        if group.multi_label
                        else torch.softmax(logits, dim=-1)
                    )
                    item[name]["probabilities"] = dict(
                        zip(group.labels, probabilities.tolist(), strict=True)
                    )

    model._decode_classification_probabilities = classification
    model._attach_entity_attributes = attributes
