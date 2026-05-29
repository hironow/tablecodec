# Contributing to tablecodec

Thank you for considering a contribution to `tablecodec`. This project follows
Kent Beck's TDD discipline and the workflow described in
[`docs/intent.md`](docs/intent.md).

## Quick start

```bash
# Prerequisites
brew install just uv prek  # or use mise

# Setup
git clone https://github.com/hironow/tablecodec
cd tablecodec
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev,cli,teds]"
just hooks   # install git hooks via prek (.pre-commit-config.yaml)

# Verify environment
just ci
```

`just ci` must be green locally before you push. It covers the core package;
if you touch the in-repo `packages/tablecodec-docling` bridge, also run
`just docling-ci` (or `just ci-all` for both).

## Workflow

We follow the Red → Green → Refactor cycle strictly. **One step = one commit.**
A commit that mixes structural and behavioral changes is rejected on review.

1. **Red**: write the smallest failing test for one increment of behavior.
2. **Green**: write the minimum production code to make that test pass.
3. **Refactor**: improve structure without changing behavior. Run tests
   between each refactor.

Pair this with *Tidy First?* (Kent Beck): never rename, extract, or move
code in the same commit as a behavior change.

## Conventional Commits

Commit messages MUST follow
[Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/).

```
<type>(<scope>)<!>: <subject>

<body>

<footer>
```

| Type prefix | Tidy First class | Meaning |
|---|---|---|
| `feat`, `fix`, `perf` | **Behavioral** | Adds/changes/fixes observable behavior |
| `refactor`, `style`, `test`, `docs`, `chore`, `build`, `ci` | **Structural** | No behavior change |

Subject: imperative mood, lowercase, ≤ 72 chars, no trailing period.
Scope: prefer SPEC chapter or module name (`ir`, `codec`, `cli`, `ci`, ...).

## Pull Requests

- **1 PR ≤ 1 milestone.** PRs that cross milestone boundaries are rejected.
- PR description MUST state which SPEC sections are implemented.
- All Acceptance Criteria for the milestone must be ✓ before merge.
- `just ci` must be green and the GitHub Actions matrix must be green.
- New public API requires docstrings and full type hints.

## Anti-patterns (auto-reject)

See [`docs/intent.md` §6](docs/intent.md) for the full table. Highlights:

- Third-party imports under `src/tablecodec/{ir,_invariants,validate,io,codecs/_base,codecs/pubtabnet,codecs/otsl}.py` — enforced by `.semgrep/rules/` (`just semgrep`; rules tested via `just semgrep-test`).
- `f.read()` / `f.readlines()` in `io.py` or `codecs/` — violates SPEC §10.
- `# type: ignore` without an explanatory comment.
- Bug fix without a regression test.
- Verbatim copy of upstream reference code (e.g. IBM `otsl.py`).
- Multiple `justfile` instances; there is exactly **one** at the repo root.
- YAML files named `.yml`; always use `.yaml`.

## Asking questions

If SPEC is ambiguous or a rule in `docs/intent.md` needs to be relaxed:

1. Open an issue describing the ambiguity and your proposed reading.
2. For SPEC changes, send a PR to `docs/spec.md` **first**, then implement.
3. For a one-off exception to `docs/intent.md`, document it in the PR
   description and obtain explicit reviewer approval.

Silent workarounds are not acceptable.
