# tablecodec

> Neutral Internal Representation + Codec registry for image-based table-recognition datasets.

`tablecodec` is a Python library that provides a single, lossless Internal
Representation (IR) for tables and a registry-based codec layer that translates
between this IR and the fragmented landscape of public table-recognition
datasets — PubTabNet, FinTabNet, OTSL, TableFormer, DocTags-tables,
PubTables-1M, TableBank.

- Stdlib-only core. Heavier features (TEDS, CLI, `orjson`, `pydantic`) are
  opt-in extras.
- Streams large JSONL datasets at constant memory.
- Self-declared loss analysis between any two codecs.

## Status

**Pre-alpha (M0).** Bootstrapping in progress. The specification is the source
of truth; see [docs/spec.md](docs/spec.md).

## Documents

- [`docs/spec.md`](docs/spec.md) — Specification (the single source of truth).
- [`docs/intent.md`](docs/intent.md) — Implementation brief (milestones, order,
  quality bar).
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — TDD-first workflow, Conventional
  Commits, PR template.
- [`CHANGELOG.md`](CHANGELOG.md) — Keep a Changelog format.

## License

MIT. See [LICENSE](LICENSE).
