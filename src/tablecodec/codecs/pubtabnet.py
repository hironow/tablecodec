"""PubTabNet codecs.

This module hosts the ``pubtabnet-2.0.0`` codec. The ``pubtabnet-1.0.0``
(no-bbox) variant arrives in M3.

PubTabNet 2.0 jsonl record shape::

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

Structure tokens grammar (informally):
- ``<thead>`` / ``</thead>`` / ``<tbody>`` / ``</tbody>``: section markers.
- ``<tr>`` / ``</tr>``: row markers.
- ``<td>`` ... ``</td>``: a simple cell (rowspan = colspan = 1).
- ``<td``, `` rowspan="N"``, `` colspan="M"``, ``>`` ... ``</td>``: a cell
  with span attributes. Token-attribute order is consistent in the
  official corpus; we accept either order.

Cells line up positionally with ``html.cells`` (i-th opened ``<td>`` ↔
``cells[i]``). Empty cells omit ``bbox`` per the official corpus.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import IO, Any, Literal, cast

from tablecodec.ir import BBox, GridCell, TableSample

__all__ = ["PubTabNet20Codec"]


_ROWSPAN_RE = re.compile(r'rowspan\s*=\s*"(\d+)"')
_COLSPAN_RE = re.compile(r'colspan\s*=\s*"(\d+)"')


@dataclass(frozen=True, slots=True)
class PubTabNet20Codec:
    """Codec for the PubTabNet 2.0 jsonl format."""

    name: str = "pubtabnet-2.0.0"
    spec_version: str = "2.0.0"
    media_type: str = "application/jsonl"

    # ----- streaming read -----

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
                msg = f"malformed PubTabNet 2.0 record at line {line_no}: {exc}"
                raise ValueError(msg) from exc

    # ----- streaming write -----

    def write(self, samples: Iterable[TableSample], sink: IO[str]) -> None:
        for sample in samples:
            sink.write(json.dumps(_sample_to_payload(sample), ensure_ascii=False))
            sink.write("\n")

    # ----- self-declared loss -----

    def lossy_read(self) -> frozenset[str]:
        # PubTabNet 2.0 has no rich attribute model beyond what we keep
        # (filename, split, imgid, cell tokens, cell bbox, rowspan,
        # colspan, header/body section). Nothing dropped on read.
        return frozenset()

    def lossy_write(self) -> frozenset[str]:
        # IR ``extras`` has no canonical home in the PubTabNet schema and
        # is therefore dropped on write.
        return frozenset({"extras"})

    # ----- detection delegate (used by codecs.detect) -----

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
                if not isinstance(payload, dict):
                    return False
                payload_dict = cast("dict[str, Any]", payload)
                html: object = payload_dict.get("html")
                if not isinstance(html, dict):
                    return False
                html_dict = cast("dict[str, Any]", html)
                return "structure" in html_dict and "cells" in html_dict
            return False
        finally:
            source.seek(pos)


# ---------- structure parser ----------


@dataclass(slots=True)
class _CellSpec:
    """One ``<td>`` opening parsed out of the structure token stream."""

    rowspan: int = 1
    colspan: int = 1
    role: Literal["header", "body"] = "body"
    # Row index assigned by the placement pass.
    row: int = -1
    col: int = -1


def _empty_cell_spec_list() -> list[_CellSpec]:
    return []


@dataclass(slots=True)
class _ParseState:
    section: Literal["header", "body"] = "body"
    in_row: bool = False
    cur_row: int = -1
    cells: list[_CellSpec] = field(default_factory=_empty_cell_spec_list)
    pending: _CellSpec | None = None
    rows_started: int = 0


_SECTION_TOKENS: dict[str, Literal["header", "body"] | None] = {
    "<thead>": "header",
    "</thead>": "body",
    "<tbody>": "body",
    "</tbody>": None,
}


def _parse_span_attrs(tokens: list[str], start: int) -> tuple[int, int, int]:
    """Scan attribute tokens after ``<td`` until ``>``; return (rowspan, colspan, end_index)."""
    rowspan = colspan = 1
    j = start
    while j < len(tokens) and tokens[j] != ">":
        attr = tokens[j]
        if (m := _ROWSPAN_RE.search(attr)) is not None:
            rowspan = int(m.group(1))
        if (m := _COLSPAN_RE.search(attr)) is not None:
            colspan = int(m.group(1))
        j += 1
    return rowspan, colspan, j


def _parse_structure_tokens(tokens: list[str]) -> list[_CellSpec]:
    """Parse PubTabNet 2.0 structure tokens into ordered cell specs."""
    state = _ParseState()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in _SECTION_TOKENS:
            new_section = _SECTION_TOKENS[tok]
            if new_section is not None:
                state.section = new_section
        elif tok == "<tr>":
            state.cur_row += 1
        elif tok == "<td>":
            state.cells.append(_CellSpec(role=state.section, row=state.cur_row))
        elif tok == "<td":
            rowspan, colspan, end = _parse_span_attrs(tokens, i + 1)
            state.cells.append(
                _CellSpec(
                    rowspan=rowspan,
                    colspan=colspan,
                    role=state.section,
                    row=state.cur_row,
                )
            )
            i = end
        # </tr>, </td>, and unknown tokens are ignored.
        i += 1
    return state.cells


# ---------- grid placement ----------


def _empty_rows() -> list[list[bool]]:
    return []


@dataclass(slots=True)
class _OccupiedGrid:
    """Mutable 2D bitmap with grow-on-demand columns."""

    nrows: int
    ncols: int
    rows: list[list[bool]] = field(default_factory=_empty_rows)

    def __post_init__(self) -> None:
        self.rows = [[False] * self.ncols for _ in range(self.nrows)]

    def ensure_cols(self, want: int) -> None:
        if want > self.ncols:
            for row in self.rows:
                row.extend([False] * (want - self.ncols))
            self.ncols = want

    def can_place(self, r: int, c: int, rowspan: int, colspan: int) -> bool:
        return all(
            not self.rows[r + dr][c + dc]
            for dr in range(rowspan)
            for dc in range(colspan)
            if r + dr < self.nrows
        )

    def mark(self, r: int, c: int, rowspan: int, colspan: int) -> None:
        for dr in range(rowspan):
            rr = r + dr
            if rr >= self.nrows:
                continue
            for dc in range(colspan):
                self.rows[rr][c + dc] = True


def _place_cells(specs: list[_CellSpec]) -> tuple[int, int]:
    """Assign (row, col) to every spec using HTML table placement."""
    if not specs:
        return (0, 0)
    nrows = max(s.row for s in specs) + 1
    grid = _OccupiedGrid(nrows=nrows, ncols=max(8, sum(s.colspan for s in specs)))
    for spec in specs:
        c = 0
        while True:
            grid.ensure_cols(c + spec.colspan)
            if grid.can_place(spec.row, c, spec.rowspan, spec.colspan):
                break
            c += 1
        spec.col = c
        grid.mark(spec.row, c, spec.rowspan, spec.colspan)
    ncols = max((s.col + s.colspan for s in specs), default=0)
    return (nrows, ncols)


# ---------- payload <-> sample ----------


def _payload_to_sample(payload: dict[str, Any]) -> TableSample:
    html = payload["html"]
    structure_tokens = html["structure"]["tokens"]
    cell_payloads = html["cells"]

    specs = _parse_structure_tokens(structure_tokens)
    if len(specs) != len(cell_payloads):
        msg = f"structure declares {len(specs)} cells but cells[] has {len(cell_payloads)} entries"
        raise ValueError(msg)

    nrows, ncols = _place_cells(specs)

    cells: list[GridCell] = []
    for spec, cell_payload in zip(specs, cell_payloads, strict=True):
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
                row=spec.row,
                col=spec.col,
                rowspan=spec.rowspan,
                colspan=spec.colspan,
                tokens=tokens,
                bbox=bbox,
                role=spec.role,
            )
        )

    split_raw = payload.get("split")
    split: Literal["train", "val", "test"] | None = None
    if split_raw in ("train", "val", "test"):
        split = split_raw
    elif split_raw is not None:
        msg = f"unknown split value {split_raw!r}"
        raise ValueError(msg)

    return TableSample(
        filename=str(payload["filename"]),
        nrows=nrows,
        ncols=ncols,
        cells=tuple(cells),
        split=split,
        imgid=payload.get("imgid"),
    )


def _sample_to_payload(sample: TableSample) -> dict[str, Any]:
    structure_tokens, cell_payloads = _sample_to_structure_and_cells(sample)
    payload: dict[str, Any] = {
        "filename": sample.filename,
        "html": {
            "structure": {"tokens": structure_tokens},
            "cells": cell_payloads,
        },
    }
    if sample.split is not None:
        payload["split"] = sample.split
    if sample.imgid is not None:
        payload["imgid"] = sample.imgid
    # SPEC §6: lossy_write declares "extras" — therefore omitted here.
    return payload


def _group_cells_by_row(cells: tuple[GridCell, ...]) -> dict[int, list[GridCell]]:
    by_row: dict[int, list[GridCell]] = {}
    for cell in cells:
        by_row.setdefault(cell.row, []).append(cell)
    for row_cells in by_row.values():
        row_cells.sort(key=lambda c: c.col)
    return by_row


def _count_header_rows(by_row: dict[int, list[GridCell]], nrows: int) -> int:
    header_rows = 0
    while header_rows < nrows:
        row_cells = by_row.get(header_rows, [])
        if not row_cells or not all(c.role == "header" for c in row_cells):
            break
        header_rows += 1
    return header_rows


@dataclass(slots=True)
class _SectionRange:
    open_tag: str
    close_tag: str
    start: int
    end: int


def _emit_section(
    structure: list[str],
    emitted: list[GridCell],
    by_row: dict[int, list[GridCell]],
    span: _SectionRange,
) -> None:
    if span.start >= span.end:
        return
    structure.append(span.open_tag)
    for r in range(span.start, span.end):
        _emit_row(structure, emitted, by_row.get(r, []))
    structure.append(span.close_tag)


def _cell_to_payload(cell: GridCell) -> dict[str, Any]:
    payload: dict[str, Any] = {"tokens": list(cell.tokens)}
    if cell.bbox is not None:
        payload["bbox"] = list(cell.bbox)
    return payload


def _sample_to_structure_and_cells(
    sample: TableSample,
) -> tuple[list[str], list[dict[str, Any]]]:
    by_row = _group_cells_by_row(sample.cells)
    header_rows = _count_header_rows(by_row, sample.nrows)

    structure: list[str] = []
    emitted_order: list[GridCell] = []
    _emit_section(
        structure,
        emitted_order,
        by_row,
        _SectionRange("<thead>", "</thead>", 0, header_rows),
    )
    _emit_section(
        structure,
        emitted_order,
        by_row,
        _SectionRange("<tbody>", "</tbody>", header_rows, sample.nrows),
    )

    return structure, [_cell_to_payload(c) for c in emitted_order]


def _emit_row(structure: list[str], emitted: list[GridCell], row_cells: list[GridCell]) -> None:
    structure.append("<tr>")
    for cell in row_cells:
        if cell.rowspan == 1 and cell.colspan == 1:
            structure.extend(["<td>", "</td>"])
        else:
            structure.append("<td")
            if cell.rowspan != 1:
                structure.append(f' rowspan="{cell.rowspan}"')
            if cell.colspan != 1:
                structure.append(f' colspan="{cell.colspan}"')
            structure.extend([">", "</td>"])
        emitted.append(cell)
    structure.append("</tr>")
