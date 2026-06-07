# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.18] - 2026-06-07

### Added

- Conformance corpus (`conformance/`, SPEC §11) now covers **all nine codecs**
  (was 2): added an independently-authored sample + expected-IR per codec for
  `pubtabnet-1.0.0`, `fintabnet`, `fintabnet-otsl`, `tableformer`, `tablebank`,
  `pubtables-1m`, `doctags-tables`. `tests/test_conformance.py` registers the
  full builtin set and runs every case, so read-path regressions are caught
  for every codec.

- `packages/tablecodec-docling/` — a bridge codec (`docling-tables`, own
  version 0.0.2) mapping between `DoclingDocument.tables` and `TableSample`,
  developed in-repo as a temporary monorepo member (ADR 0013, SPEC §15). It
  depends on docling-core and lives in its own uv project, so the stdlib-only
  core package and its environment are unaffected. Discover it via
  `tablecodec.codecs.load_plugins()`. Run its checks with `just docling-ci`
  (or `just ci-all` for the whole monorepo).
  - **read** (0.0.1): JSONL of `DoclingDocument`s -> one `TableSample` per
    table; populates `image_width`/`image_height` from page size so
    docling-read samples can be validated under the STRICT profile.
  - **write** (0.0.2): each `TableSample` -> one `DoclingDocument` (the inverse
    of read), so `read(write([s]))` round-trips modulo
    `lossy_write = {"tokens", "extras"}` (docling stores one string per cell;
    no home for IR extras). `writable = True`, so docling-tables is now a real
    `analyze_loss` conversion target.

### Security

- Hardened the release pipeline ahead of the first PyPI publish (ADR 0014):
  - All GitHub Actions are pinned to full commit SHAs (was mutable tags;
    `pypa/gh-action-pypi-publish` now at the v1.14.0 SHA), with Dependabot
    tracking bumps behind a 7-day cooldown (`.github/dependabot.yml`).
  - The release workflow records a **SLSA build provenance** attestation
    (`actions/attest-build-provenance`) and notes that PyPI **PEP 740**
    publish attestations are emitted automatically by Trusted Publishing.
    `skip-existing` makes a partial-failure re-run idempotent.
  - CI (and the release build) route installs through Takumi Guard, a
    screening proxy that blocks known-malicious packages; `[tool.uv]
    exclude-newer` is pinned to an absolute date and `uv sync --locked`
    guards against lockfile drift.
  - PEP 639 SPDX license metadata (`license = "MIT"` + `license-files`;
    core-metadata 2.4 via hatchling >= 1.29).

## [0.0.17] - 2026-05-29

### Added

- `TableSample.image_width` / `image_height` (`int | None`, default `None`):
  optional sample-level source-image dimensions, peers of `filename`/`imgid`.
  They join `__hash__`/`__eq__`. No codec carries them yet, so `None`
  round-trips losslessly and no loss declaration changes (loss_matrix
  unaffected). See `docs/adr/0012-strict-profile-image-bounds.md`.

### Changed

- `profiles.STRICT` now implements SPEC §8's bbox-in-image cross-check instead
  of aliasing `DEFAULT`. STRICT = DEFAULT plus: a bbox-free sample needs no
  image metadata; once any cell carries a bbox the sample MUST declare
  `image_width`/`image_height` (`STRICT-IMAGE-METADATA`) and every bbox must
  lie within the image rectangle `0 <= x0 < x1 <= width`,
  `0 <= y0 < y1 <= height`, upper bound inclusive (`STRICT-BBOX-OUT-OF-BOUNDS`)
  (ADR 0012, option C). The check is a containment test independent of bbox
  precision, so it ships with int image dims and does not depend on OQ-3.
  Scope is IR field + check only: no codec populates dims yet, so a
  bbox-bearing codec-read sample fails STRICT until a codec carries dims
  (accepted for opt-in 0.x; codec population is a future patch).

## [0.0.16] - 2026-05-29

### Added

- TEDS (Tree-Edit-Distance based Similarity) metric, the `[teds]` optional
  feature (`apted`, `lxml`). `from tablecodec.teds import teds, teds_html`:
  `teds(pred, true, *, structure_only=False)` scores two `TableSample`s in
  `[0, 1]` (`structure_only` gives TEDS-Struct); `teds_html` does the same for
  HTML strings. The tree construction, rename-cost rule, and
  `1 - dist / max_nodes` formula are adapted from IBM's PubTabNet reference
  metric (Apache-2.0; see `THIRD_PARTY_NOTICES.md` and
  `docs/adr/0011-teds-metric-port.md`), with a pure-Python normalized
  Levenshtein and no batching. `teds.py` is core-external (not in the semgrep
  core list, never imported by `tablecodec/__init__`), so `import tablecodec`
  stays zero-dependency. `just test`/`type`/`cov` now run with `--extra teds`;
  the tests `importorskip` when it is absent.

## [0.0.15] - 2026-05-29

### Changed

- I-05 (bbox well-formed) now decides "empty cell" by **content**, not by
  token count: a cell whose tokens concatenate to only whitespace
  (`"".join(tokens).strip() == ""`) localizes nothing, so its placeholder
  bbox is out of scope for the geometry check. This widens the 0.0.12
  scoping (which only skipped `tokens == ()`) to also skip a lone
  empty-string token `("",)` and whitespace-only tokens `(" ",)` — the
  dominant residual finding in an e2e verification sweep (70/85 SynthTabNet
  cells were `("",)`). Markup-only cells (e.g. `("<sup>", " ", "</sup>")`)
  stay content-bearing and ARE geometry-checked: the core IR does not model
  HTML, so any non-whitespace token counts as content (the IR-neutral
  line). Validation-layer only (`_invariants.py`); codecs unchanged, no
  `lossy_*` / round-trip impact. See `docs/spec.md` §5.2 and
  `docs/adr/0010-i05-empty-cell-is-whitespace-content.md` (refines ADR
  0007).

## [0.0.14] - 2026-05-29

### Removed

- The `fast` (`orjson`) and `validate` (`pydantic`) optional extras
  (`pyproject.toml` + SPEC §13 dependency table). Both were declared but
  wired nowhere, and could not be: the work they would touch — JSONL
  parsing, IR construction, validation — runs inside the zero-dependency
  core, where `semgrep.yaml` forbids third-party imports. Installing them
  pulled in a package nothing could import. `tablecodec[teds]` (a separate,
  core-external feature) and `tablecodec[cli]`/`[hf]` are unaffected.
  Stricter validation remains available via the layered validation
  profiles (SPEC §8), which are stdlib-only. See
  `docs/adr/0009-drop-fast-and-validate-extras.md`.

## [0.0.13] - 2026-05-29

### Added

- `codecs.load_plugins()` — discovers and registers third-party codecs from
  the `tablecodec.codecs` entry-point group (SPEC §6.2). Each entry point
  references a `Codec` class (instantiated) or instance; already-registered
  names are skipped (idempotent). The CLI now calls it after registering the
  built-ins, so `pip install tablecodec-<x>` codecs appear in `codecs list`
  and are usable by every command. Stdlib-only (`importlib.metadata`).

### Fixed

- E2E harness (`scripts/e2e_hf_check.py`): the DocTags round-trip adapter
  parsed `sink.getvalue().splitlines()[0]`, which breaks when a cell token
  contains a Unicode line separator (U+2028/U+2029/U+0085) that
  `json.dumps(ensure_ascii=False)` leaves raw — slicing the record
  mid-string (1/16k rows). It now parses the whole single-record buffer.
  The DocTags codec was already correct (it emits valid JSON);
  `--self-test` gains a U+2028 regression guard. Harness-only; no library
  or codec change.

## [0.0.12] - 2026-05-29

### Changed

- I-05 (bbox well-formed) is now scoped to **content-bearing cells**: a
  bbox on an empty cell (`tokens == ()`) is a placeholder region and is no
  longer geometry-checked. A live sweep showed the dominant validation
  finding was empty cells carrying zero-area placeholder boxes (≈45% of
  sampled SynthTabNet tables); these are degenerate in the SOURCE data
  (not introduced by our float→int cast), and an empty cell localizes no
  content. The fix lives entirely in the validation layer
  (`_invariants.py`); codecs are unchanged and still read/keep the bbox
  faithfully (no `lossy_*` / round-trip impact). Degenerate bboxes on
  content-bearing cells are still flagged. Profiles that require bbox
  *presence* (`tableformer`, `pubtabnet-2.0`) are unaffected. See
  `docs/spec.md` §5.2 and `docs/adr/0007-i05-empty-cell-bbox-scope.md`.

## [0.0.11] - 2026-05-29

### Fixed

- OTSL reconstruction follow-up (`_otslgrid.py`): `check_right`/`check_down`
  now stop at cells already claimed by a 2D-span `registry`. Without this a
  long `lcel` run in one row swallowed `xcel` cells belonging to a 2D span
  from above, overlapping it (real SynthTabNet rows, e.g. imgid 6075). The
  remaining SynthTabNet I-04 are genuine OTSL span ambiguity (L-shaped
  regions that cannot form an exact-cover grid), matching the HTML path.

### Added

- E2E native PubTables-1M coverage (`scripts/e2e_hf_check.py`): reads the
  original PASCAL VOC structure annotation (`bsmock/pubtables-1m`,
  download-only) from a local tar under `input/` and reconstructs the
  logical grid (rows × columns intersection, spanning-cell merge,
  column-header role) for the `pubtables-1m` codec. The harness gained a
  local-tar source alongside HF streaming; XML is parsed with `defusedxml`
  (added to the `[hf]` extra). A live run reads 200/200 real VOC tables
  clean. FinTabNet / TableBank natives remain download-only and
  Docling-covered. See `docs/adr/0006-native-datasets-via-local-download.md`.

## [0.0.10] - 2026-05-28

### Fixed

- OTSL grid reconstruction (`codecs/_otslgrid.py::build_anchors`): complex
  2D span topologies were mis-decoded — a diagonal `xcel` resolution plus
  independent `max` colspan/rowspan inflated vertical-only spans into
  overlapping boxes, and a column-0 `xcel` was wrongly rejected. A live
  e2e sweep exposed this: `SynthTabNet_OTSL` through `otsl-1.0.0` scored
  48/300 while every other corpus scored 300/300, and an HTML-vs-OTSL
  cross-check on the same rows proved the token streams were well-formed.
  `build_anchors` now reconstructs the grid with the anchor-centric
  algorithm adapted (with attribution) from docling-ibm-models'
  `otsl_to_html` — `check_right`/`check_down` span runs over `lcel`/`xcel`
  and `ucel`/`xcel`, a 2D-span registry preventing double-claims, and
  continuation tokens skipped rather than erroring. Fixes `otsl-1.0.0`,
  `fintabnet-otsl`, `doctags-tables`, `pubtables-1m` (all call
  `build_anchors`). License is unchanged (MIT → MIT requires only
  attribution; see `THIRD_PARTY_NOTICES.md` and
  `docs/adr/0005-port-otsl-reconstruction.md`).

### Added

- E2E harness (`scripts/e2e_hf_check.py`, `[hf]` extra): streams the
  Docling OTSL dataset family through the codecs and validates the
  resulting IR. Exercises the real `codec.read()` path (square-table
  assumption, anchor/cell alignment, HTML structure parsing) against
  real tables. Rows are randomly sampled (streaming shuffle reshuffles
  shard order; each run prints its `--seed` for reproducibility), so
  repeated runs progressively cover the corpora. HF logging / progress
  bars are silenced so output is just the summary. Occasional /
  local-only (not CI-gated); a network-free `--self-test` /
  `just e2e-selftest` verifies the adapters through the real codecs.
  See `docs/adr/0003-e2e-against-docling-otsl-family.md`.
  All nine shipped codecs now have at least one official-corpus check:
  the FinTabNet_OTSL checks route through the actual `fintabnet` /
  `fintabnet-otsl` codecs (adapter bridges Docling's `imgid` to
  `table_id`); `pubtabnet-1.0.0` / `tableformer` read the Docling HTML;
  `tablebank` reads the HTML structure with cells omitted; `pubtables-1m`
  reads object-detection records whose grid coords are derived from OTSL
  placement; and `doctags-tables` is a real-content round-trip. Every
  failed row is recorded as a JSONL finding
  under `output/e2e_findings/` (gitignored) — with full provenance
  (dataset/split/codec/seed/row_index), the offending cell, and the
  exact `input_payload` so a finding can be replayed and judged
  (library bug vs. malformed upstream data vs. over-strict invariant);
  `verdict` is always `needs-review`.
  The PubTabNet codecs additionally read their first-published dataset in
  its **native** shape via `apoidea/pubtabnet-html` (the original
  PubTabNet 2.0 `html` annotation, fed unmodified — not the Docling OTSL
  conversion). The other codecs' native originals (FinTabNet, TableBank,
  PubTables-1M PASCAL VOC) ship as tar.gz / image files not exposed
  through the HF Datasets viewer, so they stay Docling-covered.
  See `docs/adr/0004-e2e-native-first-published-datasets.md`.

## [0.0.9] - 2026-05-28

### Added

- FinTabNet_OTSL codec (`fintabnet-otsl`, HF `ds4sd/FinTabNet_OTSL`):
  OTSL structure with FinTabNet provenance — a `table_id` identifier
  (mapped onto `imgid`) and an `extras` dict (e.g. `otsl_raw`). It is the
  **first codec that round-trips IR `extras`**, so `extras` is
  deliberately absent from `lossy_write` (`lossy_read = {"role"}`,
  `lossy_write = {"role"}`). Structure handling is shared with OTSL via
  `_otslgrid`. `sniff()` requires both `otsl` and `table_id` keys. This
  brings the SPEC §7 initial codec set to nine.
- `_otslgrid` gains `otsl_to_cells` / `cells_to_otsl` so OTSL and
  FinTabNet_OTSL share the OTSL payload↔GridCell mapping.

### Changed

- `otsl.py` delegates its payload↔sample mapping to the new `_otslgrid`
  helpers (Tidy First, no behaviour change).

## [0.0.8] - 2026-05-28

### Fixed

- `tablecodec codecs list` now lists every built-in codec. The CLI's
  built-in registration had drifted — it still seeded only the three
  codecs that existed when the CLI was written (pubtabnet-1.0.0,
  pubtabnet-2.0.0, otsl-1.0.0), omitting fintabnet, tableformer,
  tablebank, pubtables-1m, and doctags-tables.

### Changed

- Introduced `tablecodec.codecs.builtins.BUILTIN_CODECS` as the single
  source of truth for the shipped codecs. The CLI and both doc
  generators now consume it instead of each maintaining their own list
  (no doc-output change; removes the triplicated registration).

## [0.0.7] - 2026-05-28

### Added

- DocTags table subset codec (`doctags-tables`): reads the IBM
  Granite-Docling table markup — OTSL cell tokens wrapped in
  `<otsl>`...`</otsl>`, each anchor annotated with four `<loc_n>` tokens
  (a 0–500 grid bbox) plus content tokens. Read is full (structure +
  bbox + content); write emits the OTSL-equivalent subset, so `role` is
  lost (`lossy_read = {"role"}`, `lossy_write = {"role", "extras"}`,
  SPEC §7 △). `sniff()` matches the `doctags` key.
- `_otslgrid` shared module: the OTSL structure↔grid machinery
  (`split_rows`, `ensure_square`, `build_anchors`, `build_token_grid`)
  extracted from `otsl.py` so OTSL and DocTags share one implementation.

### Changed

- `otsl.py` now delegates its grid parsing/serialization to `_otslgrid`
  (Tidy First, no behaviour change).

## [0.0.6] - 2026-05-28

### Added

- PubTables-1M codec (`pubtables-1m`): the first **read-only** codec.
  Reads the object-detection format (cells carry explicit
  row/col/rowspan/colspan/bbox in detection order) and normalises to
  row-major IR; derives nrows/ncols when absent. `write` raises
  `NotImplementedError`.
- `Codec.writable` flag (ADR 0002): boolean capability on the Codec
  Protocol. All writable codecs default to `True`; read-only codecs set
  `False`. `analyze_loss` short-circuits to a new
  `round_trip_classification` value **`"unwritable"`** when the target
  is read-only, and the loss matrix renders it as ⚫. `format_support.md`
  gains a "Writable" column.

### Changed

- Every built-in codec now declares `writable` (mechanical, defaults to
  `True`).

## [0.0.5] - 2026-05-28

### Added

- TableBank codec (`tablebank`): a structure-only format — the source
  ships `html.structure` with no `html.cells`, so on read every cell is
  empty (`tokens=()`, `bbox=None`) and the grid shape is reconstructed
  from the structure tokens. Write emits structure only. `lossy_read =
  {"tokens", "bbox"}`, `lossy_write = {"tokens", "bbox", "extras"}` —
  so TableBank is the first codec to surface `lossy` (🔴) classifications
  in the loss matrix (token loss is not structure-preserving). `sniff()`
  requires `html.structure` present and `html.cells` absent.
- `_htmltable` gains `parse_html_structure_only` /
  `serialize_html_structure_only` and a `require_no_cells` sniff knob.

## [0.0.4] - 2026-05-28

### Added

- TableFormer Format codec (`tableformer`): PubTabNet 2.0's HTML-token
  structure plus the invariant that EVERY cell — including empty ones —
  carries a bbox. The codec enforces this on read (raising a clear error
  if any cell lacks a bbox), so its output always satisfies
  `profiles.TABLEFORMER`. `sniff()` requires all cells to have a bbox,
  which distinguishes it from PubTabNet (whose empty cells omit bbox).
  `lossy_read = {}`, `lossy_write = {"extras"}`.

## [0.0.3] - 2026-05-28

### Added

- FinTabNet (original) codec (`fintabnet`): same HTML-token structure as
  PubTabNet 2.0, with `table_id` as the record identifier instead of
  `imgid`. Reads/writes via the shared `_htmltable` machinery with
  `id_field="table_id"`; `sniff()` requires the `table_id` key so a
  PubTabNet (imgid) record is not mis-detected as FinTabNet.
  `lossy_read = {}`, `lossy_write = {"extras"}`.

### Changed

- Extracted the HTML-token parser / grid-placement / serializer out of
  `codecs/pubtabnet.py` into `codecs/_htmltable.py` (Tidy First, no
  behaviour change) so PubTabNet and FinTabNet share one implementation.
- `docs/format_support.md` now also lists `otsl-1.0.0` (previously the
  generator only seeded the two PubTabNet codecs).

## [0.0.2] - 2026-05-28

Development preview (0.0.x makes no stability promises). Stdlib-only
core, three codecs, streaming I/O, static loss analysis, optional CLI,
and an in-repo conformance suite. Not published to PyPI yet — codecs
are being added incrementally within the 0.0.x series.

### Added

- Repository bootstrap (M0): `pyproject.toml` (hatchling, Python 3.11+),
  `justfile`, `ruff.toml`, `pyrightconfig.json`, GitHub Actions CI matrix
  (Python 3.11–3.13 × Ubuntu/macOS), `semgrep.yaml` enforcing
  SPEC §13 zero-dependency policy, MIT license, smoke test scaffold.
- Internal Representation (M1): SPEC §5.1 `BBox`, `GridCell`,
  `TableSample` as frozen, slotted, hashable dataclasses; SPEC §5.2
  invariants I-01..I-07 each as an independent `check_iXX` function
  returning `list[ValidationError]`. SPEC §8 validation profiles
  (`LENIENT`, `DEFAULT`, `PUBTABNET_2_0`, `TABLEFORMER`, `STRICT`)
  exposed via `tablecodec.profiles` and orchestrated by `validate()`.
  Hypothesis-driven property tests (10,000 cases) verify that valid
  samples pass every profile and that a single broken invariant is
  reported by its own check function without spurious cross-talk.
  Coverage 100% across all M1 modules; pyright strict clean.
- Codec layer (M2): SPEC §6 `Codec` Protocol (`@property` getters so
  frozen-dataclass implementations satisfy the protocol) in
  `tablecodec.codecs._base`; in-process registry (`register`, `get`,
  `list_codecs`, `detect`) in `tablecodec.codecs`. First codec:
  `PubTabNet20Codec` (`pubtabnet-2.0.0`) with streaming `read` /
  `write`, span-aware HTML table-placement algorithm, honest
  `lossy_read` (empty) and `lossy_write` (`{"extras"}`), and a
  `sniff()` delegate for `codecs.detect()`. Round-trip tests verify
  that `read → write → read` is the identity for non-extras payloads.
- Streaming I/O + PubTabNet 1.0 (M3): `tablecodec.io.open()` accepts a
  path-like or text stream and returns a streaming iterator; auto-detect
  via `tablecodec.io.detect()` peeks the source without consuming it.
  Second codec: `PubTabNet10Codec` (`pubtabnet-1.0.0`) — same format
  family minus bbox; `lossy_read = {"bbox"}`, `lossy_write =
  {"bbox", "extras"}`. Sniff discriminates the two versions by bbox
  presence in the first record. SPEC §10 streaming guarantee verified
  by tracemalloc-instrumented test: 100,000 pubtabnet-2.0 records read
  with peak < 50 MB. `docs/format_support.md` is auto-generated by
  `scripts/gen_format_support.py` and CI fails if it goes stale
  (`just docs-check`). `tests/benchmarks/` houses pytest-benchmark
  micro-benchmarks (deselected from default run, executed by
  `just bench` and the new `.github/workflows/benchmark.yaml`).
- OTSL 1.0 codec (M4): `OTSL10Codec` (`otsl-1.0.0`) implements the
  five-token OTSL grammar from arXiv 2305.03393 (`fcel`, `ecel`,
  `lcel`, `ucel`, `xcel`, plus `nl`). Square-table assumption is
  enforced on read (jagged row widths rejected with a clear error).
  Continuation tokens (lcel/ucel/xcel) extend the anchor cell they
  reference; the IR is reconstructed in two passes (parse rows →
  resolve anchors). The implementation is derived from the paper, not
  copied from `docling-ibm-models/tableformer/otsl.py`. `lossy_read =
  {"role"}` and `lossy_write = {"extras", "role"}` are honest about
  the header/body distinction collapsing through OTSL — a property
  verified by a cross-codec test that round-trips a PubTabNet sample
  with header cells through OTSL and observes role=body on return.
- Loss analysis (M5): `tablecodec.analyze_loss(source, target)` returns
  a `LossReport` derived statically from the codecs' `lossy_read` and
  `lossy_write` declarations — no data is read. The round-trip
  classification distinguishes `lossless` (nothing dropped),
  `structure-preserving` (only auxiliary `bbox`/`role`/`extras` lost),
  and `lossy` (any other field lost). `docs/loss_matrix.md` is
  auto-generated by `scripts/gen_loss_matrix.py` and the same
  `just docs-check` gate that protects `format_support.md` also
  protects it.
- CLI (M6): `tablecodec` console script (`[project.scripts]`) backed by
  `src/tablecodec/cli.py` and the `[cli]` extra (click 8.x). Six
  subcommands: `validate`, `convert`, `stats`, `diff`, `analyze-loss`,
  `codecs list`. Every command streams input; non-zero exit on
  validation failures and diff mismatches. `convert --dry-run` prints
  the static `analyze_loss` report without touching the input file.
  CLI is wholly optional — the core continues to install and run
  without click (verified by the existing pip-install-check job).
- Conformance suite skeleton (M7): the SPEC §11 corpus is bootstrapped
  in-repo under `conformance/` (manifest `INDEX.json` + draft-2020-12
  JSON Schema + samples + hand-authored expected-IR JSON), pending
  extraction to a separate vendor-neutral repository before v1.0 (see
  `docs/adr/0001-conformance-suite-in-repo-temporarily.md`).
  `tests/test_conformance.py` validates `INDEX.json` against its schema
  and runs every case (3 × pubtabnet-2.0.0, 3 × otsl-1.0.0) by reading
  the sample and comparing the IR to the independent expectation.
  `jsonschema` added to the `[dev]` extra (test-only).

<!-- v0.0.18 is the first cut release (tag + GitHub Release created by
     .github/workflows/release.yaml). Earlier 0.0.x headings stay plain text
     (no tags were pushed for them). -->
[Unreleased]: https://github.com/hironow/tablecodec/compare/v0.0.18...main
[0.0.18]: https://github.com/hironow/tablecodec/releases/tag/v0.0.18
