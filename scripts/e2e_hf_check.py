#!/usr/bin/env python3
"""End-to-end check: stream real table-recognition datasets through tablecodec.

Occasional / local-only (see docs/adr/0003). For each streamed row this
builds the input of a target codec, runs the *actual* ``codec.read()``,
and validates the resulting IR — so the risky logic (square-table
assumption, anchor/cell alignment, HTML structure parsing) is exercised
against real tables.

Sources: the Docling OTSL family (uniform converted schema across
PubTabNet / FinTabNet / PubTables-1M / SynthTabNet) plus the native
first-published PubTabNet annotation via apoidea/pubtabnet-html.

Usage:
    # network-free smoke test of the adapters through the real codecs
    python scripts/e2e_hf_check.py --self-test

    # live run (needs the [hf] extra + network); sample 200 rows per check
    python scripts/e2e_hf_check.py --limit 200
    python scripts/e2e_hf_check.py --dataset FinTabNet_OTSL --limit 50
    python scripts/e2e_hf_check.py --limit 0           # full sweep (huge)

The live path imports ``datasets`` lazily so ``--self-test`` and
``--list`` work without the [hf] extra installed.
"""

from __future__ import annotations

import argparse
import ast
import functools
import importlib.util
import io
import json
import logging
import os
import random
import sys
import tarfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO as IOType
from typing import Any

# Quiet the Hugging Face stack BEFORE `datasets` is imported (env vars are
# read at import time). Keeps the e2e output to our own summary lines.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("DATASETS_VERBOSITY", "error")

from tablecodec import __version__, profiles, validate
from tablecodec.codecs._base import Codec
from tablecodec.codecs._otslgrid import build_anchors, otsl_to_cells, split_rows
from tablecodec.codecs.doctags import DocTagsTablesCodec
from tablecodec.codecs.fintabnet import FinTabNetCodec
from tablecodec.codecs.fintabnet_otsl import FinTabNetOTSLCodec
from tablecodec.codecs.otsl import OTSL10Codec
from tablecodec.codecs.pubtables1m import PubTables1MCodec
from tablecodec.codecs.pubtabnet import PubTabNet10Codec, PubTabNet20Codec
from tablecodec.codecs.tablebank import TableBankCodec
from tablecodec.codecs.tableformer import TableFormerCodec
from tablecodec.ir import TableSample


def _silence_hf_logging() -> None:
    """Raise log levels of the HF / network stack to ERROR (hide retries)."""
    for name in ("datasets", "huggingface_hub", "urllib3", "fsspec", "filelock"):
        logging.getLogger(name).setLevel(logging.ERROR)
    try:
        import datasets

        datasets.disable_progress_bars()
        datasets.utils.logging.set_verbosity_error()
    except (ImportError, AttributeError):
        pass


# ---------- Docling row -> canonical codec payload ----------


def flatten_cells(nested: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Flatten Docling's row-grouped cells into a single row-major list.

    Docling stores ``cells`` as ``List[List[{tokens, bbox}]]`` (one inner
    list per table row). The OTSL / HTML codecs expect a flat, row-major
    ``cells[]`` aligned with the structure's anchor order.
    """
    flat: list[dict[str, Any]] = []
    for row in nested:
        flat.extend(row)
    return flat


def docling_to_otsl_payload(row: dict[str, Any], *, id_key: str = "imgid") -> dict[str, Any]:
    # id_key lets us target codecs whose record uses a different id field
    # (otsl-1.0.0 / fintabnet-otsl read "imgid"/"table_id" respectively),
    # bridging the Docling-always-"imgid" convention to each codec.
    return {
        "filename": row.get("filename", "<docling>"),
        "split": row.get("split"),
        id_key: row.get("imgid"),
        "otsl": list(row["otsl"]),
        "cells": flatten_cells(row["cells"]),
    }


def docling_to_html_payload(row: dict[str, Any], *, id_key: str = "imgid") -> dict[str, Any]:
    return {
        "filename": row.get("filename", "<docling>"),
        "split": row.get("split"),
        id_key: row.get("imgid"),
        "html": {
            "structure": {"tokens": list(row["html"])},
            "cells": flatten_cells(row["cells"]),
        },
    }


def docling_to_tablebank_payload(row: dict[str, Any]) -> dict[str, Any]:
    # TableBank ships structure only (no cells). We feed the HTML
    # structure tokens and omit cells — a faithful field-mapping.
    return {
        "filename": row.get("filename", "<docling>"),
        "split": row.get("split"),
        "imgid": row.get("imgid"),
        "html": {"structure": {"tokens": list(row["html"])}},
    }


def _bbox4(bbox: Any) -> list[int] | None:
    if isinstance(bbox, list) and len(bbox) >= 4:
        return [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]
    return None


def docling_to_pubtables1m_payload(row: dict[str, Any]) -> dict[str, Any]:
    # PubTables-1M is object-detection: explicit row/col per cell. Docling
    # has no per-cell grid coords, so we DERIVE them from the OTSL anchor
    # placement (real bbox/tokens, derived coordinates — mild circularity,
    # documented in ADR 0003). A structure/cell-count mismatch raises and
    # is recorded as a parse_error.
    nrows, ncols, anchors = build_anchors(split_rows(list(row["otsl"])))
    flat = flatten_cells(row["cells"])
    if len(anchors) != len(flat):
        msg = f"anchor/cell count mismatch: {len(anchors)} vs {len(flat)}"
        raise ValueError(msg)
    cells = [
        {
            "row": a.row,
            "col": a.col,
            "rowspan": a.rowspan,
            "colspan": a.colspan,
            "tokens": list(cell.get("tokens", [])),
            "bbox": _bbox4(cell.get("bbox")),
        }
        for a, cell in zip(anchors, flat, strict=True)
    ]
    return {
        "filename": row.get("filename", "<docling>"),
        "split": row.get("split"),
        "imgid": row.get("imgid"),
        "nrows": nrows,
        "ncols": ncols,
        "cells": cells,
    }


def docling_to_doctags_payload(row: dict[str, Any]) -> dict[str, Any]:
    # DocTags has no public GT dataset (it is a model OUTPUT format). We
    # reconstruct the table from the real Docling content (otsl + cells)
    # and serialize it via the DocTags codec, then the check reads it back
    # — a real-content round-trip (write→read), documented in ADR 0003.
    nrows, ncols, cells = otsl_to_cells(list(row["otsl"]), flatten_cells(row["cells"]))
    sample = TableSample(
        filename=row.get("filename", "<docling>"),
        nrows=nrows,
        ncols=ncols,
        cells=cells,
        imgid=row.get("imgid"),
    )
    sink = io.StringIO()
    DocTagsTablesCodec().write([sample], sink)
    # write() emits exactly one JSON record (+ trailing newline). Parse the
    # whole buffer, NOT splitlines()[0]: str.splitlines() also breaks on
    # Unicode line separators (U+2028/U+2029/U+0085) that a cell token may
    # contain and that json.dumps(ensure_ascii=False) leaves raw — which
    # would slice the record mid-string. json.loads ignores trailing space.
    payload: dict[str, Any] = json.loads(sink.getvalue())
    return payload


# ---------- native (first-published) row -> codec payload ----------


def _parse_struct(value: Any) -> dict[str, Any]:
    """Parse a serialized ``{cells, structure}`` blob into a dict.

    ``apoidea/pubtabnet-html`` stores the original PubTabNet ``html``
    annotation as a string column. In practice it is a Python ``repr``
    (single-quoted), not JSON, so ``json.loads`` fails; we fall back to
    ``ast.literal_eval``, which parses Python *literals only* (no name
    lookup, no calls, no code execution) and raises on anything else. The
    Datasets viewer may also hand back an already-parsed mapping. A value
    that is neither yields a recorded parse_error rather than a silent
    coercion.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = ast.literal_eval(value)
        if not isinstance(parsed, dict):
            msg = f"html parsed to {type(parsed).__name__}, expected dict"
            raise TypeError(msg)
        return parsed
    msg = f"unexpected html field type: {type(value).__name__}"
    raise TypeError(msg)


def apoidea_to_pubtabnet_payload(row: dict[str, Any]) -> dict[str, Any]:
    # apoidea/pubtabnet-html is the ORIGINAL PubTabNet 2.0 annotation (the
    # first-published dataset for the pubtabnet codecs): its `html` column
    # is the exact value of the upstream jsonl `html` field — the native
    # {cells:[{tokens,bbox}], structure:{tokens}} shape the codec reads.
    # No structural reshaping: we only wrap it back into a record.
    html = _parse_struct(row["html"])
    imgid = row.get("imgid")
    return {
        "filename": f"{imgid}.png" if imgid is not None else "<apoidea>",
        "split": row.get("split"),
        "imgid": imgid,
        "html": html,
    }


# ---------- native PubTables-1M (PASCAL VOC) -> pubtables-1m payload ----------

_VocBox = tuple[float, float, float, float]


def _voc_objects(xml: str) -> list[tuple[str, _VocBox]]:
    # defusedxml is imported lazily so --self-test runs on a bare interpreter
    # (it lives in the [hf] extra alongside datasets); parsing is hardened
    # against entity/DTD/external-reference attacks by defusedxml's defaults.
    from defusedxml.ElementTree import fromstring

    root = fromstring(xml)
    out: list[tuple[str, _VocBox]] = []
    for obj in root.findall("object"):
        name_el = obj.find("name")
        bnd = obj.find("bndbox")
        if name_el is None or name_el.text is None or bnd is None:
            continue
        coords = tuple(
            float(bnd.find(t).text or 0) if bnd.find(t) is not None else 0.0
            for t in ("xmin", "ymin", "xmax", "ymax")
        )
        out.append((name_el.text, (coords[0], coords[1], coords[2], coords[3])))
    return out


def _in(value: float, lo: float, hi: float) -> bool:
    return lo <= value <= hi


def _voc_owners(
    rows: list[_VocBox], cols: list[_VocBox], spanning: list[_VocBox], proj: list[_VocBox]
) -> dict[tuple[int, int], int]:
    # Map every base grid cell (i, j) to the spanning region (if any) that
    # contains its centre. Projected row headers span all columns and get a
    # synthetic per-row group id so they collapse to one wide cell.
    owner: dict[tuple[int, int], int] = {}
    for gid, span in enumerate(spanning):
        for i, rb in enumerate(rows):
            for j, cb in enumerate(cols):
                if _in((cb[0] + cb[2]) / 2, span[0], span[2]) and _in(
                    (rb[1] + rb[3]) / 2, span[1], span[3]
                ):
                    owner[(i, j)] = gid
    for i, rb in enumerate(rows):
        if any(_in((rb[1] + rb[3]) / 2, p[1], p[3]) for p in proj):
            for j in range(len(cols)):
                owner.setdefault((i, j), 1_000_000 + i)
    return owner


def _voc_cell(
    r: int, c: int, rs: int, cs: int, rows: list[_VocBox], cols: list[_VocBox], *, header: bool
) -> dict[str, Any]:
    return {
        "row": r,
        "col": c,
        "rowspan": rs,
        "colspan": cs,
        "tokens": [],
        "bbox": [
            int(cols[c][0]),
            int(rows[r][1]),
            int(cols[c + cs - 1][2]),
            int(rows[r + rs - 1][3]),
        ],
        "role": "header" if header else "body",
    }


def voc_to_pubtables1m_payload(row: dict[str, Any]) -> dict[str, Any]:
    # Native PubTables-1M structure annotation is PASCAL VOC object detection
    # (geometric row / column / spanning-cell / header regions, NO grid
    # indices). Reconstruct the logical grid: rows x columns intersection,
    # merge cells whose centres fall inside a spanning region, mark
    # column-header rows. tokens are empty (VOC carries no cell content).
    objs = _voc_objects(row["xml"])
    rows = sorted((b for n, b in objs if n == "table row"), key=lambda b: b[1])
    cols = sorted((b for n, b in objs if n == "table column"), key=lambda b: b[0])
    if not rows or not cols:
        msg = f"degenerate VOC grid {len(rows)}x{len(cols)}"
        raise ValueError(msg)
    headers = [b for n, b in objs if n == "table column header"]
    proj = [b for n, b in objs if n == "table projected row header"]
    spanning = [b for n, b in objs if n == "table spanning cell"]
    header_rows = {
        i for i, rb in enumerate(rows) if any(_in((rb[1] + rb[3]) / 2, h[1], h[3]) for h in headers)
    }
    owner = _voc_owners(rows, cols, spanning, proj)
    cells: list[dict[str, Any]] = []
    seen: set[int] = set()
    for i in range(len(rows)):
        for j in range(len(cols)):
            gid = owner.get((i, j))
            if gid is None:
                cells.append(_voc_cell(i, j, 1, 1, rows, cols, header=i in header_rows))
            elif gid not in seen:
                seen.add(gid)
                members = [k for k, g in owner.items() if g == gid]
                r0, c0 = min(m[0] for m in members), min(m[1] for m in members)
                r1, c1 = max(m[0] for m in members), max(m[1] for m in members)
                cells.append(
                    _voc_cell(
                        r0, c0, r1 - r0 + 1, c1 - c0 + 1, rows, cols, header=r0 in header_rows
                    )
                )
    return {
        "filename": row.get("filename", "<voc>"),
        "imgid": row.get("imgid"),
        "nrows": len(rows),
        "ncols": len(cols),
        "cells": cells,
    }


# ---------- check registry ----------


@dataclass(frozen=True, slots=True)
class Check:
    dataset: str
    split: str
    codec: Codec
    to_payload: Callable[[dict[str, Any]], dict[str, Any]]
    # When set, rows are read from a local tar.gz under input/ (members
    # matching local_suffix) instead of streamed from the HF hub. Used for
    # the download-only native datasets (e.g. PubTables-1M PASCAL VOC) whose
    # archives the Datasets viewer does not expose.
    local_tar: str | None = None
    local_suffix: str = ".xml"

    @property
    def label(self) -> str:
        short = self.dataset.split("/")[-1]
        return f"{short}[{self.split}] -> {self.codec.name}"


_OTSL = OTSL10Codec()
_PUBTABNET20 = PubTabNet20Codec()
_PUBTABNET10 = PubTabNet10Codec()
_FINTABNET = FinTabNetCodec()
_FINTABNET_OTSL = FinTabNetOTSLCodec()
_TABLEFORMER = TableFormerCodec()
_TABLEBANK = TableBankCodec()
_PUBTABLES1M = PubTables1MCodec()
_DOCTAGS = DocTagsTablesCodec()

# FinTabNet codecs read "table_id"; Docling rows carry "imgid" → bridge it.
_otsl_table_id = functools.partial(docling_to_otsl_payload, id_key="table_id")
_html_table_id = functools.partial(docling_to_html_payload, id_key="table_id")

# Every shipped codec is exercised against at least one official corpus
# (PubTabNet / FinTabNet / PubTables-1M / SynthTabNet via the Docling OTSL
# family). Most are direct field-mappings; pubtables-1m derives grid coords
# from OTSL placement and doctags-tables is a real-content round-trip — see
# the adapter docstrings and ADR 0003 for the honesty caveats.
#
# The pubtabnet codecs additionally read their FIRST-PUBLISHED dataset in
# its NATIVE shape via apoidea/pubtabnet-html (the original PubTabNet 2.0
# `html` annotation, not the Docling OTSL conversion). pubtables-1m also
# reads its NATIVE PASCAL VOC annotation (object-detection geometry, grid
# reconstructed) from a local tar under input/ (download-only; see
# README + ADR 0004). FinTabNet / TableBank natives remain download-only
# and Docling-covered.
_PUBTABLES1M_VOC_TAR = "input/pubtables-1m/PubTables-1M-Structure_Annotations_Val.tar.gz"

CHECKS: tuple[Check, ...] = (
    Check("docling-project/PubTabNet_OTSL", "val", _OTSL, docling_to_otsl_payload),
    Check("docling-project/PubTabNet_OTSL", "val", _PUBTABNET20, docling_to_html_payload),
    Check("docling-project/PubTabNet_OTSL", "val", _PUBTABNET10, docling_to_html_payload),
    Check("docling-project/PubTabNet_OTSL", "val", _TABLEBANK, docling_to_tablebank_payload),
    Check("docling-project/PubTabNet_OTSL", "val", _DOCTAGS, docling_to_doctags_payload),
    # Native first-published PubTabNet (original annotation, not OTSL).
    Check("apoidea/pubtabnet-html", "validation", _PUBTABNET20, apoidea_to_pubtabnet_payload),
    Check("apoidea/pubtabnet-html", "validation", _PUBTABNET10, apoidea_to_pubtabnet_payload),
    Check("docling-project/FinTabNet_OTSL", "test", _OTSL, docling_to_otsl_payload),
    Check("docling-project/FinTabNet_OTSL", "test", _PUBTABNET20, docling_to_html_payload),
    Check("docling-project/FinTabNet_OTSL", "test", _FINTABNET_OTSL, _otsl_table_id),
    Check("docling-project/FinTabNet_OTSL", "test", _FINTABNET, _html_table_id),
    Check("docling-project/FinTabNet_OTSL", "test", _TABLEFORMER, docling_to_html_payload),
    Check("docling-project/PubTables-1M_OTSL", "val", _OTSL, docling_to_otsl_payload),
    Check("docling-project/PubTables-1M_OTSL", "val", _PUBTABLES1M, docling_to_pubtables1m_payload),
    # Native first-published PubTables-1M (PASCAL VOC, local download).
    Check(
        "bsmock/pubtables-1m",
        "val",
        _PUBTABLES1M,
        voc_to_pubtables1m_payload,
        local_tar=_PUBTABLES1M_VOC_TAR,
        local_suffix=".xml",
    ),
    Check("docling-project/SynthTabNet_OTSL", "val", _OTSL, docling_to_otsl_payload),
)


# ---------- running a check ----------


@dataclass(slots=True)
class Report:
    label: str
    rows: int = 0
    ok: int = 0
    parse_errors: int = 0
    validation_failures: int = 0
    examples: list[str] = field(default_factory=list)

    def note(self, msg: str) -> None:
        if len(self.examples) < 5:
            self.examples.append(msg)


_RECORD_README = """\
# E2E findings — for later verification

Each `run-*.jsonl` file holds one JSON object per FAILED row from a
`scripts/e2e_hf_check.py` run. A "failure" is either a codec parse error
or a validation finding. **A finding is NOT proof of a library bug** —
it may be (a) our implementation, (b) a malformed upstream row, or
(c) an over-strict / mistaken invariant. `verdict` is always
`needs-review`; investigate before concluding.

## Record fields

- `dataset`, `split`, `codec`, `profile`, `seed`, `row_index`,
  `shuffle_buffer`: provenance — re-running with the same `seed` +
  `shuffle_buffer` reaches the same `row_index`.
- `kind`: `parse_error` | `validation_failure`.
- `invariant`, `cell_index`, `message`: the finding detail.
- `provenance`: upstream `filename` / `imgid` (trace back to the source).
- `offending_cell`: the cell the finding points at (when cell-scoped).
- `input_payload`: the EXACT dict fed to `codec.read()` — replay it.

## Replay a finding

```python
import io, json
from tablecodec import profiles, validate
from tablecodec.codecs.<module> import <Codec>   # match record["codec"]

rec = json.loads(open("run-XXationXX.jsonl").readline())
sample = next(iter(<Codec>().read(io.StringIO(json.dumps(rec["input_payload"])))))
print(validate(sample, profile=getattr(profiles, rec["profile"])))
```

If `validate(...)` returns the same finding, decide: is the upstream
`input_payload` genuinely malformed (data bug), or is the invariant
wrong (library bug)? Record the conclusion alongside this file.
"""


@dataclass(slots=True)
class FindingsRecorder:
    """Append failed-row records (JSONL) under output/ for later audit."""

    path: Path
    seed: int | None
    shuffle_buffer: int
    profile_name: str
    enabled: bool = True
    _fh: IOType[str] | None = field(default=None, init=False)
    written: int = field(default=0, init=False)

    def _ensure_open(self) -> IOType[str]:
        if self._fh is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            readme = self.path.parent / "README.md"
            if not readme.exists():
                readme.write_text(_RECORD_README, encoding="utf-8")
            self._fh = self.path.open("w", encoding="utf-8")
        return self._fh

    def record(self, finding: dict[str, Any]) -> None:
        if not self.enabled:
            return
        fh = self._ensure_open()
        fh.write(json.dumps(finding, ensure_ascii=False) + "\n")
        fh.flush()
        self.written += 1

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def _provenance(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": payload.get("filename"),
        "imgid": payload.get("imgid"),
        "table_id": payload.get("table_id"),
    }


def _check_row(
    check: Check,
    row: dict[str, Any],
    row_index: int,
    profile: Any,
    report: Report,
    recorder: FindingsRecorder,
) -> None:
    report.rows += 1
    payload: dict[str, Any] | None = None
    try:
        payload = check.to_payload(row)
        line = json.dumps(payload, ensure_ascii=False)
        sample = next(iter(check.codec.read(io.StringIO(line))))
    except (KeyError, ValueError, TypeError, StopIteration) as exc:
        report.parse_errors += 1
        report.note(f"parse: {type(exc).__name__}: {exc}")
        recorder.record(
            _build_record(
                check,
                row_index,
                recorder,
                kind="parse_error",
                message=f"{type(exc).__name__}: {exc}",
                payload=payload,
            )
        )
        return
    errors = validate(sample, profile=profile)
    if errors:
        report.validation_failures += 1
        first = errors[0]
        report.note(f"validate: {first.invariant}: {first.message}")
        offending = None
        if first.cell_index is not None and payload is not None:
            cells = payload.get("cells") or payload.get("html", {}).get("cells")
            if isinstance(cells, list) and 0 <= first.cell_index < len(cells):
                offending = cells[first.cell_index]
        recorder.record(
            _build_record(
                check,
                row_index,
                recorder,
                kind="validation_failure",
                message=first.message,
                payload=payload,
                invariant=first.invariant,
                cell_index=first.cell_index,
                offending_cell=offending,
            )
        )
    else:
        report.ok += 1


def _build_record(
    check: Check,
    row_index: int,
    recorder: FindingsRecorder,
    *,
    kind: str,
    message: str,
    payload: dict[str, Any] | None,
    invariant: str | None = None,
    cell_index: int | None = None,
    offending_cell: Any = None,
) -> dict[str, Any]:
    return {
        "schema": "tablecodec-e2e-finding/1",
        "timestamp": datetime.now(UTC).isoformat(),
        "tablecodec_version": __version__,
        "dataset": check.dataset,
        "split": check.split,
        "codec": check.codec.name,
        "profile": recorder.profile_name,
        "seed": recorder.seed,
        "shuffle_buffer": recorder.shuffle_buffer,
        "row_index": row_index,
        "kind": kind,
        "invariant": invariant,
        "cell_index": cell_index,
        "message": message,
        "verdict": "needs-review",
        "provenance": _provenance(payload) if payload else {},
        "offending_cell": offending_cell,
        "input_payload": payload,
    }


def _run_local_tar(
    check: Check,
    limit: int,
    profile: Any,
    recorder: FindingsRecorder,
    *,
    seed: int | None,
) -> Report:
    """Iterate XML members of a local tar.gz (download-only native datasets)."""
    report = Report(label=check.label)
    tar_path = Path(check.local_tar or "")
    if not tar_path.exists():
        report.note(f"missing local archive: {tar_path} (download it first)")
        report.parse_errors += 1
        return report
    with tarfile.open(tar_path, "r:gz") as tar:
        names = [m.name for m in tar.getmembers() if m.name.endswith(check.local_suffix)]
    if seed is not None:
        random.Random(seed).shuffle(names)
    chosen = set(names[:limit] if limit else names)
    with tarfile.open(tar_path, "r:gz") as tar:
        i = 0
        for member in tar:
            if member.name not in chosen:
                continue
            fobj = tar.extractfile(member)
            if fobj is None:
                continue
            xml = fobj.read().decode("utf-8", errors="replace")
            row = {"xml": xml, "filename": Path(member.name).name, "imgid": None}
            _check_row(check, row, i, profile, report, recorder)
            i += 1
    return report


def run_check(
    check: Check,
    limit: int,
    profile: Any,
    recorder: FindingsRecorder,
    *,
    seed: int | None = None,
    shuffle_buffer: int = 1000,
) -> Report:
    if check.local_tar is not None:
        return _run_local_tar(check, limit, profile, recorder, seed=seed)

    from datasets import Image, load_dataset  # lazy: only needed for live runs

    _silence_hf_logging()
    report = Report(label=check.label)
    stream = load_dataset(check.dataset, split=check.split, streaming=True)
    # Turn off image decoding so `datasets` does not require Pillow — we
    # only read the textual structure / cells, never the image bytes.
    try:
        stream = stream.cast_column("image", Image(decode=False))
    except (ValueError, KeyError):
        pass  # no image column in this dataset
    # Random sampling: shuffle() also reshuffles shard order, so repeated
    # runs with different seeds sample different regions of the (huge)
    # dataset — approximating full coverage over many runs. seed=None
    # disables shuffling for a deterministic head-of-stream read.
    if seed is not None:
        stream = stream.shuffle(seed=seed, buffer_size=shuffle_buffer)
    for i, row in enumerate(stream):
        if limit and i >= limit:
            break
        _check_row(check, row, i, profile, report, recorder)
    return report


# ---------- self-test (no network) ----------


def _synthetic_docling_row() -> dict[str, Any]:
    """A row shaped like the Docling OTSL schema (2x2 table, header row)."""
    return {
        "filename": "synthetic.png",
        "split": "val",
        "imgid": 1,
        "dataset": "PubTabNet",
        "otsl": ["fcel", "fcel", "nl", "fcel", "fcel", "nl"],
        "html": [
            "<thead>",
            "<tr>",
            "<td>",
            "</td>",
            "<td>",
            "</td>",
            "</tr>",
            "</thead>",
            "<tbody>",
            "<tr>",
            "<td>",
            "</td>",
            "<td>",
            "</td>",
            "</tr>",
            "</tbody>",
        ],
        "cells": [
            [{"tokens": ["a"], "bbox": [0, 0, 10, 5]}, {"tokens": ["b"], "bbox": [10, 0, 20, 5]}],
            [{"tokens": ["c"], "bbox": [0, 5, 10, 10]}, {"tokens": ["d"], "bbox": [10, 5, 20, 10]}],
        ],
        "cols": 2,
        "rows": 2,
    }


def _synthetic_apoidea_row() -> dict[str, Any]:
    """A row shaped like apoidea/pubtabnet-html (native PubTabNet `html`)."""
    html = {
        "structure": {
            "tokens": [
                "<thead>",
                "<tr>",
                "<td>",
                "</td>",
                "<td>",
                "</td>",
                "</tr>",
                "</thead>",
                "<tbody>",
                "<tr>",
                "<td>",
                "</td>",
                "<td>",
                "</td>",
                "</tr>",
                "</tbody>",
            ]
        },
        "cells": [
            {"tokens": ["a"], "bbox": [0, 0, 10, 5]},
            {"tokens": ["b"], "bbox": [10, 0, 20, 5]},
            {"tokens": ["c"], "bbox": [0, 5, 10, 10]},
            {"tokens": ["d"], "bbox": [10, 5, 20, 10]},
        ],
    }
    return {"split": "val", "imgid": 7, "html": json.dumps(html), "html_table": "<html></html>"}


def _synthetic_voc_row() -> dict[str, Any]:
    """A row shaped like PubTables-1M VOC (2x2, header on row 0)."""
    xml = (
        "<annotation><size><width>20</width><height>10</height></size>"
        "<object><name>table</name><bndbox><xmin>0</xmin><ymin>0</ymin>"
        "<xmax>20</xmax><ymax>10</ymax></bndbox></object>"
        "<object><name>table row</name><bndbox><xmin>0</xmin><ymin>0</ymin>"
        "<xmax>20</xmax><ymax>5</ymax></bndbox></object>"
        "<object><name>table row</name><bndbox><xmin>0</xmin><ymin>5</ymin>"
        "<xmax>20</xmax><ymax>10</ymax></bndbox></object>"
        "<object><name>table column</name><bndbox><xmin>0</xmin><ymin>0</ymin>"
        "<xmax>10</xmax><ymax>10</ymax></bndbox></object>"
        "<object><name>table column</name><bndbox><xmin>10</xmin><ymin>0</ymin>"
        "<xmax>20</xmax><ymax>10</ymax></bndbox></object>"
        "<object><name>table column header</name><bndbox><xmin>0</xmin><ymin>0</ymin>"
        "<xmax>20</xmax><ymax>5</ymax></bndbox></object></annotation>"
    )
    return {"xml": xml, "filename": "synthetic.xml", "imgid": None}


def _synthetic_row_for(check: Check) -> dict[str, Any]:
    if check.local_tar is not None:
        return _synthetic_voc_row()
    if check.dataset.startswith("apoidea/"):
        return _synthetic_apoidea_row()
    return _synthetic_docling_row()


def self_test() -> int:
    """Drive every registered check's adapter on a synthetic row (no network).

    Proves each (codec, adapter) wiring in CHECKS reads its adapted form of
    a shape-matched synthetic row and the resulting IR passes DEFAULT — so
    the e2e coverage map (native PubTabNet + native PubTables-1M VOC
    included) is wired. Local (download-only) checks need the `[hf]` extra's
    defusedxml; they are skipped with a note when it is absent.
    """
    profile = profiles.DEFAULT
    recorder = FindingsRecorder(
        path=Path("/dev/null"),
        seed=None,
        shuffle_buffer=0,
        profile_name="DEFAULT",
        enabled=False,
    )
    have_voc = importlib.util.find_spec("defusedxml") is not None
    failures: list[str] = []
    skipped = 0
    for check in CHECKS:
        if check.local_tar is not None and not have_voc:
            skipped += 1
            continue
        report = Report(label=check.label)
        _check_row(check, _synthetic_row_for(check), 0, profile, report, recorder)
        if report.ok != 1:
            failures.append(f"{check.label}: {report.examples}")

    # Regression guard: a cell token may carry a Unicode line separator
    # (U+2028/U+2029/U+0085). The doctags round-trip adapter must parse the
    # whole serialized record, not splitlines()[0] (str.splitlines breaks on
    # those, slicing the JSON mid-string).
    line_sep = chr(0x2028)  # Unicode LINE SEPARATOR; str.splitlines() breaks on it
    tricky = _synthetic_docling_row()
    tricky["cells"] = [
        [
            {"tokens": ["a", line_sep, "b"], "bbox": [0, 0, 10, 5]},
            {"tokens": ["c"], "bbox": [10, 0, 20, 5]},
        ],
        [
            {"tokens": ["d"], "bbox": [0, 5, 10, 10]},
            {"tokens": ["e"], "bbox": [10, 5, 20, 10]},
        ],
    ]
    try:
        if "doctags" not in docling_to_doctags_payload(tricky):
            failures.append("doctags U+2028 guard: missing 'doctags' key")
    except (ValueError, TypeError, KeyError) as exc:
        failures.append(f"doctags U+2028 guard raised {type(exc).__name__}: {exc}")

    if failures:
        sys.stdout.write("SELF-TEST FAILED:\n" + "\n".join(failures) + "\n")
        return 1
    codecs_covered = sorted({c.codec.name for c in CHECKS})
    tail = f" ({skipped} local check(s) skipped: defusedxml absent)" if skipped else ""
    sys.stdout.write(
        f"self-test OK: {len(CHECKS) - skipped} checks across {len(codecs_covered)} codecs "
        f"read their adapted synthetic row and pass DEFAULT{tail}\n"
    )
    return 0


# ---------- CLI ----------


def _print_report(report: Report) -> None:
    sys.stdout.write(
        f"{report.label}: rows={report.rows} ok={report.ok} "
        f"parse_errors={report.parse_errors} validation_failures={report.validation_failures}\n"
    )
    for ex in report.examples:
        sys.stdout.write(f"    e.g. {ex}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=200, help="rows per check (0 = all)")
    parser.add_argument("--dataset", default=None, help="substring filter on dataset name")
    parser.add_argument("--profile", default="DEFAULT", help="validation profile")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="shuffle seed; omitted = a fresh random seed each run (random sampling)",
    )
    parser.add_argument(
        "--shuffle-buffer", type=int, default=1000, help="streaming shuffle buffer size"
    )
    parser.add_argument(
        "--no-shuffle",
        action="store_true",
        help="deterministic head-of-stream read (no random sampling)",
    )
    parser.add_argument(
        "--findings-dir",
        default="output/e2e_findings",
        help="directory for per-run JSONL findings records (for later audit)",
    )
    parser.add_argument("--no-record", action="store_true", help="do not write findings records")
    parser.add_argument("--list", action="store_true", help="list checks and exit")
    parser.add_argument("--self-test", action="store_true", help="network-free adapter check")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    selected = [
        c for c in CHECKS if args.dataset is None or args.dataset.lower() in c.dataset.lower()
    ]
    if args.list or not selected:
        for c in CHECKS:
            sys.stdout.write(f"{c.label}  ({c.dataset})\n")
        return 0

    # Random sampling by default: pick a fresh seed each run unless one is
    # given (or --no-shuffle requests a deterministic head read). The seed
    # is printed so any finding can be reproduced exactly.
    seed: int | None
    if args.no_shuffle:
        seed = None
    elif args.seed is not None:
        seed = args.seed
    else:
        seed = random.randrange(1_000_000)
    if seed is not None:
        sys.stdout.write(f"random sampling with --seed {seed} (buffer {args.shuffle_buffer})\n")

    profile = getattr(profiles, args.profile.upper())
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    recorder = FindingsRecorder(
        path=Path(args.findings_dir) / f"run-{stamp}.jsonl",
        seed=seed,
        shuffle_buffer=args.shuffle_buffer,
        profile_name=args.profile.upper(),
        enabled=not args.no_record,
    )
    try:
        reports = [
            run_check(
                c, args.limit, profile, recorder, seed=seed, shuffle_buffer=args.shuffle_buffer
            )
            for c in selected
        ]
    finally:
        recorder.close()
    for report in reports:
        _print_report(report)
    total_problems = sum(r.parse_errors + r.validation_failures for r in reports)
    if recorder.written:
        sys.stdout.write(f"recorded {recorder.written} finding(s) to {recorder.path}\n")
    return 1 if total_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
