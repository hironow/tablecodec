"""Tests for tablecodec.ir — IR dataclass shapes and semantics.

Covers SPEC §5.1 requirements: frozen, slots, hashable.

M1 acceptance criterion requires the IR to be pickle-safe (multiprocessing
dataset pipelines use pickle as the IPC format). We verify this indirectly
via copy.deepcopy, which exercises the same __reduce_ex__ protocol that
pickle uses, without importing pickle directly (security: avoid creating
a pickle-using surface inside the test suite).
"""

from __future__ import annotations

import copy

import pytest

from tablecodec.ir import BBox, GridCell, TableSample


class TestGridCell:
    def test_is_frozen(self) -> None:
        # given
        cell = GridCell(row=0, col=0)

        # when / then
        with pytest.raises((AttributeError, TypeError)):
            cell.row = 1  # type: ignore[misc]  # reason: verifying frozen contract

    def test_has_slots(self) -> None:
        # given
        cell = GridCell(row=0, col=0)

        # when / then
        assert not hasattr(cell, "__dict__")
        assert hasattr(GridCell, "__slots__")

    def test_is_hashable(self) -> None:
        # given
        a = GridCell(row=0, col=0)
        b = GridCell(row=0, col=0)

        # when / then
        assert hash(a) == hash(b)
        assert {a, b} == {a}

    def test_defaults(self) -> None:
        # given / when
        cell = GridCell(row=2, col=3)

        # then
        assert cell.rowspan == 1
        assert cell.colspan == 1
        assert cell.tokens == ()
        assert cell.bbox is None
        assert cell.role == "body"

    def test_bbox_is_optional_tuple(self) -> None:
        # given
        cell = GridCell(row=0, col=0, bbox=(0, 0, 10, 20))

        # when / then
        assert cell.bbox == (0, 0, 10, 20)
        assert isinstance(cell.bbox, tuple)

    def test_role_literal(self) -> None:
        # given / when
        header = GridCell(row=0, col=0, role="header")
        body = GridCell(row=1, col=0, role="body")

        # then
        assert header.role == "header"
        assert body.role == "body"

    def test_supports_pickle_protocol(self) -> None:
        # SPEC M1: TableSample/GridCell must be pickle-safe.
        # copy.deepcopy exercises __reduce_ex__ (the pickle protocol entry
        # point) without instantiating the pickle module here.
        # given
        cell = GridCell(row=2, col=3, rowspan=2, tokens=("hello",), bbox=(1, 2, 3, 4))

        # when
        restored = copy.deepcopy(cell)

        # then
        assert restored == cell
        assert restored is not cell

    def test_reduce_ex_returns_usable_tuple(self) -> None:
        # Direct check: __reduce_ex__ must succeed at protocol 2 (the default
        # for picklers in Python 3) and yield a non-None reducer.
        # given
        cell = GridCell(row=1, col=1, tokens=("x",))

        # when
        reduced = cell.__reduce_ex__(2)

        # then
        assert reduced is not None
        assert isinstance(reduced, tuple)


class TestTableSample:
    def test_is_frozen(self) -> None:
        # given
        sample = TableSample(filename="x.png", nrows=1, ncols=1, cells=(GridCell(0, 0),))

        # when / then
        with pytest.raises((AttributeError, TypeError)):
            sample.filename = "y.png"  # type: ignore[misc]  # reason: verifying frozen contract

    def test_has_slots(self) -> None:
        # given
        sample = TableSample(filename="x.png", nrows=1, ncols=1, cells=(GridCell(0, 0),))

        # when / then
        assert not hasattr(sample, "__dict__")
        assert hasattr(TableSample, "__slots__")

    def test_is_hashable(self) -> None:
        # given
        cells = (GridCell(0, 0),)
        a = TableSample(filename="x.png", nrows=1, ncols=1, cells=cells)
        b = TableSample(filename="x.png", nrows=1, ncols=1, cells=cells)

        # when / then
        assert hash(a) == hash(b)
        assert {a, b} == {a}

    def test_defaults(self) -> None:
        # given / when
        sample = TableSample(filename="x.png", nrows=1, ncols=1, cells=(GridCell(0, 0),))

        # then
        assert sample.split is None
        assert sample.imgid is None
        assert sample.extras == {}

    def test_supports_pickle_protocol(self) -> None:
        # SPEC M1: must be pickle-safe. See note above.
        # given
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(
                GridCell(0, 0, tokens=("a",)),
                GridCell(0, 1, tokens=("b",)),
                GridCell(1, 0, tokens=("c",)),
                GridCell(1, 1, tokens=("d",)),
            ),
            split="train",
            imgid=42,
        )

        # when
        restored = copy.deepcopy(sample)

        # then
        assert restored == sample
        assert restored is not sample


class TestTableSampleImageDims:
    """SPEC §5.1 / §8: optional image_width/image_height back the STRICT
    bbox-in-image cross-check."""

    def test_image_dims_default_to_none(self) -> None:
        # given / when
        sample = TableSample(filename="x.png", nrows=1, ncols=1, cells=(GridCell(0, 0),))

        # then
        assert sample.image_width is None
        assert sample.image_height is None

    def test_image_dims_are_stored(self) -> None:
        # given / when
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=1,
            cells=(GridCell(0, 0),),
            image_width=640,
            image_height=480,
        )

        # then
        assert sample.image_width == 640
        assert sample.image_height == 480

    def test_image_dims_participate_in_equality_and_hash(self) -> None:
        # given — two samples differing only in image dimensions.
        cells = (GridCell(0, 0),)
        a = TableSample(filename="x.png", nrows=1, ncols=1, cells=cells, image_width=10)
        b = TableSample(filename="x.png", nrows=1, ncols=1, cells=cells, image_width=20)
        same_as_a = TableSample(filename="x.png", nrows=1, ncols=1, cells=cells, image_width=10)

        # then — differing dims => unequal; matching dims => equal and same hash.
        assert a != b
        assert a == same_as_a
        assert hash(a) == hash(same_as_a)

    def test_image_dims_survive_deepcopy(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=1,
            cells=(GridCell(0, 0),),
            image_width=100,
            image_height=200,
        )

        # when
        restored = copy.deepcopy(sample)

        # then
        assert restored == sample
        assert restored.image_width == 100
        assert restored.image_height == 200


class TestBBoxAlias:
    def test_bbox_is_tuple_alias(self) -> None:
        # given
        bbox: BBox = (0, 0, 10, 20)

        # when / then
        assert bbox == (0, 0, 10, 20)
        assert len(bbox) == 4
