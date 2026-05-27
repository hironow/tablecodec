"""Internal Representation (IR) for tablecodec.

SPEC §5: the 2D grid model that every supported codec maps to/from.
Types are immutable (``frozen=True``), memory-compact (``slots=True``),
and hashable. Zero third-party dependencies (SPEC §13).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

__all__ = ["BBox", "GridCell", "TableSample"]


# Absolute pixel coordinates: (x0, y0, x1, y1). See SPEC §5.1.
BBox = tuple[int, int, int, int]


def _empty_extras() -> dict[str, object]:
    return {}


@dataclass(frozen=True, slots=True)
class GridCell:
    """A single grid cell in a :class:`TableSample`.

    Attributes:
        row: Zero-indexed row of the cell's top-left anchor.
        col: Zero-indexed column of the cell's top-left anchor.
        rowspan: Number of rows the cell occupies (``>= 1``).
        colspan: Number of columns the cell occupies (``>= 1``).
        tokens: Ordered tokens that form the cell content. Empty tuple for
            empty cells. The tuple is never ``None`` (SPEC §5.2 I-07).
        bbox: Bounding box in absolute pixels, or ``None`` when the source
            format does not provide one (e.g. empty cells, pubtabnet-1.0.0).
        role: ``"header"`` or ``"body"``. Header cells must form a
            contiguous top-region (SPEC §5.2 I-06).
    """

    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    tokens: tuple[str, ...] = ()
    bbox: BBox | None = None
    role: Literal["header", "body"] = "body"


@dataclass(frozen=True, slots=True)
class TableSample:
    """One annotated table image.

    Attributes:
        filename: Source image filename.
        nrows: Logical row count of the grid (``>= 1``).
        ncols: Logical column count of the grid (``>= 1``).
        cells: Ordered top-to-bottom, left-to-right (SPEC §5.1).
        split: Optional dataset split assignment.
        imgid: Optional dataset-defined integer id.
        extras: Codec-defined opaque metadata. Opaque to validation but
            must be JSON-serializable for codecs that round-trip via it
            (SPEC §5.2 closing paragraph). Excluded from :meth:`__hash__`
            because ``Mapping`` is not generally hashable; equality still
            considers it via the dataclass-generated ``__eq__``.
    """

    filename: str
    nrows: int
    ncols: int
    cells: tuple[GridCell, ...]
    split: Literal["train", "val", "test"] | None = None
    imgid: int | None = None
    extras: Mapping[str, object] = field(default_factory=_empty_extras)

    def __hash__(self) -> int:
        # extras is a Mapping (potentially a dict, which is unhashable);
        # excluding it preserves the hash/eq contract: equal samples that
        # also have equal extras hash identically, while two samples that
        # differ only in extras may collide (acceptable for a hash).
        return hash(
            (self.filename, self.nrows, self.ncols, self.cells, self.split, self.imgid)
        )
