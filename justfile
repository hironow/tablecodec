SEMGREP := env("SEMGREP", "semgrep")
UV := env("UV", "uv")

# tablecodec task runner.
# Project convention: exactly one justfile at repo root, default → help.

# mise-pinned external tools (see mise.toml), wrapped so the pinned version wins.
MARKDOWNLINT := "mise exec -- markdownlint-cli2"
PREK := "mise exec -- prek"

default: help

# Show available tasks (default)
help:
    @just --list

# Install package + dev dependencies into the current env (editable)
install:
    {{UV}} pip install -e ".[dev,cli,teds]"

# Run this to pull dependencies forward. `--upgrade` is the part that matters:
# it forces a fresh resolution, which is when the relative `[tool.uv]
# exclude-newer` window is recomputed, so anything published since the last
# resolution becomes reachable. A plain `uv lock` deliberately keeps existing
# pins and would move nothing. There is no date to hand-edit any more, and the
# dependencies resolve against official PyPI, with no registry override.
#
# Re-resolve every dependency and verify the lock the way CI does
deps-upgrade:
    {{UV}} lock --upgrade
    {{UV}} sync --locked

# Install git hooks via prek (pre-commit + pre-push; reads .pre-commit-config.yaml)
hooks:
    {{PREK}} install -t pre-commit -t pre-push

alias install-hooks := hooks

# Run every prek hook against all files (matches what git invokes)
pre-commit:
    {{PREK}} run --all-files

# Run unit tests (--extra teds so the optional TEDS tests run, not skip)
test:
    {{UV}} run --extra teds pytest tests/ -v

# Lint (ruff check + format check + markdown, no writes).
# docs/adr/ is excluded: ADRs are immutable records, not reformatted/gated.
lint:
    {{UV}} run --group lint ruff check src/ tests/ scripts/
    {{UV}} run --group lint ruff format --check src/ tests/ scripts/
    git ls-files -z '*.md' ':!docs/adr' | xargs -0 -r {{MARKDOWNLINT}}

# Format and auto-fix (does not fail the build)
fmt:
    {{UV}} run --group lint ruff format src/ tests/ scripts/
    {{UV}} run --group lint ruff check --fix src/ tests/ scripts/
    git ls-files -z '*.md' ':!docs/adr' | xargs -0 -r {{MARKDOWNLINT}} --fix

# Strict type check (--extra teds so apted/lxml resolve when checking teds.py)
type:
    {{UV}} run --locked --group lint --extra teds ty check src/ tests/

# Coverage report
cov:
    {{UV}} run --extra teds pytest tests/ --cov=tablecodec --cov-report=term-missing --cov-report=html

# Run pytest-benchmark micro-benchmarks (excluded from default test run)
bench:
    {{UV}} run pytest tests/benchmarks/ -m benchmark --benchmark-only

# Network-free smoke test of the e2e HF adapters (no [hf] extra needed)
e2e-selftest:
    {{UV}} run python scripts/e2e_hf_check.py --self-test

# Stream Docling OTSL datasets through the codecs (needs [hf] extra + network).
# Occasional / local-only. Override LIMIT to sample more/fewer rows per check.
e2e limit="200" *args:
    {{UV}} run --locked --extra hf python scripts/e2e_hf_check.py --limit {{limit}} {{args}}

# Download the native PubTables-1M VOC structure annotations (~30MB) into
# input/ for the native pubtables-1m e2e check (download-only dataset).
e2e-fetch-pubtables1m:
    {{UV}} run --extra hf python -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='bsmock/pubtables-1m', repo_type='dataset', filename='PubTables-1M-Structure_Annotations_Val.tar.gz', local_dir='input/pubtables-1m')"

# Semgrep meta-rules (SPEC §13, intent.md §6) — scan the source
semgrep:
    {{SEMGREP}} --config .semgrep/rules/ --error src/

# Test the semgrep rules against their co-located fixtures (rule correctness)
semgrep-test:
    {{SEMGREP}} test .semgrep/rules/

# Regenerate auto-generated docs from the codec registry
docs:
    {{UV}} run python scripts/gen_format_support.py
    {{UV}} run python scripts/gen_loss_matrix.py

# Verify auto-generated docs are up to date (CI gate)
docs-check:
    @{{UV}} run python scripts/gen_format_support.py
    @{{UV}} run python scripts/gen_loss_matrix.py
    @git diff --quiet docs/format_support.md docs/loss_matrix.md || (echo "docs/{format_support,loss_matrix}.md is stale; run 'just docs'"; exit 1)

# Full local pre-merge gate (core package only; stays zero-dep-focused)
ci: lint type test semgrep semgrep-test docs-check
    @echo "OK: all checks passed"

# Strict no-write gate == ci (the pre-push hook runs this; nothing weaker
# than the full gate catches what CI catches here)
alias check := ci

# ---- docling bridge sub-package (packages/tablecodec-docling, ADR 0013) ----
# Run in its OWN uv project so docling-core stays out of the core env.
_DOCLING := "packages/tablecodec-docling"

# Lint the docling bridge package.
# --locked asserts the bridge lockfile matches its pyproject.toml, the same
# guard CI applies to the core with `uv sync --locked`. Without it a drifted
# bridge lock (a stale pin or an unexpected registry) goes
# unnoticed, because no CI job gates this sub-package.
docling-lint:
    {{UV}} run --project {{_DOCLING}} --locked --group lint ruff check {{_DOCLING}}
    {{UV}} run --project {{_DOCLING}} --locked --group lint ruff format --check {{_DOCLING}}

# Type-check the docling bridge package (ty)
docling-type:
    {{UV}} run --project {{_DOCLING}} --locked --group lint ty check {{_DOCLING}}/src {{_DOCLING}}/tests

# Test the docling bridge package
docling-test:
    {{UV}} run --project {{_DOCLING}} --locked pytest {{_DOCLING}}/tests

# Full gate for the docling bridge sub-package
docling-ci: docling-lint docling-type docling-test
    @echo "OK: docling bridge checks passed"

# Whole-monorepo gate: core + docling bridge
ci-all: ci docling-ci
    @echo "OK: all packages passed"

# Wipe local caches and build artifacts
clean:
    rm -rf .pytest_cache .ruff_cache .pyright htmlcov .coverage dist build .hypothesis
    find . -type d -name "*.egg-info" -prune -exec rm -rf {} +
    find . -type d -name __pycache__ -prune -exec rm -rf {} +

# Verify the core lock with the same extras as CI
lock-check:
    {{UV}} sync --locked --group lint --extra dev --extra cli --extra teds

# Check draft/ready policy in both pull-request workflows
check-workflows:
    {{UV}} run --locked pytest tests/test_workflow_policy.py -q

# Verify editable core installation in a fresh environment without extras
core-install-check:
    {{UV}} venv .venv-check --python 3.11
    {{UV}} pip install --python .venv-check/bin/python -e .
    .venv-check/bin/python -c "import tablecodec; print(tablecodec.__version__)"

# Resolve against official PyPI while retaining the current package pins.
lock-public:
    {{UV}} lock
    {{UV}} lock --project packages/tablecodec-docling

# Build without publishing; release OIDC and tag gates remain separate.
build-check:
    {{UV}} build
    {{UV}} build --project packages/tablecodec-docling

bridge-lock-check:
    {{UV}} sync --project packages/tablecodec-docling --locked --group lint

# Format only the test fixtures changed for the type-checker transition.
format-type-tests:
    {{UV}} run --group lint ruff format tests/test_invariants.py tests/test_ir.py tests/test_spec_surface.py tests/test_validate.py

lint-md-fix:
    {{MARKDOWNLINT}} --fix CLAUDE.md README.md packages/tablecodec-docling/README.md docs/release.md docs/intent.md docs/handover.md

check-actionlint:
    actionlint .github/workflows/*.yaml

docling-fmt:
    {{UV}} run --project {{_DOCLING}} --locked --group lint ruff format {{_DOCLING}}
