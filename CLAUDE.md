# CLAUDE.md — tablecodec

Project-specific guidance for AI assistants and contributors. This file
**adds to** the global development guidelines (TDD, Tidy First,
Conventional Commits, `uv`/`just`/`ruff`/`pyright`/`semgrep`, `.yaml`
extension, ASCII-only diagrams). It does not repeat them — read those
first, then the rules here win on any project-specific point.

Authoritative documents, in precedence order:

1. `docs/spec.md` — the specification. Behaviour, contracts, invariants.
2. `docs/intent.md` — implementation brief: milestones, tech choices,
   quality bar.
3. global guidelines — coding standards, commit discipline.

If code and `docs/spec.md` disagree, the spec wins; propose a spec PR
before changing behaviour.

## What this project is

A Python library giving a neutral, lossless **Internal Representation
(IR)** for image-based table-recognition datasets, plus a registry of
**codecs** that translate between the IR and public dataset formats
(PubTabNet, FinTabNet, OTSL, TableFormer, ...). The headline constraint:
**the core has zero third-party runtime dependencies.**

## Non-negotiable invariants

- **Zero-dependency core.** `src/tablecodec/{ir,_invariants,validate,io,
  loss}.py` and `src/tablecodec/codecs/{_base,__init__,_htmltable,
  pubtabnet,otsl,fintabnet,tableformer,...}.py` import **stdlib only**.
  This is enforced by the semgrep rule
  `.semgrep/rules/core-deps/tablecodec-no-third-party-imports-in-core.yaml`.
  When you add a core module, add it to that rule's `paths.include` list.
- **Optional features are extras.** Two modules are permitted third-party
  imports and are excluded from the semgrep core list: `cli.py` (click,
  `[cli]` extra) and `teds.py` (apted/lxml, `[teds]` extra — the TEDS metric,
  ADR 0011). Neither is imported by `tablecodec/__init__`, so
  `import tablecodec` must work on a bare interpreter (the `pip install -e .`
  CI job guards this). (`loss.py` is stdlib-only — static, data-free analysis
  over codec `lossy_*` declarations — so it stays IN the core list and is
  enforced.) The `tablecodec-docling` bridge (apted/lxml + docling-core) is a
  **separate package** under `packages/`, not part of this core package at all
  (ADR 0013).
- **Streaming, not slurping.** `read` yields lazily; never `f.read()` /
  `f.readlines()` a whole dataset. The semgrep rule
  `.semgrep/rules/streaming/tablecodec-no-full-file-read.yaml` enforces this
  in `io.py` and `codecs/`. SPEC §10 requires constant memory.
- **IR is immutable.** `BBox`, `GridCell`, `TableSample` are
  `@dataclass(frozen=True, slots=True)`, hashable, and safe to send
  across process boundaries.

## Quality gate

`just ci` = `lint type test semgrep semgrep-test docs-check`. Everything must
be green before commit. Specifically:

- `just lint` — ruff check + ruff format --check (config in `pyproject.toml`).
- `just type` — pyright **strict** (`pyrightconfig.json`). Zero errors.
- `just test` — pytest. Benchmarks are marked `benchmark` and excluded
  by default; run with `just bench`.
- `just semgrep` — scan `src/` with the core meta-rules (`.semgrep/rules/`).
- `just semgrep-test` — `semgrep test .semgrep/rules/`: verify each rule
  against its co-located fixture (rule correctness, never against real code).
- `just docs-check` — regenerates `docs/format_support.md` and
  `docs/loss_matrix.md` and fails if they differ from what's committed.

Run `just fmt` to auto-fix, `just docs` to regenerate the tables.

`just ci` covers the **core package only** (and runs `test`/`type` with
`--extra teds` so the optional TEDS tests run rather than skip). The in-repo
`tablecodec-docling` bridge (`packages/`, ADR 0013) has its own gate
`just docling-ci`; `just ci-all` runs both. Touching `packages/` → run
`just docling-ci` (or `just ci-all`).

## Adding a codec (the common task)

Most new work is "add codec X". The established recipe:

1. If X is an HTML-token format (PubTabNet-like), reuse
   `codecs/_htmltable.py`:
   `parse_html_table(payload, *, id_field=, drop_bbox=)`,
   `serialize_html_table(sample, *, id_field=, include_bbox=)`,
   `sniff_html_table(source, *, require_no_bbox=, require_all_bbox=,
   require_field=)`. Do **not** copy the parser — extend the knobs.
2. If X is a different token language (like OTSL), write a fresh parser,
   but derive the algorithm from the source paper/spec — **never copy
   upstream reference code verbatim** (intent.md §6; e.g. IBM's
   `otsl.py` is off-limits as a copy source).
3. Codec class is `@dataclass(frozen=True, slots=True)` implementing the
   `Codec` Protocol (`codecs/_base.py`): `name`, `spec_version`,
   `media_type` (declared as `@property` in the Protocol so frozen
   dataclass attrs satisfy it), `read`, `write`, `lossy_read`,
   `lossy_write`, and a `sniff` delegate for `codecs.detect`.
4. `lossy_read` / `lossy_write` MUST be honest — a round-trip test and
   the `analyze_loss` matrix depend on them. Auxiliary fields whose loss
   is "structure-preserving" are exactly `{bbox, role, extras}`; losing
   anything else is "lossy".
5. TDD: write `tests/codecs/test_X.py` first (identity, read variants,
   round-trip, lossy declarations, sniff discrimination), then implement.
   Add minimal **synthetic** fixtures under `tests/fixtures/X/` — no
   borrowed upstream data.
6. Register the codec in both doc generators
   (`scripts/gen_format_support.py`, `scripts/gen_loss_matrix.py`) and
   run `just docs`.
7. Add the new core module path to the `paths.include` list of
   `.semgrep/rules/core-deps/tablecodec-no-third-party-imports-in-core.yaml`.
8. Patch-bump the version within **0.0.x** (one codec ≈ one patch bump:
   `pyproject.toml` + `src/tablecodec/__init__.py`), add a CHANGELOG
   `[0.0.N]` section, update the compare/tag links.

## Gotchas (learned the hard way)

- **Registry isolation in tests.** Any test that registers codecs must
  bookend with `codecs._snapshot()` / `codecs._restore(saved)` (see the
  fixture in `tests/codecs/test_registry.py`). Otherwise it leaks into
  sibling tests.
- **`tests/codecs/` has no `__init__.py`.** Adding one makes pytest
  import it as a package named `codecs`, shadowing the stdlib `codecs`
  module and breaking collection. Keep it absent.
- **`TableSample.__hash__` excludes `extras`** on purpose (`Mapping` is
  not hashable). `__eq__` still considers it. Don't "fix" this.
- **Round-trip safety is tested via `copy.deepcopy`**, not by importing
  the stdlib `pickle` module into the test tree (keeps the supply-chain
  surface clean). `deepcopy` exercises the same `__reduce_ex__` protocol
  the IR must support.
- **pyright strict is picky.** Common fixes: type `field(default_factory=
  ...)` with a named helper (not a bare `dict`/`list`); narrow
  `json.loads` results with `cast("dict[str, Any]", x)`; give inline
  test payloads an explicit `dict[str, Any]` annotation.
- **Lint complexity caps.** ruff enforces mccabe (C901) and
  PLR0911/PLR0913. When a function trips them, extract a helper rather
  than suppressing.
- **CI installs `[dev,cli]`.** pyright must resolve click to type-check
  `cli.py`; the matrix install includes the cli extra. The separate
  `pip install -e .` job verifies the core still installs with no extras.

## Conformance suite

`conformance/` holds an in-repo copy of the SPEC §11 corpus (manifest +
JSON Schema + samples + hand-authored expected-IR). This is a
**temporary** deviation from SPEC §11 (which mandates a separate
vendor-neutral repo) recorded in
`docs/adr/0001-conformance-suite-in-repo-temporarily.md`; it must be
extracted before v1.0. Expected-IR files are authored independently of
the codecs so the suite catches read-path regressions.

## Versioning & release

- Staying in **0.0.x** for now (no public PyPI release yet). Each codec
  is a patch bump.
- The release workflow lives at `.github/workflows/release.yaml` and
  fires on a `v*` tag, publishing via PyPI Trusted Publishing (OIDC).
  It is inert until the PyPI-side setup is done — the runbook is in the
  gitignored `private/PYPI_RELEASE_STEPS.md`.

## Where things live

- `docs/spec.md` — spec (source of truth; current contract only).
  `docs/intent.md` — brief **and the single home for all future/roadmap work
  (§8 "Future work")**; spec §17 and handover point here, not the reverse.
- `docs/handover.md` — current session state (read for "where are we"); it
  references intent §8 for the roadmap rather than duplicating it.
  `docs/adr/` — decision history.
- `src/tablecodec/` — the library (see "Non-negotiable invariants").
  `teds.py` is the core-external TEDS metric (`[teds]`, ADR 0011).
- `packages/tablecodec-docling/` — the docling bridge codec, an in-repo
  monorepo member with its own `pyproject`/`src`/`tests` and its own version
  (temporary; extract before publish, ADR 0013). Run it via
  `just docling-ci`.
- `tests/` — `test_*.py` at root, codec tests in `tests/codecs/`,
  fixtures in `tests/fixtures/<codec>/`, hypothesis strategies in
  `tests/strategies.py`, benchmarks in `tests/benchmarks/`.
- `scripts/gen_*.py` — doc generators wired into `just docs`.
