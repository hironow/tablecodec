"""Shared OTSL grid machinery for codec implementations.

OTSL (Lysak et al., ICDAR 2023, arXiv 2305.03393) and the DocTags table
subset (IBM Granite-Docling) both encode table structure with the same
five-token cell vocabulary plus a row separator:

- ``fcel`` filled-cell anchor
- ``ecel`` empty-cell anchor
- ``lcel`` left-merged continuation (extends the anchor's colspan)
- ``ucel`` up-merged continuation (extends the anchor's rowspan)
- ``xcel`` cross-merged continuation (extends both)
- ``nl``   newline / row separator

This module owns the structure↔grid conversion so OTSL and DocTags do
not duplicate it. DocTags additionally interleaves location and content
tokens, which it strips before calling :func:`build_anchors`, and
re-inserts when serialising from :func:`build_token_grid`.

The grid-reconstruction logic in :func:`build_anchors` (the anchor-centric
scan, the ``check_right``/``check_down`` span runs, and the 2D-span
registry) is adapted from docling-ibm-models' ``otsl_to_html``:

    https://github.com/docling-project/docling-ibm-models
    docling_ibm_models/tableformer/otsl.py
    Copyright (c) 2024 International Business Machines
    Licensed under the MIT License.

It is reimplemented here for the neutral IR (it emits ``GridCell`` spans
rather than HTML strings) and carries no third-party imports. See
THIRD_PARTY_NOTICES.md and docs/adr/0005-port-otsl-reconstruction.md.

Stdlib-only (SPEC §13).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from tablecodec.ir import GridCell, TableSample

__all__ = [
    "ANCHOR_TOKENS",
    "CELL_TOKENS",
    "CONTINUATION_TOKENS",
    "VALID_TOKENS",
    "AnchorPlacement",
    "build_anchors",
    "build_token_grid",
    "cells_to_otsl",
    "ensure_square",
    "otsl_to_cells",
    "split_rows",
]

ANCHOR_TOKENS = frozenset({"fcel", "ecel"})
CONTINUATION_TOKENS = frozenset({"lcel", "ucel", "xcel"})
CELL_TOKENS = ANCHOR_TOKENS | CONTINUATION_TOKENS
VALID_TOKENS = CELL_TOKENS | {"nl"}


@dataclass(slots=True)
class AnchorPlacement:
    """One ``fcel`` / ``ecel`` anchor mapped to its grid coordinates."""

    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    is_empty: bool = False


def split_rows(tokens: list[str]) -> list[list[str]]:
    """Split a flat cell-token stream on ``nl`` into per-row token lists.

    Rejects any token outside :data:`VALID_TOKENS`. A trailing ``nl`` does
    not produce an empty final row.
    """
    rows: list[list[str]] = [[]]
    for tok in tokens:
        if tok not in VALID_TOKENS:
            msg = f"unknown OTSL token {tok!r}"
            raise ValueError(msg)
        if tok == "nl":
            rows.append([])
        else:
            rows[-1].append(tok)
    if rows and not rows[-1]:
        rows.pop()
    return rows


def ensure_square(rows: list[list[str]]) -> int:
    """Return the common row width, or raise if rows are jagged."""
    if not rows:
        return 0
    widths = {len(r) for r in rows}
    if len(widths) != 1:
        msg = f"OTSL square-table assumption violated; row widths = {sorted(widths)}"
        raise ValueError(msg)
    return next(iter(widths))


def _normalize_edge_continuations(rows: list[list[str]], nrows: int, ncols: int) -> list[list[str]]:
    """Repair structurally-impossible continuations at the grid edges.

    A continuation cannot merge in a direction that has no neighbour:
    row 0 has nothing above, column 0 has nothing to the left. Real
    encoders (and the docling OTSL decoder's "structure error correction")
    emit ``xcel``/``ucel`` in row 0 and ``xcel``/``lcel`` in column 0 that
    must be read as the only possible merge:

    - row 0: ``ucel``/``xcel`` -> ``lcel`` (can only merge left).
    - col 0: ``lcel``/``xcel`` -> ``ucel`` (can only merge up).

    A copy is returned; the caller's rows are not mutated.
    """
    grid = [list(row) for row in rows]
    for c in range(ncols):
        if grid[0][c] in {"ucel", "xcel"}:
            grid[0][c] = "lcel"
    for r in range(nrows):
        if grid[r][0] in {"lcel", "xcel"}:
            grid[r][0] = "ucel"
    return grid


@dataclass(slots=True)
class _OtslReader:
    """Anchor-centric OTSL grid reader (logic adapted from docling, see header).

    ``registry`` mirrors docling's ``registry_2d_span``: cells already
    claimed by a 2D (``xcel``) span, so a later anchor cannot re-claim them.
    """

    grid: list[list[str]]
    nrows: int
    ncols: int
    registry: list[list[bool]]

    def _check_right(self, r: int, c: int) -> int:
        # colspan: extend right over horizontal continuations (lcel/xcel);
        # stop at an anchor, an up-merge, or the edge (docling check_right).
        dist = 1
        x = c
        while x + 1 < self.ncols and self.grid[r][x + 1] in {"lcel", "xcel"}:
            x += 1
            dist += 1
        return dist

    def _check_down(self, r: int, c: int) -> int:
        # rowspan: extend down over vertical continuations (ucel/xcel);
        # stop at an anchor, a left-merge, or the edge (docling check_down).
        dist = 1
        y = r
        while y + 1 < self.nrows and self.grid[y + 1][c] in {"ucel", "xcel"}:
            y += 1
            dist += 1
        return dist

    def _claim_2d(self, r: int, c: int, rowspan: int, colspan: int) -> bool:
        # Mark the rectangle in the registry iff none of it is already
        # claimed (docling's double-count guard); returns whether it claimed.
        for dr in range(rowspan):
            for dc in range(colspan):
                if self.registry[r + dr][c + dc]:
                    return False
        for dr in range(rowspan):
            for dc in range(colspan):
                self.registry[r + dr][c + dc] = True
        return True

    def span_of(self, r: int, c: int) -> tuple[int, int]:
        """Compute (rowspan, colspan) for the anchor at (r, c) from its neighbours."""
        colspan = rowspan = 1
        right = self.grid[r][c + 1] if c + 1 < self.ncols else ""
        below = self.grid[r + 1][c] if r + 1 < self.nrows else ""
        if right == "lcel":
            colspan = self._check_right(r, c)
        if below == "ucel":
            rowspan = self._check_down(r, c)
        if right == "xcel":
            xr = self._check_right(r, c)
            xd = self._check_down(r, c)
            if self._claim_2d(r, c, xd, xr):
                colspan, rowspan = xr, xd
        return rowspan, colspan


def build_anchors(rows: list[list[str]]) -> tuple[int, int, list[AnchorPlacement]]:
    """Walk the row × col grid; return (nrows, ncols, ordered anchors).

    Anchor-centric reconstruction (adapted from docling's ``otsl_to_html``,
    see the module header): each ``fcel``/``ecel`` is an anchor whose span
    is read from its neighbouring continuation tokens — a right ``lcel`` run
    gives colspan, a below ``ucel`` run gives rowspan, and a right ``xcel``
    gives a 2D span guarded by the registry against double-claiming.
    Continuation tokens carry no content and are skipped; anchors are
    returned in row-major order — the order the source ``cells[]`` appear in.
    """
    nrows = len(rows)
    ncols = ensure_square(rows)
    reader = _OtslReader(
        grid=_normalize_edge_continuations(rows, nrows, ncols),
        nrows=nrows,
        ncols=ncols,
        registry=[[False] * ncols for _ in range(nrows)],
    )
    ordered: list[AnchorPlacement] = []
    for r in range(nrows):
        for c in range(ncols):
            tok = reader.grid[r][c]
            if tok not in ANCHOR_TOKENS:
                continue
            rowspan, colspan = reader.span_of(r, c)
            ordered.append(
                AnchorPlacement(
                    row=r, col=c, rowspan=rowspan, colspan=colspan, is_empty=(tok == "ecel")
                )
            )
    return nrows, ncols, ordered


def build_token_grid(sample: TableSample) -> tuple[list[list[str]], list[GridCell]]:
    """Lay a sample's cells onto a 2D token grid.

    Returns ``(grid, anchors)`` where ``grid[r][c]`` is one of the five
    cell tokens and ``anchors`` is the row-major list of the anchor cells
    (so callers can attach per-cell content / bbox in the right order).
    A cell with empty ``tokens`` becomes ``ecel``; otherwise ``fcel``.
    """
    grid: list[list[str]] = [[""] * sample.ncols for _ in range(sample.nrows)]
    anchored = sorted(sample.cells, key=lambda c: (c.row, c.col))
    for cell in anchored:
        grid[cell.row][cell.col] = "ecel" if not cell.tokens else "fcel"
        for dr in range(cell.rowspan):
            for dc in range(cell.colspan):
                if dr == 0 and dc == 0:
                    continue
                rr, cc = cell.row + dr, cell.col + dc
                if dr == 0:
                    grid[rr][cc] = "lcel"
                elif dc == 0:
                    grid[rr][cc] = "ucel"
                else:
                    grid[rr][cc] = "xcel"
    return grid, anchored


# ---------- OTSL payload <-> GridCells ----------


def otsl_to_cells(
    otsl_tokens: list[str], cell_payloads: list[dict[str, object]]
) -> tuple[int, int, tuple[GridCell, ...]]:
    """Map an OTSL token stream + positional ``cells[]`` to GridCells.

    Returns ``(nrows, ncols, cells)``. Every cell defaults to
    ``role="body"`` (the OTSL core has no header marker). Raises if the
    anchor count and ``cells[]`` length disagree.
    """
    rows = split_rows(otsl_tokens)
    nrows, ncols, anchors = build_anchors(rows)
    if len(anchors) != len(cell_payloads):
        msg = (
            f"OTSL declares {len(anchors)} anchored cells but cells[] has "
            f"{len(cell_payloads)} entries"
        )
        raise ValueError(msg)

    cells: list[GridCell] = []
    for anchor, cell_payload in zip(anchors, cell_payloads, strict=True):
        tokens = tuple(cast("tuple[str, ...]", cell_payload.get("tokens", ())))
        bbox_raw = cell_payload.get("bbox")
        bbox = None
        if bbox_raw is not None:
            seq = cast("list[int]", bbox_raw)
            bbox = (int(seq[0]), int(seq[1]), int(seq[2]), int(seq[3]))
        cells.append(
            GridCell(
                row=anchor.row,
                col=anchor.col,
                rowspan=anchor.rowspan,
                colspan=anchor.colspan,
                tokens=tokens,
                bbox=bbox,
                role="body",
            )
        )
    return nrows, ncols, tuple(cells)


def cells_to_otsl(sample: TableSample) -> tuple[list[str], list[dict[str, object]]]:
    """Serialize a sample to an OTSL token stream + positional ``cells[]``."""
    grid, emitted_order = build_token_grid(sample)
    tokens: list[str] = []
    for row in grid:
        tokens.extend(row)
        tokens.append("nl")
    cell_payloads: list[dict[str, object]] = []
    for cell in emitted_order:
        payload: dict[str, object] = {"tokens": list(cell.tokens)}
        if cell.bbox is not None:
            payload["bbox"] = list(cell.bbox)
        cell_payloads.append(payload)
    return tokens, cell_payloads
