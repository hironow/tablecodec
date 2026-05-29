# Test fixture for `semgrep test` (NOT real code; never imported or run).
# Lines tagged ruleid must be flagged by the rule; lines tagged ok must not.
# `semgrep test` ignores the rule's `paths:` filter, so the pattern is
# exercised here directly.

# ruleid: tablecodec-no-third-party-imports-in-core
import pydantic

# ruleid: tablecodec-no-third-party-imports-in-core
import lxml.etree

# ruleid: tablecodec-no-third-party-imports-in-core
from numpy import array

# ruleid: tablecodec-no-third-party-imports-in-core
from apted import APTED

# ok: tablecodec-no-third-party-imports-in-core
import json

# ok: tablecodec-no-third-party-imports-in-core
from collections.abc import Iterator

# ok: tablecodec-no-third-party-imports-in-core
from tablecodec.ir import TableSample
