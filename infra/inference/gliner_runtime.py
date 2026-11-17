"""Load the measured GLiNER setup: FP16, DisentangledFlash and compiled heads."""

from functools import partial

import torch
from gliner2 import AutoExtractor
from gliner2.models.boundary.engine import BoundaryExtractor
from gliner_attributes import prepare_attributes

# Extraction-head modules compiled alongside the prepared flash-attention encoder.
# GLiNER 2.1.0 does not allow compiling the DisentangledFlash encoder itself.
COMPILED_HEADS = (
    "boundary_encoder",
    "boundary_query_head",
    "boundary_proposer",
    "pair_scorer",
    "shared_pool_builder",
    "shared_pool_scorer",
)


def load_model(path: str) -> BoundaryExtractor:
    """Place every parameter on CUDA in FP16 and score span attributes in batches."""
    model = AutoExtractor.from_pretrained(path, map_location="cuda")
    if not isinstance(model, BoundaryExtractor):
        raise TypeError("Extraction requires a GLiNER boundary checkpoint")
    model.to(dtype=torch.float16)
    model.eval()
    model._prepare_batched_attributes = partial(prepare_attributes, model)
    model.enable_disentangled_flash()
    for name in COMPILED_HEADS:
        module = getattr(model.boundary_head, name, None)
        if module is not None:
            setattr(model.boundary_head, name, torch.compile(module, dynamic=True))
    devices = {str(parameter.device) for parameter in model.parameters()}
    if not devices or any(not device.startswith("cuda:") for device in devices):
        raise ValueError(f"Model parameters are not entirely on CUDA: {devices}")
    return model
