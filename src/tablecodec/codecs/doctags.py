"""DocTags table subset codec.

DocTags (IBM Granite-Docling, 2026) is a document markup where tables are
encoded as OTSL cell tokens wrapped in ``<otsl>`` ... ``</otsl>``. Each
anchor cell is annotated with four ``<loc_n>`` tokens — a bounding box on
a fixed 0–500 grid — followed by the cell's content tokens. Continuation
tokens (``lcel`` / ``ucel`` / ``xcel``) carry neither loc nor content.

This codec handles the **table subset** of DocTags:

- read: full — structure (via the shared :mod:`._otslgrid`), bbox (from
  the loc tokens), and cell content.
- write: the OTSL-equivalent subset only (SPEC §7 marks this △). Header
  / body ``role`` has no representation in the OTSL core, so it is lost
  (``lossy_write`` declares ``role``); ``extras`` is also dropped.

Canonical jsonl record shape::

    {
        "filename": "...",
        "split": "train" | "val" | "test",  # optional
        "imgid": 0,  # optional
        "doctags": [
            "<otsl>",
            "fcel",
            "<loc_0>",
            "<loc_0>",
            "<loc_250>",
            "<loc_50>",
            "Year",
            ...,
            "nl",
            "</otsl>",
        ],
    }

Derived from the published DocTags / OTSL description, not copied from
upstream reference code.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import IO, Any, cast

from tablecodec.codecs._otslgrid import (
    ANCHOR_TOKENS,
    CELL_TOKENS,
    build_anchors,
    build_token_grid,
)
from tablecodec.ir import BBox, GridCell, TableSample

__all__ = ["DocTagsTablesCodec"]

_OTSL_OPEN = "<otsl>"
_OTSL_CLOSE = "</otsl>"
_LOC_RE = re.compile(r"^<loc_(\d+)>$")
_LOC_PER_BBOX = 4


@dataclass(frozen=True, slots=True)
class DocTagsTablesCodec:
    """Codec for the DocTags table subset (read full, write OTSL subset)."""

    name: str = "doctags-tables"
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
                msg = f"malformed DocTags record at line {line_no}: {exc}"
                raise ValueError(msg) from exc

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        for sample in samples:
            sink.write(json.dumps(_sample_to_payload(sample), ensure_ascii=False))
            sink.write("\n")

    def lossy_read(self) -> frozenset[str]:
        # The OTSL core has no header marker; role defaults to body.
        return frozenset({"role"})

    def lossy_write(self) -> frozenset[str]:
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
                return isinstance(payload, dict) and "doctags" in cast("dict[str, Any]", payload)
            return False
        finally:
            source.seek(pos)


# ---------- DocTags token stream parsing ----------


@dataclass(slots=True)
class _ParsedCell:
    """A structural cell token plus, for anchors, its bbox and content."""

    token: str
    bbox: BBox | None = None
    content: tuple[str, ...] = ()


def _initial_rows() -> list[list[str]]:
    return [[]]


def _empty_parsed_cells() -> list[_ParsedCell]:
    return []


@dataclass(slots=True)
class _StreamState:
    rows: list[list[str]] = field(default_factory=_initial_rows)
    anchors: list[_ParsedCell] = field(default_factory=_empty_parsed_cells)


def _parse_loc_run(tokens: list[str], start: int) -> tuple[BBox | None, int]:
    """Read up to four consecutive ``<loc_n>`` tokens from *start*.

    Returns (bbox or None, index after the loc run).
    """
    coords: list[int] = []
    j = start
    while j < len(tokens) and len(coords) < _LOC_PER_BBOX:
        m = _LOC_RE.match(tokens[j])
        if m is None:
            break
        coords.append(int(m.group(1)))
        j += 1
    if len(coords) == _LOC_PER_BBOX:
        return (coords[0], coords[1], coords[2], coords[3]), j
    return None, start  # not a full bbox; leave tokens for content


def _parse_content_run(tokens: list[str], start: int) -> tuple[tuple[str, ...], int]:
    """Read content tokens until the next structural / loc / nl / wrapper token."""
    content: list[str] = []
    j = start
    while j < len(tokens):
        tok = tokens[j]
        if tok in CELL_TOKENS or tok == "nl" or tok in (_OTSL_OPEN, _OTSL_CLOSE):
            break
        if _LOC_RE.match(tok) is not None:
            break
        content.append(tok)
        j += 1
    return tuple(content), j


def _parse_doctags_stream(tokens: list[str]) -> _StreamState:
    state = _StreamState()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in (_OTSL_OPEN, _OTSL_CLOSE):
            i += 1
        elif tok == "nl":
            state.rows.append([])
            i += 1
        elif tok in CELL_TOKENS:
            state.rows[-1].append(tok)
            if tok in ANCHOR_TOKENS:
                bbox, after_loc = _parse_loc_run(tokens, i + 1)
                content, after_content = _parse_content_run(tokens, after_loc)
                state.anchors.append(_ParsedCell(token=tok, bbox=bbox, content=content))
                i = after_content
            else:
                i += 1
        else:
            msg = f"unexpected DocTags token {tok!r}"
            raise ValueError(msg)
    if state.rows and not state.rows[-1]:
        state.rows.pop()
    return state


def _payload_to_sample(payload: dict[str, Any]) -> TableSample:
    tokens = list(payload["doctags"])
    state = _parse_doctags_stream(tokens)
    _nrows, _ncols, placements = build_anchors(state.rows)

    if len(placements) != len(state.anchors):
        msg = (
            f"DocTags declares {len(placements)} anchors but the stream parsed "
            f"{len(state.anchors)} cell contents"
        )
        raise ValueError(msg)

    cells = tuple(
        GridCell(
            row=placement.row,
            col=placement.col,
            rowspan=placement.rowspan,
            colspan=placement.colspan,
            tokens=parsed.content,
            bbox=parsed.bbox,
            role="body",
        )
        for placement, parsed in zip(placements, state.anchors, strict=True)
    )

    return TableSample(
        filename=str(payload["filename"]),
        nrows=_nrows,
        ncols=_ncols,
        cells=cells,
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


# ---------- IR → DocTags ----------


def _loc_tokens(bbox: BBox) -> list[str]:
    return [f"<loc_{v}>" for v in bbox]


def _sample_to_payload(sample: TableSample) -> dict[str, Any]:
    grid, anchored = build_token_grid(sample)
    by_pos = {(c.row, c.col): c for c in anchored}

    tokens: list[str] = [_OTSL_OPEN]
    for r, row in enumerate(grid):
        for c, structural in enumerate(row):
            tokens.append(structural)
            cell = by_pos.get((r, c))
            if cell is None:
                continue  # continuation token: no loc/content
            if cell.bbox is not None:
                tokens.extend(_loc_tokens(cell.bbox))
            tokens.extend(cell.tokens)
        tokens.append("nl")
    tokens.append(_OTSL_CLOSE)

    out: dict[str, Any] = {"filename": sample.filename, "doctags": tokens}
    if sample.split is not None:
        out["split"] = sample.split
    if sample.imgid is not None:
        out["imgid"] = sample.imgid
    return out
