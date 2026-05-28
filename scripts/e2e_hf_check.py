#!/usr/bin/env python3
"""End-to-end check: stream Docling OTSL-family datasets through tablecodec.

Occasional / local-only (see docs/adr/0003). For each streamed row this
builds the canonical input of a target codec, runs the *actual*
``codec.read()``, and validates the resulting IR — so the risky logic
(square-table assumption, anchor/cell alignment, HTML structure parsing)
is exercised against real tables.

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
import io
import json
import logging
import os
import random
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Quiet the Hugging Face stack BEFORE `datasets` is imported (env vars are
# read at import time). Keeps the e2e output to our own summary lines.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("DATASETS_VERBOSITY", "error")

from tablecodec import profiles, validate  # noqa: E402
from tablecodec.codecs._base import Codec  # noqa: E402
from tablecodec.codecs.otsl import OTSL10Codec  # noqa: E402
from tablecodec.codecs.pubtabnet import PubTabNet20Codec  # noqa: E402


def _silence_hf_logging() -> None:
    """Raise log levels of the HF / network stack to ERROR (hide retries)."""
    for name in ("datasets", "huggingface_hub", "urllib3", "fsspec", "filelock"):
        logging.getLogger(name).setLevel(logging.ERROR)
    try:
        import datasets  # noqa: PLC0415

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


def docling_to_otsl_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": row.get("filename", "<docling>"),
        "split": row.get("split"),
        "imgid": row.get("imgid"),
        "otsl": list(row["otsl"]),
        "cells": flatten_cells(row["cells"]),
    }


def docling_to_html_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": row.get("filename", "<docling>"),
        "split": row.get("split"),
        "imgid": row.get("imgid"),
        "html": {
            "structure": {"tokens": list(row["html"])},
            "cells": flatten_cells(row["cells"]),
        },
    }


# ---------- check registry ----------


@dataclass(frozen=True, slots=True)
class Check:
    dataset: str
    split: str
    codec: Codec
    to_payload: Callable[[dict[str, Any]], dict[str, Any]]

    @property
    def label(self) -> str:
        short = self.dataset.split("/")[-1]
        return f"{short}[{self.split}] -> {self.codec.name}"


_OTSL = OTSL10Codec()
_PUBTABNET20 = PubTabNet20Codec()

CHECKS: tuple[Check, ...] = (
    Check("docling-project/PubTabNet_OTSL", "val", _OTSL, docling_to_otsl_payload),
    Check("docling-project/PubTabNet_OTSL", "val", _PUBTABNET20, docling_to_html_payload),
    Check("docling-project/FinTabNet_OTSL", "test", _OTSL, docling_to_otsl_payload),
    Check("docling-project/FinTabNet_OTSL", "test", _PUBTABNET20, docling_to_html_payload),
    Check("docling-project/PubTables-1M_OTSL", "val", _OTSL, docling_to_otsl_payload),
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


def _check_row(check: Check, row: dict[str, Any], profile: Any, report: Report) -> None:
    report.rows += 1
    try:
        payload = check.to_payload(row)
        line = json.dumps(payload, ensure_ascii=False)
        sample = next(iter(check.codec.read(io.StringIO(line))))
    except (KeyError, ValueError, TypeError, StopIteration) as exc:
        report.parse_errors += 1
        report.note(f"parse: {type(exc).__name__}: {exc}")
        return
    errors = validate(sample, profile=profile)
    if errors:
        report.validation_failures += 1
        report.note(f"validate: {errors[0].invariant}: {errors[0].message}")
    else:
        report.ok += 1


def run_check(
    check: Check,
    limit: int,
    profile: Any,
    *,
    seed: int | None = None,
    shuffle_buffer: int = 1000,
) -> Report:
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
        _check_row(check, row, profile, report)
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
            "<thead>", "<tr>", "<td>", "</td>", "<td>", "</td>", "</tr>", "</thead>",
            "<tbody>", "<tr>", "<td>", "</td>", "<td>", "</td>", "</tr>", "</tbody>",
        ],
        "cells": [
            [{"tokens": ["a"], "bbox": [0, 0, 10, 5]}, {"tokens": ["b"], "bbox": [10, 0, 20, 5]}],
            [{"tokens": ["c"], "bbox": [0, 5, 10, 10]}, {"tokens": ["d"], "bbox": [10, 5, 20, 10]}],
        ],
        "cols": 2,
        "rows": 2,
    }


def self_test() -> int:
    row = _synthetic_docling_row()
    profile = profiles.DEFAULT
    failures: list[str] = []
    for check in (
        Check("self/otsl", "val", _OTSL, docling_to_otsl_payload),
        Check("self/html", "val", _PUBTABNET20, docling_to_html_payload),
    ):
        report = Report(label=check.label)
        _check_row(check, row, profile, report)
        if report.ok != 1:
            failures.append(f"{check.label}: {report.examples}")
    if failures:
        sys.stdout.write("SELF-TEST FAILED:\n" + "\n".join(failures) + "\n")
        return 1
    sys.stdout.write("self-test OK: docling-row adapters round-trip through otsl + html codecs\n")
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
    reports = [
        run_check(c, args.limit, profile, seed=seed, shuffle_buffer=args.shuffle_buffer)
        for c in selected
    ]
    for report in reports:
        _print_report(report)
    total_problems = sum(r.parse_errors + r.validation_failures for r in reports)
    return 1 if total_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
