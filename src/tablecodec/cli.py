"""Click-based command line interface (SPEC §12).

Optional: requires the ``[cli]`` extra (``pip install "tablecodec[cli]"``).
Importing this module without click installed will fail with a clear
``ImportError`` — by design, since the rest of the package must run
without click.

Subcommands implemented for M6:

- ``validate``    — run a profile against every record in a file.
- ``convert``     — re-encode a file from one codec to another.
- ``stats``       — print sample / cell / span counts.
- ``diff``        — record-by-record diff of two same-codec files.
- ``analyze-loss`` — static loss report for a codec pair.
- ``codecs list`` — list registered codec names.

All commands stream their input. Exit codes:

- ``0`` success / no findings.
- ``1`` validation failures, diff mismatches, or recoverable errors.
- ``2`` argument / usage error (click default).
"""

from __future__ import annotations

import dataclasses
import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import click

from tablecodec import codecs
from tablecodec import io as tio
from tablecodec.codecs._base import Codec
from tablecodec.codecs.builtins import BUILTIN_CODECS
from tablecodec.ir import TableSample
from tablecodec.loss import analyze_loss
from tablecodec.validate import Profile, profiles, validate

_PROFILE_NAMES = ["LENIENT", "DEFAULT", "PUBTABNET_2_0", "TABLEFORMER", "STRICT"]


def _ensure_builtins_registered() -> None:
    existing = set(codecs.list_codecs())
    for codec in BUILTIN_CODECS:
        if codec.name not in existing:
            codecs.register(codec)
    # SPEC §6.2: also pick up third-party codecs that self-register via the
    # `tablecodec.codecs` entry-point group (idempotent / no-op if none).
    codecs.load_plugins()


def _resolve_codec_name(name: str) -> Codec:
    try:
        return codecs.get(name)
    except KeyError as exc:
        msg = f"unknown codec {name!r}. Run `tablecodec codecs list` to see registered names."
        raise click.UsageError(msg) from exc


def _resolve_profile(name: str) -> Profile:
    upper = name.upper()
    if upper not in _PROFILE_NAMES:
        msg = f"unknown profile {name!r}. Available: {', '.join(_PROFILE_NAMES)}."
        raise click.UsageError(msg)
    profile: Profile = getattr(profiles, upper)
    return profile


@click.group()
@click.version_option(package_name="tablecodec")
def main() -> None:
    """tablecodec command-line interface."""
    _ensure_builtins_registered()


# ---------- validate ----------


@main.command("validate")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--profile",
    "profile_name",
    default="DEFAULT",
    show_default=True,
    help="Validation profile (see SPEC §8).",
)
@click.option(
    "--codec",
    "codec_name",
    default=None,
    help="Codec name; if omitted, auto-detect from the file.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def validate_cmd(source: Path, profile_name: str, codec_name: str | None, as_json: bool) -> None:
    """Validate every record in SOURCE against the chosen profile."""
    profile = _resolve_profile(profile_name)
    codec = _resolve_codec_name(codec_name) if codec_name else None
    findings: list[dict[str, Any]] = []
    sample_count = 0
    for sample_index, sample in enumerate(tio.open(source, codec=codec)):
        sample_count += 1
        for err in validate(sample, profile=profile):
            findings.append(
                {
                    "record": sample_index,
                    "filename": sample.filename,
                    "invariant": err.invariant,
                    "message": err.message,
                    "cell_index": err.cell_index,
                }
            )
    if as_json:
        click.echo(
            json.dumps(
                {
                    "source": str(source),
                    "profile": profile.name,
                    "sample_count": sample_count,
                    "findings": findings,
                },
                ensure_ascii=False,
            )
        )
    else:
        for finding in findings:
            click.echo(f"record={finding['record']} {finding['invariant']}: {finding['message']}")
        click.echo(f"checked {sample_count} record(s), {len(findings)} finding(s)")
    if findings:
        sys.exit(1)


# ---------- convert ----------


@main.command("convert")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("output_path", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--from", "from_codec", required=True, help="Source codec name.")
@click.option("--to", "to_codec", required=True, help="Target codec name.")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Do not read the input; print the static analyze_loss report and exit.",
)
def convert_cmd(
    input_path: Path,
    output_path: Path,
    from_codec: str,
    to_codec: str,
    dry_run: bool,
) -> None:
    """Re-encode INPUT_PATH from --from to --to, writing OUTPUT_PATH."""
    src = _resolve_codec_name(from_codec)
    tgt = _resolve_codec_name(to_codec)
    if dry_run:
        report = analyze_loss(source=from_codec, target=to_codec)
        click.echo(json.dumps(dataclasses.asdict(_serialize_report(report))))
        return
    written = _stream_convert(input_path, output_path, src, tgt)
    click.echo(f"wrote {written} record(s) to {output_path}")


def _stream_convert(input_path: Path, output_path: Path, src: Codec, tgt: Codec) -> int:
    written = 0

    def _consume() -> Iterator[TableSample]:
        nonlocal written
        with input_path.open(encoding="utf-8") as handle:
            for sample in src.read(handle):
                written += 1
                yield sample

    with output_path.open("w", encoding="utf-8") as sink:
        tgt.write(_consume(), sink)
    return written


@dataclasses.dataclass(frozen=True, slots=True)
class _SerializableReport:
    source: str
    target: str
    source_fields_dropped_on_read: list[str]
    ir_fields_unrepresentable_in_target: list[str]
    round_trip_classification: str


def _serialize_report(report: Any) -> _SerializableReport:
    return _SerializableReport(
        source=report.source,
        target=report.target,
        source_fields_dropped_on_read=sorted(report.source_fields_dropped_on_read),
        ir_fields_unrepresentable_in_target=sorted(report.ir_fields_unrepresentable_in_target),
        round_trip_classification=report.round_trip_classification,
    )


# ---------- stats ----------


@main.command("stats")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--codec",
    "codec_name",
    default=None,
    help="Codec name; if omitted, auto-detect.",
)
@click.option("--json", "as_json", is_flag=True)
def stats_cmd(source: Path, codec_name: str | None, as_json: bool) -> None:
    """Print sample / cell / spanned-cell counts for SOURCE."""
    codec = _resolve_codec_name(codec_name) if codec_name else None
    sample_count = 0
    cell_count = 0
    spanned_count = 0
    for sample in tio.open(source, codec=codec):
        sample_count += 1
        cell_count += len(sample.cells)
        spanned_count += sum(1 for c in sample.cells if c.rowspan != 1 or c.colspan != 1)
    payload = {
        "source": str(source),
        "samples": sample_count,
        "cells": cell_count,
        "spanned_cells": spanned_count,
    }
    if as_json:
        click.echo(json.dumps(payload))
    else:
        click.echo(f"samples: {sample_count}")
        click.echo(f"cells: {cell_count}")
        click.echo(f"spanned cells: {spanned_count}")


# ---------- diff ----------


@main.command("diff")
@click.argument("a_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("b_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--codec", "codec_name", default=None)
def diff_cmd(a_path: Path, b_path: Path, codec_name: str | None) -> None:
    """Record-by-record diff of A_PATH and B_PATH (same codec on both sides)."""
    codec = _resolve_codec_name(codec_name) if codec_name else None
    a_iter = tio.open(a_path, codec=codec)
    b_iter = tio.open(b_path, codec=codec)
    diffs = list(_iter_diffs(a_iter, b_iter))
    for index, side, sample in diffs:
        if side == "both":
            click.echo(f"differ @ record {index}: {sample}")
        elif side == "left-only":
            click.echo(f"only in A @ record {index}: filename={sample}")
        else:
            click.echo(f"only in B @ record {index}: filename={sample}")
    click.echo(f"{len(diffs)} difference(s)")
    if diffs:
        sys.exit(1)


def _iter_diffs(
    a: Iterable[TableSample], b: Iterable[TableSample]
) -> Iterator[tuple[int, str, str]]:
    a_it = iter(a)
    b_it = iter(b)
    index = 0
    while True:
        a_sample = next(a_it, None)
        b_sample = next(b_it, None)
        if a_sample is None and b_sample is None:
            return
        if a_sample is None:
            assert b_sample is not None  # narrows for pyright
            yield index, "right-only", b_sample.filename
        elif b_sample is None:
            yield index, "left-only", a_sample.filename
        elif a_sample != b_sample:
            yield index, "both", f"{a_sample.filename} != {b_sample.filename}"
        index += 1


# ---------- analyze-loss ----------


@main.command("analyze-loss")
@click.option("--from", "from_codec", required=True)
@click.option("--to", "to_codec", required=True)
def analyze_loss_cmd(from_codec: str, to_codec: str) -> None:
    """Static loss report for the FROM -> TO codec pair."""
    _resolve_codec_name(from_codec)
    _resolve_codec_name(to_codec)
    report = analyze_loss(source=from_codec, target=to_codec)
    click.echo(json.dumps(dataclasses.asdict(_serialize_report(report))))


# ---------- codecs list ----------


@main.group("codecs")
def codecs_group() -> None:
    """Inspect the in-process codec registry."""


@codecs_group.command("list")
def codecs_list_cmd() -> None:
    """List registered codec names."""
    for name in codecs.list_codecs():
        click.echo(name)


if __name__ == "__main__":  # pragma: no cover
    main()
