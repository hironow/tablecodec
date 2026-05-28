"""PubTabNet codecs (1.0.0 and 2.0.0).

Both share the HTML-token table machinery in :mod:`._htmltable`. The
only difference is bbox handling:

- ``pubtabnet-2.0.0`` reads and writes per-cell ``bbox``.
- ``pubtabnet-1.0.0`` has no bbox: it drops bbox on read and omits it on
  write (declared honestly in ``lossy_read`` / ``lossy_write``).

PubTabNet jsonl record shape::

    {
        "filename": "PMC...",
        "split": "train" | "val" | "test",  # optional
        "imgid": 0,  # optional
        "html": {
            "structure": {"tokens": ["<thead>", "<tr>", "<td>", "</td>", ...]},
            "cells": [
                {"tokens": ["a"], "bbox": [x0, y0, x1, y1]},
                {"tokens": []},  # empty cells may omit bbox
                ...,
            ],
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

__all__ = ["PubTabNet10Codec", "PubTabNet20Codec"]


@dataclass(frozen=True, slots=True)
class PubTabNet20Codec:
    """Codec for the PubTabNet 2.0 jsonl format."""

    name: str = "pubtabnet-2.0.0"
    spec_version: str = "2.0.0"
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
                yield parse_html_table(payload)
            except (KeyError, ValueError, TypeError) as exc:
                msg = f"malformed PubTabNet 2.0 record at line {line_no}: {exc}"
                raise ValueError(msg) from exc

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        for sample in samples:
            sink.write(json.dumps(serialize_html_table(sample), ensure_ascii=False))
            sink.write("\n")

    def lossy_read(self) -> frozenset[str]:
        # PubTabNet 2.0 keeps filename, split, imgid, tokens, bbox,
        # rowspan, colspan, header/body. Nothing dropped on read.
        return frozenset()

    def lossy_write(self) -> frozenset[str]:
        # IR ``extras`` has no canonical home in the PubTabNet schema.
        return frozenset({"extras"})

    def sniff(self, source: IO[str]) -> bool:
        return sniff_html_table(source, require_no_bbox=False)


@dataclass(frozen=True, slots=True)
class PubTabNet10Codec:
    """Codec for the PubTabNet 1.0.0 jsonl format (no bbox)."""

    name: str = "pubtabnet-1.0.0"
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
                yield parse_html_table(payload, drop_bbox=True)
            except (KeyError, ValueError, TypeError) as exc:
                msg = f"malformed PubTabNet 1.0 record at line {line_no}: {exc}"
                raise ValueError(msg) from exc

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        for sample in samples:
            sink.write(
                json.dumps(serialize_html_table(sample, include_bbox=False), ensure_ascii=False)
            )
            sink.write("\n")

    def lossy_read(self) -> frozenset[str]:
        # bbox is not in the 1.0 source format; if the file is 2.0-shaped,
        # bbox is dropped silently.
        return frozenset({"bbox"})

    def lossy_write(self) -> frozenset[str]:
        return frozenset({"bbox", "extras"})

    def sniff(self, source: IO[str]) -> bool:
        return sniff_html_table(source, require_no_bbox=True)
