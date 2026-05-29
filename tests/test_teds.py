"""Tests for tablecodec.teds — the TEDS similarity metric (optional [teds]).

Skipped unless the [teds] extra (apted + lxml) is installed. Run with
``uv run --extra teds pytest tests/test_teds.py``.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("apted")
pytest.importorskip("lxml")

from tablecodec.ir import GridCell, TableSample
from tablecodec.teds import teds, teds_html


def _table(*, h1: str = "H1", h2: str = "H2", a: str = "a", b: str = "b") -> TableSample:
    """A 2x2 table: one header row, one body row, with overridable content."""
    return TableSample(
        filename="t.png",
        nrows=2,
        ncols=2,
        cells=(
            GridCell(row=0, col=0, tokens=(h1,), role="header"),
            GridCell(row=0, col=1, tokens=(h2,), role="header"),
            GridCell(row=1, col=0, tokens=(a,), role="body"),
            GridCell(row=1, col=1, tokens=(b,), role="body"),
        ),
    )


class TestIdentity:
    @pytest.mark.parametrize(
        "sample",
        [
            pytest.param(_table(), id="2x2-header-body"),
            pytest.param(
                TableSample(
                    filename="t.png",
                    nrows=1,
                    ncols=1,
                    cells=(GridCell(row=0, col=0, tokens=("solo",)),),
                ),
                id="single-cell",
            ),
            pytest.param(
                TableSample(
                    filename="t.png",
                    nrows=2,
                    ncols=2,
                    cells=(
                        GridCell(row=0, col=0, tokens=("wide",), colspan=2, role="header"),
                        GridCell(row=1, col=0, tokens=("x",)),
                        GridCell(row=1, col=1, tokens=("y",)),
                    ),
                ),
                id="colspan",
            ),
        ],
    )
    def test_identical_sample_scores_one(self, sample: TableSample) -> None:
        # given / when
        score = teds(sample, sample)

        # then
        assert math.isclose(score, 1.0)

    def test_structure_only_identical_scores_one(self) -> None:
        # given
        sample = _table()

        # when
        score = teds(sample, sample, structure_only=True)

        # then
        assert math.isclose(score, 1.0)


class TestContentSensitivity:
    def test_changed_cell_text_lowers_score(self) -> None:
        # given — same structure, one body cell text differs.
        pred = _table(a="a")
        true = _table(a="completely-different")

        # when
        score = teds(pred, true)

        # then — strictly between 0 and 1.
        assert 0.0 < score < 1.0

    def test_structure_only_ignores_cell_text(self) -> None:
        # given — identical structure, different content everywhere.
        pred = _table(h1="X", h2="Y", a="P", b="Q")
        true = _table(h1="1", h2="2", a="3", b="4")

        # when
        score_struct = teds(pred, true, structure_only=True)
        score_full = teds(pred, true)

        # then — structure is identical, content is not.
        assert math.isclose(score_struct, 1.0)
        assert score_full < 1.0


class TestStructureSensitivity:
    def test_extra_row_lowers_score(self) -> None:
        # given — true has an additional body row.
        pred = _table()
        true = TableSample(
            filename="t.png",
            nrows=3,
            ncols=2,
            cells=(
                GridCell(row=0, col=0, tokens=("H1",), role="header"),
                GridCell(row=0, col=1, tokens=("H2",), role="header"),
                GridCell(row=1, col=0, tokens=("a",)),
                GridCell(row=1, col=1, tokens=("b",)),
                GridCell(row=2, col=0, tokens=("c",)),
                GridCell(row=2, col=1, tokens=("d",)),
            ),
        )

        # when
        score = teds(pred, true)

        # then
        assert 0.0 < score < 1.0

    def test_changed_span_lowers_score(self) -> None:
        # given — same grid footprint but a different colspan split.
        pred = TableSample(
            filename="t.png",
            nrows=1,
            ncols=2,
            cells=(GridCell(row=0, col=0, tokens=("wide",), colspan=2),),
        )
        true = TableSample(
            filename="t.png",
            nrows=1,
            ncols=2,
            cells=(
                GridCell(row=0, col=0, tokens=("wide",)),
                GridCell(row=0, col=1, tokens=("",)),
            ),
        )

        # when
        score = teds(pred, true)

        # then
        assert 0.0 <= score < 1.0


class TestBounds:
    def test_score_is_in_unit_interval(self) -> None:
        # given
        pred = _table(a="x")
        true = _table(a="y", b="z")

        # when
        score = teds(pred, true)

        # then
        assert 0.0 <= score <= 1.0

    def test_symmetric_when_node_counts_match(self) -> None:
        # given — same structure (equal node counts), different content.
        pred = _table(a="left")
        true = _table(a="right")

        # when / then — equal denominators => symmetric.
        assert math.isclose(teds(pred, true), teds(true, pred))


class TestTedsHtml:
    def test_empty_prediction_scores_zero(self) -> None:
        # given — an empty HTML prediction.
        true_html = "<html><body><table><tr><td>a</td></tr></table></body></html>"

        # when
        score = teds_html("", true_html)

        # then
        assert math.isclose(score, 0.0, abs_tol=1e-9)

    def test_no_table_scores_zero(self) -> None:
        # given — well-formed HTML with no <table>.
        # when
        score = teds_html(
            "<html><body><p>hi</p></body></html>", "<html><body><p>hi</p></body></html>"
        )

        # then
        assert math.isclose(score, 0.0, abs_tol=1e-9)

    def test_identical_html_scores_one(self) -> None:
        # given
        html = "<html><body><table><tr><td>a</td><td>b</td></tr></table></body></html>"

        # when
        score = teds_html(html, html)

        # then
        assert math.isclose(score, 1.0)
