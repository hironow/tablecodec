"""Shared HTML-token table machinery for codec implementations.

PubTabNet (1.x / 2.0) and FinTabNet (original) all encode table structure
as an HTML-like token stream (``<thead>``/``<tbody>``/``<tr>``/``<td>`` with
optional ``rowspan``/``colspan`` attributes) paired with a positional
``cells`` array. This module owns the parsing, grid placement, and
serialization so the concrete codecs stay thin and never duplicate it.

The only per-format knobs are:

- ``id_field``  — the record-level integer id key (``"imgid"`` for
  PubTabNet, ``"table_id"`` for FinTabNet).
- ``drop_bbox`` — discard per-cell bbox on read (PubTabNet 1.0).
- ``include_bbox`` — omit per-cell bbox on write (PubTabNet 1.0).

Stdlib-only (SPEC §13).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import IO, Any, Literal, cast

from tablecodec.ir import BBox, GridCell, TableSample

__all__ = [
    "looks_like_html_table",
    "parse_html_table",
    "serialize_html_table",
    "sniff_html_table",
]

_ROWSPAN_RE = re.compile(r'rowspan\s*=\s*"(\d+)"')
_COLSPAN_RE = re.compile(r'colspan\s*=\s*"(\d+)"')

_SECTION_TOKENS: dict[str, Literal["header", "body"] | None] = {
    "<thead>": "header",
    "</thead>": "body",
    "<tbody>": "body",
    "</tbody>": None,
}


# ---------- structure parser ----------


@dataclass(slots=True)
class _CellSpec:
    """One ``<td>`` opening parsed out of the structure token stream."""

    rowspan: int = 1
    colspan: int = 1
    role: Literal["header", "body"] = "body"
    row: int = -1  # assigned by the placement pass
    col: int = -1


def _empty_cell_spec_list() -> list[_CellSpec]:
    return []


@dataclass(slots=True)
class _ParseState:
    section: Literal["header", "body"] = "body"
    cur_row: int = -1
    cells: list[_CellSpec] = field(default_factory=_empty_cell_spec_list)


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
    """Parse HTML structure tokens into ordered cell specs."""
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


# ---------- payload -> sample ----------


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


def parse_html_table(
    payload: dict[str, Any], *, id_field: str = "imgid", drop_bbox: bool = False
) -> TableSample:
    """Build a :class:`TableSample` from an HTML-token table record."""
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
        bbox_raw = None if drop_bbox else cell_payload.get("bbox")
        bbox: BBox | None = None
        if bbox_raw is not None:
            bbox = (int(bbox_raw[0]), int(bbox_raw[1]), int(bbox_raw[2]), int(bbox_raw[3]))
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

    return TableSample(
        filename=str(payload["filename"]),
        nrows=nrows,
        ncols=ncols,
        cells=tuple(cells),
        split=_normalize_split(payload.get("split")),
        imgid=payload.get(id_field),
    )


# ---------- sample -> payload ----------


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


def _cell_to_payload(cell: GridCell, *, include_bbox: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {"tokens": list(cell.tokens)}
    if include_bbox and cell.bbox is not None:
        payload["bbox"] = list(cell.bbox)
    return payload


def _structure_and_cells(
    sample: TableSample, *, include_bbox: bool
) -> tuple[list[str], list[dict[str, Any]]]:
    by_row = _group_cells_by_row(sample.cells)
    header_rows = _count_header_rows(by_row, sample.nrows)
    structure: list[str] = []
    emitted_order: list[GridCell] = []
    _emit_section(
        structure, emitted_order, by_row, _SectionRange("<thead>", "</thead>", 0, header_rows)
    )
    _emit_section(
        structure,
        emitted_order,
        by_row,
        _SectionRange("<tbody>", "</tbody>", header_rows, sample.nrows),
    )
    return structure, [_cell_to_payload(c, include_bbox=include_bbox) for c in emitted_order]


def serialize_html_table(
    sample: TableSample, *, id_field: str = "imgid", include_bbox: bool = True
) -> dict[str, Any]:
    """Serialize a :class:`TableSample` to an HTML-token table record.

    ``extras`` is intentionally omitted (declared in the codec's
    ``lossy_write``).
    """
    structure_tokens, cell_payloads = _structure_and_cells(sample, include_bbox=include_bbox)
    payload: dict[str, Any] = {
        "filename": sample.filename,
        "html": {"structure": {"tokens": structure_tokens}, "cells": cell_payloads},
    }
    if sample.split is not None:
        payload["split"] = sample.split
    if sample.imgid is not None:
        payload[id_field] = sample.imgid
    return payload


# ---------- detection ----------


def _cells_list(html_dict: dict[str, Any]) -> list[object] | None:
    cells_field: object = html_dict.get("cells", [])
    if not isinstance(cells_field, list):
        return None
    return cast("list[object]", cells_field)


def _no_cell_has_bbox(html_dict: dict[str, Any]) -> bool:
    cells = _cells_list(html_dict)
    if cells is None:
        return False
    return not any(isinstance(c, dict) and "bbox" in c for c in cells)


def _all_cells_have_bbox(html_dict: dict[str, Any]) -> bool:
    cells = _cells_list(html_dict)
    if cells is None:
        return False
    return all(isinstance(c, dict) and "bbox" in c for c in cells)


def _bbox_constraint_ok(
    html_dict: dict[str, Any], *, require_no_bbox: bool, require_all_bbox: bool
) -> bool:
    if require_no_bbox:
        return _no_cell_has_bbox(html_dict)
    if require_all_bbox:
        return _all_cells_have_bbox(html_dict)
    return True


def looks_like_html_table(
    payload: object,
    *,
    require_no_bbox: bool = False,
    require_all_bbox: bool = False,
    require_field: str | None = None,
) -> bool:
    """Pure (no I/O) shape check for an HTML-token table record."""
    if not isinstance(payload, dict):
        return False
    payload_dict = cast("dict[str, Any]", payload)
    if require_field is not None and require_field not in payload_dict:
        return False
    html: object = payload_dict.get("html")
    if not isinstance(html, dict):
        return False
    html_dict = cast("dict[str, Any]", html)
    if "structure" not in html_dict or "cells" not in html_dict:
        return False
    return _bbox_constraint_ok(
        html_dict, require_no_bbox=require_no_bbox, require_all_bbox=require_all_bbox
    )


def sniff_html_table(
    source: IO[str],
    *,
    require_no_bbox: bool = False,
    require_all_bbox: bool = False,
    require_field: str | None = None,
) -> bool:
    """Peek the first non-blank line; verify it is an HTML-token table.

    Stream position is always restored.
    """
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
            return looks_like_html_table(
                payload,
                require_no_bbox=require_no_bbox,
                require_all_bbox=require_all_bbox,
                require_field=require_field,
            )
        return False
    finally:
        source.seek(pos)
