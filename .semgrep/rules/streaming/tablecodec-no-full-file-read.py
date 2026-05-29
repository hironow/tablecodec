# Test fixture for `semgrep test` (NOT real code; never imported or run).
# Lines tagged ruleid must be flagged by the rule; lines tagged ok must not.


def _read(f):
    # ruleid: tablecodec-no-full-file-read
    data = f.read()
    # ruleid: tablecodec-no-full-file-read
    lines = source.readlines()
    # ok: tablecodec-no-full-file-read
    chunk = f.read(1024)
    # ok: tablecodec-no-full-file-read
    for line in f:
        chunk = line
    return data, lines, chunk
