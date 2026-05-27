"""Tests for tablecodec._invariants — SPEC §5.2 invariants I-01..I-07.

Every invariant has at least one positive (passes) and one negative
(rejects, with the right invariant id reported) test case.
"""

from __future__ import annotations

from tablecodec._invariants import (
    ValidationError,
    check_i01_nrows_ncols_positive,
    check_i02_cell_in_bounds,
    check_i03_span_in_bounds,
    check_i04_grid_exact_cover,
    check_i05_bbox_well_formed,
    check_i06_header_contiguous_top,
    check_i07_tokens_is_tuple,
)
from tablecodec.ir import GridCell, TableSample


def _single_cell_sample(nrows: int = 1, ncols: int = 1, **cell_kwargs: object) -> TableSample:
    return TableSample(
        filename="x.png",
        nrows=nrows,
        ncols=ncols,
        cells=(GridCell(row=0, col=0, rowspan=nrows, colspan=ncols, **cell_kwargs),),  # type: ignore[arg-type]
    )


# ---------- I-01: nrows >= 1 and ncols >= 1 ----------


class TestI01:
    def test_positive_minimal_grid(self) -> None:
        # given
        sample = _single_cell_sample(nrows=1, ncols=1)

        # when
        errors = check_i01_nrows_ncols_positive(sample)

        # then
        assert errors == []

    def test_rejects_zero_nrows(self) -> None:
        # given
        sample = TableSample(filename="x.png", nrows=0, ncols=1, cells=())

        # when
        errors = check_i01_nrows_ncols_positive(sample)

        # then
        assert len(errors) == 1
        assert errors[0].invariant == "I-01"

    def test_rejects_zero_ncols(self) -> None:
        # given
        sample = TableSample(filename="x.png", nrows=1, ncols=0, cells=())

        # when
        errors = check_i01_nrows_ncols_positive(sample)

        # then
        assert len(errors) == 1
        assert errors[0].invariant == "I-01"

    def test_rejects_negative(self) -> None:
        # given
        sample = TableSample(filename="x.png", nrows=-1, ncols=-1, cells=())

        # when
        errors = check_i01_nrows_ncols_positive(sample)

        # then
        assert all(e.invariant == "I-01" for e in errors)
        assert len(errors) >= 1


# ---------- I-02: 0 <= row < nrows, 0 <= col < ncols ----------


class TestI02:
    def test_positive(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(
                GridCell(0, 0),
                GridCell(0, 1),
                GridCell(1, 0),
                GridCell(1, 1),
            ),
        )

        # when
        errors = check_i02_cell_in_bounds(sample)

        # then
        assert errors == []

    def test_rejects_row_out_of_bounds(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=1,
            cells=(GridCell(row=5, col=0),),
        )

        # when
        errors = check_i02_cell_in_bounds(sample)

        # then
        assert any(e.invariant == "I-02" for e in errors)

    def test_rejects_negative_col(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=1,
            cells=(GridCell(row=0, col=-1),),
        )

        # when
        errors = check_i02_cell_in_bounds(sample)

        # then
        assert any(e.invariant == "I-02" for e in errors)

    def test_reports_cell_index(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(GridCell(0, 0), GridCell(row=10, col=10)),
        )

        # when
        errors = check_i02_cell_in_bounds(sample)

        # then
        assert any(e.cell_index == 1 for e in errors)


# ---------- I-03: row + rowspan <= nrows, col + colspan <= ncols ----------


class TestI03:
    def test_positive_full_span(self) -> None:
        # given
        sample = _single_cell_sample(nrows=3, ncols=3)

        # when
        errors = check_i03_span_in_bounds(sample)

        # then
        assert errors == []

    def test_rejects_rowspan_overshoot(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(GridCell(row=0, col=0, rowspan=5, colspan=1),),
        )

        # when
        errors = check_i03_span_in_bounds(sample)

        # then
        assert any(e.invariant == "I-03" for e in errors)

    def test_rejects_colspan_overshoot(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(GridCell(row=0, col=0, rowspan=1, colspan=5),),
        )

        # when
        errors = check_i03_span_in_bounds(sample)

        # then
        assert any(e.invariant == "I-03" for e in errors)

    def test_rejects_zero_or_negative_span(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(GridCell(row=0, col=0, rowspan=0, colspan=1),),
        )

        # when
        errors = check_i03_span_in_bounds(sample)

        # then — SPEC §5.1 docstring states "must be >= 1".
        assert any(e.invariant == "I-03" for e in errors)

    def test_rejects_zero_colspan(self) -> None:
        # given — separate branch from zero rowspan.
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(GridCell(row=0, col=0, rowspan=1, colspan=0),),
        )

        # when
        errors = check_i03_span_in_bounds(sample)

        # then
        assert any(e.invariant == "I-03" for e in errors)


# ---------- I-04: union of footprints exactly covers nrows × ncols ----------


class TestI04:
    def test_positive_full_coverage(self) -> None:
        # given — 2x2 fully covered with 4 cells.
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(
                GridCell(0, 0),
                GridCell(0, 1),
                GridCell(1, 0),
                GridCell(1, 1),
            ),
        )

        # when
        errors = check_i04_grid_exact_cover(sample)

        # then
        assert errors == []

    def test_positive_with_spans(self) -> None:
        # given — 2x2 covered by one 2x2 cell.
        sample = _single_cell_sample(nrows=2, ncols=2)

        # when
        errors = check_i04_grid_exact_cover(sample)

        # then
        assert errors == []

    def test_rejects_gap(self) -> None:
        # given — 2x2 with cell (1,1) missing.
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(
                GridCell(0, 0),
                GridCell(0, 1),
                GridCell(1, 0),
            ),
        )

        # when
        errors = check_i04_grid_exact_cover(sample)

        # then
        assert any(e.invariant == "I-04" for e in errors)

    def test_rejects_overlap(self) -> None:
        # given — two cells claim (0, 0).
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=2,
            cells=(
                GridCell(row=0, col=0, colspan=2),
                GridCell(row=0, col=0),
            ),
        )

        # when
        errors = check_i04_grid_exact_cover(sample)

        # then
        assert any(e.invariant == "I-04" for e in errors)

    def test_rejects_out_of_grid_cells_gracefully(self) -> None:
        # given — cell positioned outside the grid; I-02/I-03 catch it,
        # but I-04 must not raise, and must still report under-coverage.
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(GridCell(row=5, col=5),),
        )

        # when
        errors = check_i04_grid_exact_cover(sample)

        # then — under-coverage of the 2x2 grid is the I-04 finding.
        assert any(e.invariant == "I-04" for e in errors)

    def test_no_double_report_when_grid_is_degenerate(self) -> None:
        # given — nrows=0; I-01 already reports this, so I-04 must
        # short-circuit silently and not double-report.
        sample = TableSample(filename="x.png", nrows=0, ncols=1, cells=())

        # when
        errors = check_i04_grid_exact_cover(sample)

        # then
        assert errors == []

    def test_gap_message_truncates_with_more_suffix(self) -> None:
        # given — a totally empty grid larger than _GAP_PREVIEW_LIMIT (5)
        # produces a "+N more" suffix instead of dumping every coordinate.
        sample = TableSample(filename="x.png", nrows=3, ncols=3, cells=())

        # when
        errors = check_i04_grid_exact_cover(sample)

        # then
        assert len(errors) == 1
        assert "more)" in errors[0].message


# ---------- I-05: bbox well-formed when set ----------


class TestI05:
    def test_positive_with_valid_bbox(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=1,
            cells=(GridCell(row=0, col=0, bbox=(0, 0, 10, 20)),),
        )

        # when
        errors = check_i05_bbox_well_formed(sample)

        # then
        assert errors == []

    def test_positive_with_none_bbox(self) -> None:
        # given
        sample = _single_cell_sample()

        # when
        errors = check_i05_bbox_well_formed(sample)

        # then
        assert errors == []

    def test_rejects_degenerate_x(self) -> None:
        # given — x0 == x2
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=1,
            cells=(GridCell(row=0, col=0, bbox=(5, 0, 5, 20)),),
        )

        # when
        errors = check_i05_bbox_well_formed(sample)

        # then
        assert any(e.invariant == "I-05" for e in errors)

    def test_rejects_inverted_y(self) -> None:
        # given — y0 > y2
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=1,
            cells=(GridCell(row=0, col=0, bbox=(0, 20, 10, 0)),),
        )

        # when
        errors = check_i05_bbox_well_formed(sample)

        # then
        assert any(e.invariant == "I-05" for e in errors)


# ---------- I-06: header cells form a contiguous top region ----------


class TestI06:
    def test_positive_no_headers(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=1,
            cells=(GridCell(0, 0), GridCell(1, 0)),
        )

        # when
        errors = check_i06_header_contiguous_top(sample)

        # then
        assert errors == []

    def test_positive_header_row_on_top(self) -> None:
        # given — row 0 is all headers, row 1 is body.
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(
                GridCell(0, 0, role="header"),
                GridCell(0, 1, role="header"),
                GridCell(1, 0, role="body"),
                GridCell(1, 1, role="body"),
            ),
        )

        # when
        errors = check_i06_header_contiguous_top(sample)

        # then
        assert errors == []

    def test_rejects_header_below_body(self) -> None:
        # given — row 0 body, row 1 header.
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=1,
            cells=(
                GridCell(0, 0, role="body"),
                GridCell(1, 0, role="header"),
            ),
        )

        # when
        errors = check_i06_header_contiguous_top(sample)

        # then
        assert any(e.invariant == "I-06" for e in errors)

    def test_positive_all_headers(self) -> None:
        # given — every cell is a header (degenerate but valid: empty body).
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=2,
            cells=(
                GridCell(0, 0, role="header"),
                GridCell(0, 1, role="header"),
            ),
        )

        # when
        errors = check_i06_header_contiguous_top(sample)

        # then
        assert errors == []

    def test_rejects_mixed_role_in_top_rows(self) -> None:
        # given — row 0 is mixed header/body; SPEC §5.2 I-06 wants a
        # contiguous top region of header rows, so a body cell in a
        # header row is a violation.
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(
                GridCell(0, 0, role="header"),
                GridCell(0, 1, role="body"),
                GridCell(1, 0, role="header"),  # header below body row
                GridCell(1, 1, role="body"),
            ),
        )

        # when
        errors = check_i06_header_contiguous_top(sample)

        # then
        assert any(e.invariant == "I-06" for e in errors)


# ---------- I-07: tokens is a tuple (never None) ----------


class TestI07:
    def test_positive_empty_tokens(self) -> None:
        # given
        sample = _single_cell_sample(tokens=())

        # when
        errors = check_i07_tokens_is_tuple(sample)

        # then
        assert errors == []

    def test_positive_with_tokens(self) -> None:
        # given
        sample = _single_cell_sample(tokens=("a", "b"))

        # when
        errors = check_i07_tokens_is_tuple(sample)

        # then
        assert errors == []

    def test_rejects_none_tokens(self) -> None:
        # given — bypass the dataclass typing to inject None.
        cell = GridCell(row=0, col=0)
        bad = object.__new__(GridCell)
        object.__setattr__(bad, "row", 0)
        object.__setattr__(bad, "col", 0)
        object.__setattr__(bad, "rowspan", 1)
        object.__setattr__(bad, "colspan", 1)
        object.__setattr__(bad, "tokens", None)
        object.__setattr__(bad, "bbox", None)
        object.__setattr__(bad, "role", "body")
        sample = TableSample(filename="x.png", nrows=1, ncols=1, cells=(bad,))

        # when
        errors = check_i07_tokens_is_tuple(sample)

        # then
        assert any(e.invariant == "I-07" for e in errors)
        # sanity: the well-formed cell would have passed
        assert (
            check_i07_tokens_is_tuple(
                TableSample(filename="x.png", nrows=1, ncols=1, cells=(cell,))
            )
            == []
        )


# ---------- ValidationError shape ----------


class TestValidationError:
    def test_is_frozen_and_hashable(self) -> None:
        # given
        a = ValidationError(invariant="I-01", message="bad", cell_index=None)
        b = ValidationError(invariant="I-01", message="bad", cell_index=None)

        # when / then
        assert hash(a) == hash(b)
        assert {a, b} == {a}
