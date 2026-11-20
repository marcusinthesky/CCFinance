"""Locate source sentences and keep the original character offsets."""

import itertools
import re


def sentences(text: str) -> list[tuple[int, int]]:
    """Find sentence bounds in the original article."""
    # Retain abbreviations such as "U.S." with the following clause where possible.
    boundaries = [0]
    for gap in re.finditer(r'\n+|(?<=[.!?])\s+(?=[A-Z0-9“"\u2018])', text):
        if "\n" not in gap[0] and re.search(
            r"(?:\b[A-Z]\.|\b(?:Inc|Mr|Dr|Corp|Co|Ltd)\.)$", text[: gap.start()]
        ):
            continue
        boundaries.append(gap.end())
    boundaries.append(len(text))
    return [(a, b) for a, b in itertools.pairwise(boundaries) if text[a:b].strip()]


def matches(sentence: tuple[int, int], spans: list[dict]) -> bool:
    """Check overlap with any accepted mention."""
    a, b = sentence
    return any(a < span["stop"] and span["start"] < b for span in spans)
