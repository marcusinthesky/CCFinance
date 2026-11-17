"""Batch span-attribute scoring while retaining GLiNER's own span selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch

if TYPE_CHECKING:
    from gliner2.models.boundary.engine import BoundaryExtractor
    from gliner2.processor import PreprocessedBatch


def prepare_attributes(
    model: BoundaryExtractor,
    batch: PreprocessedBatch,
    core: dict,
    metadata_list: list[dict],
    grouped_candidates: list[list[list[tuple[float, int, int]]]] | None,
    null_probs: torch.Tensor | None,
) -> dict[int, dict]:
    """Collect exactly the decoded spans, then score all eligible windows together."""
    pending = []
    core["_pending_attribute_inputs"] = pending
    try:
        for index, metadata in enumerate(metadata_list):
            if not metadata.get("entity_attribute_groups"):
                continue
            model._decode_entities(
                index,
                core,
                core["ext_specs"][index],
                grouped_candidates[index] if grouped_candidates is not None else [],
                metadata,
                null_probs[index] if null_probs is not None else None,
                model._resolved_overlap_policy(metadata.get("_overlap_policy")),
                core["word_offsets"][index],
                batch.start_mappings[index],
                batch.end_mappings[index],
                batch.original_texts[index],
                len(batch.start_mappings[index]),
                True,
                True,
            )
    finally:
        del core["_pending_attribute_inputs"]
    cases = []
    for sample_index, specs, metadata, decoded, coordinates in pending:
        pairs = list(
            dict.fromkeys(
                coordinates[id(item)] for items in decoded.values() for item in items
            )
        )
        if not pairs:
            continue
        query_by_name = {
            spec["field_name"]: index
            for index, spec in enumerate(specs)
            if spec["task_type"] == "entities"
        }
        prompts = metadata.get("entity_attribute_prompt_labels", {})
        rows = list(
            dict.fromkeys(
                (label, query_by_name[prompt])
                for group in metadata["entity_attribute_groups"].values()
                for label in group.labels
                if (prompt := prompts.get(label, label)) in query_by_name
            )
        )
        if rows:
            cases.append((sample_index, rows, pairs))
    if not cases:
        return {}
    device = core["query_states"].device
    count = len(cases)
    queries = max(len(rows) for _, rows, _ in cases)
    spans = max(len(pairs) for _, _, pairs in cases)
    query_indices = torch.zeros((count, queries), dtype=torch.long)
    query_valid = torch.zeros((count, queries), dtype=torch.bool)
    indices = torch.zeros((count, queries, spans, 2), dtype=torch.long)
    valid = torch.zeros((count, queries, spans), dtype=torch.bool)
    for index, (_, rows, pairs) in enumerate(cases):
        query_indices[index, : len(rows)] = torch.tensor([query for _, query in rows])
        query_valid[index, : len(rows)] = True
        indices[index, : len(rows), : len(pairs)] = torch.tensor(pairs).unsqueeze(0)
        valid[index, : len(rows), : len(pairs)] = True
    samples = torch.tensor([sample for sample, _, _ in cases], device=device)
    query_indices = query_indices.to(device)
    states = core["query_states"].index_select(0, samples)
    states = states.gather(
        1, query_indices.unsqueeze(-1).expand(-1, -1, states.shape[-1])
    )
    mask = core["query_mask"].index_select(0, samples).gather(1, query_indices)
    mask = mask & query_valid.to(device)
    logits = model.boundary_head.score_explicit_spans(
        core["text_states"].index_select(0, samples),
        core["text_mask"].index_select(0, samples),
        states,
        mask,
        indices.to(device),
        valid_mask=valid.to(device),
    )
    logits = (logits / model.boundary_settings.pair_temperature).float().cpu()
    return {
        sample: {
            "labels": [label for label, _ in rows],
            "pairs": {pair: index for index, pair in enumerate(pairs)},
            "logits": logits[index, : len(rows), : len(pairs)],
        }
        for index, (sample, rows, pairs) in enumerate(cases)
    }
