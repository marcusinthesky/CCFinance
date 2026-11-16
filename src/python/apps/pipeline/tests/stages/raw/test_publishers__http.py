"""Measure row-group pruning using a local HTTP server with byte ranges."""

from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import override

import duckdb
import pytest
from pipeline.stages.raw.publishers import extract_group


@contextmanager
def _serve_parquet(path: Path) -> Iterator[tuple[str, list[int]]]:
    payload = path.read_bytes()
    transferred: list[int] = []

    class RangeHandler(BaseHTTPRequestHandler):
        @override
        def log_message(self, format: str, *args: object) -> None:
            """Keep normal local requests out of test output."""

        def _respond(self, *, body: bool) -> None:
            first, last = 0, len(payload) - 1
            requested = self.headers.get("Range")
            if requested is not None:
                start, stop = requested.removeprefix("bytes=").split("-", 1)
                first = int(start)
                last = int(stop) if stop else last
            self.send_response(206 if requested else 200)
            self.send_header("Content-Length", str(last - first + 1))
            self.send_header("Accept-Ranges", "bytes")
            if requested:
                self.send_header(
                    "Content-Range", f"bytes {first}-{last}/{len(payload)}"
                )
            self.end_headers()
            if body:
                selected = payload[first : last + 1]
                self.wfile.write(selected)
                transferred.append(len(selected))

        def do_HEAD(self) -> None:
            self._respond(body=False)

        def do_GET(self) -> None:
            self._respond(body=True)

    with ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/source.parquet", transferred
        finally:
            server.shutdown()
            worker.join()


@pytest.mark.integration
def test_row_bounds_transfer_less_than_full_projected_scan(tmp_path: Path) -> None:
    # Arrange: many independent row groups make skipped payload observable.
    source = tmp_path / "source.parquet"
    domains = tmp_path / "domains.csv"
    domains.write_text("domain\nexample.com\n", encoding="utf-8")
    with duckdb.connect() as con:
        con.execute(
            """COPY (
                SELECT md5(i::VARCHAR) || md5((i + 1)::VARCHAR) AS text,
                    i::VARCHAR AS id,
                    {'url': 'https://example.com/' || i,
                     'url_hostname': 'example.com'} AS metadata
                FROM range(24576) AS rows(i)
            ) TO ? (FORMAT PARQUET, ROW_GROUP_SIZE 2048)""",
            [str(source)],
        )

    with _serve_parquet(source) as (url, transferred):
        # Act: compare fresh connections with HTTP caching disabled.
        with duckdb.connect() as con:
            con.execute("LOAD httpfs; SET enable_external_file_cache=false")
            counts = extract_group(
                con, "fine_news", url, 4096, 6144, domains, tmp_path / "sample.parquet"
            )
        sample_bytes = sum(transferred)
        transferred.clear()
        with duckdb.connect() as con:
            con.execute("LOAD httpfs; SET enable_external_file_cache=false")
            full = con.execute(
                "SELECT sum(length(text) + length(id) + "
                "length(metadata.url) + length(metadata.url_hostname)) "
                "FROM read_parquet(?, hive_partitioning=false)",
                [url],
            ).fetchone()
        full_bytes = sum(transferred)

    # Assert: the selected rows are complete and fewer HTTP bytes were sent.
    assert counts == {"input_rows": 2048, "english_rows": 2048, "matched_rows": 2048}
    assert full is not None and full[0] > 0
    assert 0 < sample_bytes < full_bytes
