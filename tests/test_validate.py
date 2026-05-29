"""Tests for tablecodec.validate — profile-driven invariant orchestration.

Covers SPEC §8 Validation Profiles.
"""

from __future__ import annotations

import pytest

from tablecodec import profiles, validate
from tablecodec.ir import GridCell, TableSample
from tablecodec.validate import ValidationError


def _valid_2x2() -> TableSample:
    return TableSample(
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


class TestProfilesExist:
    """SPEC §8 Validation Profiles: 5 named bundles."""

    @pytest.mark.parametrize(
        "name",
        ["LENIENT", "DEFAULT", "PUBTABNET_2_0", "TABLEFORMER", "STRICT"],
    )
    def test_profile_is_exposed(self, name: str) -> None:
        # given / when
        profile = getattr(profiles, name)

        # then
        assert profile is not None
        assert profile.name == name


class TestValidateValid:
    def test_valid_sample_passes_default(self) -> None:
        # given
        sample = _valid_2x2()

        # when
        errors = validate(sample, profile=profiles.DEFAULT)

        # then
        assert errors == []

    def test_valid_sample_passes_lenient(self) -> None:
        # given
        sample = _valid_2x2()

        # when
        errors = validate(sample, profile=profiles.LENIENT)

        # then
        assert errors == []


class TestValidateInvalid:
    def test_default_reports_gap_via_i04(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(GridCell(0, 0),),  # huge gap
        )

        # when
        errors = validate(sample, profile=profiles.DEFAULT)

        # then
        assert any(e.invariant == "I-04" for e in errors)

    def test_lenient_skips_i04(self) -> None:
        # given — gap that I-04 catches; lenient must skip it.
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(GridCell(0, 0),),
        )

        # when
        errors = validate(sample, profile=profiles.LENIENT)

        # then
        assert not any(e.invariant == "I-04" for e in errors)

    def test_lenient_still_catches_i01(self) -> None:
        # given
        sample = TableSample(filename="x.png", nrows=0, ncols=1, cells=())

        # when
        errors = validate(sample, profile=profiles.LENIENT)

        # then
        assert any(e.invariant == "I-01" for e in errors)


class TestPubTabNet20Profile:
    """SPEC §8: default + every non-empty cell has bbox."""

    def test_passes_when_non_empty_cells_have_bbox(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=1,
            cells=(GridCell(row=0, col=0, tokens=("a",), bbox=(0, 0, 1, 1)),),
        )

        # when
        errors = validate(sample, profile=profiles.PUBTABNET_2_0)

        # then
        assert errors == []

    def test_rejects_non_empty_cell_without_bbox(self) -> None:
        # given — non-empty cell missing bbox.
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=1,
            cells=(GridCell(row=0, col=0, tokens=("a",), bbox=None),),
        )

        # when
        errors = validate(sample, profile=profiles.PUBTABNET_2_0)

        # then
        assert any(e.invariant == "PUBTABNET-2.0-BBOX" for e in errors)

    def test_allows_empty_cell_without_bbox(self) -> None:
        # given — empty cell may omit bbox.
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=1,
            cells=(GridCell(row=0, col=0, tokens=(), bbox=None),),
        )

        # when
        errors = validate(sample, profile=profiles.PUBTABNET_2_0)

        # then
        assert not any(e.invariant == "PUBTABNET-2.0-BBOX" for e in errors)


class TestTableFormerProfile:
    """SPEC §8: default + every cell (even empty) has bbox."""

    def test_rejects_any_cell_without_bbox(self) -> None:
        # given
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=1,
            cells=(GridCell(row=0, col=0, tokens=(), bbox=None),),
        )

        # when
        errors = validate(sample, profile=profiles.TABLEFORMER)

        # then
        assert any(e.invariant == "TABLEFORMER-BBOX" for e in errors)

    def test_passes_when_every_cell_has_bbox(self) -> None:
        # given — exercises the branch where bbox is set.
        sample = TableSample(
            filename="x.png",
            nrows=1,
            ncols=1,
            cells=(GridCell(row=0, col=0, tokens=(), bbox=(0, 0, 1, 1)),),
        )

        # when
        errors = validate(sample, profile=profiles.TABLEFORMER)

        # then
        assert not any(e.invariant == "TABLEFORMER-BBOX" for e in errors)


def _bbox_2x2(
    *,
    image_width: int | None = None,
    image_height: int | None = None,
    last_bbox: tuple[int, int, int, int] = (10, 5, 20, 10),
) -> TableSample:
    """A 2x2 grid where every cell carries a bbox (so STRICT engages)."""
    return TableSample(
        filename="x.png",
        nrows=2,
        ncols=2,
        cells=(
            GridCell(0, 0, tokens=("A",), bbox=(0, 0, 10, 5)),
            GridCell(0, 1, tokens=("B",), bbox=(10, 0, 20, 5)),
            GridCell(1, 0, tokens=("c",), bbox=(0, 5, 10, 10)),
            GridCell(1, 1, tokens=("d",), bbox=last_bbox),
        ),
        image_width=image_width,
        image_height=image_height,
    )


class TestStrictProfile:
    """SPEC §8 / ADR 0012: strict = default + bbox-in-image cross-check.

    Semantics (option C): a bbox-free sample passes without dims; a
    bbox-bearing sample REQUIRES image dims and every bbox must lie within
    the image rectangle (upper bound inclusive)."""

    def test_bbox_free_sample_passes_without_dims(self) -> None:
        # given — no cell has a bbox, so there is nothing to bound-check.
        sample = _valid_2x2()

        # when
        errors = validate(sample, profile=profiles.STRICT)

        # then
        assert errors == []

    def test_bbox_present_without_dims_is_rejected(self) -> None:
        # given — bboxes but no image metadata to verify them against.
        sample = _bbox_2x2(image_width=None, image_height=None)

        # when
        errors = validate(sample, profile=profiles.STRICT)

        # then
        assert any(e.invariant == "STRICT-IMAGE-METADATA" for e in errors)

    def test_bbox_within_image_passes(self) -> None:
        # given — every bbox lies inside a 20x10 image.
        sample = _bbox_2x2(image_width=20, image_height=10)

        # when
        errors = validate(sample, profile=profiles.STRICT)

        # then
        assert errors == []

    def test_bbox_at_exact_boundary_passes(self) -> None:
        # given — the last bbox touches the image edge (x1 == width).
        sample = _bbox_2x2(image_width=20, image_height=10, last_bbox=(10, 5, 20, 10))

        # when
        errors = validate(sample, profile=profiles.STRICT)

        # then — upper bound is inclusive (<=).
        assert errors == []

    @pytest.mark.parametrize(
        "image_width,image_height,last_bbox",
        [
            pytest.param(15, 10, (10, 5, 20, 10), id="x1-exceeds-width"),
            pytest.param(20, 8, (10, 5, 20, 10), id="y1-exceeds-height"),
        ],
    )
    def test_bbox_outside_image_is_rejected(
        self,
        image_width: int,
        image_height: int,
        last_bbox: tuple[int, int, int, int],
    ) -> None:
        # given — a bbox spilling outside the image rectangle.
        sample = _bbox_2x2(image_width=image_width, image_height=image_height, last_bbox=last_bbox)

        # when
        errors = validate(sample, profile=profiles.STRICT)

        # then
        assert any(e.invariant == "STRICT-BBOX-OUT-OF-BOUNDS" for e in errors)

    def test_strict_still_runs_default_checks(self) -> None:
        # given — an I-04 coverage gap (cell (1,1) missing) plus valid dims.
        sample = TableSample(
            filename="x.png",
            nrows=2,
            ncols=2,
            cells=(
                GridCell(0, 0, tokens=("A",), bbox=(0, 0, 10, 5)),
                GridCell(0, 1, tokens=("B",), bbox=(10, 0, 20, 5)),
                GridCell(1, 0, tokens=("c",), bbox=(0, 5, 10, 10)),
            ),
            image_width=20,
            image_height=10,
        )

        # when
        errors = validate(sample, profile=profiles.STRICT)

        # then — STRICT includes the DEFAULT checks, so I-04 still fires.
        assert any(e.invariant == "I-04" for e in errors)


class TestValidateRaisesOnUnknownProfile:
    """SPEC §8: validators raise only on programmer error."""

    def test_unknown_profile_raises_value_error(self) -> None:
        # given
        sample = _valid_2x2()

        # when / then
        with pytest.raises((ValueError, TypeError, AttributeError)):
            validate(sample, profile="not-a-profile")  # type: ignore[arg-type]


class TestValidationErrorReExported:
    def test_validation_error_is_importable_from_validate_module(self) -> None:
        # given / when / then
        err = ValidationError(invariant="I-01", message="x")
        assert err.invariant == "I-01"
