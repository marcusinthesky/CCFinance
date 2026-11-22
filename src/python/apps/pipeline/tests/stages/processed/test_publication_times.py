"""Test first-publication and exchange-cutoff boundaries."""

from datetime import UTC, datetime

import pytest
from pipeline.stages.processed.publication_times import (
    NEW_YORK,
    first_publication,
    overnight_status,
)


@pytest.mark.unit
def test_first_publication_remains_distinct_from_update() -> None:
    """Use the first publication line from the same captured version."""
    # Arrange
    body = (
        "Last Updated: Mar 13 2023 | 6:40 PM IST\n"
        "First Published: Mar 13 2023 | 5:30 PM IST"
    )

    # Act
    evidence, published = first_publication("business-standard.com", body)

    # Assert
    assert evidence == "First Published: Mar 13 2023 | 5:30 PM IST"
    assert published == datetime(2023, 3, 13, 12, tzinfo=UTC)
    assert first_publication("business-standard.com", body.splitlines()[0]) == (
        "",
        None,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("previous", "cutoff", "published", "captured", "expected"),
    [
        (
            "2023-03-10T16:00",
            "2023-03-13T09:00",
            "2023-03-13T12:55+00:00",
            "2023-03-13T13:00+00:00",
            "eligible",
        ),
        (
            "2023-01-13T16:00",
            "2023-01-17T09:00",
            "2023-01-14T07:00+00:00",
            "2023-01-17T13:00+00:00",
            "eligible",
        ),
        (
            "2023-11-24T13:00",
            "2023-11-27T09:00",
            "2023-11-24T19:00+00:00",
            "2023-11-24T19:01+00:00",
            "eligible",
        ),
        (
            "2023-11-24T13:00",
            "2023-11-27T09:00",
            "2023-11-24T18:00+00:00",
            "2023-11-24T19:01+00:00",
            "outside_overnight",
        ),
        (
            "2023-03-10T16:00",
            "2023-03-13T09:00",
            "2023-03-13T13:00+00:00",
            "2023-03-13T13:00+00:00",
            "outside_overnight",
        ),
        (
            "2023-03-10T16:00",
            "2023-03-13T09:00",
            "2023-03-13T12:55+00:00",
            "2023-03-13T12:50+00:00",
            "capture_before_publication",
        ),
        (
            "2023-03-10T16:00",
            "2023-03-13T09:00",
            "2023-03-13T12:55+00:00",
            "2023-03-13T13:01+00:00",
            "capture_after_cutoff",
        ),
    ],
)
def test_overnight_timing(
    previous: str, cutoff: str, published: str, captured: str, expected: str
) -> None:
    """Enforce strict publication bounds and capture no later than cutoff."""
    # Arrange
    previous_close = datetime.fromisoformat(previous).replace(tzinfo=NEW_YORK)
    cutoff_at = datetime.fromisoformat(cutoff).replace(tzinfo=NEW_YORK)

    # Act
    result = overnight_status(
        datetime.fromisoformat(published),
        datetime.fromisoformat(captured),
        previous_close,
        cutoff_at,
    )

    # Assert
    assert result == expected
