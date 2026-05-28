# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/hironow/tablecodec/compare/v0.0.9...HEAD
[0.0.9]: https://github.com/hironow/tablecodec/releases/tag/v0.0.9
[0.0.8]: https://github.com/hironow/tablecodec/releases/tag/v0.0.8
[0.0.7]: https://github.com/hironow/tablecodec/releases/tag/v0.0.7
[0.0.6]: https://github.com/hironow/tablecodec/releases/tag/v0.0.6
[0.0.5]: https://github.com/hironow/tablecodec/releases/tag/v0.0.5
[0.0.4]: https://github.com/hironow/tablecodec/releases/tag/v0.0.4
[0.0.3]: https://github.com/hironow/tablecodec/releases/tag/v0.0.3
[0.0.2]: https://github.com/hironow/tablecodec/releases/tag/v0.0.2
