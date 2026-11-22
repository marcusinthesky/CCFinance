"""Check throughput, article order and reference fidelity on six frozen shards."""

import time
from collections.abc import Callable, Iterable, Iterator
from itertools import islice
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

MONTHS = ("2017-04", "2018-04", "2020-04", "2022-04", "2024-04", "2026-03")


def benchmark(
    source_root: Path,
    output: Path,
    write: Callable[[Iterable[pa.RecordBatch], Path], None],
    verify: Callable[[Path, list[str], list[int]], None],
) -> None:
    """Time two passes and verify the resulting vectors against native FP32."""
    sources = [
        sorted((source_root / m / "eng_Latn").glob("*.parquet"))[0] for m in MONTHS
    ]

    def sample() -> Iterator[pa.RecordBatch]:
        for source in sources:
            pf = pq.ParquetFile(source)
            yield from islice(
                pf.iter_batches(
                    batch_size=32,
                    row_groups=[pf.num_row_groups // 2],
                    columns=["id", "text"],
                ),
                12,
            )

    path = output / "benchmark.parquet"
    for _ in range(2):
        start = time.monotonic()
        write(sample(), path)
        rate = 2304 / (time.monotonic() - start)
        print("Articles/s", rate, flush=True)
    rows = pa.concat_tables(
        [pa.Table.from_batches([b]) for b in sample()], promote_options="default"
    )
    if len(rows) != 2304 or not rows["id"].equals(pq.read_table(path)["id"]):
        raise ValueError("Frozen sample count or output order changed")
    texts = rows["text"].to_pylist()
    indices = []
    for start in range(0, 2304, 384):
        ranked = sorted(
            (i for i in range(start, start + 384) if texts[i] and texts[i].strip()),
            key=lambda i: len(texts[i]),
        )
        indices.extend(
            ranked[int((len(ranked) - 1) * p)]
            for p in (0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.97, 1)
        )
    verify(path, [texts[i] for i in indices], indices)
    if rate < 0.95 * 133.8:
        raise ValueError(f"Warm throughput below acceptance floor: {rate:.1f}")
