# 0007. I-05 geometry check is scoped to content-bearing cells

**Date:** 2026-05-29
**Status:** Superseded by [0010](0010-i05-empty-cell-is-whitespace-content.md)

## Context

I-05 required every set `bbox` to satisfy `x0 < x1` and `y0 < y1`
(positive area). A 1000-sample-per-check e2e sweep (16k rows) found that
the dominant validation finding was **empty cells carrying a zero-area
"point" bbox** (`x0 == x1` and `y0 == y1`): ~450/1000 SynthTabNet rows,
plus a long tail in FinTabNet / PubTabNet. Verified against the source
data: the degeneracy is present in the upstream float coordinates (our
`float → int` cast introduced none), and the offending cells are empty
(`tokens == ()`). Datasets assign these placeholder boxes to empty cells
that have no content to localize.

We considered fixing this in the **codec read path** (drop empty-cell
degenerate bboxes to `None`). Rejected: that makes a codec silently
discard a source field, which (a) cannot be declared honestly in
`lossy_read` (a static field set — the drop is conditional), and (b)
would have to be replicated across codecs, risking divergence. Codecs
must read faithfully; this is a *validation* question, not a *read* one.

## Decision

Scope **I-05** to **content-bearing cells**: when `bbox` is set on a cell
with non-empty `tokens`, enforce `x0 < x1` and `y0 < y1`; when the cell is
empty (`tokens == ()`), its bbox is treated as a placeholder region and is
**not** geometry-checked. The change lives entirely in the validation
layer (`_invariants.py::check_i05_bbox_well_formed` + spec §5.2). Codecs
are unchanged: the bbox is still read, kept on the IR, and preserved on
round-trip.

This is a single, profile-independent definition (every profile that
includes I-05 inherits the new scope). Profiles that check bbox
*presence* (`tableformer`, `pubtabnet-2.0`) are unaffected — a placeholder
box is still present.

## Enforcement inventory

- **Entry points**: `tablecodec._invariants.check_i05_bbox_well_formed`
  is the sole producer of I-05 errors; `validate()` runs it for every
  profile whose `checks` tuple includes it (LENIENT, DEFAULT,
  PUBTABNET_2_0, TABLEFORMER, STRICT — all of them today).
- **Carried data**: the discriminator is `GridCell.tokens` (empty tuple =
  empty cell). No new field needed.
- **Bypass candidates**: none — there is exactly one I-05 implementation;
  no codec re-implements the geometry check.
- **Tests**: empty cell + degenerate bbox → I-05 passes; non-empty cell +
  degenerate bbox → I-05 still fails; empty cell + valid bbox → unchanged.

## Consequences

### Positive

- Removes a large class of false-positive findings (benign placeholder
  boxes on empty cells) while still flagging degenerate bboxes on cells
  that actually localize content.
- Codecs stay honest: no read-path change, no silent field drop,
  `lossy_read`/`lossy_write`/`analyze_loss`/round-trip untouched.

### Negative

- A genuinely malformed bbox on an *empty* cell (e.g. inverted) is no
  longer flagged by any built-in profile. Judged acceptable: an empty
  cell localizes no content, so its bbox geometry carries little value.
  A caller needing maximum rigor can compose a custom profile.

### Neutral

- The bbox remains on the IR for empty cells; downstream code can still
  inspect it. This ADR changes only what `validate()` reports, not the data.
