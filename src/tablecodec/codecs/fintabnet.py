"""FinTabNet (original) codec.

FinTabNet's original IBM annotations encode table structure with the
same HTML-token scheme as PubTabNet 2.0, differing only in the
record-level identifier: ``table_id`` instead of ``imgid``. The shared
machinery lives in :mod:`._htmltable`; this module just sets
``id_field="table_id"`` and a sniff discriminator.

Record shape::

    {
        "filename": "...",
        "split": "train" | "val" | "test",  # optional
        "table_id": 0,
        "html": {
            "structure": {"tokens": [...]},
            "cells": [{"tokens": [...], "bbox": [x0, y0, x1, y1]}, ...],
        },
    }
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import IO, Any

from tablecodec.codecs._htmltable import (
    parse_html_table,
    serialize_html_table,
    sniff_html_table,
)
from tablecodec.ir import TableSample

__all__ = ["FinTabNetCodec"]

_ID_FIELD = "table_id"


@dataclass(frozen=True, slots=True)
class FinTabNetCodec:
    """Codec for the FinTabNet (original) jsonl format."""

    name: str = "fintabnet"
    spec_version: str = "1.0.0"
    media_type: str = "application/jsonl"

    def read(self, source: IO[str]) -> Iterator[TableSample]:
        for line_no, raw in enumerate(source, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                payload: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError as exc:
                msg = f"invalid JSON at line {line_no}: {exc.msg}"
                raise ValueError(msg) from exc
            try:
                yield parse_html_table(payload, id_field=_ID_FIELD)
            except (KeyError, ValueError, TypeError) as exc:
                msg = f"malformed FinTabNet record at line {line_no}: {exc}"
                raise ValueError(msg) from exc

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        for sample in samples:
            sink.write(
                json.dumps(serialize_html_table(sample, id_field=_ID_FIELD), ensure_ascii=False)
            )
            sink.write("\n")

    def lossy_read(self) -> frozenset[str]:
        # Same HTML-token model as PubTabNet 2.0: nothing dropped on read.
        return frozenset()

    def lossy_write(self) -> frozenset[str]:
        # IR ``extras`` has no canonical home in the FinTabNet schema.
        return frozenset({"extras"})

    def sniff(self, source: IO[str]) -> bool:
        # Require the table_id key so a PubTabNet (imgid) record is not
        # mis-detected as FinTabNet.
        return sniff_html_table(source, require_field=_ID_FIELD)
