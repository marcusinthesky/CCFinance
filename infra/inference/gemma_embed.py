"""Write normalized EmbeddingGemma vectors for the frozen Fine News corpus."""

import asyncio
import fcntl
import os
import shutil
from collections import deque
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import sglang as sgl
import torch
from safetensors.torch import load_file
from sglang.srt.managers.io_struct import EmbeddingReqInput
from transformers import AutoModel, AutoTokenizer, PreTrainedTokenizerBase

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


def reference(texts: list[str], tokenizer: PreTrainedTokenizerBase) -> torch.Tensor:
    """Encode individual articles with the native FP32 model and projection heads."""
    torch.set_num_threads(2)
    model = AutoModel.from_pretrained(MODEL, dtype=torch.float32).eval()
    heads = [
        load_file(str(p)) for p in sorted(Path(MODEL).glob("*_Dense/model.safetensors"))
    ]
    if len(heads) != 2:
        raise ValueError("Expected two Gemma projection heads")
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


async def write_batches(
    engine: sgl.Engine,
    tokenizer: PreTrainedTokenizerBase,
    batches: Iterable[pa.RecordBatch],
    path: Path,
) -> None:
    """Submit two encoder requests concurrently and drain them in source order."""

    async def submit(ids: list[list[int]]) -> torch.Tensor:
        stream = engine.tokenizer_manager.generate_request(
            EmbeddingReqInput(input_ids=ids), None
        )
        try:
            results = await anext(stream)
        finally:
            await stream.aclose()
        vectors = torch.tensor([r["embedding"] for r in results])
        if vectors.shape != (len(ids), 768) or not torch.allclose(
            vectors.norm(dim=1), torch.ones(len(ids)), atol=1e-4
        ):
            raise ValueError("Invalid embedding output")
        return vectors

    queue = deque()
    writer = None

    async def finish() -> None:
        nonlocal writer
        batch, present, task = queue.popleft()
        vectors = np.zeros((len(batch), 768), dtype=np.float16)
        mask = np.zeros(len(batch), dtype=bool)
        if task is not None:
            vectors[present] = (await task).half().numpy()
            mask[present] = True
        table = pa.table(
            {
                "id": batch.column("id"),
                "embedding": pa.FixedSizeListArray.from_arrays(
                    pa.array(vectors.ravel()), 768
                ),
                "has_text": mask,
            }
        ).replace_schema_metadata(METADATA)
        if writer is None:
            writer = pq.ParquetWriter(path, table.schema, use_dictionary=False)
        writer.write_table(table)

    try:
        for batch in batches:
            if len(queue) == 2:
                await finish()
            texts = batch.column("text").to_pylist()
            present = [i for i, t in enumerate(texts) if t and t.strip()]
            ids = (
                tokenizer(
                    [PREFIX + texts[i] for i in present],
                    truncation=True,
                    max_length=2048,
                )["input_ids"]
                if present
                else []
            )
            queue.append(
                (batch, present, asyncio.create_task(submit(ids)) if present else None)
            )
            await asyncio.sleep(0)
        while queue:
            await finish()
    finally:
        tasks = [task for _, _, task in queue if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if writer:
            writer.close()


def run() -> None:
    """Resume the locked corpus build or run the fixed acceptance sample."""
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

    def write(batches: Iterable[pa.RecordBatch], path: Path) -> None:
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

        def verify(path: Path, texts: list[str], indices: list[int]) -> None:
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
        warm_batch = next(
            pq.ParquetFile(sources[0]).iter_batches(
                batch_size=32, columns=["id", "text"]
            )
        )
        write([warm_batch], probe_path)
        write([probe], probe_path)
        verify(probe_path, probe.column("text").to_pylist(), [0, 1])
        probe_path.unlink()
        if os.getenv("BENCHMARK") == "1":
            from gemma_benchmark import benchmark

            benchmark(SOURCE, OUTPUT, write, verify)
            return
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
