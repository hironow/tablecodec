# tablecodec Semgrep rules

Project-specific static-analysis rules that encode tablecodec's
non-negotiable invariants (the things a reviewer would otherwise catch by
hand). Each rule lives in its own file and ships with a co-located test.

## Layout

```
.semgrep/rules/<category>/<rule-id>.yaml   # one rule per file (id == filename)
.semgrep/rules/<category>/<rule-id>.py     # co-located `semgrep test` fixture
```

> **Why co-located** (not a separate `.semgrep/tests/` tree): `semgrep test`
> does not support a split rules/tests layout ("the split of tests/ and
> rules/ is not supported yet"). Keeping the `.py` test next to its `.yaml`
> rule is the tool-native form. The `.py` fixtures are never imported, run,
> or linted (they live outside `src/`/`tests/`), so their intentional bad
> imports / `# type: ignore` lines are inert.

## Current rules

| Rule id | Category | Severity | Enforces |
|---|---|---|---|
| `tablecodec-no-third-party-imports-in-core` | core-deps | ERROR | SPEC §13: the core imports stdlib only |
| `tablecodec-no-full-file-read` | streaming | ERROR | SPEC §10: `read` streams, never `$F.read()`/`.readlines()` |
| `tablecodec-no-untagged-type-ignore` | typing | WARNING | a `# type: ignore` must carry `[code]` + reason |

## Running

- **Scan** the source: `just semgrep` = `semgrep --config .semgrep/rules/ --error src/`.
- **Test the rules** (authoritative — never verify a rule against real code):
  `just semgrep-test` = `semgrep test .semgrep/rules/`. It checks each rule
  against its `.py` fixture via `# ruleid:` (must flag) / `# ok:` (must not)
  annotations. `semgrep test` ignores a rule's `paths:` filter, so a
  path-scoped rule is still exercised by its fixture.

Both run in `just ci`.

## Adding a rule

1. `.semgrep/rules/<category>/<project-prefix>-<short-name>.yaml` — one rule,
   `id` equal to the filename stem.
2. `.semgrep/rules/<category>/<same-stem>.py` — at least one `# ruleid:` line
   (must match) and one `# ok:` line (must not).
3. `just semgrep-test` must pass; then `just semgrep` on `src/` stays green.
4. If the rule is path-scoped to core modules, add the new module path to the
   rule's `paths.include` (see `tablecodec-no-third-party-imports-in-core`).
