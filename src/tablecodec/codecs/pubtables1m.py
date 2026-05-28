"""PubTables-1M codec (read-only).

PubTables-1M (Microsoft, table-transformer) is an object-detection
format: each cell carries explicit grid coordinates and a bbox, in
detection order rather than reading order. This codec READS that into
the IR (normalising to row-major order) and is READ-ONLY — ``write``
raises ``NotImplementedError`` and ``writable`` is ``False`` (ADR 0002).

Canonical jsonl record shape::

    {
        "filename": "...",
        "split": "train" | "val" | "test",  # optional
        "imgid": 0,  # optional
        "nrows": 2,  # optional; derived from cells if absent
        "ncols": 2,  # optional; derived from cells if absent
        "cells": [
            {
                "row": 0,
                "col": 0,
                "rowspan": 1,
                "colspan": 1,
                "bbox": [x0, y0, x1, y1],
                "tokens": ["..."],
            },
            ...,  # any order
        ],
    }
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import IO, Any, Literal, cast

from tablecodec.ir import BBox, GridCell, TableSample

__all__ = ["PubTables1MCodec"]


@dataclass(frozen=True, slots=True)
class PubTables1MCodec:
    """Read-only codec for the PubTables-1M object-detection format."""

    name: str = "pubtables-1m"
    spec_version: str = "1.0.0"
    media_type: str = "application/jsonl"
    writable: bool = False

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
                yield _payload_to_sample(payload)
            except (KeyError, ValueError, TypeError) as exc:
                msg = f"malformed PubTables-1M record at line {line_no}: {exc}"
                raise ValueError(msg) from exc

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        msg = "pubtables-1m is a read-only codec (object-detection format); write is unsupported"
        raise NotImplementedError(msg)

    def lossy_read(self) -> frozenset[str]:
        # Our canonical jsonl keeps every IR field; nothing dropped.
        return frozenset()

    def lossy_write(self) -> frozenset[str]:
        # Never consulted: analyze_loss short-circuits on writable=False.
        return frozenset()

    def sniff(self, source: IO[str]) -> bool:
        pos = source.tell()
        try:
            for raw in source:
                line = raw.strip()
                if not line:
                    continue
                try:
                    payload: object = json.loads(line)
                except json.JSONDecodeError:
                    return False
                return _looks_like_pubtables1m(payload)
            return False
        finally:
            source.seek(pos)


def _looks_like_pubtables1m(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    payload_dict = cast("dict[str, Any]", payload)
    if "html" in payload_dict:  # rules out PubTabNet/FinTabNet/TableFormer/TableBank
        return False
    cells: object = payload_dict.get("cells")
    if not isinstance(cells, list) or not cells:
        return False
    first = cast("list[object]", cells)[0]
    return isinstance(first, dict) and "row" in first and "col" in first


def _normalize_split(value: object) -> Literal["train", "val", "test"] | None:
    if value == "train":
        return "train"
    if value == "val":
        return "val"
    if value == "test":
        return "test"
    if value is None:
        return None
    msg = f"unknown split value {value!r}"
    raise ValueError(msg)


def _cell_from_payload(cell_payload: dict[str, Any]) -> GridCell:
    bbox_raw = cell_payload.get("bbox")
    bbox: BBox | None = None
    if bbox_raw is not None:
        bbox = (int(bbox_raw[0]), int(bbox_raw[1]), int(bbox_raw[2]), int(bbox_raw[3]))
    role_raw = cell_payload.get("role", "body")
    role: Literal["header", "body"] = "header" if role_raw == "header" else "body"
    return GridCell(
        row=int(cell_payload["row"]),
        col=int(cell_payload["col"]),
        rowspan=int(cell_payload.get("rowspan", 1)),
        colspan=int(cell_payload.get("colspan", 1)),
        tokens=tuple(cell_payload.get("tokens", ())),
        bbox=bbox,
        role=role,
    )


def _payload_to_sample(payload: dict[str, Any]) -> TableSample:
    cell_payloads = list(payload["cells"])
    cells = [_cell_from_payload(c) for c in cell_payloads]
    # Object-detection order is arbitrary; the IR is row-major.
    cells.sort(key=lambda c: (c.row, c.col))

    nrows = payload.get("nrows")
    ncols = payload.get("ncols")
    if nrows is None:
        nrows = max((c.row + c.rowspan for c in cells), default=0)
    if ncols is None:
        ncols = max((c.col + c.colspan for c in cells), default=0)

    return TableSample(
        filename=str(payload["filename"]),
        nrows=int(nrows),
        ncols=int(ncols),
        cells=tuple(cells),
        split=_normalize_split(payload.get("split")),
        imgid=payload.get("imgid"),
    )
