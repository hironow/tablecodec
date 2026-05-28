"""Tests for tablecodec.cli — click CliRunner exercises every subcommand."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from tablecodec import codecs
from tablecodec.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolate_registry() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    saved = codecs._snapshot()  # type: ignore[attr-defined]
    codecs._restore({})  # type: ignore[attr-defined]
    yield
    codecs._restore(saved)  # type: ignore[attr-defined]


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------- codecs list ----------


class TestCodecsList:
    def test_lists_every_builtin_codec(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["codecs", "list"])
        assert result.exit_code == 0
        for name in (
            "pubtabnet-1.0.0",
            "pubtabnet-2.0.0",
            "fintabnet",
            "tableformer",
            "tablebank",
            "pubtables-1m",
            "otsl-1.0.0",
            "doctags-tables",
        ):
            assert name in result.output


# ---------- analyze-loss ----------


class TestAnalyzeLoss:
    def test_json_report_for_pubtabnet_to_otsl(self, runner: CliRunner) -> None:
        result = runner.invoke(
            main,
            ["analyze-loss", "--from", "pubtabnet-2.0.0", "--to", "otsl-1.0.0"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["source"] == "pubtabnet-2.0.0"
        assert payload["target"] == "otsl-1.0.0"
        assert payload["round_trip_classification"] == "structure-preserving"
        assert "role" in payload["ir_fields_unrepresentable_in_target"]

    def test_unknown_codec_is_usage_error(self, runner: CliRunner) -> None:
        result = runner.invoke(
            main,
            ["analyze-loss", "--from", "no-such", "--to", "otsl-1.0.0"],
        )
        assert result.exit_code != 0


# ---------- validate ----------


class TestValidate:
    def test_passes_on_clean_file(self, runner: CliRunner) -> None:
        result = runner.invoke(
            main,
            [
                "validate",
                str(FIXTURES / "pubtabnet" / "simple_2x2.jsonl"),
                "--codec",
                "pubtabnet-2.0.0",
                "--profile",
                "DEFAULT",
            ],
        )
        assert result.exit_code == 0
        assert "0 finding(s)" in result.output

    def test_json_output(self, runner: CliRunner) -> None:
        result = runner.invoke(
            main,
            [
                "validate",
                str(FIXTURES / "pubtabnet" / "simple_2x2.jsonl"),
                "--codec",
                "pubtabnet-2.0.0",
                "--json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["sample_count"] == 1
        assert payload["findings"] == []

    def test_unknown_profile_is_usage_error(self, runner: CliRunner) -> None:
        result = runner.invoke(
            main,
            [
                "validate",
                str(FIXTURES / "pubtabnet" / "simple_2x2.jsonl"),
                "--codec",
                "pubtabnet-2.0.0",
                "--profile",
                "NOPE",
            ],
        )
        assert result.exit_code != 0


# ---------- stats ----------


class TestStats:
    def test_human_output(self, runner: CliRunner) -> None:
        result = runner.invoke(
            main,
            [
                "stats",
                str(FIXTURES / "pubtabnet" / "with_rowspan.jsonl"),
                "--codec",
                "pubtabnet-2.0.0",
            ],
        )
        assert result.exit_code == 0
        assert "samples: 1" in result.output
        assert "spanned cells: 1" in result.output

    def test_json_output(self, runner: CliRunner) -> None:
        result = runner.invoke(
            main,
            [
                "stats",
                str(FIXTURES / "pubtabnet" / "simple_2x2.jsonl"),
                "--codec",
                "pubtabnet-2.0.0",
                "--json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["samples"] == 1
        assert payload["cells"] == 4
        assert payload["spanned_cells"] == 0


# ---------- convert ----------


class TestConvert:
    def test_dry_run_does_not_open_inputs(self, runner: CliRunner, tmp_path: Path) -> None:
        # given — input doesn't even need to exist for --dry-run logic,
        # but click validates the path; supply a real file from fixtures.
        nonexistent_output = tmp_path / "out.jsonl"
        result = runner.invoke(
            main,
            [
                "convert",
                str(FIXTURES / "pubtabnet" / "simple_2x2.jsonl"),
                str(nonexistent_output),
                "--from",
                "pubtabnet-2.0.0",
                "--to",
                "otsl-1.0.0",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["round_trip_classification"] == "structure-preserving"
        # No output file should have been written under --dry-run.
        assert not nonexistent_output.exists()

    def test_writes_target_codec_output(self, runner: CliRunner, tmp_path: Path) -> None:
        out = tmp_path / "converted.jsonl"
        result = runner.invoke(
            main,
            [
                "convert",
                str(FIXTURES / "pubtabnet" / "simple_2x2.jsonl"),
                str(out),
                "--from",
                "pubtabnet-2.0.0",
                "--to",
                "otsl-1.0.0",
            ],
        )
        assert result.exit_code == 0
        assert out.exists()
        # First record of OTSL output should contain the otsl key.
        payload = json.loads(out.read_text().splitlines()[0])
        assert "otsl" in payload


# ---------- diff ----------


class TestDiff:
    def test_identical_files_have_no_diff(self, runner: CliRunner, tmp_path: Path) -> None:
        a = FIXTURES / "pubtabnet" / "simple_2x2.jsonl"
        b = tmp_path / "copy.jsonl"
        b.write_text(a.read_text())
        result = runner.invoke(main, ["diff", str(a), str(b), "--codec", "pubtabnet-2.0.0"])
        assert result.exit_code == 0
        assert "0 difference(s)" in result.output

    def test_different_files_exit_nonzero(self, runner: CliRunner, tmp_path: Path) -> None:
        a = FIXTURES / "pubtabnet" / "simple_2x2.jsonl"
        b = FIXTURES / "pubtabnet" / "with_rowspan.jsonl"
        result = runner.invoke(main, ["diff", str(a), str(b), "--codec", "pubtabnet-2.0.0"])
        assert result.exit_code != 0
        assert "difference(s)" in result.output
