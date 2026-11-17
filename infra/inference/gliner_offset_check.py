"""Check GLiNER's patched chunk-to-document offset handling."""

from gliner2.inference.chunking import TextChunk, remap_result_spans
from gliner_metadata import label_record_choices


def main() -> None:
    """Exercise synthetic punctuation, original punctuation and invalid offsets."""
    # Arrange: the processor appends a period to the first unpunctuated window.
    source = "Apple next"
    chunk = TextChunk(text="Apple", start_char=0, end_char=5, start_word=0, end_word=1)
    result = {"text": "Apple.", "start": 0, "end": 6, "confidence": 0.9}

    # Act: map the model's window coordinates into the original article.
    mapped = remap_result_spans(result, source, chunk)

    # Assert: synthetic punctuation does not consume the source's next character.
    if (
        mapped["text"] != "Apple"
        or (mapped["start"], mapped["end"]) != (0, 5)
        or mapped.get("synthetic_suffix_removed") is not True
    ):
        raise AssertionError(mapped)

    # Arrange: the source itself contains punctuation.
    chunk = TextChunk(text="Apple.", start_char=0, end_char=6, start_word=0, end_word=1)
    result = {"text": "Apple.", "start": 0, "end": 6}

    # Act: map an unchanged valid span.
    mapped = remap_result_spans(result, "Apple.", chunk)

    # Assert: real punctuation survives and no correction is reported.
    if (
        mapped["text"] != "Apple."
        or (mapped["start"], mapped["end"]) != (0, 6)
        or "synthetic_suffix_removed" in mapped
    ):
        raise AssertionError(mapped)

    # Arrange: an unexpected out-of-window offset cannot be repaired safely.
    chunk = TextChunk(text="Apple", start_char=0, end_char=5, start_word=0, end_word=1)
    result = {"text": "unexpected", "start": 0, "end": 7}

    # Act: map the unexpected result.
    mapped = remap_result_spans(result, source, chunk)

    # Assert: the caller can reject it even if the document slice exists.
    if mapped.get("invalid_window_span") is not True:
        raise AssertionError(mapped)

    # Arrange: an enum's coordinates identify its record anchor, not its label.
    source = "News: Apple acquired Intel."
    chunk = TextChunk(source[6:], 6, len(source), 1, 4)
    result = {
        "events": [
            {
                "family": {
                    "text": "transactions",
                    "start": 0,
                    "end": 5,
                    "confidence": 0.9,
                }
            }
        ]
    }
    definition = {
        "json_structures": [
            {
                "events": {
                    "family": {"choices": ["transactions", "operations"]},
                }
            }
        ]
    }

    # Act: distinguish classification labels before global span remapping.
    label_record_choices(result, definition, chunk.text)
    mapped = remap_result_spans(result, source, chunk)

    # Assert: the label survives and its supporting anchor uses source offsets.
    field = mapped["events"][0]["family"]
    if field["label"] != "transactions" or field["support"] != {
        "text": "Apple",
        "start": 6,
        "end": 11,
    }:
        raise AssertionError(mapped)
    print("GLiNER window-offset checks passed")


if __name__ == "__main__":
    main()
