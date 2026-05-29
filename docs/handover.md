# Handover

**Last updated:** 2026-05-29 (JST)
**Updated by:** Claude (Opus 4.8, 1M context)

## Current State

`tablecodec` is feature-complete against `docs/spec.md`, staying in **0.0.x**
(no public PyPI release yet). `main` package version is **0.0.17**; the
in-repo `tablecodec-docling` bridge is at its own **0.0.2**.

Shipped:

- IR + invariants (I-01..I-07) + validation profiles + codec registry +
  streaming I/O + static loss analysis + click CLI + in-repo conformance.
- **All nine core codecs**: `pubtabnet-1.0.0/2.0.0`, `otsl-1.0.0`,
  `fintabnet`, `fintabnet-otsl`, `tableformer`, `tablebank`, `pubtables-1m`,
  `doctags-tables`.
- **`[teds]`** TEDS metric (`tablecodec.teds`, 0.0.16, ADR 0011).
  Verified (2026-05-29) **bit-identical** to a verbatim run of IBM's PubTabNet
  `metric.py` across a 9-case corpus (full + structure_only, max abs diff 0.0)
  — see ADR 0011 §Verification. `teds_html(...)` reproduces the canonical
  PubTabNet TEDS exactly; the IR-native `teds(...)` renders via
  `_sample_to_html` first (renderer-defined, per ADR 0011 §2).
- **§8 STRICT** profile + optional `TableSample.image_width/height`
  (0.0.17, ADR 0012).
- **`tablecodec-docling`** read+write bridge codec (`packages/`, ADR 0013).
- **No declared-but-unwired extras**: `[fast]`/`[validate]` dropped (ADR 0009);
  `[teds]`/`[cli]`/`[hf]` all wire real features.

Both gates green: `just ci` (core: ruff + pyright-strict + pytest + semgrep +
docs-check; zero-dep core, semgrep-enforced) and `just docling-ci` (the
bridge). `just ci-all` runs both. Coverage: core ~91% (recent-work modules
`_invariants`/`ir`/`loss`/`validate` 100%, `teds` 99%); docling codec 100%.

The spec/intent are reconciled to the code; the §-by-§ conformance audit is
complete (see git history + the ADRs below). The remaining open contract
questions (cell ordering, tokenization, float bbox, IR JSON Schema) and all
roadmap work are consolidated in `docs/intent.md` §8.

## In Progress

Nothing active. Session closed after a test-sufficiency audit of the recent
work (TEDS / loss classification / STRICT / docling) — gaps filled, dead code
removed. Detail in git log + CHANGELOG.

## Next Actions

Nothing active. **All future/roadmap work lives in `docs/intent.md` §8**
(the single home: extraction & publish, codec image-dims population, the
docling-core e2e, and the OQ-1..4 open questions) — handover does not
duplicate it. Pick the next item from there when resuming.

## Known Risks / Blockers

- **Remote CI is account-blocked** (GitHub billing): Actions end in ~2s / 0
  steps — NOT a code problem. **Local `just ci` / `just ci-all` is the real
  gate.**
- **codex plan review is rate-limited** (was until 2026-05-31). When it
  errors with a usage-limit message, CLAUDE.md says skip the review.
- **A security hook hard-blocks any edit containing the substring `eval`** —
  trips `ast.literal_eval` (used in the apoidea e2e adapter; user approved).
  Don't obfuscate around it; surface + ask.
- **Conformance + docling bridge are in-repo** (ADR 0001 / 0013), to be
  extracted before v1.0 / publish.

## Context the Next Actor Needs

- **Monorepo layout (ADR 0013).** The docling bridge is a separate uv project
  (`[tool.uv.sources] tablecodec = {path=../../, editable}`), run with
  `uv run --project packages/tablecodec-docling`. docling-core (+ numpy/pandas)
  install into the SUB-package `.venv` only; the core env and the zero-dep
  `pip install -e .` guard stay clean. There is exactly ONE justfile (root);
  it orchestrates the bridge via `docling-*` recipes.
- **Zero-dep core is sacred.** Only `cli.py` (click) and the core-external
  `teds.py` (apted/lxml) may import third-party; both are excluded from
  `semgrep.yaml`'s core list and NOT imported by `tablecodec/__init__`.
  `import tablecodec` must work on a bare interpreter.
- **Attributed ports** (keep headers + `THIRD_PARTY_NOTICES.md`):
  `_otslgrid.py` (docling-ibm-models, MIT, ADR 0005) and `teds.py`
  (IBM PubTabNet metric, Apache-2.0, ADR 0011).
- **scripts/ is NOT in CI scope** (`just lint`/`type` = `src/`+`tests/`).
  Editor pyright flags unresolved imports there — expected/ungated.
- **`input/`, `output/`, `private/`** are gitignored local-only trees.
- **TDD discipline**: 1 commit = 1 Conventional-Commit type; structural vs
  behavioural never mixed. The `just ci` gate forbids committing a failing
  (RED) test alone, so bundle a TDD test+impl in one commit. Run `just docs`
  after any codec name/`lossy_*` change (`docs-check` enforces it).

## E2E harness (`scripts/e2e_hf_check.py`) — occasional / local-only

Streams REAL datasets through `codec.read()` + validates. NOT in CI (`[hf]`
extra). 16 checks; `just e2e-selftest` runs every adapter offline; `just e2e
N` samples live; `just e2e-fetch-pubtables1m` fetches the native VOC archive.
Data sources: docling OTSL family (all codecs; ADR 0003), native PubTabNet via
`apoidea/pubtabnet-html` (ADR 0004), native PubTables-1M VOC via
`bsmock/pubtables-1m` (ADR 0006). Failures → `output/e2e_findings/` (gitignored)
with replayable payloads; `output/e2e_findings/TRIAGE.md` holds the
AI-authored, needs-confirmation triage. Last full sweep (16k rows):
`parse_errors = 1/16,000`; all other findings are genuine upstream DATA quirks.
A docling-core-driven e2e is a deliberate non-gap (the bridge's round-trip +
30 tests are the coverage); revisit at extraction.

## Relevant Files and Commands

- `docs/spec.md` — source of truth. `docs/intent.md` — brief/roadmap.
  `docs/glossary.md` — vocabulary (tablecodec vs borrowed terms + origins).
- `docs/adr/000{1..9}.md` + `0010..0013` — decision history (0009 drop extras;
  0010 I-05 content-emptiness; 0011 TEDS port; 0012 STRICT/image-dims;
  0013 docling monorepo).
- `tests/test_spec_surface.py` — black-box conformance to the public surface;
  run after any public-API/CLI/profile change.
- `src/tablecodec/teds.py`, `packages/tablecodec-docling/` — the two
  core-external features.
- `just ci` / `just ci-all` — gates. `just docling-ci` — bridge only.
  `just e2e-selftest` — offline e2e smoke.
