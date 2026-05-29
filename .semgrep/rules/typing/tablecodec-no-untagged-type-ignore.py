# Test fixture for `semgrep test` (NOT real code; never imported or run).
# Lines tagged ruleid must be flagged by the rule; lines tagged ok must not.

# ruleid: tablecodec-no-untagged-type-ignore
bad = some_call()  # type: ignore

# ok: tablecodec-no-untagged-type-ignore
good = some_call()  # type: ignore[arg-type]  # reason: third-party stub gap

# ok: tablecodec-no-untagged-type-ignore
fine = some_call()  # a normal comment, no type-ignore at all
