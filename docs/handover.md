# Handover

**Last updated:** 2026-05-29 (JST)
**Updated by:** Claude (Opus 4.7, 1M context)

## Current State

Library is feature-complete against `docs/spec.md`, staying in **0.0.x**
(no public PyPI release yet). `main` is at **0.0.12** (origin is one
release behind until the next push).
Shipped:

- IR + invariants (I-01..I-07) + validation profiles + codec registry +
  streaming I/O + static loss analysis + click CLI + in-repo conformance.
- **All nine codecs**: `pubtabnet-1.0.0/2.0.0`, `otsl-1.0.0`,
  `fintabnet`, `fintabnet-otsl`, `tableformer`, `tablebank`,
  `pubtables-1m`, `doctags-tables`.
- `just ci` green (ruff + pyright strict + pytest + semgrep + docs-check).
  Zero third-party deps in core (semgrep-enforced — `loss.py` now included).

### Terminology + consistency audit (this session)

- `docs/glossary.md` added: separates tablecodec-defined terms (Group A)
  from borrowed terms (Group B, each with an **Origin** = Paper / Dataset /
  Standard / General / tablecodec) and data-property terms + confusion
  guards (Group C). The trigger was "degenerate bbox" (data geometry) being
  read as "loss" (dropped IR fields) — now sharply disambiguated.
- A doc/version audit fixed stale state: README status, intent.md M8 +
  roadmap (realigned from the abandoned v0.1.0 / minor-rollout plan to the
  executed 0.0.x reality), spec.md status (clarified spec-doc v0.1.0 vs the
  0.0.x package), and the version triple (pyproject / `__init__` / uv.lock)
  all consistent (now 0.0.12). `loss.py` added to the semgrep core list and a
  CLAUDE.md self-contradiction about it resolved.

### E2E harness (`scripts/e2e_hf_check.py`)

Streams/reads REAL datasets through the actual `codec.read()` + validates.
Occasional / local-only (`[hf]` extra), NOT in CI. **16 checks**;
`just e2e-selftest` exercises every adapter offline.

Data sources:
- Docling OTSL family (PubTabNet/FinTabNet/PubTables-1M/SynthTabNet) — all
  nine codecs (some via derived grid / round-trip; ADR 0003 caveats).
- **Native** PubTabNet via `apoidea/pubtabnet-html` (streaming) → pubtabnet
  codecs (ADR 0004).
- **Native** PubTables-1M PASCAL VOC via `bsmock/pubtables-1m` (local
  download to `input/`, grid reconstructed) → pubtables-1m codec (ADR
  0006). `just e2e-fetch-pubtables1m` fetches the ~30 MB archive.

Random sampling (seed printed, `--seed N` to reproduce). Failed rows →
JSONL under `output/e2e_findings/` (gitignored) with replayable payload;
`verdict` always `needs-review`. `output/e2e_findings/TRIAGE.md` holds the
(AI-authored, needs-confirmation) triage.

### Final verification (1000 samples/check, seed 2026, 16k rows)

`parse_errors = 1 / 16,000` — the library READS essentially all real data.
PubTables-1M (OTSL + native VOC) = 1000/1000 clean. Every other failure is
a validation finding on genuine upstream DATA quirks (recorded in
`output/e2e_findings/`). See `output/e2e_findings/TRIAGE.md`.

### Findings triaged this session (all DATA quirks unless noted)

- **OTSL SynthTabNet bug** (was 48/300): real LIBRARY BUG in `build_anchors`
  (diagonal xcel + max-bbox + col-0 reject). FIXED — ported docling's
  anchor-centric `otsl_to_html` (ADR 0005, attributed MIT), then a
  registry-stop follow-up so span scans halt at cells already claimed by a
  2D span. SynthTabNet I-04 overlaps dropped to ~0.2% (2/1000); the rest is
  genuine OTSL span ambiguity (L-shaped regions; matches the HTML path).
- **I-05 degenerate bbox**: was a DATA quirk (empty cells with zero-area
  placeholder boxes — degenerate already in the SOURCE floats, our
  float→int cast introduced zero; ~45% of SynthTabNet). RESOLVED in 0.0.12:
  I-05 now geometry-checks only **content-bearing** cells (spec §5.2, ADR
  0007). The fix is validation-layer only — codecs still read/keep the bbox
  faithfully (no read-path "lie"). Live: SynthTabNet otsl ok ~50% → 294/300;
  residual = I-04 ambiguity + genuine degenerate boxes on content cells.
- **I-04 ragged / I-03 over-span** (native PubTabNet ~1%): DATA property
  surfaced by strict exact-cover; passes LENIENT. (No change planned.)
- **doctags parse_error (1/16k)**: HARNESS bug — the e2e doctags round-trip
  adapter's `json.loads(...splitlines()[0])` broke on a cell token with a
  Unicode line separator (U+2028 etc.). FIXED — parses the whole record;
  `--self-test` gained a U+2028 guard. The DocTags codec was always correct.

## In Progress

Nothing active. Native-dataset coverage is as complete as practical:
pubtabnet + pubtables-1m have native checks; otsl's native IS docling;
fintabnet/tablebank natives are deferred (see Next Actions).

## Next Actions

1. **Refine the I-05 "empty cell" definition (needs spec/ADR — recorded,
   not yet started).** 0.0.12 scoped I-05 to `tokens != ()`, but a seed-7
   verification (8k rows) showed SynthTabNet still flags 85 cells that are
   *effectively* empty: 70 are `tokens == ['']` (single empty-string token)
   and 15 are markup-only (`<sup> </sup>`); 0 had real text. The literal
   `tokens == ()` is too narrow. Proposed IR-neutral fix:
   `"".join(tokens).strip() != ""` (clears the 70; leaves the 15 markup-only
   since the core IR can't know `<sup>` is markup). Address via a spec edit
   / superseding ADR (do NOT change behaviour silently). Detail in
   `output/e2e_findings/TRIAGE.md`.
2. **fintabnet / tablebank native: deferred** (maintainer decision, ADR
   0006). FinTabNet.c is VOC (redundant with pubtables-1m, wrong codec);
   the real fintabnet native is IBM-only (developer.ibm.com, not HF).
   TableBank is a 24 GB split zip. Both stay Docling-covered.
3. **Deferred PyPI publish** (unchanged): `private/PYPI_RELEASE_STEPS.md`.

## Known Risks / Blockers

- **CI is account-blocked**: GitHub Actions ends in ~2s / 0 steps
  (account billing/quota, NOT code). Local `just ci` is the real gate.
- **A security hook hard-blocks any edit containing the substring `eval`**
  — trips `ast.literal_eval` (used in the apoidea adapter; user approved).
  Don't obfuscate around it; surface + ask.
- **Conformance is in-repo** (ADR 0001), extract before v1.0.

## Context the Next Actor Needs

- **scripts/ is NOT in CI scope** (`just lint`/`type` = src+tests only).
  Editor pyright flags unresolved `tablecodec.*` imports in the e2e script
  — expected/ungated. The e2e script has pre-existing PLR0913s (ungated).
- **OTSL reconstruction is an attributed port** of docling-ibm-models
  (MIT); keep the header + `THIRD_PARTY_NOTICES.md` if you touch
  `_otslgrid.py::build_anchors`. intent.md §6 narrowed by ADR 0005.
- **`input/`, `output/`, `private/`** are gitignored local-only trees.
- TDD: 1 commit = 1 Conventional-Commit type; structural vs behavioural
  never mixed. `docs-check` in `just ci` — run `just docs` after any codec
  name/lossy change.

## Relevant Files and Commands

- `docs/adr/000{1..6}-*.md` — decisions (0003/0004/0006 = e2e data sources;
  0005 = OTSL port).
- `docs/glossary.md` — vocabulary (tablecodec vs borrowed terms + origins).
- `scripts/e2e_hf_check.py` — harness (docling + native adapters, VOC grid
  inference, local-tar source, FindingsRecorder, self_test).
- `src/tablecodec/codecs/_otslgrid.py` — OTSL grid (attributed port).
- `just ci` — full gate. `just e2e-selftest` — offline. `just e2e 200`
  — live sampled. `just e2e-fetch-pubtables1m` — fetch native VOC.
- `output/e2e_findings/TRIAGE.md` — finding triage (needs human confirm).
