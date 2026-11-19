"""Atomic directory publication for raw stages."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


@contextmanager
def stage_output(output: Path) -> Iterator[Path]:
    """Publish a complete stage directory once, preserving existing outputs."""
    if output.exists():
        raise FileExistsError(f"Output exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        staging = Path(temporary) / "output"
        staging.mkdir()
        yield staging
        staging.rename(output)
