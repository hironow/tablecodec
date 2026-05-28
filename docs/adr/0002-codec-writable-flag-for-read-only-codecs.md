# 0002. Add a `writable` flag to the Codec contract

**Date:** 2026-05-28
**Status:** Accepted

## Context

SPEC §7 lists formats that are read-only (`write` = ✗), starting with
PubTables-1M (Microsoft, object-detection). The `Codec` Protocol
(SPEC §6) as originally written assumes every codec can both `read` and
`write`, and `analyze_loss` (SPEC §9) computes a target's
unrepresentable fields from `target.lossy_write()`.

A read-only codec has no meaningful `write` and no meaningful
`lossy_write`. Without a way to express "this codec cannot be a write
target", `analyze_loss(source, "pubtables-1m")` would silently consult a
`lossy_write()` that does not describe reality, and the loss matrix would
mislabel an impossible conversion as merely lossy/structure-preserving.

## Decision

Extend the `Codec` Protocol with a boolean capability flag:

```python
@property
def writable(self) -> bool:
    """False for read-only codecs; their write() raises NotImplementedError."""
```

- Concrete codecs are frozen dataclasses; they satisfy the property with
  a field `writable: bool = True`. Read-only codecs set
  `writable: bool = False` and raise `NotImplementedError` from `write`.
- `analyze_loss(source, target)` short-circuits when
  `target.writable is False`, returning a new
  `round_trip_classification` value **`"unwritable"`** and an empty
  `ir_fields_unrepresentable_in_target`. `source_fields_dropped_on_read`
  is still meaningful and is reported.
- The loss matrix renders `"unwritable"` as a distinct glyph
  (⚫ unwritable).

This is an additive extension of the SPEC §6 contract. It does not
change behaviour for existing (writable) codecs: the field defaults to
`True`, every shipped codec keeps `writable=True`, and all prior
`analyze_loss` results are unchanged.

## Consequences

### Positive

- Read-only formats (PubTables-1M, and the partial-write `doctags-tables`
  if later modelled as read-only) become first-class citizens.
- `analyze_loss` honestly reports that a conversion target cannot be
  written, instead of inventing a loss classification.

### Negative

- Every concrete codec must now declare `writable` (defaulted to `True`,
  so the edit is mechanical). Third-party codecs written against the old
  Protocol still satisfy `runtime_checkable` structural checks only if
  they expose `writable`; a codec missing it will fail an explicit
  `isinstance(x, Codec)` check. Acceptable for a pre-1.0 contract.

### Neutral

- `lossy_write()` on a read-only codec is never consulted by
  `analyze_loss` (the `writable` short-circuit happens first), so its
  return value is unconstrained; by convention it returns
  `frozenset()`.
- A future SPEC update should fold `writable` into the §6 Codec
  definition proper; until then this ADR is the authority.
