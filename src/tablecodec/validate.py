"""Validation entry-point and named profiles.

SPEC §8: a user explicitly opts into the strictness they need. Five
profiles ship: ``LENIENT``, ``DEFAULT``, ``PUBTABNET_2_0``, ``TABLEFORMER``,
``STRICT``. Custom profiles can be constructed by composing the
``check_iXX`` functions in :mod:`tablecodec._invariants`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace

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
from tablecodec.ir import TableSample

__all__ = ["Profile", "ValidationError", "profiles", "validate"]

Check = Callable[[TableSample], list[ValidationError]]


@dataclass(frozen=True, slots=True)
class Profile:
    """A named bundle of invariant checks.

    Attributes:
        name: Human-visible profile identifier.
        checks: Ordered tuple of check functions. Order determines the
            order of errors in the returned list (lower-numbered
            invariants first, by convention).
    """

    name: str
    checks: tuple[Check, ...] = field(default_factory=tuple)


# ---------- profile-specific extra checks ----------


def _check_pubtabnet_20_bbox(sample: TableSample) -> list[ValidationError]:
    """SPEC §8 pubtabnet-2.0 profile: non-empty cells must have bbox."""
    errors: list[ValidationError] = []
    for idx, cell in enumerate(sample.cells):
        if cell.tokens and cell.bbox is None:
            errors.append(
                ValidationError(
                    invariant="PUBTABNET-2.0-BBOX",
                    message=f"non-empty cell index {idx} is missing bbox",
                    cell_index=idx,
                )
            )
    return errors


def _check_tableformer_bbox(sample: TableSample) -> list[ValidationError]:
    """SPEC §8 tableformer profile: every cell (even empty) must have bbox."""
    errors: list[ValidationError] = []
    for idx, cell in enumerate(sample.cells):
        if cell.bbox is None:
            errors.append(
                ValidationError(
                    invariant="TABLEFORMER-BBOX",
                    message=f"cell index {idx} is missing bbox",
                    cell_index=idx,
                )
            )
    return errors


def _check_strict_bbox_in_image(sample: TableSample) -> list[ValidationError]:
    """SPEC §8 strict profile / ADR 0012: cross-check bbox vs image dimensions.

    Semantics (option C): a bbox-free sample needs no image metadata. If any
    cell carries a bbox, the sample MUST declare ``image_width`` and
    ``image_height`` (else the coordinates cannot be bound-checked), and every
    bbox must lie within the image rectangle ``0 <= x0 < x1 <= width`` and
    ``0 <= y0 < y1 <= height`` (upper bound inclusive — a bbox may touch the
    image edge).
    """
    cells_with_bbox = [(idx, c.bbox) for idx, c in enumerate(sample.cells) if c.bbox is not None]
    if not cells_with_bbox:
        return []

    width, height = sample.image_width, sample.image_height
    if width is None or height is None:
        return [
            ValidationError(
                invariant="STRICT-IMAGE-METADATA",
                message=(
                    "sample carries cell bboxes but no image_width/image_height "
                    "to cross-check them against"
                ),
                cell_index=None,
            )
        ]

    errors: list[ValidationError] = []
    for idx, bbox in cells_with_bbox:
        x0, y0, x1, y1 = bbox
        if not (0 <= x0 and x1 <= width):
            errors.append(
                ValidationError(
                    invariant="STRICT-BBOX-OUT-OF-BOUNDS",
                    message=(f"bbox x-range [{x0}, {x1}] outside [0, {width}] at cell index {idx}"),
                    cell_index=idx,
                )
            )
        if not (0 <= y0 and y1 <= height):
            errors.append(
                ValidationError(
                    invariant="STRICT-BBOX-OUT-OF-BOUNDS",
                    message=(
                        f"bbox y-range [{y0}, {y1}] outside [0, {height}] at cell index {idx}"
                    ),
                    cell_index=idx,
                )
            )
    return errors


# ---------- profile registry ----------

_DEFAULT_CHECKS: tuple[Check, ...] = (
    check_i01_nrows_ncols_positive,
    check_i02_cell_in_bounds,
    check_i03_span_in_bounds,
    check_i04_grid_exact_cover,
    check_i05_bbox_well_formed,
    check_i06_header_contiguous_top,
    check_i07_tokens_is_tuple,
)

# SPEC §8: LENIENT enforces I-01, I-02, I-03, I-05 only.
_LENIENT_CHECKS: tuple[Check, ...] = (
    check_i01_nrows_ncols_positive,
    check_i02_cell_in_bounds,
    check_i03_span_in_bounds,
    check_i05_bbox_well_formed,
)


# SimpleNamespace exposes the five built-in profiles as ``profiles.NAME``
# without pyright flagging uppercase attributes as ``reportConstantRedefinition``.
# SPEC §8 / ADR 0012: STRICT = DEFAULT + a bbox-in-image cross-check that
# requires image metadata whenever a sample carries bboxes.
profiles = SimpleNamespace(
    LENIENT=Profile(name="LENIENT", checks=_LENIENT_CHECKS),
    DEFAULT=Profile(name="DEFAULT", checks=_DEFAULT_CHECKS),
    PUBTABNET_2_0=Profile(
        name="PUBTABNET_2_0",
        checks=(*_DEFAULT_CHECKS, _check_pubtabnet_20_bbox),
    ),
    TABLEFORMER=Profile(
        name="TABLEFORMER",
        checks=(*_DEFAULT_CHECKS, _check_tableformer_bbox),
    ),
    STRICT=Profile(name="STRICT", checks=(*_DEFAULT_CHECKS, _check_strict_bbox_in_image)),
)


def validate(sample: TableSample, profile: Profile) -> list[ValidationError]:
    """Run the checks bundled in *profile* against *sample*.

    Returns a flat list of :class:`ValidationError`. Empty list = valid.
    Never raises on data; raises ``TypeError`` if *profile* is not a
    :class:`Profile` instance (SPEC §8 "raise only on programmer error").
    """
    if not isinstance(profile, Profile):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = f"profile must be a Profile instance, got {type(profile).__name__}"
        raise TypeError(msg)

    errors: list[ValidationError] = []
    for check in profile.checks:
        errors.extend(check(sample))
    return errors
