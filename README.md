# tablecodec

[![PyPI](https://img.shields.io/pypi/v/tablecodec)](https://pypi.org/project/tablecodec/)
[![CI](https://github.com/hironow/tablecodec/actions/workflows/ci.yaml/badge.svg)](https://github.com/hironow/tablecodec/actions/workflows/ci.yaml)
[![Python](https://img.shields.io/pypi/pyversions/tablecodec)](https://pypi.org/project/tablecodec/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

One **lossless Internal Representation (IR)** for image-based table-recognition
datasets, plus a **registry of codecs** that translate between the IR and the
fragmented public formats — PubTabNet, FinTabNet, OTSL, TableFormer,
DocTags-tables, PubTables-1M, TableBank.

Read any of them into one neutral shape, validate it, convert between formats,
and get a **static, data-free loss report** for any conversion before you run it.
The core has **zero third-party runtime dependencies** — `import tablecodec`
works on a bare Python 3.11+; heavier features (TEDS, CLI, HF streaming) are
opt-in extras.

[`docs/spec.md`](docs/spec.md) is the source of truth. The `0.x` line makes no
API-stability promises; the public surface freezes at `1.0` (SPEC §14).

## Install

```bash
pip install tablecodec            # stdlib-only core
pip install "tablecodec[cli]"     # + command-line interface (click)
pip install "tablecodec[teds]"    # + TEDS similarity metric (apted, lxml)
```

## Quick start

```python
import tablecodec
from tablecodec import codecs, validate, profiles, analyze_loss
from tablecodec.codecs.pubtabnet import PubTabNet20Codec

# Register a codec (the CLI self-registers the built-ins; in library use you
# register the ones you need).
codecs.register(PubTabNet20Codec())

# Stream-read a dataset into the neutral IR (constant memory).
with open("pubtabnet_val.jsonl", encoding="utf-8") as f:
    for sample in codecs.get("pubtabnet-2.0.0").read(f):
        errors = validate(sample, profile=profiles.DEFAULT)
        if errors:
            print(sample.filename, errors)

# Static, data-free loss analysis between two formats.
report = analyze_loss(source="pubtabnet-2.0.0", target="otsl-1.0.0")
print(report.round_trip_classification)  # "structure-preserving"
```

## Supported

Verified in CI (see [`.github/workflows/ci.yaml`](.github/workflows/ci.yaml)).

| Component | Supported | Notes |
|---|---|---|
| Python | 3.11 – 3.13 | core is stdlib-only (zero runtime deps, SPEC §13) |
| Codecs | 9 built-in | `pubtabnet-1.0.0/2.0.0`, `otsl-1.0.0`, `fintabnet`, `fintabnet-otsl`, `tableformer`, `tablebank`, `pubtables-1m`, `doctags-tables` |
| Extras | `[cli]` `[teds]` `[hf]` | click · apted+lxml · datasets (occasional/local e2e) |
| Bridge | `docling-tables` | a separate `tablecodec-docling` package (`packages/`, own version) |

Auto-generated capability tables: [format support](docs/format_support.md) ·
[loss matrix](docs/loss_matrix.md). Dependency bumps within these ranges are
tracked by Dependabot.

## TEDS similarity (`[teds]` extra)

A Tree-Edit-Distance-based Similarity score between two samples. It lives
outside the core (it imports `apted`/`lxml`), so import it from its submodule:

```python
from tablecodec.teds import teds

score = teds(pred_sample, true_sample)                        # 0.0 .. 1.0
struct = teds(pred_sample, true_sample, structure_only=True)  # ignore cell text
```

## CLI (`[cli]` extra)

```bash
tablecodec codecs list
tablecodec analyze-loss --from pubtabnet-2.0.0 --to otsl-1.0.0
tablecodec validate path/to/dataset.jsonl --codec pubtabnet-2.0.0 --profile DEFAULT
tablecodec stats path/to/dataset.jsonl --codec pubtabnet-2.0.0 --json
tablecodec convert in.jsonl out.jsonl --from pubtabnet-2.0.0 --to otsl-1.0.0
tablecodec convert in.jsonl /dev/null --from pubtabnet-2.0.0 --to otsl-1.0.0 --dry-run
tablecodec diff a.jsonl b.jsonl --codec pubtabnet-2.0.0
```

All commands stream their input; exit codes are non-zero on validation failures
or diffs (suitable for CI / data pipelines).

## End-to-end check against real datasets

`scripts/e2e_hf_check.py` streams real datasets through the codecs and validates
the resulting IR. It is **occasional / local-only** (network + multi-GB
datasets), not part of CI. Every shipped codec gets at least one official-corpus
check, from three sources:

- the **Docling OTSL family**
  (`docling-project/{PubTabNet,FinTabNet,PubTables-1M,SynthTabNet}_OTSL`) — a
  uniform converted schema that feeds all nine codecs;
- the **native** first-published PubTabNet annotation (`apoidea/pubtabnet-html`)
  fed unmodified to the `pubtabnet` codecs;
- the **native** PubTables-1M PASCAL VOC structure annotation
  (`bsmock/pubtables-1m`, download-only) with the logical grid reconstructed for
  the `pubtables-1m` codec.

```bash
just e2e-selftest              # network-free adapter smoke test
just e2e 200                   # 200 randomly-sampled rows per check (needs [hf] extra)
just e2e-fetch-pubtables1m     # download native PubTables-1M VOC (~30MB) into input/
```

Rows are sampled randomly and each run prints its `--seed`, so repeated runs
progressively cover the corpora and any finding is reproducible. Failures are
appended to `output/e2e_findings/` (gitignored) with a replayable payload. See
[ADR 0003](docs/adr/0003-e2e-against-docling-otsl-family.md) and
[ADR 0004](docs/adr/0004-e2e-native-first-published-datasets.md) for the
data-source decisions and the canonical-vs-real-shape caveats.

## Documentation

- [`docs/spec.md`](docs/spec.md) — Specification (the single source of truth).
- [`docs/glossary.md`](docs/glossary.md) — Precise vocabulary: terms tablecodec
  defines vs. borrows (e.g. "loss" vs a "degenerate" bbox).
- [`docs/intent.md`](docs/intent.md) — Implementation brief and roadmap
  (milestones, quality bar, §8 future work).
- [`docs/adr/`](docs/adr/) — the decisions and their reasoning (the "Why").
- [`CHANGELOG.md`](CHANGELOG.md) — Keep a Changelog format.

## Development

```bash
just install      # editable install with dev + cli + teds extras
just ci           # lint + pyright (strict) + pytest + semgrep + docs-check
just docs         # regenerate the codec/loss tables (docs-check enforces freshness)
just ci-all       # core + the in-repo tablecodec-docling bridge
```

Releases are published from GitHub Actions via PyPI **OIDC Trusted Publishing**
(no long-lived token), carrying PEP 740 attestations and a SLSA build provenance
([ADR 0014](docs/adr/0014-release-via-oidc-trusted-publishing.md)).

## License

MIT. See [LICENSE](LICENSE). The OTSL grid-reconstruction logic and the TEDS
metric are adapted (with attribution) from upstream MIT / Apache-2.0 sources —
see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
