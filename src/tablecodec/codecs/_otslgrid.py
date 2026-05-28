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

Derived from the paper, not copied from upstream reference code.
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


def _resolve_anchor_at(
    anchors: list[list[AnchorPlacement | None]], r: int, c: int, kind: str
) -> AnchorPlacement:
    """Return the anchor referenced by a continuation token at (r, c)."""
    if kind == "lcel":
        ref = anchors[r][c - 1] if c > 0 else None
    elif kind == "ucel":
        ref = anchors[r - 1][c] if r > 0 else None
    elif kind == "xcel":
        ref = anchors[r - 1][c - 1] if r > 0 and c > 0 else None
    else:  # pragma: no cover - defensive
        msg = f"unexpected continuation kind {kind!r}"
        raise ValueError(msg)
    if ref is None:
        msg = f"OTSL continuation {kind!r} at (row={r}, col={c}) has no anchor"
        raise ValueError(msg)
    return ref


def build_anchors(rows: list[list[str]]) -> tuple[int, int, list[AnchorPlacement]]:
    """Walk the row × col grid; return (nrows, ncols, ordered anchors).

    Anchors are returned in row-major order — the same order the source
    cell content (OTSL ``cells[]`` / DocTags content tokens) appears in.
    """
    nrows = len(rows)
    ncols = ensure_square(rows)
    anchors: list[list[AnchorPlacement | None]] = [[None] * ncols for _ in range(nrows)]
    ordered: list[AnchorPlacement] = []

    for r in range(nrows):
        for c in range(ncols):
            tok = rows[r][c]
            if tok in ANCHOR_TOKENS:
                anchor = AnchorPlacement(row=r, col=c, is_empty=(tok == "ecel"))
                anchors[r][c] = anchor
                ordered.append(anchor)
            else:
                anchor = _resolve_anchor_at(anchors, r, c, tok)
                anchors[r][c] = anchor
                if tok in {"lcel", "xcel"}:
                    anchor.colspan = max(anchor.colspan, c - anchor.col + 1)
                if tok in {"ucel", "xcel"}:
                    anchor.rowspan = max(anchor.rowspan, r - anchor.row + 1)
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
