# Handover

**Last updated:** 2026-05-28 (JST)
**Updated by:** Claude (Opus 4.7, 1M context)

## Current State

Library is feature-complete against `docs/spec.md` and staying in the
**0.0.x** series (no public PyPI release yet — one codec ≈ one patch
bump). `main` is at **0.0.9**. Shipped:

- IR + invariants (I-01..I-07) + validation profiles + codec registry +
  streaming I/O + static loss analysis + click-based CLI + in-repo
  conformance suite.
- **All nine codecs**: `pubtabnet-1.0.0`, `pubtabnet-2.0.0`,
  `otsl-1.0.0`, `fintabnet`, `fintabnet-otsl`, `tableformer`,
  `tablebank`, `pubtables-1m`, `doctags-tables`.
- `just ci` green (lint + pyright strict + pytest + semgrep + docs-check).
  Zero third-party deps in core (enforced by `semgrep.yaml`).

### E2E harness (this session's work)

`scripts/e2e_hf_check.py` streams REAL datasets through the actual
`codec.read()` and validates the IR. Occasional / local-only (network +
`[hf]` extra), NOT in CI.

- **Coverage**: every shipped codec has ≥1 official-corpus check (Docling
  OTSL family for all nine; some via derived grid coords / round-trip —
  see ADR 0003 caveats). Plus the **native** first-published PubTabNet
  via `apoidea/pubtabnet-html` feeding the two pubtabnet codecs (ADR
  0004). 15 checks total; `--self-test` / `just e2e-selftest` exercises
  every adapter offline.
- **Random sampling**: streaming `shuffle(seed)` reshuffles shard order;
  a fresh seed each run (printed) → repeated runs approximate full
  coverage. `--seed N` to reproduce, `--no-shuffle` for head read.
- **Findings recorder**: every failed row → JSONL under
  `output/e2e_findings/` (gitignored) with provenance + replayable
  `input_payload`; `verdict` always `needs-review`. A generated
  `README.md` documents the schema + replay recipe.

### Live findings so far (need human audit, NOT yet triaged)

- PubTabNet_OTSL / FinTabNet_OTSL (Docling): occasional I-05 on real
  degenerate bboxes — `x0>=x1`, `y0>=y1`, and **5-element bbox arrays**
  (our 4-element assumption may be wrong, OR upstream quirk). ~1/100 rows.
- Native PubTabNet (apoidea, seed 128869): pubtabnet-2.0.0 +
  pubtabnet-1.0.0 both **80/80 clean** — the native original envelope
  passes cleanly.

## In Progress

Nothing in active development. The user's "native first-published
dataset per codec" request is satisfied as far as HF streaming allows
(only PubTabNet's native original is viewer-streamable).

## Next Actions

1. **Audit the recorded e2e findings** before concluding anything: run
   `just e2e 200` a few times, then inspect `output/e2e_findings/*.jsonl`.
   Decide per finding: library bug / upstream data bug / over-strict
   invariant. The 5-element bbox case is the most interesting — confirm
   whether PubTabNet bbox can carry a 5th element and whether `_bbox4`
   truncation is correct.
2. **Deferred native-original gaps** (ADR 0004): `fintabnet`,
   `pubtables-1m` (PASCAL VOC XML), `tablebank` originals are file-based
   (tar.gz / images) and not exposed via the HF Datasets viewer. Adding
   them needs a downloader + format parser — only invest if there's a
   reason.
3. **Deferred PyPI publish**: still on hold (maintainer decision).
   Procedure in `private/PYPI_RELEASE_STEPS.md` (gitignored). Release
   workflow fires on a `v*` tag but can't authenticate until Trusted
   Publishing is configured.

## Known Risks / Blockers

- **CI is account-blocked**: GitHub Actions runs end in ~2s with 0 steps
  (account-level billing/quota/disabled-Actions issue, NOT code). Fix is
  user-side at github.com/settings/billing. **Local `just ci` is the
  real gate** and is green.
- **`apoidea/pubtabnet-html` `html` is a Python repr** (single-quoted),
  not JSON — `_parse_struct` falls back to `ast.literal_eval` (safe
  literal-only parser). A note-worthy gotcha: the repo author serialized
  with `str(dict)`, not `json.dumps`.
- **Conformance is in-repo, not vendor-neutral yet** (ADR 0001): must be
  extracted to a separate repo before v1.0.

## Context the Next Actor Needs

- **TDD strictness**: 1 commit = 1 step; structural vs behavioural never
  mixed. Conventional Commits type encodes which.
- **scripts/ is NOT in CI scope** (`just ci` runs `pyright src/ tests/`,
  `ruff check src/ tests/`). Editor pyright flags unresolved
  `tablecodec.*` imports in `scripts/e2e_hf_check.py` — expected/ungated.
- **A security hook hard-blocks any edit containing the substring
  "eval"** (PreToolUse). `ast.literal_eval` trips it; the user approved
  it for `_parse_struct`. Do NOT obfuscate around the hook.
- **`tests/codecs/` must NOT have `__init__.py`** (it would shadow stdlib
  `codecs`). Registry tests bookend with `_snapshot()` / `_restore()`.
- **`TableSample.__hash__` excludes `extras`** on purpose; `__eq__`
  includes it. Don't "fix".
- **`docs-check` is in `just ci`**: after any codec `name`/`spec_version`/
  `media_type`/`lossy_*` change, run `just docs` before committing.

## Relevant Files and Commands

- `docs/spec.md` — source of truth. `docs/intent.md` — brief.
- `docs/adr/000{1,2,3,4}-*.md` — decision history (0003/0004 = e2e data
  sources + caveats).
- `src/tablecodec/codecs/` — the nine codecs + `_htmltable.py` /
  `_otslgrid.py` shared parsers + `builtins.py` (BUILTIN_CODECS).
- `scripts/e2e_hf_check.py` — the e2e harness (adapters, CHECKS registry,
  FindingsRecorder, self_test).
- `output/e2e_findings/` — gitignored; per-run JSONL findings for audit.
- `just ci` — full local gate. `just e2e-selftest` — offline adapter
  smoke. `just e2e 200` — live sampled run (needs `[hf]`).
- `uv run --extra hf python scripts/e2e_hf_check.py --dataset apoidea --limit 80`
  — native PubTabNet run.
