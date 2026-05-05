"""Shared fixtures for DARIO orchestrator tests."""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add orchestrator to path
ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))


@pytest.fixture
def test_db(tmp_path):
    """Fresh SQLite DB for each test."""
    from db import DB
    db_path = str(tmp_path / "test.db")
    db = DB(db_path=db_path)
    return db


@pytest.fixture
def populated_db(test_db):
    """DB with sample tasks."""
    test_db.create_task("T-001", "Brand positioning", project="test", skill="dario-brand", priority="critical")
    test_db.create_task("T-002", "Naming check", project="test", skill="dario-naming", priority="medium",
                        depends_on=["T-001"])
    test_db.create_task("T-003", "SEO audit", project="test", skill="seo-audit", priority="high")
    return test_db
