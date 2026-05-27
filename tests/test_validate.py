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


class TestStrictProfile:
    """SPEC §8: strict cross-checks bbox against image dimensions; without
    image metadata it falls back to default behavior."""

    def test_strict_without_image_metadata_falls_back_to_default(self) -> None:
        # given
        sample = _valid_2x2()

        # when
        errors = validate(sample, profile=profiles.STRICT)

        # then
        assert errors == []


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
