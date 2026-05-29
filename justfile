# tablecodec task runner.
# ROOT_AGENTS.md compliance: exactly one justfile at repo root, default → help.

default: help

# Show available tasks (default)
help:
    @just --list

# Install package + dev dependencies into the current env (editable)
install:
    uv pip install -e ".[dev,cli,teds]"

# Run unit tests (--extra teds so the optional TEDS tests run, not skip)
test:
    uv run --extra teds pytest tests/ -v

# Lint (ruff check + format check)
lint:
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/

# Format and auto-fix (does not fail the build)
fmt:
    uv run ruff format src/ tests/
    uv run ruff check --fix src/ tests/

# Strict type check (--extra teds so apted/lxml resolve when checking teds.py)
type:
    uv run --extra teds pyright src/ tests/

# Coverage report
cov:
    uv run --extra teds pytest tests/ --cov=tablecodec --cov-report=term-missing --cov-report=html

# Run pytest-benchmark micro-benchmarks (excluded from default test run)
bench:
    uv run pytest tests/benchmarks/ -m benchmark --benchmark-only

# Network-free smoke test of the e2e HF adapters (no [hf] extra needed)
e2e-selftest:
    uv run python scripts/e2e_hf_check.py --self-test

# Stream Docling OTSL datasets through the codecs (needs [hf] extra + network).
# Occasional / local-only. Override LIMIT to sample more/fewer rows per check.
e2e limit="200":
    uv run --extra hf python scripts/e2e_hf_check.py --limit {{limit}}

# Download the native PubTables-1M VOC structure annotations (~30MB) into
# input/ for the native pubtables-1m e2e check (download-only dataset).
e2e-fetch-pubtables1m:
    uv run --extra hf python -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='bsmock/pubtables-1m', repo_type='dataset', filename='PubTables-1M-Structure_Annotations_Val.tar.gz', local_dir='input/pubtables-1m')"

# Semgrep meta-rules (SPEC §13, intent.md §6)
semgrep:
    semgrep --config semgrep.yaml --error src/

# Regenerate auto-generated docs from the codec registry
docs:
    uv run python scripts/gen_format_support.py
    uv run python scripts/gen_loss_matrix.py

# Verify auto-generated docs are up to date (CI gate)
docs-check:
    @uv run python scripts/gen_format_support.py
    @uv run python scripts/gen_loss_matrix.py
    @git diff --quiet docs/format_support.md docs/loss_matrix.md || (echo "docs/{format_support,loss_matrix}.md is stale; run 'just docs'"; exit 1)

# Full local pre-merge gate
ci: lint type test semgrep docs-check
    @echo "OK: all checks passed"

# Wipe local caches and build artifacts
clean:
    rm -rf .pytest_cache .ruff_cache .pyright htmlcov .coverage dist build .hypothesis
    find . -type d -name "*.egg-info" -prune -exec rm -rf {} +
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
