"""Hypothesis strategies for tablecodec IR types.

Two layers:

- Raw strategies (``gridcell_st``, ``tablesample_st``) generate
  *possibly-invalid* samples to exercise validation against bad input.
- ``valid_tablesample_st`` generates samples that satisfy every SPEC §5.2
  invariant. The valid generator uses 1×1 cell tiling — every grid cell
  is filled by exactly one cell with no spans. That is sufficient to
  exercise I-04 coverage on every shape, and avoids the NP-hard rectangle
  packing problem that span-aware valid generation would require.

Span-aware valid generation arrives later (see TODO inside the module).
"""

from __future__ import annotations

from typing import Literal

from hypothesis import strategies as st

from tablecodec.ir import BBox, GridCell, TableSample

__all__ = [
    "bbox_st",
    "gridcell_st",
    "tablesample_st",
    "valid_tablesample_st",
]


# ---------- primitives ----------


@st.composite
def bbox_st(draw: st.DrawFn) -> BBox:
    """A well-formed BBox: x0 < x1 and y0 < y1."""
    x0 = draw(st.integers(min_value=0, max_value=10_000))
    y0 = draw(st.integers(min_value=0, max_value=10_000))
    w = draw(st.integers(min_value=1, max_value=500))
    h = draw(st.integers(min_value=1, max_value=500))
    return (x0, y0, x0 + w, y0 + h)


tokens_st = st.lists(st.text(min_size=1, max_size=4), min_size=0, max_size=4).map(tuple)


# ---------- raw (possibly-invalid) generators ----------


@st.composite
def gridcell_st(draw: st.DrawFn) -> GridCell:
    """Generate an arbitrary GridCell. May violate I-01..I-05 by design."""
    row = draw(st.integers(min_value=-2, max_value=10))
    col = draw(st.integers(min_value=-2, max_value=10))
    rowspan = draw(st.integers(min_value=1, max_value=4))
    colspan = draw(st.integers(min_value=1, max_value=4))
    tokens = draw(tokens_st)
    bbox = draw(st.none() | bbox_st())
    roles: tuple[Literal["header", "body"], ...] = ("header", "body")
    role = draw(st.sampled_from(roles))
    return GridCell(
        row=row,
        col=col,
        rowspan=rowspan,
        colspan=colspan,
        tokens=tokens,
        bbox=bbox,
        role=role,
    )


@st.composite
def tablesample_st(draw: st.DrawFn) -> TableSample:
    """Generate an arbitrary TableSample. Often invalid; use for fuzz tests."""
    nrows = draw(st.integers(min_value=0, max_value=6))
    ncols = draw(st.integers(min_value=0, max_value=6))
    cells = tuple(draw(st.lists(gridcell_st(), min_size=0, max_size=12)))
    filename = draw(st.text(min_size=1, max_size=8))
    return TableSample(filename=filename, nrows=nrows, ncols=ncols, cells=cells)


# ---------- valid generator (passes DEFAULT profile) ----------


@st.composite
def valid_tablesample_st(
    draw: st.DrawFn,
    max_nrows: int = 5,
    max_ncols: int = 5,
) -> TableSample:
    """Generate a TableSample that satisfies every SPEC §5.2 invariant.

    Strategy: tile the entire ``nrows × ncols`` grid with 1×1 cells. Header
    cells form a contiguous top region (0..H rows), body cells fill the
    rest. Spans = 1, so I-03 / I-04 hold trivially.

    TODO(M2+): grow a span-aware valid generator backed by a rectangle
    packing strategy. Out of M1 scope (1×1 tiling already exercises every
    invariant exhaustively).
    """
    nrows = draw(st.integers(min_value=1, max_value=max_nrows))
    ncols = draw(st.integers(min_value=1, max_value=max_ncols))
    header_rows = draw(st.integers(min_value=0, max_value=nrows))
    filename = draw(st.text(min_size=1, max_size=8))

    cells: list[GridCell] = []
    header_role: Literal["header"] = "header"
    body_role: Literal["body"] = "body"
    for r in range(nrows):
        role: Literal["header", "body"] = header_role if r < header_rows else body_role
        for c in range(ncols):
            tokens = draw(tokens_st)
            bbox = draw(st.none() | bbox_st())
            cells.append(
                GridCell(
                    row=r,
                    col=c,
                    tokens=tokens,
                    bbox=bbox,
                    role=role,
                )
            )

    return TableSample(
        filename=filename,
        nrows=nrows,
        ncols=ncols,
        cells=tuple(cells),
    )
