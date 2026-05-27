# tablecodec task runner.
# ROOT_AGENTS.md compliance: exactly one justfile at repo root, default → help.

default: help

# Show available tasks (default)
help:
    @just --list

# Install package + dev dependencies into the current env (editable)
install:
    uv pip install -e ".[dev,cli,teds,validate,fast]"

# Run unit tests
test:
    uv run pytest tests/ -v

# Lint (ruff check + format check)
lint:
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/

# Format and auto-fix (does not fail the build)
fmt:
    uv run ruff format src/ tests/
    uv run ruff check --fix src/ tests/

# Strict type check
type:
    uv run pyright src/ tests/

# Coverage report
cov:
    uv run pytest tests/ --cov=tablecodec --cov-report=term-missing --cov-report=html

# Run pytest-benchmark micro-benchmarks (excluded from default test run)
bench:
    uv run pytest tests/benchmarks/ -m benchmark --benchmark-only

# Semgrep meta-rules (SPEC §13, intent.md §6)
semgrep:
    semgrep --config semgrep.yaml --error src/

# Regenerate docs/format_support.md from the codec registry
docs:
    uv run python scripts/gen_format_support.py

# Verify docs/format_support.md is up to date (CI gate)
docs-check:
    @uv run python scripts/gen_format_support.py
    @git diff --quiet docs/format_support.md || (echo "docs/format_support.md is stale; run 'just docs'"; exit 1)

# Full local pre-merge gate
ci: lint type test semgrep docs-check
    @echo "OK: all checks passed"

# Wipe local caches and build artifacts
clean:
    rm -rf .pytest_cache .ruff_cache .pyright htmlcov .coverage dist build .hypothesis
    find . -type d -name "*.egg-info" -prune -exec rm -rf {} +
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
