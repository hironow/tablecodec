# tablecodec — Specification

**Status:** Draft — spec document v0.1.0 (this is the specification's own
version; the `tablecodec` package is independently versioned in the 0.0.x
series — see the package metadata / CHANGELOG for its current version).
**Last updated:** 2026-05-29
**License of this document:** CC BY 4.0

---

## 1. Abstract

`tablecodec` is a Python library that provides a neutral **Internal Representation (IR)** for image-based table-recognition datasets and a registry-based **Codec** layer that translates between this IR and the fragmented landscape of public dataset formats (PubTabNet, FinTabNet, TableBank, PubTables-1M, OTSL, TableFormer Format, DocTags-tables, and others).

The library has a **stdlib-only core**. Heavier features (TEDS evaluation, HTML parsing, CLI) are opt-in extras.

---

## 2. Motivation

As of mid-2026, table-structure datasets are published in incompatible formats:

- **HTML-token formats**: PubTabNet 1.x / 2.0, FinTabNet (original), TableBank, SciTSR.
- **Sequence-language formats**: OTSL (IBM, ICDAR 2023), DocTags (IBM Granite-Docling, January 2026).
- **Object-detection formats**: PubTables-1M (Microsoft).
- **Augmented derivatives**: TableFormer Format (IBM internal), FinTabNet_OTSL, MUSTARD (SPRINT, March 2025).

Every major training pipeline (PaddleOCR, Docling, MTL-TabNet, UniTable, SPRINT) reinvents preprocessing scripts. There is no shared abstraction. `docling-core` (the closest existing library) is document-wide, Pydantic-bound, and ships heavy dependencies, making it unsuitable for dataset-only workflows, large-scale streaming validation, or environments where install footprint matters.

`tablecodec` fills exactly this gap, and only this gap.

---

## 3. Goals and Non-goals

### 3.1 Goals

1. Provide a lossless, neutral IR that can represent every cited format without privileging any.
2. Provide a Codec registry that allows third parties to add new formats without modifying the core.
3. Stream-friendly I/O: handle JSONL files with 500k+ samples without loading all into memory.
4. Self-declared loss analysis: every codec must state what information it loses on read / write.
5. Conformance test corpus published as a separate, vendor-neutral artifact.
6. Stable API once 1.0 is reached. Breaking changes require a major version bump.
7. Zero third-party dependencies in the core package.

### 3.2 Non-goals

- Model inference, training, or any GPU code.
- Image manipulation (no Pillow, OpenCV, numpy in core).
- Full document representation. `tablecodec` only handles tables, not entire pages or documents. `docling-core` is the right tool for whole-document workflows.
- Dataset download or hosting. Hugging Face Datasets and the official repositories serve that role.
- An opinion on which format is "best." All supported formats are first-class.

---

## 4. Terminology

| Term              | Definition |
|-------------------|------------|
| **IR**            | The internal representation defined in §5. |
| **Codec**         | A reader + writer pair for one external format. |
| **Sample**        | One annotated table image with its structural metadata. |
| **Profile**       | A named bundle of validation rules tied to a specific format version (e.g. `pubtabnet-2.0.0`). |
| **Conformance**   | Verifiable behavioral compliance with this specification, established by passing the published test corpus. |

---

## 5. Internal Representation (IR)

The IR is intentionally a **2D grid model**, not HTML, not OTSL, and not DocTags. The grid model:

- Is the smallest representation that can hold every cited format losslessly.
- Makes structural invariants directly checkable (coverage, span consistency).
- Maps cleanly to and from every token-language format published to date.

### 5.1 Types

All types are immutable, hashable, and defined using `dataclasses` (`frozen=True, slots=True`). No Pydantic dependency.

```python
BBox = tuple[int, int, int, int]   # (x0, y0, x1, y1), absolute pixels

@dataclass(frozen=True, slots=True)
class GridCell:
    row: int                       # zero-indexed
    col: int                       # zero-indexed
    rowspan: int = 1               # must be >= 1
    colspan: int = 1               # must be >= 1
    tokens: tuple[str, ...] = ()   # cell content as ordered tokens
    bbox: BBox | None = None       # absent when content is empty OR format omits it
    role: Literal["header", "body"] = "body"

@dataclass(frozen=True, slots=True)
class TableSample:
    filename: str
    nrows: int                     # logical row count
    ncols: int                     # logical column count
    cells: tuple[GridCell, ...]    # ordered top-to-bottom, left-to-right
    split: Literal["train", "val", "test"] | None = None
    imgid: int | None = None
    extras: Mapping[str, object] = field(default_factory=dict)
```

### 5.2 Invariants

A `TableSample` is **valid** when **all** of the following hold:

| ID    | Invariant |
|-------|-----------|
| I-01  | `nrows >= 1` and `ncols >= 1`. |
| I-02  | For every cell, `0 <= row < nrows` and `0 <= col < ncols`. |
| I-03  | For every cell, `row + rowspan <= nrows` and `col + colspan <= ncols`. |
| I-04  | The union of cell footprints (using rowspan / colspan) **exactly covers** the `nrows × ncols` grid. No overlaps, no gaps. |
| I-05  | When `bbox` is set **on a content-bearing cell** (`tokens` non-empty): `bbox[0] < bbox[2]` and `bbox[1] < bbox[3]`. A bbox on an **empty cell** (`tokens == ()`) is a placeholder region and is **not** geometry-checked. |
| I-06  | Header cells form a contiguous top-region of the grid (no header rows below body rows). |
| I-07  | `tokens` may be empty (empty cell), but the tuple itself is never `None`. |

I-05 guards the geometry of a box that **localizes content**. An empty
cell localizes nothing, and source datasets routinely assign zero-area
placeholder boxes to empty cells (e.g. SynthTabNet, where ~45% of sampled
tables carry such boxes), so an empty cell's bbox geometry is out of
scope for I-05. Codecs still read and keep the bbox faithfully — it
remains on the IR and is preserved on round-trip; only the geometry check
is skipped for empty cells. (Profiles that require bbox *presence* —
`tableformer`, `pubtabnet-2.0` — are unaffected: a placeholder box is
still present.)

The `extras` field is **opaque to validation** but must be JSON-serializable for codecs that round-trip through it.

### 5.3 What the IR intentionally does NOT model

- Cell styling (fonts, colors, borders). HTML attributes beyond structure are lost on import. Codecs may preserve them via `extras` but the IR does not validate them.
- Multi-table documents. One sample = one table.
- Page-level layout. Use `docling-core` for that.

---

## 6. Codec Contract

A codec is registered against a stable string name and provides four operations:

```python
class Codec(Protocol):
    name: str                          # registry key, e.g. "pubtabnet-2.0.0"
    spec_version: str                  # version of the source format, not of this library
    media_type: str                    # canonical MIME type, e.g. "application/jsonl"

    def read(self, source: IO[str]) -> Iterator[TableSample]: ...
    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None: ...

    def lossy_read(self) -> frozenset[str]: ...
    """Field paths within the source format that are dropped on read."""

    def lossy_write(self) -> frozenset[str]: ...
    """IR fields that cannot be expressed in this format on write."""
```

### 6.1 Required behavior

1. `read` MUST yield samples lazily. No full-file slurp.
2. `read` parses each record into a `TableSample` and MUST raise (with the record offset, see 4) on any record it cannot parse — invalid JSON, unknown tokens, structure/cell-count mismatch, etc. `read` does **not** evaluate the structural invariants (§5.2). Invariant checking is a separate, opt-in step performed by `validate(sample, profile)` (§8), so the caller chooses the strictness and pays the cost only when wanted, and may still read records that are parseable but invariant-invalid (common in real corpora). See ADR 0008.
3. `write` MUST produce output that, when re-read by the same codec, round-trips losslessly **except** for the fields declared in `lossy_write`.
4. Errors during streaming MUST include the source line / record offset.
5. `lossy_read` and `lossy_write` MUST be honest. CI in this repository enforces this via round-trip tests.

### 6.2 Registry

```python
from tablecodec import codecs

codecs.register(MyCodec())
codecs.get("pubtabnet-2.0.0")
codecs.detect(source)   # returns name | None by peeking at the first record
```

Third-party codecs distribute themselves as separate PyPI packages (`tablecodec-mycodec`) and self-register via the entry-point group `tablecodec.codecs`.

---

## 7. Supported Formats (initial)

| Codec name              | Source format                          | Read | Write | Notes |
|-------------------------|----------------------------------------|------|-------|-------|
| `pubtabnet-1.0.0`       | PubTabNet 1.x (no bbox)                | ✓    | ✓     | bbox always None on read |
| `pubtabnet-2.0.0`       | PubTabNet 2.0.0                        | ✓    | ✓     | Reference codec for §11 invariants |
| `fintabnet`             | FinTabNet (original PubTabNet-like)    | ✓    | ✓     |       |
| `fintabnet-otsl`        | `ds4sd/FinTabNet_OTSL` (HF)            | ✓    | ✓     | Lossy on `extras.otsl_raw` removal |
| `otsl-1.0.0`            | OTSL token sequences                   | ✓    | ✓     | Square-table assumption per spec |
| `tableformer`           | TableFormer Format (IBM internal)      | ✓    | ✓     | bbox required on empty cells |
| `doctags-tables`        | DocTags table subset (Granite-Docling) | ✓    | △     | Write is OTSL-equivalent subset only |
| `pubtables-1m`          | Microsoft PubTables-1M (object-det.)   | ✓    | ✗     | Read-only: bbox-first, no token order |
| `tablebank`             | TableBank                              | ✓    | △     | Tokens absent in source |

`△` = partial / lossy. Each codec's documentation MUST specify exactly which fields are affected.

Codecs not listed here are out-of-scope for v1.0 but may be added as third-party packages.

---

## 8. Validation Profiles

Validation is layered. A user explicitly opts into the strictness they need.

| Profile          | Enforces |
|------------------|----------|
| `lenient`        | I-01, I-02, I-03, I-05 only. Permits gaps and overlaps (I-04 off). |
| `default`        | All of §5.2 (I-01 through I-07). |
| `pubtabnet-2.0`  | `default` plus: every non-empty cell has `bbox`. |
| `tableformer`    | `default` plus: every cell, empty or not, has `bbox`. |
| `strict`         | `default` plus: cross-check bbox against image dimensions (requires image metadata). |

Profile selection:

```python
from tablecodec import validate, profiles

errors = validate(sample, profile=profiles.PUBTABNET_2_0)
```

Errors are returned as a structured list. Validators never raise on data; they raise only on programmer error (e.g. unknown profile name).

---

## 9. Loss Analysis

`tablecodec` provides one feature that no inference-oriented library offers: explicit, automated loss analysis between any two codecs.

```python
from tablecodec import analyze_loss

report = analyze_loss(source="pubtabnet-2.0.0", target="otsl-1.0.0")
# Report contains:
#   - source_fields_dropped_on_read
#   - ir_fields_unrepresentable_in_target
#   - round_trip_classification: "lossless" | "structure-preserving" | "lossy"
```

This is the operational backbone for any migration from one format to another. CI in this repository runs `analyze_loss` across the full Cartesian product of supported codecs and publishes the result with each release.

---

## 10. Streaming Guarantees

| Operation                            | Guarantee |
|--------------------------------------|-----------|
| Reading a 568k-sample JSONL          | Constant memory (one sample at a time), single-pass. |
| Writing the same                     | Constant memory. |
| Validation across the dataset        | Lazy generator, constant memory. |
| `analyze_loss`                       | No data read at all; static analysis of codec metadata. |
| `convert`                            | Constant memory; backpressure-safe iterator chain. |

These guarantees are part of the public API contract and are enforced by CI benchmarks.

---

## 11. Conformance Suite

A separate, vendor-neutral repository (`tablecodec/conformance`) hosts test fixtures and expected outputs. Any implementation (in any language) claiming `tablecodec`-compatibility MUST pass this suite.

The suite is structured as:

```
conformance/
├── samples/
│   ├── pubtabnet-2.0.0/
│   │   ├── 001_simple.jsonl
│   │   ├── 002_complex_spans.jsonl
│   │   └── ...
│   ├── otsl-1.0.0/
│   └── ...
├── expectations/
│   ├── 001_simple.ir.json         # expected IR after read
│   └── ...
└── INDEX.json                      # machine-readable test manifest
```

Vendors (Docling, PaddleOCR, MMOCR, internal pipelines) are invited to certify their preprocessing against this suite and link the certification badge from their READMEs.

---

## 12. CLI Surface

Available with `pip install "tablecodec[cli]"`.

```
tablecodec validate <file>           [--profile NAME] [--codec <codec>] [--json]
tablecodec convert  <in> <out>       --from <codec> --to <codec> [--dry-run]
tablecodec stats    <file>           [--codec <codec>] [--json]
tablecodec diff     <a> <b>          [--codec <codec>]
tablecodec analyze-loss --from <codec> --to <codec>
tablecodec codecs   list
```

`--codec` selects the reader; when omitted, the codec is auto-detected
from the file (`codecs.detect`). (`--strict` is just `--profile strict`;
parallel conversion is not offered — `convert` is a constant-memory
single-pass stream.)

All commands stream input and exit non-zero on validation failures, suitable for use in CI / data pipelines.

---

## 13. Dependency Policy

| Package                   | Dependencies                                   |
|---------------------------|------------------------------------------------|
| `tablecodec`              | **Python stdlib only.** Hard requirement.      |
| `tablecodec[teds]`        | `apted`, `lxml` (TEDS evaluation wrappers)     |
| `tablecodec[cli]`         | `click` (CLI)                                  |
| `tablecodec[hf]`          | `datasets`, `defusedxml` (occasional, local-only e2e harness; not a library runtime dependency) |
| `tablecodec[all]`         | All of the above                               |

A pull request that introduces a new third-party dependency to the core package MUST be rejected. CI enforces this via an import-graph linter (`semgrep.yaml`).

> The earlier `fast` (orjson) and `validate` (pydantic) extras were removed
> (ADR 0009): the work they would touch — JSONL parsing, IR construction,
> validation — happens in the zero-dependency core, where third-party
> imports are forbidden, so the extras could never be wired in. Stricter
> validation is provided by the layered profiles (§8), which are stdlib-only.

---

## 14. Versioning and Stability

`tablecodec` follows Semantic Versioning, with the following additional commitments:

- **0.x**: API may change. No stability promises.
- **1.0**: API frozen for minor releases. Breaking changes require a major bump.
- **LTS**: Each major version is supported (security and codec compatibility fixes) for at least **3 years** from its initial release.
- **Format spec drift**: When an upstream format changes (e.g. PubTabNet publishes 3.0.0), a new codec name is registered (`pubtabnet-3.0.0`). Old codecs are kept until their corresponding upstream format is officially deprecated.

The library version and each codec's `spec_version` are tracked
**independently** — the library version is `tablecodec.__version__`
(printed by `tablecodec --version`), while each codec carries its own
`spec_version` attribute and encodes the format version in its registry
name (e.g. `pubtabnet-2.0.0`). The IR has no separate runtime version
constant: in the 0.x line it evolves with the library, and this document
(see the Status header) is the versioned description of the IR.

---

## 15. Relationship to docling-core

`tablecodec` and `docling-core` are complementary, not competing.

| Aspect              | `docling-core`                                  | `tablecodec`                                  |
|---------------------|-------------------------------------------------|-----------------------------------------------|
| Scope               | Entire documents (pages, sections, tables, figures) | Tables only                                   |
| IR                  | `DoclingDocument` (Pydantic, hierarchical)      | `TableSample` (dataclass, 2D grid)            |
| Dependencies        | Pydantic, jsonschema, latex2mathml, typer, ...  | Stdlib                                        |
| Use case            | Document conversion pipelines                   | Dataset I/O, validation, format migration     |
| Format opinion      | DocTags / OTSL native, others as importers      | All formats first-class                       |

A bridge codec (`tablecodec-docling`) is planned as a separate package, allowing `DoclingDocument.tables` to be exported as `TableSample` instances.

---

## 16. Governance

`tablecodec` is released under the **MIT License**. Contributions are accepted under the same license.

The library deliberately maintains **no dependency on any single vendor's format**. Should a single format become the de facto standard, that format will be supported as one codec among equals, not as a privileged IR.

The Conformance Suite repository is a separate, MIT-licensed artifact intended for vendor-neutral certification. Should a foundation (e.g. Linux Foundation AAIF) wish to adopt it, the maintainers will support the donation under preservation of the format-neutrality clause above.

---

## 17. Open Questions

The following are intentionally left undecided in v0.1 and will be resolved before v1.0:

- **OQ-1**: Should `TableSample.cells` be ordered (current spec) or unordered (a set)? Ordering simplifies serialization but introduces a canonicalization requirement.
- **OQ-2**: How should multi-line text within a single cell be tokenized? Per-character (PubTabNet) or per-word (PubTables-1M)?
- **OQ-3**: Should `bbox` support floating-point coordinates? Currently integer-only, but PubTables-1M uses floats.
- **OQ-4**: Whether to publish a JSON Schema for the IR alongside the dataclass definitions, for cross-language use.

---

## 18. References

### Datasets and format specifications

- PubTabNet: <https://github.com/ibm-aur-nlp/PubTabNet>
- PubTabNet on Hugging Face (current mirror): <https://huggingface.co/datasets/ajimeno/PubTabNet>
- FinTabNet: <https://developer.ibm.com/exchanges/data/all/fintabnet/>
- FinTabNet_OTSL (Docling Project): <https://huggingface.co/datasets/ds4sd/FinTabNet_OTSL> · <https://huggingface.co/datasets/docling-project/FinTabNet_OTSL>
- PubTables-1M (Microsoft): <https://github.com/microsoft/table-transformer>
- TableBank: <https://github.com/doc-analysis/TableBank>
- SciTSR: <https://github.com/Academic-Hammer/SciTSR>
- MUSTARD (multilingual OTSL): <https://github.com/IITB-LEAP-OCR/SPRINT>

### Papers

- Zhong, ShafieiBavani, Yepes. *Image-based table recognition: data, model, and evaluation*. ECCV 2020. <https://arxiv.org/abs/1911.10683>
- Nassar et al. *TableFormer: Table Structure Understanding with Transformers*. CVPR 2022. <https://arxiv.org/abs/2203.01017>
- Lysak et al. *Optimized Table Tokenization for Table Structure Recognition* (OTSL). ICDAR 2023. <https://arxiv.org/abs/2305.03393>
- Smock, Pesala, Abraham. *PubTables-1M: Towards Comprehensive Table Extraction*. CVPR 2022. <https://arxiv.org/abs/2110.00061>
- Smock et al. *GriTS: Grid table similarity metric*. ICDAR 2023.
- Mehta et al. *SPRINT: Script-agnostic Structure Recognition in Tables*. arXiv 2025-03. <https://arxiv.org/abs/2503.11932>

### Reference implementations consulted

- TEDS metric (official): <https://github.com/ibm-aur-nlp/PubTabNet/blob/master/src/metric.py>
- OTSL reference parser (Docling): <https://github.com/docling-project/docling-ibm-models/blob/main/docling_ibm_models/tableformer/otsl.py>
- `docling-core` (DoclingDocument): <https://github.com/docling-project/docling-core>
- PaddleOCR PP-Structure table module: <https://github.com/PaddlePaddle/PaddleOCR/tree/main/ppstructure/table>
- UniTable mini-PubTabNet format: <https://github.com/poloclub/unitable>

### Related ecosystem

- Docling (project): <https://github.com/docling-project/docling>
- Linux Foundation Agentic AI Foundation (AAIF): <https://aaif.linuxfoundation.org/>
- Granite-Docling-258M (DocTags origin, January 2026): <https://huggingface.co/ibm-granite/granite-docling-258M>

### Prior-art naming conventions

- Python `codecs` module (registry pattern): <https://docs.python.org/3/library/codecs.html>
- JSON Schema Test Suite (conformance pattern): <https://github.com/json-schema-org/JSON-Schema-Test-Suite>
- Web Platform Tests (multi-vendor conformance): <https://github.com/web-platform-tests/wpt>
