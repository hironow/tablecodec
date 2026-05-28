"""SPEC §5.2 invariants I-01..I-07 as independent check functions.

Each ``check_iXX`` returns a list of :class:`ValidationError` describing every
violation it found (empty list = pass). Functions never raise on data; they
raise only on programmer error (e.g. wrong type passed in).

Functions are pure and read-only. They never mutate the input.
"""

from __future__ import annotations

from dataclasses import dataclass

from tablecodec.ir import TableSample

__all__ = [
    "ValidationError",
    "check_i01_nrows_ncols_positive",
    "check_i02_cell_in_bounds",
    "check_i03_span_in_bounds",
    "check_i04_grid_exact_cover",
    "check_i05_bbox_well_formed",
    "check_i06_header_contiguous_top",
    "check_i07_tokens_is_tuple",
]

# Cap how many gap coordinates I-04 enumerates in its error message,
# so a totally empty grid does not produce a multi-megabyte string.
_GAP_PREVIEW_LIMIT = 5


@dataclass(frozen=True, slots=True)
class ValidationError:
    """A single invariant violation.

    Attributes:
        invariant: The SPEC §5.2 id (``"I-01"`` ... ``"I-07"``).
        message: Human-readable description of the violation.
        cell_index: Index into ``TableSample.cells`` if applicable, else
            ``None`` (e.g. grid-level invariants like I-01, I-04).
    """

    invariant: str
    message: str
    cell_index: int | None = None


# ---------- I-01: nrows >= 1 and ncols >= 1 ----------


def check_i01_nrows_ncols_positive(sample: TableSample) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if sample.nrows < 1:
        errors.append(
            ValidationError(invariant="I-01", message=f"nrows must be >= 1, got {sample.nrows}")
        )
    if sample.ncols < 1:
        errors.append(
            ValidationError(invariant="I-01", message=f"ncols must be >= 1, got {sample.ncols}")
        )
    return errors


# ---------- I-02: 0 <= row < nrows, 0 <= col < ncols ----------


def check_i02_cell_in_bounds(sample: TableSample) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for idx, cell in enumerate(sample.cells):
        if cell.row < 0 or cell.row >= sample.nrows:
            errors.append(
                ValidationError(
                    invariant="I-02",
                    message=(f"row {cell.row} out of [0, {sample.nrows}) at cell index {idx}"),
                    cell_index=idx,
                )
            )
        if cell.col < 0 or cell.col >= sample.ncols:
            errors.append(
                ValidationError(
                    invariant="I-02",
                    message=(f"col {cell.col} out of [0, {sample.ncols}) at cell index {idx}"),
                    cell_index=idx,
                )
            )
    return errors


# ---------- I-03: row + rowspan <= nrows, col + colspan <= ncols ----------


def check_i03_span_in_bounds(sample: TableSample) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for idx, cell in enumerate(sample.cells):
        # SPEC §5.1: rowspan/colspan must be >= 1.
        if cell.rowspan < 1:
            errors.append(
                ValidationError(
                    invariant="I-03",
                    message=f"rowspan must be >= 1, got {cell.rowspan} at cell index {idx}",
                    cell_index=idx,
                )
            )
        if cell.colspan < 1:
            errors.append(
                ValidationError(
                    invariant="I-03",
                    message=f"colspan must be >= 1, got {cell.colspan} at cell index {idx}",
                    cell_index=idx,
                )
            )
        if cell.row + cell.rowspan > sample.nrows:
            errors.append(
                ValidationError(
                    invariant="I-03",
                    message=(
                        f"row+rowspan = {cell.row + cell.rowspan} exceeds nrows "
                        f"{sample.nrows} at cell index {idx}"
                    ),
                    cell_index=idx,
                )
            )
        if cell.col + cell.colspan > sample.ncols:
            errors.append(
                ValidationError(
                    invariant="I-03",
                    message=(
                        f"col+colspan = {cell.col + cell.colspan} exceeds ncols "
                        f"{sample.ncols} at cell index {idx}"
                    ),
                    cell_index=idx,
                )
            )
    return errors


# ---------- I-04: union of cell footprints exactly covers the grid ----------


def check_i04_grid_exact_cover(sample: TableSample) -> list[ValidationError]:
    """Check the cell footprints exactly cover the ``nrows × ncols`` grid.

    Implementation: 2D occupancy bitmap. For every cell, iterate over its
    footprint and increment the count at each (row, col). Overlap = any
    count > 1; gap = any count == 0 inside the grid.

    Out-of-grid cell coordinates (caught by I-02/I-03) are skipped here so
    this check never raises; under-coverage of the in-grid cells is still
    reported, which is the right user-visible outcome.

    Complexity: O(N) where N = sum of all footprint areas.
    """
    errors: list[ValidationError] = []

    # I-01 must hold for the grid to make sense.
    if sample.nrows < 1 or sample.ncols < 1:
        # I-01 already reports this; do not double-report under I-04.
        return errors

    occupancy = [[0] * sample.ncols for _ in range(sample.nrows)]

    for idx, cell in enumerate(sample.cells):
        # Defensive clipping: stay within bounds even if I-02/I-03 violated.
        r0 = max(0, cell.row)
        c0 = max(0, cell.col)
        r1 = min(sample.nrows, cell.row + max(1, cell.rowspan))
        c1 = min(sample.ncols, cell.col + max(1, cell.colspan))

        for r in range(r0, r1):
            row = occupancy[r]
            for c in range(c0, c1):
                row[c] += 1
                if row[c] > 1:
                    errors.append(
                        ValidationError(
                            invariant="I-04",
                            message=(
                                f"overlap at (row={r}, col={c}); cell index {idx} "
                                f"overlaps a previously placed cell"
                            ),
                            cell_index=idx,
                        )
                    )

    gaps: list[tuple[int, int]] = [
        (r, c) for r, row in enumerate(occupancy) for c, count in enumerate(row) if count == 0
    ]
    if gaps:
        # Report a single I-04 error with the first few coordinates to
        # keep error volume bounded for pathological cases.
        preview = gaps[:_GAP_PREVIEW_LIMIT]
        extra = len(gaps) - _GAP_PREVIEW_LIMIT
        suffix = f" (+{extra} more)" if extra > 0 else ""
        errors.append(
            ValidationError(
                invariant="I-04",
                message=f"gap(s) in grid coverage at {preview}{suffix}",
            )
        )

    return errors


# ---------- I-05: bbox well-formed when set ----------


def check_i05_bbox_well_formed(sample: TableSample) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for idx, cell in enumerate(sample.cells):
        bbox = cell.bbox
        if bbox is None:
            continue
        if not cell.tokens:
            # I-05 guards a box that *localizes content*. An empty cell
            # localizes nothing and datasets routinely give it a zero-area
            # placeholder box, so its geometry is out of scope (spec §5.2,
            # ADR 0007). The bbox itself is still kept on the IR.
            continue
        x0, y0, x1, y1 = bbox
        if x0 >= x1:
            errors.append(
                ValidationError(
                    invariant="I-05",
                    message=(f"bbox x0 >= x1 ({x0} >= {x1}) at cell index {idx}"),
                    cell_index=idx,
                )
            )
        if y0 >= y1:
            errors.append(
                ValidationError(
                    invariant="I-05",
                    message=(f"bbox y0 >= y1 ({y0} >= {y1}) at cell index {idx}"),
                    cell_index=idx,
                )
            )
    return errors


# ---------- I-06: header cells form a contiguous top region ----------


def check_i06_header_contiguous_top(sample: TableSample) -> list[ValidationError]:
    """Check headers form a contiguous top-region of the grid.

    Reads "contiguous top region" as: there exists an integer
    ``H in [0, nrows]`` such that every cell anchored at ``row < H`` is a
    header and every cell anchored at ``row >= H`` is a body cell. H is the
    smallest row at which any body cell appears.
    """
    errors: list[ValidationError] = []

    body_rows = [c.row for c in sample.cells if c.role == "body"]
    header_rows = [c.row for c in sample.cells if c.role == "header"]
    if not header_rows:
        return errors

    if not body_rows:
        # All headers — fine; the header region spans the whole grid.
        return errors

    first_body_row = min(body_rows)

    for idx, cell in enumerate(sample.cells):
        if cell.role == "header" and cell.row >= first_body_row:
            errors.append(
                ValidationError(
                    invariant="I-06",
                    message=(
                        f"header cell at row {cell.row} (cell index {idx}) appears "
                        f"at or below the first body row {first_body_row}"
                    ),
                    cell_index=idx,
                )
            )
    return errors


# ---------- I-07: tokens is a tuple (never None) ----------


def check_i07_tokens_is_tuple(sample: TableSample) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for idx, cell in enumerate(sample.cells):
        # Runtime defense: callers can bypass the static type with
        # ``object.__setattr__`` and inject None / list. SPEC §5.2 I-07
        # requires this be reported, so the runtime check is intentional.
        if not isinstance(cell.tokens, tuple):  # pyright: ignore[reportUnnecessaryIsInstance]
            errors.append(
                ValidationError(
                    invariant="I-07",
                    message=(
                        f"tokens must be a tuple (possibly empty) at cell index "
                        f"{idx}, got {type(cell.tokens).__name__}"
                    ),
                    cell_index=idx,
                )
            )
    return errors
