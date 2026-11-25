import pytest

from pipeline.common import log


@pytest.fixture
def run_log(tmp_path):
    """A fresh run whose log goes to a temp file (never the real runs.jsonl)."""
    path = tmp_path / "runs.jsonl"
    log.start_run("test", log_path=path)
    yield path
    log._current = None
