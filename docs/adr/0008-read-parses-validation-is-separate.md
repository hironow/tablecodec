# 0008. `read` parses; invariant validation is a separate, opt-in step

**Date:** 2026-05-29
**Status:** Accepted

## Context

Spec §6.1.2 said: "`read` MUST validate at least **I-01 through I-05** for
every yielded sample." The implementation does not do this: every codec's
`read` parses a record into a `TableSample` and **raises** (with the record
offset, §6.1.4) on records it cannot structurally parse — invalid JSON,
unknown tokens, structure/cell-count mismatches — but it does **not** run
the invariant checks. I-04 (exact cover) and I-05 (bbox geometry) can pass
`read` unflagged; they are only reported by `validate(sample, profile)`
(§8). A conformance audit (2026-05-29) flagged this as spec-vs-code drift.

Two ways to reconcile:

1. Make `read` run I-01..I-05 on every sample.
2. Keep `read` as a pure parser and amend §6.1.2 to match — validation is a
   separate, profile-driven step the caller opts into.

## Decision

Adopt option 2. `read` parses and raises only on records it cannot turn
into a `TableSample` (with the offset); it does **not** evaluate the
structural invariants. Invariants I-01..I-07 are checked exclusively by
`validate(sample, profile)` (§8). Spec §6.1 and the `Codec.read` docstring
are updated to say so.

Rationale:

- **Strictness is the caller's choice.** §8 already layers profiles
  (`lenient` … `strict`); baking I-01..I-05 into `read` would impose one
  fixed strictness on every reader and duplicate the profile machinery.
- **Validation cost is opt-in.** Streaming a multi-hundred-k-sample dataset
  should not pay per-sample invariant checks unless the caller wants them
  (§10 constant-memory streaming; the validate pass is itself a lazy
  generator the caller composes).
- **Real data legitimately violates some invariants** (the e2e sweeps
  surfaced ragged tables [I-04] and degenerate bboxes [I-05] in upstream
  data). A reader that hard-validated I-04/I-05 could not even *yield* such
  rows for inspection; separating parse from validate lets a caller read,
  then decide.
- **Honest separation of concerns.** `read` answers "is this a
  parseable record?"; `validate` answers "does this sample satisfy
  profile P?"; `analyze_loss` answers "what does a round-trip drop?" — three
  independent, composable operations.

## Consequences

### Positive

- The spec matches the (cleaner) implementation; the `read` contract is
  unambiguous: parse + offset-tagged errors, no silent validation.
- Callers retain full control over which profile (if any) to apply, and
  can stream-read data that is structurally parseable but invariant-invalid
  (common in real corpora) for triage.

### Negative

- A caller who never calls `validate` may consume samples that violate
  I-04/I-05. Mitigation: the CLI `validate`/`stats`/`convert` paths run a
  profile; library users are directed to `validate` in the README/docs.

### Neutral

- No code change — this ADR ratifies existing behaviour and updates the
  spec text + `Codec.read` docstring to remove the unmet MUST.
- Supersedes the §6.1.2 wording only; the other §6.1 requirements
  (lazy streaming, round-trip honesty, offset-tagged errors) are unchanged.
