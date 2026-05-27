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
# SPEC §8: STRICT cross-checks bbox against image dimensions; without that
# metadata (arriving with io.py in a later milestone) it degrades to DEFAULT.
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
    STRICT=Profile(name="STRICT", checks=_DEFAULT_CHECKS),
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
