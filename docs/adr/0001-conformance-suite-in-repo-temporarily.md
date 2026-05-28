# 0001. Conformance Suite hosted in-repo temporarily

**Date:** 2026-05-28
**Status:** Accepted

## Context

SPEC §11 and §16 specify that the Conformance Suite lives in a separate,
vendor-neutral repository (`tablecodec/conformance`) so that any
implementation in any language can certify against it without depending
on the Python package, and so the test corpus is owned by no single
implementation. This is the WPT / JSON-Schema-Test-Suite pattern
(SPEC §18 prior-art).

For M7, the implementation brief (`docs/intent.md`) lists creating that
separate repository as a deliverable. However, standing up a second
public repository is an out-of-band action that requires a hosting
decision (personal account vs. a future `tablecodec` org) and adds
cross-repo CI plumbing (git submodule or HF dataset fetch) before any
fixture can be exercised.

The requester chose to bootstrap the suite **inside this repository**
first (option "b" during M7 planning), deferring the extraction to a
separate repo until before the v1.0 freeze.

## Decision

Host the conformance corpus and its harness inside this repository under
a top-level `conformance/` directory whose layout mirrors the
separate-repo layout described in SPEC §11:

```
conformance/
├── schema/index.schema.json   # JSON Schema (draft 2020-12) for INDEX.json
├── INDEX.json                 # machine-readable manifest of test cases
├── samples/<codec>/*.jsonl    # input records
└── expectations/<codec>/*.ir.json  # hand-authored expected IR
```

`tests/test_conformance.py` reads `INDEX.json`, validates it against the
schema, and for each case reads the sample with the declared codec and
compares the resulting IR against the hand-authored expectation. The
expectations are authored independently of the codec implementation so
the suite catches read-path regressions rather than merely re-asserting
the codec's own output.

This is an explicit, temporary deviation from SPEC §11, taken under
`docs/intent.md` §9 ("一時的に緩める必要" — documented with reviewer
acknowledgement). It does NOT amend the SPEC: the canonical decision
remains a separate vendor-neutral repository.

## Consequences

### Positive

- M7 can be delivered and CI-gated immediately, with no second repo and
  no cross-repo fetch plumbing.
- The in-repo layout is byte-for-byte the SPEC §11 layout, so extraction
  later is a `git filter-repo` / move, not a redesign.
- Hand-authored expectations make the suite a genuine regression net for
  the read path of every codec.

### Negative

- While in-repo, the corpus is NOT vendor-neutral: it appears to belong
  to the Python implementation. Third-party implementations cannot yet
  certify against a neutral artifact. This is the exact property SPEC
  §11/§16 want, and it is unmet until extraction.
- The `conformance/` directory is not one of the standard root
  directories enumerated in `docs/intent.md` project-structure rules;
  it is an intentional addition tracked by this ADR.

### Neutral

- Adds `jsonschema` to the `[dev]` extra (test-only) so INDEX.json is
  validated against a real JSON Schema. The stdlib-only core is
  unaffected.
- Before v1.0 (per the roadmap in `docs/intent.md` §8), a superseding
  ADR will record the extraction to `tablecodec/conformance` and flip
  this ADR's status to "Superseded".
