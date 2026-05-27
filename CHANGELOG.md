# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/hironow/tablecodec/compare/HEAD...HEAD
