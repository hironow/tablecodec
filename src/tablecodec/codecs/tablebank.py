"""TableBank codec.

TableBank ships table *structure* only — the source has no per-cell
tokens or bbox. On read, the grid is reconstructed from the structure
tokens and every cell is empty (``tokens=()``, ``bbox=None``). Writing
emits structure only, so any tokens/bbox an IR carries are dropped
(SPEC §7 marks TableBank write as partial / lossy).

Record shape::

    {
        "filename": "...",
        "split": "train" | "val" | "test",  # optional
        "imgid": 0,  # optional
        "html": {"structure": {"tokens": [...]}},  # no "cells"
    }
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import IO, Any

from tablecodec.codecs._htmltable import (
    parse_html_structure_only,
    serialize_html_structure_only,
    sniff_html_table,
)
from tablecodec.ir import TableSample

__all__ = ["TableBankCodec"]


@dataclass(frozen=True, slots=True)
class TableBankCodec:
    """Codec for the TableBank jsonl format (structure only, no cell content)."""

    name: str = "tablebank"
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
                yield parse_html_structure_only(payload)
            except (KeyError, ValueError, TypeError) as exc:
                msg = f"malformed TableBank record at line {line_no}: {exc}"
                raise ValueError(msg) from exc

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        for sample in samples:
            sink.write(json.dumps(serialize_html_structure_only(sample), ensure_ascii=False))
            sink.write("\n")

    def lossy_read(self) -> frozenset[str]:
        # The source carries no cell content; reading a richer file via
        # this codec discards tokens and bbox.
        return frozenset({"tokens", "bbox"})

    def lossy_write(self) -> frozenset[str]:
        return frozenset({"tokens", "bbox", "extras"})

    def sniff(self, source: IO[str]) -> bool:
        # TableBank records have html.structure but NO html.cells.
        return sniff_html_table(source, require_no_cells=True)
