import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DIR = Path(tempfile.mkdtemp(prefix="freelance-crm-"))
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DIR / 'test.db'}"

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
