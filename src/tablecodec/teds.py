"""TEDS (Tree-Edit-Distance based Similarity) for table samples.

TEDS scores the similarity of two tables in ``[0, 1]`` by the normalized
tree-edit distance between their HTML-DOM trees (Zhong et al., "Image-based
table recognition: data, model, and evaluation"). ``1.0`` means identical
structure and content; ``structure_only=True`` ignores cell text (TEDS-Struct).

This is the optional ``[teds]`` feature: it imports ``apted`` and ``lxml`` and
therefore lives OUTSIDE the zero-dependency core. It is never imported by
``tablecodec/__init__`` — use ``from tablecodec.teds import teds``.

Attribution: the tree construction, the rename-cost rule, and the
``1 - dist / max_nodes`` formula are adapted from IBM's PubTabNet reference
metric (``src/metric.py``, Apache License 2.0, Copyright 2020 IBM,
peter.zhong@au1.ibm.com). This is NOT a verbatim copy: the IR-native entry
point, a pure-Python normalized Levenshtein (replacing the ``distance``
package), and the removal of batching/parallelism are tablecodec's. See
``THIRD_PARTY_NOTICES.md`` and ``docs/adr/0011-teds-metric-port.md``.
"""

from __future__ import annotations

from typing import Any, cast

from apted import APTED, Config  # pyright: ignore[reportMissingTypeStubs]
from lxml import html  # pyright: ignore[reportMissingTypeStubs]

from tablecodec.ir import GridCell, TableSample

__all__ = ["teds", "teds_html"]


# ---------- normalized Levenshtein (pure stdlib; replaces `distance`) ----------


def _levenshtein(a: list[str], b: list[str]) -> int:
    """Edit distance between two token sequences."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def _normalized_distance(a: list[str], b: list[str]) -> float:
    """Levenshtein distance scaled to ``[0, 1]`` by the longer sequence."""
    longest = max(len(a), len(b))
    if longest == 0:
        return 0.0
    return _levenshtein(a, b) / longest


# ---------- apted tree + config (adapted from IBM PubTabNet metric.py) ----------


class _TableTree:
    """An apted tree node for one HTML table element."""

    def __init__(
        self,
        tag: str,
        colspan: int | None,
        rowspan: int | None,
        content: list[str] | None,
        *children: _TableTree,
    ) -> None:
        self.tag = tag
        self.colspan = colspan
        self.rowspan = rowspan
        self.content = content
        self.children: list[_TableTree] = list(children)

    def bracket(self) -> str:
        """Bracket notation used by apted for the tree's string form."""
        if self.tag == "td":
            result = f'"tag": {self.tag}, "colspan": {self.colspan}, "rowspan": {self.rowspan}, "text": {self.content}'
        else:
            result = f'"tag": {self.tag}'
        for child in self.children:
            result += child.bracket()
        return f"{{{result}}}"


class _CustomConfig(Config):
    def children(self, node: _TableTree) -> list[_TableTree]:
        return node.children

    # apted annotates rename as `-> int`, but TEDS uses fractional content
    # costs; apted sums costs as numbers, so a float is correct at runtime.
    def rename(self, node1: _TableTree, node2: _TableTree) -> float:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Cost of relabeling ``node1`` to ``node2``."""
        if (
            node1.tag != node2.tag
            or node1.colspan != node2.colspan
            or node1.rowspan != node2.rowspan
        ):
            return 1.0
        if node1.tag == "td" and (node1.content or node2.content):
            return _normalized_distance(node1.content or [], node2.content or [])
        return 0.0


# ---------- untyped third-party boundary (apted + lxml have no stubs) ----------
#
# apted and lxml ship no type information, so pyright (strict) cannot type the
# few lines that touch them. These thin wrappers confine that boundary: each
# returns a concretely-typed value, so the rest of the module is fully checked.


def _parse_first_table(doc: str) -> Any:
    """Parse `doc` and return its first ``body/table`` element, or ``None``."""
    parser = cast("Any", html.HTMLParser(remove_comments=True))
    root = cast("Any", html.fromstring(doc, parser=parser))  # pyright: ignore[reportUnknownMemberType]
    tables = cast("list[Any]", root.xpath("body/table"))
    return tables[0] if tables else None


def _count_descendant_elements(table: Any) -> int:
    """Number of element nodes below `table` (the TEDS denominator term)."""
    return len(cast("list[Any]", table.xpath(".//*")))


def _tree_edit_distance(tree1: _TableTree, tree2: _TableTree) -> float:
    raw = cast("Any", APTED(tree1, tree2, _CustomConfig()).compute_edit_distance())
    return float(raw)


# ---------- lxml element -> apted tree (adapted from IBM PubTabNet) ----------


def _tokenize(node: Any, tokens: list[str]) -> None:
    """Flatten an element into tokens: char-level text + tag markers."""
    tokens.append(f"<{node.tag}>")
    if node.text is not None:
        tokens.extend(list(node.text))
    for child in node:
        _tokenize(child, tokens)
    if node.tag != "unk":
        tokens.append(f"</{node.tag}>")
    if node.tag != "td" and node.tail is not None:
        tokens.extend(list(node.tail))


def _load_html_tree(node: Any, *, structure_only: bool) -> _TableTree:
    """Convert an lxml table element into the apted tree apted expects."""
    if node.tag == "td":
        if structure_only:
            content: list[str] = []
        else:
            tokens: list[str] = []
            _tokenize(node, tokens)
            content = tokens[1:-1]
        new_node = _TableTree(
            "td",
            int(node.attrib.get("colspan", "1")),
            int(node.attrib.get("rowspan", "1")),
            content,
        )
    else:
        new_node = _TableTree(str(node.tag), None, None, None)
        for child in node:
            new_node.children.append(_load_html_tree(child, structure_only=structure_only))
    return new_node


# ---------- IR -> HTML ----------


def _is_header_row(cells: list[GridCell]) -> bool:
    return any(cell.role == "header" for cell in cells)


def _cell_html(cell: GridCell) -> str:
    attrs = ""
    if cell.colspan != 1:
        attrs += f' colspan="{cell.colspan}"'
    if cell.rowspan != 1:
        attrs += f' rowspan="{cell.rowspan}"'
    return f"<td{attrs}>{''.join(cell.tokens)}</td>"


def _row_html(cells: list[GridCell]) -> str:
    inner = "".join(_cell_html(cell) for cell in sorted(cells, key=lambda c: c.col))
    return f"<tr>{inner}</tr>"


def _sample_to_html(sample: TableSample) -> str:
    """Render a sample as ``<html><body><table>...`` for TEDS.

    Cells are grouped by anchor row (HTML rowspan/colspan handle the rest);
    header rows go in ``<thead>``, body rows in ``<tbody>``. All cells render
    as ``<td>`` (PubTabNet convention) so the metric scores their content.
    """
    rows: dict[int, list[GridCell]] = {}
    for cell in sample.cells:
        rows.setdefault(cell.row, []).append(cell)

    header = [r for r in sorted(rows) if _is_header_row(rows[r])]
    body = [r for r in sorted(rows) if not _is_header_row(rows[r])]

    parts = ["<html><body><table>"]
    if header:
        parts.append("<thead>")
        parts.extend(_row_html(rows[r]) for r in header)
        parts.append("</thead>")
    if body:
        parts.append("<tbody>")
        parts.extend(_row_html(rows[r]) for r in body)
        parts.append("</tbody>")
    parts.append("</table></body></html>")
    return "".join(parts)


# ---------- public API ----------


def teds_html(pred_html: str, true_html: str, *, structure_only: bool = False) -> float:
    """TEDS between two HTML table documents.

    Each input is parsed; the first ``body/table`` is scored. Empty input or
    HTML with no table scores ``0.0`` (the canonical convention).
    """
    if not pred_html or not true_html:
        return 0.0
    pred_table = _parse_first_table(pred_html)
    true_table = _parse_first_table(true_html)
    if pred_table is None or true_table is None:
        return 0.0
    n_nodes = max(_count_descendant_elements(pred_table), _count_descendant_elements(true_table))
    if n_nodes == 0:
        return 1.0
    tree_pred = _load_html_tree(pred_table, structure_only=structure_only)
    tree_true = _load_html_tree(true_table, structure_only=structure_only)
    distance = _tree_edit_distance(tree_pred, tree_true)
    return 1.0 - distance / n_nodes


def teds(pred: TableSample, true: TableSample, *, structure_only: bool = False) -> float:
    """TEDS between two :class:`TableSample`s.

    Both samples are rendered to HTML with the same renderer, so the score is
    a well-defined similarity in ``[0, 1]`` regardless of their source codecs.
    """
    return teds_html(_sample_to_html(pred), _sample_to_html(true), structure_only=structure_only)
