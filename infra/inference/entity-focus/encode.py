"""Offline reference encoders for the entity-focus study."""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import torch
from safetensors.torch import load_file
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoTokenizer

MODELS = {
    "open": "opensearch-v1",
    "gemma": "embeddinggemma-300m",
    "qwen": "Qwen3-Embedding-0.6B",
}


def encoder(root: Path, key: str) -> tuple[object, int, Callable]:
    """Load the checkpoint and its published projection."""
    path = root / MODELS[key]
    if key != "open":
        model = SentenceTransformer(
            str(path),
            device="cpu",
            local_files_only=True,
            model_kwargs={"dtype": torch.float32},
        )

        def encode(text: str) -> np.ndarray:
            return model.encode([text], prompt="", normalize_embeddings=True)[0]

        probe = "Focal company: Example\nAn acquisition was announced."
        inputs = model.tokenizer(probe, return_tensors="pt")
        with torch.inference_mode():
            hidden = model[0].auto_model(**inputs).last_hidden_state.float()
            expected = hidden[:, -1] if key == "qwen" else hidden.mean(1)
            if key == "gemma":
                for directory in ("2_Dense", "3_Dense"):
                    weights = load_file(str(path / directory / "model.safetensors"))
                    expected = torch.nn.functional.linear(
                        expected, weights["linear.weight"].float()
                    )
            expected = torch.nn.functional.normalize(expected)[0].numpy()
        if np.dot(expected, encode(probe)) < 0.999:
            raise ValueError(f"{key} reference-vector parity failed")
        return model.tokenizer, model.max_seq_length, encode

    tokenizer = AutoTokenizer.from_pretrained(path)
    backbone = AutoModel.from_pretrained(path, dtype=torch.bfloat16).eval()
    head = load_file(str(path / "2_Dense/model.safetensors"))

    @torch.inference_mode()
    def encode(text: str) -> np.ndarray:
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=8192)
        hidden = backbone(**inputs, use_cache=False).last_hidden_state.float().mean(1)
        vector = torch.nn.functional.linear(
            hidden, head["linear.weight"], head["linear.bias"]
        )
        return torch.nn.functional.normalize(vector)[0].numpy()

    return tokenizer, 8192, encode
