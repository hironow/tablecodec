"""Property-based tests for SPEC §5.2 invariants.

Per docs/intent.md M1 Acceptance Criteria:

- "valid な TableSample を生成 → すべての invariant がパス"
- "特定の invariant を壊した時、その invariant のみが失敗を報告"
- "hypothesis が 10,000 ケース回って fail なし"
"""

from __future__ import annotations

import dataclasses

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from strategies import valid_tablesample_st

from tablecodec import profiles, validate
from tablecodec._invariants import (
    check_i01_nrows_ncols_positive,
    check_i02_cell_in_bounds,
    check_i03_span_in_bounds,
    check_i04_grid_exact_cover,
    check_i05_bbox_well_formed,
    check_i06_header_contiguous_top,
    check_i07_tokens_is_tuple,
)
from tablecodec.ir import GridCell, TableSample


@given(valid_tablesample_st())
@settings(
    max_examples=10_000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
def test_valid_sample_passes_default_profile(sample: TableSample) -> None:
    # then
    assert validate(sample, profile=profiles.DEFAULT) == []


@given(valid_tablesample_st())
@settings(
    max_examples=2_000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
def test_valid_sample_passes_lenient_profile(sample: TableSample) -> None:
    # then
    assert validate(sample, profile=profiles.LENIENT) == []


@given(valid_tablesample_st())
@settings(
    max_examples=2_000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
def test_valid_sample_with_covering_image_dims_passes_strict(sample: TableSample) -> None:
    # given — image dimensions chosen to contain every cell bbox (STRICT, ADR
    # 0012: a bbox-bearing sample needs dims and every bbox must lie within).
    boxes = [c.bbox for c in sample.cells if c.bbox is not None]
    if boxes:
        sample = dataclasses.replace(
            sample,
            image_width=max(x1 for _, _, x1, _ in boxes),
            image_height=max(y1 for _, _, _, y1 in boxes),
        )

    # then — no STRICT-specific finding (bboxes fit; or no bbox so none needed).
    errors = validate(sample, profile=profiles.STRICT)
    assert not any(e.invariant.startswith("STRICT-") for e in errors)


@given(valid_tablesample_st(), st.integers(min_value=-3, max_value=0))
@settings(
    max_examples=1_000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
def test_broken_nrows_reports_i01_only_in_its_checker(sample: TableSample, bad_nrows: int) -> None:
    # given — replace nrows with a value <= 0.
    broken = dataclasses.replace(sample, nrows=bad_nrows)

    # when
    errs_i01 = check_i01_nrows_ncols_positive(broken)
    errs_i02 = check_i02_cell_in_bounds(broken)

    # then — I-01 must fire; I-02 may fire (rows now out of bounds), but
    # every error I-01 produces must carry the I-01 invariant id.
    assert len(errs_i01) >= 1
    assert all(e.invariant == "I-01" for e in errs_i01)
    # I-02 errors, if any, must be I-02 (not I-01).
    assert all(e.invariant == "I-02" for e in errs_i02)


@given(valid_tablesample_st(max_nrows=3, max_ncols=3))
@settings(
    max_examples=1_000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
def test_broken_bbox_reports_i05_only_in_its_checker(sample: TableSample) -> None:
    # given — make every cell content-bearing (I-05 guards only those; an
    # empty cell's bbox is a placeholder, see ADR 0007) with a degenerate
    # bbox (x0 == x1).
    broken_cells = tuple(
        dataclasses.replace(cell, tokens=("x",), bbox=(0, 0, 0, 10)) for cell in sample.cells
    )
    broken = dataclasses.replace(sample, cells=broken_cells)

    # when
    errs = check_i05_bbox_well_formed(broken)

    # then — at least one I-05 finding per cell, all labelled I-05.
    assert len(errs) >= len(broken_cells)
    assert all(e.invariant == "I-05" for e in errs)


@given(valid_tablesample_st(max_nrows=3, max_ncols=3))
@settings(
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
def test_dropping_a_cell_triggers_i04_only(sample: TableSample) -> None:
    # given — remove one cell to create a gap.
    if not sample.cells:
        return
    broken_cells = sample.cells[:-1]
    broken = dataclasses.replace(sample, cells=broken_cells)

    # when
    errs_i04 = check_i04_grid_exact_cover(broken)
    errs_i01 = check_i01_nrows_ncols_positive(broken)
    errs_i02 = check_i02_cell_in_bounds(broken)
    errs_i03 = check_i03_span_in_bounds(broken)
    errs_i07 = check_i07_tokens_is_tuple(broken)

    # then — I-04 must catch the gap; the other invariants (which were
    # satisfied before the drop) must still pass after the drop.
    assert any(e.invariant == "I-04" for e in errs_i04)
    assert errs_i01 == []
    assert errs_i02 == []
    assert errs_i03 == []
    assert errs_i07 == []


@given(valid_tablesample_st(max_nrows=3, max_ncols=3))
@settings(
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
def test_swapping_header_below_body_triggers_i06(sample: TableSample) -> None:
    # given — flip the first cell to header and ensure another later cell is
    # body. If the sample has fewer than 2 rows there is nothing to break.
    if sample.nrows < 2:
        return
    # Pick a cell at row >= 1 that is currently body, and a cell at row 0.
    body_at_or_below_one: GridCell | None = None
    for cell in sample.cells:
        if cell.row >= 1 and cell.role == "body":
            body_at_or_below_one = cell
            break
    if body_at_or_below_one is None:
        return

    new_cells: list[GridCell] = []
    for cell in sample.cells:
        if cell is body_at_or_below_one:
            new_cells.append(dataclasses.replace(cell, role="header"))
        else:
            new_cells.append(cell)
    # Force the first cell to body so we have at least one body row 0.
    new_cells[0] = dataclasses.replace(new_cells[0], role="body")
    broken = dataclasses.replace(sample, cells=tuple(new_cells))

    # when
    errs = check_i06_header_contiguous_top(broken)

    # then
    assert any(e.invariant == "I-06" for e in errs)
