"""Check SEC public-float frame snapshots and their provenance."""

import json
from pathlib import Path

import httpx
import pytest
from pipeline.stages.raw.public_float import periods, snapshot


@pytest.mark.unit
def test_periods_cover_every_quarter_of_each_year() -> None:
    # Arrange: two calendar years.
    first, last = 2019, 2020

    # Act: list their instant frames.
    frames = periods(first, last)

    # Assert: four quarters per year, in order.
    assert frames[:2] == ["CY2019Q1I", "CY2019Q2I"]
    assert (len(frames), frames[-1]) == (8, "CY2020Q4I")


@pytest.mark.integration
def test_snapshot_keeps_published_frames_and_records_missing_ones(
    tmp_path: Path,
) -> None:
    # Arrange: SEC serves one frame and has not published the next.
    frame = {"data": [{"cik": 320193, "end": "2019-03-29", "val": 8.7e11}]}

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("CY2019Q1I.json"):
            return httpx.Response(200, json=frame)
        return httpx.Response(404)

    # Act: snapshot two frames.
    output = tmp_path / "public-float"
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        snapshot(client, ["CY2019Q1I", "CY2019Q2I"], output)

    # Assert: the published frame and both provenance records are kept.
    saved = json.loads((output / "frames/CY2019Q1I.json").read_text())
    assert saved == frame
    assert not (output / "frames/CY2019Q2I.json").exists()
    provenance = json.loads((output / "provenance.json").read_text())
    assert provenance["frames/CY2019Q1I.json"]["bytes"] > 0
    assert provenance["frames/CY2019Q2I.json"]["status"] == "not published"


@pytest.mark.integration
def test_snapshot_fails_on_server_errors(tmp_path: Path) -> None:
    # Arrange: SEC refuses the request.

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    # Act and assert: the snapshot fails and leaves no output.
    output = tmp_path / "public-float"
    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        snapshot(client, ["CY2019Q1I"], output)
    assert not output.exists()
