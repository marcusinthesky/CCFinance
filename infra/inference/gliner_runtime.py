"""Load the local extractor with explicit precision and attention choices."""

from collections import Counter
from functools import partial

import torch
from gliner2 import AutoExtractor
from gliner2.models.boundary.engine import BoundaryExtractor


def load_model(
    path: str, precision: str, backend: str, *, batched_attributes: bool = False
) -> tuple[BoundaryExtractor, dict]:
    """Set precision before preparing attention kernels or compiling the model."""
    model = AutoExtractor.from_pretrained(path, map_location="cuda")
    if not isinstance(model, BoundaryExtractor):
        raise TypeError("This benchmark requires a GLiNER boundary checkpoint")
    if precision == "fp16":
        model.to(dtype=torch.float16)
    elif precision in {"bf16", "fp8", "nvfp4"}:
        model.to(dtype=torch.bfloat16)
    if precision in {"int8", "fp8", "nvfp4"}:
        from torchao.quantization import quantize_

        if backend.startswith("disentangled_flash"):
            raise ValueError(
                "Quantized encoder projections need separate backend validation"
            )
        if precision == "int8":
            from torchao.quantization import Int8WeightOnlyConfig

            config = Int8WeightOnlyConfig()
        elif precision == "fp8":
            from torchao.quantization import Float8DynamicActivationFloat8WeightConfig

            config = Float8DynamicActivationFloat8WeightConfig()
        else:
            from torchao.prototype.mx_formats.inference_workflow import (
                NVFP4DynamicActivationNVFP4WeightConfig,
            )

            config = NVFP4DynamicActivationNVFP4WeightConfig(use_triton_kernel=False)
        quantize_(model.encoder, config)
    model.eval()
    if batched_attributes:
        from gliner_attributes import prepare_attributes

        model._prepare_batched_attributes = partial(prepare_attributes, model)
    if backend.startswith("disentangled_flash"):
        model.enable_disentangled_flash()
        if backend == "disentangled_flash_heads":
            # Compile the extraction heads only; the prepared attention
            # encoder remains outside torch.compile, as its API requires.
            for name in (
                "boundary_encoder",
                "boundary_query_head",
                "boundary_proposer",
                "pair_scorer",
                "shared_pool_builder",
                "shared_pool_scorer",
            ):
                module = getattr(model.boundary_head, name, None)
                if module is not None:
                    setattr(
                        model.boundary_head, name, torch.compile(module, dynamic=True)
                    )
    elif backend == "compiled":
        model.compile(dynamic=True)
    devices = {str(parameter.device) for parameter in model.parameters()}
    if not devices or any(not device.startswith("cuda:") for device in devices):
        raise ValueError(f"Model parameters are not entirely on CUDA: {devices}")
    metadata = {
        "parameter_devices": sorted(devices),
        "parameter_dtypes": dict(Counter(str(p.dtype) for p in model.parameters())),
        "encoder_linear_weight_types": dict(
            Counter(
                type(module.weight).__name__
                for module in model.encoder.modules()
                if isinstance(module, torch.nn.Linear)
            )
        ),
        "compute_capability": torch.cuda.get_device_capability(),
    }
    return model, metadata
