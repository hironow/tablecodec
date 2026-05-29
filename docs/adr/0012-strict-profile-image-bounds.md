# 0012. STRICT profile cross-checks bbox against image dimensions

**Date:** 2026-05-29
**Status:** Accepted

## Context

SPEC §8 lists five validation profiles; `strict` was specified as "`default`
plus: cross-check bbox against image dimensions (requires image metadata)".
The shipped `profiles.STRICT` was byte-identical to `DEFAULT` because the IR
carried no image dimensions to check against — a known gap, recorded in the
handover as v1.0-planning work.

Three things had to be resolved:

1. **Where do image dimensions live?** The IR (`TableSample`) had no width /
   height. Validation must not read from `extras` (which §5.2 declares opaque).
2. **What does STRICT do when a sample has no image metadata?** Most token
   formats (PubTabNet, OTSL, TableBank) never carry image size.
3. **Is this entangled with OQ-3 (float bbox)?** The handover flagged it as
   such.

## Decision

### Image dimensions become first-class, optional IR fields

`TableSample` gains `image_width: int | None = None` and
`image_height: int | None = None` (flat ints, joined to `__hash__`). They are
sample-level metadata — peers of `filename` / `imgid`, describing the source
image, not the grid. A nested `image: ImageMeta` type (dpi, channels, ...) was
considered and rejected as speculative; if image metadata grows later, that is
an additive migration.

### OQ-3 is orthogonal; STRICT ships with int dims

STRICT's check is bbox **containment** in the image rectangle, which is
precision-independent. It works identically for int or float coordinates, so
STRICT ships now with int `image_width`/`image_height` and does NOT wait on
OQ-3. The only edge — a float coordinate at the exact image boundary rounding
outward — is absorbed by making the upper bound inclusive (`<=`).

### STRICT semantics (option C): "bbox present ⇒ image metadata required"

`strict` = `default` + `_check_strict_bbox_in_image`:

- no cell has a bbox → pass (no metadata needed; e.g. `pubtabnet-1.0.0`).
- any cell has a bbox but the sample lacks `image_width`/`image_height` →
  `STRICT-IMAGE-METADATA` error (coordinates that cannot be bound-checked are
  rejected, not silently accepted).
- dims present → every bbox must satisfy `0 <= x0 < x1 <= image_width` and
  `0 <= y0 < y1 <= image_height` (upper bound inclusive); a bbox outside →
  `STRICT-BBOX-OUT-OF-BOUNDS` error.

Two rejected alternatives: (B) skip the cross-check when dims are absent —
makes STRICT silently equal DEFAULT, hiding unverifiable bboxes; (A) require
dims unconditionally — fails even bbox-free samples, making STRICT unusable for
token formats. Option C is the honest middle: "if you give me coordinates,
give me the canvas to check them against."

### Scope: IR field + check only (codecs unchanged)

No codec is changed in this unit. Every codec keeps leaving image dims `None`.
Consequence (accepted for 0.x): any bbox-bearing sample read through a codec
(`pubtabnet-2.0`, `tableformer`, `pubtables1m`, `fintabnet`) fails STRICT until
a codec populates dims. STRICT is opt-in, so this is correct and honest, not a
regression. Populating dims (e.g. `pubtables1m` from PASCAL VOC `<size>`) is a
separate future patch.

### Loss model is unchanged and stays honest

Because no codec reads or writes image dims, `None` round-trips losslessly and
no `lossy_write` declaration names them — listing them would be a *false* loss
claim. This is made explicit (not accidental) in `loss.py`'s scope docstring:
the loss model covers table-content fields a codec actually carries; sample
metadata (`filename`/`nrows`/`ncols`/`split`/`imgid`/`image_*`) is out of
scope. `loss_matrix.md` is unaffected.

## Enforcement inventory

### Entry points
- `tablecodec.validate.validate(sample, profile=profiles.STRICT)` — the sole
  path that runs `_check_strict_bbox_in_image`. STRICT's `checks` tuple is
  `(*_DEFAULT_CHECKS, _check_strict_bbox_in_image)`.

### Persistent / carried data needed at each enforcement point
- `TableSample.image_width`, `TableSample.image_height` (the rectangle).
- `GridCell.bbox` on each cell (the coordinates to bound-check).

### Bypass candidates ("where can this go wrong?")
- A sample with bboxes but no dims silently passing → **closed**: that is the
  `STRICT-IMAGE-METADATA` fail-closed branch.
- A codec re-implementing the check inconsistently → **none**: there is exactly
  one implementation; codecs do not validate.
- Loss matrix drifting because dims look like a dropped field → **closed**:
  dims are out of the loss model (documented), and no codec declares them.
- `image_width`/`image_height` accidentally excluded from equality/hash so two
  differently-sized samples compare equal → **closed**: both join `__hash__`
  and the dataclass `__eq__`; `tests/test_ir.py` asserts it.

### Tests proving coverage (one per enforcement point / bypass)
- `test_bbox_free_sample_passes_without_dims` (no-bbox → pass).
- `test_bbox_present_without_dims_is_rejected` (`STRICT-IMAGE-METADATA`).
- `test_bbox_within_image_passes`, `test_bbox_at_exact_boundary_passes`
  (inclusive upper bound).
- `test_bbox_outside_image_is_rejected` (x and y overflow → `STRICT-BBOX-OUT-OF-BOUNDS`).
- `test_strict_still_runs_default_checks` (DEFAULT checks still fire under STRICT).
- `tests/test_ir.py::TestTableSampleImageDims` (dims in eq/hash/deepcopy).

## Consequences

### Positive
- `profiles.STRICT` now does what SPEC §8 promises, instead of aliasing DEFAULT.
- The IR can carry image dimensions, unblocking future codec population and any
  geometric validation.
- The loss model's scope is now explicit, closing a latent ambiguity.

### Negative
- Until a codec populates dims, STRICT rejects every bbox-bearing codec-read
  sample. Acceptable for opt-in 0.x; surfaced here and in the handover.

### Neutral
- OQ-3 remains open; STRICT does not force its resolution.
- `image_width`/`image_height` are flat ints; a richer `ImageMeta` would be a
  later additive change.
