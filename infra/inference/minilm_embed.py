"""Encode the fixed captured titles with the published MiniLM architecture."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import torch
from transformers import AutoModel, AutoTokenizer

MODEL = "/model"
METADATA = {
    "model": "sentence-transformers/all-MiniLM-L6-v2",
    "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    "max_tokens": "256",
    "pooling": "masked mean, L2 normalized",
}


def run() -> None:
    """Apply MiniLM's published Transformer, Pooling and Normalize modules."""
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModel.from_pretrained(MODEL, dtype=torch.float32).eval().cuda()
    source = pq.read_table("/articles/titles.parquet", columns=["id", "text"])
    batches = []
    with torch.inference_mode():
        for batch in source.to_batches(max_chunksize=256):
            inputs = tokenizer(
                [title.strip() for title in batch.column("text").to_pylist()],
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="pt",
            ).to("cuda")
            hidden = model(**inputs).last_hidden_state
            mask = inputs["attention_mask"].unsqueeze(-1)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1)
            vectors = torch.nn.functional.normalize(pooled).cpu().numpy()
            batches.append(
                pa.record_batch(
                    {
                        "id": batch.column("id"),
                        "embedding": pa.FixedSizeListArray.from_arrays(
                            pa.array(vectors.ravel()), 384
                        ),
                        "has_text": pa.array([True] * len(batch)),
                    }
                )
            )
    output = Path("/output/vectors.parquet")
    temp = output.with_suffix(".partial")
    pq.write_table(
        pa.Table.from_batches(batches).replace_schema_metadata(METADATA), temp
    )
    temp.replace(output)


if __name__ == "__main__":
    run()
