"""TableFormer Format codec.

TableFormer (IBM internal) uses PubTabNet 2.0's HTML-token structure
with one extra invariant: EVERY cell — including empty ones — carries a
bbox. This codec enforces that on read (raising if any cell lacks one)
and its output therefore satisfies ``profiles.TABLEFORMER``.

Record shape is the PubTabNet 2.0 shape; the difference is purely that
``cells[i].bbox`` is always present, even when ``tokens`` is empty.
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

__all__ = ["TableFormerCodec"]


@dataclass(frozen=True, slots=True)
class TableFormerCodec:
    """Codec for the TableFormer Format jsonl (every cell has bbox)."""

    name: str = "tableformer"
    spec_version: str = "1.0.0"
    media_type: str = "application/jsonl"
    writable: bool = True

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
                sample = parse_html_table(payload)
                _require_all_cells_have_bbox(sample, line_no)
            except (KeyError, ValueError, TypeError) as exc:
                msg = f"malformed TableFormer record at line {line_no}: {exc}"
                raise ValueError(msg) from exc
            yield sample

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        for sample in samples:
            sink.write(json.dumps(serialize_html_table(sample), ensure_ascii=False))
            sink.write("\n")

    def lossy_read(self) -> frozenset[str]:
        return frozenset()

    def lossy_write(self) -> frozenset[str]:
        return frozenset({"extras"})

    def sniff(self, source: IO[str]) -> bool:
        # Discriminator: every cell carries a bbox (PubTabNet may omit it
        # on empty cells, so a bbox-less cell rules TableFormer out).
        return sniff_html_table(source, require_all_bbox=True)


def _require_all_cells_have_bbox(sample: TableSample, line_no: int) -> None:
    for idx, cell in enumerate(sample.cells):
        if cell.bbox is None:
            msg = (
                f"TableFormer requires every cell to have a bbox; cell index "
                f"{idx} has none (line {line_no})"
            )
            raise ValueError(msg)
