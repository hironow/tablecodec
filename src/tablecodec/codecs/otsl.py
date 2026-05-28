"""OTSL 1.0 codec.

Implements the Optimized Table Structure Language (Lysak et al.,
ICDAR 2023, arXiv 2305.03393). OTSL uses a five-token vocabulary plus
a newline marker:

- ``fcel`` filled cell anchor (body content)
- ``ecel`` empty cell anchor
- ``lcel`` left-merged continuation — extends the colspan of the anchor
  to its left
- ``ucel`` up-merged continuation — extends the rowspan of the anchor above
- ``xcel`` cross-merged continuation — extends both row and column
  (the anchor sits at (r-1, c-1) of this position)
- ``nl``   newline / row separator

Square-table assumption (per the paper): every row produced by ``nl``
splits MUST have the same number of cell-position tokens. Jagged input
is rejected with a clear error.

This implementation is derived from the paper, not copied from the
official Docling OTSL reference implementation. Cross-validation
against the reference is wired separately in a later milestone.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import IO, Any, cast

from tablecodec.codecs._otslgrid import build_anchors, build_token_grid, split_rows
from tablecodec.ir import BBox, GridCell, TableSample

__all__ = ["OTSL10Codec"]


@dataclass(frozen=True, slots=True)
class OTSL10Codec:
    """Codec for the OTSL 1.0 jsonl format."""

    name: str = "otsl-1.0.0"
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
                yield _payload_to_sample(payload)
            except (KeyError, ValueError, TypeError) as exc:
                msg = f"malformed OTSL 1.0 record at line {line_no}: {exc}"
                raise ValueError(msg) from exc

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        for sample in samples:
            sink.write(json.dumps(_sample_to_payload(sample), ensure_ascii=False))
            sink.write("\n")

    def lossy_read(self) -> frozenset[str]:
        # OTSL has no header/body distinction in its grammar; reads default
        # every cell to role="body". This is a real loss when the source
        # carried a header/body tag.
        return frozenset({"role"})

    def lossy_write(self) -> frozenset[str]:
        # role: collapsed to "body" on write.
        # extras: no canonical home in OTSL.
        return frozenset({"extras", "role"})

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
                return _looks_like_otsl(payload)
            return False
        finally:
            source.seek(pos)


def _looks_like_otsl(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    payload_dict = cast("dict[str, Any]", payload)
    return "otsl" in payload_dict and "cells" in payload_dict


# ---------- token → grid (delegates to _otslgrid) ----------


def _payload_to_sample(payload: dict[str, Any]) -> TableSample:
    otsl_tokens = list(payload["otsl"])
    cell_payloads = list(payload["cells"])
    rows = split_rows(otsl_tokens)
    nrows, ncols, anchors = build_anchors(rows)

    if len(anchors) != len(cell_payloads):
        msg = (
            f"OTSL declares {len(anchors)} anchored cells but cells[] has "
            f"{len(cell_payloads)} entries"
        )
        raise ValueError(msg)

    cells: list[GridCell] = []
    for anchor, cell_payload in zip(anchors, cell_payloads, strict=True):
        tokens = tuple(cell_payload.get("tokens", ()))
        bbox_raw = cell_payload.get("bbox")
        bbox: BBox | None = None
        if bbox_raw is not None:
            bbox = (
                int(bbox_raw[0]),
                int(bbox_raw[1]),
                int(bbox_raw[2]),
                int(bbox_raw[3]),
            )
        cells.append(
            GridCell(
                row=anchor.row,
                col=anchor.col,
                rowspan=anchor.rowspan,
                colspan=anchor.colspan,
                tokens=tokens,
                bbox=bbox,
                role="body",  # OTSL grammar has no header marker.
            )
        )

    return TableSample(
        filename=str(payload["filename"]),
        nrows=nrows,
        ncols=ncols,
        cells=tuple(cells),
        split=_normalize_split(payload.get("split")),
        imgid=payload.get("imgid"),
    )


def _normalize_split(value: object) -> Any:
    if value in ("train", "val", "test"):
        return value
    if value is None:
        return None
    msg = f"unknown split value {value!r}"
    raise ValueError(msg)


# ---------- IR → OTSL ----------


def _sample_to_payload(sample: TableSample) -> dict[str, Any]:
    tokens, cell_payloads = _sample_to_otsl_and_cells(sample)
    out: dict[str, Any] = {
        "filename": sample.filename,
        "otsl": tokens,
        "cells": cell_payloads,
    }
    if sample.split is not None:
        out["split"] = sample.split
    if sample.imgid is not None:
        out["imgid"] = sample.imgid
    return out


def _sample_to_otsl_and_cells(
    sample: TableSample,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Lay anchors back onto the grid (via _otslgrid) and flatten to tokens."""
    grid, emitted_order = build_token_grid(sample)

    tokens: list[str] = []
    for row in grid:
        tokens.extend(row)
        tokens.append("nl")

    cell_payloads: list[dict[str, Any]] = []
    for cell in emitted_order:
        payload: dict[str, Any] = {"tokens": list(cell.tokens)}
        if cell.bbox is not None:
            payload["bbox"] = list(cell.bbox)
        cell_payloads.append(payload)

    return tokens, cell_payloads
