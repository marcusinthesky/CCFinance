"""Check low-precision CUDA linear kernels independently of model accuracy."""

import argparse
import copy
import json
from pathlib import Path

import torch
from torchao.quantization import Float8DynamicActivationFloat8WeightConfig, quantize_


def main() -> None:
    """Test the encoder's representative matrix dimensions on this GPU."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["fp8", "nvfp4"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    torch.manual_seed(42)
    model = (
        torch.nn.Sequential(
            torch.nn.Linear(384, 1536), torch.nn.GELU(), torch.nn.Linear(1536, 384)
        )
        .to(device="cuda", dtype=torch.bfloat16)
        .eval()
    )
    reference = copy.deepcopy(model)
    if args.format == "fp8":
        config = Float8DynamicActivationFloat8WeightConfig()
    else:
        from torchao.prototype.mx_formats.inference_workflow import (
            NVFP4DynamicActivationNVFP4WeightConfig,
        )

        config = NVFP4DynamicActivationNVFP4WeightConfig(use_triton_kernel=False)
    quantize_(model, config)
    inputs = torch.randn(4096, 384, device="cuda", dtype=torch.bfloat16)
    with torch.inference_mode():
        expected = reference(inputs)
        observed = model(inputs)
        if not torch.isfinite(observed).all():
            raise ValueError("Low-precision kernel returned non-finite outputs")
        difference = (expected.float() - observed.float()).abs()
        result = {
            "format": args.format,
            "gpu": torch.cuda.get_device_name(),
            "capability": torch.cuda.get_device_capability(),
            "input_device": str(inputs.device),
            "output_device": str(observed.device),
            "output_dtype": str(observed.dtype),
            "mean_absolute_error": difference.mean().item(),
            "max_absolute_error": difference.max().item(),
            "interpretation": (
                "Kernel compatibility probe, not model accuracy or throughput."
            ),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
