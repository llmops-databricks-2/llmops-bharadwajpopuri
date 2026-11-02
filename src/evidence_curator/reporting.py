"""Small helpers for the Markdown reports the notebooks regenerate."""

from pathlib import Path

OBSERVATIONS_HEADING = "## Observations"


def preserve_observations(path: Path, default: str) -> str:
    """Return the Observations section already written in `path`, or `default` when there is none yet.

    The notebooks rewrite their reports on every run; the Observations are written by hand after
    reading them, so a rerun must carry them over rather than replace them with the placeholder.
    """
    if not path.exists():
        return default
    text = path.read_text()
    if OBSERVATIONS_HEADING not in text:
        return default
    section = text.split(OBSERVATIONS_HEADING, 1)[1].strip()
    if not section or section.startswith("_Filled in"):
        return default
    return section
