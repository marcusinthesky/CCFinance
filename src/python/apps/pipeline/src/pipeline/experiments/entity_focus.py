"""Render entity-focus inputs while retaining offsets into the article body."""

from collections import Counter

TASK = "Represent what the focal company did, experienced, or proposed."
CANDIDATES = ("header", "instruction", "marked", "query_style")
ARMS = ("plain", "name", *CANDIDATES, "sentences")


def render(
    row: dict, firm: dict, model: str, arm: str, bounds: list, headline: bool = False
) -> tuple[str, list]:
    """Return model input and source-to-input segments for truncation diagnostics."""
    body = row["body"]
    spans = sorted({(s["start"], s["stop"]) for s in firm["spans"]})
    if not spans or any(a < 0 or a >= b or b > len(body) for a, b in spans):
        raise ValueError("Invalid accepted mention offsets")
    name = Counter(body[a:b] for a, b in spans).most_common(1)[0][0]
    prefix = (
        "title: " + (row["title"] if headline else "none") + " | text: "
        if model == "gemma"
        else ""
    )
    header = f"Focal company: {name}\n"
    if arm == "name":
        return prefix + name, []
    if arm == "query_style":
        prefix = (
            f"task: {TASK} | query: "
            if model == "gemma"
            else f"Instruct: {TASK}\nQuery: "
        )
        if headline:
            prefix += f"Title: {row['title']}\n"
    if arm != "plain":
        prefix += header
    if arm in ("instruction", "marked"):
        prefix += TASK + "\n"
    chunks = []
    if arm == "sentences":
        chunks = [
            (a, b, "", "\n")
            for a, b in bounds
            if any(a < y and x < b for x, y in spans)
        ]
    elif arm == "marked":
        end = 0
        for a, b in spans:
            if a < end:
                continue
            chunks.extend([(end, a, "", ""), (a, b, "<focus>", "</focus>")])
            end = b
        chunks.append((end, len(body), "", ""))
    else:
        chunks = [(0, len(body), "", "")]
    text = prefix
    mapping = []
    for a, b, left, right in chunks:
        text += left
        mapping.append((a, b, len(text)))
        text += body[a:b] + right
    return text, mapping


def visible(start: int, stop: int, mapping: list, cutoff: int) -> bool:
    """Check contiguous source coverage across inserted markup boundaries."""
    cursor = start
    for a, b, offset in mapping:
        if a > cursor:
            break
        cursor = max(cursor, min(b, a + max(0, cutoff - offset)))
        if cursor >= stop:
            return True
    return False
