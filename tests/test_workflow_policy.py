"""Draft pull requests must skip CI and resume when marked ready."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("filename", ["ci.yaml", "benchmark.yaml"])
def test_pull_request_workflow_resumes_when_ready(filename: str) -> None:
    workflow = (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8")
    trigger = workflow.split("concurrency:", maxsplit=1)[0]
    assert re.search(r"^    types:.*\bready_for_review\b", trigger, re.MULTILINE)


@pytest.mark.parametrize("filename", ["ci.yaml", "benchmark.yaml"])
def test_every_pull_request_job_skips_drafts(filename: str) -> None:
    workflow = (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8")
    jobs = re.findall(
        r"^  ([\w-]+):\n(.*?)(?=^  [\w-]+:|\Z)",
        workflow.split("jobs:\n", maxsplit=1)[1],
        re.MULTILINE | re.DOTALL,
    )
    assert jobs
    missing = [
        name
        for name, body in jobs
        if not re.search(r"^    if:.*github.event.pull_request.draft == false", body, re.MULTILINE)
    ]
    assert missing == []
