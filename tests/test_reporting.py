"""Tests of the report helpers."""

from pathlib import Path

from evidence_curator.reporting import preserve_observations

PLACEHOLDER = "_Filled in after the run._"


def test_preserve_observations_keeps_hand_written_text(tmp_path: Path) -> None:
    """A section written by hand survives a rerun; a missing file or the placeholder yields the default."""
    report = tmp_path / "report.md"
    assert preserve_observations(report, PLACEHOLDER) == PLACEHOLDER
    report.write_text("# Report\n\nnumbers\n\n## Observations\n\n" + PLACEHOLDER + "\n")
    assert preserve_observations(report, PLACEHOLDER) == PLACEHOLDER
    report.write_text("# Report\n\nnumbers\n\n## Observations\n\n1. The parser output is mostly furniture.\n2. More.\n")
    assert preserve_observations(report, PLACEHOLDER) == "1. The parser output is mostly furniture.\n2. More."
    report.write_text("# Report without the section\n")
    assert preserve_observations(report, PLACEHOLDER) == PLACEHOLDER
