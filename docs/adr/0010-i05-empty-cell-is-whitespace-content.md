# 0010. I-05 "empty cell" is decided by content, not token count

**Date:** 2026-05-29
**Status:** Accepted (refines ADR 0007)

## Context

ADR 0007 scoped the I-05 bbox geometry check to *content-bearing* cells,
defining "empty" as `tokens == ()` (the empty tuple). A follow-up e2e
verification (seed 7, ~8k rows) showed that the `tokens == ()` predicate
is too narrow: SynthTabNet still flagged 85 cells that carry a degenerate
placeholder bbox yet hold no real content —

- **70** had `tokens == ("",)` — a single empty-string token, not the
  empty tuple. Source HTML-token corpora emit a `("",)` (or `(" ",)`)
  cell where a structurally-present cell has no text.
- **15** were markup-only, e.g. `("<sup>", " ", "</sup>")` — structure
  tokens wrapping nothing but whitespace.
- **0** held actual text.

The `("",)` / `(" ",)` cells are *the same situation* ADR 0007 addressed
(an empty cell with a placeholder box) but slip past `tokens == ()`, so
they produce exactly the false positives 0007 set out to remove.

## Decision

Refine the "empty cell" predicate from `tokens == ()` to **content
emptiness**: a cell is empty when its tokens, concatenated, contain no
non-whitespace character —

```python
def _is_content_empty(tokens: tuple[str, ...]) -> bool:
    return "".join(tokens).strip() == ""
```

I-05 geometry-checks a `bbox` only on cells that are **not** content-empty.
This clears the 70 `("",)` / whitespace cases. The 15 markup-only cells
stay content-bearing (and thus geometry-checked): `"".join(("<sup>", " ",
"</sup>")).strip()` is non-empty, and the core IR does not model HTML
semantics, so it cannot know `<sup>` renders no glyph. Treating
markup-bearing tokens as content is the IR-neutral choice — a degenerate
box there is a genuine (if minor) source quirk worth surfacing.

The change stays entirely in the validation layer
(`_invariants.py::check_i05_bbox_well_formed` + spec §5.2). Codecs are
unchanged: the bbox is still read, kept on the IR, and preserved on
round-trip. The predicate remains single and profile-independent.

## Enforcement inventory

- **Entry points**: `tablecodec._invariants.check_i05_bbox_well_formed`
  is the sole producer of I-05 errors; `validate()` runs it for every
  profile whose `checks` tuple includes it (all built-ins today).
- **Carried data**: the discriminator is `GridCell.tokens`. No new field.
- **Bypass candidates**: none — one I-05 implementation; no codec
  re-implements the geometry check. The doc generators read codec
  metadata, not invariants, so they are unaffected.
- **Tests**: `("",)` / `(" ",)` + degenerate bbox → I-05 passes;
  markup-only `("<sup>", " ", "</sup>")` + degenerate bbox → I-05 still
  fails; text `("a",)` + degenerate bbox → still fails; empty cell + valid
  bbox → unchanged.

## Consequences

### Positive

- Removes the residual false positives ADR 0007 missed (the dominant one,
  70/85 in the verification sweep) with a predicate that matches intent
  ("no content to localize") rather than a structural accident
  (`tokens == ()`).
- Still flags degenerate boxes on cells that carry any non-whitespace
  token, including markup-only cells — no rigor lost for content cells.

### Negative

- A degenerate bbox on a *whitespace-only* cell is no longer flagged by
  any built-in profile (an extension of the 0007 tradeoff). Judged
  acceptable for the same reason: such a cell localizes no content.
- `"".join(tokens)` allocates per cell during validation. Negligible: it
  runs only when a bbox is present, on a handful of short tokens.

### Neutral

- The bbox remains on the IR for empty cells; this ADR changes only what
  `validate()` reports, not the data.

## Supersession

Refines ADR 0007. ADR 0007's decision (validation-layer-only scoping of
I-05 to content-bearing cells) stands; only the *definition of empty* is
tightened here. ADR 0007 is marked "Superseded by 0010".
