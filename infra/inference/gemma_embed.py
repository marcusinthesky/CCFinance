"""Write normalized EmbeddingGemma vectors for the frozen Fine News corpus."""

import asyncio
import fcntl
import shutil
from collections import deque
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
PREFIX = "title: none | text: "
METADATA = {
    "model": "google/embeddinggemma-300m",
    "revision": "57c266a740f537b4dc058e1b0cda161fd15afa75",
    "max_tokens": "2048",
    "prefix": PREFIX,
}


def reference(texts, tokenizer):
    model = AutoModel.from_pretrained(MODEL, dtype=torch.float32).eval()
    heads = [
        load_file(str(p)) for p in sorted(Path(MODEL).glob("*_Dense/model.safetensors"))
    ]
    assert len(heads) == 2
    vectors = []
    with torch.inference_mode():
        for text in texts:
            inputs = tokenizer(
                PREFIX + text, truncation=True, max_length=2048, return_tensors="pt"
            )
            vector = model(**inputs, use_cache=False).last_hidden_state.mean(1)
            for head in heads:
                vector = torch.nn.functional.linear(
                    vector, head["linear.weight"].float(), head.get("linear.bias")
                )
            vectors.append(torch.nn.functional.normalize(vector))
    return torch.cat(vectors)


async def write_batches(engine, tokenizer, batches, path):
    async def encode(batch):
        texts = batch.column("text").to_pylist()
        present = [i for i, t in enumerate(texts) if t and t.strip()]
        vectors = np.zeros((len(batch), 768), dtype=np.float16)
        if present:
            ids = tokenizer(
                [PREFIX + texts[i] for i in present], truncation=True, max_length=2048
            )["input_ids"]
            stream = engine.tokenizer_manager.generate_request(
                EmbeddingReqInput(input_ids=ids), None
            )
            try:
                results = await anext(stream)
            finally:
                await stream.aclose()
            v = torch.tensor([r["embedding"] for r in results])
            if len(v) != len(present) or not torch.allclose(
                v.norm(dim=1), torch.ones(len(v)), atol=1e-4
            ):
                raise ValueError("Invalid embedding output")
            vectors[present] = v.half().numpy()
        mask = np.zeros(len(batch), dtype=bool)
        mask[present] = True
        return pa.table(
            {
                "id": batch.column("id"),
                "embedding": pa.FixedSizeListArray.from_arrays(
                    pa.array(vectors.ravel()), 768
                ),
                "has_text": mask,
            }
        ).replace_schema_metadata(METADATA)

    queue = deque()
    writer = None
    try:
        for batch in batches:
            queue.append(asyncio.create_task(encode(batch)))
            if len(queue) == 2:
                table = await queue.popleft()
                if writer is None:
                    writer = pq.ParquetWriter(path, table.schema, use_dictionary=False)
                writer.write_table(table)
            await asyncio.sleep(0)
        while queue:
            table = await queue.popleft()
            if writer is None:
                writer = pq.ParquetWriter(path, table.schema, use_dictionary=False)
            writer.write_table(table)
    finally:
        for task in queue:
            task.cancel()
        await asyncio.gather(*queue, return_exceptions=True)
        if writer:
            writer.close()


def run():
    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    sources = sorted(SOURCE.rglob("*.parquet"))
    if not sources:
        raise ValueError("No source shards")
    engine = sgl.Engine(
        model_path=MODEL,
        is_embedding=True,
        dtype="bfloat16",
        context_length=2049,
        disable_radix_cache=True,
        chunked_prefill_size=-1,
        disable_cuda_graph=True,
        attention_backend="fa4",
        mem_fraction_static=0.75,
    )

    def write(batches, path):
        engine.loop.run_until_complete(write_batches(engine, tokenizer, batches, path))

    try:
        probe = pa.record_batch(
            {
                "id": [0, 1],
                "text": [
                    "A firm reported earnings.",
                    "Markets closed higher on Friday.",
                ],
            }
        )

        def verify(path, texts, indices):
            values = (
                pq.read_table(path)["embedding"]
                .combine_chunks()
                .values.to_numpy()
                .reshape(-1, 768)
            )
            cosine = torch.nn.functional.cosine_similarity(
                torch.tensor(values[indices].astype(np.float32)),
                reference(texts, tokenizer),
            )
            print("Minimum FP32 cosine", cosine.min().item(), flush=True)
            if not torch.all(cosine >= 0.999):
                raise ValueError("FP32 reference mismatch")

        probe_path = OUTPUT / ".probe.partial"
        write([probe], probe_path)
        verify(probe_path, probe.column("text").to_pylist(), [0, 1])
        probe_path.unlink()
        for source in sources:
            pf = pq.ParquetFile(source)
            directory = OUTPUT / source.relative_to(SOURCE)
            directory.mkdir(parents=True, exist_ok=True)
            for group in range(pf.num_row_groups):
                dest = directory / f"group-{group:04d}.parquet"
                if dest.exists():
                    if (
                        pq.read_schema(dest).metadata.get(b"revision")
                        != METADATA["revision"].encode()
                    ):
                        raise ValueError(f"Unexpected model revision in {dest}")
                    continue
                rows = pf.metadata.row_group(group).num_rows
                if shutil.disk_usage(OUTPUT).free < (3 << 30) + rows * 1800:
                    raise SystemExit("Paused at disk reserve")
                temp = dest.with_suffix(".partial")
                write(
                    pf.iter_batches(
                        batch_size=32, row_groups=[group], columns=["id", "text"]
                    ),
                    temp,
                )
                if pq.ParquetFile(temp).metadata.num_rows != rows:
                    raise ValueError("Incomplete row group")
                temp.replace(dest)
                print("Saved", dest, flush=True)
    finally:
        engine.shutdown()


if __name__ == "__main__":
    with (OUTPUT / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run()
