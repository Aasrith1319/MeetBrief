import os
import tempfile
from pathlib import Path

import pytest

# unit tests exercise the rule-based pipeline; test_models.py turns the HF models on
os.environ.setdefault("MEETBRIEF_MODELS", "off")
os.environ["MEETBRIEF_DATA_DIR"] = tempfile.mkdtemp(prefix="meetbrief_test_")
os.environ["MEETBRIEF_API_TOKEN"] = "test-token"

from backend.capture.transcript_normalizer import parse_transcript, to_segments  # noqa: E402
from backend.memory.meeting_state import build_memory  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[2] / "datasets" / "sample_transcripts"


def load(name: str):
    segs = to_segments("t", parse_transcript((SAMPLES / name).read_text(), filename=name))
    return segs, build_memory("t", segs, {})


@pytest.fixture
def demo():
    return load("demo_indexing.txt")


@pytest.fixture
def sprint():
    return load("sprint_planning.txt")


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from backend.api import service
    from backend.database.db import Database, set_db
    from backend.main import app

    set_db(Database(str(tmp_path / "test.sqlite3")))
    service._cache.clear()
    with TestClient(app) as c:
        c.headers.update({"X-MeetBrief-Token": "test-token"})
        yield c
