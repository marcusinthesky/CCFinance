"""Encode frozen Fine News rows with SGLang, then project into OpenSearch space."""

import fcntl
import shutil
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import sglang as sgl
import torch
from safetensors.torch import load_file
from sglang.srt.managers.io_struct import EmbeddingReqInput
from transformers import AutoModel, AutoTokenizer

SOURCE = Path("/articles")
OUTPUT = Path("/output")
MODEL = "/model"
MODEL_ID = "opensearch-project/opensearch-neural-embed-v1"
BATCH = 32
LIMIT = 8192


def run() -> None:
    """Resume encoding the frozen corpus one source row group at a time."""
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    head = load_file(f"{MODEL}/2_Dense/model.safetensors")

    def project(means: torch.Tensor) -> torch.Tensor:
        return torch.nn.functional.normalize(
            means.float() @ head["linear.weight"].T + head["linear.bias"], dim=-1
        )

    probes = ["A firm reported earnings.", "Markets closed higher on Friday."]
    reference = AutoModel.from_pretrained(MODEL).eval()
    inputs = tokenizer(probes, padding=True, return_tensors="pt")
    with torch.inference_mode():
        hidden = reference(**inputs).last_hidden_state
        mask = inputs.attention_mask.unsqueeze(-1)
        expected = project((hidden * mask).sum(1) / mask.sum(1))
    del reference, hidden

    engine = sgl.Engine(
        model_path=MODEL,
        is_embedding=True,
        dtype="bfloat16",
        context_length=LIMIT + 1,  # SGLang reserves a token even on encode requests.
        disable_radix_cache=True,
        chunked_prefill_size=-1,
        disable_cuda_graph=True,
        attention_backend="triton",
        mem_fraction_static=0.75,
    )

    def encode(texts: list[str]) -> torch.Tensor:
        ids = tokenizer(texts, truncation=True, max_length=LIMIT)["input_ids"]
        if any(not tokens for tokens in ids):
            raise ValueError("Empty document token sequence")
        request = EmbeddingReqInput(input_ids=ids)
        stream = engine.tokenizer_manager.generate_request(request, None)
        responses = engine.loop.run_until_complete(anext(stream))
        vectors = project(torch.tensor([row["embedding"] for row in responses]))
        if not torch.allclose(vectors.norm(dim=1), torch.ones(len(texts)), atol=1e-4):
            raise ValueError("Invalid embedding norm")
        return vectors

    try:
        similarity = (encode(probes) * expected).sum(1)
        if not torch.all(similarity > 0.999):
            raise ValueError(f"Reference cosine check failed {similarity}")
        print(f"Reference cosine {similarity.tolist()}", flush=True)
        for source in sorted(SOURCE.rglob("*.parquet")):
            parquet = pq.ParquetFile(source)
            directory = OUTPUT / source.relative_to(SOURCE)
            directory.mkdir(parents=True, exist_ok=True)
            for group in range(parquet.num_row_groups):
                dest = directory / f"group-{group:04d}.parquet"
                if dest.exists():
                    continue
                rows = parquet.metadata.row_group(group).num_rows
                if shutil.disk_usage(OUTPUT).free < (3 << 30) + rows * 4500:
                    raise SystemExit(
                        "Paused at disk reserve. Resume with more storage."
                    )
                temp = dest.with_suffix(".partial")
                writer = None
                try:
                    for batch in parquet.iter_batches(
                        batch_size=BATCH, row_groups=[group], columns=["id", "text"]
                    ):
                        texts = batch.column("text").to_pylist()
                        present = [
                            i for i, text in enumerate(texts) if text and text.strip()
                        ]
                        vectors = np.zeros((len(texts), 2048), dtype=np.float16)
                        if present:
                            vectors[present] = (
                                encode([texts[i] for i in present]).half().numpy()
                            )
                        array = pa.FixedSizeListArray.from_arrays(
                            pa.array(vectors.ravel()), 2048
                        )
                        table = pa.table(
                            {
                                "id": batch.column("id"),
                                "embedding": array,
                                "has_text": [bool(t and t.strip()) for t in texts],
                            }
                        )
                        table = table.replace_schema_metadata(
                            {
                                "model": MODEL_ID,
                                "revision": "d558088abac35e8932772965a85e927aedfe49c7",
                                "max_tokens": str(LIMIT),
                            }
                        )
                        if writer is None:
                            writer = pq.ParquetWriter(
                                temp, table.schema, use_dictionary=False
                            )
                        writer.write_table(table)
                finally:
                    if writer is not None:
                        writer.close()
                temp.replace(dest)
                print(f"Saved {rows} rows to {dest}", flush=True)
    finally:
        engine.shutdown()


if __name__ == "__main__":
    with (OUTPUT / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run()
